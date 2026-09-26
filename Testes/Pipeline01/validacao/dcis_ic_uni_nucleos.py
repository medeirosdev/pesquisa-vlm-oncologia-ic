"""
Plano UNI2-h, teste 3: UNI2-h + medida dos núcleos juntos no DCIS vs. IC. Um complementa o outro?

Fixado ANTES de rodar (commit anterior aos resultados):
  - Tiles e lâminas: os mesmos dos testes 1 e do CellViT (BRACS_748, BRACS_773, BRACS_295).
  - Combinação por stacking, sem usar a lâmina de teste no treino:
      1. nas 2 lâminas de treino, a logística do UNI2-h (a do teste 1) é treinada numa e dá a
         pontuação (logit) na outra, e vice-versa — cada tile de treino recebe uma pontuação
         de um modelo que não o viu;
      2. uma logística de 2 entradas [logit do UNI2-h, fração de neoplásicos encostados em
         conjuntivo] é treinada nessas pontuações;
      3. na lâmina de teste: UNI2-h treinado nas 2 lâminas -> logit -> logística de 2 entradas.
  - Critério de "funcionou": AUC da combinação > AUC do UNI2-h sozinho nas TRÊS lâminas.
  - Descritivo: correlação entre o logit do UNI2-h e a medida dos núcleos na lâmina de teste
    (se for alta, um não tem o que acrescentar ao outro).

Uso (venv do projeto):
    .venv/bin/python validacao/dcis_ic_uni_nucleos.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from comum.lamina import RESULTADOS_DIR
from dcis_ic_nucleos import LAMINAS, auc
from dcis_ic_uni import dados, logistica_prob_ic


def main():
    D = {s: dados(s) for s in LAMINAS}
    resumo = {}
    for s in LAMINAS:
        a, b = [o for o in LAMINAS if o != s]
        # 1. pontuações fora da amostra nas lâminas de treino
        logit_a = logistica_prob_ic(D[b]["uni2h"], D[b]["y"], D[a]["uni2h"])
        logit_b = logistica_prob_ic(D[a]["uni2h"], D[a]["y"], D[b]["uni2h"])
        X2_tr = np.column_stack([np.concatenate([logit_a, logit_b]),
                                 np.concatenate([D[a]["nucleos"], D[b]["nucleos"]])])
        y_tr = np.concatenate([D[a]["y"], D[b]["y"]])
        # 3. lâmina de teste
        logit_s = logistica_prob_ic(np.concatenate([D[a]["uni2h"], D[b]["uni2h"]]), y_tr, D[s]["uni2h"])
        comb = logistica_prob_ic(X2_tr, y_tr, np.column_stack([logit_s, D[s]["nucleos"]]))
        y = D[s]["y"]
        resumo[s] = {"uni2h": auc(logit_s[y == 1], logit_s[y == 0]),
                     "nucleos": auc(D[s]["nucleos"][y == 1], D[s]["nucleos"][y == 0]),
                     "combinacao": auc(comb[y == 1], comb[y == 0]),
                     "correlacao_uni_nucleos": round(float(np.corrcoef(logit_s, D[s]["nucleos"])[0, 1]), 3)}
    resumo["funcionou"] = all(resumo[s]["combinacao"] > resumo[s]["uni2h"] for s in LAMINAS)
    (RESULTADOS_DIR / "dcis_ic_uni_nucleos.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                            encoding="utf-8")
    print(f"{'Lâmina de teste':<18}{'UNI2-h':>9}{'Núcleos':>9}{'Juntos':>9}{'Correlação':>12}")
    for s in LAMINAS:
        r = resumo[s]
        print(f"{s:<18}{r['uni2h']:>9}{r['nucleos']:>9}{r['combinacao']:>9}{r['correlacao_uni_nucleos']:>12}")
    print(f"\nCritério fixado antes (juntos > UNI2-h nas três): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
