"""
Os achados do estágio 3 variam entre classes reais, ou colapsam no mesmo achado?

Para cada variante do estágio 3 (bruto, normalizado, ensemble...), os patches
selecionados que caem dentro de um RoI herdam a classe dele; mede quantas classes têm
achado dominante diferente entre si (1/N = não discrimina nada). Não afirma "a classe X
deveria dar o achado Y" — só mede consistência dentro da classe e diferença entre classes.

Uso:
    .venv/bin/python validacao/validacao_classe.py --svs BRACS_748 --k 128 --sufixos "" _norm _ensemble _ensemble_norm
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comum.lamina import dir_resultados, resolver_svs
from comum.rois import bbox_sobrepoe, caixa_tile, carregar_rois


def rodar(svs=None, k=128, sufixos=("", "_norm")) -> dict:
    stem = resolver_svs(svs).stem
    rois = [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5]
    e3 = dir_resultados(stem, "estagio3")
    resultado = {}
    for sufixo in sufixos:
        caminho = e3 / f"estagio3_descritores_k{k}{sufixo}.json"
        if not caminho.exists():
            continue
        por_classe = defaultdict(Counter)
        for d in json.loads(caminho.read_text(encoding="utf-8"))["descritores"]:
            classes = {r["classe"] for r in rois if bbox_sobrepoe(caixa_tile(d["x0"], d["y0"]), r)}
            if len(classes) == 1:
                por_classe[classes.pop()][frozenset(d["achados"])] += 1  # ordem das frases não importa
        dominantes = {c: sorted(cont.most_common(1)[0][0]) for c, cont in por_classe.items()}
        resultado[sufixo.strip("_") or "bruto"] = {
            "por_classe": {c: {"n": sum(cont.values()), "achado_dominante": dominantes[c]}
                           for c, cont in por_classe.items()},
            "classes_com_achado_distinto": f"{len({tuple(v) for v in dominantes.values()})}/{len(dominantes)}",
        }
    saida = dir_resultados(stem, "validacao")
    (saida / f"validacao_classe_k{k}.json").write_text(json.dumps(resultado, indent=2, ensure_ascii=False),
                                                       encoding="utf-8")
    return {"lamina": stem, "k": k, "variantes": resultado}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    parser.add_argument("--k", type=int, default=128)
    parser.add_argument("--sufixos", nargs="+", default=["", "_norm"])
    a = parser.parse_args()
    print(json.dumps(rodar(a.svs, a.k, a.sufixos), indent=2, ensure_ascii=False))
