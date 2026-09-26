"""
DCIS vs. IC olhando a vizinhança do patch. A diferença entre os dois é de localização: no DCIS
as células ficam dentro do ducto (membrana basal intacta), no IC invadem o estroma. Um patch
sozinho muitas vezes não mostra isso; o patch com os 8 vizinhos em volta pode mostrar.

Variantes, fixadas antes de rodar:
    A  só o patch (referência)
    B  média dos embeddings do patch + 8 vizinhos (3x3)
    C  voto: cada um dos 9 classificado sozinho, vence a maioria (empate -> o do centro)
    D  média numa vizinhança 5x5 (sensibilidade ao tamanho)

Vizinhos sem tecido (fora da grade de candidatos) simplesmente não entram na média/voto.
Classificação zero-shot só entre os bancos DCIS e IC (BANCO_POR_CLASSE). Métrica: acurácia
balanceada (média do acerto em DCIS e em IC), acaso = 50%. Tiles rotulados de todas as lâminas
que têm DCIS ou IC; a BRACS_748 é a única com os dois juntos, então é reportada à parte.

Uso:
    .venv/bin/python validacao/dcis_ic_vizinhanca.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from classificacao import classificar, embeddings_de_classe
from comum.lamina import RESULTADOS_DIR, TILE_NATIVO, dir_resultados, listar_laminas
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import carregar_rois, rotular_tiles

CLASSES = ["DCIS", "IC"]
VARIANTES = ["A_patch", "B_media_3x3", "C_voto_3x3", "D_media_5x5"]


def vizinhos(x0, y0, pos, raio):
    """Índices dos tiles com tecido numa janela (2*raio+1)^2 centrada em (x0, y0), centro primeiro."""
    idx = [pos[(x0, y0)]]
    for dy in range(-raio, raio + 1):
        for dx in range(-raio, raio + 1):
            j = pos.get((x0 + dx * TILE_NATIVO, y0 + dy * TILE_NATIVO))
            if (dx or dy) and j is not None:
                idx.append(j)
    return idx


def media(embs, idx):
    m = embs[idx].mean(axis=0)
    return m / np.linalg.norm(m)


def acuracia_balanceada(reais, preditas):
    por_classe = {}
    for c in CLASSES:
        pares = [(r, p) for r, p in zip(reais, preditas) if r == c]
        if pares:
            por_classe[c] = round(100 * sum(r == p for r, p in pares) / len(pares), 1)
    return {**por_classe, "balanceada": round(sum(por_classe.values()) / len(por_classe), 1) if por_classe else None,
            "n": dict(Counter(reais))}


def rodar_lamina(stem, emb_c):
    embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
    rot = [r for r in rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
           if r["classe_real"] in CLASSES]
    if not rot:
        return None
    pos = {tuple(p): i for i, p in enumerate(xy)}
    reais = [r["classe_real"] for r in rot]
    viz3 = [vizinhos(r["x0"], r["y0"], pos, 1) for r in rot]
    viz5 = [vizinhos(r["x0"], r["y0"], pos, 2) for r in rot]

    sozinho = dict(zip(range(len(xy)), classificar(embs, emb_c)))  # cada tile classificado sozinho
    preditas = {
        "A_patch": [sozinho[r["idx"]] for r in rot],
        "B_media_3x3": classificar(np.stack([media(embs, v) for v in viz3]), emb_c),
        "C_voto_3x3": [voto([sozinho[j] for j in v]) for v in viz3],
        "D_media_5x5": classificar(np.stack([media(embs, v) for v in viz5]), emb_c),
    }
    return {"reais": reais, "preditas": preditas,
            "vizinhos_com_tecido_3x3": round(float(np.mean([len(v) - 1 for v in viz3])), 2)}


def voto(classes):
    cont = Counter(classes).most_common()
    if len(cont) > 1 and cont[0][1] == cont[1][1]:
        return classes[0]  # empate: fica o do centro
    return cont[0][0]


def main():
    emb_c = embeddings_de_classe(CLASSES)
    por_lamina, tudo_reais, tudo_pred = {}, [], {v: [] for v in VARIANTES}
    for svs in listar_laminas():
        r = rodar_lamina(svs.stem, emb_c)
        if r is None:
            continue
        por_lamina[svs.stem] = {v: acuracia_balanceada(r["reais"], r["preditas"][v]) for v in VARIANTES}
        por_lamina[svs.stem]["vizinhos_com_tecido_3x3"] = r["vizinhos_com_tecido_3x3"]
        tudo_reais += r["reais"]
        for v in VARIANTES:
            tudo_pred[v] += r["preditas"][v]

    resumo = {"todas": {v: acuracia_balanceada(tudo_reais, tudo_pred[v]) for v in VARIANTES},
              "por_lamina": por_lamina}
    (RESULTADOS_DIR / "dcis_ic_vizinhanca.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                            encoding="utf-8")

    print(f"Todas as lâminas somadas — {dict(Counter(tudo_reais))}")
    for v in VARIANTES:
        a = resumo["todas"][v]
        print(f"  {v:<12} DCIS {a['DCIS']:>5}  IC {a['IC']:>5}  balanceada {a['balanceada']:>5}")
    for stem, d in por_lamina.items():
        print(f"\n{stem} ({d['A_patch']['n']}, vizinhos com tecido em média: {d['vizinhos_com_tecido_3x3']}/8)")
        for v in VARIANTES:
            a = d[v]
            print(f"  {v:<12} " + "  ".join(f"{c} {a[c]:>5}" for c in CLASSES if c in a)
                  + (f"  balanceada {a['balanceada']:>5}" if len(a) > 3 else ""))


if __name__ == "__main__":
    main()
