"""
Sorteio, download e extração de embeddings UNI2-h do conjunto externo do PANDA (Karolinska, distribuição natural).

Motivo (críticas 2 e 3): as 300 biópsias anteriores do Karolinska (dados/panda/lista_panda.tsv) foram usadas para
escolher o GAT-MIL padronizado e tinham distribuição artificialmente balanceada (50 por grau ISUP). Aqui sorteamos
500 biópsias novas do Karolinska, fora das 300 anteriores, na distribuição natural do centro.

Fixado ANTES de baixar (commit anterior aos resultados):
  Sorteio (--sortear): todas as biópsias do Karolinska em <HD>/Dados Gerais/PANDA/train.csv cujo image_id não está em
     dados/panda/lista_panda.tsv, ordenadas por image_id; sorteio uniforme sem reposição de 500 biópsias com
     random.Random(1). Lista gravada em dados/panda/lista_panda_externo.tsv.
  Extração de patches e embeddings: idêntica à de panda_baixar_e_embutir.py (patches de 128 µm no nível 0, máscara de
     tecido Otsu na saturação, até 2.000 patches com random.Random(0), UNI2-h congelado, frações da máscara em
     mascara_frac.npy).
  Imagens temporárias: baixadas em <HD>/Dados Gerais/PANDA/externo/ para não tocar nas 900 biópsias anteriores; com
     --apagar (padrão na etapa embutir), cada TIFF de imagem e máscara é apagado logo após gravar meta.json.

Uso (venv do projeto, HD montado, internet):
    .venv/bin/python dados/panda/panda_externo_baixar.py --sortear
    .venv/bin/python dados/panda/panda_externo_baixar.py --etapa baixar
    .venv/bin/python dados/panda/panda_externo_baixar.py --etapa embutir
    .venv/bin/python dados/panda/panda_externo_baixar.py --etapa tudo
Saída: resultados/panda_externo/<image_id>/{amostra2000.npy, amostra2000_xy.csv, mascara_frac.npy, meta.json}
"""

import argparse
import csv
import json
import random
import subprocess
import sys
import time
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

from comum.lamina import RESULTADOS_DIR  # noqa: E402
from panda_baixar_e_embutir import COMPETICAO, KAGGLE, LISTA as LISTA_ANTIGA, embutir, pasta_panda  # noqa: E402

N_EXTERNO = 500
SEMENTE_SORTEIO = 1
ADIANTE = 3
LISTA = Path(__file__).resolve().parent / "lista_panda_externo.tsv"
SAIDA = RESULTADOS_DIR / "panda_externo"


def pasta_externo():
    return pasta_panda() / "externo"


def sortear():
    usadas = {r["image_id"] for r in csv.DictReader(open(LISTA_ANTIGA, encoding="utf-8"), delimiter="\t")}
    candidatas = sorted(
        [r for r in csv.DictReader(open(pasta_panda() / "train.csv", encoding="utf-8"))
         if r["data_provider"] == "karolinska" and r["image_id"] not in usadas],
        key=lambda r: r["image_id"],
    )
    rng = random.Random(SEMENTE_SORTEIO)
    escolhidas = sorted(rng.sample(candidatas, N_EXTERNO), key=lambda r: r["image_id"])
    saida = [{**r, "conjunto": "externo"} for r in escolhidas]
    with open(LISTA, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["image_id", "data_provider", "isup_grade", "gleason_score", "conjunto"], delimiter="\t")
        w.writeheader()
        w.writerows(saida)
    cont = Counter(r["isup_grade"] for r in saida)
    print(f"{len(saida)} biópsias sorteadas em {LISTA} (de {len(candidatas)} disponíveis)")
    print("distribuição ISUP:", {k: cont[k] for k in "012345"})


def baixar_arquivo(remoto, raiz):
    final = raiz / remoto
    z = final.with_name(final.name + ".zip")
    if final.exists() and final.stat().st_size > 0:
        return final
    saida = ""
    for _ in range(2):
        for espera in (60, 120, 300, 600, 900, 0):
            if z.exists():
                break
            r = subprocess.run([KAGGLE, "competitions", "download", "-c", COMPETICAO, "-f", remoto, "-p", str(raiz), "-q"],
                               capture_output=True, text=True, timeout=1800)
            saida = f"{r.stdout.strip()[-200:]} {r.stderr.strip()[-200:]}"
            if "429" not in saida or not espera:
                break
            time.sleep(espera)
        if not z.exists():
            if "429" in saida:
                raise RuntimeError(f"{remoto}: limite de requisições do Kaggle persistiu")
            break
        try:
            with zipfile.ZipFile(z) as zf:
                nomes = zf.namelist()
                if nomes != [final.name]:
                    raise RuntimeError(f"zip inesperado: {nomes}")
                zf.extractall(final.parent)
            z.unlink()
            break
        except zipfile.BadZipFile:
            z.unlink()
    if not final.exists() or final.stat().st_size == 0:
        raise FileNotFoundError(f"{remoto}: {saida}")
    return final


