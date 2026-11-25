"""
O aviso de discordância contra as linhas de base certas: ele acrescenta algo à confiança do próprio classificador para
achar os erros?

Antes (aviso_erro.py): o MIL erra mais nas lâminas com aviso (pulmão 4/27 × 0/51; próstata 16% × 6%), mas a comparação
com a confiança não usava a mesma taxa de marcação, e não havia AUROC nem outras linhas de base.

Fixado ANTES de rodar (commit anterior aos resultados):
  Pulmão: as 197 lâminas da divisão por centro (pulmao_por_centro.py), cada uma prevista por modelos que não viram o
     centro dela. Erro: tipo previsto diferente do real.
  Próstata: as 300 biópsias de teste, GAT-MIL padronizado, execução 0 de panda_repeticoes.py (probabilidades de cada
     semente e atenção média). Regiões: 3 de maior atenção com centros a >= 192 µm; classe pelo mesmo descritor dos
     pré-laudos (panda_prelaudo/<id>_descritor.npy). Erro: câncer × benigno trocado.
  Sinais (maior = mais suspeito de erro):
     aviso: número de regiões discordantes (0 a 3), pela regra dos pré-laudos;
     confiança: 1 − probabilidade da classe prevista (média das 5 sementes), o número que vai no laudo;
     sementes: desvio-padrão entre as 5 sementes da probabilidade que decide (pulmão: P(LUSC); próstata: P(ISUP 0));
     classe: 1 se a classe prevista é a "por ausência" (adenocarcinoma; benigno), 0 se não;
     combinação: regressão logística (L2, C = 1) sobre [confiança, aviso], padronizados, com previsão fora da amostra
        por validação cruzada em 5 partes estratificada pelo erro (semente 0).
  Medidas: AUROC para achar erro de cada sinal, com IC 95% por bootstrap das lâminas (2.000, semente 0); diferenças
     pareadas de AUROC; na mesma taxa de marcação do aviso (k = lâminas com aviso), quantos erros cada sinal contínuo
     pega marcando as k mais suspeitas (empates desfeitos ao acaso, média de 200 sorteios, semente 0); curvas de
     risco-cobertura e a área sob elas (AURC).
  Critérios, em cada órgão:
     B1 (o aviso informa): AUROC(aviso) com limite inferior do IC > 0,5.
     B2 (o aviso acrescenta à confiança): AUROC(combinação) − AUROC(confiança) > 0, com limite inferior do IC > 0.
  Observação: calibrar a confiança (escala de temperatura) não muda a ordem das lâminas, então não muda AUROC nem
     risco-cobertura; por isso a confiança entra sem calibrar.

Uso (venv do projeto; depois de pulmao_por_centro.py e panda_repeticoes.py): .venv/bin/python prelaudo/aviso_linhas_base.py
Saída: resultados/aviso_linhas_base/resumo.json
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
from scipy.optimize import minimize  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "aviso_linhas_base"
N_BOOT, SORTEIOS = 2000, 200


def auroc(s, e):
    s, e = np.asarray(s, float), np.asarray(e, bool)
    pos, neg = s[e], s[~e]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def logistica(Xtr, ytr, Xte, C=1.0):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A, B = np.c_[(Xtr - mu) / sd, np.ones(len(Xtr))], np.c_[(Xte - mu) / sd, np.ones(len(Xte))]

    def f(w):
        z = A @ w
        p = 1 / (1 + np.exp(-z))
        g = A.T @ (p - ytr)
        g[:-1] += w[:-1] / C
        return np.sum(np.logaddexp(0, z) - ytr * z) + 0.5 / C * w[:-1] @ w[:-1], g

    w = minimize(f, np.zeros(A.shape[1]), jac=True, method="L-BFGS-B").x
    return B @ w


def combinacao(X, e):
    rng = random.Random(0)
    parte = np.zeros(len(e), int)
    for v in (True, False):
        idx = [i for i in range(len(e)) if e[i] == v]
        rng.shuffle(idx)
        for j, i in enumerate(idx):
            parte[i] = j % 5
    s = np.zeros(len(e))
    for k in range(5):
        tr, te = parte != k, parte == k
        s[te] = logistica(X[tr], e[tr].astype(float), X[te])
    return s


def pegos_na_taxa(s, e, k):
    rng = np.random.default_rng(0)
    v = []
    for _ in range(SORTEIOS):
        ordem = np.lexsort((rng.random(len(s)), -np.asarray(s)))
        v.append(int(e[ordem[:k]].sum()))
    return round(float(np.mean(v)), 2)


def risco_cobertura(s, e):
    ordem = np.argsort(np.asarray(s), kind="stable")  # menos suspeitos primeiro
    ee = e[ordem].astype(float)
    n = len(ee)
    risco = np.cumsum(ee) / np.arange(1, n + 1)
    return {"cobertura": [round((i + 1) / n, 4) for i in range(n)], "risco": [round(float(r), 4) for r in risco],
            "aurc": round(float(risco.mean()), 4)}


def avaliar(sinais, e):
    e = np.asarray(e, bool)
    sinais = dict(sinais)
    sinais["combinacao"] = combinacao(np.c_[sinais["confianca"], sinais["aviso"]], e)
    rng = random.Random(0)
    boot = [np.array([rng.randrange(len(e)) for _ in e]) for _ in range(N_BOOT)]
    boot = [b for b in boot if 0 < e[b].sum() < len(b)]

    def ic(v):
        return [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]

    out = {"n": int(len(e)), "erros": int(e.sum()), "com_aviso": int((sinais["aviso"] > 0).sum()), "auroc": {}}
    for n_, s in sinais.items():
        s = np.asarray(s, float)
        out["auroc"][n_] = {"valor": round(auroc(s, e), 3), "ic95": ic([auroc(s[b], e[b]) for b in boot])}
    for a, b_ in (("aviso", "confianca"), ("combinacao", "confianca"), ("aviso", "sementes"), ("aviso", "classe")):
        sa, sb = np.asarray(sinais[a], float), np.asarray(sinais[b_], float)
        out[f"dif_auroc_{a}_menos_{b_}"] = {"valor": round(auroc(sa, e) - auroc(sb, e), 3),
                                             "ic95": ic([auroc(sa[b], e[b]) - auroc(sb[b], e[b]) for b in boot])}
    k = out["com_aviso"]
    out["erros_pegos_na_taxa_do_aviso"] = {"k": k, "aviso": int(e[np.asarray(sinais["aviso"]) > 0].sum()),
                                           **{n_: pegos_na_taxa(sinais[n_], e, k) for n_ in ("confianca", "sementes", "classe", "combinacao")},
                                           "acaso": round(k * e.mean(), 2)}
    out["risco_cobertura"] = {n_: risco_cobertura(s, e) for n_, s in sinais.items()}
    out["aurc"] = {n_: v["aurc"] for n_, v in out["risco_cobertura"].items()}
    out["criterio_B1"] = out["auroc"]["aviso"]["ic95"][0] > 0.5
    d = out["dif_auroc_combinacao_menos_confianca"]
    out["criterio_B2"] = d["valor"] > 0 and d["ic95"][0] > 0
    return out


def pulmao():
    por = json.loads((RESULTADOS_DIR / "pulmao_centro" / "por_lamina.json").read_text(encoding="utf-8"))
    v = list(por.values())
    p = np.array([d["p_lusc"] for d in v])
    pred = np.array([d["previsto"] for d in v])
    e = pred != np.array([d["real"] for d in v])
    return avaliar({"aviso": np.array([d["n_discordantes"] for d in v], float),
                    "confianca": 1 - np.maximum(p, 1 - p),
                    "sementes": np.array([np.std(d["p_lusc_sementes"]) for d in v]),
                    "classe": (pred == 0).astype(float)}, e)


def prostata():
    from panda_descritor_prelaudo import CLASSES, N_REGIOES, SAIDA as SAIDA_PANDA, carregar
    from panda_mil import biopsias
    from tcga_descritor_prelaudo import gate_um
    pasta = RESULTADOS_DIR / "panda_repeticoes"
    r0 = json.loads((pasta / "gat_padronizado_r0.json").read_text(encoding="utf-8"))
    _, prontas = biopsias()
    te = [l for l in prontas if l["conjunto"] == "teste"]
    av, conf, sem, cl, e = [], [], [], [], []
    for l in te:
        i = l["image_id"]
        d = r0[i]
        g, probs = d["previsto"], np.array(d["probs"])
        meta, xy, _ = carregar(l)
        P = np.load(SAIDA_PANDA / f"{i}_descritor.npy")
        att = np.load(pasta / f"{i}_atencao.npy")
        lado = meta["lado_px"]
        ps = [{"cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a), "classe": CLASSES[int(q.argmax())]}
              for (x, y), q, a in zip(xy, P, att)]
        reg = gate_um(sorted(ps, key=lambda t: -t["atencao"]), meta["mpp"], N_REGIOES)
        av.append(sum((c["classe"] != "benigno") if g == 0 else (c["classe"] == "benigno") for c in reg))
        conf.append(1 - probs[g])
        sem.append(np.std([s[0] for s in d["probs_sementes"]]))
        cl.append(float(g == 0))
        e.append((g == 0) != (d["real"] == 0))
    return avaliar({"aviso": np.array(av, float), "confianca": np.array(conf), "sementes": np.array(sem),
                    "classe": np.array(cl)}, np.array(e))


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    resumo = {"pulmao": pulmao(), "prostata": prostata()}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for o, r in resumo.items():
        print(o, {k: v for k, v in r.items() if k not in ("risco_cobertura",)})
        print(f"{o}: B1 {'SIM' if r['criterio_B1'] else 'NÃO'} | B2 {'SIM' if r['criterio_B2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
