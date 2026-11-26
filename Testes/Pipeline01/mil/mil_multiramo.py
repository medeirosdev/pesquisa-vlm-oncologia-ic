"""
MIL com atenção por classe (um ramo de atenção para cada classe, como no CLAM multi-ramo, sem a perda de agrupamento).

Antes (ausencia.py): no ABMIL, a atenção é uma só para todas as classes, e nas lâminas previstas como adenocarcinoma os
20 patches de maior atenção têm contribuição líquida zero e sozinhos sustentam a classe pior que 20 sorteados (−1,98 em
logit). Com o classificador linear, o ABMIL já é um MIL aditivo (logit = soma de a_i · W h_i), então a decomposição de
ausencia.py é a contribuição do MIL aditivo com cabeça linear. O que falta testar, como pediu a revisão, é a atenção
por classe: com um ramo por classe, os patches de maior atenção do ramo da classe prevista passam a sustentar a classe
também nas lâminas "por ausência"?

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelo MR (multi-ramo): a mesma projeção (1.536 → 256) e as mesmas camadas da atenção com porta do ABMIL, mas a
     camada final da atenção dá um escore por classe; a_i^k = softmax nos patches; z_k = soma de a_i^k h_i; logit_k =
     w_k · z_k + b_k (um classificador linear por classe). Treino igual ao do ABMIL (mil_atencao.treinar: entropia
     cruzada ponderada, Adam 1e-4, 40 épocas, sementes 0 a 4, sem ajuste).
  Pulmão: as 197 lâminas, as mesmas 5 partes por centro de pulmao_por_centro.py; comparador: ABMIL nas mesmas partes e
     sementes (o de ausencia.py).
  Próstata: treino 600 Radboud, teste 300 Karolinska, embeddings padronizados por centro (panda_centro); comparador:
     ABMIL padronizado com as mesmas sementes. (O GAT-MIL fica de fora: o multi-ramo é comparado com o ABMIL, que tem a
     mesma estrutura sem o grafo.)
  Classe prevista: argmax da probabilidade média das 5 sementes. Grupos "por ausência": previstas como adenocarcinoma;
     previstas como ISUP 0.
  Suficiência na margem, por lâmina e semente (média das sementes): margem = logit da classe prevista − média dos
     logits das outras; margem só com os 20 patches de maior atenção do ramo da classe prevista (no ABMIL, da atenção
     única) − margem só com 20 sorteados (média de 5 sorteios, semente [0, i]); atenção renormalizada no subconjunto.
     IC 95% por bootstrap das lâminas do grupo (2.000, semente 0).
  Critérios:
     M1 (o multi-ramo decide): pulmão por centro, AUC >= 0,85 e acurácia balanceada >= 0,75 (os mesmos de Z1).
     M2 (pulmão): nas previstas como adenocarcinoma, suficiência na margem do MR > 0, com limite inferior do IC > 0.
     M3 (próstata): nas previstas como ISUP 0, suficiência na margem do MR > 0, com limite inferior do IC > 0.
  Também reportado (sem critério): a mesma suficiência no ABMIL (comparador) e no grupo "positivo"; kappa quadrático da
     próstata do MR e do ABMIL padronizado; AUC do pulmão do ABMIL nas mesmas partes.
  Limites conhecidos: sem a perda de agrupamento do CLAM; 5 sementes; uma só divisão.

Uso (venv do projeto; GPU): .venv/bin/python mil/mil_multiramo.py
Saída: resultados/mil_multiramo/resumo.json
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "mil_multiramo"
TOP, SORT, N_BOOT = 20, 5, 2000
AUC_MIN, BA_MIN = 0.85, 0.75


class MRMIL(nn.Module):
    def __init__(self, d_in=1536, d_h=256, d_att=128, k=2):
        super().__init__()
        self.proj = nn.Sequential(nn.Linear(d_in, d_h), nn.ReLU(), nn.Dropout(0.25))
        self.att_v = nn.Sequential(nn.Linear(d_h, d_att), nn.Tanh())
        self.att_u = nn.Sequential(nn.Linear(d_h, d_att), nn.Sigmoid())
        self.att_w = nn.Linear(d_att, k)
        self.w = nn.Parameter(torch.randn(k, d_h) * 0.02)
        self.b = nn.Parameter(torch.zeros(k))

    def atencao(self, h):
        return torch.softmax(self.att_w(self.att_v(h) * self.att_u(h)), dim=0)  # n × k

    def forward(self, x):
        h = self.proj(x)
        a = self.atencao(h)
        z = a.T @ h  # k × d_h
        return (z * self.w).sum(1) + self.b, a


def treinar_mr(X, y, semente, dev, k):
    import mil_atencao
    original = mil_atencao.ABMIL
    mil_atencao.ABMIL = lambda k=k: MRMIL(k=k)
    try:
        return mil_atencao.treinar(X, y, semente, dev, k=k)
    finally:
        mil_atencao.ABMIL = original


def margem_sub(m, x, idx, prev, mr):
    with torch.no_grad():
        xx = x[torch.from_numpy(np.asarray(idx)).to(x.device)]
        h = m.proj(xx)
        if mr:
            a = m.atencao(h)
            logit = ((a.T @ h) * m.w).sum(1) + m.b
        else:
            a = torch.softmax(m.att_w(m.att_v(h) * m.att_u(h)).squeeze(-1), dim=0)
            logit = m.cls((a.unsqueeze(-1) * h).sum(0))
        outras = [c for c in range(len(logit)) if c != prev]
        return float(logit[prev] - logit[outras].mean())


def ordem_top(m, x, prev, mr):
    with torch.no_grad():
        h = m.proj(x)
        if mr:
            a = m.atencao(h)[:, prev]
        else:
            a = torch.softmax(m.att_w(m.att_v(h) * m.att_u(h)).squeeze(-1), dim=0)
        return np.argsort(-a.cpu().numpy())


def suficiencia(modelos, x, prev, mr, rng):
    n = len(x)
    sorteios = [np.sort(rng.permutation(n)[:min(TOP, n)]) for _ in range(SORT)]
    v = []
    for m in modelos:
        top = np.sort(ordem_top(m, x, prev, mr)[:min(TOP, n)])
        v.append(margem_sub(m, x, top, prev, mr) - np.mean([margem_sub(m, x, s, prev, mr) for s in sorteios]))
    return float(np.mean(v))


def prever(modelos, x):
    with torch.no_grad():
        return np.mean([torch.softmax(m(x)[0], 0).cpu().numpy() for m in modelos], 0)


def ic(v):
    v = np.asarray(v)
    rng = random.Random(0)
    b = [float(np.mean(v[[rng.randrange(len(v)) for _ in v]])) for _ in range(N_BOOT)]
    return [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)]


def grupo(v):
    return {"n": len(v), "media": round(float(np.mean(v)), 3), "ic95": ic(v)} if len(v) else {"n": 0}


def pulmao(dev):
    import csv
    from mil_atencao import SEMENTES, auc, treinar
    from pulmao_por_centro import PARTES, centro, partes_por_centro
    from tcga_descritor_prelaudo import PASTA
    from tcga_mil import CLASSES, LISTA
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    lam = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    parte_c = partes_por_centro(lam)
    y = np.array([CLASSES.index(l["projeto"]) for l in lam])
    parte = np.array([parte_c[centro(l)] for l in lam])
    X = [torch.from_numpy(np.load(PASTA / l["file_id"] / "amostra2000.npy")) for l in lam]
    res = {}
    for nome, mr in (("multiramo", True), ("abmil", False)):
        P, suf = np.zeros((len(lam), 2)), np.zeros(len(lam))
        for k in range(PARTES):
            tr, te = np.where(parte != k)[0], np.where(parte == k)[0]
            mods = [(treinar_mr if mr else (lambda X_, y_, s, d, k: treinar(X_, y_, s, d, k=k)))(
                [X[i] for i in tr], y[tr], s, dev, 2).eval() for s in SEMENTES]
            for i in te:
                x = X[i].to(dev)
                P[i] = prever(mods, x)
                suf[i] = suficiencia(mods, x, int(P[i].argmax()), mr, np.random.default_rng([0, int(i)]))
            print(f"  pulmão {nome} parte {k}", flush=True)
        pred = P.argmax(1)
        ba = float(np.mean([np.mean(pred[y == c] == c) for c in (0, 1)]))
        res[nome] = {"auc": round(auc(P[y == 1, 1], P[y == 0, 1]), 3), "acuracia_balanceada": round(ba, 3),
                     "suficiencia_previstas_adenocarcinoma": grupo(suf[pred == 0]),
                     "suficiencia_previstas_escamoso": grupo(suf[pred == 1])}
    return res


def kappa_q(real, pred, k=6):
    O = np.zeros((k, k))
    for r, p in zip(real, pred):
        O[r, p] += 1
    W = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    return float(1 - (W * O).sum() / (W * E).sum())


def prostata(dev):
    from gat_mil_panda import carregar
    from mil_atencao import SEMENTES, treinar
    from panda_centro import padronizar_por_centro
    from panda_mil import biopsias
    _, prontas = biopsias()
    yd = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X0, _ = carregar(tr + te)
    X = padronizar_por_centro(X0, [tr, te])
    ytr = np.array([yd[i] for i in tr])
    real = np.array([yd[i] for i in te])
    res = {}
    for nome, mr in (("multiramo", True), ("abmil", False)):
        mods = [(treinar_mr(  [X[i] for i in tr], ytr, s, dev, 6) if mr else treinar([X[i] for i in tr], ytr, s, dev, k=6)).eval()
                for s in SEMENTES]
        P, suf = np.zeros((len(te), 6)), np.zeros(len(te))
        for j, i in enumerate(te):
            x = X[i].to(dev)
            P[j] = prever(mods, x)
            suf[j] = suficiencia(mods, x, int(P[j].argmax()), mr, np.random.default_rng([0, j]))
        pred = P.argmax(1)
        res[nome] = {"kappa_quadratico": round(kappa_q(real, pred), 3),
                     "suficiencia_previstas_isup0": grupo(suf[pred == 0]),
                     "suficiencia_previstas_isup1_ou_mais": grupo(suf[pred >= 1])}
        print(f"  próstata {nome} pronto", flush=True)
    return res


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    res = {"pulmao": pulmao(dev), "prostata": prostata(dev)}
    mrp, mrq = res["pulmao"]["multiramo"], res["prostata"]["multiramo"]
    res["criterio_M1"] = mrp["auc"] >= AUC_MIN and mrp["acuracia_balanceada"] >= BA_MIN
    g = mrp["suficiencia_previstas_adenocarcinoma"]
    res["criterio_M2"] = bool(g["n"] and g["media"] > 0 and g["ic95"][0] > 0)
    g = mrq["suficiencia_previstas_isup0"]
    res["criterio_M3"] = bool(g["n"] and g["media"] > 0 and g["ic95"][0] > 0)
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(" | ".join(f"{c} {'SIM' if res[f'criterio_{c}'] else 'NÃO'}" for c in ("M1", "M2", "M3")))


if __name__ == "__main__":
    main()
