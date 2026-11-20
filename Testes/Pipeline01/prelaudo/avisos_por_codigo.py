"""
Avisos de discordância colados por código, e o pré-laudo final em inglês (pulmão e próstata).

No teste anterior (aviso_discordancia.py), com o AVISO pronto nos campos o texto passou a apontar todas as regiões
discordantes, mas o modelo de linguagem, ao reescrever a seção de avisos, acrescentou avisos em regiões que não
discordam (próstata, 9 de 60 documentos) e trocou a classe da região em 3. Aqui a seção de avisos deixa de ser
redigida pelo modelo: depois que ele escreve, o código apaga o que estiver na seção "## Avisos de discordância"
("## Discordance warnings" em inglês) e cola as linhas de AVISO calculadas a partir dos campos. A checagem passa a
conferir também o par coordenada-classe.

Fixado ANTES de rodar (commit anterior aos resultados):
  Documentos: os mesmos 78 de pulmão (TCGA) e 60 de próstata (PANDA) de aviso_discordancia.py, com os mesmos campos,
     classe sugerida e regra de discordância (aviso_discordancia.discordantes).
  Colagem: a primeira seção de avisos do texto tem o conteúdo trocado pelas linhas calculadas (ou pela frase "Nenhum
     aviso." / "No warnings."); seções de avisos repetidas são apagadas; se o modelo não escreveu a seção, ela é
     inserida antes de "## Regiões para revisão prioritária" / "## Regions for priority review" (ou, se essa também
     faltar, antes da seção seguinte à impressão diagnóstica, ou no fim). O resto do texto não muda.
  Etapa portugues (item 1, sem chamar o modelo): a colagem é aplicada aos textos já escritos em
     resultados/aviso_discordancia. A classe extraída é a do registro anterior (a impressão não muda).
  Etapas campos_en, redigir_en (item 2): os campos são traduzidos para o inglês por substituição fixa de frases
     (nenhum número muda; a tradução falha se sobrar português) e ganham a seção de avisos em inglês. Instruções: as
     de aviso_discordancia.py traduzidas (INSTRUCOES_EN abaixo). Mesmo modelo (Gemma 3 4B) e opções (temperatura
     0,2, semente 0). Classe extraída por uma segunda chamada em JSON restrito, em inglês. O texto bruto do modelo é
     guardado (<id>_modelo.md) e o final, com a colagem, em <id>.md.
  Medidas (texto inteiro, depois da colagem):
     - números sem sustentação e coordenadas inventadas (prelaudo_campos.checar_texto);
     - classe trocada: linha com exatamente uma coordenada dos campos e com pelo menos um nome de classe, em que a
       classe da região nos campos não está entre os nomes da linha;
     - aviso em região concordante: a medida "aponta" de aviso_discordancia.py (expressão de discordância na linha
       da coordenada ou na seguinte) aplicada às regiões que não discordam; em inglês, expressões: discord,
       disagree, contradict, inconsisten, differ, warning, caution, alert, however, although, despite, whereas,
       conflict; linhas de título ("## ...") não contam, porque o próprio título da seção tem "discord"/"aviso";
     - regiões discordantes presentes na seção de avisos.
  Critérios, em cada órgão:
     K1 (português colado): 0 classe trocada, 0 aviso em região concordante, todas as regiões discordantes na seção,
        0 números sem sustentação e 0 coordenadas inventadas.
     K2 (inglês colado): classe extraída = sugerida em >= 90% dos textos, e as mesmas condições de K1.
  Também reportado (sem critério): as mesmas medidas no texto bruto do modelo em inglês (antes da colagem); em
     quantos textos o modelo escreveu a seção; tempo por texto.
  Limites conhecidos: as medidas são por expressões e nomes de classe, não por leitura; a checagem de classe só vê
     linhas com uma coordenada; a tradução dos campos é fixa e foi conferida só por ausência de português.

Uso (venv do projeto; redigir_en precisa do Ollama no ar):
    .venv/bin/python prelaudo/avisos_por_codigo.py --etapa portugues
    .venv/bin/python prelaudo/avisos_por_codigo.py --etapa campos_en
    .venv/bin/python prelaudo/avisos_por_codigo.py --etapa redigir_en
    .venv/bin/python prelaudo/avisos_por_codigo.py --etapa checar_en
Saída: resultados/avisos_por_codigo/{pt,en}/{pulmao,prostata}/ e resultados/avisos_por_codigo/resumo_{pt,en}.json
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

from comum.lamina import RESULTADOS_DIR  # noqa: E402

from aviso_discordancia import (EXPRESSOES, ORIGEM, REGIAO, SAIDA as SAIDA_AVISO,  # noqa: E402
                                apontadas, discordantes, documentos, linha_aviso)

SAIDA = RESULTADOS_DIR / "avisos_por_codigo"
CONCORDA_MIN = 0.90
COORD = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]")

LINGUA = {
    "pt": {"secao": "## Avisos de discordância", "proxima": "## Regiões para revisão prioritária",
           "impressao": "## Impressão diagnóstica sugerida", "nenhum": "Nenhum aviso.", "expressoes": EXPRESSOES,
           "classes": {"pulmao": ("adenocarcinoma", "carcinoma escamoso", "pulmão normal"),
                       "prostata": ("benigno", "gleason 3", "gleason 4", "gleason 5")}},
    "en": {"secao": "## Discordance warnings", "proxima": "## Regions for priority review",
           "impressao": "## Suggested diagnostic impression", "nenhum": "No warnings.",
           "expressoes": ("discord", "disagree", "contradict", "inconsisten", "differ", "warning", "caution", "alert",
                          "however", "although", "despite", "whereas", "conflict"),
           "classes": {"pulmao": ("adenocarcinoma", "squamous cell carcinoma", "normal lung"),
                       "prostata": ("benign", "gleason 3", "gleason 4", "gleason 5")}},
}
CLASSE_EN = {"adenocarcinoma": "adenocarcinoma", "carcinoma escamoso": "squamous cell carcinoma",
             "pulmão normal": "normal lung", "benigno": "benign",
             "Gleason 3": "Gleason 3", "Gleason 4": "Gleason 4", "Gleason 5": "Gleason 5"}
TRADUCAO = [
    ("=== Campos para o pré-laudo ===", "=== Fields for the draft report ==="),
    ("Lâmina: ", "Slide: "), ("Biópsia: ", "Biopsy: "),
    ("Tipo sugerido pelo classificador da lâmina: ", "Type suggested by the slide classifier: "),
    ("Grau ISUP sugerido pelo classificador da biópsia: ", "ISUP grade suggested by the biopsy classifier: "),
    (" (sem câncer)", " (no cancer)"),
    ("Probabilidades do classificador: ", "Classifier probabilities: "),
    ("Confiança: alta", "Confidence: high"), ("Confiança: moderada", "Confidence: moderate"),
    ("Confiança: baixa", "Confidence: low"),
    ("(probabilidade do tipo sugerido ", "(probability of the suggested type "),
    ("(probabilidade do grau sugerido ", "(probability of the suggested grade "),
    ("Proporção entre os ", "Proportion among the "),
    (" patches de tecido sorteados da lâmina (classe de cada patch pelo descritor):",
     " tissue patches sampled from the slide (class of each patch by the descriptor):"),
    (" patches de tecido da biópsia (classe de cada patch pelo descritor):",
     " tissue patches of the biopsy (class of each patch by the descriptor):"),
    ("Regiões que mais pesaram na decisão do classificador (classe de cada patch pelo descritor):",
     "Regions that weighed most in the classifier decision (class of each patch by the descriptor):"),
    ("carcinoma escamoso", "squamous cell carcinoma"), ("pulmão normal", "normal lung"), ("benigno", "benign"),
]

_INSTR_EN = """You write a DRAFT histopathology pre-report of {objeto}, to be reviewed by a pathologist.

