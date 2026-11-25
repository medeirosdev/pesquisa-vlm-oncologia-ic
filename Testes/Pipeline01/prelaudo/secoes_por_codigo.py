"""
Seções críticas montadas pelo código e a linha de base sem modelo de linguagem.

Antes: com a colagem por título (prelaudo_final.py), os zeros nas seções coladas são garantidos por construção, e com
o Llama 3.2 3B a colagem falhou quando o modelo mudou o formato dos títulos (segundo_modelo.py). A revisão pediu (a) a
linha de base óbvia, um template determinístico sem modelo de linguagem, e (b) medir a fidelidade só no texto que o
modelo escreve livremente.

Fixado ANTES de rodar (commit anterior aos resultados):
  Documentos e campos: os da configuração final (pulmão 78, campos de aviso_discordancia/pulmao e
     avisos_por_codigo/en/pulmao; próstata 60 com o GAT-MIL padronizado, campos de prelaudo_final/prostata/{pt,en}).
  Braço T (template, sem modelo de linguagem): o laudo inteiro é montado pelo código a partir dos campos: resumo
     (frases fixas com a decisão, as probabilidades, a confiança e as proporções), impressão (classe e confiança),
     avisos (linhas calculadas), regiões (linhas dos campos) e limitações (frase fixa).
  Braço M (código monta, modelo resume): o modelo de linguagem recebe os campos e escreve só um parágrafo de resumo da
     evidência, sem títulos; o código monta o laudo: "## Resumo da evidência" + parágrafo do modelo, e as outras quatro
     seções iguais às do braço T. Modelos: Gemma 3 4B e Llama 3.2 3B (mesmas opções: temperatura 0,2, semente 0).
  Medidas, no braço M, só no parágrafo escrito pelo modelo: números sem sustentação e coordenadas inventadas
     (prelaudo_campos.checar_texto contra os campos), classe trocada e aviso em região concordante (avisos_por_codigo.medir
     aplicado ao parágrafo), parágrafo vazio, número de palavras. No laudo inteiro: classe lida por código na impressão
     (extracao_codigo.por_codigo) = sugerida.
  Critério Q, para cada modelo, órgão e idioma (8 casos): no parágrafo livre, 0 números sem sustentação, 0 coordenadas
     inventadas, 0 classes trocadas e 0 avisos em região concordante; e classe lida = sugerida em 100% dos laudos.
  Também reportado (sem critério): o braço T passa por construção (conferido pela mesma checagem); comprimento dos
     textos; os mesmos erros no texto bruto das rodadas anteriores (Gemma: prelaudo_final; Llama: segundo_modelo).
  Limite conhecido: nenhuma avaliação humana de legibilidade; o que o modelo acrescenta ao template só é medido em
     erros e em comprimento.

Uso (venv do projeto; Ollama no ar com gemma3:4b e llama3.2:3b):
    .venv/bin/python prelaudo/secoes_por_codigo.py --etapa template
    .venv/bin/python prelaudo/secoes_por_codigo.py --etapa redigir --modelo gemma3:4b
    .venv/bin/python prelaudo/secoes_por_codigo.py --etapa redigir --modelo llama3.2:3b
    .venv/bin/python prelaudo/secoes_por_codigo.py --etapa checar
Saída: resultados/secoes_por_codigo/
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

import avisos_por_codigo as apc  # noqa: E402
from aviso_discordancia import REGIAO, SAIDA as SAIDA_AVISO, documentos  # noqa: E402
from extracao_codigo import por_codigo  # noqa: E402
from prelaudo_final import SAIDA as SAIDA_FINAL, documentos_prostata, linhas_regioes  # noqa: E402

SAIDA = RESULTADOS_DIR / "secoes_por_codigo"
MODELOS = {"gemma3:4b": "gemma", "llama3.2:3b": "llama"}
TIT = {"pt": ["## Resumo da evidência", "## Impressão diagnóstica sugerida", "## Avisos de discordância",
              "## Regiões para revisão prioritária", "## Limitações"],
       "en": ["## Summary of evidence", "## Suggested diagnostic impression", "## Discordance warnings",
              "## Regions for priority review", "## Limitations"]}
LIMIT = {"pt": "Texto gerado automaticamente a partir dos campos acima; precisa de confirmação por patologista.",
         "en": "Text generated automatically from the fields above; it needs confirmation by a pathologist."}
INSTR = {
    "pt": ("Você recebe os campos de um pré-laudo histopatológico gerados automaticamente. Escreva UM parágrafo curto, em "
           "português, resumindo a evidência dos campos, para um patologista. Use apenas os números, classes e "
           "coordenadas que estão nos campos, sem arredondar de outro jeito e sem calcular números novos. Não decida nem "
           "mude a classe sugerida e não descreva achados que não estejam nos campos. Responda só com o parágrafo, sem "
           "títulos e sem listas."),
    "en": ("You receive the fields of an automatically generated histopathology draft report. Write ONE short paragraph, "
           "in English, summarizing the evidence in the fields, for a pathologist. Use only the numbers, classes and "
           "coordinates that are in the fields, without rounding them differently and without computing new numbers. Do "
           "not decide or change the suggested class and do not describe findings that are not in the fields. Answer "
           "only with the paragraph, without headings and without lists."),
}


def casos():
    """{(orgao, lingua): [(id, sugerido, campos_pt_base, campos_do_prompt)]}."""
    ler = lambda p: p.read_text(encoding="utf-8")  # noqa: E731
    pul, pro = documentos("pulmao"), documentos_prostata()
    return {("pulmao", "pt"): [(k, s, c, ler(SAIDA_AVISO / "pulmao" / f"{k}_campos.txt")) for k, s, c in pul],
            ("pulmao", "en"): [(k, s, c, ler(apc.SAIDA / "en" / "pulmao" / f"{k}_campos.txt")) for k, s, c in pul],
            ("prostata", "pt"): [(k, s, c, ler(SAIDA_FINAL / "prostata" / "pt" / f"{k}_campos.txt")) for k, s, c in pro],
            ("prostata", "en"): [(k, s, c, ler(SAIDA_FINAL / "prostata" / "en" / f"{k}_campos.txt")) for k, s, c in pro]}


def linhas_campos(campos):
    return [l.strip() for l in campos.splitlines() if l.strip() and not l.startswith("===")]


def resumo_template(campos_prompt, lingua):
    """Frases fixas: as linhas dos campos até as regiões (decisão, probabilidades, confiança, proporções)."""
    out = []
    for l in linhas_campos(campos_prompt):
        if l.startswith(("Regiões que mais pesaram", "Regions that weighed most", "Avisos de discordância",
                         "Discordance warnings")):
            break
        out.append(l.lstrip("- "))
    return " ".join(x if x.endswith((".", ":")) else x + ";" for x in out).rstrip(";") + "."


def impressao(orgao, lingua, sugerido, campos_prompt):
    conf = re.search(r"(Confiança|Confidence): ([^\n]+)", campos_prompt).group(0)
    if orgao == "pulmao":
        nome = sugerido if lingua == "pt" else apc.CLASSE_EN[sugerido]
        return f"{nome[0].upper() + nome[1:]}. {conf}."
    return f"ISUP {sugerido}{' (sem câncer)' if lingua == 'pt' and sugerido == 0 else ' (no cancer)' if sugerido == 0 else ''}. {conf}."


def montar(orgao, lingua, sugerido, base, campos_prompt, resumo):
    t = TIT[lingua]
    av = apc.linhas_aviso(orgao, lingua, sugerido, base)
    partes = [t[0], resumo.strip(), "", t[1], impressao(orgao, lingua, sugerido, campos_prompt), "", t[2],
              "\n".join(av) if av else apc.LINGUA[lingua]["nenhum"], "", t[3], "\n".join(linhas_regioes(base, lingua)), "",
              t[4], LIMIT[lingua]]
    return "\n".join(partes) + "\n"


def etapa_template():
    for (orgao, lg), docs in casos().items():
        pasta = SAIDA / "template" / lg / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        for k, sug, base, campos in docs:
            (pasta / f"{k}.md").write_text(montar(orgao, lg, sug, base, campos, resumo_template(campos, lg)), encoding="utf-8")
    print("template pronto")


def etapa_redigir(modelo):
    import sintese
    nome = MODELOS[modelo]
    for (orgao, lg), docs in casos().items():
        pasta = SAIDA / nome / lg / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        reg = pasta / "registro.json"
        feito = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else {}
        for k, sug, base, campos in docs:
            if k in feito:
                continue
            t0 = time.time()
            par = sintese.chamar(modelo, campos, [], instrucoes=INSTR[lg], lembrete="")["message"]["content"].strip()
            (pasta / f"{k}_paragrafo.txt").write_text(par, encoding="utf-8")
            (pasta / f"{k}.md").write_text(montar(orgao, lg, sug, base, campos, par), encoding="utf-8")
            feito[k] = {"sugerido": sug, "segundos": round(time.time() - t0, 1)}
            reg.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {nome} {orgao} {lg} {k[:12]} ({feito[k]['segundos']} s)", flush=True)


def medir_paragrafo(orgao, lg, sug, base, campos, par):
    from prelaudo_campos import checar_texto
    m = apc.medir(orgao, lg, sug, base, par, campos)
    ch = checar_texto(par, campos)
    return {"nao_sustentados": len(ch["nao_sustentados"]), "numeros_nao_sustentados": ch["nao_sustentados"][:5],
            "coordenadas_inventadas": len(ch["coordenadas_inventadas"]), "numeros_checados": ch["numeros_checados"],
            "classe_trocada": m["classe_trocada"], "aviso_em_regiao_concordante": m["aviso_em_regiao_concordante"],
            "vazio": not par.strip(), "palavras": len(par.split())}


def etapa_checar():
    resumo = {}
    for (orgao, lg), docs in casos().items():
        # template: laudo inteiro checado
        pt = SAIDA / "template" / lg / orgao
        tm = [apc.medir(orgao, lg, s, b, (pt / f"{k}.md").read_text(encoding="utf-8"), c) for k, s, b, c in docs]
        tcl = sum(por_codigo(orgao, lg, (pt / f"{k}.md").read_text(encoding="utf-8")) == s for k, s, b, c in docs)
        resumo[f"template_{orgao}_{lg}"] = {"n": len(docs), "classe_lida_igual": f"{tcl}/{len(docs)}",
                                            **apc.somar(dict(enumerate(tm))),
                                            "palavras_resumo_medio": round(float(np.mean([len(resumo_template(c, lg).split()) for _, _, _, c in docs])), 1)}
        for nome in MODELOS.values():
            pasta = SAIDA / nome / lg / orgao
            if not (pasta / "registro.json").exists():
                continue
            med, cl = {}, 0
            for k, s, b, c in docs:
                par = (pasta / f"{k}_paragrafo.txt").read_text(encoding="utf-8")
                med[k] = medir_paragrafo(orgao, lg, s, b, c, par)
                cl += por_codigo(orgao, lg, (pasta / f"{k}.md").read_text(encoding="utf-8")) == s
            n = len(docs)
            soma = {x: sum(v[x] for v in med.values()) for x in ("nao_sustentados", "coordenadas_inventadas", "classe_trocada",
                                                                  "aviso_em_regiao_concordante", "vazio", "numeros_checados")}
            r = {"n": n, **soma, "documentos_com_numero_nao_sustentado": sum(v["nao_sustentados"] > 0 for v in med.values()),
                 "palavras_medio": round(float(np.mean([v["palavras"] for v in med.values()])), 1),
                 "classe_lida_igual": f"{cl}/{n}",
                 "exemplos_numeros": sorted({x for v in med.values() for x in v["numeros_nao_sustentados"]})[:10]}
            r["criterio_Q"] = (soma["nao_sustentados"] == 0 and soma["coordenadas_inventadas"] == 0 and soma["classe_trocada"] == 0
                               and soma["aviso_em_regiao_concordante"] == 0 and cl == n)
            resumo[f"{nome}_{orgao}_{lg}"] = r
            print(f"{nome} {orgao} {lg}: {r} | Q {'SIM' if r['criterio_Q'] else 'NÃO'}", flush=True)
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["template", "redigir", "checar"], required=True)
    p.add_argument("--modelo", choices=list(MODELOS), default="gemma3:4b")
    a = p.parse_args()
    {"template": etapa_template, "redigir": lambda: etapa_redigir(a.modelo), "checar": etapa_checar}[a.etapa]()
