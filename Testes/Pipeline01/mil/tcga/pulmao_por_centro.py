"""
Pulmão (TCGA, adenocarcinoma × carcinoma escamoso) com divisão por centro de origem.

Motivo: na amostra de tcga_mil.py nenhum dos 54 centros de origem (o código TSS no código do paciente, TCGA-XX-...)
mandou as duas classes, e 65 das 80 lâminas de teste vêm de centros que também estão no treino. O classificador pode
estar reconhecendo o centro (coloração, escâner) em vez do subtipo, e a AUC de 0,981 (divisão aleatória por paciente)
pode estar inflada. Aqui cada lâmina é prevista por um modelo que não viu nenhuma lâmina do seu centro.

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas: todas as de dados/tcga/lista_tcga_pulmao.tsv com embeddings prontos (treino + teste de tcga_mil.py).
  Partes: validação cruzada em 5 partes agrupada por centro. Os centros de cada classe são ordenados por número de
     lâminas (decrescente; empate pelo código) e distribuídos um a um para a parte com menos lâminas daquela classe,
     então cada parte tem as duas classes e nenhum centro aparece em duas partes.
  Modelo: mil_atencao.treinar (ABMIL, k = 2, 40 épocas, sem ajuste), 5 sementes por parte; probabilidade e atenção =
     média das 5 sementes; guarda também P(LUSC) de cada semente.
  Descritor: pulmao_descritor.aplicar_todos (LungHist700) em todas as lâminas; regiões = 3 de maior atenção com
     centros a >= 192 µm (tcga_descritor_prelaudo.gate_um); aviso = alguma região com classe do descritor diferente do
     tipo previsto (inclui pulmão normal), a mesma regra dos pré-laudos.
  Critérios:
     Z1 (decisão com centros novos): AUC >= 0,85 e acurácia balanceada >= 0,75 (os mesmos de tcga_mil.py).
     Z2 (aviso × erro com centros novos): taxa de erro maior nas lâminas com aviso, Fisher unilateral p < 0,05.
  Também reportado (sem critério): IC 95% por bootstrap das lâminas (2.000, semente 0); acerto por classe; a AUC da
     divisão aleatória (tcga_mil.py) ao lado; erros por classe prevista; avisos por classe prevista.
  Limite conhecido: como cada centro manda uma classe só, o centro continua ligado à classe; a divisão por centro mede
     se o modelo acerta em centros que nunca viu, não separa por completo subtipo de centro.

Uso (venv do projeto; GPU): .venv/bin/python mil/tcga/pulmao_por_centro.py
Saída: resultados/pulmao_centro/{resumo.json, por_lamina.json, <file_id>_atencao.npy, <file_id>_descritor.npy}
"""

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "pulmao_centro"
PARTES = 5
AUC_MIN, BA_MIN, P_MAX = 0.85, 0.75, 0.05
N_BOOT = 2000


def centro(l):
    return l["paciente"].split("-")[1]


def partes_por_centro(laminas):
    parte = {}
    for proj in sorted({l["projeto"] for l in laminas}):
        cont = Counter(centro(l) for l in laminas if l["projeto"] == proj)
        carga = [0] * PARTES
        for c, n in sorted(cont.items(), key=lambda t: (-t[1], t[0])):
            k = int(np.argmin(carga))
            parte[c] = k
            carga[k] += n
    return parte


