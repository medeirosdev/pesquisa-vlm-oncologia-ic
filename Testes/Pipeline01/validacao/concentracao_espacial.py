"""
Concentração espacial dos patches suspeitos como atributo da lâmina, pra separar benigno de atípico (o ponto
mais fraco: AUC 0,66 em suspeito × benigno com o rótulo oficial). Hipótese vinda de dois mapas de calor: numa
lesão de verdade, os patches suspeitos formam um foco; numa lâmina benigna, os falsos positivos ficam espalhados.

Fixado ANTES de rodar (commit anterior aos resultados):
  Patches: a amostra de até 2.000 patches de tecido de cada lâmina, descrita pelo descritor D2 de
     rotulo_oficial.py (rótulo oficial + negativos benignos, com a mesma separação: os atributos de uma lâmina de
     treino vêm de um descritor treinado sem os negativos do paciente dela e, nas de desenvolvimento, sem as
     RoIs dela). Classe de cada patch: benigno, atípico, DCIS ou IC.
  Vizinhança: os 8 vizinhos mais próximos de cada patch dentro da amostra da lâmina (independe do tamanho
     da lâmina; a amostra cobre a lâmina toda).
  Atributos espaciais (4):
     enriquecimento dos suspeitos (atípico, DCIS ou IC): fração média de vizinhos suspeitos entre os patches
       suspeitos, dividida pela fração de suspeitos na lâmina (1 = espalhados ao acaso; > 1 = em foco);
     o mesmo pros malignos (DCIS ou IC) e pros atípicos (sem patches da classe, ou com todos: 1);
     fração de patches da lâmina que são suspeitos com pelo menos 4 dos 8 vizinhos suspeitos ("suspeitos em foco").
  Classificadores: os 12 atributos de classificador_lamina.py (A12) contra A12 + 4 espaciais (A16); mesma
     logística, treino nas 79 lâminas, teste nas 57.
  Tarefa principal: benigno × atípico, treinando e testando só nas lâminas dessas duas classes (treino:
     34 benignas + 17 atípicas; teste: 20 + 17).
  Critério de "funcionou": nas 37 lâminas benignas e atípicas do teste, AUC(A16) >= AUC(A12) + 0,05 E
     AUC(A16) >= 0,70.
  Também reportado (sem critério): intervalo de 95% da diferença de AUC por bootstrap agrupado por paciente;
     acurácia balanceada nas 4 classes (plano e hierárquico) e AUC de suspeito × benigno com A12 e A16;
     médias dos atributos espaciais por classe no teste; conferência de que A12 aqui é igual ao de
     rotulo_oficial.py.
  As 57 lâminas já foram usadas em vários testes; a confirmação depende das 30 de teste ainda não usadas.

Uso (venv do projeto; só CPU; ~30 min):
    .venv/bin/python validacao/concentracao_espacial.py
As probabilidades por patch ficam em resultados/concentracao_espacial/probs/ (servem aos mapas de calor).
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from comum.lamina import RESULTADOS_DIR, dir_resultados
from comum.rois import info_lamina

K_VIZINHOS = 8
MIN_VIZINHOS_FOCO = 4
GANHO_MIN = 0.05
AUC_MIN = 0.70
N_BOOTSTRAP = 2000
ESPACIAIS = ["enriq_suspeitos", "enriq_malignos", "enriq_atipicos", "f_suspeitos_em_foco"]
SAIDA = RESULTADOS_DIR / "concentracao_espacial"


def coordenadas(s):
    with open(dir_resultados(s, "uni2h") / "amostra2000_xy.csv", newline="", encoding="utf-8") as f:
        return np.array([(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)], dtype=float)


def espaciais(p1, p2, xy):
    from scipy.spatial import cKDTree
    cat, sub = p1.argmax(1), p2.argmax(1)
    suspeito, maligno, atipico = cat != 0, cat == 2, cat == 1
    _, viz = cKDTree(xy).query(xy, k=K_VIZINHOS + 1)
    viz = viz[:, 1:]  # o próprio patch é o vizinho mais próximo

    def enriquecimento(m):
        f = m.mean()
        if m.sum() == 0 or f == 1:
            return 1.0
        return float(m[viz][m].mean() / f)
    foco = suspeito & (suspeito[viz].sum(1) >= MIN_VIZINHOS_FOCO)
    return [enriquecimento(suspeito), enriquecimento(maligno), enriquecimento(atipico), float(foco.mean())]


def calcular(dev, val, teste, benignas, pac):
    """Probabilidades por patch (D2) e atributos A12 + espaciais; cache progressivo."""
    from classificador_lamina import atributos
    from lamina_inteira import amostra, dados_descritor_rois, treinar_e_prever
    from negativos_benignos import negativos
    (SAIDA / "probs").mkdir(parents=True, exist_ok=True)
    cache = SAIDA / "atributos.json"
    A = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    base = dados_descritor_rois()
    neg = {s: negativos(s) for s in benignas}
    grupos = {}  # mesma divisão de negativos_benignos.calcular_atributos
    for s in dev + val + teste:
        sem_paciente = pac[s] if s not in teste and any(pac[b] == pac[s] for b in benignas) else None
        grupos.setdefault((s if s in dev else None, sem_paciente), []).append(s)
    for i, ((excluir, sem_paciente), stems) in enumerate(sorted(grupos.items(), key=lambda g: str(g[0])), 1):
        faltam = [s for s in stems if s not in A]
        if not faltam:
            continue
        X1, y1, X2, y2 = base(excluir=excluir)
        Xn = np.concatenate([neg[b] for b in benignas if pac[b] != sem_paciente])
        X1, y1 = np.concatenate([X1, Xn]), np.concatenate([y1, np.zeros(len(Xn), dtype=y1.dtype)])
        for j in range(0, len(faltam), 20):  # em blocos, pela memória
            bloco = faltam[j:j + 20]
            X = [amostra(s) for s in bloco]
            p1, p2 = treinar_e_prever(X1, y1, X2, y2, np.concatenate(X))
            ini = 0
            for s, x in zip(bloco, X):
                a, b = p1[ini:ini + len(x)], p2[ini:ini + len(x)]
                xy = coordenadas(s)
                assert len(xy) == len(x), s
                np.savez(SAIDA / "probs" / f"{s}_probs.npz", p1=a, p2=b, xy=xy.astype(int))
                A[s] = {"A12": atributos(a, b), "espaciais": espaciais(a, b, xy)}
                ini += len(x)
            cache.write_text(json.dumps(A, indent=1), encoding="utf-8")
        print(f"  modelo {i}/{len(grupos)}: {len(faltam)} lâminas", flush=True)
    return A


def auc_bxa(A, real, treino, teste, chave):
    from decisao_lamina import auc, prob
    tr = [s for s in treino if real[s] in ("benigno", "atipico")]
    te = [s for s in teste if real[s] in ("benigno", "atipico")]
    P = prob(A[chave], tr, [int(real[s] == "atipico") for s in tr], te, 2)
    p = {s: float(v[1]) for s, v in zip(te, P)}
    return auc([p[s] for s in te if real[s] == "atipico"], [p[s] for s in te if real[s] == "benigno"]), p, te


def main():
    from classificador_lamina import classificar, metricas
    from decisao_lamina import auc, hierarquico, prob
    from lamina_inteira import classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    dev, val, teste = laminas_dev(), laminas_val(), laminas_teste()
    treino = val + dev
    rot = {s: info_lamina(s)["rotulo"] for s in treino + teste}
    real = {s: classe_final(rot[s]) for s in rot}
    pac = pacientes()
    benignas = [s for s in treino if real[s] == "benigno"]
    bruto = calcular(dev, val, teste, benignas, pac)
    A = {"A12": {s: bruto[s]["A12"] for s in bruto}, "A16": {s: bruto[s]["A12"] + bruto[s]["espaciais"] for s in bruto}}

    ref = json.loads((RESULTADOS_DIR / "rotulo_oficial" / "rois_neg" / "atributos.json").read_text(encoding="utf-8"))
    dif_ref = max(abs(a - b) for s in treino + teste for a, b in zip(A["A12"][s], ref[s]))

    resumo = {"conferencia_A12_igual_rotulo_oficial_max_dif": dif_ref, "por_forma": {}}
    probs_bxa = {}
    for chave in ("A12", "A16"):
        a, p, te_ba = auc_bxa(A, real, treino, teste, chave)
        probs_bxa[chave] = p
        plano = {s: c for s, (c, _) in classificar(A[chave], real, treino, teste).items()}
        h = hierarquico(A[chave], real, treino, teste, pac, 0.0)
        pos = {"FEA", "ADH", "DCIS", "IC"}
        P = prob(A[chave], treino, [int(rot[s] in pos) for s in treino], teste, 2)
        ps = {s: float(v[1]) for s, v in zip(teste, P)}
        resumo["por_forma"][chave] = {
            "auc_benigno_x_atipico": round(a, 3),
            "plano_4_classes": metricas(real, plano, teste),
            "hierarquico_4_classes": {k: h["teste_57"][k] for k in ("acuracia_balanceada", "acertos", "por_classe")},
            "auc_suspeito_x_benigno": round(auc([ps[s] for s in teste if rot[s] in pos], [ps[s] for s in teste if rot[s] not in pos]), 3)}
    grupos = {}
    for s in te_ba:
        grupos.setdefault(pac[s], []).append(s)
    chaves, rng, difs = sorted(grupos), random.Random(0), []
    for _ in range(N_BOOTSTRAP):
        am = [s for g in (rng.choice(chaves) for _ in chaves) for s in grupos[g]]
        pos_, neg_ = [s for s in am if real[s] == "atipico"], [s for s in am if real[s] == "benigno"]
        if pos_ and neg_:
            difs.append(auc([probs_bxa["A16"][s] for s in pos_], [probs_bxa["A16"][s] for s in neg_])
                        - auc([probs_bxa["A12"][s] for s in pos_], [probs_bxa["A12"][s] for s in neg_]))
    resumo["ic95_diferenca_auc_bxa"] = [round(float(np.percentile(difs, 2.5)), 3), round(float(np.percentile(difs, 97.5)), 3)]
    resumo["media_espaciais_teste"] = {c: dict(zip(ESPACIAIS, np.round(np.mean([bruto[s]["espaciais"] for s in teste if real[s] == c], 0), 3).tolist()))
                                       for c in ("benigno", "atipico", "DCIS", "IC")}
    a12, a16 = resumo["por_forma"]["A12"]["auc_benigno_x_atipico"], resumo["por_forma"]["A16"]["auc_benigno_x_atipico"]
    resumo["funcionou"] = a16 >= a12 + GANHO_MIN and a16 >= AUC_MIN
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"conferência: A12 igual ao de rotulo_oficial (máx. diferença {dif_ref:.2e})")
    for chave, r in resumo["por_forma"].items():
        print(f"{chave}: AUC benigno × atípico {r['auc_benigno_x_atipico']} | suspeito × benigno {r['auc_suspeito_x_benigno']} | "
              f"plano bal {r['plano_4_classes']['acuracia_balanceada']} {r['plano_4_classes']['acertos']}/57 {r['plano_4_classes']['por_classe']} | "
              f"hierárquico bal {r['hierarquico_4_classes']['acuracia_balanceada']} {r['hierarquico_4_classes']['acertos']}")
    print(f"IC 95% da diferença de AUC (A16 - A12): {resumo['ic95_diferenca_auc_bxa']}")
    for c, m in resumo["media_espaciais_teste"].items():
        print(f"  {c:<8} {m}")
    print(f"Critério fixado antes (AUC A16 >= A12 + {GANHO_MIN} e >= {AUC_MIN}): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
