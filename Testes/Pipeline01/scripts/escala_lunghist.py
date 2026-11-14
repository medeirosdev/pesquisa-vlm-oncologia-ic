"""
Escala (µm/px) das imagens do LungHist700 (Diosdado et al., Scientific Data 2024; CC BY 4.0), que o artigo não
informa (só "20x" e "40x", câmera Leica ICC50 W). Sem ela não dá pra cortar patches de 128 µm como no resto da
pipeline.

Régua: o núcleo de linfócito, que tem tamanho parecido em qualquer tecido. O CellViT segmenta os núcleos nas
lâminas do BRACS (resolução conhecida, MPP do cabeçalho) e nas imagens do LungHist700; a razão entre os diâmetros
medianos dos núcleos inflamatórios dá a escala.

Fixado ANTES de rodar (commit anterior aos resultados):
  Referência: BRACS_295, BRACS_748, BRACS_773 (MPP do cabeçalho, ~0,252 µm/px); 10 tiles por lâmina sorteados
     (semente 0) entre os que já têm núcleos salvos (validacao/dcis_ic_nucleos.py); janela de 1024 px.
  LungHist700: 30 imagens de 40x e 30 de 20x, sorteadas (semente 0) entre todas as classes. 40x: recorte central de
     1024 px. 20x: recorte central de 512 px ampliado 2x (bicúbica) pra 1024; o diâmetro medido é dividido por 2.
  Núcleos usados: tipo "inflamatorio" com probabilidade >= 0,8, contorno sem tocar a borda da janela.
     Diâmetro equivalente = 2 * sqrt(área / pi), área do contorno.
  Escala = (diâmetro mediano no BRACS em px * MPP do BRACS) / diâmetro mediano no LungHist700 em px, separada pra
     20x e 40x. Conferência (sem critério): a razão 20x / 40x deve ficar perto de 2.

Roda no ambiente do CellViT (GPU):
    "<HD>/venvs/cellvit/bin/python" scripts/escala_lunghist.py
Saída: resultados/lunghist700/escala.json
"""

import csv
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validacao"))

import cv2
import numpy as np
import torch

from comum.lamina import RESULTADOS_DIR, Lamina, raiz_hd, resolver_svs

LAMINAS_REF = ["BRACS_295", "BRACS_748", "BRACS_773"]
N_TILES_REF = 10
N_IMAGENS = 30
PROB_MIN = 0.8
SAIDA = RESULTADOS_DIR / "lunghist700"


def pasta_lunghist():
    return Path(raiz_hd()) / "Dados Gerais" / "LungHist700" / "data"


def imagens_lunghist():
    """[(caminho, superclasse, subclasse, aumento, paciente)] a partir de data.csv."""
    base = pasta_lunghist()
    saida = []
    for r in csv.DictReader(open(base / "data.csv", encoding="utf-8")):
        pasta = f"{r['superclass']}_{r['subclass']}" if r["subclass"] else r["superclass"]
        nome = f"{pasta}_{r['resolution']}_{r['image_id']}.jpg"
        saida.append((base / "images" / pasta / nome, r["superclass"], r["subclass"], r["resolution"], r["patient_id"]))
    return saida


def mpp_cabecalho(s):
    import tifffile
    with tifffile.TiffFile(resolver_svs(s)) as t:
        return float(re.search(r"MPP\s*=\s*([0-9.]+)", t.pages[0].description).group(1))


def diametros(celulas, lado):
    d = []
    for c in celulas.values():
        if c["type"] != 2 or c["type_prob"] < PROB_MIN:  # 2 = inflamatório
            continue
        cont = np.asarray(c["contour"], np.int32)
        if cont.min() <= 0 or cont.max() >= lado - 1:
            continue
        area = cv2.contourArea(cont)
        if area > 0:
            d.append(2 * np.sqrt(area / np.pi))
    return d


def main():
    from nucleos_cellvit import carregar_modelo, ler_janela, segmentar
    SAIDA.mkdir(parents=True, exist_ok=True)
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, media, desvio = carregar_modelo(dispositivo)

    ref_um = []
    for s in LAMINAS_REF:
        mpp = mpp_cabecalho(s)
        tiles = sorted((RESULTADOS_DIR / s / "nucleos").glob("nucleos_*.json"))
        lamina = Lamina(resolver_svs(s))
        for f in random.Random(0).sample(tiles, N_TILES_REF):
            x0, y0 = map(int, f.stem.split("_")[1:])
            ref_um += [d * mpp for d in diametros(segmentar(modelo, media, desvio, ler_janela(lamina, x0, y0), dispositivo), 1024)]
        print(f"  {s}: {len(ref_um)} núcleos inflamatórios até aqui", flush=True)

    imgs = imagens_lunghist()
    res = {"referencia_bracs": {"n_nucleos": len(ref_um), "diametro_mediano_um": round(float(np.median(ref_um)), 3)}}
    for aumento in ("40x", "20x"):
        escolhidas = random.Random(0).sample(sorted(i for i in imgs if i[3] == aumento), N_IMAGENS)
        d_px = []
        for caminho, *_ in escolhidas:
            rgb = cv2.cvtColor(cv2.imread(str(caminho)), cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            if aumento == "40x":
                crop, fator = rgb[h // 2 - 512:h // 2 + 512, w // 2 - 512:w // 2 + 512], 1
            else:
                crop = cv2.resize(rgb[h // 2 - 256:h // 2 + 256, w // 2 - 256:w // 2 + 256], (1024, 1024), interpolation=cv2.INTER_CUBIC)
                fator = 2
            d_px += [d / fator for d in diametros(segmentar(modelo, media, desvio, np.ascontiguousarray(crop), dispositivo), 1024)]
        med = float(np.median(d_px))
        res[aumento] = {"n_imagens": N_IMAGENS, "n_nucleos": len(d_px), "diametro_mediano_px": round(med, 3),
                        "mpp": round(float(np.median(ref_um)) / med, 4)}
        print(f"  {aumento}: {len(d_px)} núcleos, diâmetro mediano {med:.2f} px -> {res[aumento]['mpp']} µm/px", flush=True)
    res["razao_20x_40x"] = round(res["20x"]["mpp"] / res["40x"]["mpp"], 3)
    (SAIDA / "escala.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
