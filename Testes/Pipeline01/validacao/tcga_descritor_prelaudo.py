"""
Pulmão (TCGA LUAD × LUSC): descritor por patch e pré-laudo, como na mama (prelaudo_mil.py). O tcga_mil.py só testou a
classe da lâmina; aqui entram a atenção do MIL, a descrição de cada região (pulmao_descritor.py, treinado no
LungHist700) e o texto do modelo de linguagem.

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas: as 78 de teste de tcga_mil.py (as lâminas de treino do MIL não entram).
  Etapa atencao: o MIL de tcga_mil.py é treinado de novo, mesmas lâminas, sementes e hiperparâmetros, agora guardando
     a atenção de cada patch (média das 5 sementes). A classe usada no pré-laudo é a desta rodada; a concordância
     com a rodada de tcga_mil.py é reportada.
  Etapa descrever: descritor final de pulmao_descritor.py (treinado uma vez nos 45 pacientes do LungHist700) aplicado aos
     2.000 patches de cada lâmina. Regiões: os 3 patches de maior atenção, com centros a >= 192 µm um do outro
     (o mesmo filtro de diversidade do roteador, em µm, porque as lâminas têm 20x e 40x).
     Critério D2: a classe do descritor (normal, adenocarcinoma, escamoso) na maioria das 3 regiões (>= 2) é a
     classe real da lâmina (LUAD -> adenocarcinoma; LUSC -> escamoso) em >= 80% das 78 lâminas.
     Também reportado (sem critério): AUC por lâmina só com o descritor, média de P(escamoso) / (P(adeno) +
     P(escamoso)) nos 2.000 patches; fração de patches descritos como normal.
  Etapas campos, redigir, checar: como prelaudo_mil.py. Campos: classe e probabilidades do MIL, confiança (alta
     >= 0,70, moderada >= 0,50), proporção de cada classe do descritor nos patches, as 3 regiões com coordenadas
     (px do nível 0), classe e probabilidade do descritor. Modelo: Gemma 3 4B (Ollama), instruções de redação
     abaixo (as da mama, adaptadas ao pulmão, mais um pedido: apontar regiões que discordam da classe sugerida).
     Classe extraída do texto por uma segunda chamada em JSON restrito (adenocarcinoma / carcinoma escamoso).
     Critério P: classe extraída = classe do MIL em >= 90% dos textos E nenhum número sem sustentação E nenhuma
     coordenada inventada (checagem de prelaudo_campos.checar_texto).
     Também reportado (sem critério): nas lâminas em que alguma região discorda da classe sugerida, quantos textos
     apontam a discordância (expressões como "discord", "no entanto", "embora", "diverg", "contradi").
  Limites conhecidos: o descritor só tem 3 classes (estroma, necrose e inflamação caem numa delas); o LungHist700 é
     de um hospital e de câmera de microscópio, não de lâmina escaneada; não há anotação de região no TCGA.

Uso (venv do projeto; a etapa redigir precisa do servidor Ollama no ar):
    .venv/bin/python validacao/tcga_descritor_prelaudo.py --etapa atencao
    .venv/bin/python validacao/tcga_descritor_prelaudo.py --etapa descrever
    .venv/bin/python validacao/tcga_descritor_prelaudo.py --etapa campos
    .venv/bin/python validacao/tcga_descritor_prelaudo.py --etapa redigir
    .venv/bin/python validacao/tcga_descritor_prelaudo.py --etapa checar
"""

import argparse
import csv
import json
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

MODELO = "gemma3:4b"
N_REGIOES = 3
DIST_MIN_UM = 192.0
D2_MIN = 0.80
CONCORDA_MIN = 0.90
PASTA = RESULTADOS_DIR / "tcga_pulmao"
SAIDA = RESULTADOS_DIR / "tcga_prelaudo"
CLASSE_LAMINA = {"TCGA-LUAD": "aca", "TCGA-LUSC": "scc"}
NOME_MIL = {"TCGA-LUAD": "adenocarcinoma", "TCGA-LUSC": "carcinoma escamoso"}
EXPRESSOES_DISCORDANCIA = ("discord", "no entanto", "embora", "diverg", "contradi", "porém", "entretanto")

