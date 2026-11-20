"""
O aviso de discordância marca os erros do MIL? Nas lâminas em que alguma das 3 regiões de maior atenção discorda da
classe sugerida (o aviso que vai no pré-laudo), o MIL erra mais do que nas lâminas sem aviso?

O aviso é calculado por código, a partir dos campos (aviso_discordancia.discordantes), sem o modelo de linguagem; então
dá para medir em todas as lâminas de teste, não só nas que viraram pré-laudo.

Fixado ANTES de rodar (commit anterior aos resultados):
  Pulmão: as 78 lâminas de teste do TCGA, decisão do ABMIL (resultados/tcga_prelaudo/mil.json) e campos dos pré-laudos
     (resultados/tcga_prelaudo/<id>_campos.txt). Erro: tipo previsto diferente do real.
  Próstata: as 300 biópsias de teste do Karolinska, decisão do GAT-MIL com embeddings padronizados por centro e as 3
     regiões de maior atenção dele (prelaudo_final.py, etapa gat), classe de cada região pelo mesmo descritor.
     Erro principal: câncer × benigno trocado (ISUP previsto 0 e real >= 1, ou previsto >= 1 e real 0), porque o
     aviso da próstata é sobre isso (região benigna com ISUP >= 1 sugerido, ou região com Gleason com ISUP 0).
     Também reportado (sem critério): erro de ISUP exato e erro de 2 ou mais graus.
  Critério E, em cada órgão: taxa de erro nas lâminas com aviso > taxa nas lâminas sem aviso, com teste exato de
     Fisher unilateral p < 0,05.
  Também reportado (sem critério): a tabela 2 × 2; sensibilidade (erros com aviso / erros), especificidade, valor
     preditivo positivo e negativo; risco relativo com IC 95% por bootstrap (2.000, semente 0); a mesma comparação
     usando "confiança não alta" (probabilidade da classe sugerida < 0,70) como sinal, e o aviso dentro das lâminas com
     confiança alta (o aviso acrescenta algo à confiança?).
  Limite conhecido: no pulmão o MIL erra pouco (4 de 78), então o teste tem pouco poder.

Uso (venv do projeto; depois de prelaudo_final.py --etapa gat):
    .venv/bin/python prelaudo/aviso_erro.py
Saída: resultados/aviso_erro/resumo.json
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
from scipy.stats import fisher_exact  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

from aviso_discordancia import ORIGEM, discordantes, documentos  # noqa: E402

SAIDA = RESULTADOS_DIR / "aviso_erro"
P_MAX = 0.05
CONF_ALTA = 0.70
N_BOOTSTRAP = 2000


def tabela(sinal, erro):
    s, e = np.asarray(sinal, bool), np.asarray(erro, bool)
    a, b = int((s & e).sum()), int((s & ~e).sum())
    c, d = int((~s & e).sum()), int((~s & ~e).sum())
    p = fisher_exact([[a, b], [c, d]], alternative="greater")[1]
    tx_s, tx_n = a / max(a + b, 1), c / max(c + d, 1)
    rng, rr = random.Random(0), []
    idx = list(range(len(s)))
    for _ in range(N_BOOTSTRAP):
        r = [rng.choice(idx) for _ in idx]
        ss, ee = s[r], e[r]
        ts, tn = ee[ss].mean() if ss.any() else np.nan, ee[~ss].mean() if (~ss).any() else np.nan
        rr.append(ts / tn if tn > 0 else np.nan)
    rr = np.array(rr, float)
    rr = rr[np.isfinite(rr)]
    return {"com_sinal_erro": a, "com_sinal_acerto": b, "sem_sinal_erro": c, "sem_sinal_acerto": d,
            "taxa_erro_com_sinal": round(tx_s, 3), "taxa_erro_sem_sinal": round(tx_n, 3),
            "sensibilidade": round(a / max(a + c, 1), 3), "especificidade": round(d / max(b + d, 1), 3),
            "vpp": round(tx_s, 3), "vpn": round(d / max(c + d, 1), 3),
            "risco_relativo": round(tx_s / tx_n, 3) if tx_n > 0 else None,
            "ic95_risco_relativo": ([round(float(np.percentile(rr, 2.5)), 3), round(float(np.percentile(rr, 97.5)), 3)]
                                    if len(rr) else None),
            "reamostras_validas_rr": int(len(rr)), "fisher_p_unilateral": round(float(p), 4)}


def comparar(aviso, erro, conf_alta):
    aviso, erro, conf_alta = map(lambda v: np.asarray(v, bool), (aviso, erro, conf_alta))
    out = {"n": int(len(aviso)), "com_aviso": int(aviso.sum()), "erros": int(erro.sum()),
           "aviso": tabela(aviso, erro), "confianca_nao_alta": tabela(~conf_alta, erro),
           "aviso_ou_confianca_nao_alta": tabela(aviso | ~conf_alta, erro)}
    if conf_alta.sum() > 0:
        out["aviso_dentro_da_confianca_alta"] = tabela(aviso[conf_alta], erro[conf_alta])
    return out


def pulmao():
    mil = json.loads((ORIGEM["pulmao"] / "mil.json").read_text(encoding="utf-8"))["por_lamina"]
    aviso, erro, conf = [], [], []
    for k, sug, campos in documentos("pulmao"):
        m = mil[k]
        aviso.append(bool(discordantes("pulmao", sug, campos)))
        erro.append(m["real"] != m["predito"])
        p = m["p_lusc"] if m["predito"] == "TCGA-LUSC" else 1 - m["p_lusc"]
        conf.append(p >= CONF_ALTA)
    return comparar(aviso, erro, conf)


def prostata():
    from panda_descritor_prelaudo import NOME_PT
    from panda_mil import biopsias
    from prelaudo_final import GAT, regioes_gat
    gat = json.loads((GAT / "resumo.json").read_text(encoding="utf-8"))["por_biopsia"]
    _, prontas = biopsias()
    aviso, erro_cb, erro_exato, erro_2, conf = [], [], [], [], []
    for l in prontas:
        if l["conjunto"] != "teste":
            continue
        m = gat[l["image_id"]]
        g, real = m["previsto"], int(l["isup_grade"])
        _, _, reg = regioes_gat(l)
        campos = "\n".join(f"  [{d['x0']},{d['y0']}] {NOME_PT[d['classe']]} {d['prob']:.2f}" for d in reg)
        aviso.append(bool(discordantes("prostata", g, campos)))
        erro_cb.append((g == 0) != (real == 0))
        erro_exato.append(g != real)
        erro_2.append(abs(g - real) >= 2)
        conf.append(m["probs"][g] >= CONF_ALTA)
    out = comparar(aviso, erro_cb, conf)
    out["erro_isup_exato"] = comparar(aviso, erro_exato, conf)
    out["erro_2_ou_mais_graus"] = comparar(aviso, erro_2, conf)
    return out


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    resumo = {"pulmao": pulmao(), "prostata": prostata()}
    for o in ("pulmao", "prostata"):
        a = resumo[o]["aviso"]
        resumo[o]["criterio_E"] = a["taxa_erro_com_sinal"] > a["taxa_erro_sem_sinal"] and a["fisher_p_unilateral"] < P_MAX
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for o, r in resumo.items():
        a = r["aviso"]
        print(f"{o}: n {r['n']}, com aviso {r['com_aviso']}, erros {r['erros']} | erro com aviso {a['taxa_erro_com_sinal']} "
              f"sem aviso {a['taxa_erro_sem_sinal']} | RR {a['risco_relativo']} {a['ic95_risco_relativo']} | "
              f"p {a['fisher_p_unilateral']} | E {'SIM' if r['criterio_E'] else 'NÃO'}")
    print(json.dumps(resumo, indent=1, ensure_ascii=False)[:4000])


if __name__ == "__main__":
    main()
