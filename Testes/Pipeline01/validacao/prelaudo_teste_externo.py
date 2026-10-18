"""
Teste externo do pré-laudo: a pipeline congelada (como em prelaudo_avaliacao.py), sem nenhum ajuste,
em lâminas do conjunto de TESTE oficial do BRACS que o projeto nunca usou.

Fixado ANTES de baixar as lâminas (commit anterior aos resultados):
  - Lâminas: scripts/lista_teste_oficial.txt — conjunto de teste oficial, pacientes que não aparecem
    nas lâminas já usadas, uma lâmina por paciente e por classe: 57 lâminas de 31 pacientes
    (N 5, PB 8, UDH 7, FEA 7, ADH 10, DCIS 8, IC 12).
  - Pipeline congelada: estágio 1 + roteador por frases (32 patches) -> descritor hierárquico UNI2-h
    treinado nos tiles rotulados das 18 lâminas já usadas -> estágio 4 sem a regra (v1) e com a
    regra do componente invasivo (v2) -> Gemma 3 4B (temperature 0,2, seed 0, contexto 4096) ->
    classificação final extraída em JSON restrito às 4 opções.
  - Rótulo real = rótulo da lâmina no BRACS, agrupado em benigno / atípico / DCIS / IC.
  - Critério de "a regra se confirma": nas 57, v2 acerta mais lâminas que v1 E acerta pelo menos
    tantas lâminas IC quanto v1.
  - Também reportado (sem critério): acerto por classe; o subconjunto com uma lâmina por paciente
    (a primeira em ordem de nome, 31 lâminas).

Uso (venv do projeto; a etapa 2 precisa do servidor Ollama no ar):
    .venv/bin/python validacao/prelaudo_teste_externo.py --etapa descrever   # estágios 1 a 4 (GPU)
    .venv/bin/python validacao/prelaudo_teste_externo.py --etapa sintetizar  # estágio 5 e avaliação
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
for sub in ("estagio2_roteador", "estagio3_descritores", "estagio4_agregacao", "estagio5_sintese"):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / sub))

from comum.lamina import RESULTADOS_DIR, dir_resultados, ler_caminhos
from comum.rois import info_lamina

LISTA = Path(__file__).resolve().parent.parent / "scripts" / "lista_teste_oficial.txt"
MODELO = "gemma3:4b"
K = 32
GRUPO = {"N": "benigno", "PB": "benigno", "UDH": "atipico", "FEA": "atipico", "ADH": "atipico", "DCIS": "DCIS", "IC": "IC"}
SAIDA = RESULTADOS_DIR / "prelaudo_teste_externo.json"


def laminas():
    return [Path(l.strip()).stem for l in LISTA.read_text(encoding="utf-8").splitlines() if l.strip()]


def baixadas():
    pasta = Path(ler_caminhos()["laminas_dir"])
    return [s for s in laminas() if (pasta / f"{s}.svs").exists()]


def descrever():
    import agregador
    import descritor_uni
    import roteador_topk
    # duas passadas, pra não ter QuiltNet (roteador) e UNI2-h (descritor) juntos na GPU de 4 GB
    for s in baixadas():
        if not (dir_resultados(s, "estagio2") / "estagio2_scores_v2.csv").exists():
            roteador_topk.rodar(s, "v2", ks=[K])
            print(f"  {s}: estágios 1 e 2 prontos", flush=True)
    import torch
    from comum.modelo import carregar_quiltnet
    carregar_quiltnet.cache_clear()
    torch.cuda.empty_cache()
    for s in baixadas():
        if (dir_resultados(s, "estagio4") / f"estagio4_prompt_k{K}_uni_regra.txt").exists():
            continue
        descritor_uni.rodar(s, K)
        agregador.rodar(s, K, ["_uni"], regra_invasivo=False)
        agregador.rodar(s, K, ["_uni"], regra_invasivo=True)
        print(f"  {s}: estágios 3 e 4 prontos", flush=True)


def sintetizar():
    import sintese
    feito = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else {}
    for s in baixadas():
        if not (dir_resultados(s, "estagio4") / f"estagio4_prompt_k{K}_uni_regra.txt").exists():
            continue
        for versao, sufixo in (("v1", "_uni"), ("v2", "_uni_regra")):
            chave = f"{s}|{versao}"
            if chave in feito:
                continue
            r = sintese.rodar(s, K, sufixo, MODELO)
            info = info_lamina(s)
            feito[chave] = {"lamina": s, "versao": versao, "predito": r["classificacao_final"],
                            "real": GRUPO[info["rotulo"]], "rotulo_bracs": info["rotulo"], "segundos": r["segundos"]}
            SAIDA.write_text(json.dumps(feito, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {s} {versao}: predito {r['classificacao_final']} | real {feito[chave]['real']}", flush=True)
    avaliar(feito)


def um_por_paciente(stems):
    import openpyxl
    ws = openpyxl.load_workbook(Path(ler_caminhos()["laminas_dir"]) / "BRACS.xlsx", read_only=True)["WSI_Information"]
    paciente = {r[0]: r[1] for r in ws.iter_rows(min_row=2, values_only=True) if r[0]}
    vistos, saida = set(), []
    for s in sorted(stems):
        if paciente[s] not in vistos:
            vistos.add(paciente[s])
            saida.append(s)
    return saida


def resumo_de(feito, versao, stems):
    linhas = [feito[f"{s}|{versao}"] for s in stems if f"{s}|{versao}" in feito]
    por_classe = {c: f"{sum(l['predito'] == c for l in linhas if l['real'] == c)}/{sum(l['real'] == c for l in linhas)}"
                  for c in ("benigno", "atipico", "DCIS", "IC")}
    return {"acertos": sum(l["predito"] == l["real"] for l in linhas), "n": len(linhas),
            "acertos_IC": sum(l["predito"] == "IC" for l in linhas if l["real"] == "IC"), "por_classe": por_classe,
            "preditas": dict(Counter(str(l["predito"]) for l in linhas))}


def avaliar(feito):
    completas = [s for s in laminas() if f"{s}|v1" in feito and f"{s}|v2" in feito]
    resumo = {"n_laminas_avaliadas": len(completas), "n_laminas_previstas": len(laminas())}
    for nome, stems in (("todas", completas), ("um_por_paciente", um_por_paciente(completas))):
        resumo[nome] = {v: resumo_de(feito, v, stems) for v in ("v1", "v2")}
    v1, v2 = resumo["todas"]["v1"], resumo["todas"]["v2"]
    resumo["regra_se_confirma"] = v2["acertos"] > v1["acertos"] and v2["acertos_IC"] >= v1["acertos_IC"]
    (RESULTADOS_DIR / "prelaudo_teste_externo_resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False),
                                                                      encoding="utf-8")
    for nome in ("todas", "um_por_paciente"):
        for v in ("v1", "v2"):
            r = resumo[nome][v]
            print(f"{nome:<16} {v}: {r['acertos']}/{r['n']} certas | IC {r['acertos_IC']} | por classe {r['por_classe']} | preditas {r['preditas']}")
    print(f"\n{len(completas)} de {len(laminas())} lâminas avaliadas. Critério fixado antes (v2 > v1 e IC v2 >= v1): "
          f"{'SIM' if resumo['regra_se_confirma'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["descrever", "sintetizar"], required=True)
    a = p.parse_args()
    descrever() if a.etapa == "descrever" else sintetizar()
