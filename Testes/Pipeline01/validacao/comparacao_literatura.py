"""
Comparação com os números publicados no BRACS e repetição exploratória da triagem e do hierárquico com o
descritor "rois+neg" (negativos_benignos.py). Sem critério fixado: só reporta.

Referência (acurácia balanceada, lâmina inteira, ABMIL; 395 lâminas de treino, 87 de teste oficial):
UNI, Chen et al., Nature Medicine 2024, Extended Data Tables 19 e 20: 0,687 em 3 classes e 0,468 em 7 classes.
Aqui: 79 lâminas de treino, 57 das 87 de teste, 3 classes = benigno, atípico, maligno (DCIS + IC).

Uso (venv do projeto; só CPU):
    .venv/bin/python validacao/comparacao_literatura.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from comum.lamina import RESULTADOS_DIR
from comum.rois import info_lamina

SAIDA = RESULTADOS_DIR / "comparacao_literatura.json"


def tres_classes(c):
    return "maligno" if c in ("DCIS", "IC") else c


def bal3(real, pred, stems):
    por = []
    for c in ("benigno", "atipico", "maligno"):
        ss = [s for s in stems if tres_classes(real[s]) == c]
        por.append(np.mean([tres_classes(pred[s]) == c for s in ss]))
    return round(float(np.mean(por)), 3)


def main():
    from decisao_lamina import hierarquico, triagem
    from classificador_lamina import classificar
    from lamina_inteira import classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    ler = lambda p: json.loads((RESULTADOS_DIR / p).read_text(encoding="utf-8"))
    treino, teste = laminas_val() + laminas_dev(), laminas_teste()
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in treino + teste}
    pac = pacientes()
    li = ler("lamina_inteira/resumo.json")
    A_rois = ler("classificador_lamina/atributos.json")
    A_neg = ler("negativos_benignos/atributos.json")
    plano = {s: c for s, (c, _) in classificar(A_rois, real, treino, teste).items()}
    plano_neg = {s: c for s, (c, _) in classificar(A_neg, real, treino, teste).items()}
    e0 = {s: li["E0_pipeline_atual"]["predito"][s] for s in teste}
    ba_neg = ler("negativos_benignos/resumo.json")["teste_57"]["acuracia_balanceada"]
    hier_neg = hierarquico(A_neg, real, treino, teste, pac, ba_neg)
    tri_neg = triagem(A_neg, real, treino, teste, pac, e0)
    metodos = {"E0 modelo de linguagem decide": e0, "E1 regra, descritor atual": li["E1_atual"]["predito"],
               "E2 regra, descritor rois": li["E2_rois"]["predito"], "classificador 4 classes (rois)": plano,
               "hierárquico (rois)": ler("decisao_lamina/resumo.json")["hierarquico"]["por_lamina_teste"],
               "classificador 4 classes (rois+neg)": plano_neg, "hierárquico (rois+neg), exploratório": hier_neg["por_lamina_teste"]}
    resumo = {"acuracia_balanceada_3_classes_57": {n: bal3(real, p, teste) for n, p in metodos.items()},
              "referencia_UNI_ABMIL": {"3_classes": 0.687, "7_classes": 0.468},
              "exploratorio_rois_neg": {"triagem": {k: tri_neg[k] for k in ("limiar", "lopo_treino", "teste_57", "auc_teste_57")},
                                        "hierarquico": {k: hier_neg[k] for k in ("lopo_treino", "teste_57")}}}
    SAIDA.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
