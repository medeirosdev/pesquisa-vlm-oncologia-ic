"""
Método 3, terceira rodada: uma medida de contato tumor–estroma mais robusta a erro de classificação
de núcleo. A medida atual (fração do tumor com >= 1 núcleo de estroma a <= 20 µm) não bateu com a
anotação nem com a classificação treinada no NuCLS (Spearman 0,35): basta um vizinho errado.

Fixado ANTES de rodar (commit anterior aos resultados):
  - Tipos dos núcleos: detecção do CellViT + logística treinada no NuCLS (nucls_classificador.py),
    previsão fora do fold (5 folds oficiais, hospitais separados).
  - Campos: os de teste com >= 10 núcleos de tumor anotados (como antes).
  - Medidas, calculadas igual nos núcleos anotados e nos previstos:
      M1  fração do tumor com >= 1 núcleo de estroma a <= 20 µm (a atual, referência);
      M2  distância mediana do núcleo de tumor ao núcleo de estroma mais próximo, limitada a 50 µm
          (sem estroma no campo = 50);
      M3  fração do tumor com >= 3 núcleos de estroma a <= 20 µm.
  - Critério, por medida: Spearman >= 0,7 E |viés médio| <= 0,10 (M1, M3) ou <= 5 µm (M2).
  - Só a medida que passar volta pro BRACS (DCIS vs. IC), num teste à parte.

Roda no ambiente do CellViT (usa os tokens já salvos por nucls_classificador.py):
    "<HD>/venvs/cellvit/bin/python" validacao/nucls_medidas_robustas.py
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

from categoria_uni import logistica_multinomial
from nucls_cellvit import MIN_TUMOR, NUCLS, SAIDA, anotados
from nucls_classificador import CLASSES, TOKENS, parear_indices, slide_do_fov

RAIO = 20
LIMITE_DIST = 50
CRITERIO = {"M1": 0.10, "M2": 5.0, "M3": 0.10}


def medidas(nucleos):
    tum = np.array([n[:2] for n in nucleos if n[2] == "neoplasico"])
    est = np.array([n[:2] for n in nucleos if n[2] == "conjuntivo"])
    if not len(tum):
        return None
    if not len(est):
        return {"M1": 0.0, "M2": float(LIMITE_DIST), "M3": 0.0}
    arv = cKDTree(est)
    d, _ = arv.query(tum)
    vizinhos = np.array([len(v) for v in arv.query_ball_point(tum, RAIO)])
    return {"M1": float(np.mean(d <= RAIO)), "M2": float(np.median(np.minimum(d, LIMITE_DIST))),
            "M3": float(np.mean(vizinhos >= 3))}


def main():
    fovs = sorted(p.stem for p in (NUCLS / "csv").glob("*.csv"))
    dados = {}
    for nome in fovs:
        z = np.load(TOKENS / f"{nome}.npz")
        gt = anotados(NUCLS / "csv" / f"{nome}.csv")
        dados[nome] = {"gt": gt, "xy": z["xy"], "feats": z["feats"].astype(np.float32),
                       "pares": parear_indices(gt, z["xy"])}

    pred = {}
    divisao = NUCLS / "train_test_splits"
    for k in range(1, 6):
        teste = {r["slide_name"] for r in csv.DictReader(open(divisao / f"fold_{k}_test.csv"))}
        treino = {r["slide_name"] for r in csv.DictReader(open(divisao / f"fold_{k}_train.csv"))}
        X = [d["feats"][j] for n, d in dados.items() if slide_do_fov(n) in treino for _, j in d["pares"]]
        y = [CLASSES.index(d["gt"][i][2]) for n, d in dados.items() if slide_do_fov(n) in treino for i, _ in d["pares"]]
        nomes = [n for n in dados if slide_do_fov(n) in teste and len(dados[n]["xy"])]
        p = logistica_multinomial(np.array(X), np.array(y), np.concatenate([dados[n]["feats"] for n in nomes]), k=len(CLASSES))
        pos = 0
        for n in nomes:
            m = len(dados[n]["xy"])
            pred[n] = [CLASSES[c] for c in p[pos:pos + m]]
            pos += m
        print(f"  fold {k}: {len(nomes)} campos de teste", flush=True)

    pares = {m: ([], []) for m in CRITERIO}
    for n in pred:
        gt = dados[n]["gt"]
        if sum(g[2] == "neoplasico" for g in gt) < MIN_TUMOR:
            continue
        a = medidas(gt)
        b = medidas([(float(x), float(y), t) for (x, y), t in zip(dados[n]["xy"], pred[n])])
        if b is None:
            continue
        for m in CRITERIO:
            pares[m][0].append(a[m])
            pares[m][1].append(b[m])

    resumo = {}
    for m, lim in CRITERIO.items():
        g, p = np.array(pares[m][0]), np.array(pares[m][1])
        rho, vies = float(spearmanr(g, p).statistic), float(np.mean(p - g))
        resumo[m] = {"n_campos": int(len(g)), "spearman": round(rho, 3), "vies_medio": round(vies, 3),
                     "media_anotado": round(float(g.mean()), 3), "media_metodo": round(float(p.mean()), 3),
                     "passou": bool(rho >= 0.7 and abs(vies) <= lim)}
    (SAIDA / "nucls_medidas_robustas.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{'Medida':<8}{'campos':>8}{'Spearman':>10}{'viés':>8}{'anotado':>9}{'método':>8}  passou")
    for m, r in resumo.items():
        print(f"{m:<8}{r['n_campos']:>8}{r['spearman']:>10}{r['vies_medio']:>8}{r['media_anotado']:>9}{r['media_metodo']:>8}  "
              f"{'SIM' if r['passou'] else 'não'}")


if __name__ == "__main__":
    main()
