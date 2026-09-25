"""Classificação zero-shot por banco de frases de classe, compartilhada pelos testes de validação."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from comum.bancos import BANCO_POR_CLASSE
from comum.modelo import codificar_textos, dispositivo


def embeddings_de_classe(classes: list[str]) -> dict:
    return {c: codificar_textos(BANCO_POR_CLASSE[c]) for c in classes}


def classificar(vetores: np.ndarray, emb_classes: dict) -> list[str]:
    """Para cada vetor (já normalizado), a classe cujo banco tem a frase mais similar."""
    classes = list(emb_classes)
    v = torch.from_numpy(np.asarray(vetores, dtype=np.float32)).to(dispositivo())
    with torch.no_grad():
        s = torch.stack([(v @ emb_classes[c].T).max(dim=1).values for c in classes], dim=1)
    return [classes[i] for i in s.argmax(dim=1).cpu().numpy()]


def media_normalizada(vetores: np.ndarray) -> np.ndarray:
    m = np.asarray(vetores).mean(axis=0, keepdims=True)
    return m / np.linalg.norm(m)


def acuracia(reais: list[str], preditas: list[str]) -> float | None:
    return round(sum(r == p for r, p in zip(reais, preditas)) / len(reais), 4) if reais else None


def baseline_maioria(reais: list[str]) -> float | None:
    return round(Counter(reais).most_common(1)[0][1] / len(reais), 4) if reais else None
