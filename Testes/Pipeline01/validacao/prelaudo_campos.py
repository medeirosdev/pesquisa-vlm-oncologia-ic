"""
Modelo de linguagem só redige: a classe vem do classificador da lâmina inteira (classificador_lamina.py) e o
modelo escreve o pré-laudo a partir de campos fixos (classe, probabilidades, confiança, proporções, regiões).
Junto, uma checagem automática do texto: a classe e os números citados batem com a evidência?

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas: as 57 do teste externo.
  Campos (por lâmina): classe sugerida e probabilidades das 4 classes (classificador_lamina.py, treino nas 79);
     confiança: alta se P(classe sugerida) >= 0,70, moderada se >= 0,50, baixa abaixo; proporção de cada classe
     entre os patches da amostra (descritor "rois"); regiões: os 3 patches da classe sugerida com maior
     confiança (com o filtro de diversidade do roteador); se a classe sugerida for benigno, os 3 de maior
     P(não benigno), como "regiões a conferir".
  Modelo: Gemma 3 4B (temperature 0,2, seed 0, contexto 4096), instruções sintese.INSTRUCOES_REDACAO, sem imagens.
  Checagem automática (mesma regra pros textos novos e pros antigos):
     classe: extração em JSON restrito às 4 opções (sintese.classificar_texto) igual à classe sugerida;
     números: cada número do texto (fora coordenadas; inteiros sem % de 0 a 10 ignorados) é "sustentado" se
       aparece nos campos/evidência na mesma precisão, direto, x100 (probabilidade como %) ou /100; 128 (µm,
       das instruções) conta como sustentado;
     coordenadas: cada [x,y] do texto tem de existir nos campos/evidência.
  Comparação: os pré-laudos antigos das mesmas 57 (v2: modelo de linguagem decidindo, prompt
     estagio4_prompt_k32_uni_regra.txt, texto prelaudo_k32_uni_regra_gemma3-4b.md).
  Critério de "funcionou": classe extraída = classe sugerida em >= 90% dos textos novos E fração de números não
     sustentados (total do conjunto) nos textos novos <= a dos antigos.
  Também reportado (sem critério): coordenadas inventadas; números não sustentados por texto; acerto da classe
     final (= a do classificador).

Uso (venv do projeto; a etapa redigir precisa do servidor Ollama no ar):
    .venv/bin/python validacao/prelaudo_campos.py --etapa campos    # descritor + campos (CPU)
    .venv/bin/python validacao/prelaudo_campos.py --etapa redigir   # modelo de linguagem
    .venv/bin/python validacao/prelaudo_campos.py --etapa checar    # checagem automática e critério
"""

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
for sub in ("estagio2_roteador", "estagio3_descritores", "estagio5_sintese"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / sub))

import numpy as np

from comum.lamina import RESULTADOS_DIR, dir_resultados
from comum.rois import info_lamina

MODELO = "gemma3:4b"
N_REGIOES = 3
NOME_PT = {"benigno": "benigno", "atipico": "atípico", "DCIS": "DCIS", "IC": "carcinoma invasivo"}
SAIDA = RESULTADOS_DIR / "prelaudo_campos"


def confianca(p):
    return "alta" if p >= 0.70 else ("moderada" if p >= 0.50 else "baixa")


def selecao_regioes(ps, classe, k):
    from roteador_topk import gate_diversidade
    if classe == "benigno":
        return (gate_diversidade(sorted(ps, key=lambda d: -d["p_nao_benigno"]), k),
                "Regiões a conferir (patches com maior probabilidade de não serem benignos)")
    return (gate_diversidade(sorted((d for d in ps if d["classe"] == classe), key=lambda d: -d["confianca"]), k),
            f"Regiões para revisão prioritária (patches de {NOME_PT[classe]} com maior probabilidade)")