{decidido} You do NOT decide or change the {alvo}: your role is to write a clear text that is faithful to the fields received:
- {alvo} suggested by the classifier, with the probabilities of the {n} {alvos} and the confidence level;
- proportion of each class among the tissue patches (each patch is a 128 µm square), according to a descriptor trained on {outro}{classes};
- regions that weighed most in the decision: [x,y] coordinates of patches, with the class and the probability given by the descriptor.

Rules:
1. Use only the numbers and coordinates provided, without rounding them differently and without inventing others.
2. Do not describe morphological findings that are not in the fields.
3. The diagnostic impression must be the suggested {alvo}, with the confidence level given.
4. If the confidence is low or the proportions are mixed, say so.
5. The fields include a section of discordance warnings, computed automatically. Reproduce each WARNING in the section "## Discordance warnings", with the region coordinate and the class given by the descriptor, without minimizing, without justifying and without using the region as an argument in favor of the suggested {alvo}. If the fields say there are no warnings, write only "No warnings." in that section.
6. Write in English, objectively.

Answer in this structure:
## Summary of evidence
## Suggested diagnostic impression
## Discordance warnings
## Regions for priority review
## Limitations
(state that the text was generated automatically and needs confirmation by a pathologist)"""
INSTRUCOES_EN = {
    "pulmao": _INSTR_EN.format(
        objeto="a lung slide (non-small cell lung carcinoma)", alvo="type", alvos="types", n=2,
        decidido="The histological type HAS ALREADY BEEN DECIDED by an automatic whole-slide classifier, between "
                 "adenocarcinoma and squamous cell carcinoma.",
        outro="another image set", classes=""),
    "prostata": _INSTR_EN.format(
        objeto="a prostate biopsy", alvo="grade", alvos="grades", n=6,
        decidido="The ISUP grade (0 = no cancer; 1 to 5 = carcinoma grade groups) HAS ALREADY BEEN DECIDED by an "
                 "automatic classifier of the whole biopsy.",
        outro="another center", classes=": benign, Gleason pattern 3, 4 or 5"),
}


def linha_aviso_en(orgao, sugerido, coord, classe, prob):
    if orgao == "pulmao":
        alvo, valor = "type", CLASSE_EN[sugerido]
    else:
        alvo, valor = "grade", f"ISUP {sugerido}" + (", no cancer" if sugerido == 0 else "")
    return (f"WARNING: region {coord} was described by the descriptor as {CLASSE_EN[classe]} ({prob}), which disagrees "
            f"with the suggested {alvo} ({valor}). This region should be reviewed before accepting the suggested {alvo}.")


def linhas_aviso(orgao, lingua, sugerido, campos):
    d = discordantes(orgao, sugerido, campos)
    if lingua == "pt":
        return [linha_aviso(orgao, sugerido, *r).strip() for r in d]
    return [linha_aviso_en(orgao, sugerido, *r) for r in d]


def colar(texto, linhas, lingua):
    """Troca o conteúdo da seção de avisos pelas linhas calculadas. Devolve (texto, o modelo escreveu a seção)."""
    L = LINGUA[lingua]
    bloco = f"{L['secao']}\n" + ("\n".join(linhas) if linhas else L["nenhum"]) + "\n\n"
    secao = re.compile(rf"^{re.escape(L['secao'])}[^\n]*\n?.*?(?=^## |\Z)", re.M | re.S)
    achadas = list(secao.finditer(texto))
    if achadas:
        partes, ini = [], 0
        for i, m in enumerate(achadas):
            partes.append(texto[ini:m.start()])
            if i == 0:
                partes.append(bloco)
            ini = m.end()
        partes.append(texto[ini:])
        return "".join(partes), True
    m = re.search(rf"^{re.escape(L['proxima'])}", texto, re.M)
    if m is None:
        imp = re.search(rf"^{re.escape(L['impressao'])}", texto, re.M)
        m = re.search(r"^## ", texto[imp.end():], re.M) if imp else None
        if m is not None:
            pos = imp.end() + m.start()
            return texto[:pos] + bloco + texto[pos:], False
        return texto.rstrip() + "\n\n" + bloco, False
    return texto[:m.start()] + bloco + texto[m.start():], False


def medir(orgao, lingua, sugerido, campos_pt, texto, evidencia):
    from prelaudo_campos import checar_texto
    L = LINGUA[lingua]
    traduz = (lambda c: c) if lingua == "pt" else (lambda c: CLASSE_EN[c])
    cls = {f"[{x},{y}]": traduz(c).lower() for x, y, c, _ in REGIAO.findall(campos_pt)}
    disc = [c for c, _, _ in discordantes(orgao, sugerido, campos_pt)]
    conc = [c for c in cls if c not in disc]
    linhas = [COORD.sub(r"[\1,\2]", l).lower() for l in texto.splitlines()]
    trocada = 0
    for l in linhas:
        cs = [c for c in cls if c in l]
        ditas = [n for n in L["classes"][orgao] if n in l]
        if len(cs) == 1 and ditas and cls[cs[0]] not in ditas:
            trocada += 1
    m = re.search(rf"^{re.escape(L['secao'])}[^\n]*\n?(.*?)(?=^## |\Z)", texto, re.M | re.S)
    secao = COORD.sub(r"[\1,\2]", m.group(1)) if m else ""
    import aviso_discordancia
    antigas = aviso_discordancia.EXPRESSOES
    aviso_discordancia.EXPRESSOES = L["expressoes"]
    try:
        sem_titulos = "\n".join("" if l.lstrip().startswith("#") else l for l in texto.splitlines())
        falsos = len(apontadas(sem_titulos, conc))
    finally:
        aviso_discordancia.EXPRESSOES = antigas
    ch = checar_texto(texto, evidencia)
    return {"classe_trocada": trocada, "aviso_em_regiao_concordante": falsos,
            "regioes_discordantes": len(disc), "discordantes_na_secao": sum(c in secao for c in disc),
            "nao_sustentados": len(ch["nao_sustentados"]), "coordenadas_inventadas": len(ch["coordenadas_inventadas"]),
            "numeros_checados": ch["numeros_checados"], "coordenadas": ch["coordenadas"]}


def somar(medidas):
    chaves = ["classe_trocada", "aviso_em_regiao_concordante", "regioes_discordantes", "discordantes_na_secao",
              "nao_sustentados", "coordenadas_inventadas", "numeros_checados", "coordenadas"]
    r = {k: sum(m[k] for m in medidas.values()) for k in chaves}
    r["documentos_com_classe_trocada"] = sum(m["classe_trocada"] > 0 for m in medidas.values())
    r["documentos_com_aviso_em_regiao_concordante"] = sum(m["aviso_em_regiao_concordante"] > 0 for m in medidas.values())
    return r


def condicoes(t):
    return (t["classe_trocada"] == 0 and t["aviso_em_regiao_concordante"] == 0
            and t["discordantes_na_secao"] == t["regioes_discordantes"]
            and t["nao_sustentados"] == 0 and t["coordenadas_inventadas"] == 0)


def etapa_portugues():
    resumo = {}
    for orgao in ORIGEM:
        pasta = SAIDA / "pt" / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        reg = json.loads((SAIDA_AVISO / orgao / "registro.json").read_text(encoding="utf-8"))
        med, med_antes, escreveu = {}, {}, 0
        for k, sug, campos in documentos(orgao):
            evid = (SAIDA_AVISO / orgao / f"{k}_campos.txt").read_text(encoding="utf-8")
            bruto = (SAIDA_AVISO / orgao / f"{k}.md").read_text(encoding="utf-8")
            final, tinha = colar(bruto, linhas_aviso(orgao, "pt", sug, campos), "pt")
            escreveu += tinha
            (pasta / f"{k}.md").write_text(final, encoding="utf-8")
            med[k] = medir(orgao, "pt", sug, campos, final, evid)
            med_antes[k] = medir(orgao, "pt", sug, campos, bruto, evid)
        concorda = sum(v["extraido"] == v["sugerido"] for v in reg.values())
        t = somar(med)
        resumo[orgao] = {"n": len(med), "classe_extraida_igual_sugerida_registro_anterior": f"{concorda}/{len(reg)}",
                         "colado": t, "texto_do_modelo_antes_da_colagem": somar(med_antes),
                         "modelo_escreveu_a_secao": f"{escreveu}/{len(med)}", "criterio_K1": condicoes(t),
                         "por_documento": med}
    (SAIDA / "resumo_pt.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for o, r in resumo.items():
        print(o, json.dumps({k: v for k, v in r.items() if k != "por_documento"}, indent=1, ensure_ascii=False))
        print(f"{o}: K1 {'SIM' if r['criterio_K1'] else 'NÃO'}")


def campos_en(orgao, sugerido, campos_pt):
    en = campos_pt
    for a, b in TRADUCAO:
        en = en.replace(a, b)
    assert not re.search(r"[ãçéêíóõúâà]|\b(de|da|do|dos|das|entre|pelo|sorteados)\b", en), en
    linhas = linhas_aviso(orgao, "en", sugerido, campos_pt)
    extra = (["Discordance warnings (computed automatically from the fields above):"] + [f"  {l}" for l in linhas]
             if linhas else ["Discordance warnings: none."])
    return en + "\n" + "\n".join(extra)


def etapa_campos_en():
    for orgao in ORIGEM:
        pasta = SAIDA / "en" / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        for k, sug, campos in documentos(orgao):
            (pasta / f"{k}_campos.txt").write_text(campos_en(orgao, sug, campos), encoding="utf-8")
        print(f"{orgao}: {len(documentos(orgao))} campos em inglês em {pasta}")


def extrair_en(orgao, texto):
    import sintese
    from tcga_descritor_prelaudo import MODELO
    if orgao == "pulmao":
        chave, opcoes = "type", ["adenocarcinoma", "squamous cell carcinoma"]
        pergunta = "Below is a lung histopathology draft report. What final histological type does it suggest?"
    else:
        chave, opcoes = "isup", list("012345")
        pergunta = "Below is a prostate biopsy draft report. What final ISUP grade (0 to 5) does it suggest?"
    formato = {"type": "object", "properties": {chave: {"type": "string", "enum": opcoes}}, "required": [chave]}
    corpo = {"model": MODELO, "stream": False, "format": formato, "options": sintese.OPCOES,
             "messages": [{"role": "user", "content": pergunta + " Answer only with the JSON.\n\n" + texto}]}
    req = urllib.request.Request(sintese.OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        v = json.loads(json.loads(r.read())["message"]["content"])[chave]
    return {"adenocarcinoma": "adenocarcinoma", "squamous cell carcinoma": "carcinoma escamoso"}[v] if orgao == "pulmao" else int(v)


def etapa_redigir_en():
    import sintese
    from tcga_descritor_prelaudo import MODELO
    for orgao in ORIGEM:
        pasta = SAIDA / "en" / orgao
        registro = pasta / "registro.json"
        feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
        for k, sug, campos_pt in documentos(orgao):
            if k in feito:
                continue
            campos = (pasta / f"{k}_campos.txt").read_text(encoding="utf-8")
            t0 = time.time()
            bruto = sintese.chamar(MODELO, campos, [], instrucoes=INSTRUCOES_EN[orgao], lembrete="")["message"]["content"]
            (pasta / f"{k}_modelo.md").write_text(bruto, encoding="utf-8")
            final, tinha = colar(bruto, linhas_aviso(orgao, "en", sug, campos_pt), "en")
            (pasta / f"{k}.md").write_text(final, encoding="utf-8")
            feito[k] = {"sugerido": sug, "extraido": extrair_en(orgao, final), "modelo_escreveu_a_secao": tinha,
                        "segundos": round(time.time() - t0, 1)}
            registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {orgao} {k[:12]}: sugerido {sug} | extraído {feito[k]['extraido']} ({feito[k]['segundos']} s)", flush=True)


def etapa_checar_en():
    resumo = {}
    for orgao in ORIGEM:
        pasta = SAIDA / "en" / orgao
        feito = json.loads((pasta / "registro.json").read_text(encoding="utf-8"))
        med, med_bruto = {}, {}
        for k, sug, campos_pt in documentos(orgao):
            evid = (pasta / f"{k}_campos.txt").read_text(encoding="utf-8")
            med[k] = medir(orgao, "en", sug, campos_pt, (pasta / f"{k}.md").read_text(encoding="utf-8"), evid)
            med_bruto[k] = medir(orgao, "en", sug, campos_pt, (pasta / f"{k}_modelo.md").read_text(encoding="utf-8"), evid)
        concorda = sum(v["extraido"] == v["sugerido"] for v in feito.values())
        t = somar(med)
        resumo[orgao] = {"n": len(feito), "classe_extraida_igual_sugerida": f"{concorda}/{len(feito)}",
                         "colado": t, "texto_do_modelo_antes_da_colagem": somar(med_bruto),
                         "modelo_escreveu_a_secao": f"{sum(v['modelo_escreveu_a_secao'] for v in feito.values())}/{len(feito)}",
                         "segundos_medio": round(sum(v["segundos"] for v in feito.values()) / len(feito), 1),
                         "criterio_K2": concorda / len(feito) >= CONCORDA_MIN and condicoes(t),
                         "por_documento": {k: {**med[k], **feito[k]} for k in med}}
    (SAIDA / "resumo_en.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for o, r in resumo.items():
        print(o, json.dumps({k: v for k, v in r.items() if k != "por_documento"}, indent=1, ensure_ascii=False))
        print(f"{o}: K2 {'SIM' if r['criterio_K2'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["portugues", "campos_en", "redigir_en", "checar_en"], required=True)
    {"portugues": etapa_portugues, "campos_en": etapa_campos_en, "redigir_en": etapa_redigir_en,
     "checar_en": etapa_checar_en}[p.parse_args().etapa]()
