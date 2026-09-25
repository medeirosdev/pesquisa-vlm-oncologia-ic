"""
Estágio 2 — roteador top-k.

Dos tiles com tecido (máscara do estágio 1), escolhe os k mais relevantes por
similaridade contrastiva (QuiltNet-B-32) contra um banco de frases, com um gate de
diversidade espacial. Mede precisão@k e recall@k contra os RoIs do estágio 1, e
compara com um baseline de tiles aleatórios.

Bancos: v1 = 5 frases suspeitas, score = máximo. v2 = benigno/suspeito, score = margem.
Simplificação registrada: não há saliência treinada; o modo "rótulo fixo" usa a mesma
similaridade contrastiva do modo VQA.

Uso:
    .venv/bin/python estagio2_roteador/roteador_topk.py --svs BRACS_1370 --banco v2
"""

import argparse
import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import torch

from comum.bancos import BANCO_V1, BANCO_V2
from comum.lamina import TILE_NATIVO, Lamina, dir_resultados, resolver_svs
from comum.modelo import codificar_textos, dispositivo, embeddings_da_lamina
from comum.rois import bbox_sobrepoe, caixa_tile, carregar_rois
from comum.tecido import grade_candidatos, mascara_tecido

DIST_MIN_DIVERSIDADE = TILE_NATIVO * 1.5  # px no nível 0, entre centros de tiles aceitos
KS_PADRAO = [8, 16, 32, 64, 128, 256, 512, 1024]


def gate_diversidade(candidatos_ordenados, k):
    """Supressão espacial gulosa: só aceita um tile se estiver longe o bastante dos já aceitos."""
    aceitos = []
    for item in candidatos_ordenados:
        cx, cy = item["x0"] + TILE_NATIVO / 2, item["y0"] + TILE_NATIVO / 2
        if all(((cx - a["x0"] - TILE_NATIVO / 2) ** 2 + (cy - a["y0"] - TILE_NATIVO / 2) ** 2) ** 0.5
               >= DIST_MIN_DIVERSIDADE for a in aceitos):
            aceitos.append(item)
            if len(aceitos) >= k:
                break
    return aceitos


def scores(embs, banco):
    img = torch.from_numpy(embs).to(dispositivo())
    with torch.no_grad():
        if banco == "v1":
            return (img @ codificar_textos(BANCO_V1).T).max(dim=1).values.cpu().numpy()
        sus = (img @ codificar_textos(BANCO_V2["suspeito"]).T).max(dim=1).values
        ben = (img @ codificar_textos(BANCO_V2["benigno"]).T).max(dim=1).values
        return (sus - ben).cpu().numpy()


def precisao_recall(selecionados, rois):
    caixas = [caixa_tile(s["x0"], s["y0"]) for s in selecionados]
    if not caixas or not rois:
        return 0.0, 0.0, 0
    acertos = sum(1 for c in caixas if any(bbox_sobrepoe(c, r) for r in rois))
    cobertos = sum(1 for r in rois if any(bbox_sobrepoe(c, r) for c in caixas))
    return acertos / len(caixas), cobertos / len(rois), cobertos


def rodar(svs=None, banco="v2", ks=KS_PADRAO) -> dict:
    lamina = Lamina(resolver_svs(svs))
    saida = dir_resultados(lamina.stem, "estagio2")
    sufixo = "" if banco == "v1" else f"_{banco}"

    rgb, ds_thumb = lamina.thumbnail(32)
    mask = mascara_tecido(rgb)
    candidatos_xy = grade_candidatos(lamina, mask, ds_thumb)
    embs = embeddings_da_lamina(lamina, candidatos_xy, saida)

    s = scores(embs, banco)
    ordenados = sorted(({"x0": x0, "y0": y0, "score": float(v)} for (x0, y0), v in zip(candidatos_xy, s)),
                       key=lambda c: -c["score"])
    with open(saida / f"estagio2_scores{sufixo}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["x0", "y0", "score"])
        writer.writeheader()
        writer.writerows(ordenados)

    rois = [r for r in carregar_rois(lamina.stem) if r["correlacao"] >= 0.5]
    rng = random.Random(0)
    curva = []
    for k in sorted(ks):
        if k > len(ordenados):
            continue
        prec, rec, cobertos = precisao_recall(gate_diversidade(ordenados, k), rois)
        prec_aleatoria = sum(precisao_recall([{"x0": x, "y0": y} for x, y in rng.sample(candidatos_xy, k)], rois)[0]
                             for _ in range(50)) / 50
        curva.append({"k": k, "precisao": round(prec, 3), "recall": round(rec, 3), "rois_cobertos": cobertos,
                      "precisao_aleatoria": round(prec_aleatoria, 3)})

    maior_k = curva[-1]["k"] if curva else 0
    overlay = rgb.copy()
    for r in rois:
        cv2.rectangle(overlay, (int(r["x"] / ds_thumb), int(r["y"] / ds_thumb)),
                      (int((r["x"] + r["w"]) / ds_thumb), int((r["y"] + r["h"]) / ds_thumb)), (150, 150, 150), 1)
    lado = max(int(TILE_NATIVO / ds_thumb), 1)
    for t in gate_diversidade(ordenados, maior_k):
        x, y = int(t["x0"] / ds_thumb), int(t["y0"] / ds_thumb)
        cv2.rectangle(overlay, (x, y), (x + lado, y + lado), (255, 140, 0), 2)
    cv2.imwrite(str(saida / f"estagio2_topk_overlay{sufixo}.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    resumo = {"lamina": lamina.stem, "banco": banco, "candidatos": len(candidatos_xy),
              "rois_validos": len(rois), "curva": curva}
    (saida / f"estagio2_curva{sufixo}.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs", help="nome (BRACS_1370) ou caminho da lâmina; padrão: svs: do caminhos.md")
    parser.add_argument("--banco", choices=["v1", "v2"], default="v2")
    parser.add_argument("--k", type=int, nargs="+", default=KS_PADRAO)
    a = parser.parse_args()
    r = rodar(a.svs, a.banco, a.k)
    print(f"{r['lamina']}: {r['candidatos']} candidatos, {r['rois_validos']} RoIs")
    for p in r["curva"]:
        print(f"  k={p['k']:>4}: precisão={p['precisao']:.2f} (aleatório {p['precisao_aleatoria']:.2f})  "
              f"recall={p['recall']:.2f} ({p['rois_cobertos']} RoIs)")
