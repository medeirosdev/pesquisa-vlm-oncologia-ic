"""
DCIS vs. IC pela posição dos núcleos (CellViT). O CellViT não tem classe "mioepitelial"; a
camada é inferida pelo arranjo: no DCIS o tumor tem UMA fronteira lisa com o estroma (membrana
basal + camada mioepitelial entre os dois), então poucos núcleos neoplásicos encostam em núcleos
conjuntivos; no IC o tumor se infiltra no estroma e os dois se misturam em pequena escala.

Fixado ANTES de rodar (commit anterior aos resultados):
  - Amostra: até 250 tiles por classe (DCIS, IC) em cada lâmina com as duas classes
    (BRACS_748, BRACS_773, BRACS_295), sorteio com semente 0.
  - Tile entra só se tiver >= 20 núcleos neoplásicos dentro do tile (tile de "DCIS" que é só
    estroma entre ductos não informa nada).
  - Medida principal: fração dos núcleos neoplásicos do tile que têm pelo menos um núcleo
    conjuntivo a <= 20 µm (80 px a 0,25 µm/px). Vizinhos procurados na janela de 1024 inteira.
  - Hipótese: maior no IC. Avaliação: AUC (DCIS vs. IC) dentro de cada lâmina, sem limiar.
  - Critério de "funcionou": AUC > 0,5 (IC maior) nas TRÊS lâminas.
  Medidas secundárias (só descritivas, não entram no critério): núcleos neoplásicos por tile,
  fração de conjuntivos entre os núcleos do tile.

Roda no ambiente do CellViT:
    "/media/medeiros/HD 1TB/venvs/cellvit/bin/python" validacao/dcis_ic_nucleos.py
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from scipy.spatial import cKDTree

from comum.lamina import RESULTADOS_DIR, Lamina, dir_resultados, resolver_svs
from comum.rois import carregar_rois, rotular_tiles

LAMINAS = ["BRACS_748", "BRACS_773", "BRACS_295"]
N_POR_CLASSE = 250
SEMENTE = 0
MIN_NEOPLASICOS = 20
RAIO_PX = 80  # 20 µm a 0,25 µm/px


def amostra_da_lamina(stem):
    with open(dir_resultados(stem, "estagio2") / "estagio2_embeddings_xy.csv", newline="", encoding="utf-8") as f:
        xy = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]
    rot = rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
    rng = random.Random(SEMENTE)
    amostra = []
    for classe in ("DCIS", "IC"):
        da_classe = sorted((r for r in rot if r["classe_real"] == classe), key=lambda r: (r["y0"], r["x0"]))
        amostra += rng.sample(da_classe, min(N_POR_CLASSE, len(da_classe)))
    return amostra


def segmentar_amostra(stem, amostra):
    """Roda o CellViT nos tiles que ainda não têm nucleos_<x0>_<y0>.json (cache)."""
    pasta = dir_resultados(stem, "nucleos")
    faltam = [r for r in amostra if not (pasta / f"nucleos_{r['x0']}_{r['y0']}.json").exists()]
    if not faltam:
        return
    import torch
    from nucleos_cellvit import MARGEM, TIPOS, carregar_modelo, ler_janela, segmentar
    from comum.lamina import TILE_NATIVO

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, media, desvio = carregar_modelo(dispositivo)
    lamina = Lamina(resolver_svs(stem))
    for i, r in enumerate(faltam, 1):
        x0, y0 = r["x0"], r["y0"]
        celulas = segmentar(modelo, media, desvio, ler_janela(lamina, x0, y0), dispositivo)
        nucleos = []
        for c in celulas.values():
            cx, cy = c["centroid"][0], c["centroid"][1]
            dentro = MARGEM <= cx < MARGEM + TILE_NATIVO and MARGEM <= cy < MARGEM + TILE_NATIVO
            nucleos.append({"x": int(x0 - MARGEM + cx), "y": int(y0 - MARGEM + cy), "tipo": TIPOS.get(int(c["type"]), "?"),
                            "prob": round(float(c["type_prob"]), 3), "no_tile": bool(dentro)})
        (pasta / f"nucleos_{x0}_{y0}.json").write_text(json.dumps(
            {"lamina": stem, "x0": x0, "y0": y0, "classe": r["classe_real"], "nucleos": nucleos}), encoding="utf-8")
        if i % 50 == 0:
            print(f"  {stem}: {i}/{len(faltam)} tiles segmentados", flush=True)


def medidas_do_tile(nucleos):
    neo_tile = np.array([[n["x"], n["y"]] for n in nucleos if n["tipo"] == "neoplasico" and n["no_tile"]])
    conj = np.array([[n["x"], n["y"]] for n in nucleos if n["tipo"] == "conjuntivo"])
    no_tile = [n for n in nucleos if n["no_tile"]]
    if len(neo_tile) < MIN_NEOPLASICOS:
        return None
    if len(conj):
        d, _ = cKDTree(conj).query(neo_tile, k=1)
        encostados = float(np.mean(d <= RAIO_PX))
    else:
        encostados = 0.0
    return {"neo_encostados_em_conjuntivo": encostados, "n_neoplasicos": len(neo_tile),
            "frac_conjuntivos": sum(n["tipo"] == "conjuntivo" for n in no_tile) / len(no_tile)}


def auc(pos, neg):
    """P(valor de um IC > valor de um DCIS), empates contam meio (Mann-Whitney)."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    if not len(pos) or not len(neg):
        return None
    maior = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return round(float(maior / (len(pos) * len(neg))), 3)


