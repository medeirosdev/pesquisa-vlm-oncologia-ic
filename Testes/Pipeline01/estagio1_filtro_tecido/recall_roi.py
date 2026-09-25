"""
Estágio 1 — recall do filtro de tecido contra os RoIs anotados pelo patologista.

Cada recorte oficial do BRACS_RoI dessa lâmina é localizado nela por template matching
(num nível ~16x da pirâmide) e comparado à máscara de tecido: recall = fração da área
do RoI que a máscara cobre. O CSV de saída (coordenadas no nível 0) é a verdade de
campo usada por todos os estágios seguintes.

Uso:
    .venv/bin/python estagio1_filtro_tecido/recall_roi.py --svs BRACS_1370
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from PIL import Image

from comum.lamina import Lamina, dir_resultados, resolver_svs
from comum.rois import classe_do_roi, listar_recortes_roi
from comum.tecido import mascara_tecido

LIMIAR_CONFIANCA = 0.5  # correlação mínima do template matching pra confiar na posição


def rodar(svs=None) -> dict:
    lamina = Lamina(resolver_svs(svs))
    saida = dir_resultados(lamina.stem, "estagio1")
    recortes = listar_recortes_roi(lamina.stem)
    if not recortes:
        raise FileNotFoundError(f"Nenhum recorte de RoI local para {lamina.stem}")

    i_busca, ds_busca = lamina.nivel_mais_proximo(16)
    busca = cv2.cvtColor(lamina.ler_nivel(i_busca), cv2.COLOR_RGB2GRAY)
    rgb, ds_thumb = lamina.thumbnail(32)
    mask = mascara_tecido(rgb)

    linhas = []
    overlay = rgb.copy()
    for caminho in recortes:
        recorte = np.array(Image.open(caminho).convert("RGB"))
        templ = cv2.cvtColor(cv2.resize(recorte, None, fx=1 / ds_busca, fy=1 / ds_busca,
                                        interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
        if templ.shape[0] >= busca.shape[0] or templ.shape[1] >= busca.shape[1] or min(templ.shape) < 8:
            print(f"  {caminho.stem}: recorte incompatível com o nível de busca, ignorado")
            continue
        _, correlacao, _, (xb, yb) = cv2.minMaxLoc(cv2.matchTemplate(busca, templ, cv2.TM_CCOEFF_NORMED))
        h, w = templ.shape
        x, y, w, h = xb * ds_busca, yb * ds_busca, w * ds_busca, h * ds_busca  # nível 0

        tx0, ty0 = int(x / ds_thumb), int(y / ds_thumb)
        tx1, ty1 = int((x + w) / ds_thumb), int((y + h) / ds_thumb)
        recorte_mask = mask[ty0:ty1, tx0:tx1]
        cobertura = np.count_nonzero(recorte_mask) / recorte_mask.size if recorte_mask.size else 0.0

        linhas.append({"roi": caminho.stem, "classe": classe_do_roi(caminho.stem),
                       "correlacao": round(float(correlacao), 3),
                       "x": round(x), "y": round(y), "w": round(w), "h": round(h),
                       "cobertura_tecido": round(float(cobertura), 3)})
        cor = (255, 255, 0) if correlacao >= LIMIAR_CONFIANCA else (255, 0, 255)
        cv2.rectangle(overlay, (tx0, ty0), (tx1, ty1), cor, 2)

    cv2.imwrite(str(saida / "roi_overlay.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    with open(saida / "recall_roi.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        writer.writeheader()
        writer.writerows(linhas)

    confiaveis = [l for l in linhas if l["correlacao"] >= LIMIAR_CONFIANCA]
    cob = [l["cobertura_tecido"] for l in confiaveis]
    resumo = {
        "lamina": lamina.stem,
        "niveis_piramide": [round(d) for d in lamina.downsamples],
        "rois_total": len(recortes),
        "rois_localizados": len(confiaveis),
        "classes": {c: sum(1 for l in linhas if l["classe"] == c) for c in sorted({l["classe"] for l in linhas})},
        "cobertura_media": round(float(np.mean(cob)), 3) if cob else None,
        "pct_rois_cobertura_ge_50": round(100 * sum(c >= 0.5 for c in cob) / len(cob), 1) if cob else None,
        "pct_rois_cobertura_ge_90": round(100 * sum(c >= 0.9 for c in cob) / len(cob), 1) if cob else None,
    }
    (saida / "recall_roi_resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs", help="nome (BRACS_1370) ou caminho da lâmina; padrão: svs: do caminhos.md")
    print(json.dumps(rodar(parser.parse_args().svs), indent=2, ensure_ascii=False))
