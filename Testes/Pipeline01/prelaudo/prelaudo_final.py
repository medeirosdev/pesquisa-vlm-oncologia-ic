"""
Pré-laudo final: lista de regiões também colada por código (pulmão) e próstata com o modelo melhor (GAT-MIL com
embeddings padronizados por centro).

Antes (avisos_por_codigo.py): com a seção de avisos colada por código, a classe e os avisos ficaram fiéis, mas no
pulmão em inglês o modelo copiou errado uma coordenada na lista "## Regions for priority review" (1 de 284), e o
critério K2 não passou. E os pré-laudos da próstata vêm do ABMIL sem padronização, que coloca quase tudo em ISUP 3
(kappa 0,24 entre centros); o melhor modelo na troca de centro é o GAT-MIL com os embeddings padronizados por centro
(panda_centro.py, braço R1: kappa 0,609), que não guardou probabilidades nem atenção por biópsia.

Fixado ANTES de rodar (commit anterior aos resultados):
  Colagem das regiões: depois da colagem dos avisos (avisos_por_codigo.colar), o conteúdo da seção "## Regiões para
     revisão prioritária" ("## Regions for priority review") é trocado pelas 3 regiões dos campos, uma por linha, na
     ordem dos campos e no formato dos campos ("[x,y] <classe> <prob>", classe em inglês no texto em inglês). Seções
     repetidas são apagadas; se o modelo não escreveu a seção, ela é inserida antes de "## Limitações"
     ("## Limitations"), ou no fim. O resto do texto não muda. O modelo continua recebendo as mesmas instruções.
  Etapa pulmao (item 1, sem chamar o modelo): a colagem dos avisos e das regiões é aplicada aos textos brutos já
     escritos: português, resultados/aviso_discordancia/pulmao/<id>.md; inglês,
     resultados/avisos_por_codigo/en/pulmao/<id>_modelo.md. Mesmos campos. A classe extraída é a dos registros
     anteriores (a impressão não muda).
  Etapa gat (item 2): GAT-MIL (gat_mil.treinar, 8 vizinhos encostados, k = 6, 5 sementes, média das probabilidades)
     com os embeddings padronizados por centro (panda_centro.padronizar_por_centro: Radboud pelas 600 de treino,
     Karolinska pelas 300 de teste, sem rótulo), treino nas 600 do Radboud, teste nas 300 do Karolinska: a mesma
     receita do braço R1|gat de panda_centro.py. Guarda as probabilidades e a atenção (média das 5 sementes) de cada
     biópsia de teste. Reportado (sem critério): o kappa nas 300, para conferir com o 0,609 de antes.
  Etapa campos_prostata: as mesmas 60 biópsias (panda_descritor_prelaudo.biopsias_prelaudo, 10 por ISUP real), os
     mesmos campos de antes (mesmo descritor, mesmo formato), trocando a decisão (ISUP e probabilidades do GAT-MIL
     padronizado) e as regiões (3 de maior atenção do GAT-MIL, >= 192 µm entre os centros). Avisos calculados como
     em aviso_discordancia.py; campos em inglês como em avisos_por_codigo.py.
  Etapa redigir_prostata: português com as instruções de aviso_discordancia.py, inglês com
     avisos_por_codigo.INSTRUCOES_EN; mesmo modelo (Gemma 3 4B, temperatura 0,2, semente 0); classe extraída por
     JSON restrito (panda_descritor_prelaudo.extrair_isup e avisos_por_codigo.extrair_en). Texto bruto guardado em
     <id>_modelo.md e o final, com as duas colagens, em <id>.md.
  Medidas: as de avisos_por_codigo.medir, no texto final (classe trocada, aviso em região concordante, regiões
     discordantes na seção de avisos, números sem sustentação, coordenadas inventadas).
  Critérios:
     F1 (pulmão, português e inglês, cada um): 0 classe trocada, 0 aviso em região concordante, todas as regiões
        discordantes na seção, 0 números sem sustentação, 0 coordenadas inventadas.
     F2 (próstata com o GAT-MIL padronizado, português e inglês, cada um): ISUP extraído = sugerido em >= 90% e as
        mesmas condições de F1.
  Também reportado (sem critério): as medidas no texto bruto; distribuição do ISUP sugerido nas 60 (antes, 40 de 60
     em ISUP 3) e ISUP sugerido = real nas 60; nas biópsias de teste com ISUP >= 1 e máscara, quantas têm >= 2 das 3
     regiões de maior atenção do GAT-MIL no câncer (antes, com o ABMIL, 190 de 250; acaso 0,43), com a mesma regra de
     panda_descritor_prelaudo.py; documentos com região discordante; tempo por texto.
  Limites conhecidos: os do avisos_por_codigo.py; com as duas seções coladas, o que resta escrito pelo modelo é o
     resumo, a impressão e as limitações.

Uso (venv do projeto; gat usa a GPU; redigir_prostata precisa do Ollama no ar):
    .venv/bin/python prelaudo/prelaudo_final.py --etapa pulmao
    .venv/bin/python prelaudo/prelaudo_final.py --etapa gat
    .venv/bin/python prelaudo/prelaudo_final.py --etapa campos_prostata
    .venv/bin/python prelaudo/prelaudo_final.py --etapa redigir_prostata
    .venv/bin/python prelaudo/prelaudo_final.py --etapa checar_prostata
Saída: resultados/prelaudo_final/
"""

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

