"""
Estágio 1 — compara 6 filtros de segmentação de tecido num thumbnail da lâmina (~32x).

Métrica aqui é só "% de tecido detectado", que não tem ground-truth — serve pra
inspeção visual. A validação de verdade é o recall_roi.py (recall contra RoIs anotados).

Uso:
    .venv/bin/python estagio1_filtro_tecido/filtro_tecido.py --svs BRACS_1370
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from comum.lamina import Lamina, dir_resultados, resolver_svs
from comum.tecido import FILTROS


def overlay_mascara(rgb, mask):
    tint = rgb.copy()
    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(tint, contornos, -1, (255, 0, 0), 3)
    tint[mask > 0] = (0.6 * tint[mask > 0] + 0.4 * np.array([0, 255, 0])).astype(np.uint8)
    return tint


def rodar(svs=None) -> dict:
    lamina = Lamina(resolver_svs(svs))
    saida = dir_resultados(lamina.stem, "estagio1")
    rgb, ds = lamina.thumbnail(32)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    cv2.imwrite(str(saida / "00_thumbnail.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    estatisticas = {}
    for nome, funcao in FILTROS.items():
        t0 = time.time()
        mask = funcao(hsv, rgb)
        estatisticas[nome] = {"pct_tecido": round(100 * np.count_nonzero(mask) / mask.size, 2),
                              "tempo_s": round(time.time() - t0, 4)}
        cv2.imwrite(str(saida / f"{nome}.png"), mask)
        cv2.imwrite(str(saida / f"{nome}_overlay.png"), cv2.cvtColor(overlay_mascara(rgb, mask), cv2.COLOR_RGB2BGR))

    montar_grade(rgb, estatisticas, saida)
    resumo = {"lamina": lamina.stem, "downsample_thumbnail": round(ds, 2), "filtros": estatisticas}
    (saida / "estatisticas.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


def montar_grade(rgb, estatisticas, saida):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    nomes = list(FILTROS)
    fig, axes = plt.subplots(3, 3, figsize=(15, 15))
    axes = axes.flatten()
    axes[0].imshow(rgb)
    axes[0].set_title("thumbnail original")
    for i, nome in enumerate(nomes, start=1):
        axes[i].imshow(cv2.cvtColor(cv2.imread(str(saida / f"{nome}_overlay.png")), cv2.COLOR_BGR2RGB))
        axes[i].set_title(f"{nome}\n{estatisticas[nome]['pct_tecido']:.1f}% tecido")
    for ax in axes:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(saida / "comparacao_grid.png", dpi=120)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs", help="nome (BRACS_1370) ou caminho da lâmina; padrão: svs: do caminhos.md")
    r = rodar(parser.parse_args().svs)
    for nome, s in r["filtros"].items():
        print(f"{nome}: {s['pct_tecido']:.1f}% tecido")
