"""
Classificação da lâmina inteira, sem o modelo de linguagem decidir a classe, e descritor treinado
com as RoIs de treino do BRACS. Ataca o gargalo do teste externo: a pipeline chamou 55 de 57
lâminas de malignas (poucos patches malignos falsos viravam a lâmina toda maligna).

Fixado ANTES de rodar (commit anterior aos resultados):
  A) Descritor "rois": de cada RoI de treino do BRACS (3.655 recortes, pasta train/ do conjunto
     BRACS_RoI), até 16 patches de 512 px (128 µm a 0,25 µm/px) com >= 50% de tecido, sorteados com
     semente 0; RoI menor que 512 px de lado entra com um patch, completado com branco. Cada patch
     recebe a classe da RoI. Escala: todos os recortes tratados como 0,25 µm/px (numa amostra de 300,
     293 batem com a anotação nessa escala). Mesma hierarquia do descritor atual (categoria ->
     DCIS/IC), mesma logística. As RoIs de validação (312) só servem pra conferência.
     Descritor "atual": o de descritor_uni.py (patches rotulados das 18 lâminas de desenvolvimento).
  B) Classe da lâmina por regra de proporção: até 2.000 patches de tecido sorteados da lâmina (semente
     0), classificados pelo descritor; frações f_mal, f_at e f_ic (fração de IC entre os malignos):
        f_mal >= t_m -> IC se f_ic >= t_ic, senão DCIS;  senão f_at >= t_a -> atípico;  senão benigno.
     t_m, t_a, t_ic em {0,05; 0,10; ...; 0,60}, escolhidos nas 18 lâminas de desenvolvimento pela maior
     acurácia balanceada (empate: maior acurácia, depois maior t_m, maior t_a, menor t_ic). Nas lâminas
     de desenvolvimento, o descritor que classifica cada lâmina nunca a viu (treino sem aquela lâmina
     e sem as RoIs dela).
  Avaliação: as 57 lâminas do teste externo (prelaudo_teste_externo.py), 4 classes.
     E0 = pipeline atual (modelo de linguagem + regra do componente invasivo): 16/57.
     E1 = regra de proporção + descritor atual.  E2 = regra de proporção + descritor "rois".
     Métrica principal: acurácia balanceada (média do acerto por classe). Também acurácia e o
     subconjunto com uma lâmina por paciente.
  Critério de "funcionou": acurácia balanceada de E2 > E0 e > E1 nas 57.

Uso (venv do projeto; etapas 1 e 2 usam a GPU):
    .venv/bin/python validacao/lamina_inteira.py --etapa rois       # embeddings dos patches das RoIs
    .venv/bin/python validacao/lamina_inteira.py --etapa amostras   # embeddings de 2.000 patches por lâmina
    .venv/bin/python validacao/lamina_inteira.py --etapa avaliar    # treino, limiares e avaliação
"""

import argparse
import csv
import itertools
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import cv2
import numpy as np
from PIL import Image

from comum.bancos import CATEGORIA_DA_CLASSE
from comum.lamina import RESULTADOS_DIR, TILE_NATIVO, Lamina, dir_resultados, ler_caminhos, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import info_lamina
from comum.tecido import mascara_tecido

Image.MAX_IMAGE_PIXELS = None
MAX_PATCHES_ROI = 16
N_AMOSTRA = 2000
MIN_TECIDO = 0.5
GRADE = [round(0.05 * i, 2) for i in range(1, 13)]
CATEGORIAS = ["benigno", "atipico", "maligno"]
FINAIS = ["benigno", "atipico", "DCIS", "IC"]
SAIDA = RESULTADOS_DIR / "lamina_inteira"


def classe_final(c):
    return {"N": "benigno", "PB": "benigno", "UDH": "benigno", "FEA": "atipico", "ADH": "atipico"}.get(c, c)


