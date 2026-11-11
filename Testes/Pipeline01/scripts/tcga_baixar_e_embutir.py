"""
Baixa lâminas do TCGA (GDC, acesso aberto) uma a uma, calcula os embeddings do UNI2-h de uma amostra de
2.000 patches de tecido e apaga a lâmina, como baixar_e_embutir.py faz pro BRACS.

Diferença: o TCGA mistura lâminas de 20x e 40x. O lado do patch no nível 0 sai da resolução gravada na lâmina
(MPP da descrição Aperio), pra cobrir sempre 128 µm de tecido: 512 px a 0,25 µm/px, 256 px a 0,5 µm/px.

Saída: resultados/tcga_pulmao/<file_id>/amostra2000.npy, amostra2000_xy.csv e meta.json. Retoma de onde parou.

Uso (venv do projeto, HD montado):
    .venv/bin/python scripts/tcga_baixar_e_embutir.py scripts/lista_tcga_pulmao.tsv
"""

import csv
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from comum.lamina import RESULTADOS_DIR, Lamina, raiz_hd
from comum.tecido import LIMIAR_TECIDO, mascara_tecido

N_AMOSTRA = 2000
LADO_UM = 128.0
SAIDA = RESULTADOS_DIR / "tcga_pulmao"


def mpp(lamina):
    m = re.search(r"MPP\s*=\s*([0-9.]+)", lamina.tif.pages[0].description or "")
    if not m:
        raise ValueError("lâmina sem MPP na descrição")
    return float(m.group(1))


def grade(lamina, mask, ds_mask, lado):
    """Como comum.tecido.grade_candidatos, com o lado do patch como parâmetro."""
    saida = []
    for y0 in range(0, lamina.altura - lado, lado):
        for x0 in range(0, lamina.largura - lado, lado):
            r = mask[int(y0 / ds_mask):int((y0 + lado) / ds_mask), int(x0 / ds_mask):int((x0 + lado) / ds_mask)]
            if r.size and np.count_nonzero(r) / r.size >= LIMIAR_TECIDO:
                saida.append((x0, y0))
    return saida


def embutir(caminho, pasta):
    import torch
    from comum.modelo import dispositivo
    from comum.uni import LOTE, _preparar, carregar_uni2h
    lamina = Lamina(caminho)
    res = mpp(lamina)
    lado = int(round(LADO_UM / res))
    rgb, ds = lamina.thumbnail(32)
    xy = grade(lamina, mascara_tecido(rgb), ds, lado)
    amostra = sorted(random.Random(0).sample(xy, min(N_AMOSTRA, len(xy))))
    modelo, embs = carregar_uni2h(), []
    for i in range(0, len(amostra), LOTE):
        lote = np.stack([_preparar(lamina.janela_nativa(x0, y0, lado)) for x0, y0 in amostra[i:i + LOTE]])
        x = torch.from_numpy(lote).to(dispositivo())
        with torch.no_grad():
            embs.append(modelo(x.half() if dispositivo() == "cuda" else x).float().cpu().numpy())
    np.save(pasta / "amostra2000.npy", np.concatenate(embs))
    with open(pasta / "amostra2000_xy.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["x0", "y0"]] + amostra)
    return {"mpp": res, "lado_px": lado, "n_tecido": len(xy), "n_amostra": len(amostra)}


def main():
    linhas = list(csv.DictReader(open(sys.argv[1], encoding="utf-8"), delimiter="\t"))
    tmp = Path(raiz_hd()) / "TCGA_pulmao_tmp"
    tmp.mkdir(exist_ok=True)
    falhas = []
    for i, l in enumerate(linhas, 1):
        pasta = SAIDA / l["file_id"]
        if (pasta / "meta.json").exists():
            continue
        pasta.mkdir(parents=True, exist_ok=True)
        svs, t0 = tmp / l["file_name"], time.time()
        try:
            if not svs.exists() or svs.stat().st_size != int(l["bytes"]):
                r = subprocess.run(["wget", "-q", "--continue", "--tries=5", "--timeout=60", "-O", str(svs),
                                    f"https://api.gdc.cancer.gov/data/{l['file_id']}"])
                if r.returncode != 0 or svs.stat().st_size != int(l["bytes"]):
                    raise RuntimeError("download incompleto")
            meta = {**{k: l[k] for k in ("file_name", "projeto", "paciente", "conjunto")}, **embutir(svs, pasta)}
            (pasta / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
            svs.unlink()
            print(f"[{i}/{len(linhas)}] {l['projeto']} {l['paciente']}: {meta['n_amostra']} de {meta['n_tecido']} patches, "
                  f"{meta['mpp']:.3f} µm/px, lado {meta['lado_px']} px ({time.time() - t0:.0f} s)", flush=True)
        except Exception as e:  # noqa: BLE001 — registra e segue
            falhas.append(l["file_id"])
            print(f"[{i}/{len(linhas)}] {l['file_name']}: ERRO {type(e).__name__}: {e}", flush=True)
    print(f"\nconcluído; falhas: {falhas or 'nenhuma'}")


if __name__ == "__main__":
    main()
