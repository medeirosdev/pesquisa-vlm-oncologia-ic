"""
Escolha dos patches com cota fixa por classe (estágio 2), testada com o modelo de linguagem decidindo a
classe. Ideia: em vez de mandar só os patches mais suspeitos, mandar um pacote com um número fixo de
patches de cada classe (benigno, atípico, DCIS, IC). No teste externo, a escolha dos mais suspeitos puxava,
nas lâminas benignas e atípicas, justamente os patches que o descritor erra (55 de 57 lâminas viraram malignas).

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas: as 61 lâminas do conjunto de VALIDAÇÃO oficial com embeddings prontos em 24/10
     (scripts/lista_validacao.txt menos BRACS_1003660 e BRACS_1003661); 25 pacientes; benigno 21,
     atípico 19, DCIS 9, IC 12. Nenhuma está nas 18 lâminas de desenvolvimento, nas 57 do teste externo
     nem nas RoIs de treino do descritor. As 57 do teste não são usadas.
  Patches: a amostra de 2.000 patches de tecido de cada lâmina (scripts/baixar_e_embutir.py), descritos
     pelo descritor "rois" de lamina_inteira.py (hierárquico, treinado nas RoIs de treino do BRACS).
     Classe de cada patch: benigno, atípico, DCIS ou IC (maior probabilidade no nível 1; se maligno, no
     nível 2). Confiança do patch na sua classe: P(categoria); pra DCIS e IC, P(maligno) x P(subtipo).
  Braços (mesmo descritor, mesmo modelo, mesmas instruções; só muda a evidência enviada):
     A "suspeitos" (como hoje): os 32 patches de maior 1 - P(benigno), com o filtro de diversidade do
        roteador; cabeçalho com as contagens dos 32 e o achado dominante, como no agregador.
     B "cotas": até 8 benignos, 6 atípicos, 6 DCIS e 6 IC (26), os de maior confiança dentro de cada classe,
        com o mesmo filtro de diversidade. Se a amostra tiver menos patches de uma classe que a cota, vão
        todos e o cabeçalho diz quantos havia. O cabeçalho avisa que as cotas são fixas e que o número de
        patches por classe no pacote não indica quanto há na lâmina.
     C "cotas + proporção": B + a proporção de cada classe entre todos os patches da amostra da lâmina.
     Nos três: a regra do componente invasivo do agregador (sobre os patches enviados) e nenhuma imagem
     (as lâminas foram apagadas depois dos embeddings).
  Modelo: Gemma 3 4B (temperature 0,2, seed 0, contexto 4096), instruções de sintese.py sem mudança,
     classificação extraída em JSON restrito às 4 opções (como no teste externo).
  Métrica principal: acurácia balanceada nas 4 classes (benigno, atípico, DCIS, IC).
  Critério de "funcionou": acurácia balanceada de C > A.
  Também reportado (sem critério): B; acerto por classe; classes preditas; subconjunto com uma lâmina por
     paciente; intervalo de 95% da diferença C - A por bootstrap agrupado por paciente (2.000 reamostragens,
     semente 0); quantos textos trazem a linha "CLASSIFICAÇÃO FINAL" e quantos concordam com a extração.

Uso (venv do projeto; a etapa sintetizar precisa do servidor Ollama no ar):
    .venv/bin/python validacao/pacote_cotas.py --etapa descrever    # descritor + prompts dos 3 braços (CPU)
    .venv/bin/python validacao/pacote_cotas.py --etapa sintetizar   # modelo de linguagem e avaliação
"""

import argparse
import csv
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
for sub in ("estagio2_roteador", "estagio3_descritores", "estagio4_agregacao", "estagio5_sintese"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / sub))

import numpy as np

from comum.lamina import RESULTADOS_DIR, dir_resultados, ler_caminhos
from comum.rois import info_lamina

LISTA = Path(__file__).resolve().parent.parent / "scripts" / "lista_validacao.txt"
FORA = {"BRACS_1003660", "BRACS_1003661"}
K_SUSPEITOS = 32
COTAS = {"benigno": 8, "atipico": 6, "DCIS": 6, "IC": 6}
CHAVE_NOME = {"benigno": ("benigno", None), "atipico": ("atipico", None), "DCIS": ("maligno", "DCIS"), "IC": ("maligno", "IC")}
BRACOS = ("A_suspeitos", "B_cotas", "C_cotas_proporcao")
MODELO = "gemma3:4b"
N_BOOTSTRAP = 2000
SAIDA = RESULTADOS_DIR / "pacote_cotas"


def laminas():
    return [s for s in (Path(l.strip()).stem for l in LISTA.read_text(encoding="utf-8").splitlines() if l.strip())
            if s not in FORA]


