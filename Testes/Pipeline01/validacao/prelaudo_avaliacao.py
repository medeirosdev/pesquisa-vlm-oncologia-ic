"""
Avaliação sistemática do pré-laudo (pipeline completa) e teste da regra do componente invasivo.

Pipeline: roteador por frases (32 patches) -> descritor hierárquico UNI2-h (treinado nas outras
lâminas) -> agregação (estágio 4) -> Gemma 3 4B via Ollama (estágio 5), com a linha final
"CLASSIFICAÇÃO FINAL: benigno | atípico | DCIS | carcinoma invasivo".

Fixado ANTES de rodar (commit anterior aos resultados):
  - Lâminas: as 18 (16 das duas levas + BRACS_773, BRACS_295). Rótulo real = rótulo da lâmina no
    BRACS (BRACS.xlsx), agrupado: N, PB -> benigno; UDH, FEA, ADH -> atípico; DCIS; IC.
  - Modelo: gemma3:4b (o melhor no teste exploratório de 17/10), temperature 0,2, seed 0.
  - A) Avaliação sistemática: prompt sem a regra (v1), nas 18 lâminas. Descritiva: acertos por
    lâmina e matriz de confusão. Resposta sem a linha final (ou ambígua) conta como erro.
  - B) Regra do componente invasivo (agregador.py, regra_invasivo=True: >= 2 patches com
    invasive carcinoma e P >= 0,90 -> "componente invasivo presente" + a regra de que ele define o
    diagnóstico). Avaliada SÓ nas 15 lâminas que não foram usadas pra criar a regra (fora:
    BRACS_748, BRACS_1489, BRACS_1370, do teste exploratório).
    Critério de "funcionou": nas 15, v2 (com regra) acerta mais lâminas IC que v1 E a acurácia
    total de v2 não é menor que a de v1.

Correção do instrumento (17/10, antes de qualquer resultado diagnóstico ser analisado): na primeira
tentativa, 0 de 9 respostas trouxeram a linha "CLASSIFICAÇÃO FINAL" (o modelo a ignora ou copia a lista
de opções). A classificação passou a ser extraída por uma segunda chamada curta ao mesmo modelo, só com o
texto que ele gerou, em JSON restrito às 4 opções (sintese.classificar_texto). Também: contexto de 8192
pra 4096 tokens (com 8192 o Ollama chegou a ~6 GB de RAM e a geração caiu pra 0,07 token/s). Critério,
lâminas e modelo não mudaram.

Uso (venv do projeto; precisa do servidor Ollama no ar pra etapa 2):
    .venv/bin/python validacao/prelaudo_avaliacao.py --etapa descrever   # estágios 3 e 4 (usa o UNI2-h)
    .venv/bin/python validacao/prelaudo_avaliacao.py --etapa sintetizar  # estágio 5 e avaliação
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
for sub in ("estagio3_descritores", "estagio4_agregacao", "estagio5_sintese"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / sub))

from comum.lamina import RESULTADOS_DIR, dir_resultados
from comum.rois import info_lamina
from descritor_uni import LAMINAS_TREINO

LAMINAS = LAMINAS_TREINO  # 18
USADAS_NA_REGRA = ["BRACS_748", "BRACS_1489", "BRACS_1370"]
LAMINAS_TESTE_REGRA = [s for s in LAMINAS if s not in USADAS_NA_REGRA]
MODELO = "gemma3:4b"
K = 32
GRUPO = {"N": "benigno", "PB": "benigno", "UDH": "atipico", "FEA": "atipico", "ADH": "atipico", "DCIS": "DCIS", "IC": "IC"}
SAIDA = RESULTADOS_DIR / "prelaudo_avaliacao.json"


def descrever():
    import agregador
    import descritor_uni
    for s in LAMINAS:
        if not (dir_resultados(s, "estagio3") / f"estagio3_descritores_k{K}_uni.json").exists():
            descritor_uni.rodar(s, K)
        agregador.rodar(s, K, ["_uni"], regra_invasivo=False)
        agregador.rodar(s, K, ["_uni"], regra_invasivo=True)
        print(f"  {s}: estágios 3 e 4 prontos", flush=True)


def sintetizar():
    import sintese
    feito = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else {}
    for s in LAMINAS:
        for versao, sufixo in (("v1", "_uni"), ("v2", "_uni_regra")):
            chave = f"{s}|{versao}"
            if chave in feito or (versao == "v2" and s not in LAMINAS_TESTE_REGRA):
                continue
            r = sintese.rodar(s, K, sufixo, MODELO)
            feito[chave] = {"lamina": s, "versao": versao, "predito": r["classificacao_final"],
                            "real": GRUPO[info_lamina(s)["rotulo"]], "rotulo_bracs": info_lamina(s)["rotulo"],
                            "segundos": r["segundos"]}
            SAIDA.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {s} {versao}: predito {r['classificacao_final']} | real {feito[chave]['real']}", flush=True)
    avaliar(feito)


def acertos(feito, versao, stems):
    linhas = [feito[f"{s}|{versao}"] for s in stems]
    return {"acertos": sum(l["predito"] == l["real"] for l in linhas), "n": len(linhas),
            "acertos_IC": sum(l["predito"] == "IC" for l in linhas if l["real"] == "IC"),
            "n_IC": sum(l["real"] == "IC" for l in linhas),
            "confusao": {c: dict(Counter(str(l["predito"]) for l in linhas if l["real"] == c))
                         for c in ("benigno", "atipico", "DCIS", "IC")}}


def avaliar(feito):
    resumo = {"A_v1_18_laminas": acertos(feito, "v1", LAMINAS),
              "B_v1_15_laminas": acertos(feito, "v1", LAMINAS_TESTE_REGRA),
              "B_v2_15_laminas": acertos(feito, "v2", LAMINAS_TESTE_REGRA)}
    v1, v2 = resumo["B_v1_15_laminas"], resumo["B_v2_15_laminas"]
    resumo["B_funcionou"] = v2["acertos_IC"] > v1["acertos_IC"] and v2["acertos"] >= v1["acertos"]
    resumo["por_lamina"] = {s: {v: feito.get(f"{s}|{v}", {}).get("predito") for v in ("v1", "v2")} | {
        "real": feito[f"{s}|v1"]["real"], "rotulo_bracs": feito[f"{s}|v1"]["rotulo_bracs"]} for s in LAMINAS}
    (RESULTADOS_DIR / "prelaudo_avaliacao_resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                                  encoding="utf-8")
    print(f"\n{'Lâmina':<15}{'rótulo':>8}{'real':>9}{'v1':>9}{'v2':>9}")
    for s, d in resumo["por_lamina"].items():
        print(f"{s:<15}{d['rotulo_bracs']:>8}{d['real']:>9}{str(d['v1']):>9}{str(d['v2']):>9}")
    a = resumo["A_v1_18_laminas"]
    print(f"\nA) v1 nas 18: {a['acertos']}/{a['n']} certas; IC {a['acertos_IC']}/{a['n_IC']}; confusão {a['confusao']}")
    print(f"B) nas 15: v1 {v1['acertos']}/15 (IC {v1['acertos_IC']}/{v1['n_IC']}) | v2 {v2['acertos']}/15 (IC {v2['acertos_IC']}/{v2['n_IC']})")
    print(f"Critério fixado antes (v2 acerta mais IC e não perde acurácia): {'SIM' if resumo['B_funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["descrever", "sintetizar"], required=True)
    a = p.parse_args()
    descrever() if a.etapa == "descrever" else sintetizar()
