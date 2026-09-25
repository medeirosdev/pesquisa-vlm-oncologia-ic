"""
Classificação por patch com banco de frases por classe BRACS.

Todos os candidatos da lâmina que caem dentro de RoIs de uma única classe herdam essa
classe; cada um é classificado pelo argmax entre os bancos de classe. Compara com o
baseline de sempre chutar a classe majoritária.

Uso:
    .venv/bin/python validacao/banco_por_classe.py --svs BRACS_1370
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from classificacao import acuracia, baseline_maioria, classificar, embeddings_de_classe
from comum.lamina import dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import CLASSES_BRACS, carregar_rois, rotular_tiles


def rodar(svs=None) -> dict:
    stem = resolver_svs(svs).stem
    embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rois = [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5]
    rotulados = rotular_tiles(xy, rois)
    reais = [r["classe_real"] for r in rotulados]
    presentes = [c for c in CLASSES_BRACS if c in set(reais)]
    vetores = embs[[r["idx"] for r in rotulados]] if rotulados else embs[:0]

    pred7 = classificar(vetores, embeddings_de_classe(CLASSES_BRACS)) if rotulados else []
    pred_pres = classificar(vetores, embeddings_de_classe(presentes)) if len(presentes) > 1 else list(reais)

    resumo = {
        "lamina": stem,
        "n_patches_rotulados": len(rotulados),
        "distribuicao_real": dict(Counter(reais)),
        "acuracia_7_classes": acuracia(reais, pred7),
        "acuracia_classes_presentes": acuracia(reais, pred_pres) if len(presentes) > 1 else None,
        "baseline_maioria": baseline_maioria(reais),
        "preditas_7_classes": dict(Counter(pred7)),
        "matriz_confusao_7": {c: dict(Counter(p for r, p in zip(reais, pred7) if r == c)) for c in presentes},
    }
    saida = dir_resultados(stem, "validacao")
    (saida / "banco_por_classe.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    print(json.dumps(rodar(parser.parse_args().svs), indent=2, ensure_ascii=False))
