"""
PANDA com normalização de cor (Reinhard et al., 2001) antes do UNI2-h, pra testar se a troca de centro (Radboud ->
Karolinska) é sobretudo diferença de coloração. Usa as mesmas biópsias, os mesmos patches (amostra2000_xy.csv) e o
mesmo lado em pixels de panda_baixar_e_embutir.py; só a cor de cada patch muda antes do embedding.

Fixado ANTES de rodar (commit anterior aos resultados; avaliação em mil/panda/panda_centro.py):
  Cor de cada biópsia: média e desvio de L, a, b (espaço Lab do OpenCV, em float) nos pixels de tecido
     (comum.tecido.mascara_tecido) da miniatura ~16x.
  Alvo: média dessas estatísticas nas 600 biópsias de treino do Radboud (etapa --alvo).
  Normalização: em cada patch, Lab -> (Lab - média da biópsia) / desvio da biópsia * desvio do alvo + média do alvo,
     volta pra RGB (recorte em 0-255). Aplicada às 900 biópsias (treino e teste), como é o uso comum.
  As imagens já estão no HD (panda_baixar_e_embutir.py guardou); nada é baixado.

Uso (venv do projeto, HD montado, GPU livre):
    .venv/bin/python dados/panda/panda_embutir_reinhard.py --alvo
    .venv/bin/python dados/panda/panda_embutir_reinhard.py          # retoma de onde parou
Saída: resultados/panda/<image_id>/amostra2000_reinhard.npy; alvo em resultados/panda_reinhard_alvo.json
"""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR, Lamina  # noqa: E402
from comum.tecido import mascara_tecido  # noqa: E402
from panda_baixar_e_embutir import LISTA, SAIDA, pasta_panda  # noqa: E402

ALVO = RESULTADOS_DIR / "panda_reinhard_alvo.json"


def estatisticas(lamina):
    rgb, _ = lamina.thumbnail(16)
    rgb = np.ascontiguousarray(rgb[..., :3])
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[mascara_tecido(rgb) > 0]
    return lab.mean(0), lab.std(0) + 1e-6


def normalizar(rgb, fonte, alvo):
    lab = cv2.cvtColor(np.ascontiguousarray(rgb[..., :3]).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    lab = (lab - fonte[0]) / fonte[1] * alvo[1] + alvo[0]
    out = cv2.cvtColor(lab.astype(np.float32), cv2.COLOR_LAB2RGB)
    return (np.clip(out, 0, 1) * 255).round().astype(np.uint8)


def linhas():
    return list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))


def calcular_alvo():
    ms, ss = [], []
    for l in linhas():
        if l["conjunto"] != "treino":
            continue
        lam = Lamina(pasta_panda() / "train_images" / f"{l['image_id']}.tiff")
        m, s = estatisticas(lam)
        lam.tif.close()
        ms.append(m)
        ss.append(s)
    alvo = {"media": np.mean(ms, 0).tolist(), "desvio": np.mean(ss, 0).tolist(), "n": len(ms)}
    ALVO.write_text(json.dumps(alvo, indent=1), encoding="utf-8")
    print(alvo)


def main():
    import torch
    from comum.modelo import dispositivo
    from comum.uni import LOTE, _preparar, carregar_uni2h
    a = json.loads(ALVO.read_text(encoding="utf-8"))
    alvo = (np.array(a["media"], np.float32), np.array(a["desvio"], np.float32))
    modelo = carregar_uni2h()
    todas = linhas()
    for k, l in enumerate(todas, 1):
        pasta = SAIDA / l["image_id"]
        if (pasta / "amostra2000_reinhard.npy").exists():
            continue
        t0 = time.time()
        meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
        xy = np.loadtxt(pasta / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        lam = Lamina(pasta_panda() / "train_images" / f"{l['image_id']}.tiff")
        fonte = estatisticas(lam)
        embs = []
        for i in range(0, len(xy), LOTE):
            lote = np.stack([_preparar(normalizar(lam.janela_nativa(int(x0), int(y0), meta["lado_px"]), fonte, alvo))
                             for x0, y0 in xy[i:i + LOTE]])
            x = torch.from_numpy(lote).to(dispositivo())
            with torch.no_grad():
                embs.append(modelo(x.half() if dispositivo() == "cuda" else x).float().cpu().numpy())
        lam.tif.close()
        np.save(pasta / "amostra2000_reinhard.npy", np.concatenate(embs))
        print(f"[{k}/{len(todas)}] {l['data_provider']} ISUP {l['isup_grade']}: {len(xy)} patches ({time.time() - t0:.0f} s)",
              flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--alvo", action="store_true")
    calcular_alvo() if p.parse_args().alvo else main()
