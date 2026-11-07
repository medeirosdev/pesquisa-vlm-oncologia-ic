"""
Resposta em conjunto: quando o classificador não separa benigno de atípico, responde "benigno ou atípico" em vez
de escolher um. A resposta passa a ser uma de quatro: benigno, atípico, benigno ou atípico, maligno (DCIS ou IC).
A ideia não é acertar mais, e sim dar uma resposta próxima e honesta quando há dúvida (recuo pra classe-mãe na
hierarquia, como em Deng et al., CVPR 2012; conjuntos de previsão, como na predição conformal).

Fixado ANTES de rodar (commit anterior aos resultados):
  Probabilidades: classificador de 4 classes com o descritor D2 (rotulo_oficial.py: rótulo oficial + negativos),
     atributos de resultados/rotulo_oficial/rois_neg/atributos.json; treino nas 79 lâminas, teste nas 57.
  Regra: Pb = P(benigno), Pa = P(atípico), Pm = P(DCIS) + P(IC).
     Pm >= max(Pb, Pa) -> maligno; senão r = Pb / (Pb + Pa):
     r >= 0,5 + d -> benigno; r <= 0,5 - d -> atípico; senão -> benigno ou atípico.
  d: o menor valor em {0; 0,05; ...; 0,45} com acerto do conjunto >= 0,80 nas previsões do treino por validação
     cruzada deixando um paciente de fora (LOPO); se nenhum chegar, 0,45.
  Métricas (3 classes oficiais: benigno, atípico, maligno):
     acerto do conjunto = fração de lâminas cuja classe real está na resposta;
     respostas exatas = fração de respostas com uma classe só.
  Critério de "funcionou", nas 57: acerto do conjunto >= 0,75 E respostas exatas >= 0,50.
  Também reportado (sem critério): a mesma regra com d = 0 (sem recuo; equivale ao classificador de 3 classes);
     tabela classe real × resposta; acerto do conjunto só nas benignas e atípicas; intervalo de 95% do acerto do
     conjunto por bootstrap agrupado por paciente.
  As 57 lâminas já foram usadas em vários testes; a confirmação depende das 30 de teste ainda não usadas.

Uso (venv do projeto; só CPU; segundos):
    .venv/bin/python validacao/resposta_em_conjunto.py
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from comum.lamina import RESULTADOS_DIR
from comum.rois import info_lamina

GRADE_D = [round(0.05 * i, 2) for i in range(10)]
ALVO_TREINO = 0.80
ACERTO_MIN = 0.75
EXATAS_MIN = 0.50
N_BOOTSTRAP = 2000
RESPOSTAS = ["benigno", "atipico", "benigno ou atipico", "maligno"]
SAIDA = RESULTADOS_DIR / "resposta_em_conjunto"


def tres(c):
    return "maligno" if c in ("DCIS", "IC") else c


def responder(p, d):
    pb, pa, pm = p[0], p[1], p[2] + p[3]
    if pm >= max(pb, pa):
        return "maligno"
    r = pb / (pb + pa)
    return "benigno" if r >= 0.5 + d else ("atipico" if r <= 0.5 - d else "benigno ou atipico")


def contem(resposta, real3):
    return real3 in resposta.split(" ou ")


def medir(resp, real, stems):
    return {"acerto_do_conjunto": round(float(np.mean([contem(resp[s], tres(real[s])) for s in stems])), 3),
            "respostas_exatas": round(float(np.mean([" ou " not in resp[s] for s in stems])), 3),
            "n": len(stems)}


def main():
    from categoria_uni import logistica_multinomial
    from decisao_lamina import lopo
    from lamina_inteira import FINAIS, classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    SAIDA.mkdir(parents=True, exist_ok=True)
    A = json.loads((RESULTADOS_DIR / "rotulo_oficial" / "rois_neg" / "atributos.json").read_text(encoding="utf-8"))
    treino, teste = laminas_val() + laminas_dev(), laminas_teste()
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in treino + teste}
    pac = pacientes()

    def prever(tr, alvo):
        P = logistica_multinomial(np.array([A[s] for s in tr]), np.array([FINAIS.index(real[s]) for s in tr]),
                                  np.array([A[s] for s in alvo]), k=4, probabilidades=True)
        return dict(zip(alvo, P))
    cv, p_te = lopo(A, treino, pac, prever), prever(treino, teste)
    curva_treino = {d: medir({s: responder(cv[s], d) for s in treino}, real, treino) for d in GRADE_D}
    d = next((d for d in GRADE_D if curva_treino[d]["acerto_do_conjunto"] >= ALVO_TREINO), GRADE_D[-1])

    resp = {s: responder(p_te[s], d) for s in teste}
    sem_recuo = {s: responder(p_te[s], 0.0) for s in teste}
    nao_mal = [s for s in teste if tres(real[s]) != "maligno"]
    grupos = {}
    for s in teste:
        grupos.setdefault(pac[s], []).append(s)
    chaves, rng, boot = sorted(grupos), random.Random(0), []
    for _ in range(N_BOOTSTRAP):
        am = [s for g in (rng.choice(chaves) for _ in chaves) for s in grupos[g]]
        boot.append(np.mean([contem(resp[s], tres(real[s])) for s in am]))
    resumo = {"d": d, "curva_treino_lopo": {str(k): v for k, v in curva_treino.items()},
              "teste_57": medir(resp, real, teste), "teste_57_sem_recuo": medir(sem_recuo, real, teste),
              "teste_benignas_e_atipicas": medir(resp, real, nao_mal),
              "teste_benignas_e_atipicas_sem_recuo": medir(sem_recuo, real, nao_mal),
              "ic95_acerto_do_conjunto": [round(float(np.percentile(boot, 2.5)), 3), round(float(np.percentile(boot, 97.5)), 3)],
              "tabela_real_x_resposta": {c: dict(Counter(resp[s] for s in teste if tres(real[s]) == c)) for c in ("benigno", "atipico", "maligno")},
              "por_lamina": {s: {"real": real[s], "resposta": resp[s], "probabilidades": np.round(p_te[s], 3).tolist()} for s in teste}}
    m = resumo["teste_57"]
    resumo["funcionou"] = m["acerto_do_conjunto"] >= ACERTO_MIN and m["respostas_exatas"] >= EXATAS_MIN
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"d escolhido no treino (LOPO): {d}")
    for k in ("teste_57", "teste_57_sem_recuo", "teste_benignas_e_atipicas", "teste_benignas_e_atipicas_sem_recuo"):
        print(f"{k:<38} {resumo[k]}")
    print(f"IC 95% do acerto do conjunto nas 57: {resumo['ic95_acerto_do_conjunto']}")
    print("real × resposta:")
    for c, linha in resumo["tabela_real_x_resposta"].items():
        print(f"  {c:<8} {linha}")
    print(f"Critério fixado antes (acerto do conjunto >= {ACERTO_MIN} e exatas >= {EXATAS_MIN}): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