def main():
    resumo = {}
    for stem in LAMINAS:
        amostra = amostra_da_lamina(stem)
        print(f"{stem}: amostra {sum(r['classe_real'] == 'DCIS' for r in amostra)} DCIS, "
              f"{sum(r['classe_real'] == 'IC' for r in amostra)} IC", flush=True)
        segmentar_amostra(stem, amostra)
        pasta = dir_resultados(stem, "nucleos")
        por_classe = {"DCIS": [], "IC": []}
        for r in amostra:
            d = json.loads((pasta / f"nucleos_{r['x0']}_{r['y0']}.json").read_text(encoding="utf-8"))
            m = medidas_do_tile(d["nucleos"])
            if m is not None:
                por_classe[r["classe_real"]].append(m)
        res = {"n_tiles_com_tumor": {c: len(v) for c, v in por_classe.items()},
               "n_tiles_amostrados": {c: sum(r["classe_real"] == c for r in amostra) for c in por_classe}}
        for chave in ("neo_encostados_em_conjuntivo", "n_neoplasicos", "frac_conjuntivos"):
            ic = [m[chave] for m in por_classe["IC"]]
            dc = [m[chave] for m in por_classe["DCIS"]]
            res[chave] = {"mediana_DCIS": round(float(np.median(dc)), 3) if dc else None,
                          "mediana_IC": round(float(np.median(ic)), 3) if ic else None,
                          "AUC_IC_maior": auc(ic, dc)}
        resumo[stem] = res

    principal = "neo_encostados_em_conjuntivo"
    resumo["funcionou"] = all((resumo[s][principal]["AUC_IC_maior"] or 0) > 0.5 for s in LAMINAS)
    (RESULTADOS_DIR / "dcis_ic_nucleos.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                        encoding="utf-8")
    print()
    for s in LAMINAS:
        r = resumo[s]
        print(f"{s}: tiles com tumor {r['n_tiles_com_tumor']} (de {r['n_tiles_amostrados']})")
        for chave in (principal, "n_neoplasicos", "frac_conjuntivos"):
            m = r[chave]
            print(f"  {chave:<30} mediana DCIS {m['mediana_DCIS']}  IC {m['mediana_IC']}  AUC {m['AUC_IC_maior']}")
    print(f"\nCritério fixado antes (AUC > 0,5 nas três lâminas): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
