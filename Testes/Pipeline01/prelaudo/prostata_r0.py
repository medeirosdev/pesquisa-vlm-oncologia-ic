"""
Reexecução de ponta a ponta da próstata com um modelo único (crítica 4): o GAT-MIL padronizado da execução 0
(sementes 0–4) de panda_repeticoes.py (resultados/panda_repeticoes/gat_padronizado_r0.json e <id>_atencao.npy;
kappa 0,621, 30 erros câncer × benigno).

Antes: as tabelas de aviso contra linhas de base, calibração e aviso por grau usavam a execução 0 (kappa 0,621, 30
erros), enquanto os pré-laudos, aviso × erro e células nas regiões usavam uma execução anterior do mesmo modelo
(prelaudo_final/prostata_gat, kappa 0,570, 35 erros). Aqui refazemos todas essas etapas com o modelo r0, gravando em
pastas novas com sufixo _r0 para não apagar os resultados anteriores.

Fixado ANTES de rodar (commit anterior aos resultados):
  Modelo único: resultados/panda_repeticoes/gat_padronizado_r0.json (probabilidades e ISUP previsto) e
     resultados/panda_repeticoes/<image_id>_atencao.npy (atenção média das 5 sementes).
  Etapas e critérios (os mesmos critérios originais, recalculados):
     1. campos + aviso_erro (resultados/prelaudo_final_r0/ e resultados/aviso_erro_r0/):
        - mesmas 60 biópsias de pré-laudo (panda_descritor_prelaudo.biopsias_prelaudo, 10 por ISUP real), mesmo
          descritor (panda_prelaudo/<id>_descritor.npy), 3 regiões de maior atenção de r0 (>= 192 µm);
        - aviso × erro nas 300 biópsias (câncer × benigno): critério E (taxa de erro maior com aviso, Fisher unilateral
          p < 0,05).
     2. celulas (resultados/celulas_regioes_r0/):
        - mesmas regras de celulas_regioes.py nas 3 regiões de maior atenção de r0 (300 biópsias, 900 regiões);
          regiões cujo centro (image_id, cx, cy, mpp) coincide exatamente com uma região já segmentada em
          resultados/celulas_regioes/nucleos.json reaproveitam o resultado determinístico do CellViT, e as demais
          passam pelo mesmo CellViT-256 x40;
        - critério N: AUC câncer × benigno da fração de núcleos neoplásicos >= 0,70, limite inferior do IC 95% > 0,5.
     3. prelaudo_final (resultados/prelaudo_final_r0/):
        - Gemma 3 4B (pt e en) com avisos e regiões colados por código (mesmas instruções de prelaudo_final.py);
        - critério F2 (pt e en): classe extraída = sugerida em >= 90%, 0 trocas de classe, 0 avisos em região
          concordante, todas as regiões discordantes na seção, 0 números sem sustentação, 0 coordenadas inventadas;
        - critério C (extracao_codigo): classe lida por código na impressão = sugerida em >= 90%.
     4. secoes_por_codigo (resultados/secoes_por_codigo_r0/):
        - braço T (template) e braço M (seções críticas montadas pelo código; Gemma 3 4B e Llama 3.2 3B escrevem só o
          parágrafo de resumo, pt e en, temperatura 0,2, semente 0);
        - critério Q (4 casos da próstata: Gemma/Llama × pt/en): no parágrafo livre, 0 números sem sustentação, 0
          coordenadas inventadas, 0 classes trocadas, 0 avisos em região concordante e classe lida = sugerida em 100%.

Uso:
    .venv/bin/python prelaudo/prostata_r0.py --etapa campos
    .venv/bin/python prelaudo/prostata_r0.py --etapa aviso_erro
    .venv/bin/python prelaudo/prostata_r0.py --etapa celulas_regioes
    "<HD>/venvs/cellvit/bin/python" prelaudo/prostata_r0.py --etapa celulas_cellvit
    .venv/bin/python prelaudo/prostata_r0.py --etapa celulas_avaliar
    .venv/bin/python prelaudo/prostata_r0.py --etapa redigir_prelaudo_final       # Ollama no ar
    .venv/bin/python prelaudo/prostata_r0.py --etapa checar_prelaudo_final
    .venv/bin/python prelaudo/prostata_r0.py --etapa secoes_template
    .venv/bin/python prelaudo/prostata_r0.py --etapa secoes_redigir --modelo gemma3:4b
    .venv/bin/python prelaudo/prostata_r0.py --etapa secoes_redigir --modelo llama3.2:3b
    .venv/bin/python prelaudo/prostata_r0.py --etapa secoes_checar
"""

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

