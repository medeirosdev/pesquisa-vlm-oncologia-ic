"""
[INCOMPLETO — não rodou até o fim] O problema é o modelo? Repete a classificação de
banco_por_classe.py trocando o QuiltNet-B-32 pelo KEEP (ViT-L/16 + BERT, ~0.4B, MIT).

KEEP carrega via transformers com trust_remote_code=True (executa código do repositório
do modelo) e foi escrito pra transformers 4.34 / timm antigo — conflita com o open_clip
do QuiltNet no mesmo venv. Próximo passo: rodar num venv separado.

Uso:
    .venv/bin/python validacao/teste_modelo_keep.py --svs BRACS_748
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch
from PIL import Image

from comum.bancos import BANCO_POR_CLASSE
from comum.lamina import Lamina, dir_resultados, resolver_svs
from comum.modelo import carregar_embeddings_cacheados
from comum.rois import carregar_rois, rotular_tiles


def rodar(svs=None) -> dict:
    from torchvision import transforms
    from transformers import AutoModel, AutoTokenizer

    lamina = Lamina(resolver_svs(svs))
    _, xy = carregar_embeddings_cacheados(dir_resultados(lamina.stem, "estagio2"))
    rois = [r for r in carregar_rois(lamina.stem) if r["correlacao"] >= 0.5]
    rotulados = rotular_tiles(xy, rois)
    classes = sorted({r["classe_real"] for r in rotulados})

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModel.from_pretrained("Astaxanthin/KEEP", trust_remote_code=True).to(device).eval()
    tokenizer = AutoTokenizer.from_pretrained("Astaxanthin/KEEP", trust_remote_code=True)
    transform = transforms.Compose([
        transforms.Resize(224, interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.CenterCrop((224, 224)), transforms.ToTensor(),
        transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225))])

    emb_classes = {}
    with torch.no_grad():
        for c in classes:
            tok = tokenizer(BANCO_POR_CLASSE[c], max_length=256, padding="max_length", truncation=True,
                            return_tensors="pt").to(device)
            e = model.encode_text(tok)
            emb_classes[c] = e / e.norm(dim=-1, keepdim=True)

    preditas = []
    for i in range(0, len(rotulados), 32):
        lote = rotulados[i:i + 32]
        imgs = torch.stack([transform(Image.fromarray(lamina.janela_nativa(r["x0"], r["y0"]))) for r in lote]).to(device)
        with torch.no_grad():
            e = model.encode_image(imgs)
            e = e / e.norm(dim=-1, keepdim=True)
            s = torch.stack([(e @ emb_classes[c].T).max(dim=1).values for c in classes], dim=1)
        preditas += [classes[j] for j in s.argmax(dim=1).cpu().numpy()]

    reais = [r["classe_real"] for r in rotulados]
    resumo = {"lamina": lamina.stem, "modelo": "Astaxanthin/KEEP", "n": len(reais),
              "acuracia_classes_presentes": round(np.mean([a == b for a, b in zip(reais, preditas)]), 4),
              "baseline_maioria": round(Counter(reais).most_common(1)[0][1] / len(reais), 4)}
    (dir_resultados(lamina.stem, "validacao") / "teste_modelo_keep.json").write_text(
        json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--svs")
    print(json.dumps(rodar(parser.parse_args().svs), indent=2, ensure_ascii=False))
