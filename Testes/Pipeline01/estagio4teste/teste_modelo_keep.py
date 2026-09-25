"""
Testa se o problema é o modelo (QuiltNet-B-32 fraco demais pra essa
distinção fina) repetindo EXATAMENTE a metodologia de banco_por_classe.py
(mesmos patches rotulados, mesmo banco de frases por classe, mesma
classificação por argmax) trocando só o encoder por KEEP (ViT-L/16 + BERT,
~0.4B parâmetros, MIT, reportado como mais forte que QuiltNet em vários
zero-shot na aba Modelos Locais).

Diferente do QuiltNet, o KEEP não tem embedding cacheado do estágio 2 —
carrega via transformers (trust_remote_code=True, código do próprio
repositório do modelo), não via open_clip. Precisa reextrair o pixel de
cada patch rotulado direto da lâmina (mesma leitura em janela via zarr) e
recodificar do zero.

Uso:
    .venv/bin/python teste_modelo_keep.py
"""

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torchvision import transforms
from transformers import AutoModel, AutoTokenizer

BASE_DIR = Path(__file__).parent
ESTAGIO1_OUTPUTS = BASE_DIR.parent / "outputs"
ESTAGIO2_OUTPUTS = BASE_DIR.parent / "estagio2" / "outputs"
OUTPUTS_ROOT = BASE_DIR / "outputs"
TILE_NATIVO = 512

from banco_por_classe import BANCO_POR_CLASSE  # noqa: E402


def bbox_sobrepoe(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or
                a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def main():
    stem = "BRACS_748"
    output_dir = OUTPUTS_ROOT / stem
    output_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(BASE_DIR.parent / "estagio1"))
    from filtro_tecido import resolver_caminho_svs, carregar_thumbnail
    import tifffile
    import zarr

    caminho_svs = resolver_caminho_svs(None)
    rgb4 = carregar_thumbnail(caminho_svs)
    tif = tifffile.TiffFile(str(caminho_svs))
    ds4 = tif.pages[0].shape[1] / rgb4.shape[1]
    store = tif.series[0].aszarr()
    za = zarr.open(store, mode="r")
    za_nivel0 = za["0"] if hasattr(za, "array_keys") else za

    with open(ESTAGIO1_OUTPUTS / stem / "recall_roi.csv", newline="", encoding="utf-8") as f:
        rois_page4 = list(csv.DictReader(f))
    rois_nativo = []
    for r in rois_page4:
        classe = r["roi"].split(f"{stem}_", 1)[1].rsplit("_", 1)[0]
        rois_nativo.append({"classe": classe, "x": int(r["x"]) * ds4, "y": int(r["y"]) * ds4,
                             "w": int(r["w"]) * ds4, "h": int(r["h"]) * ds4})

    with open(ESTAGIO2_OUTPUTS / stem / "estagio2_embeddings_xy.csv", newline="", encoding="utf-8") as f:
        xy = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]

    rotulados = []
    for x0, y0 in xy:
        box = {"x": x0, "y": y0, "w": TILE_NATIVO, "h": TILE_NATIVO}
        classes = sorted(set(r["classe"] for r in rois_nativo if bbox_sobrepoe(box, r)))
        if len(classes) == 1:
            rotulados.append({"x0": x0, "y0": y0, "classe_real": classes[0]})
    print(f"{len(rotulados)} patches rotulados (mesmo conjunto de banco_por_classe.py)")
    print(f"distribuição: {Counter(r['classe_real'] for r in rotulados)}")

    # --- KEEP ---
    print("Carregando KEEP (Astaxanthin/KEEP, trust_remote_code=True)...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModel.from_pretrained("Astaxanthin/KEEP", trust_remote_code=True).to(device).eval()
    tokenizer = AutoTokenizer.from_pretrained("Astaxanthin/KEEP", trust_remote_code=True)

    transform = transforms.Compose([
        transforms.Resize(size=224, interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.CenterCrop(size=(224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
    ])

    classes_ordem = list(BANCO_POR_CLASSE.keys())
    emb_por_classe = {}
    with torch.no_grad():
        for classe, frases in BANCO_POR_CLASSE.items():
            tok = tokenizer(frases, max_length=256, padding="max_length", truncation=True, return_tensors="pt").to(device)
            emb = model.encode_text(tok)
            emb_por_classe[classe] = emb / emb.norm(dim=-1, keepdim=True)

    # --- reextrai pixel de cada patch rotulado e reencoda com KEEP ---
    t0 = time.time()
    BATCH = 32
    acertos = 0
    matriz = {c: Counter() for c in classes_ordem}
    detalhe = []
    for i in range(0, len(rotulados), BATCH):
        lote = rotulados[i:i + BATCH]
        imgs = []
        for r in lote:
            janela = np.asarray(za_nivel0[r["y0"]:r["y0"] + TILE_NATIVO, r["x0"]:r["x0"] + TILE_NATIVO])
            imgs.append(transform(Image.fromarray(janela)))
        batch_tensor = torch.stack(imgs).to(device)
        with torch.no_grad():
            img_emb = model.encode_image(batch_tensor)
            img_emb = img_emb / img_emb.norm(dim=-1, keepdim=True)
            scores_todas_classes = {c: (img_emb @ emb_por_classe[c].T).max(dim=1).values.cpu().numpy() for c in classes_ordem}
        for j, r in enumerate(lote):
            scores = {c: float(scores_todas_classes[c][j]) for c in classes_ordem}
            predita = max(scores, key=scores.get)
            correto = predita == r["classe_real"]
            acertos += correto
            matriz[r["classe_real"]][predita] += 1
            detalhe.append({**r, "classe_predita": predita, "acertou": correto})
        if i % (BATCH * 10) == 0:
            print(f"  {i+len(lote)}/{len(rotulados)} reprocessados...")

    dt = time.time() - t0
    acuracia = acertos / len(rotulados)
    baseline_maioria = max(Counter(r["classe_real"] for r in rotulados).values()) / len(rotulados)

    print(f"\n{len(rotulados)} patches reprocessados com KEEP em {dt:.1f}s")
    print(f"Acurácia KEEP: {acuracia:.1%} ({acertos}/{len(rotulados)})")
    print(f"Acurácia QuiltNet-B-32 (mesmo teste, banco_por_classe.py): 23,9%")
    print(f"Baseline (classe majoritária): {baseline_maioria:.1%}")
    print("\nMatriz de confusão (linha = real, coluna = predita):")
    print("real\\pred  " + "  ".join(f"{c:>6}" for c in classes_ordem))
    for c_real in classes_ordem:
        linha = "  ".join(f"{matriz[c_real][c_pred]:>6}" for c_pred in classes_ordem)
        print(f"{c_real:>9}  {linha}")

    (output_dir / "teste_modelo_keep_resultado.json").write_text(
        json.dumps({
            "modelo": "Astaxanthin/KEEP",
            "n_rotulados": len(rotulados),
            "acuracia": round(acuracia, 4),
            "acuracia_quiltnet_referencia": 0.239,
            "baseline_maioria": round(baseline_maioria, 4),
            "matriz_confusao": {c: dict(matriz[c]) for c in classes_ordem},
            "detalhe": detalhe,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaída em {output_dir / 'teste_modelo_keep_resultado.json'}")


if __name__ == "__main__":
    main()