# ---------- etapa 1: campos ----------
def etapa_campos():
    from classificador_lamina import SAIDA as SAIDA_CLASSIFICADOR
    from lamina_inteira import FINAIS, amostra, dados_descritor_rois, laminas_teste, treinar_e_prever
    from pacote_cotas import patches_de_probs
    SAIDA.mkdir(parents=True, exist_ok=True)
    classif = json.loads((SAIDA_CLASSIFICADOR / "resumo.json").read_text(encoding="utf-8"))["por_lamina_teste"]
    teste = laminas_teste()
    treino = dados_descritor_rois()()
    for i in range(0, len(teste), 20):
        bloco = [s for s in teste[i:i + 20] if not (SAIDA / f"{s}_probs.npz").exists()]
        if not bloco:
            continue
        X = [amostra(s) for s in bloco]
        p1, p2 = treinar_e_prever(*treino, np.concatenate(X))
        ini = 0
        for s, x in zip(bloco, X):
            with open(dir_resultados(s, "uni2h") / "amostra2000_xy.csv", newline="", encoding="utf-8") as f:
                xy = np.array([(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)])
            np.savez(SAIDA / f"{s}_probs.npz", p1=p1[ini:ini + len(x)], p2=p2[ini:ini + len(x)], xy=xy)
            ini += len(x)
    for s in teste:
        ps = patches_de_probs(SAIDA / f"{s}_probs.npz")
        classe, probs = classif[s]["predito"], classif[s]["probabilidades"]
        pmax = probs[FINAIS.index(classe)]
        n = len(ps)
        cont = Counter(d["classe"] for d in ps)
        linhas = ["=== Campos para o pré-laudo ===", f"Lâmina: {s}",
                  f"Classe sugerida pelo classificador da lâmina: {NOME_PT[classe]}",
                  "Probabilidades do classificador: " + ", ".join(f"{NOME_PT[c]} {p:.2f}" for c, p in zip(FINAIS, probs)),
                  f"Confiança: {confianca(pmax)} (probabilidade da classe sugerida {pmax:.2f})",
                  f"Proporção entre os {n} patches de tecido sorteados da lâmina (classe prevista de cada patch):"]
        linhas += [f"  - {NOME_PT[c]}: {cont.get(c, 0)} patches ({100 * cont.get(c, 0) / n:.1f}%)" for c in FINAIS]
        regioes, rotulo = selecao_regioes(ps, classe, N_REGIOES)
        linhas += [f"{rotulo}:"] + [f"  {d['texto']}" for d in regioes]
        (SAIDA / f"{s}_campos.txt").write_text("\n".join(linhas), encoding="utf-8")
    print(f"campos de {len(teste)} lâminas em {SAIDA}")


# ---------- etapa 2: redigir ----------
def etapa_redigir():
    import sintese
    from lamina_inteira import classe_final, laminas_teste
    from classificador_lamina import SAIDA as SAIDA_CLASSIFICADOR
    classif = json.loads((SAIDA_CLASSIFICADOR / "resumo.json").read_text(encoding="utf-8"))["por_lamina_teste"]
    registro = SAIDA / "registro.json"
    feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
    for s in laminas_teste():
        if s in feito:
            continue
        campos = (SAIDA / f"{s}_campos.txt").read_text(encoding="utf-8")
        t0 = time.time()
        r = sintese.chamar(MODELO, campos, [], instrucoes=sintese.INSTRUCOES_REDACAO, lembrete="")
        texto = r["message"]["content"]
        (SAIDA / f"{s}.md").write_text(texto, encoding="utf-8")
        feito[s] = {"lamina": s, "classe_sugerida": classif[s]["predito"], "real": classe_final(info_lamina(s)["rotulo"]),
                    "classe_extraida": sintese.classificar_texto(MODELO, texto), "segundos": round(time.time() - t0, 1)}
        registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  {s}: sugerida {feito[s]['classe_sugerida']} | extraída {feito[s]['classe_extraida']} ({feito[s]['segundos']} s)", flush=True)


# ---------- etapa 3: checagem automática ----------
COORD = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]")
NUM = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?)(\s*%)?")


def numeros(texto):
    """[(valor, casas decimais, tem_%)] fora das coordenadas."""
    sem_coord = COORD.sub(" ", texto)
    saida = []
    for m in NUM.finditer(sem_coord):
        bruto = m.group(1).replace(",", ".")
        casas = len(bruto.split(".")[1]) if "." in bruto else 0
        saida.append((float(bruto), casas, bool(m.group(2))))
    return saida


