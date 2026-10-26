"""
Lâminas benignas como exemplos negativos pro descritor. O rótulo de uma lâmina do BRACS é o da lesão mais
grave; numa lâmina N ou PB, nenhum patch é atípico nem maligno. Os patches dessas lâminas entram no treino
do nível 1 do descritor como "benigno", pra cortar os falsos DCIS/IC (ex.: 115 de 2.000 patches "IC" na
BRACS_1261, benigna).

Fixado ANTES de rodar (commit anterior aos resultados):
  Negativos: as lâminas benignas (N, PB) entre as 79 de treino de classificador_lamina.py (61 de validação
     + 18 de desenvolvimento): 26 lâminas; até 500 patches de cada, sorteados da amostra de 2.000 (semente 0),
     rotulados "benigno" no nível 1. O nível 2 (DCIS × IC) não muda.
  Descritor "rois+neg": RoIs de treino do BRACS (como o "rois") + negativos.
  Sem vazamento: os atributos de cada lâmina de treino vêm de um descritor treinado sem os negativos do
     paciente dela (e, nas lâminas de desenvolvimento, também sem as RoIs dela, como antes). As 57 de teste
     usam o descritor com todos os negativos; nenhuma lâmina de teste entra como negativo.
  Classificador da lâmina: igual ao de classificador_lamina.py (mesmos 12 atributos, mesma logística,
     treino nas 79, teste nas 57); só troca o descritor.
  Critério de "funcionou": acurácia balanceada nas 57 > a do classificador_lamina.py (descritor "rois").
  Também reportado (sem critério): fração média de patches DCIS + IC nas lâminas benignas do teste, antes e
     depois; acerto por classe; intervalo de 95% por bootstrap agrupado por paciente; acerto por patch nas
     RoIs de validação (o benigno tem vazamento parcial: parte dessas RoIs vem das lâminas usadas como
     negativos; atípico e maligno não).

Uso (venv do projeto; só CPU; depois de classificador_lamina.py):
    .venv/bin/python validacao/negativos_benignos.py
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np

from comum.lamina import RESULTADOS_DIR
from comum.rois import info_lamina

N_NEGATIVOS = 500
SAIDA = RESULTADOS_DIR / "negativos_benignos"


def negativos(s):
    from lamina_inteira import amostra
    x = amostra(s)
    return x[sorted(random.Random(0).sample(range(len(x)), min(N_NEGATIVOS, len(x))))]


def calcular_atributos(dev, val, teste, benignas, pac):
    """Atributos por lâmina com o descritor rois+neg (cache progressivo em SAIDA/atributos.json)."""
    from classificador_lamina import atributos
    from lamina_inteira import amostra, dados_descritor_rois, treinar_e_prever
    cache = SAIDA / "atributos.json"
    A = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    base = dados_descritor_rois()
    neg = {s: negativos(s) for s in benignas}
    # um modelo por (lâmina de desenvolvimento excluída, paciente cujos negativos saem)
    grupos = {}
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
                A[s] = atributos(p1[ini:ini + len(x)], p2[ini:ini + len(x)])
                ini += len(x)
            cache.write_text(json.dumps(A, indent=1), encoding="utf-8")
        print(f"  modelo {i}/{len(grupos)}: {len(faltam)} lâminas", flush=True)
    return A


def conferencia_rois_val(benignas):
    from lamina_inteira import CATEGORIAS, dados_descritor_rois, treinar_e_prever
    from comum.bancos import CATEGORIA_DA_CLASSE
    X1, y1, X2, y2 = dados_descritor_rois()()
    Xn = np.concatenate([negativos(b) for b in benignas])
    z = np.load(RESULTADOS_DIR / "lamina_inteira" / "rois_val.npz")
    p1, _ = treinar_e_prever(np.concatenate([X1, Xn]), np.concatenate([y1, np.zeros(len(Xn), dtype=y1.dtype)]), X2, y2,
                             z["embs"].astype(np.float32))
    reais = [CATEGORIA_DA_CLASSE[c] for c in z["classes"]]
    pred = [CATEGORIAS[i] for i in p1.argmax(1)]
    return {c: round(float(np.mean([p == c for r, p in zip(reais, pred) if r == c])), 3) for c in CATEGORIAS}


def main():
    from classificador_lamina import SAIDA as SAIDA_ROIS
    from classificador_lamina import bootstrap, classificar, metricas
    from lamina_inteira import classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    SAIDA.mkdir(parents=True, exist_ok=True)
    dev, val, teste = laminas_dev(), laminas_val(), laminas_teste()
    treino = val + dev
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in treino + teste}
    pac = pacientes()
    benignas = [s for s in treino if real[s] == "benigno"]
    A = calcular_atributos(dev, val, teste, benignas, pac)

    pred = {s: c for s, (c, _) in classificar(A, real, treino, teste).items()}
    antes = json.loads((SAIDA_ROIS / "resumo.json").read_text(encoding="utf-8"))
    A_antes = json.loads((SAIDA_ROIS / "atributos.json").read_text(encoding="utf-8"))
    ben_teste = [s for s in teste if real[s] == "benigno"]
    frac_mal = lambda AA: round(float(np.mean([AA[s][2] + AA[s][3] for s in ben_teste])), 4)  # f_DCIS + f_IC
    resumo = {"n_negativas": len(benignas), "negativas": benignas,
              "teste_57": metricas(real, pred, teste),
              "ic95_acuracia_balanceada_57": bootstrap(real, pred, teste, pac),
              "antes_rois_teste_57": antes["teste_57"],
              "fracao_DCIS_IC_benignas_teste": {"antes": frac_mal(A_antes), "depois": frac_mal(A)},
              "conferencia_rois_val_por_patch": conferencia_rois_val(benignas),
              "por_lamina_teste": pred}
    resumo["funcionou"] = resumo["teste_57"]["acuracia_balanceada"] > antes["teste_57"]["acuracia_balanceada"]
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for nome in ("antes_rois_teste_57", "teste_57"):
        m = resumo[nome]
        print(f"{nome:<22} bal {m['acuracia_balanceada']:.3f} | {m['acertos']}/{m['n']} | {m['por_classe']} | {m['preditas']}")
    print(f"IC 95% nas 57: {resumo['ic95_acuracia_balanceada_57']}")
    print(f"fração DCIS+IC nas benignas do teste: {resumo['fracao_DCIS_IC_benignas_teste']}")
    print(f"conferência RoIs de validação (por patch): {resumo['conferencia_rois_val_por_patch']}")
    print(f"Critério fixado antes (bal rois+neg > bal rois nas 57): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
