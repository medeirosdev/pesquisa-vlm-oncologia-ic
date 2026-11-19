"""
Gera PNGs de exemplo do dataset de pulmão (Adenocarcinoma × Carcinoma Epidermoide) para inspeção visual.
As imagens ficam em exemplos/ (fora do git: o dataset não é público). Os pacientes viram caso_01, caso_02, ...;
a tabela caso -> pasta original fica só em exemplos/casos.csv.

Uso: ../Pipeline01/.venv/bin/python exemplos.py <pasta do dataset com labels.xlsx e original/>
"""

import csv
import random
import sys
from pathlib import Path

import numpy as np
import openpyxl
from PIL import Image, ImageDraw

CLASSES = {"Adenocarcinoma": "adenocarcinoma", "Epidermoid Carcinoma": "epidermoide"}
CASOS_POR_CLASSE, CAMPOS_POR_CASO, NUCLEOS_POR_CASO = 4, 3, 8


def rotulos(raiz):
    linhas = list(openpyxl.load_workbook(raiz / "labels.xlsx", read_only=True).worksheets[0].iter_rows(values_only=True))
    out = {}
    for r in linhas[1:]:
        if r[1] and r[4]:
            a, b = str(r[1]).split("-")
            out[f"{int(a):05d}-{b}"] = r[4]
    return out


def caixa_do_nucleo(nucleo, campo):
    """Acha onde o núcleo (recorte sobre fundo branco) está no campo de origem; devolve a máscara e o canto."""
    import cv2
    a = np.asarray(nucleo.convert("RGB")).astype(np.float32)
    m = a.sum(2) < 700
    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    t, mk = a[y0:y1, x0:x1], m[y0:y1, x0:x1].astype(np.float32)
    r = cv2.matchTemplate(np.asarray(campo.convert("RGB")).astype(np.float32), t, cv2.TM_SQDIFF,
                          mask=np.repeat(mk[..., None], 3, 2))
    return mk > 0, cv2.minMaxLoc(r)[2]


def main():
    raiz = Path(sys.argv[1])
    saida = Path(__file__).resolve().parent / "exemplos"
    lab = rotulos(raiz)
    rng = random.Random(0)
    tabela = []
    for diag, nome in CLASSES.items():
        casos = rng.sample(sorted(c for c, d in lab.items() if d == diag), CASOS_POR_CLASSE)
        grade_campos, grade_nucleos = [], []
        for caso in casos:
            cod = f"caso_{len(tabela) + 1:02d}"
            tabela.append((cod, caso, nome))
            P = raiz / "original" / caso
            sub = next(s for s in P.iterdir() if s.is_dir())
            campos = rng.sample(sorted(P.glob("*.BMP")), CAMPOS_POR_CASO)
            nucleos = rng.sample(sorted(sub.glob("*.BMP")), NUCLEOS_POR_CASO)
            d = saida / nome / cod
            (d / "biopsia").mkdir(parents=True, exist_ok=True)
            (d / "nucleos").mkdir(exist_ok=True)
            for j, f in enumerate(campos, 1):
                im = Image.open(f).convert("RGB")
                im.save(d / "biopsia" / f"campo_{j}.png")
                grade_campos.append(im)
            for j, f in enumerate(nucleos, 1):
                im = Image.open(f).convert("RGB")
                im.save(d / "nucleos" / f"nucleo_{j}.png")
                grade_nucleos.append(im)
            # de onde veio um núcleo: contorno no campo de origem
            n = nucleos[0]
            campo = Image.open(P / f"{n.stem[:8]}.BMP").convert("RGB")
            mk, (x, y) = caixa_do_nucleo(Image.open(n), campo)
            ed = np.zeros(mk.shape, bool)
            ed[1:-1, 1:-1] = mk[1:-1, 1:-1] & ~(mk[:-2, 1:-1] & mk[2:, 1:-1] & mk[1:-1, :-2] & mk[1:-1, 2:])
            arr = np.asarray(campo).copy()
            yy, xx = np.where(ed)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    arr[np.clip(yy + y + dy, 0, arr.shape[0] - 1), np.clip(xx + x + dx, 0, arr.shape[1] - 1)] = (0, 200, 0)
            lado = Image.new("RGB", (620 + 256, 480), "white")
            lado.paste(Image.fromarray(arr), (0, 0))
            lado.paste(Image.open(n).convert("RGB"), (620, 112))
            ImageDraw.Draw(lado).text((626, 380), "nucleo da pasta\nde 'citologia'", fill=(0, 0, 0))
            lado.save(d / "origem_do_nucleo.png")
        g = Image.new("RGB", (620 * CAMPOS_POR_CASO, 480 * CASOS_POR_CLASSE), "white")
        for k, im in enumerate(grade_campos):
            g.paste(im, (620 * (k % CAMPOS_POR_CASO), 480 * (k // CAMPOS_POR_CASO)))
        g.save(saida / f"grade_biopsia_{nome}.png")
        g = Image.new("RGB", (256 * NUCLEOS_POR_CASO, 256 * CASOS_POR_CLASSE), "white")
        for k, im in enumerate(grade_nucleos):
            g.paste(im, (256 * (k % NUCLEOS_POR_CASO), 256 * (k // NUCLEOS_POR_CASO)))
        g.save(saida / f"grade_nucleos_{nome}.png")
    with open(saida / "casos.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([("codigo", "pasta_original", "classe"), *tabela])
    print(f"exemplos em {saida}")


if __name__ == "__main__":
    main()
