"""
Próstata (PANDA, Radboud -> Karolinska): o resultado do GAT-MIL com padronização por centro se repete? E o que causa o
ganho (o grafo ou a padronização)?

Antes: panda_centro.py (uma execução) deu kappa 0,609 com GAT-MIL padronizado; a mesma receita retreinada em
prelaudo_final.py deu 0,570; o mínimo fixado em panda_mil.py era 0,60. O treino do GAT na GPU não é determinístico.

Fixado ANTES de rodar (commit anterior aos resultados):
  Desenho 2 × 2, as mesmas 600 de treino (Radboud) e 300 de teste (Karolinska) de panda_mil.py: modelo ABMIL
     (mil_atencao.treinar) ou GAT-MIL (gat_mil.treinar, 8 vizinhos encostados) × embeddings originais ou padronizados por
     centro (panda_centro.padronizar_por_centro). k = 6, 40 épocas, sem ajuste.
  Execuções: 5. A execução r usa as sementes 5r a 5r + 4 (5 modelos, média das probabilidades), então as execuções
     diferem pela semente e pelo não determinismo da GPU.
  Medidas por execução e braço: kappa quadrático (ISUP 0-5), AUC benigno × câncer, acurácia exata, sensibilidade e
     especificidade câncer × benigno, matriz de confusão.
  Critérios:
     S1 (o ganho se repete): kappa(GAT-MIL padronizado) − kappa(ABMIL original) > 0 em todas as 5 execuções.
     S2 (atinge o mínimo original): média do kappa do GAT-MIL padronizado nas 5 execuções >= 0,60.
  Também reportado (sem critério): média e desvio de cada braço; efeito do grafo (GAT − ABMIL) e da padronização
     (padronizado − original) por execução.
  A execução 0 do GAT-MIL padronizado guarda, para cada biópsia de teste, a probabilidade de cada semente e a atenção
     média (usadas em prelaudo/aviso_linhas_base.py).

Uso (venv do projeto; GPU; ~2 h): .venv/bin/python mil/panda/panda_repeticoes.py
Saída: resultados/panda_repeticoes/{resumo.json, gat_padronizado_r0.json, <image_id>_atencao.npy}
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "panda_repeticoes"
K, EXECUCOES = 6, 5
KAPPA_MIN = 0.60


def medidas(real, P):
    from panda_mil import auc_rank, kappa_quadratico
    pred = P.argmax(1)
    conf = np.zeros((K, K), int)
    for r, q in zip(real, pred):
        conf[r, q] += 1
    pc = 1 - P[:, 0]
    return {"kappa": round(float(kappa_quadratico(real, pred, K)), 4),
            "auc_benigno_x_cancer": round(float(auc_rank(pc[real >= 1], pc[real == 0])), 4),
            "acuracia_exata": round(float(np.mean(pred == real)), 4),
            "sensibilidade_cancer": round(float(np.mean(pred[real >= 1] >= 1)), 4),
            "especificidade_benigno": round(float(np.mean(pred[real == 0] == 0)), 4),
            "matriz_confusao_real_x_previsto": conf.tolist()}


def main():
    import torch
    import gat_mil
    import mil_atencao
    from gat_mil_panda import carregar
    from panda_centro import padronizar_por_centro
    from panda_mil import biopsias
    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    y = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X0, G = carregar(tr + te)
    Xs = {"original": X0, "padronizado": padronizar_por_centro(X0, [tr, te])}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    ytr = np.array([y[i] for i in tr])
    real = np.array([y[i] for i in te])
    resumo = {"execucoes": {}}
    for r in range(EXECUCOES):
        sementes = list(range(5 * r, 5 * r + 5))
        resumo["execucoes"][r] = {"sementes": sementes}
        for emb, X in Xs.items():
            for nome in ("abmil", "gat"):
                P = np.zeros((len(te), K))
                guardar = r == 0 and nome == "gat" and emb == "padronizado"
                P_sem = np.zeros((len(te), len(sementes), K))
                att = [np.zeros(len(X[i])) for i in te]
                for s_i, s in enumerate(sementes):
                    if nome == "abmil":
                        m = mil_atencao.treinar([X[i] for i in tr], ytr, s, dev, k=K).eval()
                    else:
                        m = gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], ytr, s, dev, k=K).eval()
                    with torch.no_grad():
                        for j, i in enumerate(te):
                            x = X[i].to(dev)
                            if nome == "abmil":
                                logit, a = m(x)
                            else:
                                logit, a, _ = m(x, G[i].to(dev))
                            q = torch.softmax(logit, 0).cpu().numpy()
                            P_sem[j, s_i] = q
                            P[j] += q / len(sementes)
                            if guardar:
                                att[j] += a.cpu().numpy() / len(sementes)
                resumo["execucoes"][r][f"{nome}_{emb}"] = medidas(real, P)
                if guardar:
                    for j, i in enumerate(te):
                        np.save(SAIDA / f"{i}_atencao.npy", att[j].astype(np.float32))
                    (SAIDA / "gat_padronizado_r0.json").write_text(json.dumps(
                        {i: {"real": int(y[i]), "previsto": int(P[j].argmax()), "probs": [round(float(v), 5) for v in P[j]],
                             "probs_sementes": [[round(float(v), 5) for v in P_sem[j, s]] for s in range(len(sementes))]}
                         for j, i in enumerate(te)}, indent=1), encoding="utf-8")
                print(f"  execução {r} {nome}_{emb}: kappa {resumo['execucoes'][r][f'{nome}_{emb}']['kappa']}", flush=True)
        (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    bracos = ["abmil_original", "abmil_padronizado", "gat_original", "gat_padronizado"]
    kap = {b: [resumo["execucoes"][r][b]["kappa"] for r in range(EXECUCOES)] for b in bracos}
    resumo["kappa_media_desvio"] = {b: [round(float(np.mean(v)), 4), round(float(np.std(v, ddof=1)), 4)] for b, v in kap.items()}
    resumo["gat_padr_menos_abmil_orig_por_execucao"] = [round(a - b, 4) for a, b in zip(kap["gat_padronizado"], kap["abmil_original"])]
    resumo["efeito_grafo_padronizado"] = [round(a - b, 4) for a, b in zip(kap["gat_padronizado"], kap["abmil_padronizado"])]
    resumo["efeito_padronizacao_gat"] = [round(a - b, 4) for a, b in zip(kap["gat_padronizado"], kap["gat_original"])]
    for m in ("especificidade_benigno", "sensibilidade_cancer", "acuracia_exata", "auc_benigno_x_cancer"):
        resumo[f"{m}_media"] = {b: round(float(np.mean([resumo["execucoes"][r][b][m] for r in range(EXECUCOES)])), 4) for b in bracos}
    resumo["criterio_S1"] = all(d > 0 for d in resumo["gat_padr_menos_abmil_orig_por_execucao"])
    resumo["criterio_S2"] = resumo["kappa_media_desvio"]["gat_padronizado"][0] >= KAPPA_MIN
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "execucoes"}, indent=1, ensure_ascii=False))
    print(f"S1 {'SIM' if resumo['criterio_S1'] else 'NÃO'} | S2 {'SIM' if resumo['criterio_S2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
