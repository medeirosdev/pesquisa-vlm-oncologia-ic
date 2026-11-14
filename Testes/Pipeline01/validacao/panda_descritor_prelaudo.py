"""
PANDA: descritor por patch (padrão de Gleason), regiões de maior atenção do MIL conferidas na máscara e pré-laudo,
como no pulmão (tcga_descritor_prelaudo.py). Diferença principal: aqui há máscara de rótulos, então dá pra saber se a
região de maior atenção é mesmo câncer, e o descritor é treinado em imagens do mesmo tipo (biópsias escaneadas).

Fixado ANTES de rodar (commit anterior aos resultados):
  Descritor: categoria_uni.logistica_multinomial, 4 classes (benigno, Gleason 3, Gleason 4, Gleason 5), treinado nos
     patches das 600 biópsias de treino do Radboud que têm máscara. Rótulo do patch pela máscara (frações de
     panda_baixar_e_embutir.py): precisa de >= 50% da área com rótulo de tecido (valores 1-5); se a fração de câncer
     (3+4+5) entre o tecido rotulado for >= 0,5, a classe é o Gleason de maior fração; se for 0, benigno; no meio,
     o patch fica de fora. Até 60 patches rotulados por biópsia (sorteio, semente 0), pra caber na memória.
  Critério D1 (patches das biópsias de teste do Karolinska com máscara): AUC benigno × câncer >= 0,85, com escore
     1 - P(benigno). Rótulo do patch no Karolinska: >= 50% da área com tecido rotulado (1-2); câncer se a fração de
     câncer (2) entre o tecido rotulado for >= 0,5, benigno se for 0, de fora no meio.
  Critério A (biópsias de teste com ISUP >= 1 e máscara): as 3 regiões de maior atenção do MIL (panda_mil.py; centros
     a >= 192 µm um do outro, como no pulmão); região "no câncer" se tiver >= 50% da área com tecido rotulado e
     fração de câncer >= 0,5 nesse tecido. Passa se >= 2 das 3 regiões estiverem no câncer em >= 80% das biópsias.
     Também reportado (sem critério): o mesmo número esperado por acaso (3 patches de tecido sorteados), e o acerto
     do descritor (câncer × benigno) nessas regiões.
  Pré-laudo: 60 biópsias de teste (10 por ISUP real, sorteio com semente 0). Campos: ISUP sugerido pelo MIL, as 6
     probabilidades, confiança (alta >= 0,70, moderada >= 0,50), proporção de cada classe do descritor nos patches,
     as 3 regiões (coordenadas no nível 0, classe e probabilidade do descritor). Modelo: Gemma 3 4B (Ollama),
     instruções abaixo, com o pedido de apontar regiões que discordam do grau sugerido. ISUP extraído do texto por
     uma segunda chamada em JSON restrito (0-5).
     Critério P: ISUP extraído = ISUP do MIL em >= 90% dos textos E nenhum número sem sustentação E nenhuma
     coordenada inventada (prelaudo_campos.checar_texto).
     Também reportado (sem critério): biópsias com região discordante (ISUP 0 sugerido e região com Gleason, ou
     ISUP >= 1 sugerido e região benigna) e quantos textos apontam a discordância (mesmas expressões do pulmão).
  Limites conhecidos: a máscara do Karolinska só separa benigno de câncer (o Gleason de cada região só pode ser
     conferido no Radboud, que é o treino); origem das máscaras não descrita no artigo principal.

Uso (venv do projeto; a etapa redigir precisa do Ollama no ar; depois de panda_mil.py):
    .venv/bin/python validacao/panda_descritor_prelaudo.py --etapa descrever
    .venv/bin/python validacao/panda_descritor_prelaudo.py --etapa campos
    .venv/bin/python validacao/panda_descritor_prelaudo.py --etapa redigir
    .venv/bin/python validacao/panda_descritor_prelaudo.py --etapa checar
Saída: resultados/panda_prelaudo/
"""

import argparse
import json
import random
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio5_sintese"))

import numpy as np

from comum.lamina import RESULTADOS_DIR
from panda_mil import PASTA, SAIDA as SAIDA_MIL, auc_rank, biopsias
from tcga_descritor_prelaudo import EXPRESSOES_DISCORDANCIA, MODELO, gate_um

CLASSES = ["benigno", "gleason3", "gleason4", "gleason5"]
NOME_PT = {"benigno": "benigno", "gleason3": "Gleason 3", "gleason4": "Gleason 4", "gleason5": "Gleason 5"}
MAX_POR_BIOPSIA = 60
MIN_ROTULADO = 0.5
D1_MIN = 0.85
A_MIN = 0.80
N_REGIOES = 3
N_PRELAUDO_POR_ISUP = 10
CONCORDA_MIN = 0.90
SAIDA = RESULTADOS_DIR / "panda_prelaudo"

