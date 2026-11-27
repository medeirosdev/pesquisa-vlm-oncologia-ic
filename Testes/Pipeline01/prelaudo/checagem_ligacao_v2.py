"""
Checagem de ligação número ↔ classe, versão 2 (PÓS-HOC).

Antes (checagem_ligacao.py, commit 8f83770): a regra por proximidade passou no template (V2), mas numa amostra de 40
das 332 ligações marcadas como erradas nos parágrafos (sorteio com semente 0) só 1 era erro real; as outras 39 eram
falsos positivos da regra (classe depois do número, "respectively", flexões). Esta versão foi desenhada DEPOIS de ver
essa amostra e é registrada como análise pós-hoc.

Fixado ANTES de rodar esta versão (commit anterior aos resultados):
  Textos e campos: os mesmos de checagem_ligacao.py (semente 0; pulmão da configuração final, próstata do modelo r0).
  Ligação só por padrões em que número e classe estão colados, sem outro número nem outra classe entre eles
  (intervalo sem dígitos, no máximo 30 caracteres):
     A: "<classe> ... <N> patches (<P>%)" ou "<classe> ... <P>%", com o número logo depois da classe;
     B: "<N> patches (<P>%) <atribuição> <classe>" ou "<P>% <atribuição> <classe>", com atribuição em
        {classificad*, classified, identificad*, identified, rotulad*, labeled, como, as, de, of, são, are, is, é};
     Frases com "respectivamente"/"respectively" são puladas. Se A e B dão classes diferentes, a afirmação é pulada.
  Ligação errada: o número existe nos campos para alguma classe (na precisão escrita) e não é o valor da classe ligada.
  Critério V2b (validade mínima): 0 ligações erradas no resumo do template nos 4 casos.
  Precisão: sorteio (semente 1) de até 40 ligações marcadas como erradas nos parágrafos dos modelos, lidas uma a uma e
     classificadas como erro real ou falso positivo da regra (leitura feita na sessão de análise, não por anotadores
     independentes); reportada a fração de erro real.
  Limites: pós-hoc; cobre só proporções e contagens por classe; não substitui leitura humana.

Uso (venv do projeto): .venv/bin/python prelaudo/checagem_ligacao_v2.py [--amostra]
Saída: resultados/checagem_ligacao/{resumo_v2.json, amostra_v2.txt}
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

from checagem_ligacao import SAIDA, bate, casos, props  # noqa: E402

NUM = re.compile(r"(\d+)\s+patch(?:es)?\s*\((\d+(?:[.,]\d+)?)\s*%\)|(\d+(?:[.,]\d+)?)\s*%")
ATRIB = re.compile(r"^\W*(?:patches\s+)?(?:\w+\s+){0,2}?(classificad\w*|classified|identificad\w*|identified|rotulad\w*|"
                   r"labeled|como|as|de|of|são|are|is|é)\b", re.I)
RESP = re.compile(r"respectivamente|respectively")
GAP = 30


def ligacoes_v2(texto, campos, classes):
    from checagem_semantica import frases
    pr = props(campos)
    if not pr:
        return [], []
    conferidas, erradas = [], []
    for f in frases(texto):
        fl = f.lower()
        if RESP.search(fl):
            continue
        mencoes = sorted((m.start(), m.end(), c) for c in classes for m in re.finditer(re.escape(c), fl))
        for m in NUM.finditer(fl):
            n, p = (m.group(1), m.group(2)) if m.group(1) else (None, m.group(3))
            cand = set()
            antes = [x for x in mencoes if x[1] <= m.start()]
            if antes:
                ini, fim, c = antes[-1]
                gap = fl[fim:m.start()]
                if len(gap) <= GAP and not re.search(r"\d", gap):
                    cand.add(c)
            depois = [x for x in mencoes if x[0] >= m.end()]
            if depois:
                ini, fim, c = depois[0]
                gap = fl[m.end():ini]
                if len(gap) <= GAP and not re.search(r"\d", gap) and ATRIB.search(gap):
                    cand.add(c)
            if len(cand) != 1:
                continue
            c = cand.pop()
            if c not in pr:
                continue
            for tipo, v in (("n", n), ("pct", p)):
                if v is None:
                    continue
                valores = [str(x[0] if tipo == "n" else x[1]) for x in pr.values()]
                if not any(bate(v, x) for x in valores):
                    continue
                proprio = str(pr[c][0] if tipo == "n" else pr[c][1])
                conferidas.append((c, v))
                if not bate(v, proprio):
                    erradas.append({"frase": f, "classe": c, "numero": v + ("%" if tipo == "pct" else " patches")})
    return conferidas, erradas


def main(amostra):
    import avisos_por_codigo as apc
    import secoes_por_codigo as spc
    res, marcadas = {}, []
    for (orgao, lg), (pasta, docs) in casos().items():
        classes = [c.lower() for c in apc.LINGUA[lg]["classes"][orgao]]
        for p in ("template", "gemma", "llama"):
            nc = ne = npar = 0
            for k, sug, base, campos in docs:
                texto = spc.resumo_template(campos, lg) if p == "template" else \
                    (pasta / p / lg / orgao / f"{k}_paragrafo.txt").read_text(encoding="utf-8")
                conf, err = ligacoes_v2(texto, campos, classes)
                nc, ne, npar = nc + len(conf), ne + len(err), npar + bool(err)
                if p != "template":
                    marcadas += [(f"{p}_{orgao}_{lg}", k[:8], e, props(campos)) for e in err]
            res[f"{p}_{orgao}_{lg}"] = {"n": len(docs), "afirmacoes_conferidas": nc, "ligacoes_erradas": ne,
                                        "paragrafos_com_ligacao_errada": npar}
    res["criterio_V2b"] = all(v["ligacoes_erradas"] == 0 for k, v in res.items() if k.startswith("template_"))
    res["marcadas_nos_modelos"] = len(marcadas)
    (SAIDA / "resumo_v2.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, v in res.items():
        print(k, v)
    print(f"V2b {'SIM' if res['criterio_V2b'] else 'NÃO'}")
    if amostra:
        random.Random(1).shuffle(marcadas)
        linhas = [f"{len(marcadas)} marcações"]
        for i, (caso, k, e, pr) in enumerate(marcadas[:40], 1):
            linhas.append(f"\n#{i} {caso} {k} | marcado: {e['classe']} {e['numero']} | campos: "
                          + "; ".join(f"{c} {n} ({p}%)" for c, (n, p) in pr.items()))
            linhas.append("   " + e["frase"][:400])
        (SAIDA / "amostra_v2.txt").write_text("\n".join(linhas), encoding="utf-8")


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--amostra", action="store_true")
    main(a.parse_args().amostra)
