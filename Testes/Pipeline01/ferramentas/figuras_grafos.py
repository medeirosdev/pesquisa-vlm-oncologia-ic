"""
Figuras dos testes com grafos, desenhadas sobre lâminas reais:
  grafo_gat_mil.jpg       GAT-MIL no PANDA: cada patch ligado aos 8 vizinhos encostados (biópsia inteira + zoom).
  grafo_bracs_parcial.jpg GAT-MIL no BRACS: grafo sobre a amostra de 2.000 patches (vizinhos a até 384 µm).
  rede_grafos.jpg         Rede de grafos no PANDA: atenção do MIL -> pontos de interesse com janelas 7 x 7 e a rede
                          entre os pontos (distâncias em mm) -> grafo local de uma janela.
  grafos_resultados.png   Kappa dos três modelos (MIL, GAT-MIL, rede de grafos) nos dois cenários do PANDA.

Uso (venv do projeto, HD montado):
    .venv/bin/python ferramentas/figuras_grafos.py [--panda <image_id>] [--bracs BRACS_1284]
Saída: docs/visao_geral/img/
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection, PatchCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

import gat_mil  # noqa: E402
import rede_grafos  # noqa: E402
from comum.lamina import RESULTADOS_DIR, Lamina, dir_resultados, raiz_hd, resolver_svs  # noqa: E402

SAIDA = comum.caminhos.RAIZ.parents[1] / "docs" / "visao_geral" / "img"
PANDA_HD = Path(raiz_hd()) / "Dados Gerais" / "PANDA"
LADO_BRACS = 512

# cores (paleta de referência do método de visualização; texto em tinta neutra)
AZUL, LARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
CINZA, TINTA, TINTA2, FUNDO = "#9a9993", "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({"font.size": 9, "text.color": TINTA, "axes.labelcolor": TINTA2, "xtick.color": TINTA2,
                     "ytick.color": TINTA2, "axes.edgecolor": "#d8d7d2", "figure.facecolor": FUNDO,
                     "axes.facecolor": FUNDO, "savefig.facecolor": FUNDO})


def salvar(fig, nome):
    SAIDA.mkdir(parents=True, exist_ok=True)
    fig.savefig(SAIDA / nome, dpi=130, bbox_inches="tight", pil_kwargs={"quality": 88} if nome.endswith("jpg") else {})
    plt.close(fig)
    print(f"  {SAIDA / nome}")


def limpar(ax, titulo):
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(titulo, loc="left", fontsize=10, color=TINTA)


def miniatura(lam, alvo=16):
    img, ds = lam.thumbnail(alvo)
    return img[..., :3], ds


class Vista:
    """Recorte da miniatura em volta do tecido, deitado na horizontal se o tecido for mais alto que largo.
    t(p) leva coordenadas do nível 0 pras do desenho."""

    def __init__(self, img, ds, xy, lado, margem=2):
        self.x0, self.y0 = np.maximum(xy.min(0) - margem * lado, 0)
        self.x1, self.y1 = xy.max(0) + (margem + 1) * lado
        self.gira = (self.y1 - self.y0) > (self.x1 - self.x0)
        self.img, self.ds = self.recortar(img, ds), ds

    def recortar(self, img, ds):
        r = img[int(self.y0 / ds):int(self.y1 / ds), int(self.x0 / ds):int(self.x1 / ds)]
        return np.rot90(r) if self.gira else r

    def t(self, p):
        p = np.asarray(p, dtype=float)
        if not self.gira:
            return p - [self.x0, self.y0]
        return np.stack([p[..., 1] - self.y0, self.x1 - p[..., 0]], -1)

    def mostrar(self, ax):
        h, w = self.img.shape[:2]
        ax.imshow(self.img, extent=[0, w * self.ds, h * self.ds, 0])
        ax.set_xlim(0, w * self.ds)
        ax.set_ylim(h * self.ds, 0)

    def quadrados(self, centros, lado, **kw):
        return PatchCollection([Rectangle(c - lado / 2, lado, lado) for c in self.t(centros)], **kw)

    def contorno(self, ax, mascara, ds, **kw):
        m = self.recortar(mascara, ds).astype(float)
        h, w = m.shape
        ax.contour(np.arange(w) * ds + ds / 2, np.arange(h) * ds + ds / 2, m, [0.5], **kw)


def segmentos(centros, arestas):
    o, d = arestas
    m = o != d
    return np.stack([centros[o[m]], centros[d[m]]], 1)


def janela_nivel0(lam, x0, y0, tam):
    return lam.janela_nativa(int(x0), int(y0), int(tam))[..., :3]


# ---------- PANDA ----------
def biopsia_panda(image_id):
    pasta = RESULTADOS_DIR / "panda" / image_id
    xy = np.loadtxt(pasta / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
    lado = json.loads((pasta / "meta.json").read_text())["lado_px"]
    att = np.load(RESULTADOS_DIR / "panda_mil" / f"{image_id}_atencao.npy")
    return xy, lado, att


def escolher_panda():
    """Uma biópsia de teste do Karolinska, ISUP >= 4, com máscara, 12+ pontos e tamanho médio."""
    lista = csv.DictReader(open(comum.caminhos.RAIZ / "dados/panda/lista_panda.tsv"), delimiter="\t")
    for l in lista:
        i = l["image_id"]
        if l["conjunto"] != "teste" or int(l["isup_grade"]) < 4:
            continue
        if not (PANDA_HD / "train_label_masks" / f"{i}_mask.tiff").exists():
            continue
        if not (RESULTADOS_DIR / "panda_mil" / f"{i}_atencao.npy").exists():
            continue
        xy, lado, att = biopsia_panda(i)
        if 350 <= len(xy) <= 900 and len(rede_grafos.montar(xy, lado, att)["pontos"]) >= 12:
            return i, l
    raise SystemExit("nenhuma biópsia atende aos filtros")


def fig_gat_mil(image_id, info):
    xy, lado, _ = biopsia_panda(image_id)
    lam = Lamina(PANDA_HD / "train_images" / f"{image_id}.tiff")
    img, ds = miniatura(lam)
    centros = xy + lado / 2
    arestas = gat_mil.arestas_vizinhos(xy, lado).numpy()

    v = Vista(img, ds, xy, lado)
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw={"width_ratios": [2.4, 1]})
    v.mostrar(a)
    a.add_collection(LineCollection(v.t(segmentos(centros, arestas)), colors=AZUL, linewidths=0.5, alpha=0.8))
    a.scatter(*v.t(centros).T, s=3, c=AZUL, lw=0)
    limpar(a, f"a) Biópsia inteira: {len(xy)} patches de tecido, cada um ligado aos 8 vizinhos encostados")

    # zoom: 6 x 6 patches em volta do patch com mais vizinhos
    grau = np.bincount(arestas[1], minlength=len(xy))
    c = int(np.argmax(grau))
    x0, y0 = xy[c] - 2 * lado
    tam = 6 * lado
    b.imshow(janela_nivel0(lam, x0, y0, tam), extent=[x0, x0 + tam, y0 + tam, y0])
    dentro = np.all((xy >= [x0, y0]) & (xy < [x0 + tam, y0 + tam]), 1)
    sel = np.isin(arestas[0], np.where(dentro)[0]) & np.isin(arestas[1], np.where(dentro)[0])
    b.add_collection(LineCollection(segmentos(centros, arestas[:, sel]), colors="white", linewidths=1.2, alpha=0.8))
    viz = arestas[0][(arestas[1] == c) & (arestas[0] != c)]
    b.add_collection(LineCollection([[centros[c], centros[v]] for v in viz], colors=AZUL, linewidths=2.4))
    b.add_collection(PatchCollection([Rectangle(xy[i], lado, lado) for i in np.where(dentro)[0]], facecolor="none",
                                     edgecolor="white", linewidth=0.5, alpha=0.6))
    b.scatter(*centros[dentro].T, s=18, c="white", edgecolors=TINTA2, linewidths=0.6, zorder=3)
    b.scatter(*centros[viz].T, s=30, c=AZUL, edgecolors="white", linewidths=0.8, zorder=4)
    b.scatter(*centros[c], s=70, c=LARANJA, edgecolors="white", linewidths=1, zorder=5)
    b.set_xlim(x0, x0 + tam)
    b.set_ylim(y0 + tam, y0)
    limpar(b, "b) Zoom (768 µm): o patch laranja mistura o embedding com\nos 8 vizinhos (azul), com um peso aprendido por vizinho")
    fig.suptitle(f"GAT-MIL no PANDA — biópsia do Karolinska, ISUP {info['isup_grade']} (patch de 128 µm)",
                 x=0.01, ha="left", fontsize=11, fontweight="bold")
    salvar(fig, "grafo_gat_mil.jpg")


def fig_rede(image_id, info):
    xy, lado, att = biopsia_panda(image_id)
    lam = Lamina(PANDA_HD / "train_images" / f"{image_id}.tiff")
    img, ds = miniatura(lam)
    centros = xy + lado / 2
    g = rede_grafos.montar(xy, lado, att)
    pts = g["pontos"]
    nos, seg, arestas = g["nos"].numpy(), g["seg"].numpy(), g["arestas"].numpy()
    pos_mm = g["pos_mm"].numpy()

    mk, dsm = Lamina(PANDA_HD / "train_label_masks" / f"{image_id}_mask.tiff").thumbnail(16)
    cancer = (mk[..., 0] if mk.ndim == 3 else mk) == 2

    v = Vista(img, ds, xy, lado)
    fig = plt.figure(figsize=(15, 7.2))
    gs = fig.add_gridspec(2, 2, width_ratios=[2.6, 1], hspace=0.25, wspace=0.05)
    ax = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[:, 1])]
    # a) atenção
    v.mostrar(ax[0])
    r = np.argsort(np.argsort(att)) / max(len(att) - 1, 1)
    q = v.quadrados(centros, lado, cmap="Blues", alpha=0.8, linewidth=0)
    q.set_array(r)
    q.set_clim(0, 1)
    ax[0].add_collection(q)
    v.contorno(ax[0], cancer, dsm, colors=LARANJA, linewidths=1.4)
    limpar(ax[0], "a) Atenção do MIL em cada patch\n(mais escuro = mais atenção; laranja = câncer anotado)")

    # b) pontos, janelas e rede
    v.mostrar(ax[1])
    for p in range(len(pts)):
        ax[1].add_collection(v.quadrados(centros[nos[seg == p]], lado, facecolor=AZUL, alpha=0.3, edgecolor="none"))
    cp = v.t(centros[pts])
    pares = [(i, j) for i in range(len(pts)) for j in range(i + 1, len(pts))]
    ax[1].add_collection(LineCollection([[cp[i], cp[j]] for i, j in pares], colors=TINTA, linewidths=0.5, alpha=0.3))
    v.contorno(ax[1], cancer, dsm, colors=LARANJA, linewidths=1.4)
    for p in range(len(pts)):
        ax[1].scatter(*cp[p], s=110, c=AZUL, edgecolors="white", linewidths=1.2, zorder=4)
        ax[1].text(*cp[p], str(p + 1), ha="center", va="center", fontsize=6.5, color="white", zorder=5,
                   fontweight="bold")
    d = np.hypot(*(pos_mm[:, None] - pos_mm[None]).transpose(2, 0, 1))
    ordem = sorted(range(1, len(pts)), key=lambda j: d[0, j])
    for j in (ordem[0], ordem[-1]):
        m = (cp[0] + cp[j]) / 2
        ax[1].text(*m, f"{d[0, j]:.1f} mm", fontsize=7, color=TINTA, ha="center", va="center", zorder=6,
                   bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.85})
    limpar(ax[1], f"b) {len(pts)} pontos de interesse (centros a ≥ 1 mm), janela 7 × 7\nem cada um e rede entre os "
                  "pontos com a distância em mm")

    # c) grafo local do ponto 1
    i = pts[0]
    x0, y0 = xy[i] - rede_grafos.MEIA_JANELA * lado
    tam = (2 * rede_grafos.MEIA_JANELA + 1) * lado
    ax[2].imshow(janela_nivel0(lam, x0, y0, tam), extent=[x0, x0 + tam, y0 + tam, y0])
    local = np.where(seg == 0)[0]
    cl = centros[nos]
    sel = np.isin(arestas[1], local) & (arestas[0] != arestas[1])
    ax[2].add_collection(LineCollection(np.stack([cl[arestas[0][sel]], cl[arestas[1][sel]]], 1), colors="white",
                                        linewidths=1.1, alpha=0.85))
    ax[2].scatter(*cl[local].T, s=22, c=AZUL, edgecolors="white", linewidths=0.7, zorder=3)
    ax[2].scatter(*centros[i], s=80, c=LARANJA, edgecolors="white", linewidths=1, zorder=4)
    ax[2].set_xlim(x0, x0 + tam)
    ax[2].set_ylim(y0 + tam, y0)
    limpar(ax[2], f"c) Grafo local do ponto 1: {len(local)} patches\n(896 µm de lado), cada um ligado aos vizinhos")
    fig.suptitle(f"Rede de grafos no PANDA — a mesma biópsia (Karolinska, ISUP {info['isup_grade']}); pontos escolhidos "
                 "pela atenção de um MIL que não viu a biópsia", x=0.01, ha="left", fontsize=11, fontweight="bold")
    salvar(fig, "rede_grafos.jpg")


# ---------- BRACS ----------
def fig_bracs(stem):
    xy = np.loadtxt(dir_resultados(stem, "uni2h") / "amostra2000_xy.csv", delimiter=",", skiprows=1,
                    dtype=np.int64).reshape(-1, 2)
    lam = Lamina(resolver_svs(stem))
    img, ds = miniatura(lam, 32)
    centros = xy + LADO_BRACS / 2
    arestas = gat_mil.arestas_proximos(xy, LADO_BRACS).numpy()
    sem = int(np.sum(np.bincount(arestas[1][arestas[0] != arestas[1]], minlength=len(xy)) == 0))

    v = Vista(img, ds, xy, LADO_BRACS, 4)
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5.4), gridspec_kw={"width_ratios": [1.4, 1]})
    v.mostrar(a)
    a.add_collection(LineCollection(v.t(segmentos(centros, arestas)), colors=AZUL, linewidths=0.35, alpha=0.8))
    a.scatter(*v.t(centros).T, s=1.5, c=AZUL, lw=0)
    limpar(a, f"a) Lâmina inteira: só os {len(xy)} patches sorteados do tecido têm embedding")

    # zoom 3 mm numa região típica: a de contagem de patches da amostra mais próxima da mediana das regiões
    tam = 12 * LADO_BRACS
    cel = (xy - tam // 2) // tam
    u, cont = np.unique(cel, axis=0, return_counts=True)
    x0, y0 = u[np.argmin(np.abs(cont - np.median(cont[cont >= 20])))] * tam + tam // 2
    sub = janela_nivel0(lam, x0, y0, tam)[::4, ::4]
    b.imshow(sub, extent=[x0, x0 + tam, y0 + tam, y0])
    dentro = np.all((xy >= [x0, y0]) & (xy < [x0 + tam, y0 + tam]), 1)
    idx = np.where(dentro)[0]
    sel = np.isin(arestas[0], idx) & np.isin(arestas[1], idx) & (arestas[0] != arestas[1])
    b.add_collection(PatchCollection([Rectangle(xy[i], LADO_BRACS, LADO_BRACS) for i in idx], facecolor=AZUL,
                                     alpha=0.25, edgecolor="white", linewidth=0.6))
    b.add_collection(LineCollection(np.stack([centros[arestas[0][sel]], centros[arestas[1][sel]]], 1), colors=AZUL,
                                    linewidths=1.3))
    b.scatter(*centros[idx].T, s=14, c=AZUL, edgecolors="white", linewidths=0.6, zorder=3)
    b.set_xlim(x0, x0 + tam)
    b.set_ylim(y0 + tam, y0)
    limpar(b, "b) Zoom (3 mm): entre os patches sorteados fica tecido sem\nembedding; cada patch se liga aos até 8 "
              "mais próximos a ≤ 384 µm")
    fig.suptitle(f"GAT-MIL na mama (BRACS, {stem}): grafo parcial — média de 6,1 vizinhos por patch no BRACS; nesta "
                 f"lâmina, {sem} de {len(xy)} patches sem nenhum vizinho", x=0.01, ha="left", fontsize=11,
                 fontweight="bold")
    salvar(fig, "grafo_bracs_parcial.jpg")


# ---------- resultados ----------
def fig_resultados():
    r = json.loads((RESULTADOS_DIR / "rede_grafos_panda" / "resumo.json").read_text())
    centro = json.loads((RESULTADOS_DIR / "panda_centro" / "resumo.json").read_text())["por_braco"]["R1|gat"]
    nomes = [("abmil", "MIL atual"), ("gat_mil", "GAT-MIL"), ("rede_grafos", "Rede de grafos")]
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, gridspec_kw={"width_ratios": [4, 3]})
    for ax, chave, titulo, extra in (
            (axs[0], "cenario1_radboud_para_karolinska", "Treino no Radboud, teste no Karolinska (300)", True),
            (axs[1], "cenario2_dentro_do_radboud", "Dentro do Radboud, validação cruzada (600)", False)):
        c = r[chave]
        barras = [(rot, c[k]["kappa"], c[k]["ic95"], AZUL if k == "rede_grafos" else CINZA) for k, rot in nomes]
        if extra:
            barras.append(("GAT-MIL +\npadronização\npor centro", centro["kappa"], centro["ic95"], CINZA))
        for x, (rot, k, ic, cor) in enumerate(barras):
            ax.bar(x, k, width=0.62, color=cor, edgecolor=FUNDO, linewidth=2)
            ax.plot([x, x], ic, color=TINTA2, lw=1)
            ax.plot([x - 0.08, x + 0.08], [ic[0]] * 2, color=TINTA2, lw=1)
            ax.plot([x - 0.08, x + 0.08], [ic[1]] * 2, color=TINTA2, lw=1)
            ax.text(x + 0.1, k + 0.012, f"{k:.3f}".replace(".", ","), ha="left", va="bottom", fontsize=9,
                    color=TINTA, fontweight="bold" if cor == AZUL else "normal")
        ax.set_xticks(range(len(barras)), [b[0] for b in barras], fontsize=8.5)
        ax.set_title(titulo, loc="left", fontsize=10)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", color="#ebeae6", lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axs[0].set_ylabel("kappa quadrático (ISUP 0–5)")
    axs[0].text(0, -0.36, "Barras: IC 95% por bootstrap. Rede de grafos − MIL: entre centros +0,205 (IC 0,104 a 0,310, "
                "passou); dentro do Radboud +0,025 (IC −0,002 a 0,051, não passou). Contra o GAT-MIL, empate nos dois. "
                "A barra da padronização é do teste de troca de centro.", transform=axs[0].transAxes, fontsize=7.5,
                color=TINTA2, wrap=True)
    fig.suptitle("Graduação da próstata (PANDA): MIL × GAT-MIL × rede de grafos", x=0.01, ha="left", fontsize=11,
                 fontweight="bold")
    salvar(fig, "grafos_resultados.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panda")
    ap.add_argument("--bracs", default="BRACS_1284")
    a = ap.parse_args()
    if a.panda:
        info = next(l for l in csv.DictReader(open(comum.caminhos.RAIZ / "dados/panda/lista_panda.tsv"),
                                              delimiter="\t") if l["image_id"] == a.panda)
        i = a.panda
    else:
        i, info = escolher_panda()
    print(f"PANDA: {i} (ISUP {info['isup_grade']})")
    fig_gat_mil(i, info)
    fig_rede(i, info)
    fig_bracs(a.bracs)
    fig_resultados()


if __name__ == "__main__":
    main()
