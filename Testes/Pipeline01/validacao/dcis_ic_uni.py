"""
Plano UNI2-h, teste 1: DCIS vs. IC com embeddings do UNI2-h, nos mesmos tiles do teste do CellViT
(dcis_ic_nucleos.py). Compara com o QuiltNet usando a MESMA camada treinada, e com a medida dos
núcleos (que não precisa de treino).

Fixado ANTES de rodar (commit anterior aos resultados):
  - Tiles: amostra de dcis_ic_nucleos.py (250 por classe por lâmina, semente 0) nas lâminas
    BRACS_748, BRACS_773, BRACS_295, só os tiles com >= 20 núcleos neoplásicos.
  - Classificador (igual pros dois encoders): regressão logística sobre os embeddings padronizados,
    pesos balanceados por classe, regularização L2 equivalente ao padrão do scikit-learn (C = 1),
    sem ajuste de hiperparâmetro.
  - Avaliação: deixa uma lâmina de fora por vez (treina nas outras duas, testa nela). AUC na lâmina
    deixada de fora. A medida dos núcleos entra direto (AUC sem treino), como referência.
  - Critério de "funcionou": AUC do UNI2-h > AUC do QuiltNet nas TRÊS lâminas.

Uso (venv do projeto):
    .venv/bin/python validacao/dcis_ic_uni.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import torch

from comum.lamina import RESULTADOS_DIR, Lamina, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.uni import embeddings_uni2h
from dcis_ic_nucleos import LAMINAS, amostra_da_lamina, auc, medidas_do_tile


def logistica_prob_ic(X_treino, y_treino, X_teste):
    """Logística com pesos balanceados e L2 equivalente a C=1 do scikit-learn; devolve P(IC) no teste."""
    mu, sd = X_treino.mean(0), X_treino.std(0) + 1e-8
    Xt = torch.tensor((X_treino - mu) / sd, dtype=torch.float64)
    yt = torch.tensor(y_treino, dtype=torch.float64)
    n = len(yt)
    peso = torch.where(yt == 1, 0.5 / yt.mean(), 0.5 / (1 - yt.mean()))
    w = torch.zeros(Xt.shape[1], dtype=torch.float64, requires_grad=True)
    b = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], max_iter=500, line_search_fn="strong_wolfe")

    def perda():
        opt.zero_grad()
        # scikit-learn: 0.5*||w||^2 + C * soma(perdas); dividindo por n: média + ||w||^2 / (2 C n)
        l = (peso * torch.nn.functional.binary_cross_entropy_with_logits(Xt @ w + b, yt, reduction="none")).mean()
        l = l + (w ** 2).sum() / (2 * n)
        l.backward()
        return l

    opt.step(perda)
    with torch.no_grad():
        return (torch.tensor((X_teste - mu) / sd, dtype=torch.float64) @ w + b).numpy()


def dados(stem):
    amostra = amostra_da_lamina(stem)
    pasta = dir_resultados(stem, "nucleos")
    tiles, nucleo = [], []
    for r in amostra:
        d = json.loads((pasta / f"nucleos_{r['x0']}_{r['y0']}.json").read_text(encoding="utf-8"))
        m = medidas_do_tile(d["nucleos"])
        if m is not None:
            tiles.append(r)
            nucleo.append(m["neo_encostados_em_conjuntivo"])
    xy = [(r["x0"], r["y0"]) for r in tiles]
    y = np.array([1 if r["classe_real"] == "IC" else 0 for r in tiles])

    embs_q, xy_q = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    pos = {p: i for i, p in enumerate(xy_q)}
    quilt = embs_q[[pos[p] for p in xy]]
    uni = embeddings_uni2h(Lamina(resolver_svs(stem)), xy, "amostra_dcis_ic")
    return {"y": y, "quiltnet": quilt, "uni2h": uni, "nucleos": np.array(nucleo)}


def main():
    D = {s: dados(s) for s in LAMINAS}
    resumo = {}
    for s in LAMINAS:
        outras = [o for o in LAMINAS if o != s]
        y_tr = np.concatenate([D[o]["y"] for o in outras])
        y_te = D[s]["y"]
        res = {"n_teste": {"DCIS": int((y_te == 0).sum()), "IC": int((y_te == 1).sum())}}
        for enc in ("quiltnet", "uni2h"):
            p = logistica_prob_ic(np.concatenate([D[o][enc] for o in outras]), y_tr, D[s][enc])
            res[enc] = auc(p[y_te == 1], p[y_te == 0])
        res["nucleos_sem_treino"] = auc(D[s]["nucleos"][y_te == 1], D[s]["nucleos"][y_te == 0])
        resumo[s] = res
    resumo["funcionou"] = all(resumo[s]["uni2h"] > resumo[s]["quiltnet"] for s in LAMINAS)
    (RESULTADOS_DIR / "dcis_ic_uni.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'Lâmina deixada de fora':<24}{'QuiltNet':>10}{'UNI2-h':>10}{'Núcleos':>10}")
    for s in LAMINAS:
        r = resumo[s]
        print(f"{s:<24}{r['quiltnet']:>10}{r['uni2h']:>10}{r['nucleos_sem_treino']:>10}   {r['n_teste']}")
    print(f"\nCritério fixado antes (UNI2-h > QuiltNet nas três lâminas): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
