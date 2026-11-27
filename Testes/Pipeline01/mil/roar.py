"""
ROAR (remover e retreinar; Hooker et al., 2019) para a atenção do MIL (revisão 01, item C3).

Antes: os testes de remoção e de suficiência (remocao_atencao*.py) tiram patches só na hora de prever, com o modelo
treinado em sacos inteiros; a revisão apontou que isso é quase tautológico para pooling por atenção e que sacos
alterados ficam fora da distribuição do treino. No ROAR, os patches são tirados de TODAS as lâminas (treino e teste) e o
modelo é retreinado; se a atenção aponta o que carrega a informação da classe, tirar os de maior atenção deve piorar o
desempenho mais do que tirar a mesma fração sorteada.

Fixado ANTES de rodar (commit anterior aos resultados):
  Pulmão (etapa pulmao): as 197 lâminas, as 5 partes por centro de origem (pulmao_por_centro.partes_por_centro),
     ABMIL (mil_atencao.treinar, k = 2, 5 sementes mil_atencao.SEMENTES). Em cada parte: (1) treina nas outras 4 com
     sacos inteiros e calcula a atenção média das 5 sementes em todas as lâminas (treino e teste da parte); (2) para
     f = 10%, 50% e 90%, tira de cada lâmina os f% de maior atenção (cenário "top") ou f% sorteados (cenário
     "sorteio", semente [f, índice da lâmina]), retreina as 5 sementes nos sacos alterados do treino e prevê os sacos
     alterados do teste. Probabilidade fora da amostra, 197 lâminas.
  Próstata (etapa prostata): 600 do Radboud (treino) e 300 do Karolinska (desenvolvimento), GAT-MIL padronizado
     (gat_mil.treinar, k = 6, 5 sementes 0–4), padronização pela média e desvio dos patches que sobram em cada centro,
     grafo refeito nos patches que sobram; atenção do modelo treinado com sacos inteiros; f = 50% apenas.
  Medidas: AUC (pulmão: escamoso × adenocarcinoma; próstata: câncer × benigno, 1 − P(ISUP 0)); acurácia balanceada
     (pulmão), kappa quadrático (próstata); sensibilidade por classe real; com sacos inteiros como referência.
  Critérios (f = 50%): ROAR-P (pulmão) e ROAR-Q (próstata): AUC(top) < AUC(sorteio), com limite superior do IC 95% da
     diferença pareada AUC(top) − AUC(sorteio) < 0 (bootstrap das lâminas, 2.000, semente 0).
  Também reportado (sem critério): f = 10% e 90% no pulmão; a mesma diferença em acurácia balanceada / kappa.
  Limites: o sorteio também tira informação; com 2.000 patches e redundância, frações pequenas podem não mudar nada
     depois de retreinar (por isso o critério é em 50%); um só sorteio por lâmina.

Uso (venv do projeto; GPU): .venv/bin/python mil/roar.py --etapa pulmao | prostata
Saída: resultados/roar/{pulmao.json, prostata.json}
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "roar"
N_BOOT = 2000


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def auc_y(y, s):
    y, s = np.asarray(y), np.asarray(s)
    return auc(s[y == 1], s[y == 0])


def ic_dif(y, s1, s2, met):
    rng = random.Random(0)
    n, d = len(y), []
    y, s1, s2 = np.asarray(y), np.asarray(s1), np.asarray(s2)
    for _ in range(N_BOOT):
        idx = np.array([rng.randrange(n) for _ in range(n)])
        if len(set(y[idx] > 0)) < 2:
            continue
        d.append(met(y[idx], s1[idx]) - met(y[idx], s2[idx]))
    return [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]


def manter(n, att, f, cond, semente):
    k = max(1, int(round(f * n)))
    if cond == "top":
        tirar = np.argsort(-att)[:k]
    else:
        tirar = np.random.default_rng(semente).choice(n, k, replace=False)
    return np.setdiff1d(np.arange(n), tirar)


def etapa_pulmao():
    from mil_atencao import SEMENTES, treinar
    from pulmao_por_centro import PARTES, centro, partes_por_centro
    from tcga_descritor_prelaudo import PASTA
    from tcga_mil import CLASSES, LISTA

    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    lam = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    parte_c = partes_por_centro(lam)
    y = np.array([CLASSES.index(l["projeto"]) for l in lam])
    parte = np.array([parte_c[centro(l)] for l in lam])
    X = [torch.from_numpy(np.load(PASTA / l["file_id"] / "amostra2000.npy")) for l in lam]
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    FR = (0.1, 0.5, 0.9)
    P = {"inteiro": np.zeros(len(lam))}
    P.update({f"{c}_{f}": np.zeros(len(lam)) for f in FR for c in ("top", "sorteio")})

    def prever(modelos, Xs, idx):
        with torch.no_grad():
            return np.array([np.mean([torch.softmax(m(Xs[i].to(dev))[0], 0)[1].item() for m in modelos]) for i in idx])

    for k in range(PARTES):
        tr, te = np.where(parte != k)[0], np.where(parte == k)[0]
        mods = [treinar([X[i] for i in tr], y[tr], s, dev, k=2).eval() for s in SEMENTES]
        P["inteiro"][te] = prever(mods, X, te)
        att = {}
        with torch.no_grad():
            for i in np.concatenate([tr, te]):
                att[i] = np.mean([m(X[i].to(dev))[1].cpu().numpy() for m in mods], 0)
        for f in FR:
            for c in ("top", "sorteio"):
                Xm = {i: X[i][torch.from_numpy(manter(len(X[i]), att[i], f, c, [int(f * 100), int(i)]))] for i in att}
                m2 = [treinar([Xm[i] for i in tr], y[tr], s, dev, k=2).eval() for s in SEMENTES]
                P[f"{c}_{f}"][te] = prever(m2, Xm, te)
        print(f"  parte {k} pronta", flush=True)

    def ba(yy, s):
        p = (np.asarray(s) >= 0.5).astype(int)
        return float(np.mean([np.mean(p[yy == c] == c) for c in (0, 1)]))

    res = {"n": len(lam), "classes": CLASSES}
    for nome, s in P.items():
        p = (s >= 0.5).astype(int)
        res[nome] = {"auc": round(auc_y(y, s), 4), "acuracia_balanceada": round(ba(y, s), 4),
                     "sens_" + CLASSES[0]: round(float(np.mean(p[y == 0] == 0)), 4),
                     "sens_" + CLASSES[1]: round(float(np.mean(p[y == 1] == 1)), 4)}
    for f in FR:
        st, ss = P[f"top_{f}"], P[f"sorteio_{f}"]
        res[f"dif_{f}"] = {"auc": round(auc_y(y, st) - auc_y(y, ss), 4), "auc_ic95": ic_dif(y, st, ss, auc_y),
                           "acuracia_balanceada": round(ba(y, st) - ba(y, ss), 4)}
    d = res["dif_0.5"]
    res["criterio_ROAR_P"] = bool(d["auc"] < 0 and d["auc_ic95"][1] < 0)
    (SAIDA / "pulmao.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"ROAR-P {'SIM' if res['criterio_ROAR_P'] else 'NÃO'}")


def etapa_prostata():
    import gat_mil
    from gat_mil_panda import PASTA
    from panda_externo import kappa_q
    from panda_mil import biopsias

    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    yv = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    dv = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X, XY, LADO = {}, {}, {}
    for i in tr + dv:
        X[i] = torch.from_numpy(np.load(PASTA / i / "amostra2000.npy"))
        XY[i] = np.loadtxt(PASTA / i / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        LADO[i] = json.loads((PASTA / i / "meta.json").read_text(encoding="utf-8"))["lado_px"]
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ytr = np.array([yv[i] for i in tr])
    real = np.array([yv[i] for i in dv])

    def montar(manter_idx):
        Xm = {i: X[i][torch.from_numpy(manter_idx[i])] for i in X}
        Gm = {i: gat_mil.arestas_vizinhos(XY[i][manter_idx[i]], LADO[i]) for i in X}
        out = {}
        for grupo in (tr, dv):
            tudo = torch.cat([Xm[i] for i in grupo])
            m, s = tudo.mean(0), tudo.std(0) + 1e-6
            out.update({i: (Xm[i] - m) / s for i in grupo})
        return out, Gm

    def treinar_prever(Xs, Gs, guardar_att=False):
        P = {i: np.zeros(6) for i in dv}
        A = {i: np.zeros(len(Xs[i])) for i in tr + dv} if guardar_att else None
        for s in range(5):
            m = gat_mil.treinar([Xs[i] for i in tr], [Gs[i] for i in tr], ytr, s, dev, k=6).eval()
            with torch.no_grad():
                for i in (tr + dv) if guardar_att else dv:
                    logit, a, _ = m(Xs[i].to(dev), Gs[i].to(dev))
                    if i in P:
                        P[i] += torch.softmax(logit, 0).cpu().numpy() / 5
                    if guardar_att:
                        A[i] += a.cpu().numpy() / 5
            print(f"    semente {s}", flush=True)
        return np.array([P[i] for i in dv]), A

    tudo = {i: np.arange(len(X[i])) for i in X}
    Xs, Gs = montar(tudo)
    P0, A = treinar_prever(Xs, Gs, guardar_att=True)
    print("  inteiro pronto", flush=True)
    P = {"inteiro": P0}
    f = 0.5
    for c in ("top", "sorteio"):
        idx = {i: manter(len(X[i]), A[i], f, c, [50, j]) for j, i in enumerate(tr + dv)}
        Xs, Gs = montar(idx)
        P[f"{c}_{f}"] = treinar_prever(Xs, Gs)[0]
        print(f"  {c} pronto", flush=True)
    yb = (real >= 1).astype(int)
    res = {"n_treino": len(tr), "n_desenvolvimento": len(dv)}
    for nome, Pm in P.items():
        pred = Pm.argmax(1)
        res[nome] = {"auc_cancer": round(auc_y(yb, 1 - Pm[:, 0]), 4), "kappa_quadratico": round(kappa_q(real, pred), 4),
                     "sens_cancer": round(float(np.mean(pred[real >= 1] >= 1)), 4),
                     "espec_benigno": round(float(np.mean(pred[real == 0] == 0)), 4)}
    st, ss = 1 - P["top_0.5"][:, 0], 1 - P["sorteio_0.5"][:, 0]
    res["dif_0.5"] = {"auc_cancer": round(auc_y(yb, st) - auc_y(yb, ss), 4), "auc_ic95": ic_dif(yb, st, ss, auc_y),
                      "kappa_quadratico": round(res["top_0.5"]["kappa_quadratico"] - res["sorteio_0.5"]["kappa_quadratico"], 4)}
    d = res["dif_0.5"]
    res["criterio_ROAR_Q"] = bool(d["auc_cancer"] < 0 and d["auc_ic95"][1] < 0)
    (SAIDA / "prostata.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"ROAR-Q {'SIM' if res['criterio_ROAR_Q'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--etapa", choices=["pulmao", "prostata"], required=True)
    {"pulmao": etapa_pulmao, "prostata": etapa_prostata}[p.parse_args().etapa]()
