"""
Teste de remoção e de suficiência da atenção com o GAT-MIL padronizado por centro, na próstata.

O teste de remoção (remocao_atencao.py) foi feito com o ABMIL nos dois órgãos; na próstata, os pré-laudos finais
passaram a usar o GAT-MIL com embeddings padronizados por centro (prelaudo_final.py), e as regiões do pré-laudo vêm da
atenção dele. Este teste repete a pergunta com esse modelo: tirar os patches de maior atenção derruba a classe prevista
mais do que tirar patches sorteados? Ficar só com eles sustenta a classe melhor do que ficar com sorteados?

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelo: a receita de prelaudo_final.etapa_gat (GAT-MIL, 8 vizinhos encostados, k = 6, 5 sementes, embeddings
     padronizados por centro; treino nas 600 do Radboud, teste nas 300 do Karolinska), retreinada aqui: os pesos da
     rodada dos pré-laudos não foram guardados e o treino do GAT na GPU não é determinístico. Reportado (sem
     critério): concordância da classe prevista com a da rodada dos pré-laudos e correlação de Spearman média da
     atenção com a atenção salva naquela rodada.
  Ordem dos patches: a atenção média das 5 sementes desta rodada, com todos os patches.
  Grafo depois de tirar patches: refeito só com os patches que ficam (gat_mil.arestas_vizinhos nas coordenadas deles);
     um patch cujos vizinhos saíram fica só com a aresta para si mesmo.
  Cenários, medidas e critérios: os de remocao_atencao.py (f = 1, 2, 5, 10, 20, 50%; n = 5, 10, 20, 50, 100, 200;
     5 sorteios por lâmina com np.random.default_rng([0, i]); bootstrap 2.000, semente 0):
     Y1 (remoção): média de (queda tirando os 10% de maior atenção − queda média tirando 10% sorteados) > 0, IC 95%
        acima de 0.
     Y2 (suficiência): média de (probabilidade só com os 20 de maior atenção − média só com 20 sorteados) > 0, IC 95%
        acima de 0.
  Também reportado (sem critério): as curvas; fração de biópsias em que a classe muda; separado entre previsão ISUP 0
     e ISUP >= 1.
  Limites conhecidos: os de remocao_atencao.py; além disso, tirar patches também tira arestas do grafo, então o
     sorteio controla as duas coisas juntas.

Uso (venv do projeto; GPU):
    .venv/bin/python mil/remocao_atencao_gat.py
Saída: resultados/remocao_atencao/prostata_gat.json e resultados/remocao_atencao/resumo_gat.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402
from remocao_atencao import F_X, FRACOES, N_X, NS, SAIDA, boot_ic, cenarios  # noqa: E402

K = 6


def main():
    import gat_mil
    import mil_atencao
    from gat_mil_panda import carregar
    from panda_centro import padronizar_por_centro
    from panda_mil import PASTA, biopsias
    from prelaudo_final import GAT
    from scipy.stats import spearmanr
    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    y = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X0, G = carregar(tr + te)
    X = padronizar_por_centro(X0, [tr, te])
    xy = {i: np.loadtxt(PASTA / i / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2) for i in te}
    lado = {i: json.loads((PASTA / i / "meta.json").read_text(encoding="utf-8"))["lado_px"] for i in te}
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    ytr = np.array([y[i] for i in tr])
    modelos = []
    for semente in mil_atencao.SEMENTES:
        modelos.append(gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], ytr, semente, dispositivo, k=K).eval())
        print(f"  semente {semente} treinada", flush=True)
    del X0
    antes = json.loads((GAT / "resumo.json").read_text(encoding="utf-8"))["por_biopsia"]

    def prever(x, g):
        p, a = np.zeros(K), np.zeros(len(x))
        with torch.no_grad():
            x, g = x.to(dispositivo), g.to(dispositivo)
            for m in modelos:
                logit, at, _ = m(x, g)
                p += torch.softmax(logit, 0).cpu().numpy() / len(modelos)
                a += at.cpu().numpy() / len(modelos)
        return p, a

    P, pred, rho, iguais = [], [], [], 0
    for n_i, i in enumerate(te):
        x = X[i]
        p_todos, att = prever(x, G[i])
        rho.append(float(spearmanr(att, np.load(GAT / f"{i}_atencao.npy")).correlation))
        conj = cenarios(len(x), att, np.random.default_rng([0, n_i]))
        Pi = {}
        for c, v in conj.items():
            if c == "todos":
                Pi[c] = [p_todos]
                continue
            Pi[c] = []
            for idx in v:
                sub = torch.from_numpy(idx)
                g = gat_mil.arestas_vizinhos(xy[i][idx], lado[i])
                Pi[c].append(prever(x[sub], g)[0])
        P.append(Pi)
        pred.append(int(p_todos.argmax()))
        iguais += pred[-1] == antes[i]["previsto"]
        if (n_i + 1) % 50 == 0:
            print(f"  {n_i + 1}/{len(te)} biópsias", flush=True)

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
    y1 = curvas["remocao"][str(F_X)]["diferenca_por_lamina"]
    y2 = curvas["suficiencia"][str(N_X)]["diferenca_por_lamina"]
    r = {"n": len(P), "classe_igual_a_rodada_dos_prelaudos": f"{iguais}/{len(P)}",
         "spearman_medio_atencao_com_rodada_dos_prelaudos": round(float(np.mean(rho)), 3),
         "prob_media_classe_prevista": round(float(np.mean(base)), 4),
         "Y1_media": round(float(np.mean(y1)), 4), "Y1_ic95": boot_ic(y1),
         "Y2_media": round(float(np.mean(y2)), 4), "Y2_ic95": boot_ic(y2)}
    r["criterio_Y1"] = r["Y1_media"] > 0 and r["Y1_ic95"][0] > 0
    r["criterio_Y2"] = r["Y2_media"] > 0 and r["Y2_ic95"][0] > 0
    for g, sel in (("previsto_isup0", [i for i in range(len(P)) if pred[i] == 0]),
                   ("previsto_isup1_ou_mais", [i for i in range(len(P)) if pred[i] >= 1])):
        r[g] = {"n": len(sel), "Y1_media": round(float(np.mean([y1[i] for i in sel])), 4) if sel else None,
                "Y2_media": round(float(np.mean([y2[i] for i in sel])), 4) if sel else None}
    (SAIDA / "prostata_gat.json").write_text(json.dumps({**r, "curvas": curvas, "ids": te, "previsto": pred},
                                                        indent=1, ensure_ascii=False), encoding="utf-8")
    sem_listas = {t: {k: {kk: vv for kk, vv in v.items() if kk != "diferenca_por_lamina"} for k, v in c.items()}
                  for t, c in curvas.items()}
    (SAIDA / "resumo_gat.json").write_text(json.dumps({**r, "curvas": sem_listas}, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
    print(json.dumps({k: v for k, v in r.items()}, indent=1, ensure_ascii=False))
    print(f"Y1 {r['Y1_media']} {r['Y1_ic95']} {'SIM' if r['criterio_Y1'] else 'NÃO'} | "
          f"Y2 {r['Y2_media']} {r['Y2_ic95']} {'SIM' if r['criterio_Y2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