INSTRUCOES_PULMAO = """Você redige um RASCUNHO de pré-laudo histopatológico de pulmão (carcinoma de pulmão de não pequenas células), para revisão por um patologista.

O tipo histológico JÁ FOI DECIDIDO por um classificador automático da lâmina inteira, entre adenocarcinoma e carcinoma escamoso. Você NÃO decide nem muda o tipo: seu papel é redigir um texto claro e fiel aos campos recebidos:
- tipo sugerido pelo classificador, com as probabilidades dos 2 tipos e o grau de confiança;
- proporção de cada classe entre os patches de tecido da lâmina (cada patch é um quadrado de 128 µm), segundo um descritor treinado em outro conjunto de imagens;
- regiões que mais pesaram na decisão: coordenadas [x,y] de patches, com a classe e a probabilidade dadas pelo descritor.

Regras:
1. Use apenas os números e as coordenadas fornecidos, sem arredondar de outro jeito e sem inventar outros.
2. Não descreva achados morfológicos que não estejam nos campos.
3. A impressão diagnóstica deve ser o tipo sugerido, com o grau de confiança informado.
4. Se a confiança for baixa ou as proporções forem mistas, diga isso.
5. Se alguma região que mais pesou na decisão for descrita com uma classe diferente do tipo sugerido, aponte essa discordância.
6. Escreva em português, de forma objetiva.

Responda nesta estrutura:
## Resumo da evidência
## Impressão diagnóstica sugerida
## Regiões para revisão prioritária
## Limitações
(inclua que o texto foi gerado automaticamente e precisa de confirmação por patologista)"""


def laminas_teste():
    from tcga_mil import LISTA
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    return [l for l in linhas if l["conjunto"] == "teste" and (PASTA / l["file_id"] / "meta.json").exists()]


def etapa_atencao():
    import torch
    from mil_atencao import SEMENTES, treinar
    from tcga_mil import CLASSES, LISTA
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    prontas = [l for l in linhas if (PASTA / l["file_id"] / "meta.json").exists()]
    tr = [l for l in prontas if l["conjunto"] == "treino"]
    te = [l for l in prontas if l["conjunto"] == "teste"]
    X = {l["file_id"]: torch.from_numpy(np.load(PASTA / l["file_id"] / "amostra2000.npy")) for l in prontas}
    y = {l["file_id"]: CLASSES.index(l["projeto"]) for l in prontas}
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    p = {l["file_id"]: 0.0 for l in te}
    att = {l["file_id"]: np.zeros(len(X[l["file_id"]])) for l in te}
    for semente in SEMENTES:
        modelo = treinar([X[l["file_id"]] for l in tr], np.array([y[l["file_id"]] for l in tr]), semente, dispositivo, k=2)
        modelo.eval()
        with torch.no_grad():
            for l in te:
                logit, a = modelo(X[l["file_id"]].to(dispositivo))
                p[l["file_id"]] += float(torch.softmax(logit, 0)[1]) / len(SEMENTES)
                att[l["file_id"]] += a.cpu().numpy() / len(SEMENTES)
        print(f"  semente {semente} pronta", flush=True)
    for l in te:
        np.save(SAIDA / f"{l['file_id']}_atencao.npy", att[l["file_id"]].astype(np.float32))
    antes = json.loads((RESULTADOS_DIR / "tcga_mil" / "resumo.json").read_text(encoding="utf-8"))["por_lamina"]
    mil = {l["file_id"]: {"arquivo": l["file_name"], "real": l["projeto"], "p_lusc": round(p[l["file_id"]], 4),
                          "predito": CLASSES[int(p[l["file_id"]] >= 0.5)]} for l in te}
    mesma = sum((antes[m["arquivo"]]["p_lusc"] >= 0.5) == (m["p_lusc"] >= 0.5) for m in mil.values())
    dif = max(abs(antes[m["arquivo"]]["p_lusc"] - m["p_lusc"]) for m in mil.values())
    (SAIDA / "mil.json").write_text(json.dumps({"mesma_classe_que_tcga_mil": f"{mesma}/{len(mil)}",
                                                "maior_diferenca_p_lusc": round(dif, 4), "por_lamina": mil},
                                               indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"classe igual à de tcga_mil.py em {mesma}/{len(mil)}; maior diferença em P(LUSC): {dif:.4f}")


def gate_um(cands, mpp, k):
    aceitos = []
    for d in cands:
        if all(((d["cx"] - a["cx"]) ** 2 + (d["cy"] - a["cy"]) ** 2) ** 0.5 * mpp >= DIST_MIN_UM for a in aceitos):
            aceitos.append(d)
            if len(aceitos) >= k:
                break
    return aceitos


def patches(l):
    """Patches de uma lâmina com a classe do descritor e a atenção."""
    meta = json.loads((PASTA / l["file_id"] / "meta.json").read_text(encoding="utf-8"))
    xy = np.loadtxt(PASTA / l["file_id"] / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=int).reshape(-1, 2)
    P = np.load(SAIDA / f"{l['file_id']}_descritor.npy")
    att = np.load(SAIDA / f"{l['file_id']}_atencao.npy")
    from pulmao_descritor import CLASSES
    lado = meta["lado_px"]
    return meta, [{"x0": int(x), "y0": int(y), "cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a),
                   "classe": CLASSES[int(p.argmax())], "prob": float(p.max()), "p": p}
                  for (x, y), p, a in zip(xy, P, att)]


def etapa_descrever():
    from mil_atencao import auc
    from pulmao_descritor import aplicar_todos
    te = laminas_teste()
    for l, P in zip(te, aplicar_todos([np.load(PASTA / l["file_id"] / "amostra2000.npy") for l in te])):
        np.save(SAIDA / f"{l['file_id']}_descritor.npy", P.astype(np.float32))
    por, acertos, r, normal = {}, 0, {}, []
    for l in te:
        meta, ps = patches(l)
        reg = gate_um(sorted(ps, key=lambda d: -d["atencao"]), meta["mpp"], N_REGIOES)
        maioria = Counter(d["classe"] for d in reg).most_common(1)[0]
        ok = maioria[1] >= 2 and maioria[0] == CLASSE_LAMINA[l["projeto"]]
        acertos += ok
        P = np.stack([d["p"] for d in ps])
        r[l["file_id"]] = float(np.mean(P[:, 2] / (P[:, 1] + P[:, 2])))
        normal.append(float(np.mean(P.argmax(1) == 0)))
        por[l["file_name"]] = {"real": l["projeto"], "regioes": [d["classe"] for d in reg], "ok": bool(ok),
                               "fracoes": {c: round(float(np.mean(P.argmax(1) == i)), 3) for i, c in enumerate(["nor", "aca", "scc"])}}
    auc_d = auc([r[l["file_id"]] for l in te if l["projeto"] == "TCGA-LUSC"], [r[l["file_id"]] for l in te if l["projeto"] == "TCGA-LUAD"])
    resumo = {"n": len(te), "regioes_concordam": f"{acertos}/{len(te)}", "fracao": round(acertos / len(te), 3),
              "por_classe": {c: f"{sum(v['ok'] for v in por.values() if v['real'] == c)}/{sum(v['real'] == c for v in por.values())}"
                             for c in CLASSE_LAMINA},
              "auc_so_descritor": round(auc_d, 3), "fracao_media_normal": round(float(np.mean(normal)), 3), "por_lamina": por}
    resumo["criterio_D2"] = resumo["fracao"] >= D2_MIN
    (SAIDA / "descritor.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_lamina"}, indent=2, ensure_ascii=False))
    print(f"Critério D2 fixado antes (maioria das 3 regiões na classe real em >= {D2_MIN:.0%} das lâminas): {'SIM' if resumo['criterio_D2'] else 'NÃO'}")


