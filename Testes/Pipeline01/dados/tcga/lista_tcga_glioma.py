"""
Sorteio das lâminas do TCGA de glioma pra uma tarefa de graduação: grau 2 e grau 3 (TCGA-LGG, campo
diagnoses.tumor_grade do GDC: G2 / G3) e grau 4 (TCGA-GBM, glioblastoma). Lâminas de diagnóstico (FFPE), acesso aberto.

Fixado ANTES de baixar (commit anterior aos resultados):
  Uma lâmina por paciente (a primeira em ordem de nome de arquivo). Pacientes do LGG sem grau no GDC ficam de fora;
  do GBM, só os com diagnóstico "Glioblastoma". 60 pacientes de cada grau, sorteados com semente 0.
  Avaliação por validação cruzada em 5 partes por paciente, estratificada por grau (semente 0); a parte de cada
  paciente vai na lista (coluna parte).
  Ressalva conhecida: os hospitais do LGG e do GBM não se misturam no TCGA, então grau 4 × graus 2-3 se confunde com
  o hospital; grau 2 × grau 3 vem dos mesmos hospitais.

Uso: .venv/bin/python dados/tcga/lista_tcga_glioma.py   (consulta a API pública do GDC; grava lista_tcga_glioma.tsv)
"""

import json
import random
import urllib.parse
import urllib.request
from pathlib import Path

from lista_tcga_pulmao import lâminas

N_POR_GRAU = 60
PARTES = 5
SAIDA = Path(__file__).resolve().parent / "lista_tcga_glioma.tsv"


def graus(projeto):
    filtro = {"op": "in", "content": {"field": "project.project_id", "value": [projeto]}}
    url = ("https://api.gdc.cancer.gov/cases?filters=" + urllib.parse.quote(json.dumps(filtro))
           + "&fields=submitter_id,diagnoses.tumor_grade,diagnoses.primary_diagnosis&size=5000&format=json")
    with urllib.request.urlopen(url, timeout=120) as r:
        casos = json.loads(r.read())["data"]["hits"]
    saida = {}
    for c in casos:
        d = (c.get("diagnoses") or [{}])[0]
        if projeto == "TCGA-LGG" and d.get("tumor_grade") in ("G2", "G3"):
            saida[c["submitter_id"]] = int(d["tumor_grade"][1])
        elif projeto == "TCGA-GBM" and d.get("primary_diagnosis") == "Glioblastoma":
            saida[c["submitter_id"]] = 4
    return saida


def main():
    candidatos = {2: {}, 3: {}, 4: {}}
    for projeto in ("TCGA-LGG", "TCGA-GBM"):
        g = graus(projeto)
        for h in sorted(lâminas(projeto), key=lambda h: h["file_name"]):
            p = h["cases"][0]["submitter_id"]
            if p in g:
                candidatos[g[p]].setdefault(p, (projeto, h))
    linhas = []
    for grau in (2, 3, 4):
        escolhidos = random.Random(0).sample(sorted(candidatos[grau]), N_POR_GRAU)
        ordem = sorted(escolhidos)
        random.Random(0).shuffle(ordem)
        parte = {p: j % PARTES for j, p in enumerate(ordem)}
        for p in escolhidos:
            projeto, h = candidatos[grau][p]
            linhas.append([h["file_id"], h["file_name"], projeto, p, p.split("-")[1], str(grau), str(parte[p]), "cv",
                           str(h["file_size"])])
        print(f"grau {grau}: {len(candidatos[grau])} pacientes elegíveis, {N_POR_GRAU} sorteados")
    cab = "file_id\tfile_name\tprojeto\tpaciente\thospital\tgrau\tparte\tconjunto\tbytes\n"
    SAIDA.write_text(cab + "\n".join("\t".join(l) for l in linhas) + "\n", encoding="utf-8")
    print(f"{len(linhas)} lâminas em {SAIDA}; {sum(int(l[8]) for l in linhas) / 1e9:.0f} GB no total")


if __name__ == "__main__":
    main()
