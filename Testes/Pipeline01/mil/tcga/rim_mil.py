"""
Rim (TCGA-RCC): carcinoma de células claras (KIRC) × papilífero (KIRP) × cromófobo (KICH), com treino e teste em
hospitais diferentes. Mesma receita do pulmão (UNI2-h congelado, amostra de 2.000 patches de 128 µm, MIL com atenção).

Fixado ANTES de baixar as lâminas (commit anterior aos resultados):
  Lâminas: dados/tcga/lista_tcga_rim.tsv (100 pacientes por subtipo, uma lâmina cada, semente 0).
  Cenário 1 (o do critério), por hospital: coluna conjunto. Nenhum hospital do teste está no treino. No TCGA de rim
     cada hospital mandou um subtipo só, então um modelo pode acertar no sorteio aleatório aprendendo o "jeito" do
     hospital (coloração, escâner, preparo) em vez da morfologia; com hospitais novos no teste, isso não ajuda.
  Cenário 2 (comparação, sem critério): coluna conjunto_aleatorio (60/40 por subtipo, sem olhar o hospital).
  Modelos: A = MIL com atenção (mil_atencao.treinar), B = GAT-MIL (gat_mil.treinar; cada patch ligado aos até 8
     patches da amostra mais próximos a até 3 lados, como no BRACS e no pulmão). k = 3, 5 sementes, média das
     probabilidades, nenhum ajuste.
  Padronização por hospital: não testada. Como cada hospital tem um subtipo só, subtrair a média do hospital é
     subtrair a média do próprio subtipo.
  Métricas: acurácia balanceada (3 classes); AUC macro (média das três AUCs um contra os outros); IC 95% por
     bootstrap pareado por lâmina (2.000, semente 0).
  Critério R1 (cenário 1, modelo A): acurácia balanceada >= 0,80 E AUC macro >= 0,90.
  Critério R2 (cenário 1): GAT-MIL não pior que o MIL: limite inferior do IC da diferença de acurácia balanceada
     (B - A) > -0,05.
  Também reportado (sem critério): acerto por subtipo e matriz de confusão; os dois modelos no cenário 2; a queda do
     cenário 2 pro cenário 1 (efeito do hospital); lâminas que falharem no download ficam de fora e são listadas.

Uso (venv do projeto; GPU; depois de tcga_baixar_e_embutir.py lista_tcga_rim.tsv --saida <HD>/Dados Gerais/TCGA_embeddings/rim):
    .venv/bin/python mil/tcga/rim_mil.py
Saída: resultados/rim_mil/resumo.json
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402

import gat_mil  # noqa: E402
import mil_atencao  # noqa: E402
from comum.lamina import RESULTADOS_DIR, raiz_hd  # noqa: E402

LISTA = comum.caminhos.RAIZ / "dados/tcga" / "lista_tcga_rim.tsv"
PASTA = Path(raiz_hd()) / "Dados Gerais" / "TCGA_embeddings" / "rim"
CLASSES = ["TCGA-KIRC", "TCGA-KIRP", "TCGA-KICH"]
K = 3
BA_MIN, AUC_MIN, MARGEM = 0.80, 0.90, -0.05
SAIDA = RESULTADOS_DIR / "rim_mil"


def acuracia_balanceada(real, pred):
    return float(np.mean([np.mean(pred[real == c] == c) for c in range(K) if np.any(real == c)]))


def auc_macro(real, P):
    return float(np.mean([mil_atencao.auc(P[real == c, c], P[real != c, c]) for c in range(K)]))


def prever(tr, te, X, G, y, dispositivo):
    P = {m: np.zeros((len(te), K)) for m in "AB"}
    ytr = np.array([y[i] for i in tr])
    for s in mil_atencao.SEMENTES:
        a = mil_atencao.treinar([X[i] for i in tr], ytr, s, dispositivo, k=K).eval()
        b = gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], ytr, s, dispositivo, k=K).eval()
        with torch.no_grad():
            for j, i in enumerate(te):
                x = X[i].to(dispositivo)
                P["A"][j] += torch.softmax(a(x)[0], 0).cpu().numpy() / len(mil_atencao.SEMENTES)
                P["B"][j] += torch.softmax(b(x, G[i].to(dispositivo))[0], 0).cpu().numpy() / len(mil_atencao.SEMENTES)
        print(f"    semente {s} pronta", flush=True)
    return P


def avaliar(te, y, P):
    real = np.array([y[i] for i in te])
    pred = {m: P[m].argmax(1) for m in "AB"}

    def v(idx):
        idx = np.array(idx)
        a = acuracia_balanceada(real[idx], pred["A"][idx])
        b = acuracia_balanceada(real[idx], pred["B"][idx])
        return {"A": a, "B": b, "dif": b - a, "aucA": auc_macro(real[idx], P["A"][idx]),
                "aucB": auc_macro(real[idx], P["B"][idx])}

    v0 = v(list(range(len(te))))
    ic = gat_mil.bootstrap_pareado(v, list(range(len(te))))
    out = {"n": len(te)}
    for m, nome in (("A", "mil"), ("B", "gat_mil")):
        conf = [[int(np.sum((real == r) & (pred[m] == c))) for c in range(K)] for r in range(K)]
        out[nome] = {"acuracia_balanceada": round(v0[m], 3), "ic95": ic[m],
                     "auc_macro": round(v0["auc" + m], 3), "ic95_auc": ic["auc" + m],
                     "acerto_por_subtipo": {CLASSES[c]: f"{conf[c][c]}/{sum(conf[c])}" for c in range(K)},
                     "matriz_confusao_real_x_previsto": conf}
    out["B_menos_A"] = {"diferenca": round(v0["dif"], 3), "ic95": ic["dif"]}
    return out


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    prontas = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    faltam = [l["file_name"] for l in linhas if l not in prontas]
    X, G, y = {}, {}, {}
    for l in prontas:
        i, pasta = l["file_id"], PASTA / l["file_id"]
        X[i] = torch.from_numpy(np.load(pasta / "amostra2000.npy"))
        xy = np.loadtxt(pasta / "amostra2000_xy.csv", delimiter=",", skiprows=1).reshape(-1, 2)
        G[i] = gat_mil.arestas_proximos(xy, json.loads((pasta / "meta.json").read_text())["lado_px"])
        y[i] = CLASSES.index(l["projeto"])
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    resumo = {"prontas": len(prontas), "faltam": faltam}
    for chave, coluna in (("cenario1_por_hospital", "conjunto"), ("cenario2_aleatorio", "conjunto_aleatorio")):
        tr = [l["file_id"] for l in prontas if l[coluna] == "treino"]
        te = [l["file_id"] for l in prontas if l[coluna] == "teste"]
        print(f"{chave}: {len(tr)} treino, {len(te)} teste", flush=True)
        resumo[chave] = avaliar(te, y, prever(tr, te, X, G, y, dispositivo))
        print(json.dumps(resumo[chave], ensure_ascii=False), flush=True)
    c1, c2 = resumo["cenario1_por_hospital"], resumo["cenario2_aleatorio"]
    resumo["criterio_R1"] = c1["mil"]["acuracia_balanceada"] >= BA_MIN and c1["mil"]["auc_macro"] >= AUC_MIN
    resumo["criterio_R2"] = c1["B_menos_A"]["ic95"][0] > MARGEM
    resumo["queda_aleatorio_para_hospital_mil"] = round(c2["mil"]["acuracia_balanceada"] - c1["mil"]["acuracia_balanceada"], 3)
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"R1 (MIL em hospitais novos): {'SIM' if resumo['criterio_R1'] else 'NÃO'} | "
          f"R2 (GAT-MIL não pior): {'SIM' if resumo['criterio_R2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
