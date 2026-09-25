"""
O descritor do estágio 3 consegue dizer "benigno"? A categoria sugerida pra cada patch
(benigno / atípico / maligno) bate com a categoria real do RoI em que ele cai?

Roda sobre todos os tiles rotulados da lâmina (não só o top-k do roteador), com o
descritor bruto e o normalizado. Baseline = sempre chutar a categoria majoritária.

Uso:
    .venv/bin/python validacao/categoria_descritor.py --svs BRACS_1370
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

from comum.bancos import CATEGORIA_DA_CLASSE
from comum.lamina import dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import carregar_rois, rotular_tiles
from descritores import categorias, similaridades


def rodar(svs=None) -> dict:
    stem = resolver_svs(svs).stem
    embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rotulados = rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
    reais = [CATEGORIA_DA_CLASSE[r["classe_real"]] for r in rotulados]
    idx = [r["idx"] for r in rotulados]

    resumo = {"lamina": stem, "n_patches_rotulados": len(rotulados), "distribuicao_real": dict(Counter(reais)),
              "baseline_maioria": round(Counter(reais).most_common(1)[0][1] / len(reais), 4) if reais else None}
    for rotulo, normalizar in (("bruto", False), ("norm", True)):
        cats = categorias(similaridades(embs, normalizar=normalizar))  # z-score contra todos os candidatos
        preditas = [cats[i] for i in idx]
        resumo[rotulo] = {
            "acuracia": round(sum(a == b for a, b in zip(reais, preditas)) / len(reais), 4) if reais else None,
            "preditas": dict(Counter(preditas)),
            "matriz_confusao": {c: dict(Counter(p for r, p in zip(reais, preditas) if r == c)) for c in sorted(set(reais))},
            "categorias_todos_candidatos": dict(Counter(cats)),
        }
    (dir_resultados(stem, "validacao") / "categoria_descritor.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    print(json.dumps(rodar(parser.parse_args().svs), indent=2, ensure_ascii=False))
