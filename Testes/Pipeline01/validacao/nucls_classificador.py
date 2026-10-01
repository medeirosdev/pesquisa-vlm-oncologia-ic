"""
Método 3, segunda versão: mantém a DETECÇÃO de núcleos do CellViT (que funciona: acha 82–93% dos
núcleos do NuCLS) e troca a CLASSIFICAÇÃO do tipo (que falhou: Spearman 0,28 na medida) por uma
camada treinada no NuCLS, avaliada em hospitais que não entraram no treino.

Fixado ANTES de rodar (commit anterior aos resultados):
  - Descrição de cada núcleo detectado: média dos tokens do CellViT (camada final, 384-d, um a
    cada 16 px) que cobrem a caixa do núcleo.
  - Rótulo pra treino: classe do núcleo anotado pareado a <= 5 µm (mesmo pareamento e mesma
    correspondência de nucls_cellvit.py: neoplasico, conjuntivo, inflamatorio, epitelial);
    detecção sem par fica fora do treino.
  - Classificador: logística multinomial de categoria_uni.py (padronizada, balanceada, L2 ~ C=1),
    sem ajuste de hiperparâmetro.
  - Avaliação: os 5 folds oficiais do NuCLS (train_test_splits/fold_1..5), que separam treino e
    teste por hospital; cada campo é avaliado uma vez, no fold em que é teste. Todas as detecções
    do campo de teste são reclassificadas.
  - Critério de "a medida é confiável" (o mesmo de nucls_cellvit.py): nos campos de teste com
    >= 10 núcleos de tumor anotados, Spearman >= 0,7 E |viés médio| <= 0,10 entre a medida com os
    tipos novos e a medida com a anotação. Referência: os tipos originais do CellViT nos mesmos campos.

Roda no ambiente do CellViT:
    "/media/medeiros/HD 1TB/venvs/cellvit/bin/python" validacao/nucls_classificador.py
"""

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from scipy.stats import spearmanr

from categoria_uni import logistica_multinomial
from nucleos_cellvit import JANELA, TIPOS, carregar_modelo
from nucls_cellvit import MIN_TUMOR, MPP_CELLVIT, MPP_NUCLS, NUCLS, RAIO_PAR_UM, SAIDA, anotados, medida

CLASSES = ["neoplasico", "conjuntivo", "inflamatorio", "epitelial"]
TOKENS = SAIDA / "tokens"
TAM_TOKEN = 16


