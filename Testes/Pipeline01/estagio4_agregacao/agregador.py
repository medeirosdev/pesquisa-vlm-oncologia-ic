"""
Estágio 4 — agregação.

Junta os blocos de texto do estágio 3 + um cabeçalho com as contagens dos achados +
até 3 patches como âncora visual num prompt só (o que entraria na VLM do estágio 5).
Não tem pergunta empírica própria; a única decisão é qual variante do estágio 3 usar.

Uso:
    .venv/bin/python estagio4_agregacao/agregador.py --svs BRACS_1370 --k 32 --ambos
"""

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comum.lamina import dir_resultados, resolver_svs

N_ANCORAS = 3
TOKENS_POR_ANCORA = 400  # meio da faixa 256-576 documentada em docs/pipelines.md


def montar(stem, k, sufixo):
    e3 = dir_resultados(stem, "estagio3")
    dados = json.loads((e3 / f"estagio3_descritores_k{k}{sufixo}.json").read_text(encoding="utf-8"))
    descritores = dados["descritores"]
    contagem = Counter(a for d in descritores for a in d["achados"])
    total = len(descritores)
    dominante, freq = contagem.most_common(1)[0]
    ancoras = sorted(descritores, key=lambda d: -d["score_roteador"])[:N_ANCORAS]

    cats = Counter(d["categoria"] for d in descritores)
    linhas = [f"=== Pré-laudo — evidência agregada (estágio 4) ===",
              f"Lâmina: {stem}",
              f"Descritor: {dados['variante']}", "",
              f"Patches analisados: {total}",
              "Patches por categoria: " + ", ".join(f"{c} {cats.get(c, 0)}" for c in ("benigno", "atipico", "maligno")),
              "Achados agregados:"]
    linhas += [f"  - {a}: {n}/{total} patches ({100 * n / total:.0f}%)" for a, n in contagem.most_common()]
    linhas += [f"Achado dominante: {dominante} ({100 * freq / total:.0f}% dos patches)", "", "Detalhe por patch:"]
    linhas += [d["texto"] for d in descritores]
    linhas += ["", f"Âncoras visuais anexadas ({len(ancoras)}): " + ", ".join(f"[{a['x0']},{a['y0']}]" for a in ancoras)]
    prompt = "\n".join(linhas)
    return prompt, ancoras, dominante, round(100 * freq / total, 1)


def rodar(svs=None, k=32, sufixos=("",)) -> dict:
    stem = resolver_svs(svs).stem
    saida = dir_resultados(stem, "estagio4")
    e3 = dir_resultados(stem, "estagio3")
    resultado = {}
    for sufixo in sufixos:
        prompt, ancoras, dominante, pct = montar(stem, k, sufixo)
        nome = f"estagio4_prompt_k{k}{sufixo}"
        (saida / f"{nome}.txt").write_text(prompt, encoding="utf-8")
        pasta = saida / f"{nome}_ancoras"
        pasta.mkdir(exist_ok=True)
        for a in ancoras:
            for origem in (e3 / f"exemplos_k{k}{sufixo}").glob(f"*x{a['x0']}_y{a['y0']}.png"):
                shutil.copy(origem, pasta / origem.name)
        tokens_texto = len(prompt.split())
        resultado[sufixo.strip("_") or "bruto"] = {
            "achado_dominante": dominante, "pct_dominante": pct, "tokens_texto": tokens_texto,
            "tokens_total_estimado": tokens_texto + len(ancoras) * TOKENS_POR_ANCORA}
    return {"lamina": stem, "k": k, "variantes": resultado}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--normalizar", action="store_true")
    parser.add_argument("--ambos", action="store_true", help="gera bruto e normalizado")
    a = parser.parse_args()
    sufixos = ["", "_norm"] if a.ambos else (["_norm"] if a.normalizar else [""])
    print(json.dumps(rodar(a.svs, a.k, sufixos), indent=2, ensure_ascii=False))
