"""
Refinamento de agregacao_por_roi.py: em vez de agregar todos os patches do
RoI igualmente (que deu 27,6%, mal acima do patch isolado), separa em
"borda" (perto do limite da caixa do RoI) e "interior" (bem no meio), e
classifica cada grupo separado. Hipótese: a distinção DCIS/IC é sobre a
camada mioepitelial na borda do ducto — um patch bem no interior da lesão
não carrega essa informação, não importa quantos você agregue com ele.

Limitação registrada: só temos a caixa retangular (bounding box) do RoI,
não o contorno real do tecido — "borda da caixa" é uma aproximação de
"borda da lesão", não a mesma coisa.

Uso:
    .venv/bin/python agregacao_por_borda.py --margem 512
"""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import open_clip
import torch

BASE_DIR = Path(__file__).parent
ESTAGIO1_OUTPUTS = BASE_DIR.parent / "outputs"
ESTAGIO2_OUTPUTS = BASE_DIR.parent / "estagio2" / "outputs"
OUTPUTS_ROOT = BASE_DIR / "outputs"
TILE_NATIVO = 512

from banco_por_classe import BANCO_POR_CLASSE  # noqa: E402


def bbox_sobrepoe(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or
                a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--margem", type=float, default=TILE_NATIVO,
                         help="distância (px nativo) da borda da caixa do RoI pra um patch contar como 'borda'")
    parser.add_argument("--min-patches", type=int, default=2)
    args = parser.parse_args()

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
        rois_nativo.append({"roi": r["roi"], "classe": classe, "x": int(r["x"]) * ds4, "y": int(r["y"]) * ds4,
                             "w": int(r["w"]) * ds4, "h": int(r["h"]) * ds4})

    e2_dir = ESTAGIO2_OUTPUTS / stem
    embs = np.load(e2_dir / "estagio2_embeddings.npy")
    with open(e2_dir / "estagio2_embeddings_xy.csv", newline="", encoding="utf-8") as f:
        xy = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]

    # --- separa cada patch em 'borda' ou 'interior', por RoI ---
    grupos_por_roi = defaultdict(lambda: {"borda": [], "interior": []})
    for i, (x0, y0) in enumerate(xy):
        px, py = x0 + TILE_NATIVO / 2, y0 + TILE_NATIVO / 2
        box = {"x": x0, "y": y0, "w": TILE_NATIVO, "h": TILE_NATIVO}
        for roi in rois_nativo:
            if not bbox_sobrepoe(box, roi):
                continue
            dist = min(px - roi["x"], (roi["x"] + roi["w"]) - px,
                       py - roi["y"], (roi["y"] + roi["h"]) - py)
            grupo = "borda" if dist <= args.margem else "interior"
            grupos_por_roi[roi["roi"]][grupo].append(i)

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
            emb_por_classe[classe] = emb / emb.norm(dim=-1, keepdim=True)

    def classificar(indices):
        if not indices:
            return None
        emb_medio = torch.from_numpy(embs[indices]).to(device).mean(dim=0, keepdim=True)
        emb_medio = emb_medio / emb_medio.norm()
        with torch.no_grad():
            scores = {c: (emb_medio @ emb_por_classe[c].T).max().item() for c in classes_ordem}
        return max(scores, key=scores.get)

    resultado = {"borda": [], "interior": [], "todos": []}
    n_rois_avaliados = 0
    for roi in rois_nativo:
        grupos = grupos_por_roi[roi["roi"]]
        todos_idx = grupos["borda"] + grupos["interior"]
        if len(todos_idx) < args.min_patches:
            continue
        n_rois_avaliados += 1
        resultado["todos"].append(classificar(todos_idx) == roi["classe"])
        if len(grupos["borda"]) >= args.min_patches:
            resultado["borda"].append(classificar(grupos["borda"]) == roi["classe"])
        if len(grupos["interior"]) >= args.min_patches:
            resultado["interior"].append(classificar(grupos["interior"]) == roi["classe"])

    print(f"margem={args.margem}px | {n_rois_avaliados} RoIs avaliados (min {args.min_patches} patches)")
    for grupo, acertos in resultado.items():
        if acertos:
            print(f"  {grupo:10s}: {sum(acertos)/len(acertos):.1%} ({sum(acertos)}/{len(acertos)} RoIs com esse grupo)")
        else:
            print(f"  {grupo:10s}: sem RoIs suficientes")

    (output_dir / "agregacao_por_borda_resultado.json").write_text(
        json.dumps({"margem": args.margem, "min_patches": args.min_patches,
                    "acuracia_borda": sum(resultado["borda"]) / len(resultado["borda"]) if resultado["borda"] else None,
                    "acuracia_interior": sum(resultado["interior"]) / len(resultado["interior"]) if resultado["interior"] else None,
                    "acuracia_todos": sum(resultado["todos"]) / len(resultado["todos"]) if resultado["todos"] else None,
                    "n_rois_borda": len(resultado["borda"]), "n_rois_interior": len(resultado["interior"]),
                    "n_rois_todos": len(resultado["todos"])}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaída em {output_dir / 'agregacao_por_borda_resultado.json'}")


if __name__ == "__main__":
    main()
