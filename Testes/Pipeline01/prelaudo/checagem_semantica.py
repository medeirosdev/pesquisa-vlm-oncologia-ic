"""
Checagem semântica do parágrafo escrito pelo modelo de linguagem (revisão 02, item C).

Antes (secoes_por_codigo.py): a checagem confere se números e coordenadas existem nos campos, mas não o que o texto
afirma sobre eles. O exemplo principal do paper (TCGA-55-6987, Gemma, português) diz "predominância de adenocarcinoma,
226 patches (32.7%)" quando o pulmão normal tem 66,7%, e a checagem não pega. E a medida de "aviso em região
concordante", feita para a seção de avisos, conta no texto livre frases que negam o aviso ou citam várias regiões juntas.

Fixado ANTES de rodar (commit anterior aos resultados):
  Textos: os parágrafos já gerados (nenhum modelo de linguagem roda aqui) em resultados/secoes_por_codigo/
     {gemma,llama}{,_s1,_s2}/{pt,en}/{pulmao,prostata}/<id>_paragrafo.txt, e o resumo do template (resumo_template) como
     controle. Campos: os mesmos de secoes_por_codigo.casos().
  Frases: o texto é dividido em frases por ponto, exclamação ou interrogação seguidos de espaço e letra maiúscula.
  S1 (predominância): nas frases com expressão de predominância (pt: "predomin", "maioria", "majoritári",
     "principalmente", "maior parte"; en: "predomin", "majority", "mostly", "most of", "main"), a primeira classe
     citada depois da expressão (ou, se nenhuma, a primeira da frase) é a classe afirmada; é contraditória se não for a
     classe de maior proporção nos campos. Conta: frases e parágrafos contraditórios.
  S2 (aviso em região concordante, versão 2): frases com exatamente uma coordenada dos campos, com expressão de
     discordância (as mesmas listas de avisos_por_codigo.LINGUA) e sem negação (pt: "não", "nenhum", "nenhuma", "sem";
     en: "no", "not", "none", "without"); conta se a coordenada é de região concordante.
  Também reportado: a medida antiga (avisos_por_codigo.medir no parágrafo) ao lado; até 3 exemplos marcados por caso e
     medida em exemplos.json, para conferência visual.
  Critério V (validade mínima da checagem): S1 e S2 dão 0 no resumo do template nos 4 casos (órgão × idioma).
  Limites conhecidos: regras por palavras-chave; não substituem leitura humana; S1 só cobre afirmações de predominância.

Uso (venv do projeto): .venv/bin/python prelaudo/checagem_semantica.py
Saída: resultados/checagem_semantica/{resumo.json, exemplos.json}
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "checagem_semantica"
PRED = {"pt": ("predomin", "maioria", "majoritári", "principalmente", "maior parte"),
        "en": ("predomin", "majority", "mostly", "most of", "main")}
NEG = {"pt": r"\b(não|nenhum|nenhuma|sem)\b", "en": r"\b(no|not|none|without)\b"}
PROP = re.compile(r"^\s*-\s*(.+?):\s*\d+ patches \(([\d.]+)%\)", re.M)
FRASES = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý])")


def frases(t):
    return [f for f in FRASES.split(t.strip()) if f.strip()]


def s1(texto, campos, lg, classes):
    props = {c.strip().lower(): float(p) for c, p in PROP.findall(campos)}
    if not props:
        return []
    maior = max(props, key=props.get)
    out = []
    for f in frases(texto):
        fl = f.lower()
        pos = [fl.find(e) for e in PRED[lg] if e in fl]
        if not pos:
            continue
        ini = min(pos)
        citadas = sorted((fl.find(c), c) for c in classes if c in fl)
        if not citadas:
            continue
        depois = [c for p, c in citadas if p >= ini]
        afirmada = depois[0] if depois else citadas[0][1]
        if afirmada != maior:
            out.append(f)
    return out


def s2(texto, campos_pt_base, orgao, sug, lg):
    import avisos_por_codigo as apc
    from aviso_discordancia import discordantes
    disc = {c for c, _, _ in discordantes(orgao, sug, campos_pt_base)}
    regs = {f"[{x},{y}]" for x, y in apc.COORD.findall(campos_pt_base)}
    conc = regs - disc
    out = []
    for f in frases(texto):
        cs = {f"[{x},{y}]" for x, y in apc.COORD.findall(f)} & regs
        fl = f.lower()
        if len(cs) == 1 and any(e in fl for e in apc.LINGUA[lg]["expressoes"]) and not re.search(NEG[lg], fl) \
                and next(iter(cs)) in conc:
            out.append(f)
    return out


def main():
    import avisos_por_codigo as apc
    import secoes_por_codigo as spc
    SAIDA.mkdir(parents=True, exist_ok=True)
    res, ex = {}, {}
    pastas = ["template"] + [p for p in ("gemma", "gemma_s1", "gemma_s2", "llama", "llama_s1", "llama_s2")
                             if (spc.SAIDA / p).exists()]
    for (orgao, lg), docs in spc.casos().items():
        classes = [c.lower() for c in apc.LINGUA[lg]["classes"][orgao]]
        for p in pastas:
            n1 = n1d = n2 = n2d = antigo = 0
            for k, sug, base, campos in docs:
                if p == "template":
                    texto = spc.resumo_template(campos, lg)
                else:
                    texto = (spc.SAIDA / p / lg / orgao / f"{k}_paragrafo.txt").read_text(encoding="utf-8")
                a, b = s1(texto, campos, lg, classes), s2(texto, base, orgao, sug, lg)
                n1, n1d, n2, n2d = n1 + len(a), n1d + bool(a), n2 + len(b), n2d + bool(b)
                if p != "template":
                    antigo += spc.medir_paragrafo(orgao, lg, sug, base, campos, texto)["aviso_em_regiao_concordante"]
                for nome, lst in (("S1", a), ("S2", b)):
                    e = ex.setdefault(f"{p}_{orgao}_{lg}_{nome}", [])
                    if lst and len(e) < 3:
                        e.append({"id": k[:12], "frase": lst[0]})
            res[f"{p}_{orgao}_{lg}"] = {"n": len(docs), "S1_frases": n1, "S1_paragrafos": n1d, "S2_frases": n2,
                                        "S2_paragrafos": n2d, **({"aviso_concordante_antigo": antigo} if p != "template" else {})}
    res["criterio_V"] = all(v["S1_frases"] == 0 and v["S2_frases"] == 0 for k, v in res.items() if k.startswith("template_"))
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "exemplos.json").write_text(json.dumps(ex, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in res.items():
        if k != "criterio_V":
            print(k, v)
    print(f"V {'SIM' if res['criterio_V'] else 'NÃO'}")


if __name__ == "__main__":
    main()
