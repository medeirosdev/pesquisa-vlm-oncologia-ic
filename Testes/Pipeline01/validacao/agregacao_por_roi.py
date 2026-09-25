"""
Classificação por RoI inteiro, juntando a evidência dos patches que caem nele.

Duas agregações: média dos embeddings do RoI (classifica uma vez) e voto majoritário
das classificações por patch. Ambas ignoram onde cada patch está dentro do RoI.

Uso:
    .venv/bin/python validacao/agregacao_por_roi.py --svs BRACS_1370
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from classificacao import acuracia, baseline_maioria, classificar, embeddings_de_classe, media_normalizada
from comum.lamina import dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import CLASSES_BRACS, bbox_sobrepoe, caixa_tile, carregar_rois

MIN_PATCHES = 3


def rodar(svs=None, min_patches=MIN_PATCHES) -> dict:
    stem = resolver_svs(svs).stem
    embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rois = [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5]
    grupos = []
    for r in rois:
        idx = [i for i, (x0, y0) in enumerate(xy) if bbox_sobrepoe(caixa_tile(x0, y0), r)]
        if len(idx) >= min_patches:
            grupos.append((r["classe"], idx))

    reais = [c for c, _ in grupos]
    presentes = [c for c in CLASSES_BRACS if c in set(reais)]
    resumo = {"lamina": stem, "n_rois": len(grupos), "distribuicao_real": dict(Counter(reais)),
              "baseline_maioria": baseline_maioria(reais)}
    for rotulo, classes in (("7_classes", CLASSES_BRACS), ("classes_presentes", presentes)):
        if not grupos or len(classes) < 2:
            resumo[f"acuracia_media_{rotulo}"] = resumo[f"acuracia_voto_{rotulo}"] = None
            continue
        emb_c = embeddings_de_classe(classes)
        pred_media = [classificar(media_normalizada(embs[idx]), emb_c)[0] for _, idx in grupos]
        pred_voto = [Counter(classificar(embs[idx], emb_c)).most_common(1)[0][0] for _, idx in grupos]
        resumo[f"acuracia_media_{rotulo}"] = acuracia(reais, pred_media)
        resumo[f"acuracia_voto_{rotulo}"] = acuracia(reais, pred_voto)

    saida = dir_resultados(stem, "validacao")
    (saida / "agregacao_por_roi.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    parser.add_argument("--min-patches", type=int, default=MIN_PATCHES)
    a = parser.parse_args()
    print(json.dumps(rodar(a.svs, a.min_patches), indent=2, ensure_ascii=False))
