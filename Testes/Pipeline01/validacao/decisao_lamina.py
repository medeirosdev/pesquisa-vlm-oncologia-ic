"""
Três formas de decidir a lâmina inteira a partir dos mesmos 12 atributos de classificador_lamina.py
(descritor "rois" sobre a amostra de 2.000 patches): triagem binária, abstenção e hierarquia.

Fixado ANTES de rodar (commit anterior aos resultados):
  Dados: atributos de resultados/classificador_lamina/atributos.json; treino nas 79 lâminas (61 de validação
     + 18 de desenvolvimento), teste nas 57 do teste externo. Logística de categoria_uni.logistica_multinomial
     (atributos padronizados, pesos balanceados, L2 equivalente a C=1). Limiares escolhidos só no treino, por
     validação cruzada deixando um paciente de fora (LOPO); nada é escolhido nas 57.
  1) Triagem binária: benigno × "precisa de atenção" (atípico, DCIS ou IC).
     Limiar: o maior limiar de P(atenção) com sensibilidade >= 0,90 nas previsões LOPO do treino.
     Critério de "funcionou": nas 57, sensibilidade >= 0,90 E especificidade >= 0,40.
     (Referência: a pipeline com modelo de linguagem, E0, chamou 55 de 57 lâminas de malignas.)
  2) Abstenção ("não sei") sobre o classificador de 4 classes de classificador_lamina.py: a lâmina vai direto
     ao patologista se a maior probabilidade for menor que t. t = o valor que deixa 60% das lâminas com
     decisão nas previsões LOPO do treino.
     Critério de "funcionou": nas 57, acurácia balanceada das lâminas com decisão > acurácia balanceada de
     todas, com pelo menos 40% das lâminas com decisão.
  3) Hierárquico (sugestão do Prof. João): três logísticas binárias — benigno × não benigno (todas as lâminas
     de treino), atípico × maligno (só as não benignas), DCIS × IC (só as malignas) — aplicadas em cadeia.
     Critério de "funcionou": nas 57, acurácia balanceada nas 4 classes > a do classificador de 4 classes
     de classificador_lamina.py.
  Também reportado (sem critério): AUC da triagem; sensibilidade e especificidade de E0; curva acerto ×
     cobertura nas 57; LOPO no treino pra cada forma; matriz de confusão do hierárquico.

Uso (venv do projeto; só CPU; depois de classificador_lamina.py):
    .venv/bin/python validacao/decisao_lamina.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from comum.lamina import RESULTADOS_DIR
from comum.rois import info_lamina

SENS_MIN = 0.90
ESPEC_MIN = 0.40
COBERTURA_ALVO = 0.60
COBERTURA_MIN = 0.40
SAIDA = RESULTADOS_DIR / "decisao_lamina"


def prob(A, treino, y, alvo, k):
    from categoria_uni import logistica_multinomial
    return logistica_multinomial(np.array([A[s] for s in treino]), np.array(y), np.array([A[s] for s in alvo]),
                                 k=k, probabilidades=True)


def lopo(A, treino, pac, prever):
    """Previsões deixando um paciente de fora: prever(treino_sem_p, slides_de_p) -> {s: valor}."""
    saida = {}
    for p in sorted({pac[s] for s in treino}):
        fora = [s for s in treino if pac[s] == p]
        saida.update(prever([s for s in treino if pac[s] != p], fora))
    return saida


def auc(pos, neg):
    return float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg]))


# ---------- 1) triagem ----------
def triagem(A, real, treino, teste, pac, e0):
    def prever(tr, alvo):
        P = prob(A, tr, [int(real[s] != "benigno") for s in tr], alvo, 2)
        return {s: float(p[1]) for s, p in zip(alvo, P)}
    cv = lopo(A, treino, pac, prever)
    pos_cv = [cv[s] for s in treino if real[s] != "benigno"]
    candidatos = sorted(set(cv.values()), reverse=True)
    limiar = next(t for t in candidatos if np.mean([v >= t for v in pos_cv]) >= SENS_MIN)
    p_te = prever(treino, teste)

    def sens_espec(pred_atencao, stems):
        pos = [s for s in stems if real[s] != "benigno"]
        neg = [s for s in stems if real[s] == "benigno"]
        return {"sensibilidade": round(float(np.mean([pred_atencao[s] for s in pos])), 3),
                "especificidade": round(float(np.mean([not pred_atencao[s] for s in neg])), 3),
                "atencao_certas": f"{sum(pred_atencao[s] for s in pos)}/{len(pos)}",
                "benignas_certas": f"{sum(not pred_atencao[s] for s in neg)}/{len(neg)}"}
    r = {"limiar": round(limiar, 4),
         "lopo_treino": sens_espec({s: cv[s] >= limiar for s in treino}, treino),
         "teste_57": sens_espec({s: p_te[s] >= limiar for s in teste}, teste),
         "auc_teste_57": round(auc([p_te[s] for s in teste if real[s] != "benigno"],
                                   [p_te[s] for s in teste if real[s] == "benigno"]), 3),
         "E0_teste_57": sens_espec({s: e0[s] not in ("benigno", None) for s in teste}, teste),
         "por_lamina_teste": {s: round(p_te[s], 3) for s in teste}}
    t = r["teste_57"]
    r["funcionou"] = t["sensibilidade"] >= SENS_MIN and t["especificidade"] >= ESPEC_MIN
    return r


# ---------- 2) abstenção ----------
def abstencao(A, real, treino, teste, pac):
    from lamina_inteira import FINAIS, acuracia_balanceada

    def prever(tr, alvo):
        P = prob(A, tr, [FINAIS.index(real[s]) for s in tr], alvo, 4)
        return {s: (FINAIS[int(p.argmax())], float(p.max())) for s, p in zip(alvo, P)}
    cv = lopo(A, treino, pac, prever)
    t = float(np.quantile([c for _, c in cv.values()], 1 - COBERTURA_ALVO))
    te = prever(treino, teste)

    def resumo(saida, stems, limiar):
        aceitas = [s for s in stems if saida[s][1] >= limiar]
        ba = lambda ss: round(acuracia_balanceada([real[s] for s in ss], [saida[s][0] for s in ss]), 3) if ss else None
        return {"cobertura": round(len(aceitas) / len(stems), 3), "n_com_decisao": len(aceitas),
                "acuracia_balanceada_com_decisao": ba(aceitas), "acuracia_balanceada_todas": ba(stems),
                "acertos_com_decisao": f"{sum(saida[s][0] == real[s] for s in aceitas)}/{len(aceitas)}",
                "classes_reais_com_decisao": dict(Counter(real[s] for s in aceitas))}
    r = {"limiar": round(t, 4), "lopo_treino": resumo(cv, treino, t), "teste_57": resumo(te, teste, t)}
    confs = sorted((c for _, c in te.values()), reverse=True)
    r["curva_teste_57"] = {f"{int(100 * f)}%": resumo(te, teste, confs[max(int(round(f * len(teste))) - 1, 0)])
                           for f in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)}
    m = r["teste_57"]
    r["funcionou"] = (m["cobertura"] >= COBERTURA_MIN and m["acuracia_balanceada_com_decisao"] is not None
                      and m["acuracia_balanceada_com_decisao"] > m["acuracia_balanceada_todas"])
    return r


# ---------- 3) hierárquico ----------
def hierarquico(A, real, treino, teste, pac, ba_plano):
    from lamina_inteira import FINAIS, acuracia_balanceada

    def prever(tr, alvo):
        nb = [s for s in tr if real[s] != "benigno"]
        mal = [s for s in tr if real[s] in ("DCIS", "IC")]
        p1 = prob(A, tr, [int(real[s] != "benigno") for s in tr], alvo, 2)
        p2 = prob(A, nb, [int(real[s] != "atipico") for s in nb], alvo, 2)
        p3 = prob(A, mal, [int(real[s] == "IC") for s in mal], alvo, 2)
        return {s: "benigno" if a[1] < 0.5 else ("atipico" if b[1] < 0.5 else ("IC" if c[1] >= 0.5 else "DCIS"))
                for s, a, b, c in zip(alvo, p1, p2, p3)}
    cv = lopo(A, treino, pac, prever)
    te = prever(treino, teste)

    def resumo(pred, stems):
        r, p = [real[s] for s in stems], [pred[s] for s in stems]
        return {"acuracia_balanceada": round(acuracia_balanceada(r, p), 3), "acertos": f"{sum(a == b for a, b in zip(r, p))}/{len(stems)}",
                "por_classe": {c: f"{sum(a == b == c for a, b in zip(r, p))}/{r.count(c)}" for c in FINAIS},
                "confusao": {c: dict(Counter(b for a, b in zip(r, p) if a == c)) for c in FINAIS}}
    r = {"lopo_treino": resumo(cv, treino), "teste_57": resumo(te, teste), "acuracia_balanceada_plano_57": ba_plano,
         "por_lamina_teste": te}
    r["funcionou"] = r["teste_57"]["acuracia_balanceada"] > ba_plano
    return r


def main():
    from classificador_lamina import SAIDA as SAIDA_CLASSIFICADOR
    from lamina_inteira import classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    SAIDA.mkdir(parents=True, exist_ok=True)
    A = json.loads((SAIDA_CLASSIFICADOR / "atributos.json").read_text(encoding="utf-8"))
    plano = json.loads((SAIDA_CLASSIFICADOR / "resumo.json").read_text(encoding="utf-8"))
    treino, teste = laminas_val() + laminas_dev(), laminas_teste()
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in treino + teste}
    pac = pacientes()
    e0 = json.loads((RESULTADOS_DIR / "prelaudo_teste_externo.json").read_text(encoding="utf-8"))
    e0 = {s: e0[f"{s}|v2"]["predito"] for s in teste}

    resumo = {"triagem": triagem(A, real, treino, teste, pac, e0),
              "abstencao": abstencao(A, real, treino, teste, pac),
              "hierarquico": hierarquico(A, real, treino, teste, pac, plano["teste_57"]["acuracia_balanceada"])}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    t = resumo["triagem"]
    print(f"TRIAGEM  limiar {t['limiar']} | LOPO treino {t['lopo_treino']}\n  teste 57: {t['teste_57']} | AUC {t['auc_teste_57']}"
          f"\n  E0: {t['E0_teste_57']}\n  critério (sens >= {SENS_MIN} e espec >= {ESPEC_MIN}): {'SIM' if t['funcionou'] else 'NÃO'}")
    a = resumo["abstencao"]
    print(f"ABSTENÇÃO  limiar {a['limiar']} | LOPO treino {a['lopo_treino']}\n  teste 57: {a['teste_57']}")
    for k, v in a["curva_teste_57"].items():
        print(f"    cobertura {k}: bal {v['acuracia_balanceada_com_decisao']} ({v['acertos_com_decisao']})")
    print(f"  critério (bal com decisão > bal todas, cobertura >= {COBERTURA_MIN}): {'SIM' if a['funcionou'] else 'NÃO'}")
    h = resumo["hierarquico"]
    print(f"HIERÁRQUICO  LOPO treino {h['lopo_treino']['acuracia_balanceada']} {h['lopo_treino']['por_classe']}"
          f"\n  teste 57: {h['teste_57']['acuracia_balanceada']} {h['teste_57']['acertos']} {h['teste_57']['por_classe']}"
          f"\n  confusão: {h['teste_57']['confusao']}\n  critério (> plano {h['acuracia_balanceada_plano_57']}): "
          f"{'SIM' if h['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
