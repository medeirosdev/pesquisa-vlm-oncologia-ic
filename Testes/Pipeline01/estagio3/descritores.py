"""
Estágio 3 da Pipeline Ideia 01: extração de descritores por patch.

Para cada um dos k patches selecionados no estágio 2, gera um achado textual
curto via o mesmo mecanismo contrastivo (QuiltNet) — casa o embedding do
patch (já calculado e cacheado no estágio 2, não recomputa imagem) contra o
banco de frases "suspeito" do banco v2, e pega as que mais casam. Sempre
inclui a coordenada do patch. Começa só com contrastivo + coordenada, como
docs/pipelines.md recomenda — sem densidade nuclear/razão H&E ainda.

Uso:
    .venv/bin/python descritores.py --k 32
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import open_clip
import torch

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR.parent / "estagio2"))
sys.path.insert(0, str(BASE_DIR.parent / "estagio1"))
from roteador_topk import BANCO_V2, TILE_NATIVO, gate_diversidade  # noqa: E402
from filtro_tecido import resolver_caminho_svs  # noqa: E402

OUTPUTS_ROOT = BASE_DIR / "outputs"
ESTAGIO2_OUTPUTS = BASE_DIR.parent / "estagio2" / "outputs"
TOP_N_ACHADOS = 2  # quantas frases do banco "suspeito" entram no achado de cada patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svs", help="Caminho do .svs (padrão: svs: em Caminhos/caminhos.md)")
    parser.add_argument("--k", type=int, default=32, help="k do estágio 2 a usar (padrão: 32, dentro do range documentado 8-32)")
    parser.add_argument("--n-exemplos", type=int, default=5, help="quantos patches salvar como recorte de imagem pra conferência visual")
    args = parser.parse_args()

    caminho_svs = resolver_caminho_svs(args.svs)
    e2_dir = ESTAGIO2_OUTPUTS / caminho_svs.stem
    output_dir = OUTPUTS_ROOT / caminho_svs.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- carrega embeddings já calculados no estágio 2 (sem GPU pra imagem) ---
    embs = np.load(e2_dir / "estagio2_embeddings.npy")
    with open(e2_dir / "estagio2_embeddings_xy.csv", newline="", encoding="utf-8") as f:
        xy = [(int(r["x0"]), int(r["y0"])) for r in csv.DictReader(f)]
    indice_por_xy = {pos: i for i, pos in enumerate(xy)}
    print(f"{len(xy)} embeddings carregados do cache do estágio 2 (nenhuma imagem recomputada)")

    # --- ranking v2 (margem benigno/suspeito) pra escolher os k do estágio 2 ---
    with open(e2_dir / "estagio2_scores_v2.csv", newline="", encoding="utf-8") as f:
        candidatos_ordenados = sorted(
            ({"x0": int(r["x0"]), "y0": int(r["y0"]), "score": float(r["score"])} for r in csv.DictReader(f)),
            key=lambda c: -c["score"],
        )
    selecionados = gate_diversidade(candidatos_ordenados, args.k)
    print(f"k={args.k}: {len(selecionados)} patches selecionados (mesmo gate de diversidade do estágio 2)")

    # --- texto do banco "suspeito", pra virar achado (não é mais margem, é ranking de frase) ---
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms("hf-hub:wisdomik/QuiltNet-B-32")
    tokenizer = open_clip.get_tokenizer("hf-hub:wisdomik/QuiltNet-B-32")
    model = model.to(device).eval()

    frases = BANCO_V2["suspeito"]
    with torch.no_grad():
        tok = tokenizer(frases).to(device)
        emb_frases = model.encode_text(tok)
        emb_frases = emb_frases / emb_frases.norm(dim=-1, keepdim=True)

    descritores = []
    for item in selecionados:
        idx = indice_por_xy[(item["x0"], item["y0"])]
        emb_patch = torch.from_numpy(embs[idx:idx + 1]).to(device)
        with torch.no_grad():
            sim = (emb_patch @ emb_frases.T).squeeze(0).cpu().numpy()
        ordem = np.argsort(-sim)[:TOP_N_ACHADOS]
        achados = [frases[i] for i in ordem]
        texto = f"[{item['x0']},{item['y0']}] " + ", ".join(achados)
        n_tokens_estimado = len(texto.split())  # aproximação grosseira, não é o tokenizador real da VLM
        descritores.append({
            "x0": item["x0"], "y0": item["y0"],
            "achados": achados, "texto": texto,
            "score_roteador": round(item["score"], 3),
            "tokens_estimados": n_tokens_estimado,
        })

    with open(output_dir / f"estagio3_descritores_k{args.k}.json", "w", encoding="utf-8") as f:
        json.dump({"lamina": str(caminho_svs), "k": args.k, "top_n_achados": TOP_N_ACHADOS,
                    "descritores": descritores}, f, indent=2, ensure_ascii=False)

    total_tokens = sum(d["tokens_estimados"] for d in descritores)
    print(f"\n{len(descritores)} descritores gerados, ~{total_tokens} tokens de texto no total (~{total_tokens/len(descritores):.0f}/patch)")
    for d in descritores[:10]:
        print(" ", d["texto"])
    if len(descritores) > 10:
        print(f"  ... (+{len(descritores)-10} no arquivo)")

    # --- recortes de exemplo pra conferência visual (patches com maior score do roteador) ---
    import tifffile
    import zarr
    tif = tifffile.TiffFile(str(caminho_svs))
    store = tif.series[0].aszarr()
    za = zarr.open(store, mode="r")
    za_nivel0 = za["0"] if hasattr(za, "array_keys") else za

    exemplos_dir = output_dir / f"exemplos_k{args.k}"
    exemplos_dir.mkdir(exist_ok=True)
    for i, d in enumerate(sorted(descritores, key=lambda x: -x["score_roteador"])[:args.n_exemplos]):
        janela = np.asarray(za_nivel0[d["y0"]:d["y0"] + TILE_NATIVO, d["x0"]:d["x0"] + TILE_NATIVO])
        nome = f"{i:02d}_x{d['x0']}_y{d['y0']}.png"
        cv2.imwrite(str(exemplos_dir / nome), cv2.cvtColor(janela, cv2.COLOR_RGB2BGR))
        print(f"  exemplo salvo: {nome} -> {', '.join(d['achados'])}")

    print(f"\nSaída em {output_dir}")


if __name__ == "__main__":
    main()