PASTA_R0 = RESULTADOS_DIR / "panda_repeticoes"
SAIDA_FINAL = RESULTADOS_DIR / "prelaudo_final_r0"
SAIDA_AVISO_ERRO = RESULTADOS_DIR / "aviso_erro_r0"
SAIDA_CELULAS = RESULTADOS_DIR / "celulas_regioes_r0"
SAIDA_SECOES = RESULTADOS_DIR / "secoes_por_codigo_r0"
K = 6


def regioes_r0(l):
    from panda_descritor_prelaudo import CLASSES, N_REGIOES, SAIDA as SAIDA_PANDA, carregar
    from tcga_descritor_prelaudo import gate_um
    meta, xy, fr = carregar(l)
    P = np.load(SAIDA_PANDA / f"{l['image_id']}_descritor.npy")
    att = np.load(PASTA_R0 / f"{l['image_id']}_atencao.npy")
    lado = meta["lado_px"]
    ps = [{"i": i, "x0": int(x), "y0": int(y), "cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a),
           "classe": CLASSES[int(p.argmax())], "prob": float(p.max())} for i, ((x, y), p, a) in enumerate(zip(xy, P, att))]
    return fr, ps, gate_um(sorted(ps, key=lambda d: -d["atencao"]), meta["mpp"], N_REGIOES)


def documentos_prostata_r0():
    reg = json.loads((SAIDA_FINAL / "prostata" / "documentos.json").read_text(encoding="utf-8"))
    return [(k, v["sugerido"], (SAIDA_FINAL / "prostata" / f"{k}_campos_base.txt").read_text(encoding="utf-8"))
            for k, v in reg.items()]


# ---------------------------------------------------------------- 1. campos + aviso_erro

def etapa_campos():
    import avisos_por_codigo as apc
    from aviso_discordancia import discordantes, linha_aviso
    from panda_descritor_prelaudo import biopsias_prelaudo, no_cancer
    from panda_mil import biopsias
    from prelaudo_final import campos_pt_prostata

    r0 = json.loads((PASTA_R0 / "gat_padronizado_r0.json").read_text(encoding="utf-8"))
    pasta = SAIDA_FINAL / "prostata"
    for lg in ("pt", "en"):
        (pasta / lg).mkdir(parents=True, exist_ok=True)
    docs, n_disc = {}, 0
    for l in biopsias_prelaudo():
        k, m = l["image_id"], r0[l["image_id"]]
        g, probs = m["previsto"], m["probs"]
        _, ps, reg = regioes_r0(l)
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

    _, prontas = biopsias()
    ok = n = 0
    acaso = []
    for l in prontas:
        if l["conjunto"] != "teste" or int(l["isup_grade"]) < 1:
            continue
        fr, _, reg = regioes_r0(l)
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
            "modelo": "panda_repeticoes/gat_padronizado_r0"}
    (pasta / "campos_info.json").write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(info, indent=1, ensure_ascii=False))


