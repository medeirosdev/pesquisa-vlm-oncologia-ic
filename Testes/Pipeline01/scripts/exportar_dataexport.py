"""
Exporta pra DataExport/ (raiz do repositório) os núcleos do CellViT já calculados, pra uso em outro projeto.

Nada é recalculado: só reformata o que está em resultados/.
  - resultados/<lâmina>/nucleos/nucleos_<x0>_<y0>.json (validacao/dcis_ic_nucleos.py): BRACS_295, BRACS_748,
    BRACS_773 -> DataExport/bracs_nucleos/<lâmina>.csv.gz e DataExport/bracs_laminas.csv (rótulo e MPP)
  - resultados/NuCLS/cellvit_por_fov.json e nucls_cellvit.json (validacao/nucls_cellvit.py)
    -> DataExport/nucls/cellvit_por_fov.csv.gz e DataExport/nucls/cellvit_x_nucls_por_classe.csv

Uso (venv do projeto; o HD só é preciso pra ler o MPP das lâminas):
    .venv/bin/python scripts/exportar_dataexport.py
"""

import csv
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tifffile

from comum.lamina import RESULTADOS_DIR, resolver_svs
from comum.rois import info_lamina

SAIDA = Path(__file__).resolve().parents[3] / "DataExport"
LAMINAS = ["BRACS_295", "BRACS_748", "BRACS_773"]
CLASSES = ["neoplasico", "conjuntivo", "inflamatorio", "epitelial"]


def mpp(s):
    with tifffile.TiffFile(resolver_svs(s)) as t:
        m = re.search(r"MPP\s*=\s*([0-9.]+)", t.pages[0].description or "")
    return float(m.group(1)) if m else None


def bracs():
    (SAIDA / "bracs_nucleos").mkdir(parents=True, exist_ok=True)
    linhas = []
    for s in LAMINAS:
        arquivos = sorted((RESULTADOS_DIR / s / "nucleos").glob("nucleos_*.json"))
        n, tipos, classes = 0, Counter(), Counter()
        with gzip.open(SAIDA / "bracs_nucleos" / f"{s}.csv.gz", "wt", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["lamina", "tile_x0", "tile_y0", "classe_tile", "x", "y", "tipo", "prob", "no_tile"])
            for a in arquivos:
                d = json.loads(a.read_text(encoding="utf-8"))
                classes[d["classe"]] += 1
                for c in d["nucleos"]:
                    w.writerow([s, d["x0"], d["y0"], d["classe"], c["x"], c["y"], c["tipo"], c["prob"], int(c["no_tile"])])
                    n += 1
                    tipos[c["tipo"]] += 1
        info = info_lamina(s)
        linhas.append({"lamina": s, "rotulo_bracs": info["rotulo"], "conjunto": info["conjunto"], "mpp": mpp(s),
                       "tiles": len(arquivos), "tiles_por_classe": json.dumps(dict(classes), ensure_ascii=False),
                       "nucleos": n, "nucleos_por_tipo": json.dumps(dict(tipos), ensure_ascii=False)})
        print(f"  {s}: {len(arquivos)} tiles, {n} núcleos", flush=True)
    with open(SAIDA / "bracs_laminas.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)


def nucls():
    (SAIDA / "nucls").mkdir(parents=True, exist_ok=True)
    fovs = json.loads((RESULTADOS_DIR / "NuCLS" / "cellvit_por_fov.json").read_text(encoding="utf-8"))
    with gzip.open(SAIDA / "nucls" / "cellvit_por_fov.csv.gz", "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fov", "x_um", "y_um", "tipo"])
        for fov, nucleos in fovs.items():
            for x, y, t in nucleos:
                w.writerow([fov, round(x, 2), round(y, 2), t])
    r = json.loads((RESULTADOS_DIR / "NuCLS" / "nucls_cellvit.json").read_text(encoding="utf-8"))["parte1_classificacao"]
    m = r["matriz_confusao_anotado_para_cellvit"]
    with open(SAIDA / "nucls" / "cellvit_x_nucls_por_classe.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["classe", "anotados", "fracao_detectada", "pareados", "recall_entre_pareados", "precisao_entre_pareados"])
        for c in CLASSES:
            pareados = sum(m[c].values())
            vp = m[c].get(c, 0)
            preditos = sum(m[a].get(c, 0) for a in CLASSES)
            w.writerow([c, r["n_anotados"][c], r["encontrados_por_classe"][c], pareados,
                        round(vp / pareados, 3), round(vp / preditos, 3)])
    (SAIDA / "nucls" / "nucls_cellvit.json").write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  NuCLS: {len(fovs)} campos", flush=True)


if __name__ == "__main__":
    bracs()
    nucls()
