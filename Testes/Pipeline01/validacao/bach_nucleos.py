"""
Medida dos núcleos (fração de neoplásicos com um conjuntivo a <= 20 µm) nas imagens InSitu e
Invasive do BACH, pro teste 4 do plano UNI2-h (bach_dcis_ic.py). Mesma regra de dcis_ic_nucleos.py,
sem treino e sem ajuste.

Cada imagem (0,42 µm/px) é reamostrada pra 0,25 µm/px (a escala do CellViT-256-x40), segmentada
em janelas de 1024 px, e dividida em tiles de 512 px (128 µm). Pontuação da imagem = média da
medida nos tiles com >= 20 núcleos neoplásicos; imagem sem nenhum tile assim fica de fora.

Roda no ambiente do CellViT:
    "/media/medeiros/HD 1TB/venvs/cellvit/bin/python" validacao/bach_nucleos.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import numpy as np
import tifffile
import torch

from bach_dcis_ic import MPP_BACH, MPP_PIPELINE, SAIDA, imagens_bach
from comum.lamina import TILE_NATIVO
from dcis_ic_nucleos import medidas_do_tile
from nucleos_cellvit import JANELA, TIPOS, carregar_modelo, segmentar


def nucleos_da_imagem(modelo, media, desvio, rgb, dispositivo):
    f = MPP_BACH / MPP_PIPELINE
    img = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    H, W = img.shape[:2]
    Hp, Wp = -(-H // JANELA) * JANELA, -(-W // JANELA) * JANELA
    pad = np.full((Hp, Wp, 3), 255, np.uint8)
    pad[:H, :W] = img
    nucleos = []
    for y0 in range(0, Hp, JANELA):
        for x0 in range(0, Wp, JANELA):
            for c in segmentar(modelo, media, desvio, pad[y0:y0 + JANELA, x0:x0 + JANELA], dispositivo).values():
                nucleos.append({"x": x0 + float(c["centroid"][0]), "y": y0 + float(c["centroid"][1]),
                                "tipo": TIPOS.get(int(c["type"]), "?")})
    return nucleos, H, W


def main():
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, media, desvio = carregar_modelo(dispositivo)
    saida = SAIDA / "nucleos_por_imagem.json"
    feito = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else {}
    for i, (p, _) in enumerate(imagens_bach(), 1):
        if p.name in feito:
            continue
        nucleos, H, W = nucleos_da_imagem(modelo, media, desvio, tifffile.imread(p)[..., :3], dispositivo)
        valores = []
        for ty in range(0, H - TILE_NATIVO + 1, TILE_NATIVO):
            for tx in range(0, W - TILE_NATIVO + 1, TILE_NATIVO):
                marcados = [{**n, "no_tile": tx <= n["x"] < tx + TILE_NATIVO and ty <= n["y"] < ty + TILE_NATIVO}
                            for n in nucleos]
                m = medidas_do_tile(marcados)
                if m is not None:
                    valores.append(m["neo_encostados_em_conjuntivo"])
        feito[p.name] = float(np.mean(valores)) if valores else None
        saida.write_text(json.dumps(feito, indent=1), encoding="utf-8")
        if i % 10 == 0:
            print(f"  {i} imagens", flush=True)
    print(f"{sum(v is not None for v in feito.values())} de {len(feito)} imagens com tiles de tumor")


if __name__ == "__main__":
    main()
