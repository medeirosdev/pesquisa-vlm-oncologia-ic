"""RoIs anotados do BRACS: recortes oficiais (BRACS_RoI) e posições já localizadas pelo estágio 1."""

import csv
import re
from pathlib import Path

from comum.lamina import RESULTADOS_DIR, TILE_NATIVO, ler_caminhos

CLASSES_BRACS = ["N", "PB", "UDH", "FEA", "ADH", "DCIS", "IC"]


def classe_do_roi(nome_roi: str) -> str:
    """BRACS_748_DCIS_12 -> DCIS"""
    return re.match(r"BRACS_\d+_([A-Z]+)_\d+", nome_roi).group(1)


def listar_recortes_roi(stem: str) -> list[Path]:
    raiz = Path(ler_caminhos()["roi_dataset"])
    return sorted(raiz.glob(f"*/*/{stem}_*.png"))


def carregar_rois(stem: str) -> list[dict]:
    """RoIs localizados pelo estágio 1 (recall_roi.py), em coordenadas do nível 0."""
    caminho = RESULTADOS_DIR / stem / "estagio1" / "recall_roi.csv"
    if not caminho.exists():
        raise FileNotFoundError(f"Rode o estágio 1 (recall_roi.py --svs {stem}) antes: {caminho}")
    with open(caminho, newline="", encoding="utf-8") as f:
        return [{"roi": r["roi"], "classe": r["classe"], "correlacao": float(r["correlacao"]),
                 "x": float(r["x"]), "y": float(r["y"]), "w": float(r["w"]), "h": float(r["h"])}
                for r in csv.DictReader(f)]


def info_lamina(stem: str) -> dict:
    """Rótulo oficial da lâmina e conjunto (treino/validação/teste), da planilha BRACS.xlsx."""
    import openpyxl
    planilha = Path(ler_caminhos()["laminas_dir"]) / "BRACS.xlsx"
    ws = openpyxl.load_workbook(planilha, read_only=True)["WSI_Information"]
    for linha in ws.iter_rows(min_row=2, values_only=True):
        if linha[0] == stem:
            return {"rotulo": linha[3], "conjunto": str(linha[4]).strip()}
    return {"rotulo": None, "conjunto": None}


def bbox_sobrepoe(a: dict, b: dict) -> bool:
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or
                a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def caixa_tile(x0: int, y0: int) -> dict:
    return {"x": x0, "y": y0, "w": TILE_NATIVO, "h": TILE_NATIVO}


def rotular_tiles(xy: list[tuple[int, int]], rois: list[dict]) -> list[dict]:
    """Tiles que caem em RoIs de exatamente uma classe herdam essa classe (os ambíguos saem)."""
    rotulados = []
    for i, (x0, y0) in enumerate(xy):
        classes = {r["classe"] for r in rois if bbox_sobrepoe(caixa_tile(x0, y0), r)}
        if len(classes) == 1:
            rotulados.append({"idx": i, "x0": x0, "y0": y0, "classe_real": classes.pop()})
    return rotulados
