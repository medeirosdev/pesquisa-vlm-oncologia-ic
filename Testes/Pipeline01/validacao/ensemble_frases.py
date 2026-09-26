"""
Ensemble de frases (sugestão do Prof. João), refeito com as métricas atuais. Cada frase é escrita
em 5 versões (TEMPLATES_ENSEMBLE: "{}", "histopathology image showing {}", ...) e o embedding de
texto é a média das 5. O teste de 16/09 foi numa lâmina só, com a métrica "achado dominante".

Fixado ANTES de rodar (commit anterior aos resultados):
  A. DCIS vs. IC: tiles do teste do CellViT/UNI2-h (BRACS_748, BRACS_773, BRACS_295; >= 20 núcleos
     neoplásicos). Pontuação = máx. similaridade com o banco IC − máx. com o banco DCIS
     (BANCO_POR_CLASSE), com e sem ensemble. AUC por lâmina.
     "Ensemble ajuda" = AUC maior nas TRÊS lâminas.
  B. Benigno / atípico / maligno: BANCO_DESCRITOR atual, categoria = a da frase mais similar, com e
     sem ensemble; todos os tiles rotulados. Acerto por categoria e média, nas 8 lâminas novas e nas 16.
     "Ensemble ajuda" = média nas 8 novas sobe >= 0,5 ponto (mesma regra das trocas de frase).

Uso (venv do projeto):
    .venv/bin/python validacao/ensemble_frases.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from comum.bancos import BANCO_POR_CLASSE, CATEGORIA_DA_CLASSE, TEMPLATES_ENSEMBLE
from comum.lamina import RESULTADOS_DIR, dir_resultados
from comum.modelo import carregar_embeddings_cacheados, codificar_textos
from comum.rois import carregar_rois, rotular_tiles
from dcis_ic_nucleos import LAMINAS, amostra_da_lamina, auc, medidas_do_tile
from descritores import categorias, similaridades
from teste_fora_da_amostra import PRIMEIRA_LEVA, SEGUNDA_LEVA

VERSOES = {"sem_ensemble": ("{}",), "ensemble": tuple(TEMPLATES_ENSEMBLE)}
CATEGORIAS = ["benigno", "atipico", "maligno"]


def teste_a():
    res = {}
    for s in LAMINAS:
        embs, xy = carregar_embeddings_cacheados(dir_resultados(s, "estagio2"))
        pos = {p: i for i, p in enumerate(xy)}
        pasta = dir_resultados(s, "nucleos")
        tiles = [r for r in amostra_da_lamina(s)
                 if medidas_do_tile(json.loads((pasta / f"nucleos_{r['x0']}_{r['y0']}.json").read_text())["nucleos"])]
        e = embs[[pos[(r["x0"], r["y0"])] for r in tiles]]
        y = np.array([r["classe_real"] == "IC" for r in tiles])
        res[s] = {}
        for nome, templates in VERSOES.items():
            ic = (e @ codificar_textos(BANCO_POR_CLASSE["IC"], templates).cpu().numpy().T).max(1)
            dc = (e @ codificar_textos(BANCO_POR_CLASSE["DCIS"], templates).cpu().numpy().T).max(1)
            res[s][nome] = auc((ic - dc)[y], (ic - dc)[~y])
    res["ajuda"] = all(res[s]["ensemble"] > res[s]["sem_ensemble"] for s in LAMINAS)
    return res


def acertos(reais, preditas):
    tot, cert = Counter(reais), Counter(r for r, p in zip(reais, preditas) if r == p)
    por = {c: round(100 * cert[c] / tot[c], 1) for c in CATEGORIAS if tot[c]}
    return {**por, "media": round(sum(por.values()) / len(por), 2)}


def teste_b():
    reais, pred = {}, {n: {} for n in VERSOES}
    for s in PRIMEIRA_LEVA + SEGUNDA_LEVA:
        embs, xy = carregar_embeddings_cacheados(dir_resultados(s, "estagio2"))
        rot = rotular_tiles(xy, [r for r in carregar_rois(s) if r["correlacao"] >= 0.5])
        e = embs[[r["idx"] for r in rot]]
        reais[s] = [CATEGORIA_DA_CLASSE[r["classe_real"]] for r in rot]
        for nome in VERSOES:
            pred[nome][s] = categorias(similaridades(e, ensemble=(nome == "ensemble")))
    res = {}
    for grupo, stems in (("novas", SEGUNDA_LEVA), ("todas_16", PRIMEIRA_LEVA + SEGUNDA_LEVA)):
        r = [c for s in stems for c in reais[s]]
        res[grupo] = {n: acertos(r, [c for s in stems for c in pred[n][s]]) for n in VERSOES}
    res["ajuda"] = res["novas"]["ensemble"]["media"] - res["novas"]["sem_ensemble"]["media"] >= 0.5
    return res


def main():
    a, b = teste_a(), teste_b()
    (RESULTADOS_DIR / "ensemble_frases.json").write_text(json.dumps({"A_dcis_ic": a, "B_categorias": b}, indent=2,
                                                                    ensure_ascii=False), encoding="utf-8")
    print("A. DCIS vs. IC, AUC (sem ensemble -> com ensemble)")
    for s in LAMINAS:
        print(f"  {s:<12} {a[s]['sem_ensemble']} -> {a[s]['ensemble']}")
    print(f"  Critério (sobe nas três): {'SIM' if a['ajuda'] else 'NÃO'}")
    print("\nB. Benigno / atípico / maligno (benigno / atípico / maligno / média)")
    for g in ("novas", "todas_16"):
        for n in VERSOES:
            x = b[g][n]
            print(f"  {g:<9} {n:<13} {x['benigno']:>5} / {x['atipico']:>5} / {x['maligno']:>5} / média {x['media']}")
    print(f"  Critério (média nas 8 novas sobe >= 0,5): {'SIM' if b['ajuda'] else 'NÃO'}")


if __name__ == "__main__":
    main()
