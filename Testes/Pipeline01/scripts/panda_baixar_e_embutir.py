"""
PANDA (Prostate cANcer graDe Assessment; Bulten et al., Nature Medicine 2022; CC BY-NC-SA 4.0, só uso não comercial):
biópsias de próstata em H&E com grau ISUP (0-5) e escore de Gleason, de dois centros (Radboud, Holanda; Karolinska,
Suécia). Distribuído só pelo Kaggle (competição prostate-cancer-grade-assessment; exige conta, regras aceitas e token
em ~/.kaggle, que nunca entra no repositório).

Fixado ANTES de baixar (commit anterior aos resultados):
  Sorteio (--sortear, semente 0, sobre o train.csv do Kaggle): treino = 600 biópsias do Radboud, 100 de cada ISUP;
     teste = 300 biópsias do Karolinska, 50 de cada ISUP. Lista em scripts/lista_panda.tsv.
     Treino e teste em centros diferentes: o PANDA não informa o paciente de cada biópsia (5.160 biópsias do Radboud
     vêm de 1.028 pacientes), e sortear dentro do mesmo centro poria o mesmo paciente nos dois lados.
  Patches como no TCGA: lado de 128 µm no nível 0, em pixels pela resolução gravada no TIFF (XResolution, px/cm);
     máscara de tecido da pipeline (comum.tecido) numa miniatura ~16x; amostra de até 2.000 patches de tecido
     (semente 0); embeddings do UNI2-h.
  Máscara de rótulos (train_label_masks, quando existe): fração de cada valor (0-5) dentro de cada patch, lida no
     nível ~4x da máscara. Radboud: 0 fundo, 1 estroma, 2 epitélio benigno, 3/4/5 Gleason 3/4/5. Karolinska: 0 fundo,
     1 tecido benigno, 2 câncer. Origem das máscaras não descrita no artigo principal: tratadas como aproximadas.
  Imagens e máscaras ficam no HD (<HD>/Dados Gerais/PANDA/), dentro do limite de 70 GB combinado.

Uso (venv do projeto, HD montado, internet):
    .venv/bin/python scripts/panda_baixar_e_embutir.py --sortear      # uma vez; gera a lista
    .venv/bin/python scripts/panda_baixar_e_embutir.py               # baixa e embute; retoma de onde parou
Saída: resultados/panda/<image_id>/{amostra2000.npy, amostra2000_xy.csv, mascara_frac.npy, meta.json}
"""

import argparse
import csv
import json
import random
import subprocess
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from comum.lamina import RESULTADOS_DIR, Lamina, raiz_hd
from comum.tecido import mascara_tecido
from tcga_baixar_e_embutir import grade

COMPETICAO = "prostate-cancer-grade-assessment"
N_TREINO_POR_ISUP = 100
N_TESTE_POR_ISUP = 50
N_AMOSTRA = 2000
LADO_UM = 128.0
ADIANTE = 3
LISTA = Path(__file__).resolve().parent / "lista_panda.tsv"
SAIDA = RESULTADOS_DIR / "panda"
KAGGLE = str(Path(sys.executable).parent / "kaggle")


def pasta_panda():
    return Path(raiz_hd()) / "Dados Gerais" / "PANDA"


def sortear():
    linhas = list(csv.DictReader(open(pasta_panda() / "train.csv", encoding="utf-8")))
    por = defaultdict(list)
    for l in linhas:
        por[(l["data_provider"], l["isup_grade"])].append(l)
    rng, saida = random.Random(0), []
    for centro, n, conjunto in (("radboud", N_TREINO_POR_ISUP, "treino"), ("karolinska", N_TESTE_POR_ISUP, "teste")):
        for isup in "012345":
            for l in rng.sample(sorted(por[(centro, isup)], key=lambda r: r["image_id"]), n):
                saida.append({**l, "conjunto": conjunto})
    with open(LISTA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["image_id", "data_provider", "isup_grade", "gleason_score", "conjunto"], delimiter="\t")
        w.writeheader()
        w.writerows(saida)
    print(f"{len(saida)} biópsias em {LISTA}")


def baixar_arquivo(remoto, destino_dir):
    """Baixa um arquivo da competição; o Kaggle entrega .zip, extraído aqui com checagem do nome."""
    destino_dir.mkdir(parents=True, exist_ok=True)
    nome = Path(remoto).name
    final = destino_dir / nome
    if final.exists() and final.stat().st_size > 0:
        return final
    r = subprocess.run([KAGGLE, "competitions", "download", "-c", COMPETICAO, "-f", remoto, "-p", str(destino_dir), "-q"],
                       capture_output=True, text=True, timeout=1800)
    z = destino_dir / f"{nome}.zip"
    if z.exists():
        with zipfile.ZipFile(z) as zf:
            nomes = zf.namelist()
            if nomes != [nome]:
                raise RuntimeError(f"zip inesperado: {nomes}")
            zf.extractall(destino_dir)
        z.unlink()
    if not final.exists() or final.stat().st_size == 0:
        raise FileNotFoundError(f"{remoto}: {r.stdout.strip()[-200:]} {r.stderr.strip()[-200:]}")
    return final


