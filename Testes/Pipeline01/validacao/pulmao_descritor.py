"""
Descritor de pulmão: o equivalente, pro pulmão, do descritor treinado nas regiões anotadas do BRACS. Classe de
cada patch de 128 µm (normal, adenocarcinoma, carcinoma escamoso) a partir do embedding do UNI2-h, treinada nas
imagens do LungHist700 (Diosdado et al., Scientific Data 2024; CC BY 4.0; 691 imagens de 45 pacientes, classificadas
por patologista; Hospital Clínico de Valladolid).

Fixado ANTES de rodar (commit anterior aos resultados; a escala vem de scripts/escala_lunghist.py):
  Patches: cada imagem é cortada em patches de 128 µm (lado = round(128 / escala) px, escala do 20x ou do 40x),
     sem sobreposição; mesmo pré-processamento da pipeline (256 -> 224). Tecido: pixel com saturação (HSV, 0-255,
     mediana 7x7) > 20; entra o patch com >= 25% de tecido. Não é a máscara da pipeline (Otsu na saturação): numa
     foto toda coberta de tecido o Otsu corta o tecido ao meio. O limiar de 25% (e não 50%) é porque na lâmina inteira
     a máscara sai de uma miniatura 32x menor, onde o espaço alveolar conta como tecido; em pixel cheio, um campo de
     pulmão normal tem ~55-85% de tecido.
     Rótulo do patch = superclasse da imagem (nor, aca, scc).
  Separação por paciente: cada paciente vai pra classe com mais imagens dele; dentro de cada classe, 20% dos
     pacientes (arredondado, mínimo 1) sorteados com semente 0 vão pro teste.
  Modelo: categoria_uni.logistica_multinomial (padronizada, pesos balanceados, L2 ~ C=1), 3 classes.
  Critério D1 (patches dos pacientes de teste): acurácia balanceada nas 3 classes >= 0,80.
  Também reportado (sem critério): acerto por classe; acurácia por imagem (média das probabilidades dos patches).
  Pra aplicar no TCGA (tcga_descritor_prelaudo.py), o modelo é retreinado com todos os 45 pacientes.

Uso (venv do projeto, HD montado):
    .venv/bin/python validacao/pulmao_descritor.py
Saída: resultados/lunghist700/{embeddings.npz, descritor.json}
"""

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import numpy as np

from comum.lamina import RESULTADOS_DIR

CLASSES = ["nor", "aca", "scc"]
NOME_PT = {"nor": "pulmão normal", "aca": "adenocarcinoma", "scc": "carcinoma escamoso"}
LADO_UM = 128.0
MIN_TECIDO = 0.25
LIMIAR_S = 20
FRACAO_TESTE = 0.2
BA_MIN = 0.80
SAIDA = RESULTADOS_DIR / "lunghist700"


def escala():
    e = json.loads((SAIDA / "escala.json").read_text(encoding="utf-8"))
    return {"20x": e["20x"]["mpp"], "40x": e["40x"]["mpp"]}


def embeddings():
    """Embeddings UNI2-h de todos os patches; cache em embeddings.npz."""
    cache = SAIDA / "embeddings.npz"
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        return z["X"], list(z["classe"]), list(z["paciente"]), list(z["imagem"])
    from comum.uni import embeddings_uni2h_de_recortes
    from escala_lunghist import imagens_lunghist
    mpp = escala()
    X, classe, paciente, imagem = [], [], [], []
    for i, (caminho, sup, _, aumento, pac) in enumerate(imagens_lunghist(), 1):
        rgb = cv2.cvtColor(cv2.imread(str(caminho)), cv2.COLOR_BGR2RGB)
        mask = cv2.medianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 1], 7) > LIMIAR_S
        lado = round(LADO_UM / mpp[aumento])
        recortes = [rgb[y:y + lado, x:x + lado] for y in range(0, rgb.shape[0] - lado + 1, lado)
                    for x in range(0, rgb.shape[1] - lado + 1, lado) if mask[y:y + lado, x:x + lado].mean() >= MIN_TECIDO]
        if recortes:
            X.append(embeddings_uni2h_de_recortes(recortes))
            classe += [sup] * len(recortes)
            paciente += [pac] * len(recortes)
            imagem += [caminho.name] * len(recortes)
        if i % 50 == 0:
            print(f"  {i} imagens, {len(classe)} patches", flush=True)
    X = np.concatenate(X).astype(np.float32)
    np.savez(cache, X=X, classe=np.array(classe), paciente=np.array(paciente), imagem=np.array(imagem))
    return X, classe, paciente, imagem


