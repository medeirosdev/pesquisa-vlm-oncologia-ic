"""
Pulmão, Adenocarcinoma × Carcinoma Epidermoide (dataset do orientador, 52 pacientes: 25 × 27): dá para separar os dois
subtipos só pelo núcleo, sem o tecido em volta? E quanto o contexto acrescenta?

Fixado ANTES de rodar (commit anterior aos resultados):
  Dados: saídas de preparar.py (embeddings UNI2-h, medidas clássicas, partes). Rótulo: DIAGNOSIS do labels.xlsx.
  Avaliação: por paciente, nunca por imagem. 5 repetições de validação cruzada em 5 partes estratificadas (partes em
     resultados/casos.csv); a probabilidade final de cada paciente é a média das 5 repetições (sempre fora da parte de
     treino). Métricas: AUC e acurácia balanceada (corte 0,5). IC 95% por bootstrap por paciente (2.000, semente 0),
     pareado nas diferenças.
  Braços (k = 2; MIL = mil_atencao.treinar: ABMIL, 40 épocas, Adam 1e-4, semente = repetição):
     T1  clássico nos núcleos: média e desvio por paciente de cada medida de preparar.py, padronizadas com a média e o
         desvio do treino; regressão logística com L2 (C = 1), sem ajuste.
     T2  biópsia: MIL sobre os recortes dos campos do paciente (embeddings "campos").
     T3  só núcleos: MIL sobre os núcleos do paciente pintados de branco em volta ("nucleo_05").
     T4  núcleo + contexto: MIL sobre as mesmas janelas sem pintar ("contexto_05").
  Critérios:
     P1 (teto): acurácia balanceada de T2 >= 0,80.
     P2 (o núcleo sozinho carrega o subtipo): AUC de T3 com limite inferior do IC > 0,5.
     P3 (o contexto ajuda): AUC(T4) - AUC(T3) > 0, limite inferior do IC > 0.
     P4 (UNI2-h ganha da visão clássica no núcleo): AUC(T3) - AUC(T1) > 0, limite inferior do IC > 0.
  Também reportado, sem critério: T3 e T4 na escala original (nucleo_10, contexto_10); média dos embeddings do
     paciente + regressão logística (como T1) para campos, nucleo_05 e contexto_05; fusão T2 + T3 (média das
     probabilidades); acerto por classe.
  Ressalva: com 52 pacientes o IC de uma acurácia perto de 0,8 tem cerca de ±0,11; diferenças pequenas não aparecem.

Uso (venv da Pipeline01; GPU; depois de preparar.py):
    ../Pipeline01/.venv/bin/python testar.py
Saída: resultados/resumo.json
"""

import csv
import json
import random
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "Pipeline01"))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402
from scipy.optimize import minimize  # noqa: E402

import mil_atencao  # noqa: E402

RES = AQUI / "resultados"
REPETICOES, PARTES, N_BOOTSTRAP, BA_MIN = 5, 5, 2000, 0.80


def logistica(Xtr, ytr, Xte, C=1.0):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    A1, B1 = np.c_[A, np.ones(len(A))], np.c_[B, np.ones(len(B))]

    def f(w):
        z = A1 @ w
        p = 1 / (1 + np.exp(-z))
        reg = 0.5 / C * (w[:-1] @ w[:-1])
        loss = np.sum(np.logaddexp(0, z) - ytr * z) + reg
        g = A1.T @ (p - ytr)
        g[:-1] += w[:-1] / C
        return loss, g

    w = minimize(f, np.zeros(A1.shape[1]), jac=True, method="L-BFGS-B").x
    return 1 / (1 + np.exp(-(B1 @ w)))


def auc(p, y):
    return mil_atencao.auc(p[y == 1], p[y == 0])


def ba(p, y):
    pred = (p >= 0.5).astype(int)
    return float(np.mean([np.mean(pred[y == k] == k) for k in (0, 1)]))