import avisos_por_codigo as apc  # noqa: E402
from aviso_discordancia import REGIAO, SAIDA as SAIDA_AVISO, discordantes, documentos, linha_aviso  # noqa: E402

SAIDA = RESULTADOS_DIR / "prelaudo_final"
GAT = SAIDA / "prostata_gat"
CONCORDA_MIN = 0.90
K = 6
SECAO_REGIOES = {"pt": "## Regiões para revisão prioritária", "en": "## Regions for priority review"}
LIMITACOES = {"pt": "## Limitações", "en": "## Limitations"}


def linhas_regioes(campos_pt, lingua):
    tr = (lambda c: c) if lingua == "pt" else (lambda c: apc.CLASSE_EN[c])
    return [f"[{x},{y}] {tr(c)} {p}" for x, y, c, p in REGIAO.findall(campos_pt)]


def colar_regioes(texto, linhas, lingua):
    titulo = SECAO_REGIOES[lingua]
    bloco = f"{titulo}\n" + "\n".join(linhas) + "\n\n"
    secao = re.compile(rf"^{re.escape(titulo)}[^\n]*\n?.*?(?=^## |\Z)", re.M | re.S)
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
    m = re.search(rf"^{re.escape(LIMITACOES[lingua])}", texto, re.M)
    if m is None:
        return texto.rstrip() + "\n\n" + bloco, False
    return texto[:m.start()] + bloco + texto[m.start():], False


def colar_tudo(orgao, lingua, sugerido, campos_pt, bruto):
    t, tinha_avisos = apc.colar(bruto, apc.linhas_aviso(orgao, lingua, sugerido, campos_pt), lingua)
    t, tinha_regioes = colar_regioes(t, linhas_regioes(campos_pt, lingua), lingua)
    return t, tinha_avisos, tinha_regioes


def resumir(med, med_bruto, n_concorda, n, extra=None):
    t = apc.somar(med)
    r = {"n": n, "classe_extraida_igual_sugerida": f"{n_concorda}/{n}", "colado": t,
         "texto_do_modelo_antes_da_colagem": apc.somar(med_bruto), "condicoes": apc.condicoes(t),
         "classe_ok": n_concorda / n >= CONCORDA_MIN}
    r.update(extra or {})
    return r


# ---------------------------------------------------------------- pulmão (item 1)