def baixar(l):
    img = baixar_arquivo(f"train_images/{l['image_id']}.tiff", pasta_panda() / "train_images")
    try:
        mask = baixar_arquivo(f"train_label_masks/{l['image_id']}_mask.tiff", pasta_panda() / "train_label_masks")
    except FileNotFoundError:
        mask = None
    return img, mask


def mpp_tiff(lamina):
    num, den = lamina.tif.pages[0].tags["XResolution"].value
    if lamina.tif.pages[0].tags["ResolutionUnit"].value != 3:
        raise ValueError("unidade de resolução diferente de cm")
    return 10000.0 / (num / den)


def fracoes_mascara(caminho, xy, lado, largura0):
    import tifffile
    with tifffile.TiffFile(caminho) as t:
        niveis = t.series[0].levels
        i = min(range(len(niveis)), key=lambda j: abs(np.log(largura0 / niveis[j].shape[1] / 4)))
        m = niveis[i].asarray()
    m = m[..., 0] if m.ndim == 3 else m
    ds = largura0 / m.shape[1]
    saida = np.zeros((len(xy), 6), np.float32)
    for k, (x0, y0) in enumerate(xy):
        r = m[int(y0 / ds):int((y0 + lado) / ds), int(x0 / ds):int((x0 + lado) / ds)]
        if r.size:
            saida[k] = np.bincount(r.ravel(), minlength=6)[:6] / r.size
    return saida


def embutir(img, mask, pasta):
    import torch
    from comum.modelo import dispositivo
    from comum.uni import LOTE, _preparar, carregar_uni2h
    lamina = Lamina(img)
    res = mpp_tiff(lamina)
    lado = int(round(LADO_UM / res))
    rgb, ds = lamina.thumbnail(16)
    xy = grade(lamina, mascara_tecido(rgb[..., :3]), ds, lado)
    if not xy:
        raise ValueError("nenhum patch de tecido")
    amostra = sorted(random.Random(0).sample(xy, min(N_AMOSTRA, len(xy))))
    modelo, embs = carregar_uni2h(), []
    for i in range(0, len(amostra), LOTE):
        lote = np.stack([_preparar(lamina.janela_nativa(x0, y0, lado)[..., :3]) for x0, y0 in amostra[i:i + LOTE]])
        x = torch.from_numpy(lote).to(dispositivo())
        with torch.no_grad():
            embs.append(modelo(x.half() if dispositivo() == "cuda" else x).float().cpu().numpy())
    np.save(pasta / "amostra2000.npy", np.concatenate(embs))
    with open(pasta / "amostra2000_xy.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([["x0", "y0"]] + amostra)
    if mask is not None:
        np.save(pasta / "mascara_frac.npy", fracoes_mascara(mask, amostra, lado, lamina.largura).astype(np.float16))
    lamina.tif.close()
    return {"mpp": round(res, 4), "lado_px": lado, "n_tecido": len(xy), "n_amostra": len(amostra), "mascara": mask is not None}


def main():
    from concurrent.futures import ThreadPoolExecutor
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    pendentes = [(i, l) for i, l in enumerate(linhas, 1) if not (SAIDA / l["image_id"] / "meta.json").exists()]
    falhas, downloads = [], {}
    with ThreadPoolExecutor(max_workers=ADIANTE) as ex:
        for j, (i, l) in enumerate(pendentes):
            for _, prox in pendentes[j:j + ADIANTE]:
                if prox["image_id"] not in downloads:
                    downloads[prox["image_id"]] = ex.submit(baixar, prox)
            pasta = SAIDA / l["image_id"]
            pasta.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            try:
                img, mask = downloads.pop(l["image_id"]).result()
                meta = {**{k: l[k] for k in ("image_id", "data_provider", "isup_grade", "gleason_score", "conjunto")},
                        **embutir(img, mask, pasta)}
                (pasta / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
                print(f"[{i}/{len(linhas)}] {l['data_provider']} ISUP {l['isup_grade']}: {meta['n_amostra']} de "
                      f"{meta['n_tecido']} patches, {meta['mpp']:.3f} µm/px, lado {meta['lado_px']} px, "
                      f"máscara {'sim' if meta['mascara'] else 'não'} ({time.time() - t0:.0f} s)", flush=True)
            except Exception as e:  # noqa: BLE001 — registra e segue
                falhas.append(l["image_id"])
                print(f"[{i}/{len(linhas)}] {l['image_id']}: FALHOU ({type(e).__name__}: {e})", flush=True)
    print(f"fim: {len(pendentes) - len(falhas)} prontas nesta rodada, {len(falhas)} falhas")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sortear", action="store_true")
    a = p.parse_args()
    sortear() if a.sortear else main()
