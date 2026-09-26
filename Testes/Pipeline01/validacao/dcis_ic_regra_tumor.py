"""
Teste da hipótese "tile de tumor cercado de tumor -> IC", vista na BRACS_748 (dcis_ic_contexto.py)
DEPOIS de olhar os dados. Por isso é testada só em lâminas que não foram usadas pra formulá-la:
BRACS_773 e BRACS_295, ambas com DCIS e IC juntos (scripts/baixar_laminas.sh --dcis-ic).

Regra fixada ANTES de baixar essas lâminas (commit anterior ao download):
    IC se >= 50% dos 8 vizinhos forem "tumor" (tipo de tecido de dcis_ic_contexto.BANCO_TECIDO);
    senão DCIS. Vizinho sem tecido conta no denominador (8 fixo).
Comparação: o patch sozinho (zero-shot DCIS vs. IC).
Métrica: acurácia balanceada DCIS/IC por lâmina e somada; acaso = 50%.
Critério de "funcionou", também fixado antes: a regra supera o patch sozinho nas DUAS lâminas.

Uso (depois de rodar a pipeline até o estágio 2 nas duas lâminas):
    .venv/bin/python validacao/dcis_ic_regra_tumor.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from classificacao import embeddings_de_classe
from comum.lamina import RESULTADOS_DIR
from dcis_ic_contexto import CLASSES, TIPOS, dados_da_lamina
from dcis_ic_vizinhanca import acuracia_balanceada

LAMINAS_TESTE = ["BRACS_773", "BRACS_295"]
LIMIAR_TUMOR = 0.5


def regra_tumor(comp):
    return ["IC" if f >= LIMIAR_TUMOR else "DCIS" for f in comp[:, TIPOS.index("tumor")]]


def main():
    emb_c = embeddings_de_classe(CLASSES)
    resumo, todos_reais, todos = {}, [], {"patch_sozinho": [], "regra_tumor": []}
    for stem in LAMINAS_TESTE:
        d = dados_da_lamina(stem, emb_c)
        pred = {"patch_sozinho": ["DCIS" if v > 0 else "IC" for v in d["score"]],
                "regra_tumor": regra_tumor(d["comp"])}
        resumo[stem] = {k: acuracia_balanceada(d["reais"], p) for k, p in pred.items()}
        todos_reais += d["reais"]
        for k, p in pred.items():
            todos[k] += p
    resumo["somadas"] = {k: acuracia_balanceada(todos_reais, p) for k, p in todos.items()}
    resumo["funcionou"] = all(resumo[s]["regra_tumor"]["balanceada"] > resumo[s]["patch_sozinho"]["balanceada"]
                              for s in LAMINAS_TESTE)

    for chave in LAMINAS_TESTE + ["somadas"]:
        print(f"{chave} {resumo[chave]['patch_sozinho']['n']}")
        for k in ("patch_sozinho", "regra_tumor"):
            a = resumo[chave][k]
            print(f"  {k:<14} DCIS {a['DCIS']:>5}  IC {a['IC']:>5}  balanceada {a['balanceada']:>5}")
    print(f"\nCritério fixado antes (regra > patch nas duas lâminas): {'SIM' if resumo['funcionou'] else 'NÃO'}")
    (RESULTADOS_DIR / "dcis_ic_regra_tumor.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                             encoding="utf-8")


if __name__ == "__main__":
    main()