# ---------- etapa 1: descritor e prompts ----------
def descrever():
    from lamina_inteira import amostra, dados_descritor_rois, treinar_e_prever
    SAIDA.mkdir(parents=True, exist_ok=True)
    stems = laminas()
    X = [amostra(s) for s in stems]
    p1, p2 = treinar_e_prever(*dados_descritor_rois()(), np.concatenate(X))
    ini = 0
    for s, x in zip(stems, X):
        with open(dir_resultados(s, "uni2h") / "amostra2000_xy.csv", newline="", encoding="utf-8") as f:
            xy = np.array([(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)])
        assert len(xy) == len(x), s
        np.savez(SAIDA / f"{s}_probs.npz", p1=p1[ini:ini + len(x)], p2=p2[ini:ini + len(x)], xy=xy)
        ini += len(x)
        ps = patches(s)
        for braco in BRACOS:
            (SAIDA / f"{s}_{braco}_prompt.txt").write_text(montar(s, braco, ps), encoding="utf-8")
        print(f"  {s}: {len(x)} patches, {dict(Counter(d['classe'] for d in ps))}", flush=True)


def patches(s):
    return patches_de_probs(SAIDA / f"{s}_probs.npz")


def patches_de_probs(arquivo):
    from descritor_uni import NOMES, SUBTIPOS, texto_do_tile
    z = np.load(arquivo)
    saida = []
    for (x0, y0), a, b in zip(z["xy"], z["p1"], z["p2"]):
        cat, sub, texto = texto_do_tile(int(x0), int(y0), a, b)
        saida.append({"x0": int(x0), "y0": int(y0), "categoria": cat, "subtipo": sub, "classe": sub or cat,
                      "achados": [NOMES[(cat, sub)]], "texto": texto,
                      "confianca": float(a.max() * (b.max() if sub else 1.0)), "p_nao_benigno": float(1 - a[0]),
                      "prob_subtipo": dict(zip(SUBTIPOS, b.tolist())) if sub else None})
    return saida


def selecao(braco, ps):
    from roteador_topk import gate_diversidade
    if braco == "A_suspeitos":
        return gate_diversidade(sorted(ps, key=lambda d: -d["p_nao_benigno"]), K_SUSPEITOS)
    escolhidos = []
    for c, q in COTAS.items():
        escolhidos += gate_diversidade(sorted((d for d in ps if d["classe"] == c), key=lambda d: -d["confianca"]), q)
    return escolhidos


def montar(s, braco, ps):
    from agregador import linhas_componente_invasivo
    from descritor_uni import NOMES
    enviados, total = selecao(braco, ps), len(ps)
    linhas = ["=== Pré-laudo — evidência agregada (estágio 4) ===", f"Lâmina: {s}", "Descritor: rois", ""]
    if braco == "A_suspeitos":
        contagem = Counter(d["achados"][0] for d in enviados)
        cats = Counter(d["categoria"] for d in enviados)
        dominante, freq = contagem.most_common(1)[0]
        n = len(enviados)
        linhas += [f"Seleção: os {n} patches mais suspeitos (maior probabilidade de não ser benigno) entre {total} "
                   "patches de tecido sorteados da lâmina",
                   f"Patches analisados: {n}",
                   "Patches por categoria: " + ", ".join(f"{c} {cats.get(c, 0)}" for c in ("benigno", "atipico", "maligno")),
                   "Achados agregados:"]
        linhas += [f"  - {a}: {k}/{n} patches ({100 * k / n:.0f}%)" for a, k in contagem.most_common()]
        linhas += [f"Achado dominante: {dominante} ({100 * freq / n:.0f}% dos patches)"]
    else:
        na_amostra, no_pacote = Counter(d["classe"] for d in ps), Counter(d["classe"] for d in enviados)
        linhas += ["Seleção: pacote com cota fixa por classe prevista — até "
                   + ", ".join(f"{q} {NOMES[CHAVE_NOME[c]]}" for c, q in COTAS.items())
                   + f" —, os de maior confiança em cada classe, entre {total} patches de tecido sorteados da lâmina",
                   "Atenção: as cotas são fixas pelo desenho; o número de patches de cada classe no pacote NÃO indica "
                   "quanto dessa classe há na lâmina.",
                   f"Patches analisados: {len(enviados)}",
                   "Patches no pacote:"]
        for c, q in COTAS.items():
            m = na_amostra.get(c, 0)
            nota = "" if m >= q else (" (nenhum patch dessa classe na amostra)" if m == 0 else f" (só {m} patches dessa classe na amostra)")
            linhas.append(f"  - {NOMES[CHAVE_NOME[c]]}: {no_pacote.get(c, 0)} de {q}{nota}")
        if braco == "C_cotas_proporcao":
            linhas += [f"Proporção na lâmina inteira ({total} patches de tecido sorteados, cada um classificado pelo descritor):"]
            linhas += [f"  - {NOMES[CHAVE_NOME[c]]}: {na_amostra.get(c, 0)} patches ({100 * na_amostra.get(c, 0) / total:.1f}%)"
                       for c in COTAS]
    linhas += linhas_componente_invasivo(enviados)
    linhas += ["", "Detalhe por patch:"] + [d["texto"] for d in enviados]
    linhas += ["", "Âncoras visuais anexadas: nenhuma"]
    return "\n".join(linhas)