def acuracia_balanceada(reais, preditas):
    return float(np.mean([np.mean([p == c for r, p in zip(reais, preditas) if r == c]) for c in CLASSES if c in reais]))


def separar(classe, paciente):
    por_pac = defaultdict(Counter)
    for c, p in zip(classe, paciente):
        por_pac[p][c] += 1
    principal = {p: cont.most_common(1)[0][0] for p, cont in por_pac.items()}
    teste = set()
    rng = random.Random(0)
    for c in CLASSES:
        pacs = sorted(p for p, k in principal.items() if k == c)
        teste |= set(rng.sample(pacs, max(1, math.floor(FRACAO_TESTE * len(pacs) + 0.5))))
    return teste


def aplicar_todos(blocos):
    """Modelo final (todos os 45 pacientes), treinado uma vez e aplicado a cada bloco de embeddings de fora do
    LungHist700: devolve uma lista de probabilidades [n_i, 3]."""
    from categoria_uni import logistica_multinomial
    X, classe, _, _ = embeddings()
    y = np.array([CLASSES.index(c) for c in classe])
    P = np.asarray(logistica_multinomial(X, y, np.concatenate(blocos), k=3, probabilidades=True))
    return np.split(P, np.cumsum([len(b) for b in blocos])[:-1])


def main():
    from categoria_uni import logistica_multinomial
    SAIDA.mkdir(parents=True, exist_ok=True)
    X, classe, paciente, imagem = embeddings()
    teste = separar(classe, paciente)
    tr = np.array([p not in teste for p in paciente])
    y = np.array([CLASSES.index(c) for c in classe])
    P = logistica_multinomial(X[tr], y[tr], X[~tr], k=3, probabilidades=True)
    P = np.asarray(P)
    real = [classe[i] for i in np.where(~tr)[0]]
    pred = [CLASSES[k] for k in P.argmax(1)]
    ba = acuracia_balanceada(real, pred)
    por_img = defaultdict(list)
    for i, p in zip(np.where(~tr)[0], P):
        por_img[imagem[i]].append(p)
    img_real = {imagem[i]: classe[i] for i in np.where(~tr)[0]}
    img_pred = {k: CLASSES[int(np.mean(v, 0).argmax())] for k, v in por_img.items()}
    resumo = {"pacientes_teste": sorted(teste), "n_pacientes_teste": len(teste),
              "patches_treino": int(tr.sum()), "patches_teste": int((~tr).sum()),
              "patches_por_classe": dict(Counter(classe)),
              "acuracia_balanceada_patches": round(ba, 3),
              "por_classe_patches": {c: f"{sum(a == b == c for a, b in zip(real, pred))}/{real.count(c)}" for c in CLASSES},
              "matriz_confusao": {c: dict(Counter(b for a, b in zip(real, pred) if a == c)) for c in CLASSES},
              "acuracia_balanceada_imagens": round(acuracia_balanceada(list(img_real.values()), [img_pred[k] for k in img_real]), 3),
              "imagens_teste": len(img_real), "escala_mpp": escala()}
    resumo["criterio_D1"] = ba >= BA_MIN
    (SAIDA / "descritor.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k != "pacientes_teste"}, indent=2, ensure_ascii=False))
    print(f"Critério D1 fixado antes (acurácia balanceada nos patches >= {BA_MIN}): {'SIM' if resumo['criterio_D1'] else 'NÃO'}")


if __name__ == "__main__":
    main()