INSTRUCOES_PROSTATA = """Você redige um RASCUNHO de pré-laudo histopatológico de biópsia de próstata, para revisão por um patologista.

O grau ISUP (0 = sem câncer; 1 a 5 = grupos de grau do carcinoma) JÁ FOI DECIDIDO por um classificador automático da biópsia inteira. Você NÃO decide nem muda o grau: seu papel é redigir um texto claro e fiel aos campos recebidos:
- grau ISUP sugerido pelo classificador, com as probabilidades dos 6 graus e o grau de confiança;
- proporção de cada classe entre os patches de tecido (cada patch é um quadrado de 128 µm), segundo um descritor treinado em outro centro: benigno, padrão de Gleason 3, 4 ou 5;
- regiões que mais pesaram na decisão: coordenadas [x,y] de patches, com a classe e a probabilidade dadas pelo descritor.

Regras:
1. Use apenas os números e as coordenadas fornecidos, sem arredondar de outro jeito e sem inventar outros.
2. Não descreva achados morfológicos que não estejam nos campos.
3. A impressão diagnóstica deve ser o grau ISUP sugerido, com o grau de confiança informado.
4. Se a confiança for baixa ou as proporções forem mistas, diga isso.
5. Se alguma região que mais pesou na decisão discordar do grau sugerido (por exemplo, região com padrão de Gleason quando o grau sugerido é ISUP 0, ou região benigna quando o grau sugerido é de câncer), aponte essa discordância.
6. Escreva em português, de forma objetiva.

Responda nesta estrutura:
## Resumo da evidência
## Impressão diagnóstica sugerida
## Regiões para revisão prioritária
## Limitações
(inclua que o texto foi gerado automaticamente e precisa de confirmação por patologista)"""


def carregar(l):
    meta = json.loads((PASTA / l["image_id"] / "meta.json").read_text(encoding="utf-8"))
    xy = np.loadtxt(PASTA / l["image_id"] / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=int).reshape(-1, 2)
    f = PASTA / l["image_id"] / "mascara_frac.npy"
    return meta, xy, (np.load(f).astype(np.float32) if f.exists() else None)


def rotulo_radboud(fr):
    tec = fr[1:6].sum()
    if tec < MIN_ROTULADO:
        return None
    fc = fr[3:6].sum() / tec
    if fc >= 0.5:
        return 1 + int(fr[3:6].argmax())
    return 0 if fr[3:6].sum() == 0 else None


def rotulo_karolinska(fr):
    tec = fr[1:3].sum()
    if tec < MIN_ROTULADO:
        return None
    fc = fr[2] / tec
    return 1 if fc >= 0.5 else (0 if fr[2] == 0 else None)


def no_cancer(fr):
    return rotulo_karolinska(fr) == 1


def regioes(l, P):
    meta, xy, fr = carregar(l)
    att = np.load(SAIDA_MIL / f"{l['image_id']}_atencao.npy")
    lado = meta["lado_px"]
    ps = [{"i": i, "x0": int(x), "y0": int(y), "cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a),
           "classe": CLASSES[int(p.argmax())], "prob": float(p.max())} for i, ((x, y), p, a) in enumerate(zip(xy, P, att))]
    return meta, fr, ps, gate_um(sorted(ps, key=lambda d: -d["atencao"]), meta["mpp"], N_REGIOES)


