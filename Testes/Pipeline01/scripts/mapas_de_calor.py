"""
Mapa de calor da lâmina: cada patch da amostra de 2.000 pintado sobre a miniatura, (a) pela classe prevista
pelo descritor "rois" (benigno, atípico, DCIS, IC; opacidade = confiança) e (b) pela probabilidade de não ser
benigno. Explicabilidade: mostra onde o sistema viu cada coisa.

Lê as probabilidades salvas por validacao/prelaudo_campos.py (teste) ou validacao/pacote_cotas.py (validação).
A miniatura precisa da lâmina no HD; sem ela, o mapa sai sobre fundo branco.

Uso (venv do projeto):
    .venv/bin/python scripts/mapas_de_calor.py BRACS_264 BRACS_1003728 [--docs]
Opção --docs: salva também em docs/visao_geral/img/ (JPEG reduzido, pra página).
Opção --reducao 64: miniatura mais reduzida, pra lâminas que estouram a memória.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "validacao"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

from comum.lamina import RESULTADOS_DIR, TILE_NATIVO, Lamina, ler_caminhos
from comum.rois import info_lamina

CORES = {"benigno": "#1f7a4d", "atipico": "#d99a06", "DCIS": "#3f2f8f", "IC": "#c8456f"}
NOME_PT = {"benigno": "benigno", "atipico": "atípico", "DCIS": "DCIS", "IC": "carcinoma invasivo"}
DOCS_IMG = Path(__file__).resolve().parents[3] / "docs" / "visao_geral" / "img"
SAIDA = RESULTADOS_DIR / "mapas_de_calor"


def arquivo_probs(s):
    for pasta in ("prelaudo_campos", "pacote_cotas"):
        f = RESULTADOS_DIR / pasta / f"{s}_probs.npz"
        if f.exists():
            return f
    raise FileNotFoundError(f"sem probabilidades salvas pra {s}")


def predito_classificador(s):
    f = RESULTADOS_DIR / "classificador_lamina" / "resumo.json"
    if f.exists():
        r = json.loads(f.read_text(encoding="utf-8")).get("por_lamina_teste", {})
        if s in r:
            return r[s]["predito"]
    return None


def desenhar(s, docs=False, reducao=32):
    from lamina_inteira import classe_final
    z = np.load(arquivo_probs(s))
    p1, p2, xy = z["p1"], z["p2"], z["xy"]
    cat, sub = p1.argmax(1), p2.argmax(1)
    classe = np.where(cat == 0, "benigno", np.where(cat == 1, "atipico", np.where(sub == 0, "DCIS", "IC")))
    conf = p1.max(1) * np.where(cat == 2, p2.max(1), 1.0)
    nao_benigno = 1 - p1[:, 0]

    svs = Path(ler_caminhos()["laminas_dir"]) / f"{s}.svs"
    if svs.exists():
        rgb, ds = Lamina(svs).thumbnail(reducao)
    else:
        ds = float(reducao)
        h, w = int((xy[:, 1].max() + TILE_NATIVO) / ds) + 1, int((xy[:, 0].max() + TILE_NATIVO) / ds) + 1
        rgb = np.full((h, w, 3), 255, np.uint8)
    lado = TILE_NATIVO / ds

    fig, eixos = plt.subplots(1, 2, figsize=(12, 6.2 * rgb.shape[0] / rgb.shape[1] + 1.2), dpi=110)
    for ax in eixos:
        ax.imshow(rgb)
        ax.set_axis_off()
    for (x0, y0), c, a in zip(xy, classe, conf):
        eixos[0].add_patch(plt.Rectangle((x0 / ds, y0 / ds), lado, lado, color=CORES[c], alpha=0.25 + 0.6 * float(a), lw=0))
    mapa = plt.get_cmap("magma_r")
    for (x0, y0), v in zip(xy, nao_benigno):
        eixos[1].add_patch(plt.Rectangle((x0 / ds, y0 / ds), lado, lado, color=mapa(float(v)), alpha=0.75, lw=0))
    eixos[0].legend(handles=[Patch(color=CORES[c], label=NOME_PT[c]) for c in CORES], loc="lower left", fontsize=8, framealpha=0.9)
    sm = plt.cm.ScalarMappable(cmap=mapa, norm=plt.Normalize(0, 1))
    fig.colorbar(sm, ax=eixos[1], fraction=0.035, pad=0.02, label="P(não benigno)")
    eixos[0].set_title("classe prevista de cada patch (opacidade = confiança)", fontsize=10)
    eixos[1].set_title("probabilidade de não ser benigno", fontsize=10)
    real = classe_final(info_lamina(s)["rotulo"])
    pred = predito_classificador(s)
    fig.suptitle(f"{s} · rótulo real: {NOME_PT[real]}" + (f" · classificador da lâmina: {NOME_PT[pred]}" if pred else ""), fontsize=11)
    fig.tight_layout()
    SAIDA.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA / f"{s}.png")
    if docs:
        fig.savefig(DOCS_IMG / f"mapa_{s}.jpg", dpi=80, pil_kwargs={"quality": 82})
    plt.close(fig)
    print(f"  {s}: {SAIDA / f'{s}.png'}", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("laminas", nargs="+")
    p.add_argument("--docs", action="store_true")
    p.add_argument("--reducao", type=int, default=32, help="redução da miniatura; 64 pra lâminas grandes")
    a = p.parse_args()
    for s in a.laminas:
        desenhar(s, a.docs, a.reducao)
