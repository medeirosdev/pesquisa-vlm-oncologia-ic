"""
Aviso de discordância pronto nos campos: o pré-laudo passa a apontar quando uma região de maior atenção contradiz a
classe sugerida? Nos pré-laudos do pulmão (tcga_descritor_prelaudo.py) e da próstata (panda_descritor_prelaudo.py), a
regra nas instruções ("aponte essa discordância") quase não funcionou: 3 de 27 e 1 de 35 textos. Aqui a discordância é
calculada antes, por código, e entra nos campos como uma linha de AVISO; o modelo de linguagem só precisa reproduzi-la.

Fixado ANTES de rodar (commit anterior aos resultados):
  Documentos: os mesmos dos testes anteriores, com os mesmos campos (lidos de resultados/tcga_prelaudo e
     resultados/panda_prelaudo): 78 lâminas de pulmão e 60 biópsias de próstata. Classe sugerida, regiões,
     coordenadas e números não mudam.
  Discordância (a mesma regra das etapas checar anteriores): pulmão, região cuja classe pelo descritor é diferente do
     tipo sugerido (inclui pulmão normal); próstata, região com padrão de Gleason quando o sugerido é ISUP 0, ou região
     benigna quando o sugerido é ISUP >= 1.
  Mudança nos campos: depois das regiões, uma seção de avisos. Para cada região discordante, uma linha
     "AVISO: a região [x,y] foi descrita pelo descritor como <classe> (<prob>), o que discorda do <tipo/grau> sugerido
     (<valor>). Esta região deve ser revisada antes de aceitar o <tipo/grau> sugerido."; sem região discordante,
     "Avisos de discordância: nenhum."
  Mudança nas instruções: a regra 5 antiga ("aponte essa discordância") vira "reproduza cada AVISO na seção
     ## Avisos de discordância, com a coordenada e a classe, sem minimizar nem justificar; sem avisos, escreva
     'Nenhum aviso.'"; a estrutura ganha essa seção. O resto das instruções, o modelo (Gemma 3 4B) e as opções de
     geração (temperatura 0,2, semente 0) são os mesmos.
  Medida "aponta" (aplicada igual aos textos antigos e aos novos): uma região é apontada se alguma linha do texto que
     contém a coordenada dela (ou a linha seguinte) tem uma destas expressões: discord, diverg, contradi, difere,
     diferente, aviso, atenção, alerta, no entanto, embora, porém, entretanto, apesar, inconsist. Um documento aponta
     a discordância se pelo menos uma das suas regiões discordantes é apontada.
  Critérios (em cada órgão separadamente):
     W1: nos documentos com região discordante, o texto novo aponta a discordância em >= 90%.
     W2 (falso alarme): nos documentos sem região discordante, alguma região apontada pela mesma medida em <= 10%.
     W3: o resto não piora: classe extraída do texto = classe sugerida em >= 90%, 0 números sem sustentação e 0
         coordenadas inventadas (prelaudo_campos.checar_texto).
  Também reportado (sem critério): a mesma medida nos textos antigos (referência); a contagem antiga por expressões
     (tcga_descritor_prelaudo.EXPRESSOES_DISCORDANCIA); fração das regiões discordantes apontadas, uma a uma.
  Limite conhecido: a medida é por expressões, não por leitura; não verifica se o texto, além de reproduzir o aviso,
     também tenta justificá-lo em outra seção.

Uso (venv do projeto; a etapa redigir precisa do Ollama no ar):
    .venv/bin/python prelaudo/aviso_discordancia.py --etapa campos
    .venv/bin/python prelaudo/aviso_discordancia.py --etapa redigir
    .venv/bin/python prelaudo/aviso_discordancia.py --etapa checar
Saída: resultados/aviso_discordancia/{pulmao,prostata}/ e resultados/aviso_discordancia/resumo.json
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "aviso_discordancia"
ORIGEM = {"pulmao": RESULTADOS_DIR / "tcga_prelaudo", "prostata": RESULTADOS_DIR / "panda_prelaudo"}
REGIAO = re.compile(r"^\s+\[(\d+),(\d+)\] (.+?) ([\d.]+)$", re.M)
EXPRESSOES = ("discord", "diverg", "contradi", "difere", "diferente", "aviso", "atenção", "alerta", "no entanto",
              "embora", "porém", "entretanto", "apesar", "inconsist")
W1_MIN, W2_MAX, CONCORDA_MIN = 0.90, 0.10, 0.90
REGRA5 = {"pulmao": "5. Se alguma região que mais pesou na decisão for descrita com uma classe diferente do tipo "
                    "sugerido, aponte essa discordância.",
          "prostata": "5. Se alguma região que mais pesou na decisão discordar do grau sugerido (por exemplo, região com "
                      "padrão de Gleason quando o grau sugerido é ISUP 0, ou região benigna quando o grau sugerido é de "
                      "câncer), aponte essa discordância."}
REGRA5_NOVA = ("5. Os campos trazem uma seção de avisos de discordância, calculada automaticamente. Reproduza cada AVISO "
               "na seção \"## Avisos de discordância\", com a coordenada da região e a classe dada pelo descritor, sem "
               "minimizar, sem justificar e sem usar a região como argumento a favor do {alvo} sugerido. Se os campos "
               "disserem que não há avisos, escreva apenas \"Nenhum aviso.\" nessa seção.")


def instrucoes(orgao):
    if orgao == "pulmao":
        from tcga_descritor_prelaudo import INSTRUCOES_PULMAO as base
        alvo = "tipo"
    else:
        from panda_descritor_prelaudo import INSTRUCOES_PROSTATA as base
        alvo = "grau"
    assert base.count(REGRA5[orgao]) == 1 and base.count("## Regiões para revisão prioritária") == 1
    return (base.replace(REGRA5[orgao], REGRA5_NOVA.format(alvo=alvo))
            .replace("## Regiões para revisão prioritária", "## Avisos de discordância\n## Regiões para revisão prioritária"))


def documentos(orgao):
    """[(id, classe sugerida, campos antigos)] na ordem do registro do teste anterior."""
    reg = json.loads((ORIGEM[orgao] / "registro.json").read_text(encoding="utf-8"))
    chave = "tipo_sugerido" if orgao == "pulmao" else "isup_sugerido"
    return [(k, v[chave], (ORIGEM[orgao] / f"{k}_campos.txt").read_text(encoding="utf-8")) for k, v in reg.items()]


def discordantes(orgao, sugerido, campos):
    out = []
    for x, y, classe, prob in REGIAO.findall(campos):
        if orgao == "pulmao":
            disc = classe != sugerido
        else:
            disc = (classe != "benigno") if sugerido == 0 else (classe == "benigno")
        if disc:
            out.append((f"[{x},{y}]", classe, prob))
    return out


def linha_aviso(orgao, sugerido, coord, classe, prob):
    if orgao == "pulmao":
        alvo, valor = "tipo", sugerido
    else:
        alvo, valor = "grau", f"ISUP {sugerido}" + (", sem câncer" if sugerido == 0 else "")
    return (f"  AVISO: a região {coord} foi descrita pelo descritor como {classe} ({prob}), o que discorda do {alvo} "
            f"sugerido ({valor}). Esta região deve ser revisada antes de aceitar o {alvo} sugerido.")


def etapa_campos():
    for orgao in ORIGEM:
        pasta = SAIDA / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        n_disc = 0
        for k, sug, campos in documentos(orgao):
            d = discordantes(orgao, sug, campos)
            n_disc += bool(d)
            extra = (["Avisos de discordância (calculados automaticamente a partir dos campos acima):"]
                     + [linha_aviso(orgao, sug, *r) for r in d]) if d else ["Avisos de discordância: nenhum."]
            (pasta / f"{k}_campos.txt").write_text(campos + "\n" + "\n".join(extra), encoding="utf-8")
        print(f"{orgao}: {len(documentos(orgao))} documentos, {n_disc} com região discordante", flush=True)


def etapa_redigir():
    import sintese
    from panda_descritor_prelaudo import extrair_isup
    from tcga_descritor_prelaudo import MODELO, classificar_texto
    for orgao in ORIGEM:
        pasta, instr = SAIDA / orgao, instrucoes(orgao)
        registro = pasta / "registro.json"
        feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
        for k, sug, _ in documentos(orgao):
            if k in feito:
                continue
            campos = (pasta / f"{k}_campos.txt").read_text(encoding="utf-8")
            t0 = time.time()
            texto = sintese.chamar(MODELO, campos, [], instrucoes=instr, lembrete="")["message"]["content"]
            (pasta / f"{k}.md").write_text(texto, encoding="utf-8")
            extraido = classificar_texto(texto) if orgao == "pulmao" else extrair_isup(texto)
            feito[k] = {"sugerido": sug, "extraido": extraido, "segundos": round(time.time() - t0, 1)}
            registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {orgao} {k[:12]}: sugerido {sug} | extraído {extraido} ({feito[k]['segundos']} s)", flush=True)


def apontadas(texto, coords):
    """Coordenadas apontadas: alguma linha com a coordenada (ou a seguinte) tem uma expressão de discordância."""
    linhas = [re.sub(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", r"[\1,\2]", l).lower() for l in texto.splitlines()]
    out = set()
    for i, l in enumerate(linhas):
        for c in coords:
            if c in l and any(e in l or (i + 1 < len(linhas) and e in linhas[i + 1]) for e in EXPRESSOES):
                out.add(c)
    return out


def medir(orgao, pasta_textos):
    from tcga_descritor_prelaudo import EXPRESSOES_DISCORDANCIA
    disc_docs = aponta = antiga = regioes_disc = regioes_ap = sem_disc = falso = 0
    for k, sug, campos in documentos(orgao):
        texto = (pasta_textos / f"{k}.md").read_text(encoding="utf-8")
        d = [c for c, _, _ in discordantes(orgao, sug, campos)]
        todas = [f"[{x},{y}]" for x, y, _, _ in REGIAO.findall(campos)]
        if d:
            ap = apontadas(texto, d)
            disc_docs += 1
            aponta += bool(ap)
            regioes_disc += len(d)
            regioes_ap += len(ap)
            antiga += any(e in texto.lower() for e in EXPRESSOES_DISCORDANCIA)
        else:
            sem_disc += 1
            falso += bool(apontadas(texto, todas))
    return {"documentos_com_regiao_discordante": disc_docs, "apontam": aponta,
            "fracao_apontam": round(aponta / max(disc_docs, 1), 3),
            "regioes_discordantes_apontadas": f"{regioes_ap}/{regioes_disc}",
            "contagem_antiga_por_expressoes": f"{antiga}/{disc_docs}",
            "documentos_sem_discordancia": sem_disc, "falso_alarme": falso,
            "fracao_falso_alarme": round(falso / max(sem_disc, 1), 3)}


def etapa_checar():
    from prelaudo_campos import checar_texto
    resumo = {}
    for orgao in ORIGEM:
        pasta = SAIDA / orgao
        feito = json.loads((pasta / "registro.json").read_text(encoding="utf-8"))
        ch = {k: checar_texto((pasta / f"{k}.md").read_text(encoding="utf-8"),
                              (pasta / f"{k}_campos.txt").read_text(encoding="utf-8")) for k in feito}
        novo, antigo = medir(orgao, pasta), medir(orgao, ORIGEM[orgao])
        concorda = sum(v["extraido"] == v["sugerido"] for v in feito.values())
        ns = sum(len(c["nao_sustentados"]) for c in ch.values())
        ci = sum(len(c["coordenadas_inventadas"]) for c in ch.values())
        r = {"n": len(feito), "novo_com_aviso": novo, "antigo_sem_aviso": antigo,
             "classe_extraida_igual_sugerida": f"{concorda}/{len(feito)}",
             "numeros_checados": sum(c["numeros_checados"] for c in ch.values()), "nao_sustentados": ns,
             "coordenadas": sum(c["coordenadas"] for c in ch.values()), "coordenadas_inventadas": ci,
             "segundos_medio": round(sum(v["segundos"] for v in feito.values()) / len(feito), 1)}
        r["criterio_W1"] = novo["fracao_apontam"] >= W1_MIN
        r["criterio_W2"] = novo["fracao_falso_alarme"] <= W2_MAX
        r["criterio_W3"] = concorda / len(feito) >= CONCORDA_MIN and ns == 0 and ci == 0
        resumo[orgao] = r
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    for o, r in resumo.items():
        print(f"{o}: W1 {'SIM' if r['criterio_W1'] else 'NÃO'} | W2 {'SIM' if r['criterio_W2'] else 'NÃO'} | "
              f"W3 {'SIM' if r['criterio_W3'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["campos", "redigir", "checar"], required=True)
    {"campos": etapa_campos, "redigir": etapa_redigir, "checar": etapa_checar}[p.parse_args().etapa]()
