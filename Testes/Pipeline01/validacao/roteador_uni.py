"""
Estágio 2 com o UNI2-h: o roteador escolhe os tiles pela probabilidade de NÃO ser benigno, dada
por uma camada treinada em cima do UNI2-h, em vez da pontuação por frases (QuiltNet, banco v2).

Fixado ANTES de rodar (commit anterior aos resultados):
  - Lâminas: as 16 da primeira e da segunda leva. Candidatos: a mesma grade de tiles com tecido
    do estágio 2 (estagio2_embeddings_xy.csv).
  - Pontuação nova: logística multinomial (a do teste 2, categoria_uni.py) treinada nos tiles
    rotulados das OUTRAS 15 lâminas; pontuação do tile = 1 - P(benigno).
  - Pontuação atual, pra comparar: banco v2 do roteador_topk.py (suspeito - benigno, QuiltNet).
  - Seleção: mesma ordenação e mesmo gate de diversidade do roteador atual (gate_diversidade).
  - Métrica corrigida: um tile escolhido só acerta se sobrepuser um RoI de LESÃO (UDH, FEA, ADH,
    DCIS, IC) — RoIs N e PB não contam. Precisão@k e recall@k (fração dos RoIs de lesão cobertos).
    Sorteio: média de 50 sorteios de k tiles entre os candidatos (como no roteador atual).
    Só entram lâminas com pelo menos um RoI de lesão (11 das 16).
  - Critério de "funcionou", em k = 32: precisão do roteador UNI2-h > roteador atual em pelo
    menos 8 das 11 lâminas E precisão média maior.

Uso (venv do projeto):
    .venv/bin/python validacao/roteador_uni.py
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio2_roteador"))

import numpy as np

from categoria_uni import dados as dados_rotulados
from categoria_uni import logistica_multinomial
from comum.lamina import RESULTADOS_DIR, Lamina, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import carregar_rois
from comum.uni import embeddings_uni2h
from roteador_topk import KS_PADRAO, gate_diversidade, precisao_recall, scores
from teste_fora_da_amostra import PRIMEIRA_LEVA, SEGUNDA_LEVA

CLASSES_LESAO = {"UDH", "FEA", "ADH", "DCIS", "IC"}
K_CRITERIO = 32
N_SORTEIOS = 50


def curva(candidatos_xy, pontuacao, rois_lesao, rng):
    ordenados = sorted(({"x0": x, "y0": y, "score": float(v)} for (x, y), v in zip(candidatos_xy, pontuacao)),
                       key=lambda c: -c["score"])
    pontos = {}
    for k in KS_PADRAO:
        if k > len(candidatos_xy):
            continue
        prec, rec, _ = precisao_recall(gate_diversidade(ordenados, k), rois_lesao)
        pontos[k] = {"precisao": round(prec, 3), "recall": round(rec, 3)}
    return pontos


def sorteio(candidatos_xy, rois_lesao, rng):
    pontos = {}
    for k in KS_PADRAO:
        if k > len(candidatos_xy):
            continue
        ps = [precisao_recall([{"x0": x, "y0": y} for x, y in rng.sample(candidatos_xy, k)], rois_lesao)
              for _ in range(N_SORTEIOS)]
        pontos[k] = {"precisao": round(float(np.mean([p[0] for p in ps])), 3),
                     "recall": round(float(np.mean([p[1] for p in ps])), 3)}
    return pontos


def main():
    laminas = PRIMEIRA_LEVA + SEGUNDA_LEVA
    rotulados = {s: dados_rotulados(s) for s in laminas}
    resumo = {}
    for s in laminas:
        rois_lesao = [r for r in carregar_rois(s) if r["correlacao"] >= 0.5 and r["classe"] in CLASSES_LESAO]
        if not rois_lesao:
            continue
        embs_q, xy = carregar_embeddings_cacheados(dir_resultados(s, "estagio2"))
        uni = embeddings_uni2h(Lamina(resolver_svs(s)), xy, "candidatos")
        outras = [o for o in laminas if o != s]
        prob = logistica_multinomial(np.concatenate([rotulados[o]["uni2h"] for o in outras]),
                                     np.concatenate([rotulados[o]["y"] for o in outras]), uni, probabilidades=True)
        rng = random.Random(0)
        resumo[s] = {"candidatos": len(xy), "rois_lesao": len(rois_lesao),
                     "atual_frases": curva(xy, scores(embs_q, "v2"), rois_lesao, rng),
                     "uni2h": curva(xy, 1 - prob[:, 0], rois_lesao, rng),
                     "sorteio": sorteio(xy, rois_lesao, rng)}
        a, u, r = (resumo[s][m].get(K_CRITERIO, {}).get("precisao") for m in ("atual_frases", "uni2h", "sorteio"))
        print(f"{s}: {len(xy)} candidatos, {len(rois_lesao)} RoIs de lesão | precisão@{K_CRITERIO}: "
              f"atual {a}  UNI2-h {u}  sorteio {r}", flush=True)

    com_k = [s for s in resumo if K_CRITERIO in resumo[s]["uni2h"]]
    p = {m: [resumo[s][m][K_CRITERIO]["precisao"] for s in com_k] for m in ("atual_frases", "uni2h", "sorteio")}
    vitorias = sum(u > a for u, a in zip(p["uni2h"], p["atual_frases"]))
    resumo["criterio"] = {"laminas": len(com_k), "uni2h_vence_atual": vitorias,
                          "media": {m: round(float(np.mean(v)), 3) for m, v in p.items()},
                          "funcionou": vitorias >= 8 and np.mean(p["uni2h"]) > np.mean(p["atual_frases"])}
    (RESULTADOS_DIR / "roteador_uni.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    c = resumo["criterio"]
    print(f"\nprecisão@{K_CRITERIO} média: atual {c['media']['atual_frases']}  UNI2-h {c['media']['uni2h']}  "
          f"sorteio {c['media']['sorteio']}; UNI2-h vence o atual em {vitorias} de {len(com_k)} lâminas")
    print(f"Critério fixado antes: {'SIM' if c['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
