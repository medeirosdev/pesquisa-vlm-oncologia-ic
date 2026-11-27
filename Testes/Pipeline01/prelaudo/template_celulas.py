"""
Células dentro do laudo (revisão 02, item D2): o template de secoes_por_codigo.py ganha, abaixo de cada região da seção
"Regiões para revisão prioritária", uma linha com as medidas do CellViT naquela região.

Antes: o paper dizia que o laudo trazia a composição celular, mas os laudos avaliados não a traziam; o CellViT só era
medido à parte (celulas_regioes.py na próstata, celulas_pulmao.py no pulmão).

Fixado ANTES de rodar (commit anterior aos resultados):
  Documentos e campos: os mesmos do braço T (template, sem modelo de linguagem) de secoes_por_codigo.py no pulmão (78) e
     de prostata_r0.py na próstata (60, modelo único r0), em pt e en.
  Células: pulmão, resultados/celulas_pulmao/nucleos.json; próstata, resultados/celulas_regioes_r0/nucleos.json. Chave
     <id>_<ordem>, com a ordem das regiões nos campos (conferida: na próstata, as 180 regiões batem pela coordenada).
  Linha por região (código, sem modelo de linguagem), na região central de 128 µm da janela do CellViT:
     pt: "  células (CellViT, 128 µm centrais): N núcleos, área nuclear mediana A µm²; tipos (CellViT sem retreino):
          neoplásico x%, inflamatório y%, ..."
     en: "  cells (CellViT, central 128 µm): N nuclei, median nuclear area A µm²; types (CellViT without retraining):
          neoplastic x%, ..."
     Com menos de 5 núcleos, só o número ("poucos núcleos para as medidas" / "too few nuclei for the measures"); sem
     dado do CellViT, "sem medida do CellViT" / "no CellViT measurement".
  Saída nova (não sobrescreve o template antigo): resultados/secoes_por_codigo/template_celulas/<lg>/<orgao>/<id>.md.
  Conferência (critério T0, o template continua sem erro): a mesma checagem do braço T de secoes_por_codigo.etapa_checar
     (avisos_por_codigo.medir): no laudo com as células, 0 classes trocadas, 0 avisos em região concordante e 0
     coordenadas inventadas; no laudo sem as linhas de células, 0 números sem sustentação nos campos (os números das
     células vêm do nucleos.json, não dos campos); e classe lida por código na impressão = sugerida em 100%, nos 4 casos.
  Os parágrafos do modelo de linguagem não mudam (foram gerados sem as células); as células entram só pelo código.
  Limite conhecido: os tipos do CellViT (PanNuke) não foram retreinados nem validados nestes tecidos; só o número de
     núcleos e a área são tratados como medida, e os tipos vão com a ressalva no próprio laudo.

Uso (venv do projeto; depois dos CellViT dos dois órgãos): .venv/bin/python prelaudo/template_celulas.py
Saída: resultados/secoes_por_codigo/template_celulas/{pt,en}/{pulmao,prostata}/<id>.md e resumo.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "secoes_por_codigo" / "template_celulas"
NUC = {"pulmao": RESULTADOS_DIR / "celulas_pulmao" / "nucleos.json",
       "prostata": RESULTADOS_DIR / "celulas_regioes_r0" / "nucleos.json"}
MIN_NUCLEOS = 5
ORDEM_TIPOS = ("neoplasico", "inflamatorio", "conjuntivo", "epitelial", "morto")
NOME_TIPO = {"pt": {"neoplasico": "neoplásico", "inflamatorio": "inflamatório", "conjuntivo": "conjuntivo",
                    "epitelial": "epitelial", "morto": "morto"},
             "en": {"neoplasico": "neoplastic", "inflamatorio": "inflammatory", "conjuntivo": "connective",
                    "epitelial": "epithelial", "morto": "dead"}}
TXT = {"pt": {"ini": "  células (CellViT, 128 µm centrais): ", "nuc": "núcleos", "area": "área nuclear mediana",
              "tipos": "tipos (CellViT sem retreino)", "poucos": "poucos núcleos para as medidas",
              "sem": "  células: sem medida do CellViT"},
       "en": {"ini": "  cells (CellViT, central 128 µm): ", "nuc": "nuclei", "area": "median nuclear area",
              "tipos": "types (CellViT without retraining)", "poucos": "too few nuclei for the measures",
              "sem": "  cells: no CellViT measurement"}}


def linha_celulas(reg, lg):
    t = TXT[lg]
    if reg is None:
        return t["sem"]
    nuc = reg["nucleos"]
    if len(nuc) < MIN_NUCLEOS:
        return f"{t['ini']}{len(nuc)} {t['nuc']} ({t['poucos']})"
    area = float(np.median([x["area_um2"] for x in nuc]))
    cont = {k: sum(x["tipo"] == k for x in nuc) for k in ORDEM_TIPOS}
    tipos = ", ".join(f"{NOME_TIPO[lg][k]} {100 * v / len(nuc):.0f}%" for k, v in cont.items() if v)
    return f"{t['ini']}{len(nuc)} {t['nuc']}, {t['area']} {area:.1f} µm²; {t['tipos']}: {tipos}"


def com_celulas(laudo, orgao, lg, k, nucleos):
    """Insere a linha de células depois de cada linha de região da seção de regiões, na ordem dos campos."""
    import secoes_por_codigo as spc
    tit = spc.TIT[lg][3]
    out, dentro, o = [], False, 0
    for l in laudo.splitlines():
        out.append(l)
        if l.startswith("## "):
            dentro = l == tit
            continue
        if dentro and l.startswith("["):
            o += 1
            out.append(linha_celulas(nucleos.get(f"{k}_{o}"), lg))
    return "\n".join(out) + "\n", o


def casos():
    import secoes_por_codigo as spc
    from prostata_r0 import casos_secoes_r0
    c = {k: v for k, v in spc.casos().items() if k[0] == "pulmao"}
    c.update(casos_secoes_r0())
    return c


def main(saida=SAIDA, nuc=NUC):
    import avisos_por_codigo as apc
    import secoes_por_codigo as spc
    from extracao_codigo import por_codigo
    nucleos = {o: json.loads(p.read_text(encoding="utf-8")) for o, p in nuc.items()}
    res = {}
    for (orgao, lg), docs in casos().items():
        pasta = saida / lg / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        soma = {"classe_trocada": 0, "aviso_em_regiao_concordante": 0, "coordenadas_inventadas": 0, "coordenadas": 0,
                "nao_sustentados": 0, "numeros_checados": 0}
        cl = sem_dado = regioes = 0
        for k, sug, base, campos in docs:
            antigo = spc.montar(orgao, lg, sug, base, campos, spc.resumo_template(campos, lg))
            novo, n_reg = com_celulas(antigo, orgao, lg, k, nucleos[orgao])
            (pasta / f"{k}.md").write_text(novo, encoding="utf-8")
            m_novo = apc.medir(orgao, lg, sug, base, novo, campos)      # classe, aviso, coordenadas: laudo com células
            m_ant = apc.medir(orgao, lg, sug, base, antigo, campos)     # números: só as seções vindas dos campos
            for x in ("classe_trocada", "aviso_em_regiao_concordante", "coordenadas_inventadas", "coordenadas"):
                soma[x] += m_novo[x]
            for x in ("nao_sustentados", "numeros_checados"):
                soma[x] += m_ant[x]
            cl += por_codigo(orgao, lg, novo) == sug
            regioes += n_reg
            sem_dado += sum(nucleos[orgao].get(f"{k}_{o}") is None for o in range(1, n_reg + 1))
        r = {"n": len(docs), "classe_lida_igual": f"{cl}/{len(docs)}", "regioes": regioes, "regioes_sem_celulas": sem_dado,
             **soma}
        r["criterio_T0"] = (soma["classe_trocada"] == 0 and soma["aviso_em_regiao_concordante"] == 0
                            and soma["coordenadas_inventadas"] == 0 and soma["nao_sustentados"] == 0 and cl == len(docs))
        res[f"template_celulas_{orgao}_{lg}"] = r
        print(f"{orgao} {lg}: {r} | T0 {'SIM' if r['criterio_T0'] else 'NÃO'}")
    res["criterio_T0"] = all(v["criterio_T0"] for v in res.values() if isinstance(v, dict))
    (saida / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"T0 {'SIM' if res['criterio_T0'] else 'NÃO'}")

if __name__ == "__main__":
    main()