def etapa_descrever():
    from categoria_uni import logistica_multinomial
    SAIDA.mkdir(parents=True, exist_ok=True)
    _, prontas = biopsias()
    tr = [l for l in prontas if l["conjunto"] == "treino"]
    te = [l for l in prontas if l["conjunto"] == "teste"]
    rng, Xtr, ytr, sem_mascara = random.Random(0), [], [], []
    for l in tr:
        _, _, fr = carregar(l)
        if fr is None:
            sem_mascara.append(l["image_id"])
            continue
        X = np.load(PASTA / l["image_id"] / "amostra2000.npy")
        idx = [i for i in range(len(fr)) if rotulo_radboud(fr[i]) is not None]
        for i in sorted(rng.sample(idx, min(MAX_POR_BIOPSIA, len(idx)))):
            Xtr.append(X[i])
            ytr.append(rotulo_radboud(fr[i]))
    Xtr, ytr = np.stack(Xtr), np.array(ytr)
    print(f"treino do descritor: {len(ytr)} patches de {len(tr) - len(sem_mascara)} biópsias; por classe {np.bincount(ytr, minlength=4).tolist()}", flush=True)
    blocos = [np.load(PASTA / l["image_id"] / "amostra2000.npy") for l in te]
    P_all = np.asarray(logistica_multinomial(Xtr, ytr, np.concatenate(blocos), k=4, probabilidades=True))
    Ps = np.split(P_all, np.cumsum([len(b) for b in blocos])[:-1])
    for l, P in zip(te, Ps):
        np.save(SAIDA / f"{l['image_id']}_descritor.npy", P.astype(np.float32))

    pos, neg, a_ok, a_n, acaso, desc_ok, desc_n, por = [], [], 0, 0, [], 0, 0, {}
    te_sem_mascara = []
    for l, P in zip(te, Ps):
        meta, fr, ps, reg = regioes(l, P)
        if fr is None:
            te_sem_mascara.append(l["image_id"])
            continue
        for p, f in zip(P, fr):
            r = rotulo_karolinska(f)
            if r is not None:
                (pos if r == 1 else neg).append(1 - p[0])
        if int(l["isup_grade"]) >= 1:
            dentro = [no_cancer(fr[d["i"]]) for d in reg]
            ok = sum(dentro) >= 2
            a_ok += ok
            a_n += 1
            q = float(np.mean([no_cancer(f) for f in fr]))  # fração de patches de tecido no câncer
            acaso.append(3 * q ** 2 * (1 - q) + q ** 3)  # P(>= 2 de 3 sorteados no câncer)
            for d, dc in zip(reg, dentro):
                rk = rotulo_karolinska(fr[d["i"]])
                if rk is not None:
                    desc_n += 1
                    desc_ok += (d["classe"] != "benigno") == (rk == 1)
            por[l["image_id"]] = {"isup": int(l["isup_grade"]), "regioes_no_cancer": int(sum(dentro)),
                                  "classes_descritor": [d["classe"] for d in reg], "fracao_cancer_tecido": round(q, 3)}
    resumo = {"patches_treino_descritor": int(len(ytr)), "por_classe_treino": np.bincount(ytr, minlength=4).tolist(),
              "treino_sem_mascara": sem_mascara, "teste_sem_mascara": te_sem_mascara,
              "D1_patches_cancer": len(pos), "D1_patches_benignos": len(neg),
              "D1_auc_benigno_x_cancer": round(auc_rank(np.array(pos), np.array(neg)), 3),
              "A_biopsias": a_n, "A_regioes_no_cancer": f"{a_ok}/{a_n}", "A_fracao": round(a_ok / a_n, 3),
              "A_esperado_por_acaso": round(float(np.mean(acaso)), 3),
              "descritor_nas_regioes_concorda_com_mascara": f"{desc_ok}/{desc_n}", "por_biopsia": por}
    resumo["criterio_D1"] = resumo["D1_auc_benigno_x_cancer"] >= D1_MIN
    resumo["criterio_A"] = resumo["A_fracao"] >= A_MIN
    (SAIDA / "descritor.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_biopsia"}, indent=1, ensure_ascii=False))
    print(f"Critério D1 (AUC >= {D1_MIN}): {'SIM' if resumo['criterio_D1'] else 'NÃO'} | "
          f"Critério A (>= 2 de 3 regiões no câncer em >= {A_MIN:.0%}): {'SIM' if resumo['criterio_A'] else 'NÃO'}")


def biopsias_prelaudo():
    _, prontas = biopsias()
    te = sorted([l for l in prontas if l["conjunto"] == "teste"], key=lambda l: l["image_id"])
    rng, saida = random.Random(0), []
    for g in "012345":
        grupo = [l for l in te if l["isup_grade"] == g]
        saida += rng.sample(grupo, min(N_PRELAUDO_POR_ISUP, len(grupo)))
    return saida


def etapa_campos():
    from prelaudo_campos import confianca
    mil = json.loads((SAIDA_MIL / "resumo.json").read_text(encoding="utf-8"))["por_biopsia"]
    for l in biopsias_prelaudo():
        m = mil[l["image_id"]]
        g, probs = m["previsto"], m["probs"]
        P = np.load(SAIDA / f"{l['image_id']}_descritor.npy")
        meta, _, ps, reg = regioes(l, P)
        n, cont = len(ps), Counter(d["classe"] for d in ps)
        linhas = ["=== Campos para o pré-laudo ===", f"Biópsia: {l['image_id'][:8]}",
                  f"Grau ISUP sugerido pelo classificador da biópsia: ISUP {g}" + (" (sem câncer)" if g == 0 else ""),
                  "Probabilidades do classificador: " + ", ".join(f"ISUP {k} {v:.2f}" for k, v in enumerate(probs)),
                  f"Confiança: {confianca(probs[g])} (probabilidade do grau sugerido {probs[g]:.2f})",
                  f"Proporção entre os {n} patches de tecido da biópsia (classe de cada patch pelo descritor):"]
        linhas += [f"  - {NOME_PT[c]}: {cont.get(c, 0)} patches ({100 * cont.get(c, 0) / n:.1f}%)" for c in CLASSES]
        linhas += ["Regiões que mais pesaram na decisão do classificador (classe de cada patch pelo descritor):"]
        linhas += [f"  [{d['x0']},{d['y0']}] {NOME_PT[d['classe']]} {d['prob']:.2f}" for d in reg]
        (SAIDA / f"{l['image_id']}_campos.txt").write_text("\n".join(linhas), encoding="utf-8")
    print(f"campos em {SAIDA}")


