"""
Estágio 2, segunda rodada — etapa 2 (ambiente do CellViT): quantos dos patches escolhidos por cada
estratégia (roteador_v2_selecao.py) têm tumor? Métrica que não depende dos RoIs (que não marcam
toda a lesão).

Fixado ANTES de rodar (commit anterior aos resultados), junto com roteador_v2_selecao.py:
  - Núcleos: detecção do CellViT-256 numa janela de 1024 px centrada no patch; tipo de cada núcleo
    pela logística treinada nos tokens do CellViT com os núcleos anotados do NuCLS (como em
    nucls_classificador.py, que deu sensibilidade 0,83 e valor preditivo 0,88 pra tumor em
    hospitais fora do treino), aqui treinada no NuCLS inteiro.
  - "Patch com tumor" = >= 20 núcleos classificados como neoplásicos dentro do patch de 512 px.
  - Métrica por lâmina: fração dos 32 patches escolhidos com tumor (sorteio: média dos 5).
  - Critério de "funcionou": uni_por_cat > frases em pelo menos 5 das 7 lâminas E média maior.

Uso (ambiente do CellViT, depois da etapa 1):
    "<HD>/venvs/cellvit/bin/python" validacao/roteador_v2_tumor.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import torch
import torch.nn.functional as F

from categoria_uni import logistica_multinomial
from comum.lamina import RESULTADOS_DIR, TILE_NATIVO, Lamina, dir_resultados, resolver_svs
from nucleos_cellvit import MARGEM, carregar_modelo, ler_janela
from nucls_classificador import CLASSES, TOKENS, parear_indices
from nucls_cellvit import NUCLS, anotados

MIN_NEOPLASICOS = 20
ESTRATEGIAS = ["frases", "uni_nao_ben", "uni_por_cat"]
TAM_TOKEN = 16


@torch.no_grad()
def nucleos_do_patch(modelo, media, desvio, lamina, x0, y0, dispositivo):
    """Descrição (384 números) de cada núcleo detectado dentro do patch de 512 px."""
    img = ler_janela(lamina, x0, y0)
    x = torch.from_numpy(((img.astype(np.float32) / 255 - media) / desvio).transpose(2, 0, 1))[None].to(dispositivo)
    with torch.autocast("cuda", dtype=torch.float16, enabled=dispositivo == "cuda"):
        o = modelo(x, retrieve_tokens=True)
    tok = o["tokens"][0].float().cpu().numpy()
    pred = {k: o[k].float() for k in ("nuclei_binary_map", "nuclei_type_map", "hv_map")}
    pred["nuclei_binary_map"] = F.softmax(pred["nuclei_binary_map"], 1)
    pred["nuclei_type_map"] = F.softmax(pred["nuclei_type_map"], 1)
    _, celulas = modelo.calculate_instance_map(pred, magnification=40)
    feats = []
    for c in celulas[0].values():
        cx, cy = float(c["centroid"][0]), float(c["centroid"][1])
        if not (MARGEM <= cx < MARGEM + TILE_NATIVO and MARGEM <= cy < MARGEM + TILE_NATIVO):
            continue
        (r0, c0), (r1, c1) = c["bbox"]
        t = tok[:, r0 // TAM_TOKEN: max(r1 - 1, r0) // TAM_TOKEN + 1, c0 // TAM_TOKEN: max(c1 - 1, c0) // TAM_TOKEN + 1]
        feats.append(t.reshape(384, -1).mean(1))
    return np.array(feats, np.float32).reshape(-1, 384)


def treino_nucls():
    """Núcleos do NuCLS pareados com detecções do CellViT: descrições e classes (todo o NuCLS)."""
    X, y = [], []
    for p in sorted((NUCLS / "csv").glob("*.csv")):
        z = np.load(TOKENS / f"{p.stem}.npz")
        gt = anotados(p)
        for i, j in parear_indices(gt, z["xy"]):
            X.append(z["feats"][j].astype(np.float32))
            y.append(CLASSES.index(gt[i][2]))
    return np.array(X), np.array(y)


def main():
    sel = json.loads((RESULTADOS_DIR / "roteador_v2_selecoes.json").read_text(encoding="utf-8"))
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, media, desvio = carregar_modelo(dispositivo)

    feats = {}
    for s, d in sel.items():
        lamina = Lamina(resolver_svs(s))
        cache = dir_resultados(s, "nucleos_tokens")
        patches = {tuple(p) for e in ESTRATEGIAS for p in d[e]} | {tuple(p) for sorteio in d["sorteio"] for p in sorteio}
        for x0, y0 in patches:
            arq = cache / f"{x0}_{y0}.npy"
            if not arq.exists():
                np.save(arq, nucleos_do_patch(modelo, media, desvio, lamina, x0, y0, dispositivo))
            feats[(s, x0, y0)] = np.load(arq)
        print(f"  {s}: {len(patches)} patches", flush=True)

    X_tr, y_tr = treino_nucls()
    chaves = [k for k in feats if len(feats[k])]
    X_te = np.concatenate([feats[k] for k in chaves])
    pred = logistica_multinomial(X_tr, y_tr, X_te, k=len(CLASSES))
    neo, pos = {}, 0
    for k in chaves:
        m = len(feats[k])
        neo[k] = int((pred[pos:pos + m] == CLASSES.index("neoplasico")).sum())
        pos += m

    def com_tumor(s, patches):
        return float(np.mean([neo.get((s, x0, y0), 0) >= MIN_NEOPLASICOS for x0, y0 in patches]))

    resumo = {}
    for s, d in sel.items():
        resumo[s] = {e: round(com_tumor(s, d[e]), 3) for e in ESTRATEGIAS}
        resumo[s]["sorteio"] = round(float(np.mean([com_tumor(s, sorteio) for sorteio in d["sorteio"]])), 3)
    laminas = list(sel)
    vitorias = sum(resumo[s]["uni_por_cat"] > resumo[s]["frases"] for s in laminas)
    medias = {e: round(float(np.mean([resumo[s][e] for s in laminas])), 3) for e in ESTRATEGIAS + ["sorteio"]}
    resumo["criterio"] = {"uni_por_cat_vence_frases": vitorias, "laminas": len(laminas), "media": medias,
                          "funcionou": vitorias >= 5 and medias["uni_por_cat"] > medias["frases"]}
    (RESULTADOS_DIR / "roteador_v2_tumor.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'Lâmina':<15}" + "".join(f"{e:>13}" for e in ESTRATEGIAS + ["sorteio"]))
    for s in laminas:
        print(f"{s:<15}" + "".join(f"{resumo[s][e]:>13}" for e in ESTRATEGIAS + ["sorteio"]))
    print(f"{'média':<15}" + "".join(f"{medias[e]:>13}" for e in ESTRATEGIAS + ["sorteio"]))
    print(f"\nCritério fixado antes (uni_por_cat > frases em >= 5 de 7 e média maior): "
          f"{'SIM' if resumo['criterio']['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
