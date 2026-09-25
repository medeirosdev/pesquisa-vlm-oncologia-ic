"""Filtros de segmentação de tecido (estágio 1). `mascara_tecido` é o escolhido e congelado:
Otsu na saturação + morfologia (ver estagio1_filtro_tecido/resultados.md)."""

import cv2
import numpy as np
from skimage.filters import threshold_otsu, threshold_triangle, threshold_yen

from comum.lamina import TILE_NATIVO

LIMIAR_TECIDO = 0.5  # fração mínima de tecido pra um tile virar candidato


def limpar_morfologia(mask: np.ndarray, kernel_size: int = 9) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)


def filtro_otsu_saturacao(hsv, rgb):
    S = cv2.medianBlur(hsv[:, :, 1], 7)
    _, mask = cv2.threshold(S, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return mask


def filtro_otsu_saturacao_morfologia(hsv, rgb):
    return limpar_morfologia(filtro_otsu_saturacao(hsv, rgb))


def filtro_otsu_s_mais_v(hsv, rgb):
    """Tenta recuperar tecido pálido via brilho (V). Não funcionou na BRACS_748."""
    S = cv2.medianBlur(hsv[:, :, 1], 7)
    V = cv2.medianBlur(hsv[:, :, 2], 7)
    _, mask_s = cv2.threshold(S, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, mask_v = cv2.threshold(V, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return limpar_morfologia(cv2.bitwise_or(mask_s, mask_v))


def filtro_yen_saturacao(hsv, rgb):
    S = cv2.medianBlur(hsv[:, :, 1], 7)
    return limpar_morfologia(np.where(S > threshold_yen(S), 255, 0).astype(np.uint8))


def filtro_triangle_saturacao(hsv, rgb):
    S = cv2.medianBlur(hsv[:, :, 1], 7)
    return limpar_morfologia(np.where(S > threshold_triangle(S), 255, 0).astype(np.uint8))


def filtro_distancia_do_branco(hsv, rgb):
    dist = np.linalg.norm(rgb.astype(np.float32) - np.array([255, 255, 255]), axis=2)
    dist_u8 = np.clip(dist, 0, 255).astype(np.uint8)
    return limpar_morfologia(np.where(dist_u8 > threshold_otsu(dist_u8), 255, 0).astype(np.uint8))


FILTROS = {
    "01_otsu_saturacao": filtro_otsu_saturacao,
    "02_otsu_saturacao_morfologia": filtro_otsu_saturacao_morfologia,
    "03_otsu_s_mais_v": filtro_otsu_s_mais_v,
    "04_yen_saturacao": filtro_yen_saturacao,
    "05_triangle_saturacao": filtro_triangle_saturacao,
    "06_distancia_do_branco": filtro_distancia_do_branco,
}


def mascara_tecido(rgb: np.ndarray) -> np.ndarray:
    return filtro_otsu_saturacao_morfologia(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), rgb)


def grade_candidatos(lamina, mask: np.ndarray, ds_mask: float) -> list[tuple[int, int]]:
    """Grade de tiles de 512px no nível 0, mantendo só os com >= LIMIAR_TECIDO de tecido na máscara."""
    candidatos = []
    for y0 in range(0, lamina.altura - TILE_NATIVO, TILE_NATIVO):
        for x0 in range(0, lamina.largura - TILE_NATIVO, TILE_NATIVO):
            recorte = mask[int(y0 / ds_mask):int((y0 + TILE_NATIVO) / ds_mask),
                           int(x0 / ds_mask):int((x0 + TILE_NATIVO) / ds_mask)]
            if recorte.size and np.count_nonzero(recorte) / recorte.size >= LIMIAR_TECIDO:
                candidatos.append((x0, y0))
    return candidatos