def checar_texto(texto, evidencia):
    ev = {v for v, _, _ in numeros(evidencia)} | {128.0}
    coords_ev = set(COORD.findall(evidencia))
    checados, nao_sustentados = 0, []
    for v, casas, pct in numeros(texto):
        if casas == 0 and not pct and v <= 10:
            continue
        checados += 1
        ok = any(round(e, casas) == v or round(e * 100, casas) == v or round(e / 100, casas) == v for e in ev)
        if not ok:
            nao_sustentados.append(v)
    coords = COORD.findall(texto)
    return {"numeros_checados": checados, "nao_sustentados": nao_sustentados,
            "coordenadas": len(coords), "coordenadas_inventadas": [c for c in coords if c not in coords_ev]}


def etapa_checar():
    from lamina_inteira import FINAIS, acuracia_balanceada, classe_final, laminas_teste
    feito = json.loads((SAIDA / "registro.json").read_text(encoding="utf-8"))
    teste = [s for s in laminas_teste() if s in feito]
    novos, antigos = {}, {}
    for s in teste:
        novos[s] = checar_texto((SAIDA / f"{s}.md").read_text(encoding="utf-8"), (SAIDA / f"{s}_campos.txt").read_text(encoding="utf-8"))
        antigos[s] = checar_texto((dir_resultados(s, "estagio5") / "prelaudo_k32_uni_regra_gemma3-4b.md").read_text(encoding="utf-8"),
                                  (dir_resultados(s, "estagio4") / "estagio4_prompt_k32_uni_regra.txt").read_text(encoding="utf-8"))

    def total(ch):
        n = sum(c["numeros_checados"] for c in ch.values())
        ns = sum(len(c["nao_sustentados"]) for c in ch.values())
        nc = sum(c["coordenadas"] for c in ch.values())
        ci = sum(len(c["coordenadas_inventadas"]) for c in ch.values())
        return {"numeros_checados": n, "nao_sustentados": ns, "fracao_nao_sustentados": round(ns / n, 4) if n else None,
                "textos_com_numero_nao_sustentado": sum(bool(c["nao_sustentados"]) for c in ch.values()),
                "coordenadas": nc, "coordenadas_inventadas": ci}
    concorda = sum(feito[s]["classe_extraida"] == feito[s]["classe_sugerida"] for s in teste)
    r, p = [classe_final(info_lamina(s)["rotulo"]) for s in teste], [feito[s]["classe_sugerida"] for s in teste]
    resumo = {"n": len(teste), "classe_extraida_igual_sugerida": f"{concorda}/{len(teste)}",
              "fracao_concorda": round(concorda / len(teste), 3),
              "novos": total(novos), "antigos": total(antigos),
              "acuracia_balanceada_classe_final": round(acuracia_balanceada(r, p), 3),
              "por_classe": {c: f"{sum(a == b == c for a, b in zip(r, p))}/{r.count(c)}" for c in FINAIS},
              "por_lamina": {s: {"novo": novos[s], "antigo": antigos[s], **feito[s]} for s in teste}}
    fn, fa = resumo["novos"]["fracao_nao_sustentados"], resumo["antigos"]["fracao_nao_sustentados"]
    resumo["funcionou"] = resumo["fracao_concorda"] >= 0.90 and fn is not None and fa is not None and fn <= fa
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"classe extraída = sugerida: {resumo['classe_extraida_igual_sugerida']}")
    print(f"novos:   {resumo['novos']}\nantigos: {resumo['antigos']}")
    print(f"classe final (classificador): bal {resumo['acuracia_balanceada_classe_final']} {resumo['por_classe']}")
    print(f"Critério fixado antes (concorda >= 90% e não sustentados novos <= antigos): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["campos", "redigir", "checar"], required=True)
    a = p.parse_args()
    {"campos": etapa_campos, "redigir": etapa_redigir, "checar": etapa_checar}[a.etapa]()
