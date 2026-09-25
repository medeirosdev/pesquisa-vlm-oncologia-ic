"""
Troca frases do banco do descritor uma de cada vez e mede o efeito no acerto de categoria
(benigno / atípico / maligno) somando todas as lâminas. Guloso: cada troca é testada em cima
das que já foram aceitas.

Regra de aceite, fixada antes de rodar: a troca fica se a média das 3 categorias (acurácia
balanceada) subir pelo menos LIMIAR_PP pontos percentuais. Tudo é registrado, inclusive o que
foi rejeitado, em validacao/experimento_frases.md.

Ressalva: as frases são ajustadas olhando as mesmas lâminas em que são avaliadas — o ganho
pode não se repetir em lâminas novas. O banco final precisa ser conferido em outras lâminas.

Uso (depois de rodar a pipeline pelo menos até o estágio 2 em todas as lâminas):
    .venv/bin/python validacao/experimento_frases.py
"""

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from comum.bancos import BANCO_DESCRITOR, CATEGORIA_DA_CLASSE
from comum.lamina import RESULTADOS_DIR, dir_resultados, listar_laminas
from comum.modelo import carregar_embeddings_cacheados, codificar_textos, dispositivo
from comum.rois import carregar_rois, rotular_tiles

LIMIAR_PP = 0.5
CATEGORIAS = ["benigno", "atipico", "maligno"]

# (frase atual, frase candidata). Ordem = prioridade: primeiro a fronteira maligno x atípico
# (o erro que sobrou), depois benignas. Cada candidata descreve o que DIFERENCIA, não só o nome.
CANDIDATAS = [
    ("ductal carcinoma in situ", "duct completely filled by atypical cells"),
    ("atypical ductal hyperplasia", "atypical cells partially filling a duct"),
    ("focal atypical epithelial proliferation", "focal atypical proliferation involving part of a duct"),
    ("mild nuclear atypia", "mild uniform nuclear atypia"),
    ("usual ductal hyperplasia", "heterogeneous streaming cells with peripheral slit-like spaces"),
    ("flat epithelial atypia", "one to few layers of atypical columnar cells lining acini"),
    ("high nuclear pleomorphism", "large pleomorphic nuclei with prominent nucleoli"),
    ("invasive carcinoma", "irregular infiltrating glands without myoepithelial cells"),
    ("tumor nests", "solid nests of malignant cells in desmoplastic stroma"),
    ("unremarkable breast lobules", "small lobules with open acini and bland nuclei"),
    ("normal breast parenchyma", "normal breast parenchyma with loose intralobular stroma"),
    ("fibroadenoma", "fibroadenoma with compressed slit-like ducts in cellular stroma"),
    ("sclerosing adenosis", "sclerosing adenosis with compressed glands and preserved myoepithelial cells"),
    ("apocrine metaplasia", "apocrine cells with abundant granular eosinophilic cytoplasm"),
]


def carregar_dados():
    """Embeddings dos tiles rotulados de todas as lâminas + categoria real de cada um."""
    vetores, reais, laminas = [], [], []
    for svs in listar_laminas():
        stem = svs.stem
        if not (RESULTADOS_DIR / stem / "estagio1" / "recall_roi.csv").exists():
            continue
        embs, xy = carregar_embeddings_cacheados(dir_resultados(stem, "estagio2"))
        rot = rotular_tiles(xy, [r for r in carregar_rois(stem) if r["correlacao"] >= 0.5])
        if not rot:
            continue
        vetores.append(embs[[r["idx"] for r in rot]])
        reais += [CATEGORIA_DA_CLASSE[r["classe_real"]] for r in rot]
        laminas.append(stem)
    return np.concatenate(vetores), reais, laminas


_cache_texto = {}


def emb_texto(frase):
    if frase not in _cache_texto:
        _cache_texto[frase] = codificar_textos([frase])[0]
    return _cache_texto[frase]


def avaliar(banco, vetores_t, reais):
    """Acerto por categoria real (somando as lâminas) e a média das três."""
    scores = []
    with torch.no_grad():
        for c in CATEGORIAS:
            e = torch.stack([emb_texto(f) for f in banco[c]])
            scores.append((vetores_t @ e.T).max(dim=1).values)
    pred = [CATEGORIAS[i] for i in torch.stack(scores, dim=1).argmax(dim=1).cpu().numpy()]
    tot = Counter(reais)
    cert = Counter(r for r, p in zip(reais, pred) if r == p)
    por_cat = {c: 100 * cert[c] / tot[c] for c in CATEGORIAS}
    return {**{c: round(v, 1) for c, v in por_cat.items()}, "media": round(sum(por_cat.values()) / 3, 2)}


