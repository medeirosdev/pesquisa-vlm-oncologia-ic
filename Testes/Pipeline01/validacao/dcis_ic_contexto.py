"""
DCIS vs. IC usando os 8 vizinhos como CONTEXTO (não misturando os embeddings).

No DCIS o tumor fica dentro do ducto: em volta de um patch de tumor há mais tumor (o ducto
cheio) e a parede do ducto. No IC o tumor está no meio do estroma: em volta há estroma.
Então, em vez de classificar o patch, olha-se o que está em volta dele.

Passos, fixados antes de rodar:
  1. Cada tile com tecido recebe um tipo de tecido (zero-shot, BANCO_TECIDO): tumor, estroma,
     ducto ou gordura. Vizinho fora da grade de tecido = "sem_tecido" (gordura/fundo).
  2. Descritivo: composição média dos 8 vizinhos dos tiles DCIS vs. IC. Se for igual, não há
     sinal de contexto pra nenhuma regra usar.
  3. Regra fixa, sem treino: IC se >= metade dos vizinhos com tecido for estroma; senão DCIS.
  4. Regressão logística com [score DCIS-IC do próprio patch, fração de cada tipo nos vizinhos],
     avaliada deixando uma lâmina de fora por vez (treina nas outras, testa nela).
     Comparada com a mesma regressão só com o score do patch (sem contexto).

Métrica: acurácia balanceada DCIS/IC (acaso = 50%), todas as lâminas somadas e a BRACS_748
à parte (única com as duas classes juntas — o teste justo).

Uso:
    .venv/bin/python validacao/dcis_ic_contexto.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import torch

from classificacao import embeddings_de_classe
from comum.lamina import RESULTADOS_DIR, TILE_NATIVO, dir_resultados, listar_laminas
from comum.modelo import carregar_embeddings_cacheados, codificar_textos
from comum.rois import carregar_rois, rotular_tiles
from dcis_ic_vizinhanca import acuracia_balanceada

CLASSES = ["DCIS", "IC"]
BANCO_TECIDO = {
    "tumor": ["sheets of tumor cells", "dense proliferation of atypical epithelial cells", "carcinoma cells"],
    "estroma": ["fibrous stroma", "collagenous connective tissue", "stroma with scattered fibroblasts"],
    "ducto": ["normal breast duct", "duct lined by two cell layers", "breast lobule with small acini"],
    "gordura": ["adipose tissue", "fat cells"],
}
TIPOS = list(BANCO_TECIDO) + ["sem_tecido"]
LAMINA_JUSTA = "BRACS_748"


def tipo_de_tecido(embs):
    v = torch.from_numpy(embs.astype(np.float32))
    s = torch.stack([(v @ codificar_textos(fs).cpu().T).max(dim=1).values for fs in BANCO_TECIDO.values()], dim=1)
    nomes = list(BANCO_TECIDO)
    return [nomes[i] for i in s.argmax(dim=1).numpy()]


def score_dcis_menos_ic(embs, emb_c):
    v = torch.from_numpy(embs.astype(np.float32))
    return ((v @ emb_c["DCIS"].cpu().T).max(dim=1).values - (v @ emb_c["IC"].cpu().T).max(dim=1).values).numpy()


def composicao(x0, y0, pos, tipos):
    cont = Counter()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx or dy:
                j = pos.get((x0 + dx * TILE_NATIVO, y0 + dy * TILE_NATIVO))
                cont[tipos[j] if j is not None else "sem_tecido"] += 1
    return np.array([cont[t] / 8 for t in TIPOS])


def dados_da_lamina(stem, emb_c):
    embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rot = [r for r in rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
           if r["classe_real"] in CLASSES]
    if not rot:
        return None
    pos = {tuple(p): i for i, p in enumerate(xy)}
    tipos = tipo_de_tecido(embs)
    score = score_dcis_menos_ic(embs, emb_c)
    comp = np.stack([composicao(r["x0"], r["y0"], pos, tipos) for r in rot])
    return {"reais": [r["classe_real"] for r in rot], "comp": comp,
            "score": np.array([score[r["idx"]] for r in rot]),
            "tipo_centro": [tipos[r["idx"]] for r in rot]}


def regra_fixa(comp):
    i_estroma, i_sem = TIPOS.index("estroma"), TIPOS.index("sem_tecido")
    com_tecido = 1 - comp[:, i_sem]
    frac_estroma = np.divide(comp[:, i_estroma], com_tecido, out=np.zeros(len(comp)), where=com_tecido > 0)
    return ["IC" if f >= 0.5 else "DCIS" for f in frac_estroma]


def logistica(X_treino, y_treino, X_teste, passos=2000):
    """Regressão logística com pesos balanceados por classe (y=1 -> IC)."""
    mu, sd = X_treino.mean(0), X_treino.std(0) + 1e-8
    Xt = torch.tensor((X_treino - mu) / sd, dtype=torch.float32)
    yt = torch.tensor(y_treino, dtype=torch.float32)
    peso = torch.where(yt == 1, 0.5 / yt.mean(), 0.5 / (1 - yt.mean()))
    w = torch.zeros(Xt.shape[1], requires_grad=True)
    b = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([w, b], max_iter=passos)

    def perda():
        opt.zero_grad()
        l = (peso * torch.nn.functional.binary_cross_entropy_with_logits(Xt @ w + b, yt, reduction="none")).mean()
        l = l + 1e-3 * (w ** 2).sum()
        l.backward()
        return l

    opt.step(perda)
    with torch.no_grad():
        p = torch.tensor((X_teste - mu) / sd, dtype=torch.float32) @ w + b
    return ["IC" if v > 0 else "DCIS" for v in p.numpy()], dict(zip(["score"] + TIPOS, w.detach().numpy().round(2).tolist()))


def main():
    emb_c = embeddings_de_classe(CLASSES)
    laminas = {}
    for svs in listar_laminas():
        d = dados_da_lamina(svs.stem, emb_c)
        if d is not None:
            laminas[svs.stem] = d

    reais = {s: d["reais"] for s, d in laminas.items()}
    todos_reais = [c for s in laminas for c in reais[s]]

    # 2. descritivo
    descritivo = {}
    for c in CLASSES:
        comp = np.concatenate([d["comp"][[r == c for r in d["reais"]]] for d in laminas.values()])
        centro = Counter(t for d in laminas.values() for t, r in zip(d["tipo_centro"], d["reais"]) if r == c)
        descritivo[c] = {"vizinhos_%": {t: round(100 * float(v), 1) for t, v in zip(TIPOS, comp.mean(0))},
                         "tipo_do_proprio_patch": dict(centro)}
    d748 = laminas.get(LAMINA_JUSTA)
    if d748:
        descritivo[f"{LAMINA_JUSTA}"] = {c: {t: round(100 * float(v), 1) for t, v in
                                              zip(TIPOS, d748["comp"][[r == c for r in d748["reais"]]].mean(0))}
                                         for c in CLASSES}

    # 3 e 4. predições
    preditas = {"patch_sozinho_zero_shot": {}, "regra_fixa_estroma": {}, "logistica_so_patch": {},
                "logistica_patch_mais_contexto": {}}
    pesos = {}
    for s, d in laminas.items():
        preditas["patch_sozinho_zero_shot"][s] = ["DCIS" if v > 0 else "IC" for v in d["score"]]
        preditas["regra_fixa_estroma"][s] = regra_fixa(d["comp"])
        outras = [o for o in laminas if o != s]
        y = np.array([1 if c == "IC" else 0 for o in outras for c in reais[o]])
        Xs = np.concatenate([laminas[o]["score"][:, None] for o in outras])
        Xc = np.concatenate([np.hstack([laminas[o]["score"][:, None], laminas[o]["comp"]]) for o in outras])
        preditas["logistica_so_patch"][s], _ = logistica(Xs, y, d["score"][:, None])
        preditas["logistica_patch_mais_contexto"][s], pesos[s] = logistica(
            Xc, y, np.hstack([d["score"][:, None], d["comp"]]))

    resumo = {"descritivo": descritivo, "resultados": {}, "pesos_logistica_por_lamina_deixada_de_fora": pesos}
    print("Composição média dos 8 vizinhos (%):")
    for c in CLASSES:
        print(f"  {c:<5} " + "  ".join(f"{t} {v:>5}" for t, v in descritivo[c]["vizinhos_%"].items()))
    if d748:
        print(f"  só {LAMINA_JUSTA}:")
        for c in CLASSES:
            print(f"  {c:<5} " + "  ".join(f"{t} {v:>5}" for t, v in descritivo[LAMINA_JUSTA][c].items()))
    print("\nTipo de tecido do próprio patch:", {c: descritivo[c]["tipo_do_proprio_patch"] for c in CLASSES})

    print("\nAcurácia balanceada (DCIS / IC / balanceada):")
    for nome, por_lamina in preditas.items():
        todas = acuracia_balanceada(todos_reais, [p for s in laminas for p in por_lamina[s]])
        justa = acuracia_balanceada(reais[LAMINA_JUSTA], por_lamina[LAMINA_JUSTA]) if d748 else None
        resumo["resultados"][nome] = {"todas": todas, LAMINA_JUSTA: justa,
                                      "por_lamina": {s: acuracia_balanceada(reais[s], p) for s, p in por_lamina.items()}}
        print(f"  {nome:<30} todas {todas['DCIS']:>5} / {todas['IC']:>5} / {todas['balanceada']:>5}   "
              f"{LAMINA_JUSTA} {justa['DCIS']:>5} / {justa['IC']:>5} / {justa['balanceada']:>5}")
    print(f"\nPesos da logística (treinada sem a {LAMINA_JUSTA}; positivo = puxa pra IC):", pesos.get(LAMINA_JUSTA))

    (RESULTADOS_DIR / "dcis_ic_contexto.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                          encoding="utf-8")


if __name__ == "__main__":
    main()
