"""
Laudos em documentos reservados (revisão 01, item D3): as regras do laudo (avisos, montagem das seções pelo código,
leitura da classe e as checagens) foram desenhadas em sequência nos mesmos 60 documentos da próstata. Aqui elas rodam,
sem nenhuma mudança, nas 240 biópsias de desenvolvimento que nunca viraram laudo.

Fixado ANTES de rodar (commit anterior aos resultados):
  Documentos: as 300 biópsias de desenvolvimento menos as 60 dos pré-laudos (panda_descritor_prelaudo.biopsias_prelaudo),
     com o modelo único r0 (prostata_r0: previsão de gat_padronizado_r0.json, regiões por regioes_r0, campos por
     prelaudo_final.campos_pt_prostata, avisos por aviso_discordancia.discordantes, campos em inglês por
     avisos_por_codigo.campos_en), exatamente como prostata_r0.etapa_campos.
  Laudos: template (secoes_por_codigo.montar com resumo_template) e braço com modelo de linguagem (Gemma 3 4B e Llama 3.2
     3B escrevem só o parágrafo de resumo; secoes_por_codigo.INSTR; mesmas opções, semente 0), pt e en.
  Medidas: no template, avisos_por_codigo.medir no laudo inteiro e classe lida por código; no parágrafo, as do critério Q
     (secoes_por_codigo.medir_paragrafo) e as checagens semânticas S1 e S2 (checagem_semantica.s1, s2).
  Critério R1 (as regras generalizam): no template, 0 classes trocadas, 0 avisos em região concordante, 0 coordenadas
     inventadas, 0 números sem sustentação e classe lida = sugerida em 100%, em pt e en.
  Também reportado: o critério Q em cada caso (modelo × idioma) e as taxas por documento (números sem sustentação,
     S1, S2) ao lado das dos 60 documentos de antes.
  Limite: reservado só na próstata (no pulmão, as 78 lâminas de teste da divisão aleatória já são todos os laudos).

Uso (venv do projeto; Ollama no ar para redigir):
    .venv/bin/python prelaudo/reservados_prostata.py --etapa campos
    .venv/bin/python prelaudo/reservados_prostata.py --etapa redigir --modelo gemma3:4b
    .venv/bin/python prelaudo/reservados_prostata.py --etapa redigir --modelo llama3.2:3b
    .venv/bin/python prelaudo/reservados_prostata.py --etapa checar
Saída: resultados/reservados_prostata/
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "reservados_prostata"


def documentos():
    reg = json.loads((SAIDA / "documentos.json").read_text(encoding="utf-8"))
    return [(k, v["sugerido"], (SAIDA / f"{k}_campos_base.txt").read_text(encoding="utf-8")) for k, v in reg.items()]


def casos():
    ler = lambda p: p.read_text(encoding="utf-8")  # noqa: E731
    d = documentos()
    return {("prostata", lg): [(k, s, c, ler(SAIDA / lg / f"{k}_campos.txt")) for k, s, c in d] for lg in ("pt", "en")}


def etapa_campos():
    import avisos_por_codigo as apc
    from aviso_discordancia import discordantes, linha_aviso
    from panda_descritor_prelaudo import biopsias_prelaudo
    from panda_mil import biopsias
    from prelaudo_final import campos_pt_prostata
    from prostata_r0 import PASTA_R0, regioes_r0

    r0 = json.loads((PASTA_R0 / "gat_padronizado_r0.json").read_text(encoding="utf-8"))
    laudo = {l["image_id"] for l in biopsias_prelaudo()}
    _, prontas = biopsias()
    for lg in ("pt", "en"):
        (SAIDA / lg).mkdir(parents=True, exist_ok=True)
    docs = {}
    for l in prontas:
        if l["conjunto"] != "teste" or l["image_id"] in laudo:
            continue
        k, m = l["image_id"], r0[l["image_id"]]
        g, probs = m["previsto"], m["probs"]
        _, ps, reg = regioes_r0(l)
        base = campos_pt_prostata(l, g, probs, ps, reg)
        (SAIDA / f"{k}_campos_base.txt").write_text(base, encoding="utf-8")
        d = discordantes("prostata", g, base)
        extra = (["Avisos de discordância (calculados automaticamente a partir dos campos acima):"]
                 + [linha_aviso("prostata", g, *r) for r in d]) if d else ["Avisos de discordância: nenhum."]
        (SAIDA / "pt" / f"{k}_campos.txt").write_text(base + "\n" + "\n".join(extra), encoding="utf-8")
        (SAIDA / "en" / f"{k}_campos.txt").write_text(apc.campos_en("prostata", g, base), encoding="utf-8")
        docs[k] = {"real": int(l["isup_grade"]), "sugerido": g, "regiao_discordante": bool(d)}
    (SAIDA / "documentos.json").write_text(json.dumps(docs, indent=1), encoding="utf-8")
    print(f"{len(docs)} documentos reservados; com região discordante: {sum(v['regiao_discordante'] for v in docs.values())}")


def etapa_redigir(modelo):
    import secoes_por_codigo as spc
    import sintese
    nome = spc.MODELOS[modelo]
    for (orgao, lg), docs in casos().items():
        pasta = SAIDA / nome / lg
        pasta.mkdir(parents=True, exist_ok=True)
        reg = pasta / "registro.json"
        feito = json.loads(reg.read_text(encoding="utf-8")) if reg.exists() else {}
        for k, sug, base, campos in docs:
            if k in feito:
                continue
            t0 = time.time()
            par = sintese.chamar(modelo, campos, [], instrucoes=spc.INSTR[lg], lembrete="")["message"]["content"].strip()
            (pasta / f"{k}_paragrafo.txt").write_text(par, encoding="utf-8")
            (pasta / f"{k}.md").write_text(spc.montar(orgao, lg, sug, base, campos, par), encoding="utf-8")
            feito[k] = {"sugerido": sug, "segundos": round(time.time() - t0, 1)}
            reg.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  {nome} {lg}: {len(feito)} prontos", flush=True)


def etapa_checar():
    import avisos_por_codigo as apc
    import secoes_por_codigo as spc
    from checagem_semantica import s1, s2
    from extracao_codigo import por_codigo
    res = {}
    for (orgao, lg), docs in casos().items():
        classes = [c.lower() for c in apc.LINGUA[lg]["classes"][orgao]]
        tm, cl = [], 0
        for k, s, b, c in docs:
            t = spc.montar(orgao, lg, s, b, c, spc.resumo_template(c, lg))
            tm.append(apc.medir(orgao, lg, s, b, t, c))
            cl += por_codigo(orgao, lg, t) == s
        soma = apc.somar(dict(enumerate(tm)))
        r = {"n": len(docs), "classe_lida_igual": f"{cl}/{len(docs)}", **soma}
        r["criterio_R1"] = (soma["classe_trocada"] == 0 and soma["aviso_em_regiao_concordante"] == 0
                            and soma["coordenadas_inventadas"] == 0 and soma["nao_sustentados"] == 0 and cl == len(docs))
        res[f"template_{orgao}_{lg}"] = r
        for nome in spc.MODELOS.values():
            pasta = SAIDA / nome / lg
            if not (pasta / "registro.json").exists():
                continue
            med, n_s1, n_s2, cl = {}, 0, 0, 0
            for k, s, b, c in docs:
                par = (pasta / f"{k}_paragrafo.txt").read_text(encoding="utf-8")
                med[k] = spc.medir_paragrafo(orgao, lg, s, b, c, par)
                n_s1 += bool(s1(par, c, lg, classes))
                n_s2 += bool(s2(par, b, orgao, s, lg))
                cl += por_codigo(orgao, lg, (pasta / f"{k}.md").read_text(encoding="utf-8")) == s
            n = len(docs)
            sm = {x: sum(v[x] for v in med.values()) for x in ("nao_sustentados", "coordenadas_inventadas", "classe_trocada",
                                                                "aviso_em_regiao_concordante", "vazio")}
            q = {"n": n, **sm, "documentos_com_numero_nao_sustentado": sum(v["nao_sustentados"] > 0 for v in med.values()),
                 "S1_paragrafos": n_s1, "S2_paragrafos": n_s2, "classe_lida_igual": f"{cl}/{n}",
                 "palavras_medio": round(float(np.mean([v["palavras"] for v in med.values()])), 1)}
            q["criterio_Q"] = (sm["nao_sustentados"] == 0 and sm["coordenadas_inventadas"] == 0 and sm["classe_trocada"] == 0
                               and sm["aviso_em_regiao_concordante"] == 0 and cl == n)
            res[f"{nome}_{orgao}_{lg}"] = q
    res["criterio_R1"] = all(v["criterio_R1"] for k, v in res.items() if k.startswith("template_"))
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, v in res.items():
        print(k, v)
    print(f"R1 {'SIM' if res['criterio_R1'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["campos", "redigir", "checar"], required=True)
    p.add_argument("--modelo", choices=["gemma3:4b", "llama3.2:3b"], default="gemma3:4b")
    a = p.parse_args()
    {"campos": etapa_campos, "redigir": lambda: etapa_redigir(a.modelo), "checar": etapa_checar}[a.etapa]()
