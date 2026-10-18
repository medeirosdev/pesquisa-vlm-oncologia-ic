"""
Gera a lista de lâminas do conjunto de TESTE oficial do BRACS pra o teste externo do pré-laudo:
uma lâmina por paciente e por classe (a primeira em ordem de nome) — lâminas do mesmo paciente com
lesões de classes diferentes são casos distintos —, só pacientes que não aparecem nas lâminas já usadas
no projeto. Saída: scripts/lista_teste_oficial.txt, no formato que baixar_laminas.sh aceita.

Uso:
    .venv/bin/python scripts/lista_teste_oficial.py
    bash scripts/baixar_laminas.sh $(cat scripts/lista_teste_oficial.txt)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from comum.lamina import ler_caminhos, listar_laminas

GRUPO_FTP = {"N": "BT", "PB": "BT", "UDH": "BT", "FEA": "AT", "ADH": "AT", "DCIS": "MT", "IC": "MT"}
SAIDA = Path(__file__).resolve().parent / "lista_teste_oficial.txt"


def selecionar():
    ws = openpyxl.load_workbook(Path(ler_caminhos()["laminas_dir"]) / "BRACS.xlsx", read_only=True)["WSI_Information"]
    linhas = sorted((r for r in ws.iter_rows(min_row=2, values_only=True) if r[0]), key=lambda r: r[0])
    info = {r[0]: r for r in linhas}
    usadas = {p.stem for p in listar_laminas()}
    pacientes_usados = {info[s][1] for s in usadas if s in info}
    escolhidas, vistos = [], set()
    for nome, paciente, _, rotulo, conjunto, *_ in linhas:
        if str(conjunto).strip() == "Testing" and nome not in usadas and paciente not in pacientes_usados \
                and (paciente, rotulo) not in vistos:
            vistos.add((paciente, rotulo))
            escolhidas.append((nome, rotulo, paciente))
    return escolhidas


if __name__ == "__main__":
    escolhidas = selecionar()
    SAIDA.write_text("\n".join(f"test/Group_{GRUPO_FTP[r]}/Type_{r}/{n}.svs" for n, r, _ in escolhidas) + "\n", encoding="utf-8")
    from collections import Counter
    print(len(escolhidas), "lâminas de", len({p for *_, p in escolhidas}), "pacientes:", dict(Counter(r for _, r, _ in escolhidas)))