# ---------- etapa 2: modelo de linguagem e avaliação ----------
def sintetizar():
    import sintese
    from lamina_inteira import classe_final
    registro = SAIDA / "registro.json"
    feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
    for s in laminas():
        info = info_lamina(s)
        for braco in BRACOS:
            chave = f"{s}|{braco}"
            if chave in feito:
                continue
            prompt = (SAIDA / f"{s}_{braco}_prompt.txt").read_text(encoding="utf-8")
            t0 = time.time()
            r = sintese.chamar(MODELO, prompt, [])
            texto = r["message"]["content"]
            (SAIDA / f"{s}_{braco}.md").write_text(texto, encoding="utf-8")
            feito[chave] = {"lamina": s, "braco": braco, "real": classe_final(info["rotulo"]), "rotulo_bracs": info["rotulo"],
                            "predito": sintese.classificar_texto(MODELO, texto),
                            "linha_final": sintese.classificacao_final(texto),
                            "segundos": round(time.time() - t0, 1), "tokens_entrada": r.get("prompt_eval_count"),
                            "tokens_saida": r.get("eval_count")}
            registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {s} {braco}: predito {feito[chave]['predito']} | real {feito[chave]['real']} "
                  f"({feito[chave]['segundos']} s)", flush=True)
    avaliar(feito)


def pacientes():
    import openpyxl
    ws = openpyxl.load_workbook(Path(ler_caminhos()["laminas_dir"]) / "BRACS.xlsx", read_only=True)["WSI_Information"]
    return {r[0]: r[1] for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}


def metricas(feito, braco, stems):
    from lamina_inteira import FINAIS, acuracia_balanceada
    linhas = [feito[f"{s}|{braco}"] for s in stems]
    r, p = [l["real"] for l in linhas], [l["predito"] for l in linhas]
    return {"acuracia_balanceada": round(acuracia_balanceada(r, p), 3), "acertos": sum(a == b for a, b in zip(r, p)),
            "n": len(stems), "por_classe": {c: f"{sum(a == b == c for a, b in zip(r, p))}/{r.count(c)}" for c in FINAIS},
            "preditas": dict(Counter(map(str, p))),
            "com_linha_final": sum(l["linha_final"] is not None for l in linhas),
            "linha_final_concorda": sum(l["linha_final"] == l["predito"] for l in linhas)}


def bootstrap_diferenca(feito, stems):
    from lamina_inteira import acuracia_balanceada
    pac = pacientes()
    grupos = {}
    for s in stems:
        grupos.setdefault(pac[s], []).append(s)
    chaves, rng, difs = sorted(grupos), random.Random(0), []
    for _ in range(N_BOOTSTRAP):
        amostra = [s for g in (rng.choice(chaves) for _ in chaves) for s in grupos[g]]
        r = [feito[f"{s}|A_suspeitos"]["real"] for s in amostra]
        ba = {b: acuracia_balanceada(r, [feito[f"{s}|{b}"]["predito"] for s in amostra]) for b in ("A_suspeitos", "C_cotas_proporcao")}
        difs.append(ba["C_cotas_proporcao"] - ba["A_suspeitos"])
    return [round(float(np.percentile(difs, 2.5)), 3), round(float(np.percentile(difs, 97.5)), 3)]


def avaliar(feito):
    from prelaudo_teste_externo import um_por_paciente
    completas = [s for s in laminas() if all(f"{s}|{b}" in feito for b in BRACOS)]
    resumo = {"n_laminas_avaliadas": len(completas), "n_laminas_previstas": len(laminas()), "metricas": {}}
    for grupo, stems in (("todas", completas), ("um_por_paciente", um_por_paciente(completas))):
        for b in BRACOS:
            resumo["metricas"][f"{b}|{grupo}"] = metricas(feito, b, stems)
    ba = {b: resumo["metricas"][f"{b}|todas"]["acuracia_balanceada"] for b in BRACOS}
    resumo["ic95_diferenca_C_menos_A"] = bootstrap_diferenca(feito, completas)
    resumo["funcionou"] = ba["C_cotas_proporcao"] > ba["A_suspeitos"]
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, m in resumo["metricas"].items():
        print(f"{k:<34} bal {m['acuracia_balanceada']:.3f} | {m['acertos']}/{m['n']} | {m['por_classe']} | {m['preditas']} "
              f"| linha final {m['com_linha_final']}, concorda {m['linha_final_concorda']}")
    print(f"\nIC 95% da diferença C - A (bootstrap por paciente): {resumo['ic95_diferenca_C_menos_A']}")
    print(f"{len(completas)} de {len(laminas())} lâminas avaliadas. Critério fixado antes (C > A em acurácia balanceada): "
          f"{'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["descrever", "sintetizar"], required=True)
    a = p.parse_args()
    descrever() if a.etapa == "descrever" else sintetizar()
