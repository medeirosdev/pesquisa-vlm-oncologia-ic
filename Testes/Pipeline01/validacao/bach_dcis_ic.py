"""
Plano UNI2-h, teste 4: o classificador DCIS vs. IC treinado no BRACS (Nápoles) funciona em outra
instituição? Aplicado SEM retreino nas imagens de microscopia do BACH (Ipatimup/INEB, Portugal;
ICIAR 2018, licença CC BY-NC-ND — Aresta et al., Medical Image Analysis 2019): "InSitu" vs. "Invasive".

Fixado ANTES de rodar (commit anterior aos resultados):
  - Treino: só BRACS — os tiles do teste 1 (dcis_ic_uni.dados) das 3 lâminas com DCIS e IC,
    todos juntos. Mesma logística do teste 1 (padronizada, balanceada, L2 ~ C=1).
  - BACH: todas as imagens InSitu e Invasive do conjunto de treino do desafio (100 + 100).
    Cada imagem é cortada em tiles de 128 µm de lado (a área de um tile de 512 px a 0,25 µm/px),
    sem sobreposição; entram os tiles com >= 50% de tecido (mascara_tecido). Mesmo
    pré-processamento da pipeline (reduz pra 256 e depois 224).
  - Pontuação da imagem: média do logit de IC dos seus tiles.
  - Métrica principal: AUC por imagem (InSitu vs. Invasive), UNI2-h. Também QuiltNet + logística,
    a medida dos núcleos (se bach_nucleos.py tiver rodado) e a AUC por tile.
  - Critério de "generaliza": AUC por imagem do UNI2-h >= 0,80.

Uso (venv do projeto, depois de extrair o zip do BACH):
    .venv/bin/python validacao/bach_dcis_ic.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import numpy as np
import tifffile
import torch
from PIL import Image

from comum.lamina import RESULTADOS_DIR, TILE_NATIVO, TILE_TRABALHO
from comum.modelo import carregar_quiltnet, dispositivo
from comum.tecido import mascara_tecido
from comum.uni import embeddings_uni2h_de_recortes
from dcis_ic_nucleos import LAMINAS, auc
from dcis_ic_uni import dados, logistica_prob_ic

BACH_DIR = Path("/media/medeiros/HD 1TB/Dados Gerais/BACH")
MPP_BACH = 0.42        # µm/px das imagens de microscopia do BACH (Aresta et al. 2019); conferido nos metadados
MPP_PIPELINE = 0.25    # nível 0 do BRACS (40x)
LADO_UM = TILE_NATIVO * MPP_PIPELINE  # 128 µm
MIN_TECIDO = 0.5
CLASSES_BACH = {"InSitu": 0, "Invasive": 1}
SAIDA = RESULTADOS_DIR / "BACH"


def imagens_bach():
    imgs = sorted(p for p in BACH_DIR.rglob("*.tif") if p.parent.name in CLASSES_BACH)
    return [(p, CLASSES_BACH[p.parent.name]) for p in imgs]


def tiles_da_imagem(caminho):
    rgb = tifffile.imread(caminho)[..., :3]
    lado = round(LADO_UM / MPP_BACH)
    mask = mascara_tecido(cv2.resize(rgb, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA))
    mask = cv2.resize((mask > 0).astype(np.uint8), (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_NEAREST)
    recortes, pos = [], []
    for y in range(0, rgb.shape[0] - lado + 1, lado):
        for x in range(0, rgb.shape[1] - lado + 1, lado):
            if mask[y:y + lado, x:x + lado].mean() >= MIN_TECIDO:
                recortes.append(rgb[y:y + lado, x:x + lado])
                pos.append((x, y))
    return recortes, pos


def embeddings_quiltnet_de_recortes(recortes):
    modelo, preprocess, _ = carregar_quiltnet()
    embs = []
    for i in range(0, len(recortes), 64):
        lote = [preprocess(Image.fromarray(cv2.resize(r, (TILE_TRABALHO, TILE_TRABALHO), interpolation=cv2.INTER_AREA)))
                for r in recortes[i:i + 64]]
        with torch.no_grad():
            e = modelo.encode_image(torch.stack(lote).to(dispositivo()))
            embs.append((e / e.norm(dim=-1, keepdim=True)).cpu().numpy())
    return np.concatenate(embs)


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    imagens = imagens_bach()
    print(f"BACH: {sum(y == 0 for _, y in imagens)} InSitu, {sum(y == 1 for _, y in imagens)} Invasive")

    # embeddings do BACH (cache)
    cache = SAIDA / "embeddings_tiles.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        uni, quilt, img_idx = z["uni"], z["quilt"], z["img_idx"]
    else:
        uni, quilt, img_idx = [], [], []
        for i, (p, _) in enumerate(imagens):
            recortes, _ = tiles_da_imagem(p)
            if recortes:
                uni.append(embeddings_uni2h_de_recortes(recortes))
                quilt.append(embeddings_quiltnet_de_recortes(recortes))
                img_idx += [i] * len(recortes)
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(imagens)} imagens", flush=True)
        uni, quilt, img_idx = np.concatenate(uni), np.concatenate(quilt), np.array(img_idx)
        np.savez(cache, uni=uni, quilt=quilt, img_idx=img_idx)
    y_img = np.array([y for _, y in imagens])
    y_tile = y_img[img_idx]

    # treino: só BRACS
    D = {s: dados(s) for s in LAMINAS}
    y_tr = np.concatenate([D[s]["y"] for s in LAMINAS])
    resumo = {"n_imagens": {"InSitu": int((y_img == 0).sum()), "Invasive": int((y_img == 1).sum())},
              "n_tiles": int(len(img_idx))}
    for nome, X_bach, chave in (("uni2h", uni, "uni2h"), ("quiltnet", quilt, "quiltnet")):
        logit = logistica_prob_ic(np.concatenate([D[s][chave] for s in LAMINAS]), y_tr, X_bach)
        por_img = np.array([logit[img_idx == i].mean() if (img_idx == i).any() else np.nan for i in range(len(imagens))])
        ok = ~np.isnan(por_img)
        resumo[nome] = {"auc_por_imagem": auc(por_img[ok & (y_img == 1)], por_img[ok & (y_img == 0)]),
                        "auc_por_tile": auc(logit[y_tile == 1], logit[y_tile == 0])}

    nuc = SAIDA / "nucleos_por_imagem.json"
    if nuc.exists():
        m = json.loads(nuc.read_text(encoding="utf-8"))
        v = np.array([m.get(p.name, np.nan) for p, _ in imagens], dtype=float)
        ok = ~np.isnan(v)
        resumo["nucleos"] = {"auc_por_imagem": auc(v[ok & (y_img == 1)], v[ok & (y_img == 0)]),
                             "imagens_com_tumor": int(ok.sum())}

    resumo["generaliza"] = resumo["uni2h"]["auc_por_imagem"] >= 0.80
    (SAIDA / "bach_dcis_ic.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(f"\nCritério fixado antes (UNI2-h, AUC por imagem >= 0,80): {'SIM' if resumo['generaliza'] else 'NÃO'}")


if __name__ == "__main__":
    main()