def baixar_par(l, raiz):
    img = baixar_arquivo(f"train_images/{l['image_id']}.tiff", raiz)
    try:
        mask = baixar_arquivo(f"train_label_masks/{l['image_id']}_mask.tiff", raiz)
    except FileNotFoundError:
        mask = None
    return img, mask


def carregar_lista():
    return list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))


def etapa_baixar():
    linhas = carregar_lista()
    raiz = pasta_externo()
    for sub in ("train_images", "train_label_masks"):
        (raiz / sub).mkdir(parents=True, exist_ok=True)
    pendentes = [
        (i, l) for i, l in enumerate(linhas, 1)
        if not (SAIDA / l["image_id"] / "meta.json").exists()
        and not (raiz / "train_images" / f"{l['image_id']}.tiff").exists()
    ]
    print(f"baixar: {len(pendentes)} pendentes de {len(linhas)}", flush=True)
    falhas = []
    with ThreadPoolExecutor(max_workers=ADIANTE) as ex:
        futs = [(i, l, ex.submit(baixar_par, l, raiz)) for i, l in pendentes]
        for i, l, fut in futs:
            try:
                img, mask = fut.result()
                if i % 25 == 0 or i == len(linhas):
                    print(f"  [{i}/{len(linhas)}] {l['image_id'][:10]} ok (máscara {'sim' if mask else 'não'})", flush=True)
            except Exception as e:  # noqa: BLE001
                falhas.append(l["image_id"])
                print(f"  [{i}/{len(linhas)}] {l['image_id']}: FALHOU ({type(e).__name__}: {e})", flush=True)
    print(f"fim baixar: {len(pendentes) - len(falhas)} baixadas, {len(falhas)} falhas", flush=True)


def etapa_embutir(apagar=True, baixar_se_faltar=False):
    linhas = carregar_lista()
    raiz = pasta_externo()
    for sub in ("train_images", "train_label_masks"):
        (raiz / sub).mkdir(parents=True, exist_ok=True)
    pendentes = [(i, l) for i, l in enumerate(linhas, 1) if not (SAIDA / l["image_id"] / "meta.json").exists()]
    print(f"embutir: {len(pendentes)} pendentes de {len(linhas)}", flush=True)
    falhas, downloads = [], {}
    with ThreadPoolExecutor(max_workers=ADIANTE) as ex:
        for j, (i, l) in enumerate(pendentes):
            if baixar_se_faltar:
                for _, prox in pendentes[j:j + ADIANTE]:
                    if prox["image_id"] not in downloads:
                        downloads[prox["image_id"]] = ex.submit(baixar_par, prox, raiz)
            pasta = SAIDA / l["image_id"]
            pasta.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            try:
                if baixar_se_faltar:
                    img, mask = downloads.pop(l["image_id"]).result()
                else:
                    img = raiz / "train_images" / f"{l['image_id']}.tiff"
                    if not img.exists():
                        img, mask = baixar_par(l, raiz)
                    else:
                        m = raiz / "train_label_masks" / f"{l['image_id']}_mask.tiff"
                        mask = m if m.exists() else None
                meta = {**{k: l[k] for k in ("image_id", "data_provider", "isup_grade", "gleason_score", "conjunto")},
                        **embutir(img, mask, pasta)}
                (pasta / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
                if apagar:
                    if img.exists():
                        img.unlink()
                    if mask is not None and mask.exists():
                        mask.unlink()
                print(f"[{i}/{len(linhas)}] ISUP {l['isup_grade']}: {meta['n_amostra']}/{meta['n_tecido']} patches, "
                      f"máscara {'sim' if meta['mascara'] else 'não'} ({time.time() - t0:.1f} s)", flush=True)
            except Exception as e:  # noqa: BLE001
                falhas.append(l["image_id"])
                print(f"[{i}/{len(linhas)}] {l['image_id']}: FALHOU ({type(e).__name__}: {e})", flush=True)
    print(f"fim embutir: {len(pendentes) - len(falhas)} prontas, {len(falhas)} falhas", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sortear", action="store_true")
    p.add_argument("--etapa", choices=["baixar", "embutir", "tudo"], default="tudo")
    p.add_argument("--manter-imagens", action="store_true", help="não apagar TIFFs temporários após embutir")
    a = p.parse_args()
    if a.sortear:
        sortear()
    elif a.etapa == "baixar":
        etapa_baixar()
    elif a.etapa == "embutir":
        etapa_embutir(apagar=not a.manter_imagens, baixar_se_faltar=False)
    else:
        etapa_embutir(apagar=not a.manter_imagens, baixar_se_faltar=True)
