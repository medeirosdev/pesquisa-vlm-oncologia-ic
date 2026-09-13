"""
Estágio 2 da Pipeline Ideia 01: roteador top-k.

Dos tiles com tecido que sobraram do estágio 1, seleciona os k mais
relevantes por similaridade contrastiva (QuiltNet-B-32, CLIP treinado no
Quilt-1M) contra um banco de frases de achados histopatológicos — o mesmo
banco já especificado para o estágio 3 em docs/pipelines.md — com um gate
de diversidade espacial simples pra evitar quase-duplicatas vizinhas.

Simplificação registrada: não há mecanismo de saliência/atenção treinado
disponível, então o modo "rótulo fixo" usa a mesma similaridade
contrastiva do modo VQA (banco de frases fixo em vez do texto de uma
pergunta) — é uma aproximação de saliência, não saliência de verdade.

Tiles são extraídos por leitura em janela (zarr) do nível 0 (nativo, ~40x)
da pirâmide, em blocos de 512px, reduzidos a 256px — o equivalente a 20x
de magnificação de trabalho (ver docs/pipelines.md, estágio 0), sem
carregar a lâmina inteira em memória.

Uso:
    .venv/bin/python roteador_topk.py --k 8 16 32 64
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import open_clip
import tifffile
import torch
import zarr

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR.parent / "estagio1"))
from filtro_tecido import carregar_thumbnail, filtro_otsu_saturacao_morfologia, resolver_caminho_svs  # noqa: E402

OUTPUTS_ROOT = BASE_DIR / "outputs"
TILE_NATIVO = 512   # px no nível 0 (~40x) -> equivalente a 256px em ~20x
TILE_TRABALHO = 256
LIMIAR_TECIDO = 0.5  # fração mínima de tecido no tile pra virar candidato (mesmo critério do estágio 1)
DIST_MIN_DIVERSIDADE = TILE_NATIVO * 1.5  # px no nível 0, entre centros de tiles aceitos

BANCO_DE_FRASES = [
    "tumor nests",
    "necrosis",
    "high nuclear pleomorphism",
    "mitotic figures",
    "dense atypical stroma",
]


def montar_grade_candidatos(largura_full, altura_full, mask4, ds4):
    """Gera a grade de tiles nativos e filtra pelos que têm tecido suficiente na máscara do estágio 1."""
    candidatos = []
    for y0 in range(0, altura_full - TILE_NATIVO, TILE_NATIVO):
        for x0 in range(0, largura_full - TILE_NATIVO, TILE_NATIVO):
            mx0, my0 = int(x0 / ds4), int(y0 / ds4)
            mx1, my1 = int((x0 + TILE_NATIVO) / ds4), int((y0 + TILE_NATIVO) / ds4)
            recorte = mask4[my0:my1, mx0:mx1]
            if recorte.size == 0:
                continue
            frac_tecido = float(np.count_nonzero(recorte)) / recorte.size
            if frac_tecido >= LIMIAR_TECIDO:
                candidatos.append((x0, y0))
    return candidatos


def extrair_tile(za_nivel0, x0, y0):
    janela = za_nivel0[y0:y0 + TILE_NATIVO, x0:x0 + TILE_NATIVO]
    return cv2.resize(np.asarray(janela), (TILE_TRABALHO, TILE_TRABALHO), interpolation=cv2.INTER_AREA)


def gate_diversidade(candidatos_ordenados, k):
    """Supressão espacial gulosa: só aceita um tile se estiver longe o bastante dos já aceitos."""
    aceitos = []
    for item in candidatos_ordenados:
        x0, y0 = item["x0"], item["y0"]
        cx, cy = x0 + TILE_NATIVO / 2, y0 + TILE_NATIVO / 2
        muito_perto = any(
            ((cx - (a["x0"] + TILE_NATIVO / 2)) ** 2 + (cy - (a["y0"] + TILE_NATIVO / 2)) ** 2) ** 0.5 < DIST_MIN_DIVERSIDADE
            for a in aceitos
        )
        if not muito_perto:
            aceitos.append(item)
        if len(aceitos) >= k:
            break
    return aceitos


def carregar_rois_ground_truth(roi_csv_path):
    rois = []
    with open(roi_csv_path, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            rois.append({
                "roi": linha["roi"],
                "x": int(linha["x"]), "y": int(linha["y"]),
                "w": int(linha["w"]), "h": int(linha["h"]),
            })
    return rois


def bbox_sobrepoe(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or
                a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svs", help="Caminho do .svs (padrão: svs: em Caminhos/caminhos.md)")
    parser.add_argument("--k", type=int, nargs="+", default=[8, 16, 32, 64], help="Valores de k a avaliar")
    args = parser.parse_args()

    caminho_svs = resolver_caminho_svs(args.svs)
    output_dir = OUTPUTS_ROOT / caminho_svs.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Lâmina: {caminho_svs}")

    # --- estágio 1: máscara de tecido já validada ---
    rgb4 = carregar_thumbnail(caminho_svs)
    hsv4 = cv2.cvtColor(rgb4, cv2.COLOR_RGB2HSV)
    mask4 = filtro_otsu_saturacao_morfologia(hsv4, rgb4)

    tif = tifffile.TiffFile(str(caminho_svs))
    largura_full = tif.pages[0].shape[1]
    altura_full = tif.pages[0].shape[0]
    ds4 = largura_full / rgb4.shape[1]

    store = tif.series[0].aszarr()
    za = zarr.open(store, mode="r")
    za_nivel0 = za["0"] if hasattr(za, "array_keys") else za

    candidatos_xy = montar_grade_candidatos(largura_full, altura_full, mask4, ds4)
    print(f"{len(candidatos_xy)} tiles candidatos com tecido (grade {TILE_NATIVO}px no nível nativo)")

    # --- QuiltNet-B-32 ---
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Carregando QuiltNet-B-32 ({device})...")
    model, _, preprocess = open_clip.create_model_and_transforms("hf-hub:wisdomik/QuiltNet-B-32")
    tokenizer = open_clip.get_tokenizer("hf-hub:wisdomik/QuiltNet-B-32")
    model = model.to(device).eval()

    with torch.no_grad():
        texto_tok = tokenizer(BANCO_DE_FRASES).to(device)
        texto_emb = model.encode_text(texto_tok)
        texto_emb = texto_emb / texto_emb.norm(dim=-1, keepdim=True)

    # --- score de cada candidato ---
    from PIL import Image
    candidatos = []
    t0 = time.time()
    BATCH = 64
    for i in range(0, len(candidatos_xy), BATCH):
        lote_xy = candidatos_xy[i:i + BATCH]
        imgs = []
        for x0, y0 in lote_xy:
            tile = extrair_tile(za_nivel0, x0, y0)
            imgs.append(preprocess(Image.fromarray(tile)))
        batch_tensor = torch.stack(imgs).to(device)
        with torch.no_grad():
            img_emb = model.encode_image(batch_tensor)
            img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
            sim = (img_emb @ texto_emb.T)  # [batch, n_frases]
            score = sim.max(dim=1).values.cpu().numpy()
        for (x0, y0), s in zip(lote_xy, score):
            candidatos.append({"x0": x0, "y0": y0, "score": float(s)})
        if i % (BATCH * 20) == 0:
            print(f"  {i+len(lote_xy)}/{len(candidatos_xy)} tiles pontuados...")

    dt = time.time() - t0
    print(f"Pontuação de {len(candidatos)} tiles em {dt:.1f}s ({dt/len(candidatos)*1000:.1f} ms/tile)")

    candidatos_ordenados = sorted(candidatos, key=lambda c: -c["score"])

    with open(output_dir / "estagio2_scores.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["x0", "y0", "score"])
        writer.writeheader()
        writer.writerows(candidatos_ordenados)

    # --- ground truth (RoIs do estágio 1) ---
    roi_csv = BASE_DIR.parent / "outputs" / caminho_svs.stem / "recall_roi.csv"
    rois_page4 = carregar_rois_ground_truth(roi_csv)
    rois_native = [{"roi": r["roi"], "x": r["x"] * ds4, "y": r["y"] * ds4,
                     "w": r["w"] * ds4, "h": r["h"] * ds4} for r in rois_page4]

    # --- curva custo x fidelidade ---
    curva = []
    for k in sorted(args.k):
        selecionados = gate_diversidade(candidatos_ordenados, k)
        boxes_sel = [{"x": s["x0"], "y": s["y0"], "w": TILE_NATIVO, "h": TILE_NATIVO} for s in selecionados]

        acertos_tile = sum(1 for b in boxes_sel if any(bbox_sobrepoe(b, r) for r in rois_native))
        precisao = acertos_tile / len(boxes_sel) if boxes_sel else 0.0

        rois_cobertos = sum(1 for r in rois_native if any(bbox_sobrepoe(b, r) for b in boxes_sel))
        recall = rois_cobertos / len(rois_native) if rois_native else 0.0

        curva.append({
            "k": k,
            "tiles_selecionados": len(boxes_sel),
            "precisao_at_k": round(precisao, 3),
            "recall_at_k": round(recall, 3),
            "rois_cobertos": rois_cobertos,
            "total_rois": len(rois_native),
        })
        print(f"k={k:>3}: precisão@k={precisao:.2f}  recall@k={recall:.2f}  ({rois_cobertos}/{len(rois_native)} RoIs)")

    (output_dir / "estagio2_curva.json").write_text(
        json.dumps({"lamina": str(caminho_svs), "banco_de_frases": BANCO_DE_FRASES, "curva": curva},
                    indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # --- overlay visual do maior k testado ---
    maior_k = max(args.k)
    selecionados = gate_diversidade(candidatos_ordenados, maior_k)
    overlay = rgb4.copy()
    for r in rois_page4:
        cv2.rectangle(overlay, (r["x"], r["y"]), (r["x"] + r["w"], r["y"] + r["h"]), (150, 150, 150), 1)
    for s in selecionados:
        x4, y4 = int(s["x0"] / ds4), int(s["y0"] / ds4)
        w4 = h4 = max(int(TILE_NATIVO / ds4), 1)
        cv2.rectangle(overlay, (x4, y4), (x4 + w4, y4 + h4), (255, 140, 0), 2)
    cv2.imwrite(str(output_dir / "estagio2_topk_overlay.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    print(f"\nSaída em {output_dir} (estagio2_curva.json, estagio2_scores.csv, estagio2_topk_overlay.png)")


if __name__ == "__main__":
    main()
