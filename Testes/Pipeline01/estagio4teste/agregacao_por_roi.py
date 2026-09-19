"""
Teste da hipótese registrada em problemas_e_metrica.md: se a informação que
discrimina DCIS de IC está no padrão agregado da região, não no patch
isolado, então classificar por RoI inteiro (juntando a evidência de todos
os patches que caem nele) deveria ir melhor que classificar patch a patch
(banco_por_classe.py deu 23,9%, pior que o baseline de 80,2%).

Método: agrupa os candidatos por RoI (não só por classe, como antes) e
para cada RoI com pelo menos N patches, faz duas agregações e classifica:

  (a) por embedding — média dos embeddings de imagem dos patches do RoI,
      depois similaridade contra os bancos de classe;
  (b) por voto — classifica cada patch individualmente (argmax por patch,
      como em banco_por_classe.py) e usa o voto majoritário do RoI.

Compara a acurácia por RoI das duas contra o baseline "sempre a classe
majoritária" e contra a acurácia por patch já medida.

Uso:
    .venv/bin/python agregacao_por_roi.py --min-patches 3
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
    parser.add_argument("--min-patches", type=int, default=3,
                         help="RoIs com menos candidatos que isso ficam de fora (agregação de 1 patch não testa nada)")
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
    print(f"{len(xy)} candidatos, {len(rois_nativo)} RoIs")

    # --- agrupa candidatos por RoI individual (não só por classe) ---
    patches_por_roi = defaultdict(list)
    for i, (x0, y0) in enumerate(xy):
        box = {"x": x0, "y": y0, "w": TILE_NATIVO, "h": TILE_NATIVO}
        for roi in rois_nativo:
            if bbox_sobrepoe(box, roi):
                patches_por_roi[roi["roi"]].append(i)

    rois_com_dado = [r for r in rois_nativo if len(patches_por_roi[r["roi"]]) >= args.min_patches]
    print(f"{len(rois_com_dado)}/{len(rois_nativo)} RoIs com >= {args.min_patches} patches candidatos "
          f"(distribuição de classe: {Counter(r['classe'] for r in rois_com_dado)})")

    # --- bancos de classe ---
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

    def scores_patch(idx):
        emb_patch = torch.from_numpy(embs[idx:idx + 1]).to(device)
        with torch.no_grad():
            return {c: (emb_patch @ emb_por_classe[c].T).max().item() for c in classes_ordem}

    acertos_embedding = acertos_voto = 0
    acertos_patch_individual = total_patch_individual = 0
    detalhe = []
    for roi in rois_com_dado:
        indices = patches_por_roi[roi["roi"]]

        # (a) agregação por embedding: média dos embeddings do RoI, depois classifica uma vez
        emb_medio = torch.from_numpy(embs[indices]).to(device).mean(dim=0, keepdim=True)
        emb_medio = emb_medio / emb_medio.norm()
        with torch.no_grad():
            scores_agregado = {c: (emb_medio @ emb_por_classe[c].T).max().item() for c in classes_ordem}
        pred_embedding = max(scores_agregado, key=scores_agregado.get)

        # (b) agregação por voto: classifica cada patch, maioria decide
        preds_individuais = []
        for idx in indices:
            s = scores_patch(idx)
            pred = max(s, key=s.get)
            preds_individuais.append(pred)
            total_patch_individual += 1
            acertos_patch_individual += pred == roi["classe"]
        pred_voto = Counter(preds_individuais).most_common(1)[0][0]

        acertos_embedding += pred_embedding == roi["classe"]
        acertos_voto += pred_voto == roi["classe"]
        detalhe.append({"roi": roi["roi"], "classe_real": roi["classe"], "n_patches": len(indices),
                         "pred_embedding_medio": pred_embedding, "pred_voto_majoritario": pred_voto})

    n = len(rois_com_dado)
    baseline_maioria = max(Counter(r["classe"] for r in rois_com_dado).values()) / n

    print(f"\n--- Por RoI (n={n} RoIs) ---")
    print(f"Agregação por embedding médio: {acertos_embedding/n:.1%} ({acertos_embedding}/{n})")
    print(f"Agregação por voto majoritário: {acertos_voto/n:.1%} ({acertos_voto}/{n})")
    print(f"Baseline (sempre a classe majoritária): {baseline_maioria:.1%}")
    print(f"\n--- Por patch individual, para comparação (n={total_patch_individual} patches) ---")
    print(f"Acurácia por patch: {acertos_patch_individual/total_patch_individual:.1%}")

    (output_dir / "agregacao_por_roi_resultado.json").write_text(
        json.dumps({
            "min_patches": args.min_patches,
            "n_rois": n,
            "acuracia_embedding_medio": round(acertos_embedding / n, 4),
            "acuracia_voto_majoritario": round(acertos_voto / n, 4),
            "baseline_maioria": round(baseline_maioria, 4),
            "acuracia_por_patch": round(acertos_patch_individual / total_patch_individual, 4),
            "detalhe": detalhe,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaída em {output_dir / 'agregacao_por_roi_resultado.json'}")


if __name__ == "__main__":
    main()
