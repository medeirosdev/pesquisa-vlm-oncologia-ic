"""
Banco de frases por classe: em vez de um banco único "suspeito" tentando
discriminar tudo de uma vez (que falhou nos testes anteriores — ver
resultados_estagio4teste.md), cria um banco de frases dedicado por classe
BRACS (ADH, DCIS, IC) com termos que descrevem especificamente o que
diferencia uma da outra, e testa como classificação: pra cada patch,
similaridade máxima dentro de cada banco de classe, prevista = argmax.

Testa contra TODOS os 15.138 candidatos do estágio 2 (não só o top-128 do
roteador) — amostra maior e sem o viés de "só os que o roteador achou
suspeitos", pra também pegar RoIs de ADH que não apareciam antes.

Os termos de cada banco vêm de critério diagnóstico padrão de patologia
mamária (WHO / critérios de Page), não são inventados:
- ADH: proliferação atípica focal, população celular monomórfica, atipia
  nuclear leve, envolvimento parcial do ducto.
- DCIS: carcinoma confinado ao ducto, com camada mioepitelial preservada
  (a membrana basal está intacta) — comedonecrose é achado clássico.
- IC: invasão do estroma, perda da camada mioepitelial (é o que define
  invasão), reação desmoplásica.

Uso:
    .venv/bin/python banco_por_classe.py
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import open_clip
import torch

BASE_DIR = Path(__file__).parent
ESTAGIO1_OUTPUTS = BASE_DIR.parent / "outputs"
ESTAGIO2_OUTPUTS = BASE_DIR.parent / "estagio2" / "outputs"
OUTPUTS_ROOT = BASE_DIR / "outputs"
TILE_NATIVO = 512

BANCO_POR_CLASSE = {
    "ADH": [
        "atypical ductal hyperplasia",
        "focal atypical epithelial proliferation",
        "mild nuclear atypia",
        "monomorphic epithelial cell population",
        "partial duct involvement by atypical cells",
    ],
    "DCIS": [
        "ductal carcinoma in situ",
        "intraductal proliferation with preserved basement membrane",
        "comedonecrosis",
        "cribriform intraductal pattern",
        "intact myoepithelial cell layer",
    ],
    "IC": [
        "invasive carcinoma",
        "stromal invasion",
        "loss of myoepithelial cell layer",
        "desmoplastic stromal reaction",
        "infiltrating tumor cells within stroma",
    ],
}


def bbox_sobrepoe(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or
                a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def main():
    stem = "BRACS_748"
    output_dir = OUTPUTS_ROOT / stem
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(BASE_DIR.parent / "estagio1"))
    from filtro_tecido import resolver_caminho_svs, carregar_thumbnail
    import tifffile

    caminho_svs = resolver_caminho_svs(None)
    rgb4 = carregar_thumbnail(caminho_svs)
    tif = tifffile.TiffFile(str(caminho_svs))
    ds4 = tif.pages[0].shape[1] / rgb4.shape[1]

    with open(ESTAGIO1_OUTPUTS / stem / "recall_roi.csv", newline="", encoding="utf-8") as f:
        rois_page4 = list(csv.DictReader(f))
    rois_nativo = []
    for r in rois_page4:
        classe = r["roi"].split(f"{stem}_", 1)[1].rsplit("_", 1)[0]
        rois_nativo.append({"classe": classe, "x": int(r["x"]) * ds4, "y": int(r["y"]) * ds4,
                             "w": int(r["w"]) * ds4, "h": int(r["h"]) * ds4})
    print(f"{len(rois_nativo)} RoIs, classes: {sorted(set(r['classe'] for r in rois_nativo))}")

    # --- TODOS os candidatos do estágio 2, não só o top-k do roteador ---
    e2_dir = ESTAGIO2_OUTPUTS / stem
    embs = np.load(e2_dir / "estagio2_embeddings.npy")
    with open(e2_dir / "estagio2_embeddings_xy.csv", newline="", encoding="utf-8") as f:
        xy = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]
    print(f"{len(xy)} candidatos do estágio 2 carregados (cache, sem GPU pra imagem)")

    # --- rotula: cada candidato que cai dentro de algum RoI vira exemplo com classe real ---
    rotulados = []
    for i, (x0, y0) in enumerate(xy):
        box = {"x": x0, "y": y0, "w": TILE_NATIVO, "h": TILE_NATIVO}
        classes = sorted(set(r["classe"] for r in rois_nativo if bbox_sobrepoe(box, r)))
        if len(classes) == 1:  # descarta ambíguos (caem em RoIs de classes diferentes)
            rotulados.append({"idx": i, "x0": x0, "y0": y0, "classe_real": classes[0]})
    print(f"{len(rotulados)} candidatos caem dentro de exatamente 1 RoI anotado (amostra rotulada)")
    print(f"  distribuição real: {Counter(r['classe_real'] for r in rotulados)}")

    # --- banco de frases por classe ---
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, _ = open_clip.create_model_and_transforms("hf-hub:wisdomik/QuiltNet-B-32")
    tokenizer = open_clip.get_tokenizer("hf-hub:wisdomik/QuiltNet-B-32")
    model = model.to(device).eval()

    classes_ordem = list(BANCO_POR_CLASSE.keys())
    emb_por_classe = {}
    with torch.no_grad():
        for classe, frases in BANCO_POR_CLASSE.items():
            tok = tokenizer(frases).to(device)
            emb = model.encode_text(tok)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            emb_por_classe[classe] = emb

    # --- classifica cada exemplo rotulado: argmax da similaridade máxima por classe ---
    acertos = 0
    matriz = {c_real: Counter() for c_real in classes_ordem}
    detalhe = []
    for r in rotulados:
        emb_patch = torch.from_numpy(embs[r["idx"]:r["idx"] + 1]).to(device)
        scores_classe = {}
        with torch.no_grad():
            for classe in classes_ordem:
                sim = (emb_patch @ emb_por_classe[classe].T).max().item()
                scores_classe[classe] = sim
        predita = max(scores_classe, key=scores_classe.get)
        correto = predita == r["classe_real"]
        acertos += correto
        matriz[r["classe_real"]][predita] += 1
        detalhe.append({**r, "classe_predita": predita, "scores": {k: round(v, 4) for k, v in scores_classe.items()}, "acertou": correto})

    acuracia = acertos / len(rotulados)
    baseline_maioria = max(Counter(r["classe_real"] for r in rotulados).values()) / len(rotulados)

    print(f"\nAcurácia (3 classes, argmax banco-por-classe): {acuracia:.1%} ({acertos}/{len(rotulados)})")
    print(f"Baseline 'sempre prever a classe majoritária': {baseline_maioria:.1%}")
    print("\nMatriz de confusão (linha = classe real, coluna = predita):")
    print("real\\pred  " + "  ".join(f"{c:>6}" for c in classes_ordem))
    for c_real in classes_ordem:
        linha = "  ".join(f"{matriz[c_real][c_pred]:>6}" for c_pred in classes_ordem)
        print(f"{c_real:>9}  {linha}")

    (output_dir / "banco_por_classe_resultado.json").write_text(
        json.dumps({
            "banco_por_classe": BANCO_POR_CLASSE,
            "n_rotulados": len(rotulados),
            "distribuicao_real": dict(Counter(r["classe_real"] for r in rotulados)),
            "acuracia": round(acuracia, 4),
            "baseline_maioria": round(baseline_maioria, 4),
            "matriz_confusao": {c: dict(matriz[c]) for c in classes_ordem},
            "detalhe": detalhe,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaída em {output_dir / 'banco_por_classe_resultado.json'}")


if __name__ == "__main__":
    main()
