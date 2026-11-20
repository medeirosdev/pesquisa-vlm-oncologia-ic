"""
A atenção do MIL aponta os patches que sustentam a decisão? Teste de remoção e de suficiência, sem precisar de
anotação, no pulmão (TCGA LUAD × LUSC, 78 lâminas de teste) e na próstata (PANDA, 300 biópsias de teste do
Karolinska). No pulmão não há anotação de região, então a atenção só tinha sido mostrada nos mapas; na próstata ela
foi conferida nas máscaras (2 de 3 regiões no câncer em 190 de 250 biópsias). Este teste mede a mesma coisa nos dois
órgãos, pelo próprio modelo: se a atenção aponta o que sustenta a classe, tirar os patches de maior atenção deve
derrubar a probabilidade da classe mais do que tirar patches sorteados, e ficar só com eles deve sustentar a classe
melhor do que ficar com patches sorteados.

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelos: os mesmos das rodadas que geraram a atenção usada nos pré-laudos e nos mapas: pulmão, como em
     tcga_descritor_prelaudo.etapa_atencao (lâminas de treino de tcga_mil.py, k = 2); próstata, como em panda_mil.py
     (600 do Radboud, k = 6). mil_atencao.treinar, 5 sementes, mesmos hiperparâmetros; a probabilidade é a média
     das 5 sementes. Reportada a concordância da classe prevista com a das rodadas anteriores.
  Ordem dos patches: a atenção média salva nas rodadas anteriores (<id>_atencao.npy), a mesma que escolhe as regiões
     do pré-laudo e desenha os mapas.
  Classe de referência de cada lâmina: a prevista com todos os patches nesta rodada. Medida: probabilidade dessa
     classe (média das 5 sementes).
  Remoção: tirar os f% de maior atenção × tirar f% sorteados (5 sorteios, mesma semente por lâmina), f = 1, 2, 5,
     10, 20 e 50% dos patches (pelo menos 1). Queda = probabilidade com todos − probabilidade sem eles.
  Suficiência: ficar só com os n patches de maior atenção × n sorteados (5 sorteios), n = 5, 10, 20, 50, 100 e 200
     (no máximo o número de patches da lâmina).
  Critérios, em cada órgão:
     X1 (remoção): média, por lâmina, de (queda tirando os 10% de maior atenção − queda média tirando 10% sorteados)
        > 0, com IC 95% por bootstrap das lâminas (2.000, semente 0) acima de 0.
     X2 (suficiência): média, por lâmina, de (probabilidade só com os 20 de maior atenção − média só com 20
        sorteados) > 0, com IC 95% acima de 0.
  Também reportado (sem critério): as curvas inteiras; fração de lâminas em que a classe prevista muda em cada
     cenário; na próstata, separado entre previsão ISUP 0 e ISUP >= 1.
  Limites conhecidos: remover patches muda a distribuição que o modelo viu no treino (as quedas com sorteio servem
     de controle para isso); o teste mede se a atenção é fiel ao modelo, não se o modelo está certo.

Uso (venv do projeto; GPU se houver):
    .venv/bin/python mil/remocao_atencao.py
Saída: resultados/remocao_atencao/{resumo.json, pulmao.json, prostata.json}
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np
import torch

from comum.lamina import RESULTADOS_DIR

SAIDA = RESULTADOS_DIR / "remocao_atencao"
FRACOES = [0.01, 0.02, 0.05, 0.10, 0.20, 0.50]
NS = [5, 10, 20, 50, 100, 200]
SORTEIOS = 5
F_X, N_X = 0.10, 20
N_BOOT = 2000


def dados_pulmao():
    from tcga_descritor_prelaudo import PASTA, SAIDA as SAIDA_PL
    from tcga_mil import CLASSES, LISTA
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    prontas = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    tr = [l for l in prontas if l["conjunto"] == "treino"]
    te = [l for l in prontas if l["conjunto"] == "teste"]
    X = lambda l: torch.from_numpy(np.load(PASTA / l["file_id"] / "amostra2000.npy"))  # noqa: E731
    antes = json.loads((SAIDA_PL / "mil.json").read_text(encoding="utf-8"))["por_lamina"]
    return {"k": 2, "Xtr": [X(l) for l in tr], "ytr": np.array([CLASSES.index(l["projeto"]) for l in tr]),
            "ids": [l["file_id"] for l in te], "Xte": [X(l) for l in te],
            "att": [np.load(SAIDA_PL / f"{l['file_id']}_atencao.npy") for l in te],
            "antes": [int(antes[l["file_id"]]["predito"] == "TCGA-LUSC") for l in te]}


def dados_prostata():
    from panda_mil import PASTA, SAIDA as SAIDA_MIL, biopsias
    _, prontas = biopsias()
    tr = [l for l in prontas if l["conjunto"] == "treino"]
    te = [l for l in prontas if l["conjunto"] == "teste"]
    X = lambda l: torch.from_numpy(np.load(PASTA / l["image_id"] / "amostra2000.npy"))  # noqa: E731
    antes = json.loads((SAIDA_MIL / "resumo.json").read_text(encoding="utf-8"))["por_biopsia"]
    return {"k": 6, "Xtr": [X(l) for l in tr], "ytr": np.array([int(l["isup_grade"]) for l in tr]),
            "ids": [l["image_id"] for l in te], "Xte": [X(l) for l in te],
            "att": [np.load(SAIDA_MIL / f"{l['image_id']}_atencao.npy") for l in te],
            "antes": [antes[l["image_id"]]["previsto"] for l in te]}


def cenarios(n, att, rng):
    """{nome: [índices mantidos, ...]} (uma lista com 1 conjunto para atenção, SORTEIOS conjuntos para sorteio)."""
    ordem = np.argsort(-att)
    todos = np.arange(n)
    c = {"todos": [todos]}
    for f in FRACOES:
        m = max(1, int(round(f * n)))
        c[f"remove_top_{f}"] = [np.sort(ordem[m:])]
        c[f"remove_sorteio_{f}"] = [np.sort(rng.permutation(n)[m:]) for _ in range(SORTEIOS)]
    for k in NS:
        m = min(k, n)
        c[f"so_top_{k}"] = [np.sort(ordem[:m])]
        c[f"so_sorteio_{k}"] = [np.sort(rng.permutation(n)[:m]) for _ in range(SORTEIOS)]
    return c


def boot_ic(v, semente=0):
    rng = random.Random(semente)
    v = np.asarray(v)
    m = [float(np.mean(v[[rng.randrange(len(v)) for _ in v]])) for _ in range(N_BOOT)]
    return [round(float(np.percentile(m, 2.5)), 4), round(float(np.percentile(m, 97.5)), 4)]


def rodar(nome, d):
    from mil_atencao import SEMENTES, treinar
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    conj = [cenarios(len(x), a, np.random.default_rng([0, i])) for i, (x, a) in enumerate(zip(d["Xte"], d["att"]))]
    # P[i][cenario] = lista (um por conjunto de índices) de vetores de probabilidade, média das sementes
    P = [{c: [np.zeros(d["k"]) for _ in v] for c, v in cj.items()} for cj in conj]
    for semente in SEMENTES:
        modelo = treinar(d["Xtr"], d["ytr"], semente, dispositivo, k=d["k"])
        modelo.eval()
        with torch.no_grad():
            for i, x in enumerate(d["Xte"]):
                x = x.to(dispositivo)
                for c, v in conj[i].items():
                    for j, idx in enumerate(v):
                        logit, _ = modelo(x[torch.from_numpy(idx).to(dispositivo)])
                        P[i][c][j] += torch.softmax(logit, 0).cpu().numpy() / len(SEMENTES)
        print(f"  {nome}: semente {semente} pronta", flush=True)
    del d["Xtr"]

    pred = [int(p["todos"][0].argmax()) for p in P]
    prob = lambda i, c: [float(v[pred[i]]) for v in P[i][c]]  # noqa: E731
    muda = lambda i, c: float(np.mean([int(v.argmax()) != pred[i] for v in P[i][c]]))  # noqa: E731
    base = [prob(i, "todos")[0] for i in range(len(P))]
    curvas = {"remocao": {}, "suficiencia": {}}
    for f in FRACOES:
        qt = [base[i] - prob(i, f"remove_top_{f}")[0] for i in range(len(P))]
        qs = [base[i] - float(np.mean(prob(i, f"remove_sorteio_{f}"))) for i in range(len(P))]
        curvas["remocao"][str(f)] = {"queda_top": round(float(np.mean(qt)), 4), "queda_sorteio": round(float(np.mean(qs)), 4),
                                     "muda_classe_top": round(float(np.mean([muda(i, f"remove_top_{f}") for i in range(len(P))])), 4),
                                     "muda_classe_sorteio": round(float(np.mean([muda(i, f"remove_sorteio_{f}") for i in range(len(P))])), 4),
                                     "diferenca_por_lamina": [round(a - b, 5) for a, b in zip(qt, qs)]}
    for k in NS:
        pt = [prob(i, f"so_top_{k}")[0] for i in range(len(P))]
        ps = [float(np.mean(prob(i, f"so_sorteio_{k}"))) for i in range(len(P))]
        curvas["suficiencia"][str(k)] = {"prob_top": round(float(np.mean(pt)), 4), "prob_sorteio": round(float(np.mean(ps)), 4),
                                         "mantem_classe_top": round(1 - float(np.mean([muda(i, f"so_top_{k}") for i in range(len(P))])), 4),
                                         "mantem_classe_sorteio": round(1 - float(np.mean([muda(i, f"so_sorteio_{k}") for i in range(len(P))])), 4),
                                         "diferenca_por_lamina": [round(a - b, 5) for a, b in zip(pt, ps)]}
    x1 = curvas["remocao"][str(F_X)]["diferenca_por_lamina"]
    x2 = curvas["suficiencia"][str(N_X)]["diferenca_por_lamina"]
    r = {"n": len(P), "classe_igual_a_rodada_anterior": f"{sum(a == b for a, b in zip(pred, d['antes']))}/{len(P)}",
         "prob_media_classe_prevista": round(float(np.mean(base)), 4),
         "X1_media": round(float(np.mean(x1)), 4), "X1_ic95": boot_ic(x1),
         "X2_media": round(float(np.mean(x2)), 4), "X2_ic95": boot_ic(x2)}
    r["criterio_X1"] = r["X1_media"] > 0 and r["X1_ic95"][0] > 0
    r["criterio_X2"] = r["X2_media"] > 0 and r["X2_ic95"][0] > 0
    if nome == "prostata":
        for g, sel in (("previsto_isup0", [i for i in range(len(P)) if pred[i] == 0]),
                       ("previsto_isup1_ou_mais", [i for i in range(len(P)) if pred[i] >= 1])):
            r[g] = {"n": len(sel), "X1_media": round(float(np.mean([x1[i] for i in sel])), 4) if sel else None,
                    "X2_media": round(float(np.mean([x2[i] for i in sel])), 4) if sel else None}
    (SAIDA / f"{nome}.json").write_text(json.dumps({**r, "curvas": curvas, "ids": d["ids"], "previsto": pred},
                                                   indent=1, ensure_ascii=False), encoding="utf-8")
    sem_listas = {t: {k: {kk: vv for kk, vv in v.items() if kk != "diferenca_por_lamina"} for k, v in c.items()}
                  for t, c in curvas.items()}
    return {**r, "curvas": sem_listas}


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    resumo = {}
    for nome, carregar in (("pulmao", dados_pulmao), ("prostata", dados_prostata)):
        resumo[nome] = rodar(nome, carregar())
        (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
        r = resumo[nome]
        print(f"{nome}: X1 {r['X1_media']} {r['X1_ic95']} {'SIM' if r['criterio_X1'] else 'NÃO'} | "
              f"X2 {r['X2_media']} {r['X2_ic95']} {'SIM' if r['criterio_X2'] else 'NÃO'}", flush=True)


if __name__ == "__main__":
    main()
