"""
Segmentação e classificação de núcleos com o CellViT-256 (x40, pesos oficiais), em tiles
rotulados como DCIS ou IC. Base pra inferir a camada mioepitelial pela posição dos núcleos:
o CellViT (tipos do PanNuke) não tem classe "mioepitelial", mas dá pra ver se os núcleos
neoplásicos estão contornados por uma fileira de outros núcleos (DCIS) ou encostados direto
no conjuntivo (IC).

Roda num ambiente separado (numpy<2, opencv fixo), no HD:
    "/media/medeiros/HD 1TB/venvs/cellvit/bin/python" validacao/nucleos_cellvit.py --svs BRACS_748 --n 10

Pra cada tile, lê uma janela de 1024x1024 (nível 0, 40x) centrada no tile de 512, pra que os
núcleos da borda do tile tenham vizinhos. Guarda os núcleos da janela inteira (coordenadas no
nível 0) e marca quais caem dentro do tile central.

Saída em resultados/<lamina>/nucleos/: nucleos_<x0>_<y0>.json e overlay_<classe>_<x0>_<y0>.png.
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from comum.lamina import TILE_NATIVO, Lamina, dir_resultados, ler_caminhos, resolver_svs
from comum.rois import carregar_rois, rotular_tiles

JANELA = 1024
MARGEM = (JANELA - TILE_NATIVO) // 2
TIPOS = {1: "neoplasico", 2: "inflamatorio", 3: "conjuntivo", 4: "morto", 5: "epitelial"}
CORES = {1: (255, 0, 0), 2: (0, 200, 0), 3: (0, 120, 255), 4: (255, 255, 0), 5: (255, 0, 255)}  # RGB


def pesos_cellvit() -> Path:
    return Path(ler_caminhos()["modelos_dir"]) / "cellvit" / "CellViT-256-x40-AMP.pth"


def carregar_modelo(dispositivo):
    from cellvit.models.cell_segmentation.cellvit_256 import CellViT256

    ck = torch.load(pesos_cellvit(), map_location="cpu", weights_only=False)
    conf = ck["config"]  # achatado: "data.num_nuclei_classes" etc.
    modelo = CellViT256(model256_path=None,
                        num_nuclei_classes=conf["data.num_nuclei_classes"],
                        num_tissue_classes=conf["data.num_tissue_classes"],
                        regression_loss=conf.get("model.regression_loss", False))
    modelo.load_state_dict(ck["model_state_dict"])
    media = conf.get("transformations.normalize.mean", (0.5, 0.5, 0.5))
    desvio = conf.get("transformations.normalize.std", (0.5, 0.5, 0.5))
    return modelo.eval().to(dispositivo), np.array(media, np.float32), np.array(desvio, np.float32)


def ler_janela(lamina, x0, y0):
    """Janela JANELAxJANELA do nível 0 centrada no tile; fora da lâmina vira branco."""
    xa, ya = x0 - MARGEM, y0 - MARGEM
    img = np.full((JANELA, JANELA, 3), 255, np.uint8)
    sx0, sy0 = max(xa, 0), max(ya, 0)
    sx1, sy1 = min(xa + JANELA, lamina.largura), min(ya + JANELA, lamina.altura)
    pedaco = lamina.janela_nativa(sx0, sy0, tamanho=JANELA)[: sy1 - sy0, : sx1 - sx0]
    img[sy0 - ya: sy1 - ya, sx0 - xa: sx1 - xa] = pedaco[..., :3]
    return img


@torch.no_grad()
def segmentar(modelo, media, desvio, img, dispositivo):
    x = torch.from_numpy(((img.astype(np.float32) / 255 - media) / desvio).transpose(2, 0, 1))[None].to(dispositivo)
    with torch.autocast("cuda", dtype=torch.float16, enabled=dispositivo == "cuda"):
        pred = modelo(x)
    pred = {k: v.float() for k, v in pred.items() if k in ("nuclei_binary_map", "nuclei_type_map", "hv_map")}
    pred["nuclei_binary_map"] = F.softmax(pred["nuclei_binary_map"], dim=1)
    pred["nuclei_type_map"] = F.softmax(pred["nuclei_type_map"], dim=1)
    _, celulas = modelo.calculate_instance_map(pred, magnification=40)
    return celulas[0]


def rodar(svs=None, n=10, semente=0):
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    lamina = Lamina(resolver_svs(svs))
    stem = lamina.stem
    with open(dir_resultados(stem, "estagio2") / "estagio2_embeddings_xy.csv", newline="", encoding="utf-8") as f:
        xy = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]
    rot = rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
    rng = random.Random(semente)
    amostra = []
    for classe in ("DCIS", "IC"):
        da_classe = [r for r in rot if r["classe_real"] == classe]
        amostra += rng.sample(da_classe, min(n, len(da_classe)))

    modelo, media, desvio = carregar_modelo(dispositivo)
    saida = dir_resultados(stem, "nucleos")
    resumo = []
    for r in amostra:
        x0, y0 = r["x0"], r["y0"]
        img = ler_janela(lamina, x0, y0)
        celulas = segmentar(modelo, media, desvio, img, dispositivo)
        nucleos = []
        overlay = img.copy()
        for c in celulas.values():
            cy, cx = c["centroid"][1], c["centroid"][0]
            dentro = MARGEM <= cx < MARGEM + TILE_NATIVO and MARGEM <= cy < MARGEM + TILE_NATIVO
            nucleos.append({"x": int(x0 - MARGEM + cx), "y": int(y0 - MARGEM + cy), "tipo": TIPOS.get(int(c["type"]), "?"),
                            "prob": round(float(c["type_prob"]), 3), "no_tile": bool(dentro)})
            cv2.drawContours(overlay, [np.asarray(c["contour"], np.int32)], -1, CORES.get(int(c["type"]), (0, 0, 0)), 2)
        cv2.rectangle(overlay, (MARGEM, MARGEM), (MARGEM + TILE_NATIVO, MARGEM + TILE_NATIVO), (0, 0, 0), 2)
        (saida / f"nucleos_{x0}_{y0}.json").write_text(json.dumps(
            {"lamina": stem, "x0": x0, "y0": y0, "classe": r["classe_real"], "janela": JANELA, "nucleos": nucleos}),
            encoding="utf-8")
        cv2.imwrite(str(saida / f"overlay_{r['classe_real']}_{x0}_{y0}.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
        cont = {t: sum(1 for m in nucleos if m["no_tile"] and m["tipo"] == t) for t in TIPOS.values()}
        resumo.append({"classe": r["classe_real"], "x0": x0, "y0": y0, **cont})
        print(r["classe_real"], x0, y0, cont)
    (saida / "resumo_piloto.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--svs", default="BRACS_748")
    p.add_argument("--n", type=int, default=10, help="tiles por classe")
    a = p.parse_args()
    rodar(a.svs, a.n)
