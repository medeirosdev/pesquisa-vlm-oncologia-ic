"""
PANDA: a troca de centro é o problema maior (kappa ~0,80 dentro do Radboud, 0,24 com o ABMIL e 0,44 com o GAT-MIL no
Karolinska; gat_mil_panda.py). Duas correções que não usam nenhum rótulo do Karolinska, testadas contra a linha de
base com os mesmos modelos.

Fixado ANTES de rodar (commit anterior aos resultados):
  Treino nas 600 biópsias do Radboud, teste nas 300 do Karolinska (as mesmas de panda_mil.py).
  Braços:
     R0 (linha de base): embeddings originais (amostra2000.npy).
     R1, padronização por centro: cada dimensão do embedding menos a média e dividida pelo desvio, calculados em
        todos os patches das biópsias do próprio centro (Radboud: as 600 de treino; Karolinska: as 300 de teste, sem
        rótulo). Usa os patches do centro novo sem rótulo; na prática exige um lote de lâminas do centro antes de usar.
     R2, normalização de cor: embeddings recalculados depois da normalização de Reinhard pra cor média do treino
        (dados/panda/panda_embutir_reinhard.py: amostra2000_reinhard.npy).
  Modelos: ABMIL (mil_atencao.treinar) e GAT-MIL (gat_mil.treinar, 8 vizinhos encostados, como em gat_mil_panda.py),
     k = 6, 5 sementes, média das probabilidades, nenhum ajuste.
  Métrica: kappa quadrático (ISUP 0-5) nas 300; diferença pareada com IC 95% por bootstrap (2.000, semente 0).
  Critério N1: com o GAT-MIL, kappa(R1) - kappa(R0) > 0 com limite inferior do IC > 0.
  Critério N2: com o GAT-MIL, kappa(R2) - kappa(R0) > 0 com limite inferior do IC > 0.
  Também reportado (sem critério): as mesmas diferenças com o ABMIL; AUC benigno × câncer; acurácia exata; previstos
     como ISUP 3; matrizes de confusão.

Uso (venv do projeto; GPU; depois de panda_embutir_reinhard.py):
    .venv/bin/python mil/panda/panda_centro.py
Saída: resultados/panda_centro/resumo.json
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402

import gat_mil  # noqa: E402
import mil_atencao  # noqa: E402
from comum.lamina import RESULTADOS_DIR  # noqa: E402
from gat_mil_panda import carregar  # noqa: E402
from panda_mil import PASTA, auc_rank, biopsias, kappa_quadratico  # noqa: E402

K = 6
SAIDA = RESULTADOS_DIR / "panda_centro"
N_BOOTSTRAP = 2000


def padronizar_por_centro(X, ids_por_centro):
    Y = {}
    for ids in ids_por_centro:
        tudo = torch.cat([X[i] for i in ids])
        m, s = tudo.mean(0), tudo.std(0) + 1e-6
        for i in ids:
            Y[i] = (X[i] - m) / s
    return Y


def prever(X, G, tr, te, y, dispositivo):
    P = {m: {i: np.zeros(K) for i in te} for m in ("abmil", "gat")}
    ytr = np.array([y[i] for i in tr])
    for semente in mil_atencao.SEMENTES:
        a = mil_atencao.treinar([X[i] for i in tr], ytr, semente, dispositivo, k=K).eval()
        b = gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], ytr, semente, dispositivo, k=K).eval()
        with torch.no_grad():
            for i in te:
                x = X[i].to(dispositivo)
                P["abmil"][i] += torch.softmax(a(x)[0], 0).cpu().numpy() / len(mil_atencao.SEMENTES)
                P["gat"][i] += torch.softmax(b(x, G[i].to(dispositivo))[0], 0).cpu().numpy() / len(mil_atencao.SEMENTES)
        print(f"    semente {semente} pronta", flush=True)
    return P


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    y = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X0, G = carregar(tr + te)
    bracos = {"R0": X0, "R1": padronizar_por_centro(X0, [tr, te]),
              "R2": {i: torch.from_numpy(np.load(PASTA / i / "amostra2000_reinhard.npy")) for i in tr + te}}
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    pred, prob = {}, {}
    for nome, X in bracos.items():
        print(f"Braço {nome}", flush=True)
        P = prever(X, G, tr, te, y, dispositivo)
        for m in P:
            prob[(nome, m)] = P[m]
            pred[(nome, m)] = np.array([int(P[m][i].argmax()) for i in te])
    real = np.array([y[i] for i in te])

    def kappas(idx):
        return {f"{b}|{m}": kappa_quadratico(real[idx], pred[(b, m)][idx], K) for b, m in pred}

    k0 = kappas(np.arange(len(te)))
    rng, boot = random.Random(0), {}
    for _ in range(N_BOOTSTRAP):
        idx = np.array([rng.randrange(len(te)) for _ in te])
        k = kappas(idx)
        for m in ("abmil", "gat"):
            for b in ("R1", "R2"):
                boot.setdefault(f"{b}-R0|{m}", []).append(k[f"{b}|{m}"] - k[f"R0|{m}"])
            for b in ("R0", "R1", "R2"):
                boot.setdefault(f"{b}|{m}", []).append(k[f"{b}|{m}"])
    ic = {c: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for c, v in boot.items()}
    resumo = {"n_treino": len(tr), "n_teste": len(te), "por_braco": {}}
    for (b, m), p in pred.items():
        conf = np.zeros((K, K), int)
        for r, q in zip(real, p):
            conf[r, q] += 1
        pc = np.array([1 - prob[(b, m)][i][0] for i in te])
        resumo["por_braco"][f"{b}|{m}"] = {
            "kappa": round(k0[f"{b}|{m}"], 3), "ic95": ic[f"{b}|{m}"],
            "auc_benigno_x_cancer": round(auc_rank(pc[real >= 1], pc[real == 0]), 3),
            "acuracia_exata": round(float(np.mean(real == p)), 3), "previstos_isup3": int((p == 3).sum()),
            "matriz_confusao_real_x_previsto": conf.tolist()}
    for m in ("abmil", "gat"):
        for b in ("R1", "R2"):
            resumo[f"{b}_menos_R0|{m}"] = {"diferenca": round(k0[f"{b}|{m}"] - k0[f"R0|{m}"], 3), "ic95": ic[f"{b}-R0|{m}"]}
    d1, d2 = resumo["R1_menos_R0|gat"], resumo["R2_menos_R0|gat"]
    resumo["criterio_N1"] = d1["diferenca"] > 0 and d1["ic95"][0] > 0
    resumo["criterio_N2"] = d2["diferenca"] > 0 and d2["ic95"][0] > 0
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_braco"}, indent=1, ensure_ascii=False))
    for c, v in resumo["por_braco"].items():
        print(f"  {c}: kappa {v['kappa']} {v['ic95']} | AUC {v['auc_benigno_x_cancer']} | ISUP 3 previstos {v['previstos_isup3']}")
    print(f"N1 (padronização por centro, GAT-MIL): {'SIM' if resumo['criterio_N1'] else 'NÃO'} | "
          f"N2 (Reinhard, GAT-MIL): {'SIM' if resumo['criterio_N2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
