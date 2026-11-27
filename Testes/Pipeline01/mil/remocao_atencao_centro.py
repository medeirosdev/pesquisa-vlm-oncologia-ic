"""
Remoção e suficiência da atenção do ABMIL no pulmão (TCGA LUAD × LUSC) na validação cruzada por centro de origem.

Antes (remocao_atencao.py): as curvas na probabilidade do pulmão (Fig. 3 do paper) foram medidas nas 78 lâminas de teste
da divisão aleatória por paciente, onde 64/78 vêm de centros presentes no treino. Aqui repetimos exatamente o mesmo teste
na validação cruzada em 5 partes agrupadas por centro de origem (197 lâminas, pulmao_por_centro.py), para que a figura
não misture a divisão aleatória com a avaliação principal por centro.

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas e partes: todas as 197 lâminas de dados/tcga/lista_tcga_pulmao.tsv com embeddings prontos, nas mesmas 5 partes
     agrupadas por centro de origem (pulmao_por_centro.partes_por_centro).
  Modelo: mil_atencao.treinar (ABMIL, k = 2, 40 épocas, sem ajuste), 5 sementes (mil_atencao.SEMENTES) por parte; a
     probabilidade em cada cenário é a média das 5 sementes treinadas nas outras 4 partes. Reportada a concordância da
     classe prevista com pulmao_centro/por_lamina.json.
  Ordem dos patches: a atenção média salva fora da amostra em resultados/pulmao_centro/<file_id>_atencao.npy.
  Classe de referência de cada lâmina: a prevista com todos os patches nesta rodada. Medida: probabilidade dessa classe.
  Remoção: tirar os f% de maior atenção × tirar f% sorteados (5 sorteios, semente [0, i]), f = 1, 2, 5, 10, 20 e 50%
     dos patches (pelo menos 1). Queda = probabilidade com todos − probabilidade sem eles.
  Suficiência: ficar só com os n patches de maior atenção × n sorteados (5 sorteios), n = 5, 10, 20, 50, 100 e 200 (no
     máximo o número de patches da lâmina).
  Critérios (os mesmos X1 e X2 de remocao_atencao.py):
     X1c (remoção): média, por lâmina, de (queda tirando os 10% de maior atenção − queda média tirando 10% sorteados) > 0,
        com limite inferior do IC 95% por bootstrap das lâminas (2.000, semente 0) > 0.
     X2c (suficiência): média, por lâmina, de (probabilidade só com os 20 de maior atenção − média só com 20 sorteados)
        > 0, com limite inferior do IC 95% > 0.
  Também reportado (sem critério): as curvas inteiras; fração de lâminas em que a classe prevista muda em cada cenário;
     X1c e X2c separados pela classe prevista (previsto_adenocarcinoma e previsto_escamoso).
  Limites conhecidos: remover patches muda a distribuição vista no treino (o sorteio serve de controle); como cada centro
     do TCGA contribui uma só classe, a divisão por centro mede generalização para centros novos, mas não separa por
     completo subtipo de centro.

Uso (venv do projeto; GPU): .venv/bin/python mil/remocao_atencao_centro.py
Saída: resultados/remocao_atencao/{pulmao_centro.json, resumo_pulmao_centro.json}
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402
from remocao_atencao import F_X, FRACOES, N_X, NS, SAIDA, boot_ic, cenarios  # noqa: E402


def main():
    from mil_atencao import SEMENTES, treinar
    from pulmao_por_centro import PARTES, SAIDA as SAIDA_CENTRO, centro, partes_por_centro
    from tcga_descritor_prelaudo import PASTA
    from tcga_mil import CLASSES, LISTA

    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    lam = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    parte_c = partes_por_centro(lam)
    ids = [l["file_id"] for l in lam]
    y = np.array([CLASSES.index(l["projeto"]) for l in lam])
    parte = np.array([parte_c[centro(l)] for l in lam])
    X = [torch.from_numpy(np.load(PASTA / i / "amostra2000.npy")) for i in ids]
    att = [np.load(SAIDA_CENTRO / f"{i}_atencao.npy") for i in ids]
    antes = json.loads((SAIDA_CENTRO / "por_lamina.json").read_text(encoding="utf-8"))
    antes_pred = [antes[i]["previsto"] for i in ids]

    conj = [cenarios(len(x), a, np.random.default_rng([0, i])) for i, (x, a) in enumerate(zip(X, att))]
    P = [{c: [np.zeros(2) for _ in v] for c, v in cj.items()} for cj in conj]
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    for k in range(PARTES):
        tr, te = np.where(parte != k)[0], np.where(parte == k)[0]
        Xtr, ytr = [X[i] for i in tr], y[tr]
        for semente in SEMENTES:
            modelo = treinar(Xtr, ytr, semente, dev, k=2).eval()
            with torch.no_grad():
                for i in te:
                    x = X[i].to(dev)
                    for c, v in conj[i].items():
                        for j, idx in enumerate(v):
                            logit, _ = modelo(x[torch.from_numpy(idx).to(dev)])
                            P[i][c][j] += torch.softmax(logit, 0).cpu().numpy() / len(SEMENTES)
        print(f"  parte {k}: {len(te)} lâminas prontas", flush=True)

    pred = [int(p["todos"][0].argmax()) for p in P]
    prob = lambda i, c: [float(v[pred[i]]) for v in P[i][c]]  # noqa: E731
    muda = lambda i, c: float(np.mean([int(v.argmax()) != pred[i] for v in P[i][c]]))  # noqa: E731
    base = [prob(i, "todos")[0] for i in range(len(P))]

    curvas = {"remocao": {}, "suficiencia": {}}
    for f in FRACOES:
        qt = [base[i] - prob(i, f"remove_top_{f}")[0] for i in range(len(P))]
        qs = [base[i] - float(np.mean(prob(i, f"remove_sorteio_{f}"))) for i in range(len(P))]
        curvas["remocao"][str(f)] = {
            "queda_top": round(float(np.mean(qt)), 4),
            "queda_sorteio": round(float(np.mean(qs)), 4),
            "muda_classe_top": round(float(np.mean([muda(i, f"remove_top_{f}") for i in range(len(P))])), 4),
            "muda_classe_sorteio": round(float(np.mean([muda(i, f"remove_sorteio_{f}") for i in range(len(P))])), 4),
            "diferenca_por_lamina": [round(a - b, 5) for a, b in zip(qt, qs)],
        }
    for n_k in NS:
        pt = [prob(i, f"so_top_{n_k}")[0] for i in range(len(P))]
        ps = [float(np.mean(prob(i, f"so_sorteio_{n_k}"))) for i in range(len(P))]
        curvas["suficiencia"][str(n_k)] = {
            "prob_top": round(float(np.mean(pt)), 4),
            "prob_sorteio": round(float(np.mean(ps)), 4),
            "mantem_classe_top": round(1 - float(np.mean([muda(i, f"so_top_{n_k}") for i in range(len(P))])), 4),
            "mantem_classe_sorteio": round(1 - float(np.mean([muda(i, f"so_sorteio_{n_k}") for i in range(len(P))])), 4),
            "diferenca_por_lamina": [round(a - b, 5) for a, b in zip(pt, ps)],
        }

    x1 = curvas["remocao"][str(F_X)]["diferenca_por_lamina"]
    x2 = curvas["suficiencia"][str(N_X)]["diferenca_por_lamina"]
    r = {
        "n": len(P),
        "centros": len(parte_c),
        "classe_igual_a_pulmao_centro": f"{sum(a == b for a, b in zip(pred, antes_pred))}/{len(P)}",
        "prob_media_classe_prevista": round(float(np.mean(base)), 4),
        "X1c_media": round(float(np.mean(x1)), 4),
        "X1c_ic95": boot_ic(x1),
        "X2c_media": round(float(np.mean(x2)), 4),
        "X2c_ic95": boot_ic(x2),
    }
    r["criterio_X1c"] = r["X1c_media"] > 0 and r["X1c_ic95"][0] > 0
    r["criterio_X2c"] = r["X2c_media"] > 0 and r["X2c_ic95"][0] > 0
    for g, sel in (
        ("previsto_adenocarcinoma", [i for i in range(len(P)) if pred[i] == 0]),
        ("previsto_escamoso", [i for i in range(len(P)) if pred[i] == 1]),
    ):
        v1, v2 = [x1[i] for i in sel], [x2[i] for i in sel]
        r[g] = {
            "n": len(sel),
            "X1c_media": round(float(np.mean(v1)), 4) if sel else None,
            "X1c_ic95": boot_ic(v1) if sel else None,
            "X2c_media": round(float(np.mean(v2)), 4) if sel else None,
            "X2c_ic95": boot_ic(v2) if sel else None,
        }

    (SAIDA / "pulmao_centro.json").write_text(
        json.dumps({**r, "curvas": curvas, "ids": ids, "previsto": pred}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    sem_listas = {
        t: {k: {kk: vv for kk, vv in v.items() if kk != "diferenca_por_lamina"} for k, v in c.items()}
        for t, c in curvas.items()
    }
    resumo = {**r, "curvas": sem_listas}
    (SAIDA / "resumo_pulmao_centro.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items()}, indent=1, ensure_ascii=False))
    print(
        f"X1c {r['X1c_media']} {r['X1c_ic95']} {'SIM' if r['criterio_X1c'] else 'NÃO'} | "
        f"X2c {r['X2c_media']} {r['X2c_ic95']} {'SIM' if r['criterio_X2c'] else 'NÃO'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
