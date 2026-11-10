"""
Pré-laudo com o MIL: a classe vem do MIL com atenção (mil_atencao.py) e as regiões citadas são os patches de maior
atenção, os que mais pesaram na decisão. O modelo de linguagem só redige, como em prelaudo_campos.py.

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas: as 57 do teste externo.
  Campos: classe sugerida e probabilidades das 4 classes do MIL; confiança (alta >= 0,70, moderada >= 0,50, baixa);
     proporção de cada classe entre os patches da amostra (descritor com negativos e rótulo oficial, probabilidades
     de concentracao_espacial.py); regiões: os 3 patches de maior atenção (filtro de diversidade do roteador), cada
     um com a descrição do descritor, apresentados como "regiões que mais pesaram na decisão".
  Modelo, instruções (sintese.INSTRUCOES_REDACAO) e checagem automática: os de prelaudo_campos.py, sem mudança.
  Critério de "funcionou": classe extraída = classe sugerida em >= 90% dos textos E fração de números sem
     sustentação <= a dos pré-laudos antigos (modelo decidindo).
  Também reportado (sem critério): acerto da classe final (a do MIL); nas lâminas de teste atípicas, DCIS ou IC
     com lesão anotada, fração das regiões citadas que caem na lesão, comparada com as regiões de
     prelaudo_campos.py (escolhidas pelo descritor).

Uso (venv do projeto; a etapa redigir precisa do servidor Ollama no ar):
    .venv/bin/python validacao/prelaudo_mil.py --etapa campos
    .venv/bin/python validacao/prelaudo_mil.py --etapa redigir
    .venv/bin/python validacao/prelaudo_mil.py --etapa checar
"""

import argparse
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
SAIDA = RESULTADOS_DIR / "prelaudo_mil"


def regioes_de_atencao(s):
    from pacote_cotas import patches_de_probs
    from roteador_topk import gate_diversidade
    ps = patches_de_probs(RESULTADOS_DIR / "concentracao_espacial" / "probs" / f"{s}_probs.npz")
    att = np.load(RESULTADOS_DIR / "mil_atencao" / f"{s}_atencao.npy")
    for d, a in zip(ps, att):
        d["atencao"] = float(a)
    return ps, gate_diversidade(sorted(ps, key=lambda d: -d["atencao"]), N_REGIOES)


def etapa_campos():
    from lamina_inteira import FINAIS, laminas_teste
    from prelaudo_campos import NOME_PT, confianca
    SAIDA.mkdir(parents=True, exist_ok=True)
    mil = json.loads((RESULTADOS_DIR / "mil_atencao" / "resumo.json").read_text(encoding="utf-8"))["por_lamina"]
    for s in laminas_teste():
        classe, probs = mil[s]["predito"], mil[s]["probabilidades"]
        pmax = probs[FINAIS.index(classe)]
        ps, regioes = regioes_de_atencao(s)
        n, cont = len(ps), Counter(d["classe"] for d in ps)
        linhas = ["=== Campos para o pré-laudo ===", f"Lâmina: {s}",
                  f"Classe sugerida pelo classificador da lâmina: {NOME_PT[classe]}",
                  "Probabilidades do classificador: " + ", ".join(f"{NOME_PT[c]} {p:.2f}" for c, p in zip(FINAIS, probs)),
                  f"Confiança: {confianca(pmax)} (probabilidade da classe sugerida {pmax:.2f})",
                  f"Proporção entre os {n} patches de tecido sorteados da lâmina (classe prevista de cada patch):"]
        linhas += [f"  - {NOME_PT[c]}: {cont.get(c, 0)} patches ({100 * cont.get(c, 0) / n:.1f}%)" for c in FINAIS]
        linhas += ["Regiões que mais pesaram na decisão do classificador (descrição de cada patch):"]
        linhas += [f"  {d['texto']}" for d in regioes]
        (SAIDA / f"{s}_campos.txt").write_text("\n".join(linhas), encoding="utf-8")
    print(f"campos de {len(laminas_teste())} lâminas em {SAIDA}")


def etapa_redigir():
    import sintese
    from lamina_inteira import laminas_teste
    mil = json.loads((RESULTADOS_DIR / "mil_atencao" / "resumo.json").read_text(encoding="utf-8"))["por_lamina"]
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
        feito[s] = {"lamina": s, "classe_sugerida": mil[s]["predito"],
                    "classe_extraida": sintese.classificar_texto(MODELO, texto), "segundos": round(time.time() - t0, 1)}
        registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  {s}: sugerida {feito[s]['classe_sugerida']} | extraída {feito[s]['classe_extraida']} ({feito[s]['segundos']} s)", flush=True)


