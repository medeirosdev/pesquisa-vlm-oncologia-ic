"""
Mapas de atenção do MIL nas lâminas de pulmão do TCGA (validacao/tcga_descritor_prelaudo.py), com a classe de cada
patch pelo descritor do LungHist700 e as 3 regiões de maior atenção citadas no pré-laudo, recortadas em resolução
cheia. As lâminas foram apagadas depois dos embeddings: o script baixa de novo do GDC só as pedidas, desenha e apaga.

Painéis: (a) classe de cada patch da amostra pelo descritor; (b) atenção do MIL em percentil dentro da lâmina, com as
3 regiões numeradas; embaixo, os recortes de 128 µm das 3 regiões, com a classe do descritor.

Uso (venv do projeto, HD montado, internet):
    .venv/bin/python scripts/mapas_atencao_tcga.py TCGA-46-3766 TCGA-55-6712 [--manter]
Saída: resultados/tcga_prelaudo/mapas/<paciente>.png
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validacao"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib

matplotlib.use("Agg")
import cv2
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from comum.lamina import Lamina, raiz_hd
from tcga_baixar_e_embutir import baixar
from tcga_descritor_prelaudo import PASTA, SAIDA, laminas_teste

CLASSES = ["nor", "aca", "scc"]
NOME = {"nor": "pulmão normal", "aca": "adenocarcinoma", "scc": "carcinoma escamoso"}
NOME_MIL = {"TCGA-LUAD": "adenocarcinoma", "TCGA-LUSC": "carcinoma escamoso"}
CORES = {"nor": "#1f7a4d", "aca": "#d99a06", "scc": "#3f2f8f"}
LARGURA_MAX = 2400


def desenhar(l, mil, manter=False):
    meta = json.loads((PASTA / l["file_id"] / "meta.json").read_text(encoding="utf-8"))
    lado = int(meta["lado_px"])
    xy = np.loadtxt(PASTA / l["file_id"] / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=int).reshape(-1, 2)
    P = np.load(SAIDA / f"{l['file_id']}_descritor.npy")
    att = np.load(SAIDA / f"{l['file_id']}_atencao.npy")
    pct = np.argsort(np.argsort(att)) / max(len(att) - 1, 1)
    campos = (SAIDA / f"{l['file_id']}_campos.txt").read_text(encoding="utf-8")
    regioes = [(int(x), int(y), c, float(p)) for x, y, c, p in
               re.findall(r"^\s+\[(\d+),(\d+)\] (.+?) ([\d.]+)$", campos, flags=re.M)]

    tmp = Path(raiz_hd()) / "TCGA_pulmao_tmp"
    tmp.mkdir(exist_ok=True)
    svs = tmp / l["file_name"]
    print(f"  {l['paciente']}: baixando {int(l['bytes']) / 1e9:.2f} GB", flush=True)
    baixar(l, svs)
    lam = Lamina(svs)
    alvo = max(16.0, lam.largura / LARGURA_MAX)
    rgb, ds = lam.thumbnail(alvo)
    if rgb.shape[1] > LARGURA_MAX:  # nível mais próximo ainda grande demais
        f = LARGURA_MAX / rgb.shape[1]
        rgb = cv2.resize(rgb, (LARGURA_MAX, int(rgb.shape[0] * f)), interpolation=cv2.INTER_AREA)
        ds /= f
    recortes = [cv2.resize(lam.janela_nativa(x, y, lado)[..., :3], (384, 384), interpolation=cv2.INTER_AREA)
                for x, y, _, _ in regioes]

    m = mil[l["file_id"]]
    p_pred = m["p_lusc"] if m["predito"] == "TCGA-LUSC" else 1 - m["p_lusc"]
    razao = rgb.shape[0] / rgb.shape[1]
    fig = plt.figure(figsize=(12, 6 * razao + 4.2), dpi=110)
    gs = fig.add_gridspec(2, 6, height_ratios=[6 * razao, 3.6])
    ea, eb = fig.add_subplot(gs[0, 0:3]), fig.add_subplot(gs[0, 3:6])
    for ax in (ea, eb):
        ax.imshow(rgb)
        ax.set_axis_off()
    lp = lado / ds
    for (x0, y0), p in zip(xy, P):
        c = CLASSES[int(p.argmax())]
        ea.add_patch(plt.Rectangle((x0 / ds, y0 / ds), lp, lp, color=CORES[c], alpha=0.25 + 0.6 * float(p.max()), lw=0))
    mapa = plt.get_cmap("magma_r")
    for (x0, y0), v in zip(xy, pct):
        eb.add_patch(plt.Rectangle((x0 / ds, y0 / ds), lp, lp, color=mapa(float(v)), alpha=0.75, lw=0))
    for k, (x, y, _, _) in enumerate(regioes, 1):
        eb.add_patch(plt.Rectangle((x / ds - lp, y / ds - lp), 3 * lp, 3 * lp, fill=False, ec="#00b3b3", lw=1.6))
        eb.text(x / ds + 2 * lp, y / ds - lp, str(k), color="#00b3b3", fontsize=11, fontweight="bold", va="top")
    ea.legend(handles=[Patch(color=CORES[c], label=NOME[c]) for c in CLASSES], loc="lower left", fontsize=8, framealpha=0.9)
    sm = plt.cm.ScalarMappable(cmap=mapa, norm=plt.Normalize(0, 1))
    fig.colorbar(sm, ax=eb, fraction=0.035, pad=0.02, label="percentil da atenção")
    ea.set_title("classe de cada patch pelo descritor (opacidade = confiança)", fontsize=10)
    eb.set_title("atenção do MIL (quadros: 3 regiões citadas no pré-laudo)", fontsize=10)
    for k, (rec, (_, _, c, p)) in enumerate(zip(recortes, regioes), 1):
        ax = fig.add_subplot(gs[1, 2 * k - 2:2 * k])
        ax.imshow(rec)
        ax.set_axis_off()
        ax.set_title(f"região {k}: {c} {p:.2f}", fontsize=9)
    fig.suptitle(f"{l['paciente']} · real: {NOME_MIL[l['projeto']]} · MIL: {NOME_MIL[m['predito']]} ({p_pred:.2f})"
                 f" · recortes de 128 µm", fontsize=11)
    fig.tight_layout()
    saida = SAIDA / "mapas"
    saida.mkdir(exist_ok=True)
    fig.savefig(saida / f"{l['paciente']}.png")
    plt.close(fig)
    lam.tif.close()
    if not manter:
        svs.unlink()
    print(f"  {l['paciente']}: {saida / (l['paciente'] + '.png')}", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pacientes", nargs="+")
    p.add_argument("--manter", action="store_true", help="não apaga a lâmina baixada")
    a = p.parse_args()
    mil = json.loads((SAIDA / "mil.json").read_text(encoding="utf-8"))["por_lamina"]
    por_pac = {l["paciente"]: l for l in laminas_teste()}
    for pac in a.pacientes:
        desenhar(por_pac[pac], mil, a.manter)


if __name__ == "__main__":
    main()