# ---------- etapa 1: patches das RoIs ----------
def patches_da_roi(caminho, rng):
    try:
        rgb = np.array(Image.open(caminho).convert("RGB"))
    except OSError as e:  # ex.: BRACS_773_UDH_20.png está truncado no dataset local
        print(f"  {caminho.name}: recorte ilegível ({e}), pulado", flush=True)
        return []
    h, w = rgb.shape[:2]
    if h < TILE_NATIVO or w < TILE_NATIVO:
        pad = np.full((max(h, TILE_NATIVO), max(w, TILE_NATIVO), 3), 255, np.uint8)
        pad[:h, :w] = rgb
        rgb, h, w = pad, pad.shape[0], pad.shape[1]
    f = 8
    mask = mascara_tecido(cv2.resize(rgb, (max(w // f, 1), max(h // f, 1)), interpolation=cv2.INTER_AREA)) > 0
    pos = []
    for y in range(0, h - TILE_NATIVO + 1, TILE_NATIVO):
        for x in range(0, w - TILE_NATIVO + 1, TILE_NATIVO):
            m = mask[y // f:(y + TILE_NATIVO) // f, x // f:(x + TILE_NATIVO) // f]
            if m.size and m.mean() >= MIN_TECIDO:
                pos.append((x, y))
    rng.shuffle(pos)
    return [rgb[y:y + TILE_NATIVO, x:x + TILE_NATIVO] for x, y in pos[:MAX_PATCHES_ROI]]


def etapa_rois():
    from comum.uni import embeddings_uni2h_de_recortes
    raiz = Path(ler_caminhos()["roi_dataset"])
    SAIDA.mkdir(parents=True, exist_ok=True)
    for divisao in ("train", "val"):
        arq = SAIDA / f"rois_{divisao}.npz"
        if arq.exists():
            continue
        embs, classes, laminas, rois = [], [], [], []
        recortes = sorted(raiz.glob(f"{divisao}/*/*.png"))
        rng = random.Random(0)
        for i, p in enumerate(recortes, 1):
            m = re.match(r"(BRACS_\d+)_([A-Z]+)_\d+", p.stem)
            patches = patches_da_roi(p, rng)
            if patches:
                embs.append(embeddings_uni2h_de_recortes(patches).astype(np.float16))
                classes += [m.group(2)] * len(patches)
                laminas += [m.group(1)] * len(patches)
                rois += [p.stem] * len(patches)
            if i % 200 == 0:
                print(f"  {divisao}: {i}/{len(recortes)} RoIs, {len(classes)} patches", flush=True)
        np.savez(arq, embs=np.concatenate(embs), classes=np.array(classes), laminas=np.array(laminas), rois=np.array(rois))
        print(f"  {divisao}: {len(classes)} patches de {len(set(rois))} RoIs", flush=True)


# ---------- etapa 2: amostra de patches por lâmina ----------
def laminas_dev():
    from descritor_uni import LAMINAS_TREINO
    return list(LAMINAS_TREINO)


def laminas_teste():
    from prelaudo_teste_externo import laminas
    return laminas()


def etapa_amostras():
    from comum.uni import embeddings_uni2h
    for s in laminas_dev() + laminas_teste():
        _, xy = carregar_embeddings_cacheados(dir_resultados(s, "estagio2"))
        amostra = sorted(random.Random(0).sample(xy, min(N_AMOSTRA, len(xy))))
        embeddings_uni2h(Lamina(resolver_svs(s)), amostra, f"amostra{N_AMOSTRA}")
        print(f"  {s}: {len(amostra)} patches", flush=True)


def amostra(s):
    return np.load(dir_resultados(s, "uni2h") / f"amostra{N_AMOSTRA}.npy").astype(np.float32)


# ---------- etapa 3: treino, limiares, avaliação ----------
def treinar_e_prever(X1, y1, X2, y2, X):
    """Probabilidades de nível 1 (3 categorias) e nível 2 (DCIS, IC) pra X."""
    from categoria_uni import logistica_multinomial
    return (logistica_multinomial(X1, y1, X, k=3, probabilidades=True),
            logistica_multinomial(X2, y2, X, k=2, probabilidades=True))


def fracoes(p1, p2):
    cat = p1.argmax(1)
    mal = cat == 2
    return {"f_mal": float(mal.mean()), "f_at": float((cat == 1).mean()),
            "f_ic": float((p2[mal].argmax(1) == 1).mean()) if mal.any() else 0.0}


def regra(fr, t_m, t_a, t_ic):
    if fr["f_mal"] >= t_m:
        return "IC" if fr["f_ic"] >= t_ic else "DCIS"
    return "atipico" if fr["f_at"] >= t_a else "benigno"


def acuracia_balanceada(reais, preditas):
    por = [np.mean([p == c for r, p in zip(reais, preditas) if r == c]) for c in FINAIS if c in reais]
    return float(np.mean(por))


def escolher_limiares(fr_dev, reais_dev):
    melhor = None
    for t_m, t_a, t_ic in itertools.product(GRADE, GRADE, GRADE):
        pred = [regra(fr_dev[s], t_m, t_a, t_ic) for s in fr_dev]
        chave = (acuracia_balanceada(reais_dev, pred), np.mean([p == r for p, r in zip(pred, reais_dev)]), t_m, t_a, -t_ic)
        if melhor is None or chave > melhor[0]:
            melhor = (chave, (t_m, t_a, t_ic))
    return melhor[1], melhor[0][0]


def dados_descritor_atual():
    from descritor_uni import rotulados
    D = {s: rotulados(s) for s in laminas_dev()}
    def treino(excluir=None):
        ds = [d for s, d in D.items() if s != excluir]
        X1 = np.concatenate([d["uni2h"] for d in ds]); y1 = np.concatenate([d["categoria"] for d in ds])
        sel = [(d["uni2h"][i], ["DCIS", "IC"].index(c)) for d in ds for i, c in enumerate(d["classe"]) if c in ("DCIS", "IC")]
        return X1, y1, np.array([a for a, _ in sel]), np.array([b for _, b in sel])
    return treino


def dados_descritor_rois():
    z = np.load(SAIDA / "rois_train.npz")
    embs, classes, laminas = z["embs"].astype(np.float32), z["classes"], z["laminas"]
    cat = np.array([CATEGORIAS.index(CATEGORIA_DA_CLASSE[c]) for c in classes])
    def treino(excluir=None):
        ok = laminas != excluir if excluir else np.ones(len(classes), bool)
        mal = ok & np.isin(classes, ["DCIS", "IC"])
        return embs[ok], cat[ok], embs[mal], (classes[mal] == "IC").astype(int)
    return treino


def conferencia_val(treino_rois):
    z = np.load(SAIDA / "rois_val.npz")
    p1, p2 = treinar_e_prever(*treino_rois(), z["embs"].astype(np.float32))
    reais = [CATEGORIA_DA_CLASSE[c] for c in z["classes"]]
    pred = [CATEGORIAS[i] for i in p1.argmax(1)]
    return {c: round(float(np.mean([p == c for r, p in zip(reais, pred) if r == c])), 3) for c in CATEGORIAS}


def etapa_avaliar():
    dev, teste = laminas_dev(), laminas_teste()
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in dev + teste}
    resumo = {}
    descritores = {"E1_atual": dados_descritor_atual(), "E2_rois": dados_descritor_rois()}
    resumo["conferencia_rois_val_por_patch"] = conferencia_val(descritores["E2_rois"])
    print("conferência nas RoIs de validação (acerto por patch):", resumo["conferencia_rois_val_por_patch"], flush=True)
    for nome, treino in descritores.items():
        fr_dev = {}
        for s in dev:
            fr_dev[s] = fracoes(*treinar_e_prever(*treino(excluir=s), amostra(s)))
            print(f"  {nome} dev {s}: {fr_dev[s]}", flush=True)
        (t_m, t_a, t_ic), ba_dev = escolher_limiares(fr_dev, [real[s] for s in dev])
        X1, y1, X2, y2 = treino()
        fr_te = {}
        for s in teste:
            fr_te[s] = fracoes(*treinar_e_prever(X1, y1, X2, y2, amostra(s)))
        pred = {s: regra(fr_te[s], t_m, t_a, t_ic) for s in teste}
        resumo[nome] = {"limiares": {"t_m": t_m, "t_a": t_a, "t_ic": t_ic}, "acuracia_balanceada_dev": round(ba_dev, 3),
                        "predito": pred, "fracoes_teste": fr_te, "fracoes_dev": fr_dev}
        print(f"{nome}: limiares {resumo[nome]['limiares']} (dev: {ba_dev:.3f})", flush=True)

    e0 = json.loads((RESULTADOS_DIR / "prelaudo_teste_externo.json").read_text(encoding="utf-8"))
    resumo["E0_pipeline_atual"] = {"predito": {s: e0[f"{s}|v2"]["predito"] for s in teste}}
    from prelaudo_teste_externo import um_por_paciente
    um = um_por_paciente(teste)
    metricas = {}
    for nome in ("E0_pipeline_atual", "E1_atual", "E2_rois"):
        pred = resumo[nome]["predito"]
        for grupo, stems in (("57", teste), ("um_por_paciente", um)):
            r, p = [real[s] for s in stems], [pred[s] for s in stems]
            metricas[f"{nome}|{grupo}"] = {
                "acuracia_balanceada": round(acuracia_balanceada(r, p), 3), "acertos": sum(a == b for a, b in zip(r, p)),
                "n": len(stems), "por_classe": {c: f"{sum(a == b == c for a, b in zip(r, p))}/{r.count(c)}" for c in FINAIS},
                "preditas": dict(Counter(map(str, p)))}
    resumo["metricas"] = metricas
    ba = {n: metricas[f"{n}|57"]["acuracia_balanceada"] for n in ("E0_pipeline_atual", "E1_atual", "E2_rois")}
    resumo["funcionou"] = ba["E2_rois"] > ba["E0_pipeline_atual"] and ba["E2_rois"] > ba["E1_atual"]
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for k, m in metricas.items():
        print(f"{k:<28} bal {m['acuracia_balanceada']:.3f} | {m['acertos']}/{m['n']} | {m['por_classe']} | {m['preditas']}")
    print(f"\nCritério fixado antes (E2 > E0 e E2 > E1 em acurácia balanceada): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["rois", "amostras", "avaliar"], required=True)
    a = p.parse_args()
    {"rois": etapa_rois, "amostras": etapa_amostras, "avaliar": etapa_avaliar}[a.etapa]()
