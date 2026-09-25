"""
O banco de frases foi ajustado olhando as 8 lâminas da primeira leva. Aqui ele é medido só nas
lâminas da segunda leva (pacientes diferentes), sem mexer em nenhuma frase: o ganho se repete?

Compara três versões do banco do descritor: sem nenhuma troca, só a troca do lóbulo, e a atual
(todas as trocas de SUBSTITUICOES_DO_DESCRITOR).

Uso (depois de rodar a pipeline nas lâminas novas):
    .venv/bin/python validacao/teste_fora_da_amostra.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import torch

from comum.bancos import BANCO_DESCRITOR, SUBSTITUICOES_DO_DESCRITOR
from comum.lamina import RESULTADOS_DIR
from comum.modelo import dispositivo
from experimento_frases import avaliar, carregar_dados

PRIMEIRA_LEVA = ["BRACS_1003677", "BRACS_1003718", "BRACS_1271", "BRACS_1370",
                 "BRACS_1489", "BRACS_1592", "BRACS_1774", "BRACS_748"]
SEGUNDA_LEVA = ["BRACS_1507", "BRACS_1641", "BRACS_1320", "BRACS_1617",
                "BRACS_743", "BRACS_1494", "BRACS_1512", "BRACS_297"]


def desfazer(banco, trocas):
    volta = {nova: velha for velha, nova in trocas.items()}
    return {c: [volta.get(f, f) for f in fs] for c, fs in banco.items()}


def main():
    lobulo = "normal terminal duct lobular unit"
    versoes = {
        "sem trocas": desfazer(BANCO_DESCRITOR, SUBSTITUICOES_DO_DESCRITOR),
        "só lóbulo": desfazer(BANCO_DESCRITOR, {v: n for v, n in SUBSTITUICOES_DO_DESCRITOR.items() if v != lobulo}),
        "atual": BANCO_DESCRITOR,
    }
    saida = {}
    for nome_leva, stems in (("primeira leva (ajuste)", PRIMEIRA_LEVA), ("segunda leva (teste)", SEGUNDA_LEVA)):
        vetores, reais, laminas = carregar_dados(stems)
        vetores_t = torch.from_numpy(vetores.astype(np.float32)).to(dispositivo())
        print(f"\n{nome_leva}: {len(reais)} tiles de {len(laminas)} lâminas {dict(Counter(reais))}")
        saida[nome_leva] = {"laminas": laminas, "distribuicao": dict(Counter(reais))}
        for nome, banco in versoes.items():
            r = avaliar(banco, vetores_t, reais)
            saida[nome_leva][nome] = r
            print(f"  {nome:<11} benigno {r['benigno']:>5}  atípico {r['atipico']:>5}  "
                  f"maligno {r['maligno']:>5}  média {r['media']:>6}")
    (RESULTADOS_DIR / "teste_fora_da_amostra.json").write_text(
        json.dumps(saida, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
