"""
Classificador da lâmina inteira: a classe final sai de um classificador treinado com o rótulo das lâminas,
não do modelo de linguagem (que passa a só redigir o texto). No teste externo, o modelo de linguagem chamou
55 de 57 lâminas de malignas; a regra de proporção de 22/10 (limiares escolhidos em 18 lâminas) também não
passou (acurácia balanceada 0,346).

Fixado ANTES de rodar (commit anterior aos resultados):
  Descritor: o "rois" de lamina_inteira.py (hierárquico, treinado nas RoIs de treino do BRACS), aplicado à
     amostra de até 2.000 patches de tecido de cada lâmina. Nas 18 lâminas de desenvolvimento, o descritor
     que descreve cada lâmina é treinado sem as RoIs dela (como em lamina_inteira.py).
  Atributos da lâmina (12), a partir de P(categoria) e P(subtipo) de cada patch:
     frações de patches previstos como benigno, atípico, DCIS e IC (4);
     médias de P(benigno), P(atípico) e P(maligno) (3);
     percentis 90 e 99 de P(maligno) e de P(maligno) x P(IC) (4);
     fração de patches com P(maligno) x P(IC) >= 0,90 (1).
  Classificador: logística multinomial nas 4 classes (benigno, atípico, DCIS, IC), atributos padronizados,
     pesos balanceados por classe, L2 equivalente a C=1 (categoria_uni.logistica_multinomial). Sem ajuste
     de hiperparâmetro.
  Treino: 79 lâminas = 61 de validação oficial (as de pacote_cotas.py) + 18 de desenvolvimento.
  Teste: as mesmas 57 lâminas do teste externo (prelaudo_teste_externo.py), pra comparar com E0, E1 e E2
     de lamina_inteira.py. Nada foi escolhido nelas.
  Métrica principal: acurácia balanceada nas 4 classes, nas 57.
  Critério de "funcionou": acurácia balanceada > 0,406 (E0, pipeline com modelo de linguagem), que é a
     maior entre E0 (0,406), E1 (0,357) e E2 (0,346).
  Também reportado (sem critério): acerto por classe e classes preditas; subconjunto com uma lâmina por
     paciente; intervalo de 95% da acurácia balanceada por bootstrap agrupado por paciente (2.000
     reamostragens, semente 0); validação cruzada deixando um paciente de fora nas 79 de treino;
     coeficientes da logística (explicabilidade).

Uso (venv do projeto; só CPU):
    .venv/bin/python validacao/classificador_lamina.py
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

ATRIBUTOS = ["f_benigno", "f_atipico", "f_DCIS", "f_IC", "media_p_benigno", "media_p_atipico", "media_p_maligno",
             "p90_p_maligno", "p99_p_maligno", "p90_p_IC", "p99_p_IC", "f_p_IC_090"]
CORTE_E0 = 0.406
N_BOOTSTRAP = 2000
SAIDA = RESULTADOS_DIR / "classificador_lamina"


def atributos(p1, p2):
    cat = p1.argmax(1)
    sub = p2.argmax(1)
    p_ic = p1[:, 2] * p2[:, 1]
    return [float((cat == 0).mean()), float((cat == 1).mean()), float(((cat == 2) & (sub == 0)).mean()),
            float(((cat == 2) & (sub == 1)).mean()), float(p1[:, 0].mean()), float(p1[:, 1].mean()),
            float(p1[:, 2].mean()), float(np.percentile(p1[:, 2], 90)), float(np.percentile(p1[:, 2], 99)),
            float(np.percentile(p_ic, 90)), float(np.percentile(p_ic, 99)), float((p_ic >= 0.90).mean())]


def calcular_atributos(dev, val, teste):
    """Atributos por lâmina (cache em SAIDA/atributos.json)."""
    from lamina_inteira import amostra, dados_descritor_rois, treinar_e_prever
    cache = SAIDA / "atributos.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    treino = dados_descritor_rois()
    A = {}
    for s in dev:
        A[s] = atributos(*treinar_e_prever(*treino(excluir=s), amostra(s)))
        print(f"  dev {s}", flush=True)
    outras = val + teste
    X = [amostra(s) for s in outras]
    p1, p2 = treinar_e_prever(*treino(), np.concatenate(X))
    ini = 0
    for s, x in zip(outras, X):
        A[s] = atributos(p1[ini:ini + len(x)], p2[ini:ini + len(x)])
        ini += len(x)
    cache.write_text(json.dumps(A, indent=1), encoding="utf-8")
    return A


def classificar(A, real, treino, alvo):
    from categoria_uni import logistica_multinomial
    from lamina_inteira import FINAIS
    X = np.array([A[s] for s in treino])
    y = np.array([FINAIS.index(real[s]) for s in treino])
    P = logistica_multinomial(X, y, np.array([A[s] for s in alvo]), k=4, probabilidades=True)
    return {s: (FINAIS[int(p.argmax())], p) for s, p in zip(alvo, P)}


def coeficientes(A, real, treino):
    """Mesma logística de categoria_uni, refeita aqui só pra expor os pesos (atributos padronizados)."""
    import torch
    from lamina_inteira import FINAIS
    X = np.array([A[s] for s in treino])
    y = torch.tensor([FINAIS.index(real[s]) for s in treino])
    mu, sd = X.mean(0), X.std(0) + 1e-8
    Xt = torch.tensor((X - mu) / sd, dtype=torch.float64)
    n, k = len(y), 4
    cont = torch.bincount(y, minlength=k).double()
    peso = torch.where(cont > 0, n / (k * cont.clamp(min=1)), torch.zeros_like(cont))
    W = torch.zeros(Xt.shape[1], k, dtype=torch.float64, requires_grad=True)
    b = torch.zeros(k, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([W, b], max_iter=500, line_search_fn="strong_wolfe")

    def perda():
        opt.zero_grad()
        l = torch.nn.functional.cross_entropy(Xt @ W + b, y, weight=peso, reduction="sum") / n + (W ** 2).sum() / (2 * n)
        l.backward()
        return l

    opt.step(perda)
    return {a: dict(zip(FINAIS, np.round(W.detach().numpy()[i], 2).tolist())) for i, a in enumerate(ATRIBUTOS)}


def metricas(real, pred, stems):
    from lamina_inteira import FINAIS, acuracia_balanceada
    r, p = [real[s] for s in stems], [pred[s] for s in stems]
    return {"acuracia_balanceada": round(acuracia_balanceada(r, p), 3), "acertos": sum(a == b for a, b in zip(r, p)),
            "n": len(stems), "por_classe": {c: f"{sum(a == b == c for a, b in zip(r, p))}/{r.count(c)}" for c in FINAIS},
            "preditas": dict(Counter(p))}


def bootstrap(real, pred, stems, pac):
    from lamina_inteira import acuracia_balanceada
    grupos = {}
    for s in stems:
        grupos.setdefault(pac[s], []).append(s)
    chaves, rng, bas = sorted(grupos), random.Random(0), []
    for _ in range(N_BOOTSTRAP):
        amostra = [s for g in (rng.choice(chaves) for _ in chaves) for s in grupos[g]]
        bas.append(acuracia_balanceada([real[s] for s in amostra], [pred[s] for s in amostra]))
    return [round(float(np.percentile(bas, 2.5)), 3), round(float(np.percentile(bas, 97.5)), 3)]


def main():
    from lamina_inteira import classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    from prelaudo_teste_externo import um_por_paciente
    SAIDA.mkdir(parents=True, exist_ok=True)
    dev, val, teste = laminas_dev(), laminas_val(), laminas_teste()
    treino = val + dev
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in treino + teste}
    pac = pacientes()
    A = calcular_atributos(dev, val, teste)

    saida_teste = classificar(A, real, treino, teste)
    pred = {s: c for s, (c, _) in saida_teste.items()}
    resumo = {"n_treino": len(treino), "n_teste": len(teste), "atributos": ATRIBUTOS,
              "teste_57": metricas(real, pred, teste),
              "teste_um_por_paciente": metricas(real, pred, um_por_paciente(teste)),
              "ic95_acuracia_balanceada_57": bootstrap(real, pred, teste, pac)}

    pred_cv = {}
    for p in sorted({pac[s] for s in treino}):
        fora = [s for s in treino if pac[s] == p]
        pred_cv.update({s: c for s, (c, _) in classificar(A, real, [s for s in treino if pac[s] != p], fora).items()})
    resumo["validacao_cruzada_treino_79"] = metricas(real, pred_cv, treino)
    resumo["coeficientes"] = coeficientes(A, real, treino)
    resumo["por_lamina_teste"] = {s: {"real": real[s], "predito": c, "probabilidades": np.round(p, 3).tolist()}
                                  for s, (c, p) in saida_teste.items()}
    resumo["funcionou"] = resumo["teste_57"]["acuracia_balanceada"] > CORTE_E0
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    for nome in ("validacao_cruzada_treino_79", "teste_57", "teste_um_por_paciente"):
        m = resumo[nome]
        print(f"{nome:<28} bal {m['acuracia_balanceada']:.3f} | {m['acertos']}/{m['n']} | {m['por_classe']} | {m['preditas']}")
    print(f"IC 95% (bootstrap por paciente) nas 57: {resumo['ic95_acuracia_balanceada_57']}")
    print(f"Critério fixado antes (acurácia balanceada nas 57 > {CORTE_E0}): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