def main():
    import torch
    from scipy.stats import fisher_exact
    from mil_atencao import SEMENTES, auc, treinar
    from pulmao_descritor import CLASSES as CLS_D, aplicar_todos
    from tcga_descritor_prelaudo import N_REGIOES, PASTA, gate_um
    from tcga_mil import CLASSES, LISTA
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    lam = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    parte_c = partes_por_centro(lam)
    ids = [l["file_id"] for l in lam]
    y = np.array([CLASSES.index(l["projeto"]) for l in lam])
    parte = np.array([parte_c[centro(l)] for l in lam])
    X = [torch.from_numpy(np.load(PASTA / i / "amostra2000.npy")) for i in ids]
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    p_sem = np.zeros((len(lam), len(SEMENTES)))
    att = [np.zeros(len(x)) for x in X]
    for k in range(PARTES):
        tr, te = np.where(parte != k)[0], np.where(parte == k)[0]
        for s_i, s in enumerate(SEMENTES):
            m = treinar([X[i] for i in tr], y[tr], s, dev, k=2).eval()
            with torch.no_grad():
                for i in te:
                    logit, a = m(X[i].to(dev))
                    p_sem[i, s_i] = float(torch.softmax(logit, 0)[1])
                    att[i] += a.cpu().numpy() / len(SEMENTES)
        print(f"  parte {k}: {len(te)} lâminas ({sum(y[te])} LUSC), centros {sorted({centro(lam[i]) for i in te})}", flush=True)
    p = p_sem.mean(1)
    pred = (p >= 0.5).astype(int)

    # descritor e avisos
    Pd = aplicar_todos([X[i].numpy() for i in range(len(lam))])
    aviso, n_disc = np.zeros(len(lam), bool), np.zeros(len(lam), int)
    por = {}
    for i, l in enumerate(lam):
        np.save(SAIDA / f"{ids[i]}_atencao.npy", att[i].astype(np.float32))
        np.save(SAIDA / f"{ids[i]}_descritor.npy", Pd[i].astype(np.float32))
        meta = json.loads((PASTA / ids[i] / "meta.json").read_text(encoding="utf-8"))
        xy = np.loadtxt(PASTA / ids[i] / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=int).reshape(-1, 2)
        lado = meta["lado_px"]
        ps = [{"cx": x + lado / 2, "cy": yy + lado / 2, "atencao": float(a), "classe": CLS_D[int(q.argmax())]}
              for (x, yy), q, a in zip(xy, Pd[i], att[i])]
        reg = gate_um(sorted(ps, key=lambda d: -d["atencao"]), meta["mpp"], N_REGIOES)
        tipo = "scc" if pred[i] == 1 else "aca"
        n_disc[i] = sum(d["classe"] != tipo for d in reg)
        aviso[i] = n_disc[i] > 0
        por[ids[i]] = {"paciente": l["paciente"], "centro": centro(l), "parte": int(parte[i]), "real": int(y[i]),
                       "p_lusc": round(float(p[i]), 5), "p_lusc_sementes": [round(float(v), 5) for v in p_sem[i]],
                       "previsto": int(pred[i]), "regioes": [d["classe"] for d in reg], "n_discordantes": int(n_disc[i])}

    erro = pred != y
    rng = random.Random(0)
    boot = [np.array([rng.randrange(len(y)) for _ in y]) for _ in range(N_BOOT)]
    boot = [b for b in boot if 0 < y[b].sum() < len(b)]

    def ba(idx):
        return float(np.mean([np.mean(pred[idx][y[idx] == c] == c) for c in (0, 1)]))

    def ic(f):
        v = [f(b) for b in boot]
        return [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]

    todos = np.arange(len(y))
    a0 = auc(p[y == 1], p[y == 0])
    tab = [[int((aviso & erro).sum()), int((aviso & ~erro).sum())], [int((~aviso & erro).sum()), int((~aviso & ~erro).sum())]]
    pf = float(fisher_exact(tab, alternative="greater")[1])
    tx_a, tx_s = tab[0][0] / max(sum(tab[0]), 1), tab[1][0] / max(sum(tab[1]), 1)
    aleat = json.loads((RESULTADOS_DIR / "tcga_mil" / "resumo.json").read_text(encoding="utf-8"))
    resumo = {
        "n": len(y), "luad": int((y == 0).sum()), "lusc": int((y == 1).sum()), "centros": len(parte_c),
        "laminas_por_parte": [int((parte == k).sum()) for k in range(PARTES)],
        "auc": round(a0, 3), "auc_ic95": ic(lambda b: auc(p[b][y[b] == 1], p[b][y[b] == 0])),
        "acuracia_balanceada": round(ba(todos), 3), "ba_ic95": ic(ba),
        "acerto_luad": f"{int(((pred == 0) & (y == 0)).sum())}/{int((y == 0).sum())}",
        "acerto_lusc": f"{int(((pred == 1) & (y == 1)).sum())}/{int((y == 1).sum())}",
        "divisao_aleatoria_tcga_mil": {"auc": aleat.get("auc"), "acuracia_balanceada": aleat.get("acuracia_balanceada"),
                                       "n_teste": aleat.get("n_teste")},
        "erros": int(erro.sum()), "erros_por_classe_prevista": {"luad": int((erro & (pred == 0)).sum()),
                                                                 "lusc": int((erro & (pred == 1)).sum())},
        "avisos": int(aviso.sum()), "avisos_por_classe_prevista": {"luad": int((aviso & (pred == 0)).sum()),
                                                                    "lusc": int((aviso & (pred == 1)).sum())},
        "aviso_x_erro": {"tabela_[com,sem]x[erro,acerto]": tab, "taxa_erro_com_aviso": round(tx_a, 3),
                         "taxa_erro_sem_aviso": round(tx_s, 3), "fisher_p_unilateral": round(pf, 4),
                         "erros_com_aviso": f"{tab[0][0]}/{int(erro.sum())}"}}
    resumo["criterio_Z1"] = resumo["auc"] >= AUC_MIN and resumo["acuracia_balanceada"] >= BA_MIN
    resumo["criterio_Z2"] = tx_a > tx_s and pf < P_MAX
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "por_lamina.json").write_text(json.dumps(por, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))
    print(f"Z1 {'SIM' if resumo['criterio_Z1'] else 'NÃO'} | Z2 {'SIM' if resumo['criterio_Z2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
