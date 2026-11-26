"""
GAT-MIL padronizado (próstata) com o grafo fixo nos testes de remoção e suficiência (revisão C3: "no GAT-MIL, testar uma
variante com o grafo fixo").

Antes (ausencia.py, H3): nas biópsias previstas como ISUP 0, a decomposição exata diz que os 20 patches de maior atenção
empurram a favor do benigno (+0,37 da soma), mas a remoção e a suficiência na margem são negativas (−3,05 e −2,79). Nesses
testes o grafo é refeito só com os patches que ficam, então cada patch perde ou muda os vizinhos, e a característica h_i
muda. Hipótese: a discordância vem de refazer o grafo. Com o grafo fixo (h_i calculado com todos os patches e os
vizinhos originais; só a atenção é renormalizada no subconjunto), os testes devem concordar com a decomposição.

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelos e dados: os mesmos de ausencia.prostata (GAT-MIL treinado nas 600 do Radboud com embeddings padronizados por
     centro, sementes 0 a 4; 300 biópsias de teste do Karolinska); classe prevista = argmax da média das sementes.
  Medidas, por biópsia e semente (média das sementes), na margem (logit da prevista − média das outras):
     grafo refeito (como em ausencia.py) e grafo fixo; remoção: queda tirando os 10% de maior atenção − queda tirando
     10% sorteados (5 sorteios); suficiência: margem só com os 20 de maior atenção − só com 20 sorteados.
  Critério F: nas previstas como ISUP 0, suficiência na margem com o grafo fixo > 0, com limite inferior do IC 95% > 0
     (bootstrap das biópsias, 2.000, semente 0).
  Também reportado (sem critério): as quatro medidas (remoção e suficiência, grafo refeito e fixo) nos dois grupos.

Uso (venv do projeto; GPU): .venv/bin/python mil/gat_grafo_fixo.py
Saída: resultados/gat_grafo_fixo/resumo.json
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "gat_grafo_fixo"
TOP, FR, SORT, N_BOOT = 20, 0.10, 5, 2000


def ic(v):
    v = np.asarray(v)
    rng = random.Random(0)
    b = [float(np.mean(v[[rng.randrange(len(v)) for _ in v]])) for _ in range(N_BOOT)]
    return [round(float(np.percentile(b, 2.5)), 3), round(float(np.percentile(b, 97.5)), 3)]


def main():
    import torch
    import gat_mil
    from ausencia import interno, margem_vetor
    from gat_mil_panda import carregar
    from panda_centro import padronizar_por_centro
    from panda_mil import PASTA, biopsias
    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    yv = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X0, G = carregar(tr + te)
    X = padronizar_por_centro(X0, [tr, te])
    del X0
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelos = [gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], np.array([yv[i] for i in tr]), s, dev, k=6).eval()
               for s in range(5)]
    linhas = []
    for n_i, i in enumerate(te):
        x, g = X[i].to(dev), G[i].to(dev)
        with torch.no_grad():
            P = np.mean([torch.softmax(m(x, g)[0], 0).cpu().numpy() for m in modelos], axis=0)
        prev = int(P.argmax())
        xy = np.loadtxt(PASTA / i / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        lado = json.loads((PASTA / i / "meta.json").read_text(encoding="utf-8"))["lado_px"]
        n = len(x)
        rng = np.random.default_rng([0, n_i])
        m_top = max(1, int(round(FR * n)))
        sort_rem = [np.sort(rng.permutation(n)[m_top:]) for _ in range(SORT)]
        sort_suf = [np.sort(rng.permutation(n)[:min(TOP, n)]) for _ in range(SORT)]
        med = {k: [] for k in ("rem_refeito", "suf_refeito", "rem_fixo", "suf_fixo")}
        for m in modelos:
            with torch.no_grad():
                wv, bv = margem_vetor(m, prev)
                h_full, a_full = interno(m, x, g)
                ordem = np.argsort(-a_full.cpu().numpy())

                def margem_refeito(idx):
                    idx_t = torch.from_numpy(np.asarray(idx)).to(dev)
                    gg = gat_mil.arestas_vizinhos(xy[np.asarray(idx)], lado).to(dev)
                    hh, aa = interno(m, x[idx_t], gg)
                    return float(((aa.unsqueeze(-1) * hh).sum(0) @ wv + bv))

                def margem_fixo(idx):
                    hh = h_full[torch.from_numpy(np.asarray(idx)).to(dev)]
                    aa = torch.softmax(m.att_w(m.att_v(hh) * m.att_u(hh)).squeeze(-1), dim=0)
                    return float(((aa.unsqueeze(-1) * hh).sum(0) @ wv + bv))

                top_rem = np.sort(ordem[m_top:])
                top_suf = np.sort(ordem[:min(TOP, n)])
                for nome, f in (("refeito", margem_refeito), ("fixo", margem_fixo)):
                    m_all = f(np.arange(n))
                    med[f"rem_{nome}"].append((m_all - f(top_rem)) - np.mean([m_all - f(s) for s in sort_rem]))
                    med[f"suf_{nome}"].append(f(top_suf) - np.mean([f(s) for s in sort_suf]))
        linhas.append({"grupo": "ausencia" if prev == 0 else "positiva", "real": yv[i], "previsto": prev,
                       **{k: float(np.mean(v)) for k, v in med.items()}})
        if (n_i + 1) % 50 == 0:
            print(f"  {n_i + 1}/{len(te)}", flush=True)
    res = {}
    for gr in ("ausencia", "positiva"):
        sel = [r for r in linhas if r["grupo"] == gr]
        res[gr] = {"n": len(sel), **{k: {"media": round(float(np.mean([r[k] for r in sel])), 3), "ic95": ic([r[k] for r in sel])}
                                     for k in ("rem_refeito", "suf_refeito", "rem_fixo", "suf_fixo")}}
    s = res["ausencia"]["suf_fixo"]
    res["criterio_F"] = bool(res["ausencia"]["n"] and s["media"] > 0 and s["ic95"][0] > 0)
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "por_biopsia.json").write_text(json.dumps(linhas, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"F {'SIM' if res['criterio_F'] else 'NÃO'}")


if __name__ == "__main__":
    main()
