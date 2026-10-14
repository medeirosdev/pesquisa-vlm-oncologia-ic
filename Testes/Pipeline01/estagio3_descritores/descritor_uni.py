"""
Estágio 3 — descritor hierárquico com o UNI2-h (sugestão do Prof. João: primeiro a categoria,
depois a evidência).

Para cada tile selecionado pelo estágio 2:
  nível 1: benigno / atípico / maligno — logística sobre o embedding do UNI2-h;
  nível 2: só se maligno, DCIS ou IC — segunda logística, treinada só em tiles DCIS e IC.
O resultado vira texto por uma tabela fixa (NOMES), com as probabilidades:
    [x0,y0] (maligno 0.93) invasive carcinoma 0.88

As camadas usadas numa lâmina são treinadas nos tiles rotulados das OUTRAS lâminas (nunca na
própria), pra a descrição não vir de um modelo que viu aquela lâmina.

Saída no mesmo formato do descritor por frases (descritores.py), com sufixo "_uni", pra o
estágio 4 ler sem mudança: resultados/<lamina>/estagio3/estagio3_descritores_k{k}_uni.json

Uso (venv do projeto):
    .venv/bin/python estagio3_descritores/descritor_uni.py --svs BRACS_748 --k 32
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validacao"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio2_roteador"))

import numpy as np

from categoria_uni import logistica_multinomial
from comum.bancos import CATEGORIA_DA_CLASSE
from comum.lamina import Lamina, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import carregar_rois, rotular_tiles
from comum.uni import embeddings_uni2h
from roteador_topk import gate_diversidade
from teste_fora_da_amostra import PRIMEIRA_LEVA, SEGUNDA_LEVA

CATEGORIAS = ["benigno", "atipico", "maligno"]
SUBTIPOS = ["DCIS", "IC"]
LAMINAS_DCIS_IC = ["BRACS_773", "BRACS_295"]
LAMINAS_TREINO = PRIMEIRA_LEVA + SEGUNDA_LEVA + LAMINAS_DCIS_IC
NOMES = {("benigno", None): "benign tissue",
         ("atipico", None): "atypical epithelial lesion",
         ("maligno", "DCIS"): "ductal carcinoma in situ",
         ("maligno", "IC"): "invasive carcinoma"}


def rotulados(stem):
    """Tiles rotulados da lâmina: embeddings do UNI2-h, categoria (0-2) e classe BRACS."""
    _, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rot = rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
    emb = embeddings_uni2h(Lamina(resolver_svs(stem)), [(r["x0"], r["y0"]) for r in rot], "rotulados")
    classes = [r["classe_real"] for r in rot]
    return {"uni2h": emb, "classe": classes,
            "categoria": np.array([CATEGORIAS.index(CATEGORIA_DA_CLASSE[c]) for c in classes])}


def prever_hierarquico(treino, X):
    """Probabilidades de nível 1 [n, 3] e de nível 2 [n, 2] (P(DCIS), P(IC)) pra os embeddings X,
    com camadas treinadas nos dados `treino` (lista de saídas de rotulados())."""
    X1 = np.concatenate([d["uni2h"] for d in treino])
    y1 = np.concatenate([d["categoria"] for d in treino])
    p1 = logistica_multinomial(X1, y1, X, k=3, probabilidades=True)
    sel = [(d["uni2h"][i], SUBTIPOS.index(c)) for d in treino for i, c in enumerate(d["classe"]) if c in SUBTIPOS]
    X2, y2 = np.array([s[0] for s in sel]), np.array([s[1] for s in sel])
    p2 = logistica_multinomial(X2, y2, X, k=2, probabilidades=True)
    return p1, p2


def texto_do_tile(x0, y0, p1, p2):
    cat = CATEGORIAS[int(np.argmax(p1))]
    sub = SUBTIPOS[int(np.argmax(p2))] if cat == "maligno" else None
    texto = f"[{x0},{y0}] ({cat} {p1.max():.2f}) {NOMES[(cat, sub)]}"
    if sub:
        texto += f" {p2.max():.2f}"
    return cat, sub, texto


def rodar(svs=None, k=32) -> dict:
    lamina = Lamina(resolver_svs(svs))
    stem = lamina.stem
    e2, saida = dir_resultados(stem, "estagio2"), dir_resultados(stem, "estagio3")
    with open(e2 / "estagio2_scores_v2.csv", newline="", encoding="utf-8") as f:
        ordenados = sorted(({"x0": int(r["x0"]), "y0": int(r["y0"]), "score": float(r["score"])}
                            for r in csv.DictReader(f)), key=lambda c: -c["score"])
    selecionados = gate_diversidade(ordenados, k)
    X = embeddings_uni2h(lamina, [(s["x0"], s["y0"]) for s in selecionados], f"selecionados_k{k}")

    treino = [rotulados(s) for s in LAMINAS_TREINO if s != stem]
    p1, p2 = prever_hierarquico(treino, X)

    descritores = []
    for s, a, b in zip(selecionados, p1, p2):
        cat, sub, texto = texto_do_tile(s["x0"], s["y0"], a, b)
        descritores.append({"x0": s["x0"], "y0": s["y0"], "categoria": cat, "subtipo": sub,
                            "achados": [NOMES[(cat, sub)]], "texto": texto,
                            "prob_categoria": dict(zip(CATEGORIAS, np.round(a, 3).tolist())),
                            "prob_subtipo": dict(zip(SUBTIPOS, np.round(b, 3).tolist())) if sub else None,
                            "score_roteador": round(s["score"], 3), "tokens_estimados": len(texto.split())})
    achados = Counter(d["achados"][0] for d in descritores)
    resumo = {"lamina": stem, "k": len(descritores), "variante": "uni",
              "laminas_de_treino": [s for s in LAMINAS_TREINO if s != stem],
              "combinacoes_distintas": len(achados),
              "combinacao_mais_comum": [achados.most_common(1)[0][0]] if achados else [],
              "pct_combinacao_mais_comum": round(100 * achados.most_common(1)[0][1] / len(descritores), 1)
              if descritores else None,
              "categorias_selecionados": dict(Counter(d["categoria"] for d in descritores)),
              "descritores": descritores}
    (saida / f"estagio3_descritores_k{k}_uni.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                              encoding="utf-8")
    return resumo


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--svs")
    p.add_argument("--k", type=int, default=32)
    a = p.parse_args()
    r = rodar(a.svs, a.k)
    print("\n".join(d["texto"] for d in r["descritores"]))