def etapa_campos():
    from prelaudo_campos import confianca
    from pulmao_descritor import CLASSES, NOME_PT
    mil = json.loads((SAIDA / "mil.json").read_text(encoding="utf-8"))["por_lamina"]
    for l in laminas_teste():
        m = mil[l["file_id"]]
        probs = {"adenocarcinoma": 1 - m["p_lusc"], "carcinoma escamoso": m["p_lusc"]}
        nome = NOME_MIL[m["predito"]]
        meta, ps = patches(l)
        reg = gate_um(sorted(ps, key=lambda d: -d["atencao"]), meta["mpp"], N_REGIOES)
        n, cont = len(ps), Counter(d["classe"] for d in ps)
        linhas = ["=== Campos para o pré-laudo ===", f"Lâmina: {l['file_name'][:12]}",
                  f"Tipo sugerido pelo classificador da lâmina: {nome}",
                  "Probabilidades do classificador: " + ", ".join(f"{k} {v:.2f}" for k, v in probs.items()),
                  f"Confiança: {confianca(probs[nome])} (probabilidade do tipo sugerido {probs[nome]:.2f})",
                  f"Proporção entre os {n} patches de tecido sorteados da lâmina (classe de cada patch pelo descritor):"]
        linhas += [f"  - {NOME_PT[c]}: {cont.get(c, 0)} patches ({100 * cont.get(c, 0) / n:.1f}%)" for c in CLASSES]
        linhas += ["Regiões que mais pesaram na decisão do classificador (classe de cada patch pelo descritor):"]
        linhas += [f"  [{d['x0']},{d['y0']}] {NOME_PT[d['classe']]} {d['prob']:.2f}" for d in reg]
        (SAIDA / f"{l['file_id']}_campos.txt").write_text("\n".join(linhas), encoding="utf-8")
    print(f"campos em {SAIDA}")


