"""
Teste de validade discriminativa dos descritores do estágio 3 (bruto vs.
normalizado), usando a classe real dos RoIs anotados como pseudo-rótulo.

Ideia: os RoIs do BRACS_RoI já vêm com classe no nome do arquivo (ADH,
DCIS, IC...). Para cada patch selecionado no estágio 2 que cai dentro de
algum RoI anotado, herda a classe daquele RoI. Depois checa: os achados do
estágio 3 (bruto ou normalizado) variam de verdade entre classes
diferentes, ou colapsam no mesmo achado independente da classe real —
o que seria evidência de que o método não está discriminando nada, só
repetindo o viés já documentado em resultados03.md.

Não afirma "a classe X deveria dar o achado Y" (isso seria eu inventando
ground-truth de patologia) — só mede se cada método é internamente
consistente por classe e diferente entre classes.

Uso:
    .venv/bin/python validacao_classe.py --k 128
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).parent
ESTAGIO1_OUTPUTS = BASE_DIR.parent / "outputs"          # recall_roi.csv (script original, não a cópia em estagio1/)
ESTAGIO3_OUTPUTS = BASE_DIR.parent / "estagio3" / "outputs"
OUTPUTS_ROOT = BASE_DIR / "outputs"


def bbox_sobrepoe(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or
                a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svs-stem", default="BRACS_748")
    parser.add_argument("--k", type=int, default=128)
    args = parser.parse_args()

    stem = args.svs_stem
    output_dir = OUTPUTS_ROOT / stem
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- RoIs reais, com classe extraída do nome do arquivo ---
    with open(ESTAGIO1_OUTPUTS / stem / "recall_roi.csv", newline="", encoding="utf-8") as f:
        rois_page4 = list(csv.DictReader(f))

    import sys
    import tifffile
    sys.path.insert(0, str(BASE_DIR.parent / "estagio1"))
    from filtro_tecido import resolver_caminho_svs, carregar_thumbnail

    caminho_svs = resolver_caminho_svs(None)
    rgb4 = carregar_thumbnail(caminho_svs)
    tif = tifffile.TiffFile(str(caminho_svs))
    ds4 = tif.pages[0].shape[1] / rgb4.shape[1]  # fator page4 -> nativo, ~32x, mesmo usado na pipeline inteira

    rois_nativo = []
    for r in rois_page4:
        classe = r["roi"].split(f"{stem}_", 1)[1].rsplit("_", 1)[0]
        rois_nativo.append({
            "classe": classe,
            "x": int(r["x"]) * ds4, "y": int(r["y"]) * ds4,
            "w": int(r["w"]) * ds4, "h": int(r["h"]) * ds4,
        })
    print(f"{len(rois_nativo)} RoIs carregados, classes: {sorted(set(r['classe'] for r in rois_nativo))}")

    # --- descritores das duas versões, mesmo k ---
    bruto = json.loads((ESTAGIO3_OUTPUTS / stem / f"estagio3_descritores_k{args.k}.json").read_text())["descritores"]
    norm = json.loads((ESTAGIO3_OUTPUTS / stem / f"estagio3_descritores_k{args.k}_norm.json").read_text())["descritores"]

    TILE_NATIVO = 512

    def anexar_classe(descritores):
        linhas = []
        for d in descritores:
            box = {"x": d["x0"], "y": d["y0"], "w": TILE_NATIVO, "h": TILE_NATIVO}
            classes_batidas = [r["classe"] for r in rois_nativo if bbox_sobrepoe(box, r)]
            linhas.append({**d, "classes": sorted(set(classes_batidas))})
        return linhas

    bruto_c = anexar_classe(bruto)
    norm_c = anexar_classe(norm)

    n_com_classe = sum(1 for d in bruto_c if d["classes"])
    print(f"{n_com_classe}/{len(bruto_c)} patches selecionados caem dentro de algum RoI anotado (têm classe real)")

    def tabela_por_classe(descritores_c, rotulo):
        por_classe = defaultdict(Counter)
        for d in descritores_c:
            for c in d["classes"]:
                por_classe[c][tuple(d["achados"])] += 1
        print(f"\n--- {rotulo} ---")
        resumo = {}
        for classe in sorted(por_classe):
            contagem = por_classe[classe]
            total = sum(contagem.values())
            top_achado, freq = contagem.most_common(1)[0]
            print(f"  classe {classe} (n={total}): achado mais comum = {top_achado} ({freq}/{total})")
            resumo[classe] = {"n": total, "achado_mais_comum": list(top_achado), "freq": freq}
        return resumo

    resumo_bruto = tabela_por_classe(bruto_c, "BRUTO")
    resumo_norm = tabela_por_classe(norm_c, "NORMALIZADO")

    # --- veredito simples: quantas classes distintas têm achado dominante diferente? ---
    def n_achados_distintos(resumo):
        return len(set(tuple(v["achado_mais_comum"]) for v in resumo.values()))

    print(f"\nClasses com achado dominante distinto entre si — bruto: {n_achados_distintos(resumo_bruto)}/{len(resumo_bruto)} | "
          f"normalizado: {n_achados_distintos(resumo_norm)}/{len(resumo_norm)}")
    print("(1/N = colapsa tudo no mesmo achado, não discrimina nada. N/N = achado dominante muda em toda classe.)")

    (output_dir / f"validacao_classe_k{args.k}.json").write_text(
        json.dumps({
            "n_patches_com_classe": n_com_classe,
            "total_patches": len(bruto_c),
            "bruto": resumo_bruto,
            "normalizado": resumo_norm,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaída em {output_dir}")


if __name__ == "__main__":
    main()
