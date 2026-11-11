"""
Generalização pra outro órgão: o mesmo MIL com atenção (mil_atencao.py), sem nenhum ajuste, em pulmão — adenocarcinoma
(TCGA-LUAD) × carcinoma escamoso (TCGA-LUSC), lâminas de diagnóstico do TCGA.

Fixado ANTES de baixar as lâminas (commit anterior aos resultados):
  Lâminas: scripts/lista_tcga_pulmao.tsv — uma por paciente, 100 pacientes de cada projeto sorteados com semente 0;
     treino 60 + 60, teste 40 + 40 (pacientes diferentes).
  Patches: amostra de até 2.000 patches de tecido de 128 µm (lado em pixels pela resolução da lâmina), embeddings
     do UNI2-h, pelo mesmo pré-processamento do BRACS (scripts/tcga_baixar_e_embutir.py).
  Modelo e treino: os de mil_atencao.py (atenção com porta, 40 épocas, 5 sementes, média), com 2 classes.
  Critério de "funcionou", no teste: AUC LUAD × LUSC >= 0,85 E acurácia balanceada >= 0,75.
  Também reportado (sem critério): intervalo de 95% da AUC por bootstrap (2.000 reamostragens, semente 0); acerto
     por classe; resolução das lâminas (20x/40x); lâminas que falharem no download ou na leitura (ficam de fora e
     são listadas).

Uso (venv do projeto; GPU se houver; depois de tcga_baixar_e_embutir.py):
    .venv/bin/python validacao/tcga_mil.py
"""

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import torch

from comum.lamina import RESULTADOS_DIR

LISTA = Path(__file__).resolve().parent.parent / "scripts" / "lista_tcga_pulmao.tsv"
CLASSES = ["TCGA-LUAD", "TCGA-LUSC"]
AUC_MIN = 0.85
BA_MIN = 0.75
N_BOOTSTRAP = 2000
SAIDA = RESULTADOS_DIR / "tcga_mil"


def main():
    from mil_atencao import SEMENTES, auc, treinar
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    pasta = RESULTADOS_DIR / "tcga_pulmao"
    prontas = [l for l in linhas if (pasta / l["file_id"] / "meta.json").exists()]
    faltam = [l["file_name"] for l in linhas if l not in prontas]
    tr = [l for l in prontas if l["conjunto"] == "treino"]
    te = [l for l in prontas if l["conjunto"] == "teste"]
    X = {l["file_id"]: torch.from_numpy(np.load(pasta / l["file_id"] / "amostra2000.npy")) for l in prontas}
    y = {l["file_id"]: CLASSES.index(l["projeto"]) for l in prontas}
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    p = {l["file_id"]: 0.0 for l in te}
    for semente in SEMENTES:
        modelo = treinar([X[l["file_id"]] for l in tr], np.array([y[l["file_id"]] for l in tr]), semente, dispositivo, k=2)
        modelo.eval()
        with torch.no_grad():
            for l in te:
                p[l["file_id"]] += float(torch.softmax(modelo(X[l["file_id"]].to(dispositivo))[0], 0)[1]) / len(SEMENTES)
        print(f"  semente {semente} pronta", flush=True)
    pos = [p[l["file_id"]] for l in te if y[l["file_id"]] == 1]
    neg = [p[l["file_id"]] for l in te if y[l["file_id"]] == 0]
    a = auc(pos, neg)
    sens, espec = float(np.mean([v >= 0.5 for v in pos])), float(np.mean([v < 0.5 for v in neg]))
    rng, boot = random.Random(0), []
    for _ in range(N_BOOTSTRAP):
        am = [rng.choice(te) for _ in te]
        bp = [p[l["file_id"]] for l in am if y[l["file_id"]] == 1]
        bn = [p[l["file_id"]] for l in am if y[l["file_id"]] == 0]
        if bp and bn:
            boot.append(auc(bp, bn))
    metas = [json.loads((pasta / l["file_id"] / "meta.json").read_text(encoding="utf-8")) for l in prontas]
    resumo = {"n_treino": len(tr), "n_teste": len(te), "faltam": faltam,
              "auc": round(a, 3), "ic95_auc": [round(float(np.percentile(boot, 2.5)), 3), round(float(np.percentile(boot, 97.5)), 3)],
              "acuracia_balanceada": round((sens + espec) / 2, 3),
              "por_classe": {"TCGA-LUAD": f"{sum(v < 0.5 for v in neg)}/{len(neg)}", "TCGA-LUSC": f"{sum(v >= 0.5 for v in pos)}/{len(pos)}"},
              "resolucoes": dict(Counter(f"{m['mpp']:.2f} µm/px" for m in metas)),
              "por_lamina": {l["file_name"]: {"real": l["projeto"], "p_lusc": round(p[l["file_id"]], 3)} for l in te}}
    resumo["funcionou"] = a >= AUC_MIN and resumo["acuracia_balanceada"] >= BA_MIN
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"treino {len(tr)}, teste {len(te)}, faltam {len(faltam)} | resoluções {resumo['resolucoes']}")
    print(f"AUC LUAD × LUSC {resumo['auc']} (IC95 {resumo['ic95_auc']}) | acurácia balanceada {resumo['acuracia_balanceada']} | {resumo['por_classe']}")
    print(f"Critério fixado antes (AUC >= {AUC_MIN} e acurácia balanceada >= {BA_MIN}): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