def classificar_texto(texto):
    import sintese
    formato = {"type": "object", "properties": {"tipo": {"type": "string", "enum": ["adenocarcinoma", "carcinoma escamoso"]}},
               "required": ["tipo"]}
    corpo = {"model": MODELO, "stream": False, "format": formato, "options": sintese.OPCOES,
             "messages": [{"role": "user", "content": "Abaixo está um pré-laudo histopatológico de pulmão. Qual é o tipo "
                           "histológico final que ele sugere? Responda só com o JSON.\n\n" + texto}]}
    req = urllib.request.Request(sintese.OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(json.loads(r.read())["message"]["content"])["tipo"]


def etapa_redigir():
    import sintese
    mil = json.loads((SAIDA / "mil.json").read_text(encoding="utf-8"))["por_lamina"]
    registro = SAIDA / "registro.json"
    feito = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
    for l in laminas_teste():
        if l["file_id"] in feito:
            continue
        campos = (SAIDA / f"{l['file_id']}_campos.txt").read_text(encoding="utf-8")
        t0 = time.time()
        texto = sintese.chamar(MODELO, campos, [], instrucoes=INSTRUCOES_PULMAO, lembrete="")["message"]["content"]
        (SAIDA / f"{l['file_id']}.md").write_text(texto, encoding="utf-8")
        feito[l["file_id"]] = {"arquivo": l["file_name"], "tipo_sugerido": NOME_MIL[mil[l["file_id"]]["predito"]],
                               "tipo_extraido": classificar_texto(texto), "segundos": round(time.time() - t0, 1)}
        registro.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  {l['file_name'][:12]}: sugerido {feito[l['file_id']]['tipo_sugerido']} | extraído "
              f"{feito[l['file_id']]['tipo_extraido']} ({feito[l['file_id']]['segundos']} s)", flush=True)


def etapa_checar():
    from prelaudo_campos import checar_texto
    from pulmao_descritor import NOME_PT
    feito = json.loads((SAIDA / "registro.json").read_text(encoding="utf-8"))
    mil = json.loads((SAIDA / "mil.json").read_text(encoding="utf-8"))["por_lamina"]
    te = [l for l in laminas_teste() if l["file_id"] in feito]
    ch, discordantes, apontadas = {}, 0, 0
    for l in te:
        texto = (SAIDA / f"{l['file_id']}.md").read_text(encoding="utf-8")
        campos = (SAIDA / f"{l['file_id']}_campos.txt").read_text(encoding="utf-8")
        ch[l["file_id"]] = checar_texto(texto, campos)
        regioes = re.findall(r"^\s+\[\d+,\d+\] (.+?) [\d.]+$", campos, flags=re.M)
        if any(c != feito[l["file_id"]]["tipo_sugerido"] for c in regioes):
            discordantes += 1
            apontadas += any(e in texto.lower() for e in EXPRESSOES_DISCORDANCIA)
    n = sum(c["numeros_checados"] for c in ch.values())
    ns = sum(len(c["nao_sustentados"]) for c in ch.values())
    ci = sum(len(c["coordenadas_inventadas"]) for c in ch.values())
    concorda = sum(feito[k]["tipo_extraido"] == feito[k]["tipo_sugerido"] for k in ch)
    certos = sum(mil[l["file_id"]]["predito"] == l["projeto"] for l in te)
    resumo = {"n": len(te), "tipo_extraido_igual_sugerido": f"{concorda}/{len(te)}", "fracao_concorda": round(concorda / len(te), 3),
              "numeros_checados": n, "nao_sustentados": ns, "coordenadas": sum(c["coordenadas"] for c in ch.values()),
              "coordenadas_inventadas": ci, "tipo_final_certo": f"{certos}/{len(te)}",
              "laminas_com_regiao_discordante": discordantes, "textos_que_apontam_a_discordancia": apontadas,
              "segundos_medio": round(float(np.mean([feito[k]["segundos"] for k in ch])), 1),
              "por_lamina": {feito[k]["arquivo"]: {**ch[k], **feito[k]} for k in ch}}
    resumo["criterio_P"] = resumo["fracao_concorda"] >= CONCORDA_MIN and ns == 0 and ci == 0
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "por_lamina"}, indent=2, ensure_ascii=False))
    print(f"Critério P fixado antes (tipo igual em >= 90%, 0 números sem sustentação, 0 coordenadas inventadas): "
          f"{'SIM' if resumo['criterio_P'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["atencao", "descrever", "campos", "redigir", "checar"], required=True)
    a = p.parse_args()
    {"atencao": etapa_atencao, "descrever": etapa_descrever, "campos": etapa_campos,
     "redigir": etapa_redigir, "checar": etapa_checar}[a.etapa]()
