"""
PANDA: grau ISUP da biópsia (0-5) com o MIL com atenção (mil_atencao.py), mesma receita do BRACS e do TCGA,
treinado nas 600 biópsias do Radboud e testado nas 300 do Karolinska (scripts/panda_baixar_e_embutir.py).

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelo e treino: mil_atencao.treinar, k = 6 classes (ISUP 0-5), 5 sementes, sem nenhum ajuste; probabilidade
     final = média das 5 sementes; ISUP previsto = classe de maior probabilidade. Atenção de cada patch das
     biópsias de teste = média das 5 sementes (usada em panda_descritor_prelaudo.py).
  Critério M1: kappa quadrático ponderado (ISUP 0-5, métrica oficial do PANDA) >= 0,60 no teste.
  Critério M2: AUC benigno (ISUP 0) × câncer (ISUP >= 1), com escore 1 - P(ISUP 0), >= 0,85 no teste.
  Também reportado (sem critério): IC 95% por bootstrap (2.000 reamostras, semente 0); AUC ISUP 1 × ISUP >= 2 entre
     as biópsias com câncer (escore P(ISUP >= 2)); acurácia exata e a +-1 grau; matriz de confusão.
  Biópsias que falharem no download ou na leitura ficam de fora e são listadas.
  Ressalvas: teste com 50 biópsias por ISUP (não é a distribuição natural do Karolinska); rótulos de treino vêm do
     laudo clínico, em geral de um só patologista; os vencedores do desafio (kappa 0,86-0,93) usaram as ~10 mil
     biópsias e muito ajuste.

Uso (venv do projeto; GPU se houver):
    .venv/bin/python validacao/panda_mil.py
Saída: resultados/panda_mil/{resumo.json, <image_id>_atencao.npy}
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import torch

from comum.lamina import RESULTADOS_DIR

LISTA = Path(__file__).resolve().parent.parent / "scripts" / "lista_panda.tsv"
PASTA = RESULTADOS_DIR / "panda"
SAIDA = RESULTADOS_DIR / "panda_mil"
K = 6
KAPPA_MIN = 0.60
AUC_MIN = 0.85
N_BOOTSTRAP = 2000


def kappa_quadratico(a, b, k=K):
    a, b = np.asarray(a), np.asarray(b)
    O = np.zeros((k, k))
    for i, j in zip(a, b):
        O[i, j] += 1
    W = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    return float(1 - (W * O).sum() / (W * E).sum())


def auc_rank(pos, neg):
    """AUC pela soma de postos (Mann-Whitney), com empates em meio ponto."""
    v = np.concatenate([pos, neg])
    ordem = v.argsort(kind="mergesort")
    postos = np.empty(len(v))
    vs = v[ordem]
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and vs[j + 1] == vs[i]:
            j += 1
        postos[ordem[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    n1, n0 = len(pos), len(neg)
    return float((postos[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def biopsias():
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    prontas = [l for l in linhas if (PASTA / l["image_id"] / "meta.json").exists()]
    return linhas, prontas


def main():
    from mil_atencao import SEMENTES, treinar
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas, prontas = biopsias()
    faltam = [l["image_id"] for l in linhas if l not in prontas]
    tr = [l for l in prontas if l["conjunto"] == "treino"]
    te = [l for l in prontas if l["conjunto"] == "teste"]
    X = {l["image_id"]: torch.from_numpy(np.load(PASTA / l["image_id"] / "amostra2000.npy")) for l in prontas}
    y = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    P = {l["image_id"]: np.zeros(K) for l in te}
    att = {l["image_id"]: np.zeros(len(X[l["image_id"]])) for l in te}
    for semente in SEMENTES:
        modelo = treinar([X[l["image_id"]] for l in tr], np.array([y[l["image_id"]] for l in tr]), semente, dispositivo, k=K)
        modelo.eval()
        with torch.no_grad():
            for l in te:
                logit, a = modelo(X[l["image_id"]].to(dispositivo))
                P[l["image_id"]] += torch.softmax(logit, 0).cpu().numpy() / len(SEMENTES)
                att[l["image_id"]] += a.cpu().numpy() / len(SEMENTES)
        print(f"  semente {semente} pronta", flush=True)
    for l in te:
        np.save(SAIDA / f"{l['image_id']}_atencao.npy", att[l["image_id"]].astype(np.float32))

    ids = [l["image_id"] for l in te]
    real = np.array([y[i] for i in ids])
    pred = np.array([int(P[i].argmax()) for i in ids])
    p_cancer = np.array([1 - P[i][0] for i in ids])
    p_sig = np.array([P[i][2:].sum() for i in ids])

    def metricas(idx):
        r, p = real[idx], pred[idx]
        out = {"kappa": kappa_quadratico(r, p)}
        if (r == 0).any() and (r >= 1).any():
            out["auc_cancer"] = auc_rank(p_cancer[idx][r >= 1], p_cancer[idx][r == 0])
        c = r >= 1
        if (r[c] == 1).any() and (r[c] >= 2).any():
            out["auc_isup1_vs_2mais"] = auc_rank(p_sig[idx][c & (r >= 2)], p_sig[idx][c & (r == 1)])
        return out

    tudo = metricas(np.arange(len(ids)))
    rng, boot = random.Random(0), {k: [] for k in tudo}
    for _ in range(N_BOOTSTRAP):
        idx = np.array([rng.randrange(len(ids)) for _ in ids])
        for k, v in metricas(idx).items():
            boot[k].append(v)
    ic = {k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for k, v in boot.items()}
    conf = np.zeros((K, K), int)
    for r, p in zip(real, pred):
        conf[r, p] += 1
    resumo = {"n_treino": len(tr), "n_teste": len(te), "faltam": faltam,
              "kappa_quadratico": round(tudo["kappa"], 3), "ic95_kappa": ic["kappa"],
              "auc_benigno_x_cancer": round(tudo["auc_cancer"], 3), "ic95_auc_cancer": ic["auc_cancer"],
              "auc_isup1_x_isup2mais": round(tudo["auc_isup1_vs_2mais"], 3), "ic95_auc_isup1_x_2mais": ic["auc_isup1_vs_2mais"],
              "acuracia_exata": round(float(np.mean(real == pred)), 3),
              "acuracia_mais_menos_1": round(float(np.mean(np.abs(real - pred) <= 1)), 3),
              "matriz_confusao_real_x_previsto": conf.tolist(),
              "por_biopsia": {i: {"real": int(r), "previsto": int(p), "probs": [round(float(v), 4) for v in P[i]]}
                              for i, r, p in zip(ids, real, pred)}}
    resumo["criterio_M1"] = resumo["kappa_quadratico"] >= KAPPA_MIN
    resumo["criterio_M2"] = resumo["auc_benigno_x_cancer"] >= AUC_MIN
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_biopsia"}, indent=1, ensure_ascii=False))
    print(f"Critério M1 (kappa quadrático >= {KAPPA_MIN}): {'SIM' if resumo['criterio_M1'] else 'NÃO'} | "
          f"Critério M2 (AUC benigno × câncer >= {AUC_MIN}): {'SIM' if resumo['criterio_M2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
