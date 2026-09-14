"""
Estágio 4 da Pipeline Ideia 01: agregação.

Junta os k blocos de texto do estágio 3 + um cabeçalho slide-level
(contagens agregadas) + N patches como âncora visual num prompt só —
o ponto em que a lâmina de gigapixels vira, de fato, uma entrada que cabe
num modelo de 4B. Não tem pergunta empírica própria (é montagem, não
pesquisa) — a única decisão real é qual versão do estágio 3 (bruto ou
normalizado) usar.

Uso:
    .venv/bin/python agregador.py --k 32                  # bruto
    .venv/bin/python agregador.py --k 32 --normalizar      # normalizado
    .venv/bin/python agregador.py --k 32 --ambos           # gera os dois, lado a lado
"""

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).parent
ESTAGIO3_OUTPUTS = BASE_DIR.parent / "estagio3" / "outputs"
OUTPUTS_ROOT = BASE_DIR / "outputs"
N_ANCORAS = 3  # docs/pipelines.md: 1-3, não mais (token visual cresce rápido)


def montar_prompt(lamina_stem, k, sufixo, e3_dir):
    caminho_json = e3_dir / f"estagio3_descritores_k{k}{sufixo}.json"
    dados = json.loads(caminho_json.read_text(encoding="utf-8"))
    descritores = dados["descritores"]

    # --- cabeçalho slide-level: agregado dos próprios achados, sem modelo novo ---
    contagem = Counter()
    for d in descritores:
        for achado in d["achados"]:
            contagem[achado] += 1
    total = len(descritores)
    achado_mais_comum, freq_mais_comum = contagem.most_common(1)[0]

    linhas_cabecalho = [
        f"Patches analisados: {total}",
        "Achados agregados:",
    ]
    for achado, n in contagem.most_common():
        linhas_cabecalho.append(f"  - {achado}: {n}/{total} patches ({100*n/total:.0f}%)")
    linhas_cabecalho.append(f"Achado dominante: {achado_mais_comum} ({100*freq_mais_comum/total:.0f}% dos patches)")

    # --- blocos de texto por patch, já prontos do estágio 3 ---
    linhas_patches = [d["texto"] for d in descritores]

    # --- âncoras visuais: os N de maior score do roteador ---
    ancoras = sorted(descritores, key=lambda d: -d["score_roteador"])[:N_ANCORAS]

    prompt = (
        f"=== Pré-laudo — evidência agregada (estágio 4) ===\n"
        f"Lâmina: {lamina_stem}\n"
        f"Banco de frases: {'normalizado (z-score)' if sufixo else 'bruto (similaridade máxima)'}\n\n"
        + "\n".join(linhas_cabecalho)
        + "\n\nDetalhe por patch:\n"
        + "\n".join(linhas_patches)
        + f"\n\nÂncoras visuais anexadas ({len(ancoras)}): "
        + ", ".join(f"[{a['x0']},{a['y0']}]" for a in ancoras)
    )

    n_tokens_texto = len(prompt.split())
    n_tokens_visuais_estimados = len(ancoras) * 400  # meio da faixa 256-576 documentada em docs/pipelines.md

    return prompt, ancoras, n_tokens_texto, n_tokens_visuais_estimados


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svs-stem", default="BRACS_748", help="nome da lâmina (subpasta em outputs/)")
    parser.add_argument("--k", type=int, default=32)
    parser.add_argument("--normalizar", action="store_true")
    parser.add_argument("--ambos", action="store_true", help="gera bruto e normalizado, lado a lado")
    args = parser.parse_args()

    e3_dir = ESTAGIO3_OUTPUTS / args.svs_stem
    output_dir = OUTPUTS_ROOT / args.svs_stem
    output_dir.mkdir(parents=True, exist_ok=True)

    sufixos = ["", "_norm"] if args.ambos else (["_norm"] if args.normalizar else [""])

    for sufixo in sufixos:
        prompt, ancoras, n_tok_texto, n_tok_visual = montar_prompt(args.svs_stem, args.k, sufixo, e3_dir)
        nome = f"estagio4_prompt_k{args.k}{sufixo}"

        (output_dir / f"{nome}.txt").write_text(prompt, encoding="utf-8")

        pasta_ancoras = output_dir / f"{nome}_ancoras"
        pasta_ancoras.mkdir(exist_ok=True)
        exemplos_dir = e3_dir / f"exemplos_k{args.k}{sufixo}"
        for a in ancoras:
            origem = exemplos_dir / f"x{a['x0']}_y{a['y0']}.png"
            candidatos_origem = list(exemplos_dir.glob(f"*x{a['x0']}_y{a['y0']}.png"))
            if candidatos_origem:
                shutil.copy(candidatos_origem[0], pasta_ancoras / candidatos_origem[0].name)

        rotulo = "NORMALIZADO" if sufixo else "BRUTO"
        print(f"--- {rotulo} (k={args.k}) ---")
        print(f"tokens de texto: {n_tok_texto} | tokens visuais estimados: {n_tok_visual} (~{len(ancoras)} âncoras) | total: ~{n_tok_texto + n_tok_visual}")
        print(f"salvo em {output_dir / (nome + '.txt')}")
        print()

    print(f"Saída em {output_dir}")


if __name__ == "__main__":
    main()