def main():
    linhas = list(csv.DictReader(open(RES / "casos.csv", encoding="utf-8")))
    casos = [l["codigo"] for l in linhas]
    y = np.array([int(l["classe"]) for l in linhas])
    parte = np.array([[int(l[f"parte_r{r}"]) for r in range(REPETICOES)] for l in linhas])
    ind = json.load(open(RES / "indices.json"))
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    def bolsas(nome, chave):
        E = np.load(RES / f"emb_{nome}.npy")
        dono = np.array(ind[chave])
        return [torch.from_numpy(E[dono == c].astype(np.float32)) for c in casos]

    B = {"campos": bolsas("campos", "campos")}
    for n in ("nucleo_05", "contexto_05", "nucleo_10", "contexto_10"):
        B[n] = bolsas(n, "nucleos")
    F = np.load(RES / "classicas.npy")
    dono = np.array(ind["nucleos"])
    Xc = np.array([np.r_[F[dono == c].mean(0), F[dono == c].std(0)] for c in casos])

    P = {}

    def cv(nome, ajustar):
        p = np.zeros(len(casos))
        for r in range(REPETICOES):
            for k in range(PARTES):
                te, tr = np.where(parte[:, r] == k)[0], np.where(parte[:, r] != k)[0]
                p[te] += ajustar(tr, te, r) / REPETICOES
        P[nome] = p
        print(f"  {nome}: AUC {auc(p, y):.3f}, acurácia balanceada {ba(p, y):.3f}", flush=True)

    def mil(b):
        def ajustar(tr, te, r):
            m = mil_atencao.treinar([b[i] for i in tr], y[tr], r, dev, k=2).eval()
            with torch.no_grad():
                return np.array([torch.softmax(m(b[i].to(dev))[0], 0)[1].item() for i in te])
        return ajustar

    def media_log(b):
        X = np.array([x.mean(0).numpy() for x in b])
        return lambda tr, te, r: logistica(X[tr], y[tr], X[te])

    cv("T1_classico_nucleos", lambda tr, te, r: logistica(Xc[tr], y[tr], Xc[te]))
    cv("T2_biopsia_mil", mil(B["campos"]))
    cv("T3_nucleo_mil", mil(B["nucleo_05"]))
    cv("T4_contexto_mil", mil(B["contexto_05"]))
    cv("T3_nucleo_mil_escala_original", mil(B["nucleo_10"]))
    cv("T4_contexto_mil_escala_original", mil(B["contexto_10"]))
    for n, b in (("biopsia", "campos"), ("nucleo", "nucleo_05"), ("contexto", "contexto_05")):
        cv(f"media_logistica_{n}", media_log(B[b]))
    P["fusao_T2_T3"] = (P["T2_biopsia_mil"] + P["T3_nucleo_mil"]) / 2

    rng = random.Random(0)
    amostras = [np.array([rng.randrange(len(casos)) for _ in casos]) for _ in range(N_BOOTSTRAP)]
    amostras = [a for a in amostras if 0 < y[a].sum() < len(a)]

    def ic(fn):
        v = [fn(a) for a in amostras]
        return [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]

    out = {"pacientes": len(casos), "adenocarcinoma": int((y == 0).sum()), "epidermoide": int((y == 1).sum()),
           "maior_erro_de_localizacao_dos_nucleos": ind["maior_erro_de_localizacao"], "bracos": {}}
    for n, p in P.items():
        pred = (p >= 0.5).astype(int)
        out["bracos"][n] = {"auc": round(auc(p, y), 3), "auc_ic95": ic(lambda a: auc(p[a], y[a])),
                            "acuracia_balanceada": round(ba(p, y), 3), "ba_ic95": ic(lambda a: ba(p[a], y[a])),
                            "acerto_adeno": f"{int(np.sum((pred == 0) & (y == 0)))}/{int((y == 0).sum())}",
                            "acerto_epidermoide": f"{int(np.sum((pred == 1) & (y == 1)))}/{int((y == 1).sum())}"}

    def dif(a, b):
        d = auc(P[a], y) - auc(P[b], y)
        return {"diferenca_auc": round(d, 3), "ic95": ic(lambda s: auc(P[a][s], y[s]) - auc(P[b][s], y[s]))}

    out["T4_menos_T3"] = dif("T4_contexto_mil", "T3_nucleo_mil")
    out["T3_menos_T1"] = dif("T3_nucleo_mil", "T1_classico_nucleos")
    out["T2_menos_T4"] = dif("T2_biopsia_mil", "T4_contexto_mil")
    out["T4_menos_T3_escala_original"] = dif("T4_contexto_mil_escala_original", "T3_nucleo_mil_escala_original")
    b = out["bracos"]
    out["criterios"] = {
        "P1_teto_biopsia": b["T2_biopsia_mil"]["acuracia_balanceada"] >= BA_MIN,
        "P2_nucleo_acima_do_acaso": b["T3_nucleo_mil"]["auc_ic95"][0] > 0.5,
        "P3_contexto_ajuda": out["T4_menos_T3"]["diferenca_auc"] > 0 and out["T4_menos_T3"]["ic95"][0] > 0,
        "P4_uni_ganha_do_classico": out["T3_menos_T1"]["diferenca_auc"] > 0 and out["T3_menos_T1"]["ic95"][0] > 0}
    out["por_caso"] = {c: {"classe": int(y[i]), **{n: round(float(p[i]), 3) for n, p in P.items()}}
                       for i, c in enumerate(casos)}
    (RES / "resumo.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    for n, v in b.items():
        print(f"{n:36s} AUC {v['auc']:.3f} {v['auc_ic95']} | BA {v['acuracia_balanceada']:.3f} {v['ba_ic95']}")
    for d in ("T4_menos_T3", "T3_menos_T1", "T2_menos_T4", "T4_menos_T3_escala_original"):
        print(d, out[d])
    print("critérios:", out["criterios"])


if __name__ == "__main__":
    main()
