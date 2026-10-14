"""
Descritor hierárquico (estagio3_descritores/descritor_uni.py) avaliado nos tiles rotulados:
nível 1 benigno / atípico / maligno, nível 2 DCIS / IC se maligno. A resposta final tem 4 classes:
benigno, atípico, DCIS, IC.

Fixado ANTES de rodar (commit anterior aos resultados):
  - Lâminas: as 16 da primeira e segunda leva + BRACS_773 e BRACS_295 (18). Tiles: todos os
    rotulados (rotular_tiles, RoIs com correlação >= 0,5). Classe final: N, PB -> benigno;
    UDH, FEA, ADH -> atípico; DCIS; IC.
  - UNI2-h: as duas camadas de descritor_uni.prever_hierarquico, treinadas nas outras 17 lâminas.
  - Referência, a mesma hierarquia com frases (zero-shot, QuiltNet): nível 1 = categoria do
    descritor atual (BANCO_DESCRITOR); nível 2 = máx. similaridade com o banco IC vs. o banco DCIS
    (BANCO_POR_CLASSE).
  - Métrica: acerto por classe final, somando as 18 lâminas, e a média das 4 (acaso = 25%).
    Também por grupo (1ª leva, 2ª leva, DCIS+IC).
  - Critério de "funcionou": média das 4 classes, nas 18 lâminas, UNI2-h > frases.

Uso (venv do projeto):
    .venv/bin/python validacao/hierarquia_uni.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from comum.bancos import BANCO_POR_CLASSE
from comum.lamina import RESULTADOS_DIR, dir_resultados
from comum.modelo import carregar_embeddings_cacheados, codificar_textos
from comum.rois import carregar_rois, rotular_tiles
from descritor_uni import CATEGORIAS, LAMINAS_DCIS_IC, LAMINAS_TREINO, SUBTIPOS, prever_hierarquico, rotulados
from descritores import categorias, similaridades
from teste_fora_da_amostra import PRIMEIRA_LEVA, SEGUNDA_LEVA

FINAIS = ["benigno", "atipico", "DCIS", "IC"]


def classe_final(classe_bracs):
    return {"N": "benigno", "PB": "benigno", "UDH": "atipico", "FEA": "atipico", "ADH": "atipico"}.get(classe_bracs,
                                                                                                    classe_bracs)


def final_de(cat, sub):
    return sub if cat == "maligno" else cat


def frases(stem):
    """Hierarquia zero-shot nos tiles rotulados, na mesma ordem de rotulados()."""
    embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rot = rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
    e = embs[[r["idx"] for r in rot]]
    cats = categorias(similaridades(e))
    ic = (e @ codificar_textos(BANCO_POR_CLASSE["IC"]).cpu().numpy().T).max(1)
    dc = (e @ codificar_textos(BANCO_POR_CLASSE["DCIS"]).cpu().numpy().T).max(1)
    return [final_de(c, "IC" if a > b else "DCIS") for c, a, b in zip(cats, ic, dc)]


def acertos(reais, preditas):
    tot, cert = Counter(reais), Counter(r for r, p in zip(reais, preditas) if r == p)
    por = {c: round(100 * cert[c] / tot[c], 1) for c in FINAIS if tot[c]}
    return {**por, "media": round(sum(por.values()) / len(por), 2), "n": {c: tot[c] for c in FINAIS}}


def main():
    D = {s: rotulados(s) for s in LAMINAS_TREINO}
    reais, uni, zs = {}, {}, {}
    for s in LAMINAS_TREINO:
        p1, p2 = prever_hierarquico([D[o] for o in LAMINAS_TREINO if o != s], D[s]["uni2h"])
        uni[s] = [final_de(CATEGORIAS[a], SUBTIPOS[b]) for a, b in zip(p1.argmax(1), p2.argmax(1))]
        zs[s] = frases(s)
        reais[s] = [classe_final(c) for c in D[s]["classe"]]
        print(f"  {s}: {len(reais[s])} tiles", flush=True)

    resumo = {}
    for grupo, stems in (("todas_18", LAMINAS_TREINO), ("primeira_leva", PRIMEIRA_LEVA),
                         ("segunda_leva", SEGUNDA_LEVA), ("dcis_ic", LAMINAS_DCIS_IC)):
        r = [c for s in stems for c in reais[s]]
        resumo[grupo] = {"uni2h": acertos(r, [c for s in stems for c in uni[s]]),
                         "frases": acertos(r, [c for s in stems for c in zs[s]])}
    mal = [(a, b) for s in LAMINAS_TREINO for a, b in zip(reais[s], uni[s]) if a in SUBTIPOS]
    resumo["uni2h_confusao_dos_malignos"] = {a: dict(Counter(b for x, b in mal if x == a)) for a in SUBTIPOS}
    resumo["funcionou"] = resumo["todas_18"]["uni2h"]["media"] > resumo["todas_18"]["frases"]["media"]
    (RESULTADOS_DIR / "hierarquia_uni.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nAcerto por classe final (benigno / atípico / DCIS / IC / média; acaso = 25%)")
    for g in ("todas_18", "primeira_leva", "segunda_leva", "dcis_ic"):
        print(f"  {g}  {resumo[g]['uni2h']['n']}")
        for m in ("frases", "uni2h"):
            a = resumo[g][m]
            print(f"    {m:<7} " + " / ".join(f"{a.get(c, '—'):>5}" for c in FINAIS) + f" / média {a['media']}")
    print("\nMalignos (UNI2-h):", resumo["uni2h_confusao_dos_malignos"])
    print(f"Critério fixado antes (média nas 18, UNI2-h > frases): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
