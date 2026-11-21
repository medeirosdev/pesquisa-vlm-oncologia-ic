"""
Segundo modelo de linguagem: a configuração final do pré-laudo (avisos e lista de regiões colados por código, classe
lida por código) com outro modelo local, de outra família, no lugar do Gemma 3 4B. Pergunta: a fidelidade vem da
colagem e da checagem por código, ou de uma propriedade do Gemma?

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelo: Llama 3.2 3B (Ollama, llama3.2:3b), mesmas opções de geração (temperatura 0,2, semente 0, contexto 4096).
  Documentos, campos e instruções: os mesmos da configuração final.
     Pulmão (78): português, campos de resultados/aviso_discordancia/pulmao e instruções de
        aviso_discordancia.instrucoes("pulmao"); inglês, campos de resultados/avisos_por_codigo/en/pulmao e
        avisos_por_codigo.INSTRUCOES_EN["pulmao"].
     Próstata (60, decisão do GAT-MIL padronizado): campos de resultados/prelaudo_final/prostata/{pt,en}; instruções
        de aviso_discordancia.instrucoes("prostata") e INSTRUCOES_EN["prostata"].
  Colagem: prelaudo_final.colar_tudo (avisos e regiões). Classe: extracao_codigo.por_codigo (primeira linha da
     impressão); se a regra não achar, segunda chamada ao mesmo Llama em JSON restrito.
  Medidas: avisos_por_codigo.medir no texto final e no texto bruto.
  Critério L, em cada órgão e idioma (4 combinações): classe = sugerida em >= 90% e as condições de F1 (0 classe
     trocada, 0 aviso em região concordante, todas as regiões discordantes na seção, 0 números sem sustentação, 0
     coordenadas inventadas).
  Também reportado (sem critério): as medidas no texto bruto (comparadas às do Gemma); em quantos textos a regra achou
     a classe; em quantos o modelo escreveu as seções de avisos e de regiões; tempo por texto.
  Limite conhecido: um único segundo modelo, também pequeno.

Uso (venv do projeto; Ollama no ar com llama3.2:3b baixado):
    .venv/bin/python prelaudo/segundo_modelo.py --etapa redigir
    .venv/bin/python prelaudo/segundo_modelo.py --etapa checar
Saída: resultados/segundo_modelo/
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

import avisos_por_codigo as apc  # noqa: E402
from aviso_discordancia import SAIDA as SAIDA_AVISO, documentos, instrucoes  # noqa: E402
from extracao_codigo import por_codigo  # noqa: E402
from prelaudo_final import SAIDA as SAIDA_FINAL, colar_tudo, documentos_prostata  # noqa: E402

MODELO_B = "llama3.2:3b"
SAIDA = RESULTADOS_DIR / "segundo_modelo"
CONCORDA_MIN = 0.90


def casos():
    """{(orgao, lingua): (instruções, [(id, sugerido, campos_pt_base, campos_do_prompt)])}."""
    pul = documentos("pulmao")
    pro = documentos_prostata()
    ler = lambda p: p.read_text(encoding="utf-8")  # noqa: E731
    return {
        ("pulmao", "pt"): (instrucoes("pulmao"),
                           [(k, s, c, ler(SAIDA_AVISO / "pulmao" / f"{k}_campos.txt")) for k, s, c in pul]),
        ("pulmao", "en"): (apc.INSTRUCOES_EN["pulmao"],
                           [(k, s, c, ler(apc.SAIDA / "en" / "pulmao" / f"{k}_campos.txt")) for k, s, c in pul]),
        ("prostata", "pt"): (instrucoes("prostata"),
                             [(k, s, c, ler(SAIDA_FINAL / "prostata" / "pt" / f"{k}_campos.txt")) for k, s, c in pro]),
        ("prostata", "en"): (apc.INSTRUCOES_EN["prostata"],
                             [(k, s, c, ler(SAIDA_FINAL / "prostata" / "en" / f"{k}_campos.txt")) for k, s, c in pro]),
    }


def extrair_json(orgao, lingua, texto):
    import sintese
    if orgao == "pulmao":
        chave, opcoes = "type", ["adenocarcinoma", "squamous cell carcinoma"]
        pergunta = "Below is a lung histopathology draft report. What final histological type does it suggest?"
    else:
        chave, opcoes = "isup", list("012345")
        pergunta = "Below is a prostate biopsy draft report. What final ISUP grade (0 to 5) does it suggest?"
    formato = {"type": "object", "properties": {chave: {"type": "string", "enum": opcoes}}, "required": [chave]}
    corpo = {"model": MODELO_B, "stream": False, "format": formato, "options": sintese.OPCOES,
             "messages": [{"role": "user", "content": pergunta + " Answer only with the JSON.\n\n" + texto}]}
    req = urllib.request.Request(sintese.OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        v = json.loads(json.loads(r.read())["message"]["content"])[chave]
    return {"adenocarcinoma": "adenocarcinoma", "squamous cell carcinoma": "carcinoma escamoso"}[v] if orgao == "pulmao" else int(v)


def etapa_redigir():
    import sintese
    for (orgao, lingua), (instr, docs) in casos().items():
        pasta = SAIDA / lingua / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        registro = pasta / "registro.json"
        feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
        for k, sug, base, campos in docs:
            if k in feito:
                continue
            t0 = time.time()
            bruto = sintese.chamar(MODELO_B, campos, [], instrucoes=instr, lembrete="")["message"]["content"]
            (pasta / f"{k}_modelo.md").write_text(bruto, encoding="utf-8")
            final, ta, tr = colar_tudo(orgao, lingua, sug, base, bruto)
            (pasta / f"{k}.md").write_text(final, encoding="utf-8")
            cod = por_codigo(orgao, lingua, final)
            ext = cod if cod is not None else extrair_json(orgao, lingua, final)
            feito[k] = {"sugerido": sug, "extraido": ext, "pela_regra": cod is not None, "modelo_escreveu_avisos": ta,
                        "modelo_escreveu_regioes": tr, "segundos": round(time.time() - t0, 1)}
            registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {orgao} {lingua} {k[:12]}: sugerido {sug} | extraído {ext} ({feito[k]['segundos']} s)", flush=True)


def etapa_checar():
    resumo = {"modelo": MODELO_B}
    for (orgao, lingua), (_, docs) in casos().items():
        pasta = SAIDA / lingua / orgao
        feito = json.loads((pasta / "registro.json").read_text(encoding="utf-8"))
        med, med_bruto = {}, {}
        for k, sug, base, campos in docs:
            med[k] = apc.medir(orgao, lingua, sug, base, (pasta / f"{k}.md").read_text(encoding="utf-8"), campos)
            med_bruto[k] = apc.medir(orgao, lingua, sug, base, (pasta / f"{k}_modelo.md").read_text(encoding="utf-8"), campos)
        n = len(feito)
        concorda = sum(v["extraido"] == v["sugerido"] for v in feito.values())
        t = apc.somar(med)
        r = {"n": n, "classe_igual_sugerida": f"{concorda}/{n}", "pela_regra": f"{sum(v['pela_regra'] for v in feito.values())}/{n}",
             "colado": t, "texto_do_modelo_antes_da_colagem": apc.somar(med_bruto),
             "modelo_escreveu_avisos": f"{sum(v['modelo_escreveu_avisos'] for v in feito.values())}/{n}",
             "modelo_escreveu_regioes": f"{sum(v['modelo_escreveu_regioes'] for v in feito.values())}/{n}",
             "segundos_medio": round(float(np.mean([v["segundos"] for v in feito.values()])), 1),
             "criterio_L": concorda / n >= CONCORDA_MIN and apc.condicoes(t),
             "por_documento": {k: {**med[k], **feito[k]} for k in med}}
        resumo[f"{orgao}_{lingua}"] = r
        print(f"{orgao} {lingua}:", json.dumps({a: b for a, b in r.items() if a != "por_documento"}, ensure_ascii=False))
        print(f"{orgao} {lingua}: L {'SIM' if r['criterio_L'] else 'NÃO'}", flush=True)
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["redigir", "checar"], required=True)
    {"redigir": etapa_redigir, "checar": etapa_checar}[p.parse_args().etapa]()
