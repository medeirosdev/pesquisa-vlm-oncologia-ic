"""
Sorteio das lâminas do TCGA de rim: carcinoma de células claras (TCGA-KIRC), papilífero (TCGA-KIRP) e cromófobo
(TCGA-KICH). Lâminas de diagnóstico (FFPE), acesso aberto no GDC.

Fixado ANTES de baixar (commit anterior aos resultados):
  Uma lâmina por paciente (a primeira em ordem de nome de arquivo). 100 pacientes de cada projeto, sorteados com
  semente 0 (o KICH tem 109 pacientes com lâmina de diagnóstico).
  Duas divisões, gravadas na lista:
    conjunto_hospital (a principal): o hospital de origem é o código XX do paciente (TCGA-XX-YYYY). No TCGA de rim,
      cada hospital mandou casos de um subtipo só, então a divisão é feita dentro de cada projeto: os hospitais do
      projeto, em ordem embaralhada (semente 0), vão inteiros pro teste até o teste ter pelo menos 40 dos 100
      pacientes; o resto é treino. Nenhum hospital do teste aparece no treino.
    conjunto_aleatorio (comparação): 60 pacientes de treino e 40 de teste em cada projeto, sorteados com semente 0,
      sem olhar o hospital (como no pulmão).

Uso: .venv/bin/python dados/tcga/lista_tcga_rim.py   (consulta a API pública do GDC; grava lista_tcga_rim.tsv)
"""

import random
from pathlib import Path

from lista_tcga_pulmao import lâminas

PROJETOS = ("TCGA-KIRC", "TCGA-KIRP", "TCGA-KICH")
N_POR_PROJETO = 100
N_TESTE = 40
SAIDA = Path(__file__).resolve().parent / "lista_tcga_rim.tsv"


def hospital(paciente):
    return paciente.split("-")[1]


def main():
    linhas = []
    for projeto in PROJETOS:
        por_paciente = {}
        for h in sorted(lâminas(projeto), key=lambda h: h["file_name"]):
            por_paciente.setdefault(h["cases"][0]["submitter_id"], h)
        escolhidos = random.Random(0).sample(sorted(por_paciente), N_POR_PROJETO)
        aleatorio = {p: ("treino" if i < N_POR_PROJETO - N_TESTE else "teste") for i, p in enumerate(escolhidos)}
        hospitais = sorted({hospital(p) for p in escolhidos})
        random.Random(0).shuffle(hospitais)
        teste_h, n = set(), 0
        for hs in hospitais:
            if n >= N_TESTE:
                break
            teste_h.add(hs)
            n += sum(hospital(p) == hs for p in escolhidos)
        for p in escolhidos:
            h = por_paciente[p]
            linhas.append([h["file_id"], h["file_name"], projeto, p, hospital(p),
                           "teste" if hospital(p) in teste_h else "treino", aleatorio[p], str(h["file_size"])])
        print(f"{projeto}: hospitais no teste {sorted(teste_h)} ({n} pacientes); no treino "
              f"{sorted(set(hospitais) - teste_h)}")
    cab = "file_id\tfile_name\tprojeto\tpaciente\thospital\tconjunto\tconjunto_aleatorio\tbytes\n"
    SAIDA.write_text(cab + "\n".join("\t".join(l) for l in linhas) + "\n", encoding="utf-8")
    print(f"{len(linhas)} lâminas em {SAIDA}; {sum(int(l[7]) for l in linhas) / 1e9:.0f} GB no total")


if __name__ == "__main__":
    main()
