"""QuiltNet-B-32: carregado uma vez por processo, com embeddings de imagem cacheados por lâmina."""

import csv
import os
import time
from functools import lru_cache

import numpy as np
import torch
from PIL import Image

from comum.lamina import ler_caminhos

NOME_MODELO = "hf-hub:wisdomik/QuiltNet-B-32"


def _configurar_cache_hf():
    # downloads de modelo vão pro HD externo, não pro disco local
    os.environ.setdefault("HF_HOME", str(ler_caminhos().get("modelos_dir", "")) + "/hf-cache")


def dispositivo() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def carregar_quiltnet():
    _configurar_cache_hf()
    import open_clip  # depois de configurar HF_HOME
    model, _, preprocess = open_clip.create_model_and_transforms(NOME_MODELO)
    tokenizer = open_clip.get_tokenizer(NOME_MODELO)
    return model.to(dispositivo()).eval(), preprocess, tokenizer


def codificar_textos(frases: list[str], templates: list[str] = ("{}",)) -> torch.Tensor:
    """Um embedding normalizado por frase; com vários templates, média das variantes."""
    model, _, tokenizer = carregar_quiltnet()
    saida = []
    with torch.no_grad():
        for frase in frases:
            emb = model.encode_text(tokenizer([t.format(frase) for t in templates]).to(dispositivo()))
            emb = emb / emb.norm(dim=-1, keepdim=True)
            media = emb.mean(dim=0)
            saida.append(media / media.norm())
    return torch.stack(saida)


def embeddings_da_lamina(lamina, candidatos_xy, pasta_estagio2) -> np.ndarray:
    """Embeddings de imagem de cada tile candidato. Calcula uma vez e salva; depois só lê do disco
    (qualquer banco de frases ou estágio posterior reaproveita sem GPU)."""
    emb_path = pasta_estagio2 / "estagio2_embeddings.npy"
    xy_path = pasta_estagio2 / "estagio2_embeddings_xy.csv"
    if emb_path.exists() and xy_path.exists():
        with open(xy_path, newline="", encoding="utf-8") as f:
            xy_cache = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]
        if xy_cache == list(candidatos_xy):
            return np.load(emb_path)
        print("  grade de candidatos mudou — recalculando embeddings")

    from comum.lamina import TILE_TRABALHO
    import cv2
    model, preprocess, _ = carregar_quiltnet()
    embs, t0 = [], time.time()
    for i in range(0, len(candidatos_xy), 64):
        lote = candidatos_xy[i:i + 64]
        imgs = [preprocess(Image.fromarray(cv2.resize(lamina.janela_nativa(x0, y0), (TILE_TRABALHO, TILE_TRABALHO),
                                                      interpolation=cv2.INTER_AREA))) for x0, y0 in lote]
        with torch.no_grad():
            e = model.encode_image(torch.stack(imgs).to(dispositivo()))
            embs.append((e / e.norm(dim=-1, keepdim=True)).cpu().numpy())
    embs = np.concatenate(embs, axis=0) if embs else np.zeros((0, 512), dtype=np.float32)
    print(f"  embeddings de {len(candidatos_xy)} tiles em {time.time() - t0:.0f}s")

    np.save(emb_path, embs)
    with open(xy_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["x0", "y0"])
        w.writerows(candidatos_xy)
    return embs


def carregar_embeddings_cacheados(pasta_estagio2) -> tuple[np.ndarray, list[tuple[int, int]]]:
    embs = np.load(pasta_estagio2 / "estagio2_embeddings.npy")
    with open(pasta_estagio2 / "estagio2_embeddings_xy.csv", newline="", encoding="utf-8") as f:
        xy = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]
    return embs, xy
