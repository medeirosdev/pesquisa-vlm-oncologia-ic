"""
Checagem de ligação número ↔ entidade no parágrafo do modelo de linguagem (revisão 01, item C5).

Antes: a checagem de números (prelaudo_campos.checar_texto) confere se cada número existe em algum lugar dos campos, não
se ele está ligado à entidade certa ("escamoso 32,7%" passa se 32,7% for a proporção de adenocarcinoma). A checagem
semântica S1 (checagem_semantica.py) cobre só as afirmações de predominância.

Fixado ANTES de rodar (commit anterior aos resultados):
  Textos: os parágrafos já gerados (nenhum modelo de linguagem roda aqui), semente 0: pulmão em
     resultados/secoes_por_codigo/{gemma,llama}/{pt,en}/pulmao/<id>_paragrafo.txt; próstata (modelo único r0) em
     resultados/secoes_por_codigo_r0/{gemma,llama}/{pt,en}/prostata/<id>_paragrafo.txt; e o resumo do template
     (secoes_por_codigo.resumo_template) como controle. Campos: os mesmos de cada caso.
  Entidades nos campos: a proporção de cada classe do classificador de patches ("- classe: N patches (P%)").
  Afirmações conferidas, por frase (a mesma divisão de checagem_semantica.frases): cada porcentagem ("P%") e cada
     contagem ("N patches") cujo valor é, na precisão escrita, a porcentagem ou a contagem de alguma classe nos campos.
     A classe ligada, na mesma frase (nomes das classes de avisos_por_codigo.LINGUA): a última citada antes do número,
     a até 80 caracteres; se logo depois do número (até 40 caracteres) vier uma expressão de atribuição ("classificad",
     "classified", "rotulad", "label", "chamad", "called", "identificad", "identified", "correspond"), a primeira citada
     depois dele; sem classe antes, a primeira depois (até 80). Sem classe, a afirmação não é conferida.
     (Regra ajustada antes do commit só com frases inventadas, nenhuma dos resultados.)
  Ligação errada: a classe ligada existe nos campos e o valor dela não é o número escrito.
  Critério V2 (validade mínima da checagem): 0 ligações erradas no resumo do template nos 4 casos (órgão × idioma).
  Também reportado: afirmações conferidas e ligações erradas por modelo, órgão e idioma; parágrafos com alguma ligação
     errada; até 3 exemplos por caso em exemplos.json, para conferência visual.
  Limites conhecidos: regra por proximidade; não cobre probabilidades, confiança, coordenadas (já cobertas pela troca
     de classe) nem flexões ("benigna" não casa com "benigno"); não substitui leitura humana.

Uso (venv do projeto): .venv/bin/python prelaudo/checagem_ligacao.py
Saída: resultados/checagem_ligacao/{resumo.json, exemplos.json}
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "checagem_ligacao"
PROP = re.compile(r"^\s*-\s*(.+?):\s*(\d+) patches \(([\d.]+)%\)", re.M)
PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
CNT = re.compile(r"(\d+)\s+patches")
DIST_MAX = 80
ATRIB = re.compile(r"classificad|classified|rotulad|label|chamad|called|identificad|identified|correspond")


def props(campos):
    return {c.strip().lower(): (int(n), p) for c, n, p in PROP.findall(campos)}


def bate(escrito, valor_campo):
    """O número escrito é o valor do campo na precisão escrita (ex.: 33 ou 32.7 para 32.7)."""
    e = escrito.replace(",", ".")
    casas = len(e.split(".")[1]) if "." in e else 0
    return abs(round(float(valor_campo), casas) - float(e)) < 1e-9


def classe_ligada(fl, m, mencoes):
    """Classe citada por último antes do número (até DIST_MAX caracteres); se logo depois do número (até 40 caracteres)
    vier uma expressão de atribuição ("classificados como", "classified as", ...), a primeira classe depois dele; sem
    classe antes, a primeira depois (até DIST_MAX)."""
    depois = sorted((p, c) for p, c in mencoes if m.end() <= p <= m.end() + DIST_MAX)
    if depois and ATRIB.search(fl[m.end(): m.end() + 40]):
        return depois[0][1]
    antes = sorted((p, c) for p, c in mencoes if m.start() - DIST_MAX <= p < m.start())
    if antes:
        return antes[-1][1]
    return depois[0][1] if depois else None


def ligacoes(texto, campos, classes):
    from checagem_semantica import frases
    pr = props(campos)
    if not pr:
        return [], []
    conferidas, erradas = [], []
    for f in frases(texto):
        fl = f.lower()
        mencoes = [(m.start(), c) for c in classes for m in re.finditer(re.escape(c), fl)]
        for tipo, rx in (("pct", PCT), ("n", CNT)):
            for m in rx.finditer(fl):
                v = m.group(1)
                valores = {c: (str(pct) if tipo == "pct" else str(n)) for c, (n, pct) in pr.items()}
                if not any(bate(v, x) for x in valores.values()):
                    continue
                c = classe_ligada(fl, m, mencoes)
                if c is None:
                    continue
                if c not in valores:
                    continue
                conferidas.append((c, v))
                if not bate(v, valores[c]):
                    erradas.append({"frase": f, "classe": c, "numero": v + ("%" if tipo == "pct" else " patches")})
    return conferidas, erradas


def casos():
    import secoes_por_codigo as spc
    from prostata_r0 import SAIDA_SECOES, casos_secoes_r0
    c = {k: (spc.SAIDA, v) for k, v in spc.casos().items() if k[0] == "pulmao"}
    c.update({k: (SAIDA_SECOES, v) for k, v in casos_secoes_r0().items()})
    return c


def main():
    import avisos_por_codigo as apc
    import secoes_por_codigo as spc
    SAIDA.mkdir(parents=True, exist_ok=True)
    res, ex = {}, {}
    for (orgao, lg), (pasta, docs) in casos().items():
        classes = [c.lower() for c in apc.LINGUA[lg]["classes"][orgao]]
        for p in ("template", "gemma", "llama"):
            nc = ne = npar = 0
            for k, sug, base, campos in docs:
                texto = spc.resumo_template(campos, lg) if p == "template" else \
                    (pasta / p / lg / orgao / f"{k}_paragrafo.txt").read_text(encoding="utf-8")
                conf, err = ligacoes(texto, campos, classes)
                nc, ne, npar = nc + len(conf), ne + len(err), npar + bool(err)
                e = ex.setdefault(f"{p}_{orgao}_{lg}", [])
                for x in err:
                    if len(e) < 3:
                        e.append({"id": k[:12], **x})
            res[f"{p}_{orgao}_{lg}"] = {"n": len(docs), "afirmacoes_conferidas": nc, "ligacoes_erradas": ne,
                                        "paragrafos_com_ligacao_errada": npar}
    res["criterio_V2"] = all(v["ligacoes_erradas"] == 0 for k, v in res.items() if k.startswith("template_"))
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "exemplos.json").write_text(json.dumps(ex, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in res.items():
        print(k, v)
    print(f"V2 {'SIM' if res['criterio_V2'] else 'NÃO'}")


if __name__ == "__main__":
    main()
