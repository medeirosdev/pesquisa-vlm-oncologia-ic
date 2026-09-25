"""
Estágio 3 — achado textual por patch.

Para cada um dos k patches do roteador (banco v2), compara o embedding já calculado no
estágio 2 contra o banco do descritor (espectro inteiro: benigno, atípico, maligno) e usa
as 2 frases mais similares como achado. Cada patch também recebe uma categoria sugerida:
a categoria cuja frase mais parecida tem a maior similaridade.

Variantes: --normalizar (z-score por frase contra todos os candidatos da lâmina) e
--ensemble (vários templates por frase). Sem densidade nuclear / razão H&E ainda.

Uso:
    .venv/bin/python estagio3_descritores/descritores.py --svs BRACS_1370 --k 32
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import torch

from comum.bancos import BANCO_DESCRITOR, TEMPLATES_ENSEMBLE
from comum.lamina import Lamina, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados, codificar_textos, dispositivo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio2_roteador"))
from roteador_topk import gate_diversidade  # noqa: E402

TOP_N_ACHADOS = 2
FRASES = [f for fs in BANCO_DESCRITOR.values() for f in fs]
CATEGORIA_DA_FRASE = {f: c for c, fs in BANCO_DESCRITOR.items() for f in fs}


def sufixo_de(normalizar, ensemble):
    return ("_ensemble" if ensemble else "") + ("_norm" if normalizar else "")


def similaridades(embs: np.ndarray, normalizar=False, ensemble=False) -> np.ndarray:
    """[n_patches, n_frases]. Com normalizar, z-score de cada frase contra todos os patches passados."""
    emb_frases = codificar_textos(FRASES, TEMPLATES_ENSEMBLE if ensemble else ["{}"])
    with torch.no_grad():
        sim = (torch.from_numpy(embs).to(dispositivo()) @ emb_frases.T).cpu().numpy()
    if normalizar:
        sim = (sim - sim.mean(axis=0)) / sim.std(axis=0)
    return sim


def categorias(sim: np.ndarray) -> list[str]:
    """Categoria de cada patch: a que tem a frase de maior similaridade (máximo por categoria)."""
    cats = list(BANCO_DESCRITOR)
    por_cat = np.stack([sim[:, [FRASES.index(f) for f in BANCO_DESCRITOR[c]]].max(axis=1) for c in cats], axis=1)
    return [cats[i] for i in por_cat.argmax(axis=1)]


def rodar(svs=None, k=32, normalizar=False, ensemble=False, n_exemplos=5) -> dict:
    lamina = Lamina(resolver_svs(svs))
    e2 = dir_resultados(lamina.stem, "estagio2")
    saida = dir_resultados(lamina.stem, "estagio3")
    sufixo = sufixo_de(normalizar, ensemble)

    embs, xy = carregar_embeddings_cacheados(e2)
    indice = {pos: i for i, pos in enumerate(xy)}
    with open(e2 / "estagio2_scores_v2.csv", newline="", encoding="utf-8") as f:
        ordenados = sorted(({"x0": int(r["x0"]), "y0": int(r["y0"]), "score": float(r["score"])}
                            for r in csv.DictReader(f)), key=lambda c: -c["score"])
    selecionados = gate_diversidade(ordenados, k)

    sim_todos = similaridades(embs, normalizar, ensemble)
    cat_todos = categorias(sim_todos)

    descritores = []
    for item in selecionados:
        i = indice[(item["x0"], item["y0"])]
        achados = [FRASES[j] for j in np.argsort(-sim_todos[i])[:TOP_N_ACHADOS]]
        texto = f"[{item['x0']},{item['y0']}] ({cat_todos[i]}) " + ", ".join(achados)
        descritores.append({"x0": item["x0"], "y0": item["y0"], "categoria": cat_todos[i], "achados": achados,
                            "texto": texto, "score_roteador": round(item["score"], 3),
                            "tokens_estimados": len(texto.split())})

    combinacoes = Counter(frozenset(d["achados"]) for d in descritores)
    cats_sel = Counter(d["categoria"] for d in descritores)
    resumo = {"lamina": lamina.stem, "k": len(descritores), "variante": sufixo.strip("_") or "bruto",
              "combinacoes_distintas": len(combinacoes),
              "combinacao_mais_comum": sorted(combinacoes.most_common(1)[0][0]) if combinacoes else [],
              "pct_combinacao_mais_comum": round(100 * combinacoes.most_common(1)[0][1] / len(descritores), 1)
              if descritores else None,
              "categorias_selecionados": dict(cats_sel),
              "categorias_todos_candidatos": dict(Counter(cat_todos)),
              "top_n_achados": TOP_N_ACHADOS, "descritores": descritores}
    (saida / f"estagio3_descritores_k{k}{sufixo}.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    exemplos = saida / f"exemplos_k{k}{sufixo}"
    exemplos.mkdir(exist_ok=True)
    for i, d in enumerate(sorted(descritores, key=lambda x: -x["score_roteador"])[:n_exemplos]):
        cv2.imwrite(str(exemplos / f"{i:02d}_x{d['x0']}_y{d['y0']}.png"),
                    cv2.cvtColor(lamina.janela_nativa(d["x0"], d["y0"]), cv2.COLOR_RGB2BGR))
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--normalizar", action="store_true")
    parser.add_argument("--ensemble", action="store_true")
    a = parser.parse_args()
    r = rodar(a.svs, a.k, a.normalizar, a.ensemble)
    print(f"{r['lamina']} k={r['k']} ({r['variante']}): categorias {r['categorias_selecionados']}, "
          f"achado mais comum {r['combinacao_mais_comum']} em {r['pct_combinacao_mais_comum']}%")
