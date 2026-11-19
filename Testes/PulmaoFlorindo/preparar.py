"""
Prepara o dataset de pulmão (Adenocarcinoma × Carcinoma Epidermoide, 52 pacientes) para testar.py: códigos dos casos,
partes da validação cruzada, posição de cada núcleo no campo de origem, medidas clássicas dos núcleos e embeddings
do UNI2-h. Tudo vai para resultados/ (fora do git: o dataset não é público).

Achado que define a preparação: as imagens da subpasta de "citologia" (N<caso>/) são núcleos recortados dos próprios
campos de biópsia (nome <campo><nn>.BMP; o recorte aparece pixel a pixel no campo). Então cada núcleo tem posição e
máscara conhecidas no campo, e dá pra comparar o núcleo isolado com o mesmo núcleo junto do tecido em volta.

Imagens que vão para o UNI2-h (224 x 224, normalização do ImageNet):
  campos:        cada campo de 620 x 480 reduzido à metade (310 x 240) e dois recortes de 224 (x = 0 e x = 86, y = 8).
  nucleo_05:     janela de 448 px em volta do núcleo, reduzida à metade; fora da máscara do núcleo, branco.
  contexto_05:   a mesma janela, sem pintar nada (núcleo + tecido em volta).
  nucleo_10 e contexto_10: o mesmo com janela de 224 px, sem reduzir (escala original).
  A janela fica centrada no núcleo e é deslocada para caber no campo (nunca sai da imagem); o núcleo fica na mesma
  posição nas duas versões. Correção feita depois de um erro na primeira execução e antes de qualquer resultado:
  quando o núcleo é maior que a janela (só 1 dos 5.593, com 227 px, na janela de 224), a janela cresce até caber o
  núcleo e é reduzida para 224; as medidas clássicas desse núcleo usam essa janela maior.
Medidas clássicas de cada núcleo (escala original): forma (área, perímetro, excentricidade, solidez, circularidade,
  eixos, razão dos eixos, extensão), cor (média e desvio de R, G, B, hematoxilina e eosina dentro da máscara) e textura
  (GLCM em 32 níveis dentro da máscara, distâncias 1 e 3, média de 4 ângulos: contraste, dissimilaridade,
  homogeneidade, energia, correlação, ASM).
Partes: 5 repetições de validação cruzada em 5 partes por paciente, estratificadas por classe (repetição r: semente r).

Uso (venv da Pipeline01; GPU):
    ../Pipeline01/.venv/bin/python preparar.py <pasta do dataset com labels.xlsx e original/>
"""

import csv
import json
import random
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "Pipeline01"))
import comum.caminhos  # noqa: E402,F401

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import openpyxl  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402
from skimage.color import rgb2hed  # noqa: E402
from skimage.feature import graycomatrix, graycoprops  # noqa: E402
from skimage.measure import regionprops  # noqa: E402

from comum.modelo import dispositivo  # noqa: E402
from comum.uni import DESVIO_IMAGENET, LOTE, MEDIA_IMAGENET, carregar_uni2h  # noqa: E402

SAIDA = AQUI / "resultados"
CLASSES = {"Adenocarcinoma": 0, "Epidermoid Carcinoma": 1}
REPETICOES, PARTES = 5, 5
JANELAS = {"05": 448, "10": 224}


def ler(f):
    return np.asarray(Image.open(f).convert("RGB"))


def casos(raiz):
    linhas = list(openpyxl.load_workbook(raiz / "labels.xlsx", read_only=True).worksheets[0].iter_rows(values_only=True))
    lab = {}
    for r in linhas[1:]:
        if r[1] and r[4]:
            a, b = str(r[1]).split("-")
            lab[f"{int(a):05d}-{b}"] = CLASSES[r[4]]
    pastas = sorted(p.name for p in (raiz / "original").iterdir() if p.is_dir())
    assert sorted(lab) == pastas, "rótulos e pastas não batem"
    return [(f"caso_{i:02d}", p, lab[p]) for i, p in enumerate(pastas, 1)]


def partes(lista):
    out = {c: [] for c, _, _ in lista}
    for r in range(REPETICOES):
        rng = random.Random(r)
        for k in (0, 1):
            cs = [c for c, _, y in lista if y == k]
            rng.shuffle(cs)
            for j, c in enumerate(cs):
                out[c].append(j % PARTES)
    return out


