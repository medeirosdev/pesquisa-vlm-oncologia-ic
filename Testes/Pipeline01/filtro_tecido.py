"""
Teste comparativo de filtros de segmentação de tecido (estágio 1 da Pipeline Ideia 01).

Lê o caminho da lâmina de Caminhos/caminhos.md, extrai um thumbnail de baixa
resolução (nível da pirâmide do .svs mais próximo de ~32x de downsample) e
aplica vários métodos de limiarização para separar tecido de fundo, salvando
máscara + overlay + estatísticas de cada um em outputs/, mais uma grade
comparativa única.

Uso:
    .venv/bin/python filtro_tecido.py
"""

import json
import time
from pathlib import Path

import cv2
import numpy as np
import tifffile
from skimage.filters import threshold_otsu, threshold_triangle, threshold_yen

BASE_DIR = Path(__file__).parent
CAMINHOS_MD = BASE_DIR.parent.parent / "Caminhos" / "caminhos.md"
OUTPUT_DIR = BASE_DIR / "outputs"
DOWNSAMPLE_ALVO = 32  # ver docs/pipelines.md — 32-64x é o ponto de equilíbrio


def ler_caminho_lamina() -> Path:
    texto = CAMINHOS_MD.read_text(encoding="utf-8").strip()
    caminho = Path(texto.splitlines()[0].strip())
    if not caminho.exists():
        raise FileNotFoundError(f"Lâmina não encontrada: {caminho}")
    return caminho


def carregar_thumbnail(caminho_svs: Path) -> np.ndarray:
    """Escolhe, entre as páginas da pirâmide, a mais próxima do downsample alvo."""
    tif = tifffile.TiffFile(str(caminho_svs))
    largura_full = tif.pages[0].shape[1]

    melhor_pagina, melhor_diff = None, float("inf")
    for pagina in tif.pages:
        if len(pagina.shape) != 3 or pagina.shape[2] != 3:
            continue
        downsample = largura_full / pagina.shape[1]
        if downsample < 2:  # pula a página full-res
            continue
        diff = abs(downsample - DOWNSAMPLE_ALVO)
        if diff < melhor_diff:
            melhor_pagina, melhor_diff = pagina, diff

    img = melhor_pagina.asarray()
    downsample_real = largura_full / img.shape[1]
    print(f"Thumbnail: {img.shape[1]}x{img.shape[0]} (downsample ~{downsample_real:.1f}x)")
    return img


def limpar_morfologia(mask: np.ndarray, kernel_size: int = 9) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    return mask


def filtro_otsu_saturacao(hsv: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    S = hsv[:, :, 1]
    S = cv2.medianBlur(S, 7)
    _, mask = cv2.threshold(S, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return mask


def filtro_otsu_saturacao_morfologia(hsv: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    return limpar_morfologia(filtro_otsu_saturacao(hsv, rgb))


def filtro_otsu_s_mais_v(hsv: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """Tenta recuperar tecido adiposo (pálido, S baixo) via canal V (brilho)."""
    S = cv2.medianBlur(hsv[:, :, 1], 7)
    V = cv2.medianBlur(hsv[:, :, 2], 7)
    _, mask_s = cv2.threshold(S, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # fundo branco = V muito alto; região um pouco menos brilhante que o fundo
    # também entra como tecido, mesmo com saturação baixa (caso do adipócito).
    _, mask_v_escuro = cv2.threshold(V, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = cv2.bitwise_or(mask_s, mask_v_escuro)
    return limpar_morfologia(mask)


def filtro_yen_saturacao(hsv: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    S = cv2.medianBlur(hsv[:, :, 1], 7)
    limiar = threshold_yen(S)
    mask = np.where(S > limiar, 255, 0).astype(np.uint8)
    return limpar_morfologia(mask)


def filtro_triangle_saturacao(hsv: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    S = cv2.medianBlur(hsv[:, :, 1], 7)
    limiar = threshold_triangle(S)
    mask = np.where(S > limiar, 255, 0).astype(np.uint8)
    return limpar_morfologia(mask)


def filtro_distancia_do_branco(hsv: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """Baseline ingênuo: distância euclidiana de cada pixel ao branco puro."""
    branco = np.array([255, 255, 255])
    dist = np.linalg.norm(rgb.astype(np.float32) - branco, axis=2)
    dist_u8 = np.clip(dist, 0, 255).astype(np.uint8)
    limiar = threshold_otsu(dist_u8)
    mask = np.where(dist_u8 > limiar, 255, 0).astype(np.uint8)
    return limpar_morfologia(mask)


FILTROS = {
    "01_otsu_saturacao": filtro_otsu_saturacao,
    "02_otsu_saturacao_morfologia": filtro_otsu_saturacao_morfologia,
    "03_otsu_s_mais_v": filtro_otsu_s_mais_v,
    "04_yen_saturacao": filtro_yen_saturacao,
    "05_triangle_saturacao": filtro_triangle_saturacao,
    "06_distancia_do_branco": filtro_distancia_do_branco,
}


def overlay_mascara(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    overlay = rgb.copy()
    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contornos, -1, (255, 0, 0), 3)
    tint = overlay.copy()
    tint[mask > 0] = (0.6 * tint[mask > 0] + 0.4 * np.array([0, 255, 0])).astype(np.uint8)
    return tint


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    caminho_svs = ler_caminho_lamina()
    print(f"Lâmina: {caminho_svs}")
    rgb = carregar_thumbnail(caminho_svs)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)

    cv2.imwrite(str(OUTPUT_DIR / "00_thumbnail.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    total_px = rgb.shape[0] * rgb.shape[1]
    estatisticas = {}

    for nome, funcao in FILTROS.items():
        t0 = time.time()
        mask = funcao(hsv, rgb)
        dt = time.time() - t0

        pct_tecido = 100 * float(np.count_nonzero(mask)) / total_px
        estatisticas[nome] = {"pct_tecido": round(pct_tecido, 2), "tempo_s": round(dt, 4)}
        print(f"{nome}: {pct_tecido:.1f}% tecido, {dt*1000:.1f} ms")

        cv2.imwrite(str(OUTPUT_DIR / f"{nome}.png"), mask)
        overlay = overlay_mascara(rgb, mask)
        cv2.imwrite(str(OUTPUT_DIR / f"{nome}_overlay.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    (OUTPUT_DIR / "estatisticas.json").write_text(
        json.dumps({"lamina": str(caminho_svs), "filtros": estatisticas}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    montar_grade_comparativa(rgb, estatisticas)
    print(f"\nSaída em {OUTPUT_DIR}")


def montar_grade_comparativa(rgb: np.ndarray, estatisticas: dict):
    import matplotlib.pyplot as plt

    nomes = list(FILTROS.keys())
    n = len(nomes) + 1
    cols = 3
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 5 * rows))
    axes = axes.flatten()

    axes[0].imshow(rgb)
    axes[0].set_title("thumbnail original")
    axes[0].axis("off")

    for i, nome in enumerate(nomes, start=1):
        overlay = cv2.cvtColor(cv2.imread(str(OUTPUT_DIR / f"{nome}_overlay.png")), cv2.COLOR_BGR2RGB)
        pct = estatisticas[nome]["pct_tecido"]
        axes[i].imshow(overlay)
        axes[i].set_title(f"{nome}\n{pct:.1f}% tecido")
        axes[i].axis("off")

    for j in range(n, len(axes)):
        axes[j].axis("off")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / "comparacao_grid.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    main()
