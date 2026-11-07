"""
Reteste com o agrupamento oficial do BRACS. Até 07/11/2026, o projeto colocava o UDH em atípico; no BRACS,
benigno = N, PB, UDH; atípico = FEA, ADH; maligno = DCIS, IC (contagens do artigo e pastas BT/AT/MT do FTP).
O descritor, os negativos e o classificador da lâmina são refeitos com o rótulo certo.

Fixado ANTES de rodar (commit anterior aos resultados):
  Descritores, com o agrupamento oficial:
     D1 "rois": como em lamina_inteira.py.
     D2 "rois+neg": como em negativos_benignos.py; as lâminas N, PB e UDH entre as 79 de treino viram negativos.
  Atributos, logística, treino (79 lâminas) e teste (57): como em classificador_lamina.py. Limiares só no treino,
     por validação cruzada deixando um paciente de fora (LOPO).
  Critérios, nas 57 (todas as comparações usam o rótulo oficial):
     C1: acurácia balanceada nas 4 classes do classificador com D2 > a das previsões antigas do mesmo método
         (negativos_benignos.py, treinado com o agrupamento antigo), repontuadas com o rótulo oficial.
     C2: maligno (DCIS, IC) × resto, com D2: sensibilidade >= 0,90 e especificidade >= 0,40, com o limiar LOPO
         de sensibilidade >= 0,90.
     C3: suspeito (FEA, ADH, DCIS, IC) × benigno, com D2: os mesmos valores de C2.
  Também reportado (sem critério): D1; hierárquico; 3 classes (referência: UNI + ABMIL, 0,687, em outro
     treino e teste); AUC e limiar 0,5 nas versões binárias; intervalo de 95% por bootstrap agrupado por
     paciente; acerto por patch nas RoIs de validação; a mesma tabela para E0, repontuado.
  As 57 lâminas já foram usadas em vários testes; a confirmação depende das 30 de teste ainda não usadas.

Uso (venv do projeto; só CPU):
    .venv/bin/python validacao/rotulo_oficial.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

import classificador_lamina
import negativos_benignos
from comum.lamina import RESULTADOS_DIR
from comum.rois import info_lamina

SAIDA = RESULTADOS_DIR / "rotulo_oficial"
SENS_MIN = 0.90
ESPEC_MIN = 0.40


def tres(c):
    return "maligno" if c in ("DCIS", "IC") else c


def bal_tres(real, pred, stems):
    return round(float(np.mean([np.mean([tres(pred[s]) == c for s in stems if tres(real[s]) == c])
                                for c in ("benigno", "atipico", "maligno")])), 3)


def binaria(A, rot, positivos, treino, teste, pac):
    from decisao_lamina import auc, lopo, prob

    def y(stems):
        return [int(rot[s] in positivos) for s in stems]

    def prever(tr, alvo):
        return {s: float(p[1]) for s, p in zip(alvo, prob(A, tr, y(tr), alvo, 2))}
    cv, p_te = lopo(A, treino, pac, prever), prever(treino, teste)
    pos_cv = [cv[s] for s in treino if rot[s] in positivos]
    limiar = next(t for t in sorted(set(cv.values()), reverse=True) if np.mean([v >= t for v in pos_cv]) >= SENS_MIN)
    pos, neg = [s for s in teste if rot[s] in positivos], [s for s in teste if rot[s] not in positivos]

    def corte(t):
        tp, tn = sum(p_te[s] >= t for s in pos), sum(p_te[s] < t for s in neg)
        return {"limiar": round(t, 4), "sensibilidade": round(tp / len(pos), 3), "especificidade": round(tn / len(neg), 3),
                "positivas_certas": f"{tp}/{len(pos)}", "negativas_certas": f"{tn}/{len(neg)}",
                "acuracia_balanceada": round((tp / len(pos) + tn / len(neg)) / 2, 3), "acertos": f"{tp + tn}/{len(teste)}"}
    r = {"auc_teste": round(auc([p_te[s] for s in pos], [p_te[s] for s in neg]), 3),
         "auc_lopo_treino": round(auc(pos_cv, [cv[s] for s in treino if rot[s] not in positivos]), 3),
         "limiar_lopo": corte(limiar), "limiar_0_5": corte(0.5), "classe_majoritaria": f"{max(len(pos), len(neg))}/{len(teste)}"}
    r["passou"] = r["limiar_lopo"]["sensibilidade"] >= SENS_MIN and r["limiar_lopo"]["especificidade"] >= ESPEC_MIN
    return r


def avaliar(A, real, rot, treino, teste, pac):
    from decisao_lamina import hierarquico
    plano = {s: c for s, (c, _) in classificador_lamina.classificar(A, real, treino, teste).items()}
    m = classificador_lamina.metricas(real, plano, teste)
    h = hierarquico(A, real, treino, teste, pac, m["acuracia_balanceada"])
    return {"classificador": {**m, "acuracia_balanceada_3_classes": bal_tres(real, plano, teste),
                              "ic95": classificador_lamina.bootstrap(real, plano, teste, pac), "por_lamina": plano},
            "hierarquico": {**h["teste_57"], "acuracia_balanceada_3_classes": bal_tres(real, h["por_lamina_teste"], teste),
                            "por_lamina": h["por_lamina_teste"]},
            "maligno_x_resto": binaria(A, rot, {"DCIS", "IC"}, treino, teste, pac),
            "suspeito_x_benigno": binaria(A, rot, {"FEA", "ADH", "DCIS", "IC"}, treino, teste, pac)}


def main():
    from lamina_inteira import classe_final, conferencia_val, dados_descritor_rois, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    dev, val, teste = laminas_dev(), laminas_val(), laminas_teste()
    treino = val + dev
    rot = {s: info_lamina(s)["rotulo"] for s in treino + teste}
    real = {s: classe_final(rot[s]) for s in rot}
    pac = pacientes()
    benignas = [s for s in treino if real[s] == "benigno"]
    # grava em pastas próprias: os atributos antigos foram calculados com o rótulo errado
    classificador_lamina.SAIDA = SAIDA / "rois"
    negativos_benignos.SAIDA = SAIDA / "rois_neg"
    for pasta in (classificador_lamina.SAIDA, negativos_benignos.SAIDA):
        pasta.mkdir(parents=True, exist_ok=True)
    A1 = classificador_lamina.calcular_atributos(dev, val, teste)
    A2 = negativos_benignos.calcular_atributos(dev, val, teste, benignas, pac)

    ler = lambda p: json.loads((RESULTADOS_DIR / p).read_text(encoding="utf-8"))
    antigo = ler("negativos_benignos/resumo.json")["por_lamina_teste"]
    e0 = ler("lamina_inteira/resumo.json")["E0_pipeline_atual"]["predito"]
    ref = {nome: {**classificador_lamina.metricas(real, {s: str(p[s]) for s in teste}, teste),
                  "acuracia_balanceada_3_classes": bal_tres(real, p, teste)}
           for nome, p in (("classificador_neg_antigo_repontuado", antigo), ("E0_repontuado", e0))}
    resumo = {"grupos_teste": {c: sum(real[s] == c for s in teste) for c in ("benigno", "atipico", "DCIS", "IC")},
              "n_negativas": len(benignas), "referencias": ref,
              "D1_rois": avaliar(A1, real, rot, treino, teste, pac), "D2_rois_neg": avaliar(A2, real, rot, treino, teste, pac),
              "conferencia_rois_val_por_patch": {"D1": conferencia_val(dados_descritor_rois()),
                                                 "D2": negativos_benignos.conferencia_rois_val(benignas)}}
    d2 = resumo["D2_rois_neg"]
    resumo["criterios"] = {"C1": d2["classificador"]["acuracia_balanceada"] > ref["classificador_neg_antigo_repontuado"]["acuracia_balanceada"],
                           "C2": d2["maligno_x_resto"]["passou"], "C3": d2["suspeito_x_benigno"]["passou"]}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    print("grupos no teste:", resumo["grupos_teste"], "| negativas:", len(benignas))
    for nome, m in ref.items():
        print(f"{nome:<38} bal4 {m['acuracia_balanceada']:.3f} bal3 {m['acuracia_balanceada_3_classes']:.3f} {m['acertos']}/{m['n']} {m['por_classe']}")
    for d in ("D1_rois", "D2_rois_neg"):
        r = resumo[d]
        print(f"\n{d}\n  classificador bal4 {r['classificador']['acuracia_balanceada']:.3f} bal3 {r['classificador']['acuracia_balanceada_3_classes']:.3f} "
              f"IC95 {r['classificador']['ic95']} {r['classificador']['acertos']}/57 {r['classificador']['por_classe']}")
        print(f"  hierárquico   bal4 {r['hierarquico']['acuracia_balanceada']:.3f} bal3 {r['hierarquico']['acuracia_balanceada_3_classes']:.3f} "
              f"{r['hierarquico']['acertos']} {r['hierarquico']['por_classe']}")
        for b in ("maligno_x_resto", "suspeito_x_benigno"):
            print(f"  {b}: AUC {r[b]['auc_teste']} (LOPO {r[b]['auc_lopo_treino']}) | LOPO {r[b]['limiar_lopo']} | 0,5 {r[b]['limiar_0_5']} | majoritária {r[b]['classe_majoritaria']}")
    print("\nconferência por patch:", resumo["conferencia_rois_val_por_patch"])
    print("Critérios fixados antes:", resumo["criterios"])


if __name__ == "__main__":
    main()
