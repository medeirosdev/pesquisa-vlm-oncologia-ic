"""
Validação do método 3 contra núcleos anotados por patologistas: o CellViT classifica os núcleos
certo, e a medida "fração de núcleos de tumor com um núcleo de estroma a <= 20 µm" bate com a
mesma medida feita nos núcleos anotados?

Dados: NuCLS, conjunto single-rater corrigido por patologista (Amgad et al., GigaScience 2022;
CC0): 1.744 campos (FOVs) de câncer de mama do TCGA, 0,2 µm/px, cada núcleo com classe.
Cópia em zip de terceiros (HuggingFace minhanhto09/NuCLS_dataset), conferida contra 73 CSVs
baixados do Drive oficial: idênticos.

Fixado ANTES de rodar o CellViT (commit anterior aos resultados):
  Parte 1 — classificação dos núcleos (descritiva):
    - todos os 1.744 FOVs, reamostrados de 0,2 pra 0,25 µm/px (escala do CellViT-256-x40);
    - núcleo anotado (centro da caixa) pareado com o núcleo do CellViT mais próximo a <= 5 µm,
      um pra um, do par mais próximo pro mais distante; núcleos AMBIGUOUS ficam de fora;
    - correspondência: tumor_any -> neoplasico; nonTILnonMQ_stromal (fibroblasto, endotélio)
      -> conjuntivo; sTIL + macrófago + neutrófilo + eosinófilo -> inflamatorio;
      epitélio ductal + mioepitélio -> epitelial;
    - métricas: fração dos anotados encontrada; matriz de confusão; sensibilidade e valor
      preditivo de "neoplasico" e "conjuntivo".
  Parte 2 — a medida:
    - FOVs com >= 10 núcleos de tumor anotados (os FOVs têm ~71 µm de lado, menores que o tile
      de 128 µm; o limiar de 20 do tile foi reduzido na proporção);
    - medida calculada com os núcleos anotados (tumor vs. fibroblasto/endotélio) e com os do
      CellViT (neoplásico vs. conjuntivo), mesmo raio de 20 µm, dentro do mesmo FOV;
    - critério de "a medida é confiável": Spearman >= 0,7 E viés médio |CellViT - anotação| <= 0,10.
  Ressalvas: o PanNuke (treino do CellViT) também vem do TCGA — pode haver lâminas em comum com
  o NuCLS, o que deixaria o resultado otimista; bordas das imagens podem ter núcleos sem anotação.

Roda no ambiente do CellViT:
    "<HD>/venvs/cellvit/bin/python" validacao/nucls_cellvit.py
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import numpy as np
import torch
from PIL import Image
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

from comum.lamina import RESULTADOS_DIR, no_hd
from nucleos_cellvit import JANELA, TIPOS, carregar_modelo, segmentar

NUCLS = Path(no_hd("/media/medeiros/HD 1TB/Dados Gerais/NuCLS/NuCLS_dataset"))
MPP_NUCLS, MPP_CELLVIT = 0.2, 0.25
RAIO_PAR_UM, RAIO_MEDIDA_UM = 5, 20
MIN_TUMOR = 10
ESPERADO = {"tumor_any": "neoplasico", "nonTILnonMQ_stromal": "conjuntivo", "sTIL": "inflamatorio",
            "macrophage": "inflamatorio", "neutrophil": "inflamatorio", "eosinophil": "inflamatorio",
            "ductal_epithelium": "epitelial", "myoepithelium": "epitelial"}
SAIDA = RESULTADOS_DIR / "NuCLS"


def classe_anotada(r):
    if r["main_classification"] in ("AMBIGUOUS",):
        return None
    if r["super_classification"] in ("tumor_any", "sTIL"):
        return ESPERADO[r["super_classification"]]
    if r["main_classification"] == "nonTILnonMQ_stromal":
        return "conjuntivo"
    return ESPERADO.get(r["raw_classification"])


def anotados(csv_path):
    """Núcleos anotados em µm: (x, y, tipo esperado no CellViT)."""
    out = []
    for r in csv.DictReader(open(csv_path, encoding="utf-8")):
        t = classe_anotada(r)
        if t:
            out.append(((float(r["xmin"]) + float(r["xmax"])) / 2 * MPP_NUCLS,
                        (float(r["ymin"]) + float(r["ymax"])) / 2 * MPP_NUCLS, t))
    return out


def cellvit(modelo, media, desvio, png, dispositivo):
    """Núcleos do CellViT em µm: (x, y, tipo)."""
    rgb = np.array(Image.open(png).convert("RGB"))
    f = MPP_NUCLS / MPP_CELLVIT
    img = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    H, W = img.shape[:2]
    Hp, Wp = -(-H // JANELA) * JANELA, -(-W // JANELA) * JANELA
    pad = np.full((Hp, Wp, 3), 255, np.uint8)
    pad[:H, :W] = img
    out = []
    for y0 in range(0, Hp, JANELA):
        for x0 in range(0, Wp, JANELA):
            for c in segmentar(modelo, media, desvio, pad[y0:y0 + JANELA, x0:x0 + JANELA], dispositivo).values():
                cx, cy = x0 + float(c["centroid"][0]), y0 + float(c["centroid"][1])
                if cx < W and cy < H:
                    out.append((cx * MPP_CELLVIT, cy * MPP_CELLVIT, TIPOS.get(int(c["type"]), "?")))
    return out


def parear(gt, pred):
    """Pares um pra um, do mais próximo pro mais distante, a <= RAIO_PAR_UM."""
    if not gt or not pred:
        return []
    d = np.linalg.norm(np.array([g[:2] for g in gt])[:, None] - np.array([p[:2] for p in pred])[None], axis=2)
    pares, usados_g, usados_p = [], set(), set()
    for i, j in zip(*np.unravel_index(np.argsort(d, axis=None), d.shape)):
        if d[i, j] > RAIO_PAR_UM:
            break
        if i not in usados_g and j not in usados_p:
            pares.append((gt[i][2], pred[j][2]))
            usados_g.add(i)
            usados_p.add(j)
    return pares


def medida(nucleos, tipo_tumor, tipo_estroma):
    tum = np.array([n[:2] for n in nucleos if n[2] == tipo_tumor])
    est = np.array([n[:2] for n in nucleos if n[2] == tipo_estroma])
    if not len(tum):
        return None
    if not len(est):
        return 0.0
    d, _ = cKDTree(est).query(tum)
    return float(np.mean(d <= RAIO_MEDIDA_UM))


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    cache = SAIDA / "cellvit_por_fov.json"
    feito = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo = None
    fovs = sorted(p.stem for p in (NUCLS / "csv").glob("*.csv"))
    for i, nome in enumerate(fovs, 1):
        if nome in feito:
            continue
        if modelo is None:
            modelo, media, desvio = carregar_modelo(dispositivo)
        feito[nome] = cellvit(modelo, media, desvio, NUCLS / "rgb" / f"{nome}.png", dispositivo)
        if i % 100 == 0:
            cache.write_text(json.dumps(feito), encoding="utf-8")
            print(f"  {i}/{len(fovs)} FOVs", flush=True)
    cache.write_text(json.dumps(feito), encoding="utf-8")

    # Parte 1
    pares, n_gt, achados = [], Counter(), Counter()
    for nome in fovs:
        gt = anotados(NUCLS / "csv" / f"{nome}.csv")
        p = parear(gt, [tuple(x) for x in feito[nome]])
        pares += p
        n_gt.update(g[2] for g in gt)
        achados.update(a for a, _ in p)
    tipos = ["neoplasico", "conjuntivo", "inflamatorio", "epitelial"]
    confusao = {a: dict(Counter(b for x, b in pares if x == a)) for a in tipos}
    parte1 = {"encontrados_por_classe": {t: round(achados[t] / n_gt[t], 3) if n_gt[t] else None for t in tipos},
              "n_anotados": dict(n_gt), "matriz_confusao_anotado_para_cellvit": confusao}
    for t in ("neoplasico", "conjuntivo"):
        vp = sum(1 for a, b in pares if a == t and b == t)
        parte1[t] = {"sensibilidade": round(vp / max(1, sum(1 for a, _ in pares if a == t)), 3),
                     "valor_preditivo": round(vp / max(1, sum(1 for _, b in pares if b == t)), 3)}

    # Parte 2
    gt_m, cv_m = [], []
    for nome in fovs:
        gt = anotados(NUCLS / "csv" / f"{nome}.csv")
        if sum(g[2] == "neoplasico" for g in gt) < MIN_TUMOR:
            continue
        a = medida(gt, "neoplasico", "conjuntivo")
        b = medida([tuple(x) for x in feito[nome]], "neoplasico", "conjuntivo")
        if b is not None:
            gt_m.append(a)
            cv_m.append(b)
    gt_m, cv_m = np.array(gt_m), np.array(cv_m)
    rho = float(spearmanr(gt_m, cv_m).statistic)
    vies = float(np.mean(cv_m - gt_m))
    parte2 = {"n_fovs": int(len(gt_m)), "spearman": round(rho, 3), "vies_medio": round(vies, 3),
              "erro_absoluto_medio": round(float(np.mean(np.abs(cv_m - gt_m))), 3),
              "media_anotado": round(float(gt_m.mean()), 3), "media_cellvit": round(float(cv_m.mean()), 3),
              "confiavel": bool(rho >= 0.7 and abs(vies) <= 0.10)}
    resumo = {"parte1_classificacao": parte1, "parte2_medida": parte2}
    (SAIDA / "nucls_cellvit.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    print(f"\nCritério fixado antes (Spearman >= 0,7 e |viés| <= 0,10): {'SIM' if parte2['confiavel'] else 'NÃO'}")


if __name__ == "__main__":
    main()
