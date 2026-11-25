"""
"Classe por ausência": nas lâminas previstas como a classe que o MIL parece decidir pela falta de evidência
(adenocarcinoma no pulmão, benigno na próstata), os patches de maior atenção empurram a decisão a favor ou contra a
classe prevista?

Antes (remocao_atencao.py, análise feita depois e sem critério): nas lâminas previstas como adenocarcinoma, os 20
patches de maior atenção sustentaram a classe pior do que 20 sorteados. A revisão apontou explicações alternativas: teto
da probabilidade (medir em logit), 20 patches fora da distribuição de treino, e atenção que não diz para qual classe o
patch empurra. Aqui a pergunta vira hipótese com critério fixado antes.

O classificador do ABMIL e do GAT-MIL é linear sobre a soma ponderada, então a margem se decompõe exatamente por patch:
margem = Σ_i a_i · (w_prevista − w_outra) · h_i + (b_prevista − b_outra), com h_i a característica do patch antes da
soma (no GAT-MIL, depois do grafo) e a_i a atenção. A contribuição assinada c_i = a_i · (w_prevista − w_outra) · h_i é
positiva quando o patch empurra a favor da classe prevista. Na próstata (6 classes), w_outra = média das outras 5.

Fixado ANTES de rodar (commit anterior aos resultados):
  Pulmão: as 197 lâminas, a mesma divisão por centro de pulmao_por_centro.py (5 partes, 5 sementes por parte; cada
     lâmina vista só por modelos que não viram o centro dela), ABMIL retreinado aqui com as mesmas sementes.
  Próstata: as 300 de teste, GAT-MIL padronizado (sementes 0 a 4) retreinado aqui, como em panda_repeticoes.py.
  Por lâmina e semente: c_i de todos os patches e a margem. Medidas (média das 5 sementes, por lâmina):
     contribuição dos 20 de maior atenção = Σ c_i nos 20 de maior atenção, dividida pela soma de |c_i| na lâmina;
     o mesmo para 20 patches sorteados (média de 5 sorteios, semente [0, i]);
     remoção e suficiência na margem (logit), não na probabilidade: queda da margem tirando os 10% de maior atenção
     menos a queda tirando 10% sorteados; margem só com os 20 de maior atenção menos só com 20 sorteados (no GAT-MIL,
     grafo refeito com os patches que ficam);
     composição pelo descritor (pulmão): fração dos 20 de maior atenção que o descritor chama da outra classe tumoral,
     menos a mesma fração em 20 sorteados.
  Grupos: classe "por ausência" prevista (adenocarcinoma; ISUP 0) e classe "positiva" prevista (escamoso; ISUP >= 1).
     IC 95% por bootstrap das lâminas dentro de cada grupo (2.000, semente 0).
  Critérios (a hipótese diz que os patches de maior atenção empurram contra a classe prevista nas lâminas "por ausência"):
     H1 (pulmão): nas previstas como adenocarcinoma, contribuição dos 20 de maior atenção < 0, com limite superior do IC < 0.
     H2 (pulmão): nas previstas como adenocarcinoma, suficiência na margem (20 de maior atenção − 20 sorteados) < 0, com
        limite superior do IC < 0 (o achado antigo, agora fixado antes e em logit).
     H3 (próstata): nas previstas como ISUP 0, contribuição dos 20 de maior atenção < 0, com limite superior do IC < 0.
  Também reportado (sem critério): as mesmas medidas no grupo "positivo"; remoção na margem por grupo; composição pelo
     descritor; número de lâminas por grupo.
  Limites conhecidos: a decomposição é exata para o modelo, não diz o que o patch mostra; no GAT-MIL h_i já mistura os
     vizinhos; poucos benignos previstos na próstata.

Uso (venv do projeto; GPU): .venv/bin/python mil/ausencia.py
Saída: resultados/ausencia/resumo.json
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "ausencia"
TOP, FR, SORT, N_BOOT = 20, 0.10, 5, 2000


def interno(m, x, g=None):
    """h_i (antes da soma) e a_i."""
    import torch
    if g is None:
        h = m.proj(x)
    else:
        h0 = m.proj(x)
        gg, _ = m.gat(h0, g)
        h = m.pos_gat(h0 + gg)
    a = torch.softmax(m.att_w(m.att_v(h) * m.att_u(h)).squeeze(-1), dim=0)
    return h, a


def margem_vetor(m, prev):
    W, b = m.cls.weight, m.cls.bias
    k = W.shape[0]
    outras = [c for c in range(k) if c != prev]
    return W[prev] - W[outras].mean(0), b[prev] - b[outras].mean()


def medir(modelos, x, g, prev, rng, xy=None, lado=None):
    """Medidas de uma lâmina (média nas sementes)."""
    import torch
    import gat_mil
    n = len(x)
    ordem = None
    contrib_top, contrib_sort, rem, suf = [], [], [], []
    m_top = max(1, int(round(FR * n)))
    sorteios_rem = [np.sort(rng.permutation(n)[m_top:]) for _ in range(SORT)]
    sorteios_suf = [np.sort(rng.permutation(n)[:min(TOP, n)]) for _ in range(SORT)]
    att_media = np.zeros(n)
    for m in modelos:
        with torch.no_grad():
            h, a = interno(m, x, g)
            att_media += a.cpu().numpy() / len(modelos)
    ordem = np.argsort(-att_media)
    for m in modelos:
        with torch.no_grad():
            wv, bv = margem_vetor(m, prev)

            def margem(idx):
                idx_t = torch.from_numpy(np.asarray(idx)).to(x.device)
                gg = None if g is None else gat_mil.arestas_vizinhos(xy[np.asarray(idx)], lado).to(x.device)
                hh, aa = interno(m, x[idx_t], gg)
                return float(((aa.unsqueeze(-1) * hh).sum(0) @ wv + bv))
            h, a = interno(m, x, g)
            c = (a * (h @ wv)).cpu().numpy()
            tot = np.abs(c).sum() + 1e-12
            contrib_top.append(c[ordem[:TOP]].sum() / tot)
            contrib_sort.append(np.mean([c[s].sum() / tot for s in sorteios_suf]))
            m_all = margem(np.arange(n))
            rem.append((m_all - margem(np.sort(ordem[m_top:]))) - np.mean([m_all - margem(s) for s in sorteios_rem]))
            suf.append(margem(np.sort(ordem[:min(TOP, n)])) - np.mean([margem(s) for s in sorteios_suf]))
    return {"contrib_top": float(np.mean(contrib_top)), "contrib_sorteio": float(np.mean(contrib_sort)),
            "remocao_margem": float(np.mean(rem)), "suficiencia_margem": float(np.mean(suf)), "ordem_top": ordem[:TOP]}


def ic(v):
    v = np.asarray(v)
    if len(v) == 0:
        return None
    rng = random.Random(0)
    b = [float(np.mean(v[[rng.randrange(len(v)) for _ in v]])) for _ in range(N_BOOT)]
    return [round(float(np.percentile(b, 2.5)), 4), round(float(np.percentile(b, 97.5)), 4)]


def resumir(linhas, grupo):
    sel = [r for r in linhas if r["grupo"] == grupo]
    out = {"n": len(sel)}
    for k in ("contrib_top", "contrib_sorteio", "remocao_margem", "suficiencia_margem", "composicao_outra_classe"):
        v = [r[k] for r in sel if r.get(k) is not None]
        if v:
            out[k] = {"media": round(float(np.mean(v)), 4), "ic95": ic(v)}
    return out


def pulmao():
    import torch
    from mil_atencao import SEMENTES, treinar
    from pulmao_por_centro import PARTES, centro, partes_por_centro
    from tcga_descritor_prelaudo import PASTA
    from tcga_mil import CLASSES, LISTA
    lam = [l for l in csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t") if (PASTA / l["file_id"] / "meta.json").exists()]
    pc = partes_por_centro(lam)
    y = np.array([CLASSES.index(l["projeto"]) for l in lam])
    parte = np.array([pc[centro(l)] for l in lam])
    X = [torch.from_numpy(np.load(PASTA / l["file_id"] / "amostra2000.npy")) for l in lam]
    desc = RESULTADOS_DIR / "pulmao_centro"
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    linhas = []
    for k in range(PARTES):
        tr, te = np.where(parte != k)[0], np.where(parte == k)[0]
        modelos = [treinar([X[i] for i in tr], y[tr], s, dev, k=2).eval() for s in SEMENTES]
        for i in te:
            x = X[i].to(dev)
            with torch.no_grad():
                p = np.mean([float(torch.softmax(m(x)[0], 0)[1]) for m in modelos])
            prev = int(p >= 0.5)
            r = medir(modelos, x, None, prev, np.random.default_rng([0, int(i)]))
            Pd = np.load(desc / f"{lam[i]['file_id']}_descritor.npy").argmax(1)  # 0 normal, 1 adeno, 2 escamoso
            outra = 2 if prev == 0 else 1
            sorteio = np.random.default_rng([1, int(i)]).permutation(len(Pd))[:TOP]
            r["composicao_outra_classe"] = float(np.mean(Pd[r.pop("ordem_top")] == outra) - np.mean(Pd[sorteio] == outra))
            r.update({"grupo": "ausencia" if prev == 0 else "positiva", "real": int(y[i]), "previsto": prev})
            linhas.append(r)
        print(f"  pulmão parte {k} pronta", flush=True)
    return linhas


def prostata():
    import torch
    import gat_mil
    from gat_mil_panda import carregar
    from panda_centro import padronizar_por_centro
    from panda_mil import PASTA, biopsias
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
        r = medir(modelos, x, g, prev, np.random.default_rng([0, n_i]), xy, lado)
        r.pop("ordem_top")
        r.update({"grupo": "ausencia" if prev == 0 else "positiva", "real": yv[i], "previsto": prev})
        linhas.append(r)
        if (n_i + 1) % 50 == 0:
            print(f"  próstata {n_i + 1}/{len(te)}", flush=True)
    return linhas


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    resumo = {}
    for nome, f in (("pulmao", pulmao), ("prostata", prostata)):
        linhas = f()
        resumo[nome] = {g: resumir(linhas, g) for g in ("ausencia", "positiva")}
        (SAIDA / f"{nome}_por_lamina.json").write_text(json.dumps(linhas, indent=1), encoding="utf-8")
        (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    a_p, a_q = resumo["pulmao"]["ausencia"], resumo["prostata"]["ausencia"]
    resumo["criterio_H1"] = a_p["contrib_top"]["media"] < 0 and a_p["contrib_top"]["ic95"][1] < 0
    resumo["criterio_H2"] = a_p["suficiencia_margem"]["media"] < 0 and a_p["suficiencia_margem"]["ic95"][1] < 0
    resumo["criterio_H3"] = (a_q.get("contrib_top") is not None and a_q["contrib_top"]["media"] < 0
                             and a_q["contrib_top"]["ic95"][1] < 0)
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))
    print(f"H1 {'SIM' if resumo['criterio_H1'] else 'NÃO'} | H2 {'SIM' if resumo['criterio_H2'] else 'NÃO'} | "
          f"H3 {'SIM' if resumo['criterio_H3'] else 'NÃO'}")


if __name__ == "__main__":
    main()
