"""
Glioma (TCGA-LGG e TCGA-GBM), grau 2 × 3 × 4: MIL × GAT-MIL × rede de grafos sobre o tecido inteiro. Segunda tarefa
de graduação, depois da próstata (PANDA), onde a vizinhança ajudou.

Fixado ANTES de baixar as lâminas (commit anterior aos resultados):
  Lâminas: dados/tcga/lista_tcga_glioma.tsv (60 pacientes por grau, uma lâmina cada, semente 0).
  Patches: TODOS os patches de tecido de 128 µm de cada lâmina (sem amostra), embeddings do UNI2-h
     (tcga_baixar_e_embutir.py --todos), pra que o grafo cubra o tecido contínuo, como no PANDA.
  Avaliação: validação cruzada em 5 partes por paciente, estratificada por grau (coluna parte da lista).
  Modelos (mesma receita de treino, k = 3, 5 sementes, média das probabilidades, nenhum ajuste):
     A = MIL com atenção (mil_atencao.treinar), todos os patches;
     B = GAT-MIL (gat_mil.treinar), cada patch ligado aos 8 vizinhos encostados da grade;
     C = rede de grafos (rede_grafos.py, como no PANDA: até 16 pontos a >= 1 mm, janela de 7 x 7 patches). Pontos de
         cada lâmina pela atenção fora da parte de um MIL A treinado nas outras 4 partes (média das 5 sementes).
         Ressalva (a mesma do PANDA): o MIL que escolhe os pontos de uma lâmina de treino da parte k viu as lâminas de
         teste dessa parte; efeito indireto, só no modelo C.
  Métrica principal: kappa quadrático do grau; IC 95% por bootstrap pareado por lâmina (2.000, semente 0).
  Critério G1 (modelo A): AUC grau 4 × graus 2-3 >= 0,90.
  Critério G2: kappa(B) - kappa(A) > 0 com limite inferior do IC > 0.
  Critério G3: kappa(C) - kappa(A) > 0 com limite inferior do IC > 0.
  Também reportado (sem critério): C - B; AUC grau 3 × grau 2 (só LGG) de cada modelo; acurácia exata; matrizes de
     confusão; patches por lâmina; pontos por lâmina. Ressalva: grau 4 × graus 2-3 se confunde com o hospital no TCGA
     (LGG e GBM vêm de hospitais diferentes); grau 2 × 3 vem dos mesmos hospitais.

Uso (venv do projeto; GPU; depois de tcga_baixar_e_embutir.py lista_tcga_glioma.tsv --saida <HD>/Dados Gerais/TCGA_embeddings/glioma --todos):
    .venv/bin/python mil/tcga/glioma_grafos.py
Saída: resultados/glioma_grafos/{resumo.json, atencao_fora_da_parte/<file_id>.npy}
"""

import csv
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
from comum.lamina import RESULTADOS_DIR, raiz_hd  # noqa: E402
from panda_mil import kappa_quadratico  # noqa: E402

LISTA = comum.caminhos.RAIZ / "dados/tcga" / "lista_tcga_glioma.tsv"
PASTA = Path(raiz_hd()) / "Dados Gerais" / "TCGA_embeddings" / "glioma"
K, PARTES, N_BOOTSTRAP, AUC_MIN = 3, 5, 2000, 0.90
SEMS = mil_atencao.SEMENTES
SAIDA = RESULTADOS_DIR / "glioma_grafos"


class Bolsa:
    """Embeddings em float16 na memória; vira float32 só na GPU (economiza metade da RAM)."""

    def __init__(self, arr):
        self.x = torch.from_numpy(arr)

    def to(self, dispositivo):
        return self.x.to(dispositivo).float()

    def __len__(self):
        return len(self.x)


