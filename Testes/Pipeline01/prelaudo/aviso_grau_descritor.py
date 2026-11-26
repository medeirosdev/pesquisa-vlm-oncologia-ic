"""
Duas perguntas da revisão sobre os dados entregues ao médico na próstata e no pulmão.

(1) Aviso por grau (revisão D1). A regra atual da próstata só compara benigno com Gleason: uma biópsia prevista como
ISUP 5 com três regiões Gleason 3 não gera aviso. Um aviso por padrão incompatível com o grau marca os erros de grau?
(2) Proporções do classificador de patches (revisão D5). O laudo traz a proporção de cada padrão entre os patches; como
essa proporção se distribui pela classe real?

Fixado ANTES de rodar (commit anterior aos resultados):
  Próstata: as 300 biópsias de teste, GAT-MIL padronizado, execução 0 de panda_repeticoes.py; regiões e classes do
     classificador de patches como em aviso_linhas_base.prostata.
  (1) Aviso de grau, nas biópsias previstas como ISUP >= 1: alguma das 3 regiões tem um padrão incompatível com o grau
     previsto pela definição do ISUP: ISUP 1 (3+3) com região Gleason 4 ou 5; ISUP 2 e 3 (3+4, 4+3) com região
     Gleason 5; ISUP 5 (4+5, 5+4, 5+5) com região Gleason 3; ISUP 4 (4+4, 3+5, 5+3) nunca.
     Erro de grau: ISUP previsto diferente do real.
     Critério G: nas previstas como ISUP >= 1, taxa de erro de grau maior com aviso de grau que sem, Fisher unilateral
        p < 0,05.
     Também reportado: o mesmo para erro de 2 ou mais graus; a diferença média real − previsto com aviso "para cima"
        (padrão mais alto que o grau: ISUP 1 com Gleason 4/5, ISUP 2-3 com Gleason 5) e "para baixo" (ISUP 5 com
        Gleason 3); número de biópsias com aviso por grau previsto.
  (2) Proporções, descritivo: pulmão, as 197 lâminas (pulmao_centro/<id>_descritor.npy): mediana da proporção de cada
     classe do classificador de patches (normal, adenocarcinoma, escamoso) por tipo real, e fração de lâminas em que a
     classe tumoral mais frequente é o tipo real; próstata, as 300 de teste (panda_prelaudo/<id>_descritor.npy):
     mediana da proporção de benigno, Gleason 3, 4 e 5 por ISUP real.
  Limites conhecidos: o classificador de patches da próstata ficou abaixo do critério (AUC 0,775) e o Karolinska não
     tem o padrão de Gleason por região, então o padrão de cada região não pode ser conferido.

Uso (venv do projeto): .venv/bin/python prelaudo/aviso_grau_descritor.py
Saída: resultados/aviso_grau_descritor/resumo.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "aviso_grau_descritor"
P_MAX = 0.05
INCOMPATIVEL = {1: {"gleason4", "gleason5"}, 2: {"gleason5"}, 3: {"gleason5"}, 4: set(), 5: {"gleason3"}}


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
        meta, xy, _ = carregar(l)
        P = np.load(SAIDA_PANDA / f"{i}_descritor.npy")
        att = np.load(pasta / f"{i}_atencao.npy")
        lado = meta["lado_px"]
        ps = [{"cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a), "classe": CLASSES[int(q.argmax())]}
              for (x, y), q, a in zip(xy, P, att)]
        reg = [c["classe"] for c in gate_um(sorted(ps, key=lambda t: -t["atencao"]), meta["mpp"], N_REGIOES)]
        prop = np.bincount(P.argmax(1), minlength=len(CLASSES)) / len(P)
        out.append({"real": int(d["real"]), "prev": int(d["previsto"]), "regioes": reg, "prop": prop})
    return out, CLASSES


def aviso_grau(v):
    from scipy.stats import fisher_exact
    sel = [x for x in v if x["prev"] >= 1]
    av = np.array([bool(set(x["regioes"]) & INCOMPATIVEL[x["prev"]]) for x in sel])
    e1 = np.array([x["prev"] != x["real"] for x in sel])
    e2 = np.array([abs(x["prev"] - x["real"]) >= 2 for x in sel])

    def tab(e):
        a, b, c, d = int((av & e).sum()), int((av & ~e).sum()), int((~av & e).sum()), int((~av & ~e).sum())
        p = float(fisher_exact([[a, b], [c, d]], alternative="greater")[1]) if (a + b) and (c + d) else None
        return {"com_aviso": f"{a}/{a + b}", "sem_aviso": f"{c}/{c + d}", "taxa_com": round(a / max(a + b, 1), 3),
                "taxa_sem": round(c / max(c + d, 1), 3), "fisher_p_unilateral": None if p is None else round(p, 4)}
    cima = [x["real"] - x["prev"] for x, a in zip(sel, av) if a and x["prev"] <= 3]
    baixo = [x["real"] - x["prev"] for x, a in zip(sel, av) if a and x["prev"] == 5]
    por_grau = {g: f"{int(sum(a for x, a in zip(sel, av) if x['prev'] == g))}/{sum(x['prev'] == g for x in sel)}"
                for g in range(1, 6)}
    t1 = tab(e1)
    return {"n_previstas_isup1_ou_mais": len(sel), "com_aviso_de_grau": int(av.sum()), "por_grau_previsto": por_grau,
            "erro_de_grau": t1, "erro_de_2_ou_mais_graus": tab(e2),
            "real_menos_previsto_aviso_para_cima": {"n": len(cima), "media": round(float(np.mean(cima)), 2) if cima else None},
            "real_menos_previsto_aviso_para_baixo": {"n": len(baixo), "media": round(float(np.mean(baixo)), 2) if baixo else None},
            "criterio_G": bool(t1["fisher_p_unilateral"] is not None and t1["taxa_com"] > t1["taxa_sem"]
                               and t1["fisher_p_unilateral"] < P_MAX)}


def proporcoes_prostata(v, classes):
    return {f"ISUP {g}": {c: round(float(np.median([x["prop"][k] for x in v if x["real"] == g])), 3)
                          for k, c in enumerate(classes)} for g in range(6)}


def proporcoes_pulmao():
    from pulmao_descritor import CLASSES
    por = json.loads((RESULTADOS_DIR / "pulmao_centro" / "por_lamina.json").read_text(encoding="utf-8"))
    out = {}
    for real, nome in ((0, "LUAD"), (1, "LUSC")):
        props, certo = [], 0
        for k, d in por.items():
            if d["real"] != real:
                continue
            P = np.load(RESULTADOS_DIR / "pulmao_centro" / f"{k}_descritor.npy")
            p = np.bincount(P.argmax(1), minlength=len(CLASSES)) / len(P)
            props.append(p)
            tum = {"aca": p[CLASSES.index("aca")], "scc": p[CLASSES.index("scc")]}
            certo += max(tum, key=tum.get) == ("aca" if real == 0 else "scc")
        props = np.array(props)
        out[nome] = {"n": len(props), **{c: round(float(np.median(props[:, i])), 3) for i, c in enumerate(CLASSES)},
                     "tumoral_mais_frequente_e_o_tipo_real": f"{certo}/{len(props)}"}
    return out


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    v, classes = dados_prostata()
    res = {"aviso_de_grau": aviso_grau(v), "proporcoes_prostata_por_isup_real": proporcoes_prostata(v, classes),
           "proporcoes_pulmao_por_tipo_real": proporcoes_pulmao()}
    res["criterio_G"] = res["aviso_de_grau"]["criterio_G"]
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"G {'SIM' if res['criterio_G'] else 'NÃO'}")


if __name__ == "__main__":
    main()
