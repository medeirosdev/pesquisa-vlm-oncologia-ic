"""UNI2-h (MahmoodLab): encoder de imagem de patologia, sem encoder de texto. Carregado uma vez por
processo, com embeddings cacheados por lâmina e por conjunto de tiles.

Pré-processamento igual ao do QuiltNet (comum/modelo.py): tile de 512 px no nível 0 (40x) reduzido
pra 256 px (~20x) e depois pra 224 px, normalização do ImageNet — como na página do modelo.
"""

import csv
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import torch

from comum.lamina import TILE_TRABALHO, dir_resultados, ler_caminhos
from comum.modelo import dispositivo

MEDIA_IMAGENET = np.array([0.485, 0.456, 0.406], np.float32)
DESVIO_IMAGENET = np.array([0.229, 0.224, 0.225], np.float32)
LOTE = 32


def pesos_uni2h() -> Path:
    return Path(ler_caminhos()["modelos_dir"]) / "UNI2H" / "pytorch_model.bin"


@lru_cache(maxsize=1)
def carregar_uni2h():
    import timm
    kw = {"img_size": 224, "patch_size": 14, "depth": 24, "num_heads": 24, "init_values": 1e-5, "embed_dim": 1536,
          "mlp_ratio": 2.66667 * 2, "num_classes": 0, "no_embed_class": True, "mlp_layer": timm.layers.SwiGLUPacked,
          "act_layer": torch.nn.SiLU, "reg_tokens": 8, "dynamic_img_size": True}  # da página do UNI2-h
    modelo = timm.create_model("vit_giant_patch14_224", pretrained=False, **kw)
    modelo.load_state_dict(torch.load(pesos_uni2h(), map_location="cpu"), strict=True)
    modelo = modelo.eval().to(dispositivo())
    return modelo.half() if dispositivo() == "cuda" else modelo


def _preparar(img_512):
    img = cv2.resize(img_512[..., :3], (TILE_TRABALHO, TILE_TRABALHO), interpolation=cv2.INTER_AREA)
    img = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)
    return ((img.astype(np.float32) / 255 - MEDIA_IMAGENET) / DESVIO_IMAGENET).transpose(2, 0, 1)


def embeddings_uni2h(lamina, xy, nome: str) -> np.ndarray:
    """Embeddings (não normalizados, 1536-d) dos tiles `xy`. Salvos em resultados/<lamina>/uni2h/<nome>.npy;
    se o arquivo existir com a mesma lista de tiles, só lê."""
    pasta = dir_resultados(lamina.stem, "uni2h")
    emb_path, xy_path = pasta / f"{nome}.npy", pasta / f"{nome}_xy.csv"
    xy = [tuple(p) for p in xy]
    if emb_path.exists() and xy_path.exists():
        with open(xy_path, newline="", encoding="utf-8") as f:
            if [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)] == xy:
                return np.load(emb_path)

    modelo = carregar_uni2h()
    embs, t0 = [], time.time()
    for i in range(0, len(xy), LOTE):
        lote = np.stack([_preparar(lamina.janela_nativa(x0, y0)) for x0, y0 in xy[i:i + LOTE]])
        x = torch.from_numpy(lote).to(dispositivo())
        with torch.no_grad():
            embs.append(modelo(x.half() if dispositivo() == "cuda" else x).float().cpu().numpy())
    embs = np.concatenate(embs) if embs else np.zeros((0, 1536), np.float32)
    print(f"  UNI2-h: {len(xy)} tiles em {time.time() - t0:.0f}s")

    np.save(emb_path, embs)
    with open(xy_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x0", "y0"])
        w.writerows(xy)
    return embs