def trocar(banco, velha, nova):
    return {c: [nova if f == velha else f for f in fs] for c, fs in banco.items()}


def main():
    vetores, reais, laminas = carregar_dados()
    vetores_t = torch.from_numpy(vetores.astype(np.float32)).to(dispositivo())
    print(f"{len(reais)} tiles rotulados de {len(laminas)} lâminas: {dict(Counter(reais))}")

    banco = {c: list(fs) for c, fs in BANCO_DESCRITOR.items()}
    atual = avaliar(banco, vetores_t, reais)
    inicio = dict(atual)
    print(f"ponto de partida: {atual}")

    registro = []
    for n, (velha, nova) in enumerate(CANDIDATAS, start=1):
        categoria = next((c for c, fs in banco.items() if velha in fs), None)
        if categoria is None:
            registro.append({"n": n, "velha": velha, "nova": nova, "categoria": "—", "decisao": "frase não está no banco"})
            continue
        teste = avaliar(trocar(banco, velha, nova), vetores_t, reais)
        delta = round(teste["media"] - atual["media"], 2)
        aceita = delta >= LIMIAR_PP
        registro.append({"n": n, "velha": velha, "nova": nova, "categoria": categoria, **teste,
                         "delta": delta, "decisao": "aceita" if aceita else "rejeitada"})
        print(f"{n:>2}. [{categoria}] {velha!r} -> {nova!r}: média {teste['media']} ({delta:+.2f}) "
              f"b {teste['benigno']} a {teste['atipico']} m {teste['maligno']} -> {'ACEITA' if aceita else 'rejeitada'}")
        if aceita:
            banco, atual = trocar(banco, velha, nova), teste

    aceitas = {r["velha"]: r["nova"] for r in registro if r["decisao"] == "aceita"}
    escrever_registro(registro, inicio, atual, laminas, Counter(reais), aceitas)
    (RESULTADOS_DIR / "experimento_frases.json").write_text(
        json.dumps({"inicio": inicio, "final": atual, "aceitas": aceitas, "registro": registro},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nfinal: {atual}\naceitas: {aceitas}")


def escrever_registro(registro, inicio, final, laminas, dist, aceitas):
    p = Path(__file__).resolve().parent / "experimento_frases.md"
    L = ["# Experimento: trocar frases do descritor uma de cada vez", "",
         f"Rodado em {time.strftime('%d/%m/%Y %H:%M')} por `experimento_frases.py`, sobre {sum(dist.values())} tiles "
         f"rotulados de {len(laminas)} lâminas (benigno {dist['benigno']}, atípico {dist['atipico']}, "
         f"maligno {dist['maligno']}).", "",
         f"**Regra de aceite (fixada antes):** a troca fica se a média das 3 categorias subir ≥ {LIMIAR_PP} ponto. "
         "Guloso: cada troca é testada em cima das já aceitas.", "",
         "**Ressalva:** as frases foram ajustadas olhando as mesmas lâminas em que são avaliadas — "
         "o ganho pode não se repetir em lâminas novas.", "",
         f"Ponto de partida: benigno {inicio['benigno']}%, atípico {inicio['atipico']}%, maligno {inicio['maligno']}%, "
         f"**média {inicio['media']}%**.", "",
         "| # | Categoria | Frase atual | Candidata | Benigno | Atípico | Maligno | Média | Δ média | Decisão |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in registro:
        if "media" not in r:
            L.append(f"| {r['n']} | — | {r['velha']} | {r['nova']} | | | | | | {r['decisao']} |")
            continue
        L.append(f"| {r['n']} | {r['categoria']} | {r['velha']} | {r['nova']} | {r['benigno']}% | {r['atipico']}% | "
                 f"{r['maligno']}% | {r['media']}% | {r['delta']:+.2f} | **{r['decisao']}** |")
    L += ["", f"**Final:** benigno {final['benigno']}%, atípico {final['atipico']}%, maligno {final['maligno']}%, "
          f"**média {final['media']}%** (partida: {inicio['media']}%).", "",
          f"Trocas aceitas ({len(aceitas)}): " + ("; ".join(f"\"{v}\" → \"{n}\"" for v, n in aceitas.items()) or "nenhuma")]
    p.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
