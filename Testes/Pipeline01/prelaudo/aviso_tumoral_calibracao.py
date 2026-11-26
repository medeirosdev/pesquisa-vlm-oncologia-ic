"""
Duas perguntas da revisão sobre os dados entregues ao médico.

(1) Aviso tumoral × aviso de tecido normal. Uma região de pulmão normal numa lâmina de adenocarcinoma (ou benigna numa
biópsia com câncer) é esperada e pode não contradizer o diagnóstico; uma região do outro tipo de tumor contradiz.
Os erros do MIL se concentram nos avisos tumorais?
(2) Calibração da confiança. A confiança do laudo (alta >= 0,70, moderada >= 0,50) vem da probabilidade média das 5
sementes, sem calibrar. Quão calibrada ela é, e quanto muda com escala de temperatura?

Fixado ANTES de rodar (commit anterior aos resultados):
  Dados: os mesmos de aviso_linhas_base.py. Pulmão: 197 lâminas da divisão por centro (pulmao_centro/por_lamina.json,
     regiões e probabilidades fora da amostra). Próstata: 300 biópsias de teste, GAT-MIL padronizado, execução 0 de
     panda_repeticoes.py; regiões e classes como em aviso_linhas_base.prostata.
  (1) Aviso tumoral: pelo menos uma região discordante é do outro tipo de tumor (pulmão: escamoso numa lâmina prevista
     como adenocarcinoma ou o contrário; próstata: padrão de Gleason numa biópsia prevista como ISUP 0). Aviso não
     tumoral: todas as regiões discordantes são tecido não tumoral (pulmão normal; benigno numa biópsia prevista como
     ISUP >= 1). Erro: como em aviso_linhas_base (tipo errado; câncer × benigno trocado).
     Critério T (pulmão): taxa de erro nas lâminas com aviso tumoral maior que nas lâminas com aviso só não tumoral,
        Fisher unilateral p < 0,05.
     Na próstata, aviso tumoral só existe nas previstas como ISUP 0 e não tumoral só nas previstas como ISUP >= 1, então
        a comparação se confunde com a classe prevista: reportada sem critério.
     Também reportado: número de lâminas e erros em cada grupo; AUROC para achar erro do número de regiões
        discordantes tumorais e do número de regiões não tumorais.
  (2) Calibração, descritiva (sem critério): confiança = probabilidade da classe prevista. ECE com 10 faixas iguais de
     confiança; taxa de acerto e número de lâminas por faixa do laudo (alta >= 0,70; moderada 0,50 a 0,70; baixa
     < 0,50). Escala de temperatura ajustada por máxima verossimilhança com validação cruzada (pulmão: as 5 partes por
     centro, ajuste em 4 e aplicação na 5ª; próstata: 5 partes estratificadas pelo grau real, semente 0, dentro do
     próprio teste, porque não há validação separada do Karolinska; isso é transdutivo e fica marcado). Probabilidades
     com piso de 1e-6 antes do logaritmo. Mesmas medidas depois de calibrar.
  Correção antes de rodar: no pulmão, as classes das regiões estão gravadas com os códigos do descritor ("nor", "aca",
     "scc"), não com os nomes por extenso; a primeira versão comparava com os nomes. Nada mais mudou.
  Limites conhecidos: a temperatura não muda a ordem das lâminas, então não muda AUROC nem risco-cobertura; na
     próstata a calibração usa o próprio centro de teste.

Uso (venv do projeto): .venv/bin/python prelaudo/aviso_tumoral_calibracao.py
Saída: resultados/aviso_tumoral_calibracao/resumo.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "aviso_tumoral_calibracao"
P_MAX = 0.05
PISO = 1e-6


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    return round(float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum())
                       / (len(pos) * len(neg))), 3)


def dados_pulmao():
    por = json.loads((RESULTADOS_DIR / "pulmao_centro" / "por_lamina.json").read_text(encoding="utf-8"))
    out = []
    for d in por.values():
        tipo = "scc" if d["previsto"] == 1 else "aca"   # códigos do descritor (pulmao_descritor.CLASSES)
        outro = "aca" if d["previsto"] == 1 else "scc"
        disc = [c for c in d["regioes"] if c != tipo]
        p = np.array([1 - d["p_lusc"], d["p_lusc"]])
        out.append({"tumoral": sum(c == outro for c in disc), "nao_tumoral": sum(c == "nor" for c in disc),
                    "erro": d["previsto"] != d["real"], "probs": p, "real": d["real"], "parte": d["parte"]})
    return out


def dados_prostata():
    from panda_descritor_prelaudo import CLASSES, N_REGIOES, SAIDA as SAIDA_PANDA, carregar
    from panda_mil import biopsias
    from tcga_descritor_prelaudo import gate_um
    pasta = RESULTADOS_DIR / "panda_repeticoes"
    r0 = json.loads((pasta / "gat_padronizado_r0.json").read_text(encoding="utf-8"))
    _, prontas = biopsias()
    out = []
    for l in [x for x in prontas if x["conjunto"] == "teste"]:
        i = l["image_id"]
        d = r0[i]
        g = d["previsto"]
        meta, xy, _ = carregar(l)
        P = np.load(SAIDA_PANDA / f"{i}_descritor.npy")
        att = np.load(pasta / f"{i}_atencao.npy")
        lado = meta["lado_px"]
        ps = [{"cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a), "classe": CLASSES[int(q.argmax())]}
              for (x, y), q, a in zip(xy, P, att)]
        reg = gate_um(sorted(ps, key=lambda t: -t["atencao"]), meta["mpp"], N_REGIOES)
        tum = sum(c["classe"] != "benigno" for c in reg) if g == 0 else 0
        nao = sum(c["classe"] == "benigno" for c in reg) if g >= 1 else 0
        out.append({"tumoral": tum, "nao_tumoral": nao, "erro": (g == 0) != (d["real"] == 0),
                    "probs": np.array(d["probs"]), "real": d["real"]})
    return out


def aviso_tumoral(v):
    from scipy.stats import fisher_exact
    tum = np.array([x["tumoral"] > 0 for x in v])
    nao = np.array([x["tumoral"] == 0 and x["nao_tumoral"] > 0 for x in v])
    e = np.array([x["erro"] for x in v])
    a, b, c, d = int((tum & e).sum()), int((tum & ~e).sum()), int((nao & e).sum()), int((nao & ~e).sum())
    p = float(fisher_exact([[a, b], [c, d]], alternative="greater")[1]) if (a + b) and (c + d) else None
    nt = np.array([x["tumoral"] for x in v], float)
    nn = np.array([x["nao_tumoral"] for x in v], float)
    return {"com_aviso_tumoral": {"laminas": a + b, "erros": a, "taxa_erro": round(a / max(a + b, 1), 3)},
            "com_aviso_so_nao_tumoral": {"laminas": c + d, "erros": c, "taxa_erro": round(c / max(c + d, 1), 3)},
            "sem_aviso": {"laminas": int((~tum & ~nao).sum()), "erros": int((~tum & ~nao & e).sum())},
            "fisher_p_unilateral": None if p is None else round(p, 4),
            "auroc_regioes_tumorais": auc(nt[e], nt[~e]), "auroc_regioes_nao_tumorais": auc(nn[e], nn[~e]),
            "criterio_T_condicao": bool(p is not None and a / max(a + b, 1) > c / max(c + d, 1) and p < P_MAX)}


def ece(conf, acerto, n_faixas=10):
    bordas = np.linspace(0, 1, n_faixas + 1)
    tot = 0.0
    for lo, hi in zip(bordas[:-1], bordas[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if m.any():
            tot += m.mean() * abs(acerto[m].mean() - conf[m].mean())
    return round(float(tot), 4)


def faixas(conf, acerto):
    out = {}
    for nome, m in [("alta", conf >= 0.70), ("moderada", (conf >= 0.50) & (conf < 0.70)), ("baixa", conf < 0.50)]:
        out[nome] = {"laminas": int(m.sum()), "acerto": round(float(acerto[m].mean()), 3) if m.any() else None}
    return out


def temperatura(logp, y):
    from scipy.optimize import minimize_scalar

    def nll(t):
        z = logp / t
        z = z - z.max(1, keepdims=True)
        return -float((z[np.arange(len(y)), y] - np.log(np.exp(z).sum(1))).mean())
    return float(minimize_scalar(nll, bounds=(0.05, 20.0), method="bounded").x)


def calibrar(v, partes):
    P = np.stack([x["probs"] for x in v])
    y = np.array([x["real"] for x in v])
    logp = np.log(np.clip(P, PISO, 1))
    Pc, ts = np.zeros_like(P), []
    for k in sorted(set(partes)):
        te, tr = partes == k, partes != k
        t = temperatura(logp[tr], y[tr])
        ts.append(round(t, 3))
        z = logp[te] / t
        z = np.exp(z - z.max(1, keepdims=True))
        Pc[te] = z / z.sum(1, keepdims=True)
    out = {}
    for nome, Q in [("antes", P), ("depois", Pc)]:
        pred = Q.argmax(1)
        conf, acerto = Q.max(1), (pred == y).astype(float)
        out[nome] = {"ece": ece(conf, acerto), "confianca_media": round(float(conf.mean()), 3),
                     "acerto_medio": round(float(acerto.mean()), 3), "faixas": faixas(conf, acerto)}
    out["temperaturas_por_parte"] = ts
    return out


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    vp, vq = dados_pulmao(), dados_prostata()
    rng = np.random.default_rng(0)
    yq = np.array([x["real"] for x in vq])
    partes_q = np.zeros(len(vq), int)
    for g in np.unique(yq):
        idx = rng.permutation(np.where(yq == g)[0])
        partes_q[idx] = np.arange(len(idx)) % 5
    res = {"pulmao": {"aviso": aviso_tumoral(vp), "calibracao": calibrar(vp, np.array([x["parte"] for x in vp]))},
           "prostata": {"aviso": aviso_tumoral(vq), "calibracao": calibrar(vq, partes_q),
                        "observacao": "aviso tumoral só nas previstas como ISUP 0; calibração transdutiva no Karolinska"}}
    res["criterio_T"] = res["pulmao"]["aviso"]["criterio_T_condicao"]
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"T {'SIM' if res['criterio_T'] else 'NÃO'}")


if __name__ == "__main__":
    main()