def etapa_aviso_erro():
    from aviso_discordancia import discordantes
    from aviso_erro import CONF_ALTA, P_MAX, comparar
    from panda_descritor_prelaudo import NOME_PT
    from panda_mil import biopsias

    SAIDA_AVISO_ERRO.mkdir(parents=True, exist_ok=True)
    r0 = json.loads((PASTA_R0 / "gat_padronizado_r0.json").read_text(encoding="utf-8"))
    _, prontas = biopsias()
    aviso, erro_cb, erro_exato, erro_2, conf = [], [], [], [], []
    for l in prontas:
        if l["conjunto"] != "teste":
            continue
        m = r0[l["image_id"]]
        g, real = m["previsto"], int(l["isup_grade"])
        _, _, reg = regioes_r0(l)
        campos = "\n".join(f"  [{d['x0']},{d['y0']}] {NOME_PT[d['classe']]} {d['prob']:.2f}" for d in reg)
        aviso.append(bool(discordantes("prostata", g, campos)))
        erro_cb.append((g == 0) != (real == 0))
        erro_exato.append(g != real)
        erro_2.append(abs(g - real) >= 2)
        conf.append(m["probs"][g] >= CONF_ALTA)
    out = comparar(aviso, erro_cb, conf)
    out["erro_isup_exato"] = comparar(aviso, erro_exato, conf)
    out["erro_2_ou_mais_graus"] = comparar(aviso, erro_2, conf)
    a = out["aviso"]
    out["criterio_E"] = bool(a["taxa_erro_com_sinal"] > a["taxa_erro_sem_sinal"] and a["fisher_p_unilateral"] < P_MAX)
    resumo = {"prostata": out}
    (SAIDA_AVISO_ERRO / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"próstata r0: n {out['n']}, com aviso {out['com_aviso']}, erros {out['erros']} | "
          f"com aviso {a['taxa_erro_com_sinal']} sem aviso {a['taxa_erro_sem_sinal']} | "
          f"RR {a['risco_relativo']} {a['ic95_risco_relativo']} | p {a['fisher_p_unilateral']} | "
          f"E {'SIM' if out['criterio_E'] else 'NÃO'}")


# ---------------------------------------------------------------- 2. células nas regiões (CellViT)

