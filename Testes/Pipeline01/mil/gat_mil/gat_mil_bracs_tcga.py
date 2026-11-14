"""
GAT-MIL × ABMIL no BRACS (mama, 4 classes) e no TCGA (pulmão, LUAD × LUSC): a mesma comparação pareada feita no
PANDA (gat_mil_panda.py, onde o GAT-MIL ganhou nos dois cenários), pra ver se a vizinhança ajuda nos outros datasets.

Fixado ANTES de rodar (commit anterior aos resultados):
  Grafo: no BRACS e no TCGA a amostra de 2.000 patches cobre em geral uma parte pequena do tecido (só 23 de 136
     lâminas do BRACS e 19 de 197 do TCGA cabem inteiras), e com os 8 vizinhos encostados quase todo patch ficaria
     sozinho. Regra geral (gat_mil.arestas_proximos): cada patch ligado aos até 8 patches da amostra mais próximos com
     centro a no máximo 3 lados (384 µm), mais o próprio. Medido antes de fixar: em média ~9 vizinhos nesse raio no
     BRACS e no TCGA. Na grade completa do PANDA a regra dá os mesmos 8 vizinhos encostados (exceto na borda).
  Modelos: A = ABMIL (mil_atencao.treinar), B = GAT-MIL (gat_mil.treinar), mesma receita, 5 sementes, probabilidade =
     média das 5, nenhum ajuste.
  BRACS (rótulo oficial, 4 classes: benigno, atípico, DCIS, IC; dados de mil_atencao.py):
     Cenário B1: treino nas 79 lâminas (61 validação + 18 desenvolvimento), teste nas 57 do teste externo.
     Cenário B2: validação cruzada nas 79, as mesmas 5 partes por paciente de mil_validacao_cruzada.py.
     Métrica: acurácia balanceada nas 4 classes. Diferença B - A com IC 95% por bootstrap agrupado por paciente
     (2.000, semente 0). Critério (cada cenário): diferença > 0 e limite inferior do IC > 0.
  TCGA (LUAD × LUSC; dados de tcga_mil.py):
     Cenário T1: treino nas 119, teste nas 78. O ABMIL já está perto do teto (AUC 0,981), então o critério é de não
     piorar: limite inferior do IC 95% da diferença de AUC (B - A; bootstrap por lâmina, 2.000, semente 0) > -0,02.
  Também reportado (sem critério): BRACS, AUC benigno × atípico e maligno × resto, acerto por classe; TCGA, acurácia
     balanceada; vizinhos por patch.
  Ressalva: as 57 lâminas do teste externo do BRACS já foram usadas em vários testes.

Uso (venv do projeto; GPU):
    .venv/bin/python mil/gat_mil/gat_mil_bracs_tcga.py
Saída: resultados/gat_mil_bracs_tcga/resumo.json
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
from comum.lamina import RESULTADOS_DIR, dir_resultados  # noqa: E402

SAIDA = RESULTADOS_DIR / "gat_mil_bracs_tcga"
N_PARTES = 5
LADO_BRACS = 512
NAO_PIORA_TCGA = -0.02


def prever(tr, te, X, G, y, k, dispositivo):
    P = {m: {i: np.zeros(k) for i in te} for m in "AB"}
    ytr = np.array([y[i] for i in tr])
    for semente in mil_atencao.SEMENTES:
        a = mil_atencao.treinar([X[i] for i in tr], ytr, semente, dispositivo, k=k).eval()
        b = gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], ytr, semente, dispositivo, k=k).eval()
        with torch.no_grad():
            for i in te:
                x = X[i].to(dispositivo)
                P["A"][i] += torch.softmax(a(x)[0], 0).cpu().numpy() / len(mil_atencao.SEMENTES)
                P["B"][i] += torch.softmax(b(x, G[i].to(dispositivo))[0], 0).cpu().numpy() / len(mil_atencao.SEMENTES)
        print(f"    semente {semente} pronta", flush=True)
    return P


def grau_medio(G, ids):
    return round(float(np.mean([G[i].shape[1] / max(int(G[i][1].max()) + 1, 1) for i in ids])) - 1, 2)


# ---------- BRACS ----------
def bracs(dispositivo):
    from comum.rois import info_lamina
    from lamina_inteira import FINAIS, acuracia_balanceada, amostra, classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    treino, teste = laminas_val() + laminas_dev(), laminas_teste()
    y = {s: FINAIS.index(classe_final(info_lamina(s)["rotulo"])) for s in treino + teste}
    pac = pacientes()
    X, G = {}, {}
    for s in treino + teste:
        X[s] = torch.from_numpy(amostra(s))
        xy = np.loadtxt(dir_resultados(s, "uni2h") / "amostra2000_xy.csv", delimiter=",", skiprows=1).reshape(-1, 2)
        G[s] = gat_mil.arestas_proximos(xy, LADO_BRACS)
    print(f"BRACS: {len(treino)} treino, {len(teste)} teste; vizinhos por patch {grau_medio(G, treino + teste)}", flush=True)

    def avaliar(ids, P):
        real = [FINAIS[y[s]] for s in ids]
        pred = {m: [FINAIS[int(P[m][s].argmax())] for s in ids] for m in "AB"}

        def ba(idx):
            r = [real[i] for i in idx]
            a = acuracia_balanceada(r, [pred["A"][i] for i in idx])
            b = acuracia_balanceada(r, [pred["B"][i] for i in idx])
            return {"A": a, "B": b, "dif": b - a}

        v = ba(list(range(len(ids))))
        ic = gat_mil.bootstrap_pareado(ba, [pac[s] for s in ids])
        out = {"n": len(ids), "ba_A_abmil": round(v["A"], 3), "ic95_A": ic["A"], "ba_B_gat": round(v["B"], 3),
               "ic95_B": ic["B"], "diferenca_B_menos_A": round(v["dif"], 3), "ic95_diferenca": ic["dif"]}
        for m, nome in (("A", "abmil"), ("B", "gat")):
            ba_ = [s for s in ids if FINAIS[y[s]] in ("benigno", "atipico")]
            razao = {s: P[m][s][1] / (P[m][s][0] + P[m][s][1]) for s in ba_}
            mal = {s: P[m][s][2] + P[m][s][3] for s in ids}
            out[nome] = {
                "por_classe": {c: f"{sum(r == p == c for r, p in zip(real, pred[m]))}/{real.count(c)}" for c in FINAIS},
                "auc_benigno_x_atipico": round(mil_atencao.auc([razao[s] for s in ba_ if FINAIS[y[s]] == "atipico"],
                                                               [razao[s] for s in ba_ if FINAIS[y[s]] == "benigno"]), 3),
                "auc_maligno_x_resto": round(mil_atencao.auc([mal[s] for s in ids if y[s] >= 2],
                                                             [mal[s] for s in ids if y[s] < 2]), 3)}
        out["criterio"] = v["dif"] > 0 and ic["dif"][0] > 0
        return out

    print("  B1: 79 -> 57", flush=True)
    b1 = avaliar(teste, prever(treino, teste, X, G, y, 4, dispositivo))
    print("  B2: validação cruzada nas 79", flush=True)
    lista = sorted({pac[s] for s in treino})
    random.Random(0).shuffle(lista)
    parte = {p: i % N_PARTES for i, p in enumerate(lista)}
    P2 = {"A": {}, "B": {}}
    for k in range(N_PARTES):
        fora = [s for s in treino if parte[pac[s]] == k]
        P = prever([s for s in treino if parte[pac[s]] != k], fora, X, G, y, 4, dispositivo)
        for m in "AB":
            P2[m].update(P[m])
    b2 = avaliar(treino, P2)
    return {"vizinhos_por_patch": grau_medio(G, treino + teste), "B1_79_para_57": b1, "B2_validacao_cruzada_79": b2}


# ---------- TCGA ----------
def tcga(dispositivo):
    from tcga_mil import CLASSES, LISTA
    pasta = RESULTADOS_DIR / "tcga_pulmao"
    linhas = [l for l in csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t")
              if (pasta / l["file_id"] / "meta.json").exists()]
    tr = [l["file_id"] for l in linhas if l["conjunto"] == "treino"]
    te = [l["file_id"] for l in linhas if l["conjunto"] == "teste"]
    y = {l["file_id"]: CLASSES.index(l["projeto"]) for l in linhas}
    X, G = {}, {}
    for i in tr + te:
        X[i] = torch.from_numpy(np.load(pasta / i / "amostra2000.npy"))
        xy = np.loadtxt(pasta / i / "amostra2000_xy.csv", delimiter=",", skiprows=1).reshape(-1, 2)
        G[i] = gat_mil.arestas_proximos(xy, json.loads((pasta / i / "meta.json").read_text())["lado_px"])
    print(f"TCGA: {len(tr)} treino, {len(te)} teste; vizinhos por patch {grau_medio(G, tr + te)}", flush=True)
    P = prever(tr, te, X, G, y, 2, dispositivo)
    real = np.array([y[i] for i in te])
    p = {m: np.array([P[m][i][1] for i in te]) for m in "AB"}

    def aucs(idx):
        idx = np.asarray(idx)
        r = real[idx]
        if r.min() == r.max():
            return {}
        a = mil_atencao.auc(p["A"][idx][r == 1], p["A"][idx][r == 0])
        b = mil_atencao.auc(p["B"][idx][r == 1], p["B"][idx][r == 0])
        return {"A": a, "B": b, "dif": b - a}

    v = aucs(range(len(te)))
    ic = gat_mil.bootstrap_pareado(aucs, list(range(len(te))))
    bal = {m: float(np.mean([np.mean((p[m][real == c] >= 0.5) == c) for c in (0, 1)])) for m in "AB"}
    return {"vizinhos_por_patch": grau_medio(G, tr + te),
            "T1_119_para_78": {"n": len(te), "auc_A_abmil": round(v["A"], 3), "ic95_A": ic["A"],
                               "auc_B_gat": round(v["B"], 3), "ic95_B": ic["B"],
                               "diferenca_B_menos_A": round(v["dif"], 3), "ic95_diferenca": ic["dif"],
                               "acuracia_balanceada_A": round(bal["A"], 3), "acuracia_balanceada_B": round(bal["B"], 3),
                               "criterio_nao_piora": ic["dif"][0] > NAO_PIORA_TCGA}}


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    resumo = {"bracs": bracs(dispositivo), "tcga": tcga(dispositivo)}
    resumo["criterio_B1"] = resumo["bracs"]["B1_79_para_57"]["criterio"]
    resumo["criterio_B2"] = resumo["bracs"]["B2_validacao_cruzada_79"]["criterio"]
    resumo["criterio_T1"] = resumo["tcga"]["T1_119_para_78"]["criterio_nao_piora"]
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))
    print(f"B1 (BRACS 79 -> 57): {'SIM' if resumo['criterio_B1'] else 'NÃO'} | B2 (BRACS validação cruzada): "
          f"{'SIM' if resumo['criterio_B2'] else 'NÃO'} | T1 (TCGA, não piora): {'SIM' if resumo['criterio_T1'] else 'NÃO'}")


if __name__ == "__main__":
    main()
