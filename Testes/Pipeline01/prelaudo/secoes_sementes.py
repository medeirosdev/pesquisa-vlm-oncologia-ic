"""
Variação entre gerações do parágrafo escrito pelo modelo de linguagem (revisão D3: uma geração por documento não mostra
variância).

Antes (secoes_por_codigo.py, semente 0): no parágrafo livre, o Gemma 3 4B cita números sem sustentação em 0 a 5
documentos por caso e o Llama 3.2 3B em 6 a 9; o critério Q não passou em nenhum dos 8 casos.

Fixado ANTES de rodar (commit anterior aos resultados):
  Gerações: as mesmas instruções e campos de secoes_por_codigo.py (braço M), com as sementes 1 e 2 do modelo de
     linguagem (temperatura 0,2), além da semente 0 já feita; Gemma 3 4B e Llama 3.2 3B; pulmão (78) e próstata (60);
     português e inglês.
  Medidas: as mesmas de secoes_por_codigo.medir_paragrafo, por semente e caso: documentos com número sem sustentação,
     números sem sustentação, coordenadas inventadas, classes trocadas, avisos em região concordante.
  Critério R (a diferença entre os modelos não depende da semente): em cada uma das 3 sementes, o total de documentos
     com número sem sustentação, somado nos 4 casos, é menor no Gemma que no Llama.
  Também reportado: mínimo e máximo entre as sementes, por caso e medida; o critério Q em cada semente.

Uso (venv do projeto; depois de redigir com --semente 1 e 2 para os dois modelos):
    .venv/bin/python prelaudo/secoes_sementes.py
Saída: resultados/secoes_por_codigo/sementes.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import secoes_por_codigo as spc  # noqa: E402

SEMENTES = [0, 1, 2]
MEDIDAS = ("nao_sustentados", "coordenadas_inventadas", "classe_trocada", "aviso_em_regiao_concordante")


def main():
    res = {}
    for nome in spc.MODELOS.values():
        for s in SEMENTES:
            pasta_m = nome + (f"_s{s}" if s else "")
            tot_docs = 0
            for (orgao, lg), docs in spc.casos().items():
                pasta = spc.SAIDA / pasta_m / lg / orgao
                med = [spc.medir_paragrafo(orgao, lg, sug, base, c, (pasta / f"{k}_paragrafo.txt").read_text(encoding="utf-8"))
                       for k, sug, base, c in docs]
                r = {m: sum(x[m] for x in med) for m in MEDIDAS}
                r["documentos_com_numero_nao_sustentado"] = sum(x["nao_sustentados"] > 0 for x in med)
                r["Q_sem_classe_lida"] = all(r[m] == 0 for m in MEDIDAS)
                tot_docs += r["documentos_com_numero_nao_sustentado"]
                res.setdefault(nome, {}).setdefault(f"{orgao}_{lg}", {})[f"semente_{s}"] = r
            res[nome].setdefault("total_documentos_com_numero_nao_sustentado", {})[f"semente_{s}"] = tot_docs
    for nome in spc.MODELOS.values():
        for caso, v in res[nome].items():
            if caso.startswith("total"):
                continue
            v["faixa"] = {m: [min(v[f"semente_{s}"][m] for s in SEMENTES), max(v[f"semente_{s}"][m] for s in SEMENTES)]
                          for m in (*MEDIDAS, "documentos_com_numero_nao_sustentado")}
    g, l = res["gemma"]["total_documentos_com_numero_nao_sustentado"], res["llama"]["total_documentos_com_numero_nao_sustentado"]
    res["criterio_R"] = all(g[f"semente_{s}"] < l[f"semente_{s}"] for s in SEMENTES)
    (spc.SAIDA / "sementes.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({n: res[n]["total_documentos_com_numero_nao_sustentado"] for n in spc.MODELOS.values()}, indent=1))
    print(f"R {'SIM' if res['criterio_R'] else 'NÃO'}")


if __name__ == "__main__":
    main()
