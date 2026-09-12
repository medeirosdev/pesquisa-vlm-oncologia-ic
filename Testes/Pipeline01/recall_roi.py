"""
Mede recall do filtro de tecido (estágio 1) contra RoIs anotados de verdade.

Ground truth: os recortes de RoI da lâmina no dataset oficial BRACS_RoI (já
extraídos pelo BRACS, um PNG por RoI anotado por um patologista). Cada
recorte é localizado na lâmina via template matching (contra o nível ~16x da
pirâmide), convertido para as coordenadas do nível ~32x (o mesmo usado na
máscara de tecido) e comparado à máscara: recall = fração da área do RoI
coberta por "tecido" segundo cada filtro.

Uso:
    .venv/bin/python recall_roi.py
"""

import csv
import glob
import json
from pathlib import Path

import cv2
import numpy as np
import tifffile
from PIL import Image

from filtro_tecido import (
    carregar_thumbnail,
    filtro_otsu_saturacao,
    filtro_otsu_saturacao_morfologia,
    ler_caminho_lamina,
)

BASE_DIR = Path(__file__).parent
CAMINHOS_MD = BASE_DIR.parent.parent / "Caminhos" / "caminhos.md"
OUTPUT_DIR = BASE_DIR / "outputs"
LIMIAR_CONFIANCA = 0.5  # correlação mínima do template matching pra confiar no match


def ler_caminho_roi_dataset() -> Path:
    for linha in CAMINHOS_MD.read_text(encoding="utf-8").splitlines():
        if linha.strip().startswith("roi_dataset:"):
            return Path(linha.split(":", 1)[1].strip())
    raise ValueError("roi_dataset: não encontrado em caminhos.md")


def localizar_roi_na_pagina3(crop_rgb: np.ndarray, search_gray: np.ndarray, downsample_pagina3: float):
    """Template matching do RoI (assumido em resolução full-res) contra a página ~16x."""
    scale = 1.0 / downsample_pagina3
    small = cv2.resize(crop_rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    templ_gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    res = cv2.matchTemplate(search_gray, templ_gray, cv2.TM_CCOEFF_NORMED)
    _, correlacao, _, (x, y) = cv2.minMaxLoc(res)
    h, w = templ_gray.shape
    return correlacao, (x, y, w, h)


def main():
    caminho_svs = ler_caminho_lamina()
    roi_root = ler_caminho_roi_dataset()
    crops = sorted(glob.glob(str(roi_root / "*" / "*" / f"{caminho_svs.stem}_*.png")))
    print(f"{len(crops)} RoIs encontrados para {caminho_svs.stem}")
    if not crops:
        raise FileNotFoundError(f"Nenhum RoI encontrado em {roi_root} para {caminho_svs.stem}")

    tif = tifffile.TiffFile(str(caminho_svs))
    largura_full = tif.pages[0].shape[1]

    page3 = tif.pages[3].asarray()  # ~16x, usado só pra localizar os RoIs
    ds3 = largura_full / page3.shape[1]
    search_gray = cv2.cvtColor(page3, cv2.COLOR_RGB2GRAY)

    rgb4 = carregar_thumbnail(caminho_svs)  # ~32x, o mesmo nível da máscara
    ds4 = largura_full / rgb4.shape[1]
    fator_3_para_4 = ds4 / ds3
    hsv4 = cv2.cvtColor(rgb4, cv2.COLOR_RGB2HSV)

    mascaras = {
        "01_otsu_saturacao": filtro_otsu_saturacao(hsv4, rgb4),
        "02_otsu_saturacao_morfologia": filtro_otsu_saturacao_morfologia(hsv4, rgb4),
    }

    linhas = []
    overlay = rgb4.copy()
    for caminho_crop in crops:
        nome = Path(caminho_crop).stem
        classe = nome.split(f"{caminho_svs.stem}_", 1)[1].rsplit("_", 1)[0]
        crop = np.array(Image.open(caminho_crop).convert("RGB"))

        correlacao, (x3, y3, w3, h3) = localizar_roi_na_pagina3(crop, search_gray, ds3)
        x4, y4, w4, h4 = (round(v / fator_3_para_4) for v in (x3, y3, w3, h3))
        x4, y4 = max(x4, 0), max(y4, 0)
        w4, h4 = max(w4, 1), max(h4, 1)

        linha = {
            "roi": nome,
            "classe": classe,
            "correlacao": round(float(correlacao), 3),
            "x": x4, "y": y4, "w": w4, "h": h4,
        }

        for nome_filtro, mask in mascaras.items():
            recorte_mask = mask[y4:y4 + h4, x4:x4 + w4]
            cobertura = float(np.count_nonzero(recorte_mask)) / recorte_mask.size if recorte_mask.size else 0.0
            linha[f"cobertura_{nome_filtro}"] = round(cobertura, 3)

        linhas.append(linha)
        print(f"{nome}: correlacao={correlacao:.2f} cobertura_01={linha['cobertura_01_otsu_saturacao']:.2f}")

        cor = (255, 255, 0) if correlacao >= LIMIAR_CONFIANCA else (255, 0, 255)
        cv2.rectangle(overlay, (x4, y4), (x4 + w4, y4 + h4), cor, 2)

    cv2.imwrite(str(OUTPUT_DIR / "roi_overlay.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    with open(OUTPUT_DIR / "recall_roi.csv", "w", newline="", encoding="utf-8") as f:
        campos = list(linhas[0].keys())
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(linhas)

    confiaveis = [l for l in linhas if l["correlacao"] >= LIMIAR_CONFIANCA]
    print(f"\n{len(confiaveis)}/{len(linhas)} RoIs localizados com confiança (correlação >= {LIMIAR_CONFIANCA})")

    resumo = {
        "total_rois": len(linhas),
        "rois_confiaveis": len(confiaveis),
        "limiar_confianca": LIMIAR_CONFIANCA,
    }
    for nome_filtro in mascaras:
        coberturas = [l[f"cobertura_{nome_filtro}"] for l in confiaveis]
        recall_50 = sum(1 for c in coberturas if c >= 0.5) / len(coberturas)
        recall_90 = sum(1 for c in coberturas if c >= 0.9) / len(coberturas)
        media = sum(coberturas) / len(coberturas)
        resumo[nome_filtro] = {
            "cobertura_media": round(media, 3),
            "pct_rois_cobertura_ge_50pct": round(100 * recall_50, 1),
            "pct_rois_cobertura_ge_90pct": round(100 * recall_90, 1),
        }
        print(
            f"{nome_filtro}: cobertura média={media:.2f} | "
            f"{100*recall_50:.0f}% dos RoIs com >=50% coberto | "
            f"{100*recall_90:.0f}% dos RoIs com >=90% coberto"
        )

    (OUTPUT_DIR / "recall_roi_resumo.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nDetalhe por RoI em outputs/recall_roi.csv, overlay em outputs/roi_overlay.png")


if __name__ == "__main__":
    main()
