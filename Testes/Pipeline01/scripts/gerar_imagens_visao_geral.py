"""
Gera as imagens de exemplo da página de visão geral da pipeline (pasta docs/visao_geral/ do
projeto, dentro de docs/ — publicada junto com o site MkDocs), a partir das saídas já calculadas dos estágios. Imagens do BRACS (CC BY-NC 4.0, com
atribuição na página) e sobreposições de núcleos do CellViT; nenhuma imagem do BACH (licença ND).

Uso (venv do projeto, com o HD montado):
    .venv/bin/python scripts/gerar_imagens_visao_geral.py
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from comum.lamina import RAIZ_PROJETO, TILE_NATIVO, Lamina, dir_resultados, resolver_svs

SAIDA = RAIZ_PROJETO / "docs" / "visao_geral" / "img"
COR = {"DCIS": (143, 47, 63), "IC": (111, 69, 200), "benigno": (77, 122, 31), "atipico": (6, 106, 154)}  # BGR


def salvar(nome, img_bgr, largura_max=1100):
    h, w = img_bgr.shape[:2]
    if w > largura_max:
        img_bgr = cv2.resize(img_bgr, (largura_max, round(h * largura_max / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(SAIDA / nome), img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 84])
    print(" ", nome, img_bgr.shape[1], "x", img_bgr.shape[0])


def miniatura_com_patches(stem, nome):
    """Miniatura da lâmina com os 32 patches do descritor, coloridos pelo resultado, e os RoIs em cinza."""
    lamina = Lamina(resolver_svs(stem))
    rgb, ds = lamina.thumbnail(32)
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    # reduz antes de desenhar, pra os marcadores terem tamanho legível na imagem final
    f = min(1.0, 1100 / img.shape[1])
    img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    ds = ds / f
    roi_csv = dir_resultados(stem, "estagio1") / "recall_roi.csv"
    if roi_csv.exists():
        for r in csv.DictReader(open(roi_csv, encoding="utf-8")):
            x, y, w, h = (float(r[k]) / ds for k in ("x", "y", "w", "h"))
            cv2.rectangle(img, (int(x), int(y)), (int(x + w), int(y + h)), (150, 150, 150), 1)
    d = json.loads((dir_resultados(stem, "estagio3") / "estagio3_descritores_k32_uni.json").read_text(encoding="utf-8"))
    lado = max(int(TILE_NATIVO / ds), 12)
    for t in d["descritores"]:
        chave = t["subtipo"] or t["categoria"]
        cx, cy = int((t["x0"] + TILE_NATIVO / 2) / ds), int((t["y0"] + TILE_NATIVO / 2) / ds)
        cv2.rectangle(img, (cx - lado // 2 - 1, cy - lado // 2 - 1), (cx + lado // 2 + 1, cy + lado // 2 + 1), (255, 255, 255), 4)
        cv2.rectangle(img, (cx - lado // 2, cy - lado // 2), (cx + lado // 2, cy + lado // 2), COR[chave], 2)
    salvar(nome, img)
    return lamina, d


def recorte(lamina, x0, y0, nome, lado=448):
    img = cv2.cvtColor(lamina.janela_nativa(x0, y0)[..., :3], cv2.COLOR_RGB2BGR)
    salvar(nome, cv2.resize(img, (lado, lado), interpolation=cv2.INTER_AREA), largura_max=lado)


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    e1 = dir_resultados("BRACS_748", "estagio1")
    salvar("e1_lamina.jpg", cv2.imread(str(e1 / "00_thumbnail.png")))
    salvar("e1_mascara.jpg", cv2.imread(str(e1 / "02_otsu_saturacao_morfologia_overlay.png")))

    lam748, d748 = miniatura_com_patches("BRACS_748", "e2_selecao_748.jpg")
    lam1370, d1370 = miniatura_com_patches("BRACS_1370", "e2_selecao_1370.jpg")

    def melhor(d, cond):
        return max((t for t in d["descritores"] if cond(t)), key=lambda t: max(t["prob_categoria"].values()))
    exemplos = {"e3_patch_dcis.jpg": (lam748, melhor(d748, lambda t: t["subtipo"] == "DCIS")),
                "e3_patch_ic.jpg": (lam748, melhor(d748, lambda t: t["subtipo"] == "IC")),
                "e3_patch_benigno.jpg": (lam1370, melhor(d1370, lambda t: t["categoria"] == "benigno")),
                "e3_patch_falso_positivo.jpg": (lam1370, melhor(d1370, lambda t: t["categoria"] == "maligno"))}
    textos = {}
    for nome, (lam, t) in exemplos.items():
        recorte(lam, t["x0"], t["y0"], nome)
        textos[nome] = t["texto"]

    nuc = dir_resultados("BRACS_748", "nucleos")
    for classe, arq in (("dcis", "overlay_DCIS_117760_77824.png"), ("ic", "overlay_IC_103936_45056.png")):
        salvar(f"e3_nucleos_{classe}.jpg", cv2.imread(str(nuc / arq)), largura_max=640)
    (SAIDA / "textos_patches.json").write_text(json.dumps(textos, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(textos, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
