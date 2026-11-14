"""
Rede de grafos (rede_grafos.py) × ABMIL × GAT-MIL no PANDA (grau ISUP 0-5).

Fixado ANTES de rodar (commit anterior aos resultados):
  Dados: as 900 biópsias de panda_mil.py (600 Radboud de treino, 300 Karolinska de teste), embeddings originais. No
     PANDA todos os patches de tecido estão embutidos, então a janela de 7 x 7 patches em volta de cada ponto é densa.
  Pontos de interesse (16 por biópsia, centros a >= 1 mm, janela de 7 x 7 patches): pela atenção de um ABMIL que não
     viu a biópsia:
     - biópsias de treino: atenção fora da parte (out-of-fold) de um ABMIL em validação cruzada em 5 partes no
       Radboud (as partes estratificadas por ISUP de gat_mil_panda.py, semente 0), média das 5 sementes;
     - biópsias de teste do Karolinska: a atenção salva por panda_mil.py (ABMIL treinado nas 600, média das 5 sementes).
  Modelos: A = ABMIL e B = GAT-MIL (como em gat_mil_panda.py, todos os patches); C = rede de grafos (só os patches
     das janelas). Mesma receita de treino, 5 sementes, média das probabilidades, nenhum ajuste.
  Cenário 1, entre centros: treino nas 600, teste nas 300.
  Cenário 2, dentro do Radboud: validação cruzada nas mesmas 5 partes; os pontos de todas as 600 vêm da atenção fora
     da parte. Ressalva: o ABMIL que escolhe os pontos de uma biópsia de treino da parte k viu as biópsias de teste
     dessa parte (não as próprias); efeito indireto e pequeno, e só no modelo C (A e B usam todos os patches).
  Métrica: kappa quadrático; diferença pareada com IC 95% por bootstrap (2.000, semente 0).
  Critério H1: no cenário 1, kappa(C) - kappa(A) > 0 com limite inferior do IC > 0.
  Critério H2: no cenário 2, idem.
  Também reportado (sem critério): C - B (contra o GAT-MIL) nos dois cenários; AUC benigno × câncer; acurácia exata;
     previstos como ISUP 3; pontos e patches usados por biópsia.

Uso (venv do projeto; GPU):
    .venv/bin/python mil/rede_grafos/rede_grafos_panda.py
Saída: resultados/rede_grafos_panda/{resumo.json, atencao_fora_da_parte/<image_id>.npy}
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
import rede_grafos  # noqa: E402
from comum.lamina import RESULTADOS_DIR  # noqa: E402
from gat_mil_panda import PARTES, carregar, partes_estratificadas  # noqa: E402
from panda_mil import PASTA, auc_rank, biopsias, kappa_quadratico  # noqa: E402
from panda_mil import SAIDA as SAIDA_MIL  # noqa: E402

K = 6
N_BOOTSTRAP = 2000
SAIDA = RESULTADOS_DIR / "rede_grafos_panda"
SEMS = mil_atencao.SEMENTES


def atencao_fora_da_parte(tr, X, y, parte, dispositivo):
    pasta = SAIDA / "atencao_fora_da_parte"
    pasta.mkdir(parents=True, exist_ok=True)
    if all((pasta / f"{i}.npy").exists() for i in tr):
        return {i: np.load(pasta / f"{i}.npy") for i in tr}
    att = {i: np.zeros(len(X[i])) for i in tr}
    for p in range(PARTES):
        dentro = [i for i in tr if parte[i] != p]
        fora = [i for i in tr if parte[i] == p]
        for s in SEMS:
            m = mil_atencao.treinar([X[i] for i in dentro], np.array([y[i] for i in dentro]), s, dispositivo, k=K).eval()
            with torch.no_grad():
                for i in fora:
                    att[i] += m(X[i].to(dispositivo))[1].cpu().numpy() / len(SEMS)
        print(f"  atenção fora da parte: parte {p + 1}/{PARTES}", flush=True)
    for i in tr:
        np.save(pasta / f"{i}.npy", att[i].astype(np.float32))
    return att


def prever(dentro, fora, X, Gviz, R, y, dispositivo):
    P = {m: {i: np.zeros(K) for i in fora} for m in "ABC"}
    ytr = np.array([y[i] for i in dentro])
    for s in SEMS:
        a = mil_atencao.treinar([X[i] for i in dentro], ytr, s, dispositivo, k=K).eval()
        b = gat_mil.treinar([X[i] for i in dentro], [Gviz[i] for i in dentro], ytr, s, dispositivo, k=K).eval()
        c = rede_grafos.treinar([X[i] for i in dentro], [R[i] for i in dentro], ytr, s, dispositivo, k=K).eval()
        with torch.no_grad():
            for i in fora:
                x = X[i].to(dispositivo)
                P["A"][i] += torch.softmax(a(x)[0], 0).cpu().numpy() / len(SEMS)
                P["B"][i] += torch.softmax(b(x, Gviz[i].to(dispositivo))[0], 0).cpu().numpy() / len(SEMS)
                P["C"][i] += torch.softmax(c(x, rede_grafos.para(R[i], dispositivo))[0], 0).cpu().numpy() / len(SEMS)
        print(f"    semente {s} pronta", flush=True)
    return P


def avaliar(ids, y, P):
    real = np.array([y[i] for i in ids])
    pred = {m: np.array([int(P[m][i].argmax()) for i in ids]) for m in "ABC"}

    def ks(idx):
        k = {m: kappa_quadratico(real[idx], pred[m][idx], K) for m in "ABC"}
        return {**k, "C-A": k["C"] - k["A"], "C-B": k["C"] - k["B"]}

    k0 = ks(np.arange(len(ids)))
    rng, boot = random.Random(0), {}
    for _ in range(N_BOOTSTRAP):
        idx = np.array([rng.randrange(len(ids)) for _ in ids])
        for c, v in ks(idx).items():
            boot.setdefault(c, []).append(v)
    ic = {c: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for c, v in boot.items()}
    out = {"n": len(ids)}
    for m, nome in (("A", "abmil"), ("B", "gat_mil"), ("C", "rede_grafos")):
        pc = np.array([1 - P[m][i][0] for i in ids])
        out[nome] = {"kappa": round(k0[m], 3), "ic95": ic[m],
                     "auc_benigno_x_cancer": round(auc_rank(pc[real >= 1], pc[real == 0]), 3),
                     "acuracia_exata": round(float(np.mean(real == pred[m])), 3),
                     "previstos_isup3": int((pred[m] == 3).sum())}
    out["C_menos_A"] = {"diferenca": round(k0["C-A"], 3), "ic95": ic["C-A"]}
    out["C_menos_B"] = {"diferenca": round(k0["C-B"], 3), "ic95": ic["C-B"]}
    out["criterio"] = k0["C-A"] > 0 and ic["C-A"][0] > 0
    return out


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    y = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X, Gviz = carregar(tr + te)
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    parte = partes_estratificadas(tr, y)
    att = atencao_fora_da_parte(tr, X, y, parte, dispositivo)
    att.update({i: np.load(SAIDA_MIL / f"{i}_atencao.npy") for i in te})
    R = {}
    for i in tr + te:
        xy = np.loadtxt(PASTA / i / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        R[i] = rede_grafos.montar(xy, json.loads((PASTA / i / "meta.json").read_text())["lado_px"], att[i])
    n_pontos = [len(R[i]["pontos"]) for i in tr + te]
    n_nos = [len(R[i]["nos"]) / len(X[i]) for i in tr + te]
    print(f"pontos por biópsia: média {np.mean(n_pontos):.1f} (mín {min(n_pontos)}); fração dos patches nas janelas "
          f"(com repetição): {np.mean(n_nos):.2f}", flush=True)

    print("Cenário 1: Radboud -> Karolinska", flush=True)
    c1 = avaliar(te, y, prever(tr, te, X, Gviz, R, y, dispositivo))
    print(json.dumps(c1, ensure_ascii=False), flush=True)
    print("Cenário 2: validação cruzada dentro do Radboud", flush=True)
    P2 = {m: {} for m in "ABC"}
    for p in range(PARTES):
        print(f"  parte {p + 1}/{PARTES}", flush=True)
        P = prever([i for i in tr if parte[i] != p], [i for i in tr if parte[i] == p], X, Gviz, R, y, dispositivo)
        for m in "ABC":
            P2[m].update(P[m])
    c2 = avaliar(tr, y, P2)
    resumo = {"pontos_por_biopsia_media": round(float(np.mean(n_pontos)), 2), "pontos_min": int(min(n_pontos)),
              "fracao_patches_nas_janelas": round(float(np.mean(n_nos)), 2),
              "cenario1_radboud_para_karolinska": c1, "cenario2_dentro_do_radboud": c2,
              "criterio_H1": c1["criterio"], "criterio_H2": c2["criterio"]}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))
    print(f"H1 (entre centros, rede de grafos > ABMIL): {'SIM' if c1['criterio'] else 'NÃO'} | "
          f"H2 (dentro do Radboud): {'SIM' if c2['criterio'] else 'NÃO'}")


if __name__ == "__main__":
    main()
