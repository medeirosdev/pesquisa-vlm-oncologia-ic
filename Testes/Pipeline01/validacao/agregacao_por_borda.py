"""
Classificação por RoI usando só os patches perto da borda da caixa do RoI, só os do
interior, ou todos. Hipótese: a diferença DCIS/IC está na borda do ducto (camada
mioepitelial), não no meio da lesão.

Limitação: só temos a caixa retangular do RoI, não o contorno real da lesão — "borda da
caixa" é uma aproximação de "borda da lesão".

Uso:
    .venv/bin/python validacao/agregacao_por_borda.py --svs BRACS_1370 --margem 512
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from classificacao import acuracia, baseline_maioria, classificar, embeddings_de_classe, media_normalizada
from comum.lamina import TILE_NATIVO, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import CLASSES_BRACS, bbox_sobrepoe, caixa_tile, carregar_rois

MIN_PATCHES = 2


def rodar(svs=None, margem=TILE_NATIVO, min_patches=MIN_PATCHES) -> dict:
    stem = resolver_svs(svs).stem
    embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rois = [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5]

    grupos = []  # (classe, idx_borda, idx_interior)
    for r in rois:
        borda, interior = [], []
        for i, (x0, y0) in enumerate(xy):
            if not bbox_sobrepoe(caixa_tile(x0, y0), r):
                continue
            px, py = x0 + TILE_NATIVO / 2, y0 + TILE_NATIVO / 2
            dist = min(px - r["x"], r["x"] + r["w"] - px, py - r["y"], r["y"] + r["h"] - py)
            (borda if dist <= margem else interior).append(i)
        grupos.append((r["classe"], borda, interior))

    presentes = [c for c in CLASSES_BRACS if c in {g[0] for g in grupos}]
    resumo = {"lamina": stem, "margem": margem}
    for rotulo, classes in (("7_classes", CLASSES_BRACS), ("classes_presentes", presentes)):
        if len(classes) < 2:
            continue
        emb_c = embeddings_de_classe(classes)
        for nome, seletor in (("borda", lambda g: g[1]), ("interior", lambda g: g[2]),
                              ("todos", lambda g: g[1] + g[2])):
            validos = [(g[0], seletor(g)) for g in grupos if len(seletor(g)) >= min_patches]
            reais = [c for c, _ in validos]
            pred = [classificar(media_normalizada(embs[idx]), emb_c)[0] for _, idx in validos]
            resumo[f"{nome}_{rotulo}"] = {"n_rois": len(validos), "acuracia": acuracia(reais, pred),
                                          "baseline_maioria": baseline_maioria(reais)}

    saida = dir_resultados(stem, "validacao")
    (saida / "agregacao_por_borda.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    parser.add_argument("--margem", type=float, default=TILE_NATIVO)
    parser.add_argument("--min-patches", type=int, default=MIN_PATCHES)
    a = parser.parse_args()
    print(json.dumps(rodar(a.svs, a.margem, a.min_patches), indent=2, ensure_ascii=False))