def extrair_isup(texto):
    import sintese
    formato = {"type": "object", "properties": {"isup": {"type": "string", "enum": list("012345")}}, "required": ["isup"]}
    corpo = {"model": MODELO, "stream": False, "format": formato, "options": sintese.OPCOES,
             "messages": [{"role": "user", "content": "Abaixo está um pré-laudo de biópsia de próstata. Qual é o grau "
                           "ISUP final que ele sugere (0 a 5)? Responda só com o JSON.\n\n" + texto}]}
    req = urllib.request.Request(sintese.OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return int(json.loads(json.loads(r.read())["message"]["content"])["isup"])


def etapa_redigir():
    import sintese
    mil = json.loads((SAIDA_MIL / "resumo.json").read_text(encoding="utf-8"))["por_biopsia"]
    registro = SAIDA / "registro.json"
    feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
    for l in biopsias_prelaudo():
        if l["image_id"] in feito:
            continue
        campos = (SAIDA / f"{l['image_id']}_campos.txt").read_text(encoding="utf-8")
        t0 = time.time()
        texto = sintese.chamar(MODELO, campos, [], instrucoes=INSTRUCOES_PROSTATA, lembrete="")["message"]["content"]
        (SAIDA / f"{l['image_id']}.md").write_text(texto, encoding="utf-8")
        feito[l["image_id"]] = {"isup_real": int(l["isup_grade"]), "isup_sugerido": mil[l["image_id"]]["previsto"],
                                "isup_extraido": extrair_isup(texto), "segundos": round(time.time() - t0, 1)}
        registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
        f = feito[l["image_id"]]
        print(f"  {l['image_id'][:8]}: sugerido {f['isup_sugerido']} | extraído {f['isup_extraido']} ({f['segundos']} s)", flush=True)


def etapa_checar():
    from prelaudo_campos import checar_texto
    feito = json.loads((SAIDA / "registro.json").read_text(encoding="utf-8"))
    ch, discordantes, apontadas = {}, 0, 0
    for k, v in feito.items():
        texto = (SAIDA / f"{k}.md").read_text(encoding="utf-8")
        campos = (SAIDA / f"{k}_campos.txt").read_text(encoding="utf-8")
        ch[k] = checar_texto(texto, campos)
        classes = re.findall(r"^\s+\[\d+,\d+\] (.+?) [\d.]+$", campos, flags=re.M)
        if any((c != "benigno") if v["isup_sugerido"] == 0 else (c == "benigno") for c in classes):
            discordantes += 1
            apontadas += any(e in texto.lower() for e in EXPRESSOES_DISCORDANCIA)
    ns = sum(len(c["nao_sustentados"]) for c in ch.values())
    ci = sum(len(c["coordenadas_inventadas"]) for c in ch.values())
    concorda = sum(v["isup_extraido"] == v["isup_sugerido"] for v in feito.values())
    resumo = {"n": len(feito), "isup_extraido_igual_sugerido": f"{concorda}/{len(feito)}",
              "fracao_concorda": round(concorda / len(feito), 3),
              "numeros_checados": sum(c["numeros_checados"] for c in ch.values()), "nao_sustentados": ns,
              "coordenadas": sum(c["coordenadas"] for c in ch.values()), "coordenadas_inventadas": ci,
              "isup_final_certo": f"{sum(v['isup_sugerido'] == v['isup_real'] for v in feito.values())}/{len(feito)}",
              "biopsias_com_regiao_discordante": discordantes, "textos_que_apontam_a_discordancia": apontadas,
              "segundos_medio": round(float(np.mean([v["segundos"] for v in feito.values()])), 1),
              "por_biopsia": {k: {**ch[k], **feito[k]} for k in feito}}
    resumo["criterio_P"] = resumo["fracao_concorda"] >= CONCORDA_MIN and ns == 0 and ci == 0
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_biopsia"}, indent=2, ensure_ascii=False))
    print(f"Critério P (ISUP igual em >= 90%, 0 números sem sustentação, 0 coordenadas inventadas): "
          f"{'SIM' if resumo['criterio_P'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["descrever", "campos", "redigir", "checar"], required=True)
    a = p.parse_args()
    {"descrever": etapa_descrever, "campos": etapa_campos, "redigir": etapa_redigir, "checar": etapa_checar}[a.etapa]()
