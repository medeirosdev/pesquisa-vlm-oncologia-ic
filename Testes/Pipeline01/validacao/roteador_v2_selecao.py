"""
Estágio 2, segunda rodada — etapa 1 (venv do projeto): escolhe os k = 32 patches de cada lâmina com
quatro estratégias e salva as escolhas. A etapa 2 (roteador_v2_tumor.py, ambiente do CellViT)
conta quantos dos escolhidos têm tumor, sem depender dos RoIs.

Fixado ANTES de rodar (commit anterior aos resultados), junto com roteador_v2_tumor.py:
  - Lâminas: as 7 com RoI maligno (DCIS ou IC): BRACS_1003677, BRACS_1489, BRACS_748, BRACS_1512,
    BRACS_297, BRACS_773, BRACS_295.
  - Estratégias, todas com o mesmo gate de diversidade do roteador atual:
      frases       — pontuação atual (banco v2: suspeito − benigno, QuiltNet);
      uni_nao_ben  — 1 − P(benigno) (roteador_uni.py);
      uni_por_cat  — NOVA: classifica todos os patches (camada de nível 1 do descritor hierárquico,
                     treinada nas outras lâminas); categorias previstas em >= 2% dos patches são as
                     "encontradas"; os k patches são divididos igualmente entre elas (sobra vai pra
                     maligno, depois atípico, depois benigno); dentro de cada uma, os de maior
                     probabilidade daquela categoria;
      sorteio      — 5 sorteios de k patches entre os candidatos (semente 0).
  - Métrica e critério: ver roteador_v2_tumor.py.

Uso:
    .venv/bin/python validacao/roteador_v2_selecao.py
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio2_roteador"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from categoria_uni import logistica_multinomial
from comum.lamina import RESULTADOS_DIR, Lamina, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.uni import embeddings_uni2h
from descritor_uni import CATEGORIAS, LAMINAS_TREINO, rotulados
from roteador_topk import gate_diversidade, scores

LAMINAS_MALIGNAS = ["BRACS_1003677", "BRACS_1489", "BRACS_748", "BRACS_1512", "BRACS_297", "BRACS_773", "BRACS_295"]
K = 32
MIN_FRACAO_CATEGORIA = 0.02
N_SORTEIOS = 5
SAIDA = RESULTADOS_DIR / "roteador_v2_selecoes.json"


def escolher(xy, pontuacao, k):
    ordenados = sorted(({"x0": x, "y0": y, "score": float(v)} for (x, y), v in zip(xy, pontuacao)),
                       key=lambda c: -c["score"])
    return [(t["x0"], t["y0"]) for t in gate_diversidade(ordenados, k)]


def por_categoria(xy, prob, k):
    pred = prob.argmax(1)
    encontradas = [c for c in range(3) if (pred == c).mean() >= MIN_FRACAO_CATEGORIA]
    cota = {c: k // len(encontradas) for c in encontradas}
    for c in sorted(encontradas, reverse=True)[: k - sum(cota.values())]:  # maligno > atípico > benigno
        cota[c] += 1
    escolhidos = []
    for c in sorted(encontradas, reverse=True):
        idx = np.where(pred == c)[0]
        escolhidos += escolher([xy[i] for i in idx], prob[idx, c], cota[c])
    return escolhidos, [CATEGORIAS[c] for c in encontradas]


def main():
    D = {s: rotulados(s) for s in LAMINAS_TREINO}
    selecoes = {}
    for s in LAMINAS_MALIGNAS:
        embs_q, xy = carregar_embeddings_cacheados(dir_resultados(s, "estagio2"))
        uni = embeddings_uni2h(Lamina(resolver_svs(s)), xy, "candidatos")
        treino = [D[o] for o in LAMINAS_TREINO if o != s]
        prob = logistica_multinomial(np.concatenate([d["uni2h"] for d in treino]),
                                     np.concatenate([d["categoria"] for d in treino]), uni, k=3, probabilidades=True)
        uni_cat, encontradas = por_categoria(xy, prob, K)
        rng = random.Random(0)
        selecoes[s] = {"frases": escolher(xy, scores(embs_q, "v2"), K),
                       "uni_nao_ben": escolher(xy, 1 - prob[:, 0], K),
                       "uni_por_cat": uni_cat,
                       "sorteio": [rng.sample(xy, K) for _ in range(N_SORTEIOS)],
                       "categorias_encontradas": encontradas,
                       "fracao_prevista": {c: round(float((prob.argmax(1) == i).mean()), 3) for i, c in enumerate(CATEGORIAS)}}
        print(f"{s}: {len(xy)} candidatos; categorias encontradas {encontradas}; previstas {selecoes[s]['fracao_prevista']}",
              flush=True)
    SAIDA.write_text(json.dumps(selecoes, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