def localizar(nucleo, campo):
    m = nucleo.astype(np.int32).sum(2) < 765
    ys, xs = np.where(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    t, mk = nucleo[y0:y1, x0:x1].astype(np.float32), m[y0:y1, x0:x1]
    r = cv2.matchTemplate(campo.astype(np.float32), t, cv2.TM_SQDIFF, mask=np.repeat(mk[..., None], 3, 2).astype(np.float32))
    v, _, (x, y), _ = cv2.minMaxLoc(r)
    return int(x), int(y), mk, float(v / (mk.sum() * 3))


def janela(campo, x, y, mk, lado):
    """Recorte de lado x lado centrado no núcleo, deslocado pra caber no campo; e a máscara do núcleo no recorte."""
    H, W = campo.shape[:2]
    lado = max(lado, *mk.shape)  # 1 núcleo dos 5.593 (227 px) não cabe na janela de 224: a janela cresce e vai a 224
    cy, cx = y + mk.shape[0] // 2, x + mk.shape[1] // 2
    j0 = min(max(cy - lado // 2, 0), H - lado)
    i0 = min(max(cx - lado // 2, 0), W - lado)
    rec = campo[j0:j0 + lado, i0:i0 + lado]
    m = np.zeros((lado, lado), bool)
    m[y - j0:y - j0 + mk.shape[0], x - i0:x - i0 + mk.shape[1]] = mk
    return rec, m


def para_224(img):
    if img.shape[0] != 224:
        img = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)
    return ((img.astype(np.float32) / 255 - MEDIA_IMAGENET) / DESVIO_IMAGENET).transpose(2, 0, 1)


class Embutidor:
    def __init__(self):
        self.modelo, self.fila, self.saida = carregar_uni2h(), [], []

    def add(self, img):
        self.fila.append(para_224(img))
        if len(self.fila) == LOTE:
            self.esvaziar()

    def esvaziar(self):
        if self.fila:
            x = torch.from_numpy(np.stack(self.fila)).to(dispositivo())
            with torch.no_grad():
                self.saida.append(self.modelo(x.half() if dispositivo() == "cuda" else x).float().cpu().numpy())
            self.fila = []

    def tudo(self):
        self.esvaziar()
        return np.concatenate(self.saida).astype(np.float16)


NOMES_CLASSICOS = (["area", "perimetro", "excentricidade", "solidez", "circularidade", "eixo_maior", "eixo_menor",
                    "razao_eixos", "extensao"]
                   + [f"{e}_{c}" for c in ("R", "G", "B", "H", "E") for e in ("media", "desvio")]
                   + [f"glcm_{p}_d{d}" for d in (1, 3) for p in ("contrast", "dissimilarity", "homogeneity", "energy",
                                                                "correlation", "ASM")])


def classicas(rec, m):
    p = regionprops(m.astype(np.uint8))[0]
    forma = [p.area, p.perimeter, p.eccentricity, p.solidity, 4 * np.pi * p.area / max(p.perimeter, 1) ** 2,
             p.axis_major_length, p.axis_minor_length, p.axis_minor_length / max(p.axis_major_length, 1e-6), p.extent]
    hed = rgb2hed(rec)
    canais = [rec[..., 0], rec[..., 1], rec[..., 2], hed[..., 0], hed[..., 1]]
    cor = [f(c[m]) for c in canais for f in (np.mean, np.std)]
    y0, x0, y1, x1 = p.bbox
    cinza = cv2.cvtColor(np.ascontiguousarray(rec[y0:y1, x0:x1]), cv2.COLOR_RGB2GRAY)
    q = (cinza.astype(np.int32) * 31 // 255 + 1).astype(np.uint8)
    q[~m[y0:y1, x0:x1]] = 0
    textura = []
    for d in (1, 3):
        P = graycomatrix(q, [d], [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4], levels=33)[1:, 1:].astype(np.float64)
        textura += [float(graycoprops(P, prop).mean()) for prop in ("contrast", "dissimilarity", "homogeneity",
                                                                    "energy", "correlation", "ASM")]
    return [float(v) for v in forma + cor + textura]


def main():
    raiz = Path(sys.argv[1])
    SAIDA.mkdir(exist_ok=True)
    lista = casos(raiz)
    pt = partes(lista)
    with open(SAIDA / "casos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["codigo", "pasta_original", "classe", *[f"parte_r{r}" for r in range(REPETICOES)]])
        for c, p, y in lista:
            w.writerow([c, p, y, *pt[c]])

    emb = {nome: Embutidor() for nome in ("campos", "nucleo_05", "contexto_05", "nucleo_10", "contexto_10")}
    idx_campos, idx_nucleos, feats, piores = [], [], [], 0.0
    for c, pasta, y in lista:
        P = raiz / "original" / pasta
        sub = next(s for s in P.iterdir() if s.is_dir())
        campos = {f.stem: ler(f) for f in sorted(P.glob("*.BMP"))}
        for k, img in campos.items():
            meia = cv2.resize(img, (310, 240), interpolation=cv2.INTER_AREA)
            for x in (0, 86):
                emb["campos"].add(meia[8:232, x:x + 224])
                idx_campos.append(c)
        for f in sorted(sub.glob("*.BMP")):
            campo = campos[f.stem[:8]]
            x, y0, mk, erro = localizar(ler(f), campo)
            piores = max(piores, erro)
            for esc, lado in JANELAS.items():
                rec, m = janela(campo, x, y0, mk, lado)
                so = rec.copy()
                so[~m] = 255
                emb[f"nucleo_{esc}"].add(so)
                emb[f"contexto_{esc}"].add(rec)
            rec, m = janela(campo, x, y0, mk, 224)
            feats.append(classicas(rec, m))
            idx_nucleos.append(c)
        print(f"{c}: {len(campos)} campos, {sum(1 for _ in sub.glob('*.BMP'))} núcleos", flush=True)
    for nome, e in emb.items():
        np.save(SAIDA / f"emb_{nome}.npy", e.tudo())
    np.save(SAIDA / "classicas.npy", np.array(feats, np.float64))
    json.dump({"campos": idx_campos, "nucleos": idx_nucleos, "classicas": NOMES_CLASSICOS,
               "maior_erro_de_localizacao": piores}, open(SAIDA / "indices.json", "w"))
    print(f"pronto; maior erro de localização dos núcleos (EQM por pixel): {piores:.3f}")


if __name__ == "__main__":
    main()
