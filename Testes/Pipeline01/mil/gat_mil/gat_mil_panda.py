"""
GAT-MIL × ABMIL no PANDA (grau ISUP 0-5). Primeiro teste do GAT-MIL (gat_mil.py); se funcionar, a mesma comparação
vai pros outros datasets.

Pergunta: o ABMIL no PANDA separa câncer de benigno (AUC 0,93 provisória) mas colapsa quase tudo em ISUP 3 (kappa
0,19 provisório). Duas explicações possíveis, que este teste separa:
  (a) falta informação espacial (o Gleason é arquitetura): o GAT-MIL deve ganhar do ABMIL nos dois cenários;
  (b) o problema é a troca de centro (Radboud -> Karolinska): os dois devem ir bem dentro do Radboud e mal no
      Karolinska, e o GAT-MIL não resolve.

Fixado ANTES de rodar (commit anterior aos resultados):
  Dados: as biópsias de scripts/lista_panda.tsv (dados/panda/lista_panda.tsv depois da reorganização) com
     embeddings prontos; mesmas amostras de patches do panda_mil.py. Todas as biópsias do PANDA cabem na amostra de
     2.000 patches, então o grafo de cada uma é completo.
  Modelos: A = ABMIL (mil_atencao.treinar, k = 6); B = GAT-MIL (gat_mil.treinar, k = 6). Mesma receita, 5 sementes,
     probabilidade = média das 5; ISUP previsto = classe de maior probabilidade. Nenhum ajuste de hiperparâmetro.
  Cenário 1, entre centros: treino nas 600 do Radboud, teste nas 300 do Karolinska (como panda_mil.py).
  Cenário 2, dentro do centro: validação cruzada em 5 partes nas 600 do Radboud, estratificada por ISUP (semente 0);
     cada biópsia é prevista pelo modelo que não a viu.
  Métrica: kappa quadrático ponderado (ISUP 0-5). Diferença pareada B - A com IC 95% por bootstrap (2.000
     reamostras das biópsias, semente 0).
  Critério G1: no cenário 1, kappa(B) - kappa(A) > 0 com o limite inferior do IC 95% > 0.
  Critério G2: no cenário 2, idem.
  Leitura combinada, escrita antes:
     G1 e G2 passam -> a informação espacial ajuda, inclusive em outro centro;
     só G2 passa -> o espaço ajuda, mas a troca de centro é um problema à parte;
     nenhum passa e o kappa dentro do Radboud é alto pros dois -> o problema é a troca de centro, não o espaço;
     nenhum passa e o kappa dentro do Radboud é baixo pros dois -> nenhum dos dois aprende a graduar com 600 biópsias.
  Também reportado (sem critério): kappa de cada modelo com IC; AUC benigno × câncer; acurácia exata e a +-1;
     matrizes de confusão.
  Ressalva do cenário 2: o PANDA não informa o paciente; as 5.160 biópsias do Radboud vêm de 1.028 pacientes, então
     a mesma pessoa pode cair no treino e no teste de uma parte. Isso infla os dois modelos; a comparação pareada é o
     que conta.

Uso (venv do projeto; GPU):
    .venv/bin/python mil/gat_mil/gat_mil_panda.py
Saída: resultados/gat_mil_panda/{resumo.json, <image_id>_atencao_gat.npy}
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402
import torch  # noqa: E402

import gat_mil  # noqa: E402
import mil_atencao  # noqa: E402
from comum.lamina import RESULTADOS_DIR  # noqa: E402
from panda_mil import PASTA, auc_rank, biopsias, kappa_quadratico  # noqa: E402

K = 6
PARTES = 5
N_BOOTSTRAP = 2000
SAIDA = RESULTADOS_DIR / "gat_mil_panda"


def carregar(ids):
    X, G = {}, {}
    for i in ids:
        X[i] = torch.from_numpy(np.load(PASTA / i / "amostra2000.npy"))
        xy = np.loadtxt(PASTA / i / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        lado = json.loads((PASTA / i / "meta.json").read_text(encoding="utf-8"))["lado_px"]
        G[i] = gat_mil.arestas_vizinhos(xy, lado)
    return X, G


def prever(tr, te, X, G, y, dispositivo, guardar_atencao=False):
    """Probabilidades médias das 5 sementes, pros dois modelos."""
    P = {m: {i: np.zeros(K) for i in te} for m in "AB"}
    att = {i: np.zeros(len(X[i])) for i in te}
    ytr = np.array([y[i] for i in tr])
    for semente in mil_atencao.SEMENTES:
        a = mil_atencao.treinar([X[i] for i in tr], ytr, semente, dispositivo, k=K).eval()
        b = gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], ytr, semente, dispositivo, k=K).eval()
        with torch.no_grad():
            for i in te:
                x, g = X[i].to(dispositivo), G[i].to(dispositivo)
                P["A"][i] += torch.softmax(a(x)[0], 0).cpu().numpy() / len(mil_atencao.SEMENTES)
                logit, at, _ = b(x, g)
                P["B"][i] += torch.softmax(logit, 0).cpu().numpy() / len(mil_atencao.SEMENTES)
                att[i] += at.cpu().numpy() / len(mil_atencao.SEMENTES)
        print(f"    semente {semente} pronta", flush=True)
    if guardar_atencao:
        for i in te:
            np.save(SAIDA / f"{i}_atencao_gat.npy", att[i].astype(np.float32))
    return P


def avaliar(ids, y, P):
    real = np.array([y[i] for i in ids])
    pred = {m: np.array([int(P[m][i].argmax()) for i in ids]) for m in "AB"}
    pc = {m: np.array([1 - P[m][i][0] for i in ids]) for m in "AB"}

    def kappas(idx):
        return {m: kappa_quadratico(real[idx], pred[m][idx], K) for m in "AB"}

    k0 = kappas(np.arange(len(ids)))
    rng, boot = random.Random(0), {"A": [], "B": [], "dif": []}
    for _ in range(N_BOOTSTRAP):
        idx = np.array([rng.randrange(len(ids)) for _ in ids])
        k = kappas(idx)
        boot["A"].append(k["A"])
        boot["B"].append(k["B"])
        boot["dif"].append(k["B"] - k["A"])
    ic = {c: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for c, v in boot.items()}
    saida = {"n": len(ids), "kappa_A_abmil": round(k0["A"], 3), "ic95_A": ic["A"],
             "kappa_B_gat": round(k0["B"], 3), "ic95_B": ic["B"],
             "diferenca_B_menos_A": round(k0["B"] - k0["A"], 3), "ic95_diferenca": ic["dif"]}
    for m, nome in (("A", "abmil"), ("B", "gat")):
        conf = np.zeros((K, K), int)
        for r, p in zip(real, pred[m]):
            conf[r, p] += 1
        saida[nome] = {"auc_benigno_x_cancer": round(auc_rank(pc[m][real >= 1], pc[m][real == 0]), 3),
                       "acuracia_exata": round(float(np.mean(real == pred[m])), 3),
                       "acuracia_mais_menos_1": round(float(np.mean(np.abs(real - pred[m]) <= 1)), 3),
                       "matriz_confusao_real_x_previsto": conf.tolist()}
    saida["criterio"] = saida["diferenca_B_menos_A"] > 0 and ic["dif"][0] > 0
    return saida


def partes_estratificadas(ids, y):
    rng, parte = random.Random(0), {}
    for c in range(K):
        grupo = sorted(i for i in ids if y[i] == c)
        rng.shuffle(grupo)
        for j, i in enumerate(grupo):
            parte[i] = j % PARTES
    return parte


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas, prontas = biopsias()
    y = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X, G = carregar(tr + te)
    graus = [int(g.shape[1]) / len(X[i]) for i, g in G.items()]
    print(f"{len(tr)} treino, {len(te)} teste; arestas por patch (com o próprio): média {np.mean(graus):.2f}", flush=True)
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"

    print("Cenário 1: Radboud -> Karolinska", flush=True)
    c1 = avaliar(te, y, prever(tr, te, X, G, y, dispositivo, guardar_atencao=True))
    print(json.dumps({k: v for k, v in c1.items() if k not in ("abmil", "gat")}, ensure_ascii=False), flush=True)

    print("Cenário 2: validação cruzada dentro do Radboud", flush=True)
    parte = partes_estratificadas(tr, y)
    P2 = {"A": {}, "B": {}}
    for p in range(PARTES):
        print(f"  parte {p + 1}/{PARTES}", flush=True)
        dentro = [i for i in tr if parte[i] != p]
        fora = [i for i in tr if parte[i] == p]
        P = prever(dentro, fora, X, G, y, dispositivo)
        for m in "AB":
            P2[m].update(P[m])
    c2 = avaliar(tr, y, P2)

    resumo = {"faltam": [l["image_id"] for l in linhas if l not in prontas],
              "arestas_por_patch_media": round(float(np.mean(graus)), 2),
              "cenario1_radboud_para_karolinska": c1, "cenario2_dentro_do_radboud": c2,
              "criterio_G1": c1["criterio"], "criterio_G2": c2["criterio"]}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))
    print(f"Critério G1 (entre centros, B > A com IC > 0): {'SIM' if c1['criterio'] else 'NÃO'} | "
          f"Critério G2 (dentro do Radboud): {'SIM' if c2['criterio'] else 'NÃO'}")


if __name__ == "__main__":
    main()
