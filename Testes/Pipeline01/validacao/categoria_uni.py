"""
Plano UNI2-h, teste 2: benigno / atípico / maligno nas 16 lâminas, com uma camada treinada em cima
dos embeddings (UNI2-h e QuiltNet), contra o descritor zero-shot por frases do QuiltNet.

Fixado ANTES de rodar (commit anterior aos resultados):
  - Lâminas: as 16 da primeira e da segunda leva (teste_fora_da_amostra.py). Tiles: todos os
    rotulados (rotular_tiles, RoIs com correlação >= 0,5), categoria = CATEGORIA_DA_CLASSE —
    igual a categoria_descritor.py.
  - Classificador (igual pros dois encoders): regressão logística multinomial (3 categorias),
    embeddings padronizados, pesos balanceados por categoria, L2 equivalente a C = 1 do
    scikit-learn, sem ajuste de hiperparâmetro.
  - Avaliação: deixa uma lâmina de fora por vez (treina nas outras 15, prevê a deixada de fora).
    Métrica: acerto por categoria real somando as lâminas e a média das 3 (acaso = 33%), nas 8
    lâminas novas e nas 16.
  - Referência: descritor zero-shot por frases (BANCO_DESCRITOR atual) — 53,2% nas 8 novas.
  - Critério de "funcionou": nas 8 lâminas novas, UNI2-h + logística > 53,2% E > QuiltNet + logística.
  - Controle: UNI2-h com os rótulos de treino embaralhados (deve ficar perto de 33%).

Uso (venv do projeto):
    .venv/bin/python validacao/categoria_uni.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import torch

from comum.bancos import CATEGORIA_DA_CLASSE
from comum.lamina import RESULTADOS_DIR, Lamina, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import carregar_rois, rotular_tiles
from comum.uni import embeddings_uni2h
from teste_fora_da_amostra import PRIMEIRA_LEVA, SEGUNDA_LEVA

CATEGORIAS = ["benigno", "atipico", "maligno"]
REFERENCIA_ZERO_SHOT_NOVAS = 53.17


def logistica_multinomial(X_treino, y_treino, X_teste, k=3):
    """Softmax com pesos balanceados por classe e L2 equivalente a C=1 do scikit-learn."""
    mu, sd = X_treino.mean(0), X_treino.std(0) + 1e-8
    Xt = torch.tensor((X_treino - mu) / sd, dtype=torch.float64)
    yt = torch.tensor(y_treino)
    n = len(yt)
    cont = torch.bincount(yt, minlength=k).double()
    peso_classe = torch.where(cont > 0, n / (k * cont.clamp(min=1)), torch.zeros_like(cont))
    W = torch.zeros(Xt.shape[1], k, dtype=torch.float64, requires_grad=True)
    b = torch.zeros(k, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([W, b], max_iter=500, line_search_fn="strong_wolfe")

    def perda():
        opt.zero_grad()
        l = torch.nn.functional.cross_entropy(Xt @ W + b, yt, weight=peso_classe, reduction="sum") / n
        l = l + (W ** 2).sum() / (2 * n)
        l.backward()
        return l

    opt.step(perda)
    with torch.no_grad():
        return (torch.tensor((X_teste - mu) / sd, dtype=torch.float64) @ W + b).argmax(1).numpy()


def dados(stem):
    embs_q, xy_q = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rot = rotular_tiles(xy_q, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
    xy = [(r["x0"], r["y0"]) for r in rot]
    y = np.array([CATEGORIAS.index(CATEGORIA_DA_CLASSE[r["classe_real"]]) for r in rot])
    return {"y": y, "quiltnet": embs_q[[r["idx"] for r in rot]],
            "uni2h": embeddings_uni2h(Lamina(resolver_svs(stem)), xy, "rotulados")}


def acertos(y, pred):
    tot, cert = Counter(y.tolist()), Counter(int(a) for a, b in zip(y, pred) if a == b)
    por = {CATEGORIAS[c]: round(100 * cert[c] / tot[c], 1) for c in range(3) if tot[c]}
    return {**por, "media": round(sum(por.values()) / len(por), 2), "n": {CATEGORIAS[c]: tot[c] for c in range(3)}}


def main():
    laminas = PRIMEIRA_LEVA + SEGUNDA_LEVA
    D = {}
    for s in laminas:
        D[s] = dados(s)
        print(f"{s}: {len(D[s]['y'])} tiles rotulados", flush=True)

    rng = np.random.default_rng(0)
    pred = {"quiltnet": {}, "uni2h": {}, "uni2h_rotulos_embaralhados": {}}
    for s in laminas:
        outras = [o for o in laminas if o != s]
        y_tr = np.concatenate([D[o]["y"] for o in outras])
        for enc in ("quiltnet", "uni2h"):
            X_tr = np.concatenate([D[o][enc] for o in outras])
            pred[enc][s] = logistica_multinomial(X_tr, y_tr, D[s][enc])
        pred["uni2h_rotulos_embaralhados"][s] = logistica_multinomial(
            np.concatenate([D[o]["uni2h"] for o in outras]), rng.permutation(y_tr), D[s]["uni2h"])
        print(f"  {s} feito", flush=True)

    resumo = {}
    for nome, grupo in (("novas", SEGUNDA_LEVA), ("primeira_leva", PRIMEIRA_LEVA), ("todas_16", laminas)):
        y = np.concatenate([D[s]["y"] for s in grupo])
        resumo[nome] = {m: acertos(y, np.concatenate([pred[m][s] for s in grupo])) for m in pred}
    resumo["por_lamina"] = {s: {m: acertos(D[s]["y"], pred[m][s]) for m in pred} for s in laminas}
    novas = resumo["novas"]
    resumo["funcionou"] = (novas["uni2h"]["media"] > REFERENCIA_ZERO_SHOT_NOVAS
                           and novas["uni2h"]["media"] > novas["quiltnet"]["media"])
    (RESULTADOS_DIR / "categoria_uni.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                       encoding="utf-8")

    print("\nAcerto por categoria (benigno / atípico / maligno / média), lâmina prevista sem ter sido usada no treino:")
    for nome in ("novas", "primeira_leva", "todas_16"):
        print(f"  {nome}  {resumo[nome]['uni2h']['n']}")
        for m in pred:
            a = resumo[nome][m]
            print(f"    {m:<28} {a['benigno']:>5} / {a['atipico']:>5} / {a['maligno']:>5} / média {a['media']:>6}")
    print(f"  referência zero-shot por frases, 8 novas: {REFERENCIA_ZERO_SHOT_NOVAS}")
    print(f"\nCritério fixado antes: {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