def atencao_fora_da_parte(ids, X, y, parte, dispositivo):
    pasta = SAIDA / "atencao_fora_da_parte"
    pasta.mkdir(parents=True, exist_ok=True)
    if all((pasta / f"{i}.npy").exists() for i in ids):
        return {i: np.load(pasta / f"{i}.npy") for i in ids}
    att = {i: np.zeros(len(X[i])) for i in ids}
    for p in range(PARTES):
        dentro = [i for i in ids if parte[i] != p]
        for s in SEMS:
            m = mil_atencao.treinar([X[i] for i in dentro], np.array([y[i] for i in dentro]), s, dispositivo, k=K).eval()
            with torch.no_grad():
                for i in (i for i in ids if parte[i] == p):
                    att[i] += m(X[i].to(dispositivo))[1].cpu().numpy() / len(SEMS)
        print(f"  atenção fora da parte: parte {p + 1}/{PARTES}", flush=True)
    for i in ids:
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
        return {**k, "B-A": k["B"] - k["A"], "C-A": k["C"] - k["A"], "C-B": k["C"] - k["B"]}

    k0 = ks(np.arange(len(ids)))
    rng, boot = random.Random(0), {}
    for _ in range(N_BOOTSTRAP):
        idx = np.array([rng.randrange(len(ids)) for _ in ids])
        for c, v in ks(idx).items():
            boot.setdefault(c, []).append(v)
    ic = {c: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for c, v in boot.items()}
    out = {"n": len(ids)}
    for m, nome in (("A", "mil"), ("B", "gat_mil"), ("C", "rede_grafos")):
        p4 = np.array([P[m][i][2] for i in ids])
        lgg = real <= 1
        p3 = np.array([P[m][i][1] / max(P[m][i][0] + P[m][i][1], 1e-9) for i in ids])
        out[nome] = {"kappa": round(k0[m], 3), "ic95": ic[m],
                     "auc_grau4_x_2e3": round(mil_atencao.auc(p4[real == 2], p4[real <= 1]), 3),
                     "auc_grau3_x_grau2": round(mil_atencao.auc(p3[lgg & (real == 1)], p3[lgg & (real == 0)]), 3),
                     "acuracia_exata": round(float(np.mean(real == pred[m])), 3),
                     "matriz_confusao_real_x_previsto": [[int(np.sum((real == r) & (pred[m] == c))) for c in range(K)]
                                                         for r in range(K)]}
    for d in ("B-A", "C-A", "C-B"):
        out[d.replace("-", "_menos_")] = {"diferenca": round(k0[d], 3), "ic95": ic[d]}
    return out


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    prontas = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    faltam = [l["file_name"] for l in linhas if l not in prontas]
    ids = [l["file_id"] for l in prontas]
    y = {l["file_id"]: int(l["grau"]) - 2 for l in prontas}
    parte = {l["file_id"]: int(l["parte"]) for l in prontas}
    X, Gviz, xy, lado = {}, {}, {}, {}
    for i in ids:
        pasta = PASTA / i
        X[i] = Bolsa(np.load(pasta / "todos.npy"))
        xy[i] = np.loadtxt(pasta / "todos_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        lado[i] = json.loads((pasta / "meta.json").read_text())["lado_px"]
        Gviz[i] = gat_mil.arestas_vizinhos(xy[i], lado[i])
    n_patches = [len(X[i]) for i in ids]
    print(f"{len(ids)} lâminas; patches por lâmina: mediana {np.median(n_patches):.0f}, máx {max(n_patches)}", flush=True)
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    att = atencao_fora_da_parte(ids, X, y, parte, dispositivo)
    R = {i: rede_grafos.montar(xy[i], lado[i], att[i]) for i in ids}
    n_pontos = [len(R[i]["pontos"]) for i in ids]
    print(f"pontos por lâmina: média {np.mean(n_pontos):.1f} (mín {min(n_pontos)})", flush=True)
    P = {m: {} for m in "ABC"}
    for p in range(PARTES):
        print(f"  parte {p + 1}/{PARTES}", flush=True)
        Pp = prever([i for i in ids if parte[i] != p], [i for i in ids if parte[i] == p], X, Gviz, R, y, dispositivo)
        for m in "ABC":
            P[m].update(Pp[m])
    r = avaliar(ids, y, P)
    resumo = {"prontas": len(ids), "faltam": faltam, "patches_por_lamina_mediana": float(np.median(n_patches)),
              "pontos_por_lamina_media": round(float(np.mean(n_pontos)), 2), **r,
              "criterio_G1": r["mil"]["auc_grau4_x_2e3"] >= AUC_MIN,
              "criterio_G2": r["B_menos_A"]["diferenca"] > 0 and r["B_menos_A"]["ic95"][0] > 0,
              "criterio_G3": r["C_menos_A"]["diferenca"] > 0 and r["C_menos_A"]["ic95"][0] > 0}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))
    print(f"G1: {'SIM' if resumo['criterio_G1'] else 'NÃO'} | G2 (GAT-MIL > MIL): {'SIM' if resumo['criterio_G2'] else 'NÃO'}"
          f" | G3 (rede > MIL): {'SIM' if resumo['criterio_G3'] else 'NÃO'}")


if __name__ == "__main__":
    main()
