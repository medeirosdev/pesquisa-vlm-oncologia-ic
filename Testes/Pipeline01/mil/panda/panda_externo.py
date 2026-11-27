"""
Próstata, teste externo do Karolinska (revisão 02, item B): o modelo escolhido olhando as 300 biópsias do Karolinska
(agora chamadas de "desenvolvimento") é avaliado, congelado, em 500 biópsias do Karolinska nunca usadas, na
distribuição natural de graus. Também mede o quanto a padronização por centro depende do lote do centro novo e calibra
a confiança fora do conjunto de teste.

Fixado ANTES de baixar as biópsias externas (commit anterior a qualquer dado externo):
  Externo: dados/panda/lista_panda_externo.tsv (dados/panda/panda_externo_baixar.py --sortear: 500 do Karolinska fora
     das 300, distribuição natural), embeddings pelo mesmo processo, em resultados/panda_externo/<image_id>/. Biópsias que falharem no download
     ficam de fora e são contadas.
  Modelo congelado: GAT-MIL (gat_mil.treinar, k = 6, 40 épocas, sementes 0 a 4) treinado nas 600 do Radboud com os
     embeddings padronizados pela média e desvio do Radboud, como em panda_repeticoes.py (execução 0). Probabilidade =
     média das 5 sementes. Nada é ajustado no externo.
  Padronização do externo (só a estatística muda; o modelo é o mesmo):
     (a) lote inteiro: média e desvio de todos os patches das biópsias externas;
     (b) lote pequeno: média e desvio de k biópsias externas sorteadas, k = 10, 25, 50 (5 sorteios cada, semente
         [k, r]), aplicados a todas as externas;
     (c) sem dado do centro novo: média e desvio do Radboud.
  Medidas (em cada caso): kappa quadrático, AUC câncer × benigno (1 − P(ISUP 0)), sensibilidade para câncer,
     especificidade para benigno, acurácia de grau exato, matriz de confusão; IC 95% por bootstrap das biópsias (2.000,
     semente 0) para kappa e AUC em (a).
  Critérios:
     K1 (o modelo escolhido se mantém num teste intocado): em (a), kappa quadrático >= 0,60 e AUC câncer >= 0,85.
     K2 (um lote pequeno basta): em (b) com k = 25, a mediana dos 5 sorteios do kappa >= kappa(a) − 0,05.
  Também reportado (sem critério): o mesmo nas 300 de desenvolvimento (referência); calibração: temperatura ajustada nas
     300 de desenvolvimento (padronizadas com o lote delas) e aplicada ao externo (a), ECE antes e depois (10 faixas) e
     acerto na faixa "alta" (>= 0,70); multi-ramo padronizado (mil_multiramo.MRMIL, mesmas sementes) no externo (a), para
     saber se o kappa exploratório de 0,721 no desenvolvimento se mantém.
  Limites conhecidos: o PANDA não identifica pacientes, então biópsias do mesmo paciente podem estar no desenvolvimento e
     no externo (os dois são do Karolinska; nenhum dos dois entra no treino); um só centro externo.

Nota: esta versão substitui uma versão anterior não commitada deste arquivo (sobrescrita por engano em 27/11).
Uso (venv do projeto; GPU; depois de baixar o externo): .venv/bin/python mil/panda/panda_externo.py
Saída: resultados/panda_externo/resumo.json
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "panda_externo"
LISTA_EXT = Path(__file__).resolve().parents[2] / "dados" / "panda" / "lista_panda_externo.tsv"
K, N_BOOT = 6, 2000
KAPPA_MIN, AUC_MIN, TOL = 0.60, 0.85, 0.05


def kappa_q(real, pred, k=K):
    O = np.zeros((k, k))
    for r, p in zip(real, pred):
        O[r, p] += 1
    W = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    return float(1 - (W * O).sum() / (W * E).sum())


def auc(pos, neg):
    pos, neg = np.asarray(pos), np.asarray(neg)
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def medidas(P, real, ic=False):
    pred = P.argmax(1)
    esc = 1 - P[:, 0]
    r = {"n": len(real), "kappa_quadratico": round(kappa_q(real, pred), 3),
         "auc_cancer": round(auc(esc[real >= 1], esc[real == 0]), 3),
         "sensibilidade_cancer": round(float(np.mean(pred[real >= 1] >= 1)), 3),
         "especificidade_benigno": round(float(np.mean(pred[real == 0] == 0)), 3),
         "acuracia_exata": round(float(np.mean(pred == real)), 3),
         "matriz_real_x_previsto": np.bincount(real * K + pred, minlength=K * K).reshape(K, K).tolist()}
    if ic:
        rng, kb, ab = random.Random(0), [], []
        for _ in range(N_BOOT):
            idx = np.array([rng.randrange(len(real)) for _ in real])
            kb.append(kappa_q(real[idx], pred[idx]))
            rr = real[idx]
            ab.append(auc(esc[idx][rr >= 1], esc[idx][rr == 0]))
        r["kappa_ic95"] = [round(float(np.percentile(kb, q)), 3) for q in (2.5, 97.5)]
        r["auc_ic95"] = [round(float(np.percentile(ab, q)), 3) for q in (2.5, 97.5)]
    return r


def padronizar(X, ids, fonte):
    import torch
    tudo = torch.cat([X[i] for i in fonte])
    m, s = tudo.mean(0), tudo.std(0) + 1e-6
    return {i: (X[i] - m) / s for i in ids}


def ece(P, real):
    conf, acerto = P.max(1), (P.argmax(1) == real).astype(float)
    tot = 0.0
    for lo, hi in zip(np.linspace(0, 1, 11)[:-1], np.linspace(0, 1, 11)[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if m.any():
            tot += m.mean() * abs(acerto[m].mean() - conf[m].mean())
    alta = conf >= 0.70
    return {"ece": round(float(tot), 4), "alta_n": int(alta.sum()),
            "alta_acerto": round(float(acerto[alta].mean()), 3) if alta.any() else None}


def temperatura(P, y):
    from scipy.optimize import minimize_scalar
    lp = np.log(np.clip(P, 1e-6, 1))

    def nll(t):
        z = lp / t
        z = z - z.max(1, keepdims=True)
        return -float((z[np.arange(len(y)), y] - np.log(np.exp(z).sum(1))).mean())
    return float(minimize_scalar(nll, bounds=(0.05, 20.0), method="bounded").x)


def aplicar_t(P, t):
    z = np.log(np.clip(P, 1e-6, 1)) / t
    z = np.exp(z - z.max(1, keepdims=True))
    return z / z.sum(1, keepdims=True)


def main():
    import torch
    import gat_mil
    from gat_mil_panda import PASTA, carregar
    from panda_mil import biopsias
    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    yv = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    dev = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    ext_lista = list(csv.DictReader(open(LISTA_EXT, encoding="utf-8"), delimiter="\t"))
    ext = [l["image_id"] for l in ext_lista if (RESULTADOS_DIR / "panda_externo" / l["image_id"] / "meta.json").exists()]
    yv.update({l["image_id"]: int(l["isup_grade"]) for l in ext_lista})
    X, G = carregar(tr + dev)
    import gat_mil as gm
    import torch as _t
    pasta_ext = RESULTADOS_DIR / "panda_externo"
    for i in ext:
        X[i] = _t.from_numpy(np.load(pasta_ext / i / "amostra2000.npy"))
        xy = np.loadtxt(pasta_ext / i / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        G[i] = gm.arestas_vizinhos(xy, json.loads((pasta_ext / i / "meta.json").read_text(encoding="utf-8"))["lado_px"])
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    Xtr = padronizar(X, tr, tr)
    ytr = np.array([yv[i] for i in tr])
    modelos = [gat_mil.treinar([Xtr[i] for i in tr], [G[i] for i in tr], ytr, s, dispositivo, k=K).eval() for s in range(5)]

    def prever(Xp, ids):
        with torch.no_grad():
            return np.array([np.mean([torch.softmax(m(Xp[i].to(dispositivo), G[i].to(dispositivo))[0], 0).cpu().numpy()
                                      for m in modelos], 0) for i in ids])

    real_ext, real_dev = np.array([yv[i] for i in ext]), np.array([yv[i] for i in dev])
    P_dev = prever(padronizar(X, dev, dev), dev)
    P_a = prever(padronizar(X, ext, ext), ext)
    res = {"externo_listados": len(ext_lista), "externo_usados": len(ext),
           "isup_externo": np.bincount(real_ext, minlength=K).tolist(),
           "desenvolvimento": medidas(P_dev, real_dev), "externo_a_lote_inteiro": medidas(P_a, real_ext, ic=True),
           "externo_c_so_radboud": medidas(prever(padronizar(X, ext, tr), ext), real_ext)}
    lotes = {}
    for k in (10, 25, 50):
        ks = []
        for r in range(5):
            sub = random.Random(k * 100 + r).sample(ext, k)
            ks.append(medidas(prever(padronizar(X, ext, sub), ext), real_ext)["kappa_quadratico"])
        lotes[str(k)] = {"kappas": ks, "mediana": round(float(np.median(ks)), 3)}
    res["externo_b_lote_pequeno"] = lotes
    t = temperatura(P_dev, real_dev)
    res["calibracao"] = {"temperatura_ajustada_no_desenvolvimento": round(t, 3), "externo_antes": ece(P_a, real_ext),
                         "externo_depois": ece(aplicar_t(P_a, t), real_ext)}
    try:
        from mil_multiramo import treinar_mr
        mr = [treinar_mr([Xtr[i] for i in tr], ytr, s, dispositivo, K).eval() for s in range(5)]
        Xa = padronizar(X, ext, ext)
        with torch.no_grad():
            Pm = np.array([np.mean([torch.softmax(m(Xa[i].to(dispositivo))[0], 0).cpu().numpy() for m in mr], 0) for i in ext])
        res["multiramo_externo_a"] = medidas(Pm, real_ext)
    except Exception as e:  # noqa: BLE001 — opcional
        res["multiramo_externo_a"] = f"falhou: {type(e).__name__}: {e}"
    a = res["externo_a_lote_inteiro"]
    res["criterio_K1"] = a["kappa_quadratico"] >= KAPPA_MIN and a["auc_cancer"] >= AUC_MIN
    res["criterio_K2"] = lotes["25"]["mediana"] >= a["kappa_quadratico"] - TOL
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"K1 {'SIM' if res['criterio_K1'] else 'NÃO'} | K2 {'SIM' if res['criterio_K2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