def etapa_celulas_regioes():
    from panda_descritor_prelaudo import biopsias_prelaudo, rotulo_karolinska
    from panda_mil import biopsias

    SAIDA_CELULAS.mkdir(parents=True, exist_ok=True)
    laudo = {l["image_id"] for l in biopsias_prelaudo()}
    _, prontas = biopsias()
    out = []
    for l in prontas:
        if l["conjunto"] != "teste":
            continue
        meta = json.loads((RESULTADOS_DIR / "panda" / l["image_id"] / "meta.json").read_text(encoding="utf-8"))
        if not meta.get("mascara"):
            continue
        fr, _, reg = regioes_r0(l)
        for k, d in enumerate(reg):
            r = rotulo_karolinska(fr[d["i"]]) if fr is not None else None
            out.append({"image_id": l["image_id"], "isup": int(l["isup_grade"]), "no_laudo": l["image_id"] in laudo,
                        "ordem": k + 1, "cx": float(d["cx"]), "cy": float(d["cy"]), "mpp": meta["mpp"],
                        "classe_descritor": d["classe"], "mascara": {1: "cancer", 0: "benigno", None: "fora"}[r]})
    (SAIDA_CELULAS / "regioes.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    antigo_p = RESULTADOS_DIR / "celulas_regioes" / "regioes.json"
    reuso = 0
    if antigo_p.exists():
        ant_set = {(r["image_id"], round(r["cx"], 2), round(r["cy"], 2), r["mpp"])
                   for r in json.loads(antigo_p.read_text(encoding="utf-8"))}
        reuso = sum((r["image_id"], round(r["cx"], 2), round(r["cy"], 2), r["mpp"]) in ant_set for r in out)
    print(f"{len(out)} regiões r0; câncer {sum(r['mascara'] == 'cancer' for r in out)}, "
          f"benigno {sum(r['mascara'] == 'benigno' for r in out)}; idênticas à rodada anterior: {reuso}/{len(out)}")


def etapa_celulas_cellvit():
    import cv2
    import torch
    from celulas_regioes import JANELA_PX, JANELA_UM, MPP_CELLVIT, REG_FIM, REG_INI, TIPOS
    from comum.lamina import Lamina, raiz_hd
    from nucleos_cellvit import carregar_modelo, segmentar

    pasta_panda = Path(raiz_hd()) / "Dados Gerais" / "PANDA"
    regs = json.loads((SAIDA_CELULAS / "regioes.json").read_text(encoding="utf-8"))
    arq = SAIDA_CELULAS / "nucleos.json"
    feito = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}

    # Reaproveita regiões com coordenadas exatamente idênticas da execução anterior (determinístico)
    ant_reg_p = RESULTADOS_DIR / "celulas_regioes" / "regioes.json"
    ant_nuc_p = RESULTADOS_DIR / "celulas_regioes" / "nucleos.json"
    cache = {}
    if ant_reg_p.exists() and ant_nuc_p.exists():
        ant_nuc = json.loads(ant_nuc_p.read_text(encoding="utf-8"))
        for r in json.loads(ant_reg_p.read_text(encoding="utf-8")):
            ch_ant = f"{r['image_id']}_{r['ordem']}"
            if ch_ant in ant_nuc:
                cache[(r["image_id"], round(r["cx"], 2), round(r["cy"], 2), r["mpp"])] = ant_nuc[ch_ant]

    reaprov = 0
    for r in regs:
        chave = f"{r['image_id']}_{r['ordem']}"
        if chave in feito:
            continue
        hit = cache.get((r["image_id"], round(r["cx"], 2), round(r["cy"], 2), r["mpp"]))
        if hit is not None:
            feito[chave] = hit
            reaprov += 1
    pendentes = [r for r in regs if f"{r['image_id']}_{r['ordem']}" not in feito]
    print(f"cellvit r0: {reaprov} reaproveitadas por coordenada exata; {len(pendentes)} a segmentar", flush=True)
    if not pendentes:
        arq.write_text(json.dumps(feito), encoding="utf-8")
        return

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, media, desvio = carregar_modelo(dev)
    abertas = {}
    for idx_p, r in enumerate(pendentes, 1):
        chave = f"{r['image_id']}_{r['ordem']}"
        t0 = time.time()
        if r["image_id"] not in abertas:
            abertas.clear()
            abertas[r["image_id"]] = Lamina(pasta_panda / "train_images" / f"{r['image_id']}.tiff")
        lam = abertas[r["image_id"]]
        lado = int(round(JANELA_UM / r["mpp"]))
        x0, y0 = int(round(r["cx"] - lado / 2)), int(round(r["cy"] - lado / 2))
        img = np.full((lado, lado, 3), 255, np.uint8)
        sx0, sy0 = max(x0, 0), max(y0, 0)
        sx1, sy1 = min(x0 + lado, lam.largura), min(y0 + lado, lam.altura)
        pedaco = lam.janela_nativa(sx0, sy0, tamanho=lado)[: sy1 - sy0, : sx1 - sx0]
        img[sy0 - y0: sy1 - y0, sx0 - x0: sx1 - x0] = pedaco[..., :3]
        img = cv2.resize(img, (JANELA_PX, JANELA_PX), interpolation=cv2.INTER_CUBIC)
        cel = segmentar(modelo, media, desvio, img, dev)
        nuc = []
        for c in cel.values():
            cx, cy = c["centroid"][0], c["centroid"][1]
            if REG_INI <= cx < REG_FIM and REG_INI <= cy < REG_FIM:
                area = float(cv2.contourArea(np.asarray(c["contour"], np.int32))) * MPP_CELLVIT ** 2
                nuc.append({"tipo": TIPOS.get(int(c["type"]), "?"), "area_um2": round(area, 1)})
        feito[chave] = {"nucleos": nuc, "segundos": round(time.time() - t0, 2)}
        if idx_p % 50 == 0 or idx_p == len(pendentes):
            arq.write_text(json.dumps(feito), encoding="utf-8")
            print(f"  {idx_p}/{len(pendentes)} novas ({len(feito)}/{len(regs)} total)", flush=True)


