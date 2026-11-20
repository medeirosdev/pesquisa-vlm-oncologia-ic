"""
Classe do pré-laudo extraída por código, antes de perguntar ao modelo de linguagem.

Nos pré-laudos finais da próstata em inglês (prelaudo_final.py), a classe extraída por uma segunda chamada ao modelo
(JSON restrito) diferiu da sugerida em 4 de 60 textos, e nos 4 a impressão escrita era a sugerida: o erro era da
extração. Aqui a classe sai do texto por regra fixa e o modelo só é usado quando a regra não acha nada.

Fixado ANTES de rodar (commit anterior aos resultados):
  Textos: os pré-laudos finais (avisos e regiões colados), sem gerar nada de novo: pulmão
     resultados/prelaudo_final/{pt,en}/pulmao/<id>.md (78 + 78); próstata resultados/prelaudo_final/prostata/{pt,en}/
     <id>.md (60 + 60).
  Regra: a primeira linha não vazia da seção de impressão ("## Impressão diagnóstica sugerida" / "## Suggested
     diagnostic impression"). Pulmão: o nome de classe que aparece primeiro nessa linha (adenocarcinoma: "adenocarcinoma";
     carcinoma escamoso: "escamos" ou "epiderm" em português, "squamous" em inglês; sem diferenciar maiúsculas).
     Próstata: o primeiro "ISUP" seguido de um dígito de 0 a 5 (aceitando "grau"/"grade" no meio). Se a seção não
     existir ou nada for achado, vale a classe que o modelo extraiu antes (registros das rodadas anteriores, nenhuma
     chamada nova).
  Critério C, em cada órgão e idioma: classe extraída (código primeiro) = sugerida em >= 90% dos textos.
  Também reportado (sem critério): quantos textos a regra resolveu sozinha; em quantos a regra e o modelo discordam, e
     qual dos dois bate com a sugerida.
  Limite conhecido: a regra lê só a primeira linha da impressão; uma impressão que comece por outra classe (por
     exemplo, citando o diagnóstico diferencial antes) seria lida errado.

Uso (venv do projeto; não precisa do Ollama):
    .venv/bin/python prelaudo/extracao_codigo.py
Saída: resultados/prelaudo_final/extracao_codigo.json
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "prelaudo_final"
CONCORDA_MIN = 0.90
IMPRESSAO = {"pt": "## Impressão diagnóstica sugerida", "en": "## Suggested diagnostic impression"}
PULMAO = {"pt": {"adenocarcinoma": r"adenocarcinoma", "carcinoma escamoso": r"escamos|epiderm"},
          "en": {"adenocarcinoma": r"adenocarcinoma", "carcinoma escamoso": r"squamous"}}
ISUP = re.compile(r"ISUP\s*(?:grau|grade)?\s*([0-5])", re.I)


def primeira_linha_impressao(texto, lingua):
    m = re.search(rf"^{re.escape(IMPRESSAO[lingua])}[^\n]*\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    if m is None:
        return None
    for l in m.group(1).splitlines():
        if l.strip():
            return l
    return None


def por_codigo(orgao, lingua, texto):
    l = primeira_linha_impressao(texto, lingua)
    if l is None:
        return None
    if orgao == "prostata":
        m = ISUP.search(l)
        return int(m.group(1)) if m else None
    achados = [(m.start(), c) for c, pad in PULMAO[lingua].items() for m in [re.search(pad, l, re.I)] if m]
    return min(achados)[1] if achados else None


def registros():
    """{(orgao, lingua): (pasta dos textos, {id: {sugerido, extraido}})}; extraído = o do modelo, rodadas anteriores."""
    return {
        ("pulmao", "pt"): (SAIDA / "pt" / "pulmao", RESULTADOS_DIR / "aviso_discordancia" / "pulmao" / "registro.json"),
        ("pulmao", "en"): (SAIDA / "en" / "pulmao", RESULTADOS_DIR / "avisos_por_codigo" / "en" / "pulmao" / "registro.json"),
        ("prostata", "pt"): (SAIDA / "prostata" / "pt", SAIDA / "prostata" / "pt" / "registro.json"),
        ("prostata", "en"): (SAIDA / "prostata" / "en", SAIDA / "prostata" / "en" / "registro.json"),
    }


def main():
    resumo = {}
    for (orgao, lingua), (pasta, arq) in registros().items():
        reg = json.loads(arq.read_text(encoding="utf-8"))
        por_doc, resolvidos, iguais, discord = {}, 0, 0, []
        for k, v in reg.items():
            cod = por_codigo(orgao, lingua, (pasta / f"{k}.md").read_text(encoding="utf-8"))
            final = cod if cod is not None else v["extraido"]
            resolvidos += cod is not None
            iguais += final == v["sugerido"]
            if cod is not None and cod != v["extraido"]:
                discord.append({"id": k, "sugerido": v["sugerido"], "codigo": cod, "modelo": v["extraido"]})
            por_doc[k] = {"sugerido": v["sugerido"], "codigo": cod, "modelo": v["extraido"], "final": final}
        n = len(reg)
        modelo_igual = sum(v["extraido"] == v["sugerido"] for v in reg.values())
        r = {"n": n, "resolvidos_pela_regra": f"{resolvidos}/{n}", "classe_final_igual_sugerida": f"{iguais}/{n}",
             "antes_so_modelo_igual_sugerida": f"{modelo_igual}/{n}",
             "regra_e_modelo_discordam": len(discord),
             "discordancias_regra_certa": sum(d["codigo"] == d["sugerido"] for d in discord),
             "discordancias_modelo_certo": sum(d["modelo"] == d["sugerido"] for d in discord),
             "criterio_C": iguais / n >= CONCORDA_MIN, "discordancias": discord, "por_documento": por_doc}
        resumo[f"{orgao}_{lingua}"] = r
        print(f"{orgao} {lingua}: regra resolveu {resolvidos}/{n}; final = sugerida {iguais}/{n} (antes {modelo_igual}/{n}); "
              f"regra × modelo discordam em {len(discord)} (regra certa {r['discordancias_regra_certa']}, modelo certo "
              f"{r['discordancias_modelo_certo']}) | C {'SIM' if r['criterio_C'] else 'NÃO'}")
    (SAIDA / "extracao_codigo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
