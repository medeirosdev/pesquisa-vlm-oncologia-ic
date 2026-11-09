"""
O MIL com atenção (mil_atencao.py) em validação cruzada nas 79 lâminas de treino: uma segunda estimativa, que não
usa as 57 lâminas do teste externo (já usadas em vários testes).

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelo, treino, épocas e sementes: exatamente os de mil_atencao.py, sem mudança.
  Divisão: 5 partes por paciente (pacientes ordenados por nome e embaralhados com semente 0, distribuídos em rodízio);
     cada lâmina é prevista pelo modelo treinado nas outras 4 partes.
  Comparação: o classificador da lâmina com negativos (rotulo_oficial.py, atributos D2), na mesma divisão.
     Os atributos D2 das lâminas de treino já vêm de um descritor treinado sem os negativos do paciente da lâmina.
  Métricas nas 79: acurácia balanceada nas 4 classes; AUC benigno × atípico (51 lâminas); AUC maligno × resto.
  Critério de "funcionou": acurácia balanceada do MIL >= 0,55 E AUC benigno × atípico do MIL >= 0,70.
  Também reportado (sem critério): as mesmas métricas do classificador com negativos; acerto por classe.

Uso (venv do projeto; GPU se houver):
    .venv/bin/python validacao/mil_validacao_cruzada.py
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np
import torch

from comum.lamina import RESULTADOS_DIR
from comum.rois import info_lamina

N_PARTES = 5
BA_MIN = 0.55
AUC_MIN = 0.70
SAIDA = RESULTADOS_DIR / "mil_validacao_cruzada"


def metricas(real, probs, stems):
    from lamina_inteira import FINAIS, acuracia_balanceada
    from mil_atencao import auc
    pred = {s: FINAIS[int(np.argmax(probs[s]))] for s in stems}
    ba_ = [s for s in stems if real[s] in ("benigno", "atipico")]
    razao = {s: probs[s][1] / (probs[s][0] + probs[s][1]) for s in ba_}
    mal = {s: probs[s][2] + probs[s][3] for s in stems}
    r = [real[s] for s in stems]
    return {"acuracia_balanceada": round(acuracia_balanceada(r, [pred[s] for s in stems]), 3),
            "acertos": f"{sum(real[s] == pred[s] for s in stems)}/{len(stems)}",
            "por_classe": {c: f"{sum(real[s] == pred[s] == c for s in stems)}/{r.count(c)}" for c in FINAIS},
            "auc_benigno_x_atipico": round(auc([razao[s] for s in ba_ if real[s] == "atipico"], [razao[s] for s in ba_ if real[s] == "benigno"]), 3),
            "auc_maligno_x_resto": round(auc([mal[s] for s in stems if real[s] in ("DCIS", "IC")], [mal[s] for s in stems if real[s] not in ("DCIS", "IC")]), 3)}


def main():
    from categoria_uni import logistica_multinomial
    from lamina_inteira import FINAIS, amostra, classe_final, laminas_dev
    from mil_atencao import SEMENTES, treinar
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    SAIDA.mkdir(parents=True, exist_ok=True)
    treino = laminas_val() + laminas_dev()
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in treino}
    pac = pacientes()
    lista = sorted({pac[s] for s in treino})
    random.Random(0).shuffle(lista)
    parte = {p: i % N_PARTES for i, p in enumerate(lista)}
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    X = {s: torch.from_numpy(amostra(s)) for s in treino}
    A = json.loads((RESULTADOS_DIR / "rotulo_oficial" / "rois_neg" / "atributos.json").read_text(encoding="utf-8"))

    p_mil, p_clf = {}, {}
    for k in range(N_PARTES):
        tr = [s for s in treino if parte[pac[s]] != k]
        te = [s for s in treino if parte[pac[s]] == k]
        y = np.array([FINAIS.index(real[s]) for s in tr])
        soma = {s: np.zeros(4) for s in te}
        for semente in SEMENTES:
            modelo = treinar([X[s] for s in tr], y, semente, dispositivo)
            modelo.eval()
            with torch.no_grad():
                for s in te:
                    soma[s] += torch.softmax(modelo(X[s].to(dispositivo))[0], 0).cpu().numpy() / len(SEMENTES)
        p_mil.update(soma)
        P = logistica_multinomial(np.array([A[s] for s in tr]), y, np.array([A[s] for s in te]), k=4, probabilidades=True)
        p_clf.update(dict(zip(te, P)))
        print(f"  parte {k + 1}/{N_PARTES}: {len(te)} lâminas", flush=True)

    resumo = {"mil": metricas(real, p_mil, treino), "classificador_negativos": metricas(real, p_clf, treino),
              "laminas_por_parte": [sum(parte[pac[s]] == k for s in treino) for k in range(N_PARTES)]}
    m = resumo["mil"]
    resumo["funcionou"] = m["acuracia_balanceada"] >= BA_MIN and m["auc_benigno_x_atipico"] >= AUC_MIN
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for nome in ("mil", "classificador_negativos"):
        print(f"{nome:<24} {resumo[nome]}")
    print(f"Critério fixado antes (MIL: bal >= {BA_MIN} e AUC benigno × atípico >= {AUC_MIN}): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