def etapa_celulas_avaliar():
    import celulas_regioes as cr
    antiga = cr.SAIDA
    cr.SAIDA = SAIDA_CELULAS
    try:
        cr.etapa_avaliar()
    finally:
        cr.SAIDA = antiga


# ---------------------------------------------------------------- 3. prelaudo_final (Gemma pt/en, F2 + C)

def etapa_redigir_prelaudo_final():
    import avisos_por_codigo as apc
    import sintese
    from aviso_discordancia import instrucoes
    from panda_descritor_prelaudo import extrair_isup
    from prelaudo_final import colar_tudo
    from tcga_descritor_prelaudo import MODELO

    instr = {"pt": instrucoes("prostata"), "en": apc.INSTRUCOES_EN["prostata"]}
    for lg in ("pt", "en"):
        pasta = SAIDA_FINAL / "prostata" / lg
        registro = pasta / "registro.json"
        feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
        for k, sug, base in documentos_prostata_r0():
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
            print(f"  prelaudo_final_r0 {lg} {k[:12]}: sug {sug} | ext {ext} ({feito[k]['segundos']} s)", flush=True)


def etapa_checar_prelaudo_final():
    import avisos_por_codigo as apc
    from extracao_codigo import CONCORDA_MIN, por_codigo
    from prelaudo_final import resumir

    resumo = {"campos": json.loads((SAIDA_FINAL / "prostata" / "campos_info.json").read_text(encoding="utf-8"))}
    ext_cod = {}
    for lg in ("pt", "en"):
        pasta = SAIDA_FINAL / "prostata" / lg
        feito = json.loads((pasta / "registro.json").read_text(encoding="utf-8"))
        med, med_bruto = {}, {}
        resolvidos = iguais_cod = 0
        for k, sug, base in documentos_prostata_r0():
            evid = (pasta / f"{k}_campos.txt").read_text(encoding="utf-8")
            txt = (pasta / f"{k}.md").read_text(encoding="utf-8")
            med[k] = apc.medir("prostata", lg, sug, base, txt, evid)
            med_bruto[k] = apc.medir("prostata", lg, sug, base, (pasta / f"{k}_modelo.md").read_text(encoding="utf-8"), evid)
            cod = por_codigo("prostata", lg, txt)
            final_c = cod if cod is not None else feito[k]["extraido"]
            resolvidos += cod is not None
            iguais_cod += final_c == sug
        concorda = sum(v["extraido"] == v["sugerido"] for v in feito.values())
        r = resumir(med, med_bruto, concorda, len(feito),
                    {"modelo_escreveu_avisos": f"{sum(v['modelo_escreveu_avisos'] for v in feito.values())}/{len(feito)}",
                     "modelo_escreveu_regioes": f"{sum(v['modelo_escreveu_regioes'] for v in feito.values())}/{len(feito)}",
                     "segundos_medio": round(float(np.mean([v["segundos"] for v in feito.values()])), 1),
                     "por_documento": {k: {**med[k], **feito[k]} for k in med}})
        r["criterio_F2"] = r["classe_ok"] and r["condicoes"]
        resumo[lg] = r
        ext_cod[f"prostata_{lg}"] = {
            "n": len(feito),
            "resolvidos_pela_regra": f"{resolvidos}/{len(feito)}",
            "classe_final_igual_sugerida": f"{iguais_cod}/{len(feito)}",
            "criterio_C": iguais_cod / len(feito) >= CONCORDA_MIN,
        }
        print(f"próstata r0 {lg}: F2 {'SIM' if r['criterio_F2'] else 'NÃO'} | C {'SIM' if ext_cod[f'prostata_{lg}']['criterio_C'] else 'NÃO'} "
              f"(classe cod {iguais_cod}/{len(feito)}, modelo {concorda}/{len(feito)})", flush=True)
    (SAIDA_FINAL / "resumo_prostata.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA_FINAL / "extracao_codigo.json").write_text(json.dumps(ext_cod, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- 4. secoes_por_codigo (template + Gemma/Llama pt/en, Q)

def casos_secoes_r0():
    ler = lambda p: p.read_text(encoding="utf-8")  # noqa: E731
    pro = documentos_prostata_r0()
    return {
        ("prostata", "pt"): [(k, s, c, ler(SAIDA_FINAL / "prostata" / "pt" / f"{k}_campos.txt")) for k, s, c in pro],
        ("prostata", "en"): [(k, s, c, ler(SAIDA_FINAL / "prostata" / "en" / f"{k}_campos.txt")) for k, s, c in pro],
    }


def etapa_secoes_template():
    import secoes_por_codigo as spc
    for (orgao, lg), docs in casos_secoes_r0().items():
        pasta = SAIDA_SECOES / "template" / lg / orgao
        pasta.mkdir(parents=True, exist_ok=True)
        for k, sug, base, campos in docs:
            (pasta / f"{k}.md").write_text(spc.montar(orgao, lg, sug, base, campos, spc.resumo_template(campos, lg)),
                                           encoding="utf-8")
    print("template r0 pronto")


def etapa_secoes_redigir(modelo):
    import sintese
    import secoes_por_codigo as spc
    nome = spc.MODELOS[modelo]
    for (orgao, lg), docs in casos_secoes_r0().items():
        pasta = SAIDA_SECOES / nome / lg / orgao
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
            print(f"  secoes_r0 {nome} {lg} {k[:12]} ({feito[k]['segundos']} s)", flush=True)


def etapa_secoes_checar():
    import avisos_por_codigo as apc
    import secoes_por_codigo as spc
    from extracao_codigo import por_codigo

    resumo = {}
    for (orgao, lg), docs in casos_secoes_r0().items():
        pt = SAIDA_SECOES / "template" / lg / orgao
        tm = [apc.medir(orgao, lg, s, b, (pt / f"{k}.md").read_text(encoding="utf-8"), c) for k, s, b, c in docs]
        tcl = sum(por_codigo(orgao, lg, (pt / f"{k}.md").read_text(encoding="utf-8")) == s for k, s, b, c in docs)
        resumo[f"template_{orgao}_{lg}"] = {
            "n": len(docs), "classe_lida_igual": f"{tcl}/{len(docs)}", **apc.somar(dict(enumerate(tm))),
            "palavras_resumo_medio": round(float(np.mean([len(spc.resumo_template(c, lg).split()) for _, _, _, c in docs])), 1),
        }
        for nome in spc.MODELOS.values():
            pasta = SAIDA_SECOES / nome / lg / orgao
            if not (pasta / "registro.json").exists():
                continue
            med, cl = {}, 0
            for k, s, b, c in docs:
                par = (pasta / f"{k}_paragrafo.txt").read_text(encoding="utf-8")
                med[k] = spc.medir_paragrafo(orgao, lg, s, b, c, par)
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
            print(f"secoes_r0 {nome} {lg}: {r} | Q {'SIM' if r['criterio_Q'] else 'NÃO'}", flush=True)
    (SAIDA_SECOES / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=[
        "campos", "aviso_erro", "celulas_regioes", "celulas_cellvit", "celulas_avaliar",
        "redigir_prelaudo_final", "checar_prelaudo_final",
        "secoes_template", "secoes_redigir", "secoes_checar",
    ], required=True)
    p.add_argument("--modelo", choices=["gemma3:4b", "llama3.2:3b"], default="gemma3:4b")
    a = p.parse_args()
    mapa = {
        "campos": etapa_campos,
        "aviso_erro": etapa_aviso_erro,
        "celulas_regioes": etapa_celulas_regioes,
        "celulas_cellvit": etapa_celulas_cellvit,
        "celulas_avaliar": etapa_celulas_avaliar,
        "redigir_prelaudo_final": etapa_redigir_prelaudo_final,
        "checar_prelaudo_final": etapa_checar_prelaudo_final,
        "secoes_template": etapa_secoes_template,
        "secoes_redigir": lambda: etapa_secoes_redigir(a.modelo),
        "secoes_checar": etapa_secoes_checar,
    }
    mapa[a.etapa]()