def regioes_na_lesao(arquivo_campos, s):
    from atencao_nas_lesoes import na_lesao, poligonos_de_lesao
    polis = poligonos_de_lesao(s)
    if not polis:
        return None
    coords = re.findall(r"^\s+\[(\d+),(\d+)\]", Path(arquivo_campos).read_text(encoding="utf-8"), flags=re.M)
    if not coords:
        return None
    return na_lesao(np.array(coords, float), polis).tolist()


def etapa_checar():
    from lamina_inteira import FINAIS, acuracia_balanceada, classe_final, laminas_teste
    from prelaudo_campos import SAIDA as SAIDA_CAMPOS
    from prelaudo_campos import checar_texto
    feito = json.loads((SAIDA / "registro.json").read_text(encoding="utf-8"))
    teste = [s for s in laminas_teste() if s in feito]
    novos, antigos, lesao_mil, lesao_desc = {}, {}, [], []
    for s in teste:
        novos[s] = checar_texto((SAIDA / f"{s}.md").read_text(encoding="utf-8"), (SAIDA / f"{s}_campos.txt").read_text(encoding="utf-8"))
        antigos[s] = checar_texto((dir_resultados(s, "estagio5") / "prelaudo_k32_uni_regra_gemma3-4b.md").read_text(encoding="utf-8"),
                                  (dir_resultados(s, "estagio4") / "estagio4_prompt_k32_uni_regra.txt").read_text(encoding="utf-8"))
        if classe_final(info_lamina(s)["rotulo"]) != "benigno":
            a, b = regioes_na_lesao(SAIDA / f"{s}_campos.txt", s), regioes_na_lesao(SAIDA_CAMPOS / f"{s}_campos.txt", s)
            if a is not None and b is not None:
                lesao_mil += a
                lesao_desc += b

    def total(ch):
        n = sum(c["numeros_checados"] for c in ch.values())
        ns = sum(len(c["nao_sustentados"]) for c in ch.values())
        return {"numeros_checados": n, "nao_sustentados": ns, "fracao_nao_sustentados": round(ns / n, 4) if n else None,
                "coordenadas": sum(c["coordenadas"] for c in ch.values()),
                "coordenadas_inventadas": sum(len(c["coordenadas_inventadas"]) for c in ch.values())}
    concorda = sum(feito[s]["classe_extraida"] == feito[s]["classe_sugerida"] for s in teste)
    r = [classe_final(info_lamina(s)["rotulo"]) for s in teste]
    p = [feito[s]["classe_sugerida"] for s in teste]
    resumo = {"n": len(teste), "classe_extraida_igual_sugerida": f"{concorda}/{len(teste)}",
              "fracao_concorda": round(concorda / len(teste), 3), "novos": total(novos), "antigos": total(antigos),
              "acuracia_balanceada_classe_final": round(acuracia_balanceada(r, p), 3),
              "acertos_classe_final": f"{sum(a == b for a, b in zip(r, p))}/{len(teste)}",
              "por_classe": {c: f"{sum(a == b == c for a, b in zip(r, p))}/{r.count(c)}" for c in FINAIS},
              "regioes_citadas_na_lesao": {"mil_atencao": f"{sum(lesao_mil)}/{len(lesao_mil)}",
                                           "descritor": f"{sum(lesao_desc)}/{len(lesao_desc)}"},
              "segundos_medio": round(float(np.mean([feito[s]["segundos"] for s in teste])), 1),
              "por_lamina": {s: {"novo": novos[s], **feito[s]} for s in teste}}
    fn, fa = resumo["novos"]["fracao_nao_sustentados"], resumo["antigos"]["fracao_nao_sustentados"]
    resumo["funcionou"] = resumo["fracao_concorda"] >= 0.90 and fn is not None and fa is not None and fn <= fa
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"classe extraída = sugerida: {resumo['classe_extraida_igual_sugerida']}")
    print(f"novos:   {resumo['novos']}\nantigos: {resumo['antigos']}")
    print(f"classe final (MIL): bal {resumo['acuracia_balanceada_classe_final']} {resumo['acertos_classe_final']} {resumo['por_classe']}")
    print(f"regiões citadas dentro da lesão anotada: {resumo['regioes_citadas_na_lesao']}")
    print(f"Critério fixado antes (concorda >= 90% e não sustentados novos <= antigos): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["campos", "redigir", "checar"], required=True)
    a = p.parse_args()
    {"campos": etapa_campos, "redigir": etapa_redigir, "checar": etapa_checar}[a.etapa]()
