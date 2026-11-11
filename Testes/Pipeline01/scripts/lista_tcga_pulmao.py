"""
Sorteio das lâminas do TCGA de pulmão (adenocarcinoma, LUAD × carcinoma escamoso, LUSC) pra testar a
generalização da pipeline em outro órgão. Lâminas de diagnóstico (FFPE), acesso aberto no GDC.

Fixado ANTES de baixar (commit anterior aos resultados):
  Uma lâmina por paciente (a primeira em ordem de nome de arquivo). 100 pacientes de cada projeto, sorteados
  com semente 0; em cada projeto, 60 pra treino e 40 pra teste (pacientes diferentes, por construção).

Uso: .venv/bin/python scripts/lista_tcga_pulmao.py   (consulta a API pública do GDC; grava lista_tcga_pulmao.tsv)
"""

import json
import random
import urllib.parse
import urllib.request
from pathlib import Path

N_POR_PROJETO = 100
N_TREINO = 60
SAIDA = Path(__file__).resolve().parent / "lista_tcga_pulmao.tsv"


def lâminas(projeto):
    filtro = {"op": "and", "content": [
        {"op": "in", "content": {"field": "cases.project.project_id", "value": [projeto]}},
        {"op": "in", "content": {"field": "data_type", "value": ["Slide Image"]}},
        {"op": "in", "content": {"field": "experimental_strategy", "value": ["Diagnostic Slide"]}}]}
    url = ("https://api.gdc.cancer.gov/files?filters=" + urllib.parse.quote(json.dumps(filtro))
           + "&fields=file_id,file_name,file_size,cases.submitter_id&size=5000&format=json")
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read())["data"]["hits"]


def main():
    linhas = []
    for projeto in ("TCGA-LUAD", "TCGA-LUSC"):
        por_paciente = {}
        for h in sorted(lâminas(projeto), key=lambda h: h["file_name"]):
            por_paciente.setdefault(h["cases"][0]["submitter_id"], h)
        pacientes = sorted(por_paciente)
        escolhidos = random.Random(0).sample(pacientes, N_POR_PROJETO)
        for i, p in enumerate(escolhidos):
            h = por_paciente[p]
            linhas.append([h["file_id"], h["file_name"], projeto, p, "treino" if i < N_TREINO else "teste", str(h["file_size"])])
    SAIDA.write_text("file_id\tfile_name\tprojeto\tpaciente\tconjunto\tbytes\n" + "\n".join("\t".join(l) for l in linhas) + "\n",
                     encoding="utf-8")
    print(f"{len(linhas)} lâminas em {SAIDA}; {sum(int(l[5]) for l in linhas) / 1e9:.0f} GB no total")


if __name__ == "__main__":
    main()