def etapa_pulmao():
    orgao, resumo = "pulmao", {}
    reg_pt = json.loads((SAIDA_AVISO / orgao / "registro.json").read_text(encoding="utf-8"))
    reg_en = json.loads((apc.SAIDA / "en" / orgao / "registro.json").read_text(encoding="utf-8"))
    for lingua, reg in (("pt", reg_pt), ("en", reg_en)):
        pasta = SAIDA / lingua / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        med, med_bruto, sec = {}, {}, Counter()
        for k, sug, campos in documentos(orgao):
            if lingua == "pt":
                evid = (SAIDA_AVISO / orgao / f"{k}_campos.txt").read_text(encoding="utf-8")
                bruto = (SAIDA_AVISO / orgao / f"{k}.md").read_text(encoding="utf-8")
            else:
                evid = (apc.SAIDA / "en" / orgao / f"{k}_campos.txt").read_text(encoding="utf-8")
                bruto = (apc.SAIDA / "en" / orgao / f"{k}_modelo.md").read_text(encoding="utf-8")
            final, ta, tr = colar_tudo(orgao, lingua, sug, campos, bruto)
            sec["avisos"] += ta
            sec["regioes"] += tr
            (pasta / f"{k}.md").write_text(final, encoding="utf-8")
            med[k] = apc.medir(orgao, lingua, sug, campos, final, evid)
            med_bruto[k] = apc.medir(orgao, lingua, sug, campos, bruto, evid)
        concorda = sum(v["extraido"] == v["sugerido"] for v in reg.values())
        r = resumir(med, med_bruto, concorda, len(med),
                    {"modelo_escreveu_avisos": f"{sec['avisos']}/{len(med)}",
                     "modelo_escreveu_regioes": f"{sec['regioes']}/{len(med)}", "por_documento": med})
        r["criterio_F1"] = r["condicoes"]
        resumo[lingua] = r
        print(lingua, json.dumps({a: b for a, b in r.items() if a != "por_documento"}, indent=1, ensure_ascii=False))
        print(f"pulmão {lingua}: F1 {'SIM' if r['criterio_F1'] else 'NÃO'}", flush=True)
    (SAIDA / "resumo_pulmao.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- próstata (item 2)

def etapa_gat():
    import torch
    import gat_mil
    import mil_atencao
    from gat_mil_panda import carregar
    from panda_centro import padronizar_por_centro
    from panda_mil import biopsias, kappa_quadratico
    GAT.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    y = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr = [l["image_id"] for l in prontas if l["conjunto"] == "treino"]
    te = [l["image_id"] for l in prontas if l["conjunto"] == "teste"]
    X0, G = carregar(tr + te)
    X = padronizar_por_centro(X0, [tr, te])
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    P = {i: np.zeros(K) for i in te}
    att = {i: np.zeros(len(X[i])) for i in te}
    ytr = np.array([y[i] for i in tr])
    n = len(mil_atencao.SEMENTES)
    for semente in mil_atencao.SEMENTES:
        b = gat_mil.treinar([X[i] for i in tr], [G[i] for i in tr], ytr, semente, dispositivo, k=K).eval()
        with torch.no_grad():
            for i in te:
                logit, a, _ = b(X[i].to(dispositivo), G[i].to(dispositivo))
                P[i] += torch.softmax(logit, 0).cpu().numpy() / n
                att[i] += a.cpu().numpy() / n
        print(f"    semente {semente} pronta", flush=True)
    for i in te:
        np.save(GAT / f"{i}_atencao.npy", att[i].astype(np.float32))
    real = np.array([y[i] for i in te])
    pred = np.array([int(P[i].argmax()) for i in te])
    resumo = {"n_treino": len(tr), "n_teste": len(te), "kappa_quadratico": round(kappa_quadratico(real, pred, K), 3),
              "kappa_antes_panda_centro_R1_gat": 0.609, "previstos_por_isup": np.bincount(pred, minlength=K).tolist(),
              "por_biopsia": {i: {"real": y[i], "previsto": int(P[i].argmax()), "probs": [round(float(v), 4) for v in P[i]]}
                              for i in te}}
    (GAT / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_biopsia"}, indent=1, ensure_ascii=False))


def regioes_gat(l):
    from panda_descritor_prelaudo import CLASSES, N_REGIOES, SAIDA as SAIDA_PANDA, carregar
    from tcga_descritor_prelaudo import gate_um
    meta, xy, fr = carregar(l)
    P = np.load(SAIDA_PANDA / f"{l['image_id']}_descritor.npy")
    att = np.load(GAT / f"{l['image_id']}_atencao.npy")
    lado = meta["lado_px"]
    ps = [{"i": i, "x0": int(x), "y0": int(y), "cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a),
           "classe": CLASSES[int(p.argmax())], "prob": float(p.max())} for i, ((x, y), p, a) in enumerate(zip(xy, P, att))]
    return fr, ps, gate_um(sorted(ps, key=lambda d: -d["atencao"]), meta["mpp"], N_REGIOES)


def campos_pt_prostata(l, g, probs, ps, reg):
    from panda_descritor_prelaudo import CLASSES, NOME_PT
    from prelaudo_campos import confianca
    n, cont = len(ps), Counter(d["classe"] for d in ps)
    linhas = ["=== Campos para o pré-laudo ===", f"Biópsia: {l['image_id'][:8]}",
              f"Grau ISUP sugerido pelo classificador da biópsia: ISUP {g}" + (" (sem câncer)" if g == 0 else ""),
              "Probabilidades do classificador: " + ", ".join(f"ISUP {k} {v:.2f}" for k, v in enumerate(probs)),
              f"Confiança: {confianca(probs[g])} (probabilidade do grau sugerido {probs[g]:.2f})",
              f"Proporção entre os {n} patches de tecido da biópsia (classe de cada patch pelo descritor):"]
    linhas += [f"  - {NOME_PT[c]}: {cont.get(c, 0)} patches ({100 * cont.get(c, 0) / n:.1f}%)" for c in CLASSES]
    linhas += ["Regiões que mais pesaram na decisão do classificador (classe de cada patch pelo descritor):"]
    linhas += [f"  [{d['x0']},{d['y0']}] {NOME_PT[d['classe']]} {d['prob']:.2f}" for d in reg]
    return "\n".join(linhas)


def documentos_prostata():
    """[(id, ISUP sugerido pelo GAT-MIL, campos em português sem avisos)] das 60 biópsias."""
    reg = json.loads((SAIDA / "prostata" / "documentos.json").read_text(encoding="utf-8"))
    return [(k, v["sugerido"], (SAIDA / "prostata" / f"{k}_campos_base.txt").read_text(encoding="utf-8"))
            for k, v in reg.items()]


def etapa_campos_prostata():
    from panda_descritor_prelaudo import biopsias_prelaudo, no_cancer
    from panda_mil import biopsias
    gat = json.loads((GAT / "resumo.json").read_text(encoding="utf-8"))["por_biopsia"]
    pasta = SAIDA / "prostata"
    for lg in ("pt", "en"):
        (pasta / lg).mkdir(parents=True, exist_ok=True)
    docs, n_disc = {}, 0
    for l in biopsias_prelaudo():
        k, m = l["image_id"], gat[l["image_id"]]
        g, probs = m["previsto"], m["probs"]
        _, ps, reg = regioes_gat(l)
        base = campos_pt_prostata(l, g, probs, ps, reg)
        (pasta / f"{k}_campos_base.txt").write_text(base, encoding="utf-8")
        d = discordantes("prostata", g, base)
        n_disc += bool(d)
        extra = (["Avisos de discordância (calculados automaticamente a partir dos campos acima):"]
                 + [linha_aviso("prostata", g, *r) for r in d]) if d else ["Avisos de discordância: nenhum."]
        (pasta / "pt" / f"{k}_campos.txt").write_text(base + "\n" + "\n".join(extra), encoding="utf-8")
        (pasta / "en" / f"{k}_campos.txt").write_text(apc.campos_en("prostata", g, base), encoding="utf-8")
        docs[k] = {"real": int(l["isup_grade"]), "sugerido": g, "regiao_discordante": bool(d)}
    (pasta / "documentos.json").write_text(json.dumps(docs, indent=1), encoding="utf-8")
    # regiões de maior atenção no câncer (biópsias de teste com ISUP >= 1 e máscara), como no critério A de antes
    _, prontas = biopsias()
    ok = n = 0
    acaso = []
    for l in prontas:
        if l["conjunto"] != "teste" or int(l["isup_grade"]) < 1:
            continue
        fr, _, reg = regioes_gat(l)
        if fr is None:
            continue
        n += 1
        ok += sum(no_cancer(fr[d["i"]]) for d in reg) >= 2
        q = float(np.mean([no_cancer(f) for f in fr]))
        acaso.append(3 * q ** 2 * (1 - q) + q ** 3)
    sug = Counter(v["sugerido"] for v in docs.values())
    info = {"documentos": len(docs), "com_regiao_discordante": n_disc,
            "isup_sugerido_por_grau": [sug.get(i, 0) for i in range(K)],
            "isup_sugerido_igual_real": f"{sum(v['sugerido'] == v['real'] for v in docs.values())}/{len(docs)}",
            "regioes_gat_no_cancer_2_de_3": f"{ok}/{n}", "esperado_por_acaso": round(float(np.mean(acaso)), 3),
            "antes_abmil": "190/250"}
    (pasta / "campos_info.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(info, indent=1, ensure_ascii=False))


def etapa_redigir_prostata():
    import sintese
    from aviso_discordancia import instrucoes
    from panda_descritor_prelaudo import extrair_isup
    from tcga_descritor_prelaudo import MODELO
    instr = {"pt": instrucoes("prostata"), "en": apc.INSTRUCOES_EN["prostata"]}
    for lg in ("pt", "en"):
        pasta = SAIDA / "prostata" / lg
        registro = pasta / "registro.json"
        feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
        for k, sug, base in documentos_prostata():
            if k in feito:
                continue
            campos = (pasta / f"{k}_campos.txt").read_text(encoding="utf-8")
            t0 = time.time()
            bruto = sintese.chamar(MODELO, campos, [], instrucoes=instr[lg], lembrete="")["message"]["content"]
            (pasta / f"{k}_modelo.md").write_text(bruto, encoding="utf-8")
            final, ta, tr = colar_tudo("prostata", lg, sug, base, bruto)
            (pasta / f"{k}.md").write_text(final, encoding="utf-8")
            ext = extrair_isup(final) if lg == "pt" else apc.extrair_en("prostata", final)
            feito[k] = {"sugerido": sug, "extraido": ext, "modelo_escreveu_avisos": ta, "modelo_escreveu_regioes": tr,
                        "segundos": round(time.time() - t0, 1)}
            registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {lg} {k[:12]}: sugerido {sug} | extraído {ext} ({feito[k]['segundos']} s)", flush=True)


def etapa_checar_prostata():
    resumo = {"campos": json.loads((SAIDA / "prostata" / "campos_info.json").read_text(encoding="utf-8"))}
    for lg in ("pt", "en"):
        pasta = SAIDA / "prostata" / lg
        feito = json.loads((pasta / "registro.json").read_text(encoding="utf-8"))
        med, med_bruto = {}, {}
        for k, sug, base in documentos_prostata():
            evid = (pasta / f"{k}_campos.txt").read_text(encoding="utf-8")
            med[k] = apc.medir("prostata", lg, sug, base, (pasta / f"{k}.md").read_text(encoding="utf-8"), evid)
            med_bruto[k] = apc.medir("prostata", lg, sug, base, (pasta / f"{k}_modelo.md").read_text(encoding="utf-8"), evid)
        concorda = sum(v["extraido"] == v["sugerido"] for v in feito.values())
        r = resumir(med, med_bruto, concorda, len(feito),
                    {"modelo_escreveu_avisos": f"{sum(v['modelo_escreveu_avisos'] for v in feito.values())}/{len(feito)}",
                     "modelo_escreveu_regioes": f"{sum(v['modelo_escreveu_regioes'] for v in feito.values())}/{len(feito)}",
                     "segundos_medio": round(float(np.mean([v["segundos"] for v in feito.values()])), 1),
                     "por_documento": {k: {**med[k], **feito[k]} for k in med}})
        r["criterio_F2"] = r["classe_ok"] and r["condicoes"]
        resumo[lg] = r
        print(lg, json.dumps({a: b for a, b in r.items() if a != "por_documento"}, indent=1, ensure_ascii=False))
        print(f"próstata {lg}: F2 {'SIM' if r['criterio_F2'] else 'NÃO'}", flush=True)
    (SAIDA / "resumo_prostata.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    etapas = {"pulmao": etapa_pulmao, "gat": etapa_gat, "campos_prostata": etapa_campos_prostata,
              "redigir_prostata": etapa_redigir_prostata, "checar_prostata": etapa_checar_prostata}
    p.add_argument("--etapa", choices=list(etapas), required=True)
    etapas[p.parse_args().etapa]()