@torch.no_grad()
def detectar_com_tokens(modelo, media, desvio, png, dispositivo):
    """Detecções do CellViT (x, y em µm; tipo original) e a descrição de 384 números de cada uma."""
    rgb = np.array(Image.open(png).convert("RGB"))
    f = MPP_NUCLS / MPP_CELLVIT
    img = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    H, W = img.shape[:2]
    pad = np.full((-(-H // JANELA) * JANELA, -(-W // JANELA) * JANELA, 3), 255, np.uint8)
    pad[:H, :W] = img
    xy, tipos, feats = [], [], []
    for y0 in range(0, pad.shape[0], JANELA):
        for x0 in range(0, pad.shape[1], JANELA):
            janela = pad[y0:y0 + JANELA, x0:x0 + JANELA]
            x = torch.from_numpy(((janela.astype(np.float32) / 255 - media) / desvio).transpose(2, 0, 1))[None].to(dispositivo)
            with torch.autocast("cuda", dtype=torch.float16, enabled=dispositivo == "cuda"):
                o = modelo(x, retrieve_tokens=True)
            tok = o["tokens"][0].float().cpu().numpy()  # 384 x h x w
            pred = {k: o[k].float() for k in ("nuclei_binary_map", "nuclei_type_map", "hv_map")}
            pred["nuclei_binary_map"] = F.softmax(pred["nuclei_binary_map"], 1)
            pred["nuclei_type_map"] = F.softmax(pred["nuclei_type_map"], 1)
            _, celulas = modelo.calculate_instance_map(pred, magnification=40)
            for c in celulas[0].values():
                cx, cy = float(c["centroid"][0]), float(c["centroid"][1])
                if x0 + cx >= W or y0 + cy >= H:
                    continue
                (r0, c0), (r1, c1) = c["bbox"]
                t = tok[:, r0 // TAM_TOKEN: max(r1 - 1, r0) // TAM_TOKEN + 1, c0 // TAM_TOKEN: max(c1 - 1, c0) // TAM_TOKEN + 1]
                xy.append(((x0 + cx) * MPP_CELLVIT, (y0 + cy) * MPP_CELLVIT))
                tipos.append(TIPOS.get(int(c["type"]), "?"))
                feats.append(t.reshape(384, -1).mean(1))
    return np.array(xy, np.float32).reshape(-1, 2), tipos, np.array(feats, np.float16).reshape(-1, 384)


def parear_indices(gt, xy_det):
    """(índice do anotado, índice da detecção) a <= RAIO_PAR_UM, um pra um, do mais próximo pro mais distante."""
    if not gt or not len(xy_det):
        return []
    d = np.linalg.norm(np.array([g[:2] for g in gt])[:, None] - xy_det[None], axis=2)
    pares, ug, ud = [], set(), set()
    for i, j in zip(*np.unravel_index(np.argsort(d, axis=None), d.shape)):
        if d[i, j] > RAIO_PAR_UM:
            break
        if i not in ug and j not in ud:
            pares.append((i, j))
            ug.add(i)
            ud.add(j)
    return pares


def slide_do_fov(nome):
    return re.match(r"(TCGA-[A-Z0-9]+-[A-Z0-9]+-DX\d)", nome).group(1)


def main():
    TOKENS.mkdir(parents=True, exist_ok=True)
    fovs = sorted(p.stem for p in (NUCLS / "csv").glob("*.csv"))
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo = None
    for i, nome in enumerate(fovs, 1):
        arq = TOKENS / f"{nome}.npz"
        if arq.exists():
            continue
        if modelo is None:
            modelo, media, desvio = carregar_modelo(dispositivo)
        xy, tipos, feats = detectar_com_tokens(modelo, media, desvio, NUCLS / "rgb" / f"{nome}.png", dispositivo)
        np.savez_compressed(arq, xy=xy, tipos=np.array(tipos), feats=feats)
        if i % 100 == 0:
            print(f"  {i}/{len(fovs)} FOVs", flush=True)

    dados = {}
    for nome in fovs:
        z = np.load(TOKENS / f"{nome}.npz")
        gt = anotados(NUCLS / "csv" / f"{nome}.csv")
        pares = parear_indices(gt, z["xy"])
        dados[nome] = {"gt": gt, "xy": z["xy"], "tipos": list(z["tipos"]), "feats": z["feats"].astype(np.float32),
                       "pares": pares}

    divisao = NUCLS / "train_test_splits"
    pred_novo = {}
    for k in range(1, 6):
        teste = {r["slide_name"] for r in csv.DictReader(open(divisao / f"fold_{k}_test.csv"))}
        treino = {r["slide_name"] for r in csv.DictReader(open(divisao / f"fold_{k}_train.csv"))}
        X, y = [], []
        for nome, d in dados.items():
            if slide_do_fov(nome) in treino:
                for i, j in d["pares"]:
                    X.append(d["feats"][j])
                    y.append(CLASSES.index(d["gt"][i][2]))
        X, y = np.array(X), np.array(y)
        nomes_teste = [n for n in dados if slide_do_fov(n) in teste and len(dados[n]["xy"])]
        X_te = np.concatenate([dados[n]["feats"] for n in nomes_teste])
        p = logistica_multinomial(X, y, X_te, k=len(CLASSES))
        pos = 0
        for n in nomes_teste:
            m = len(dados[n]["xy"])
            pred_novo[n] = [CLASSES[c] for c in p[pos:pos + m]]
            pos += m
        print(f"  fold {k}: treino {len(y)} núcleos {dict(Counter(CLASSES[c] for c in y))}; teste {len(nomes_teste)} campos",
              flush=True)

    resumo = {}
    for versao in ("cellvit_original", "classificador_nucls"):
        tipos_de = (lambda n: dados[n]["tipos"]) if versao == "cellvit_original" else (lambda n: pred_novo[n])
        aval = [n for n in pred_novo]
        pares_tipo = [(dados[n]["gt"][i][2], tipos_de(n)[j]) for n in aval for i, j in dados[n]["pares"]]
        parte1 = {}
        for t in ("neoplasico", "conjuntivo"):
            vp = sum(a == t and b == t for a, b in pares_tipo)
            parte1[t] = {"sensibilidade": round(vp / max(1, sum(a == t for a, _ in pares_tipo)), 3),
                         "valor_preditivo": round(vp / max(1, sum(b == t for _, b in pares_tipo)), 3)}
        gt_m, pr_m = [], []
        for n in aval:
            gt = dados[n]["gt"]
            if sum(g[2] == "neoplasico" for g in gt) < MIN_TUMOR:
                continue
            det = [(float(x), float(y), t) for (x, y), t in zip(dados[n]["xy"], tipos_de(n))]
            b = medida(det, "neoplasico", "conjuntivo")
            if b is not None:
                gt_m.append(medida(gt, "neoplasico", "conjuntivo"))
                pr_m.append(b)
        gt_m, pr_m = np.array(gt_m), np.array(pr_m)
        rho, vies = float(spearmanr(gt_m, pr_m).statistic), float(np.mean(pr_m - gt_m))
        resumo[versao] = {"classificacao": parte1, "medida": {
            "n_campos": int(len(gt_m)), "spearman": round(rho, 3), "vies_medio": round(vies, 3),
            "erro_absoluto_medio": round(float(np.mean(np.abs(pr_m - gt_m))), 3),
            "media_anotado": round(float(gt_m.mean()), 3), "media_metodo": round(float(pr_m.mean()), 3),
            "confiavel": bool(rho >= 0.7 and abs(vies) <= 0.10)}}
    (SAIDA / "nucls_classificador.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(f"\nCritério fixado antes (classificador NuCLS: Spearman >= 0,7 e |viés| <= 0,10): "
          f"{'SIM' if resumo['classificador_nucls']['medida']['confiavel'] else 'NÃO'}")


if __name__ == "__main__":
    main()
