"""Caminhos do projeto, abertura de lâmina e pasta de resultados, usados por todos os estágios."""

import os
from pathlib import Path

import numpy as np
import tifffile
import zarr

PIPELINE_DIR = Path(__file__).resolve().parent.parent
RAIZ_PROJETO = PIPELINE_DIR.parent.parent
CAMINHOS_MD = RAIZ_PROJETO / "Caminhos" / "caminhos.md"

# O HD externo é montado com o nome do rótulo do volume ("HD 1TB"), mas se a pasta já existir o
# sistema usa outro nome ("HD 1TB1"). Os caminhos do caminhos.md são escritos com HD_PADRAO e
# ajustados pra onde o volume estiver montado de fato.
HD_ROTULO = "HD 1TB"
HD_PADRAO = "/media/medeiros/HD 1TB"
RESULTADOS_DIR = PIPELINE_DIR / "resultados"

TILE_NATIVO = 512    # px no nível 0 da pirâmide
TILE_TRABALHO = 256  # 512px nativo reduzido pela metade: ~20x numa lâmina escaneada em 40x


def raiz_hd() -> str:
    """Onde o volume com rótulo HD_ROTULO está montado agora (HD_PADRAO se não achar)."""
    rotulo = Path("/dev/disk/by-label") / HD_ROTULO.replace(" ", "\\x20")
    if rotulo.exists():
        dispositivo = os.path.realpath(rotulo)
        with open("/proc/mounts", encoding="utf-8") as f:
            for linha in f:
                origem, alvo = linha.split()[:2]
                if os.path.realpath(origem) == dispositivo:
                    return alvo.replace("\\040", " ")
    return HD_PADRAO


def no_hd(caminho: str) -> str:
    """Troca o prefixo HD_PADRAO pela montagem atual do HD."""
    return raiz_hd() + caminho[len(HD_PADRAO):] if caminho.startswith(HD_PADRAO + "/") else caminho


def ler_caminhos() -> dict:
    caminhos = {}
    for linha in CAMINHOS_MD.read_text(encoding="utf-8").splitlines():
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            caminhos[chave.strip()] = no_hd(valor.strip())
    return caminhos


def resolver_svs(svs: str | None = None) -> Path:
    """Aceita caminho completo, só o nome (BRACS_1370) ou nada (usa `svs:` do caminhos.md)."""
    caminhos = ler_caminhos()
    if svs is None:
        caminho = Path(caminhos["svs"])
    elif svs.endswith(".svs") or "/" in svs:
        caminho = Path(svs)
    else:
        caminho = Path(caminhos["laminas_dir"]) / f"{svs}.svs"
    if not caminho.exists():
        raise FileNotFoundError(f"Lâmina não encontrada: {caminho}")
    return caminho


def listar_laminas() -> list[Path]:
    return sorted(Path(ler_caminhos()["laminas_dir"]).glob("BRACS_*.svs"))


def dir_resultados(stem: str, etapa: str) -> Path:
    pasta = RESULTADOS_DIR / stem / etapa
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


class Lamina:
    """Uma lâmina .svs aberta. Escolhe nível da pirâmide pelo fator de redução, não pela
    posição na lista — lâminas pequenas têm menos níveis (ex. 1x/4x/8x em vez de 1x/4x/16x/32x)."""

    def __init__(self, caminho_svs):
        self.caminho = Path(caminho_svs)
        self.stem = self.caminho.stem
        self.tif = tifffile.TiffFile(str(self.caminho))
        self.niveis = self.tif.series[0].levels
        self.altura, self.largura = self.niveis[0].shape[:2]
        self.downsamples = [self.largura / n.shape[1] for n in self.niveis]
        self._nivel0 = None

    def nivel_mais_proximo(self, downsample_alvo: float) -> tuple[int, float]:
        i = min(range(len(self.downsamples)),
                key=lambda j: abs(np.log(self.downsamples[j] / downsample_alvo)))
        return i, self.downsamples[i]

    def ler_nivel(self, i: int) -> np.ndarray:
        """Nível inteiro em memória — só use em níveis de baixa resolução."""
        return self.niveis[i].asarray()

    def thumbnail(self, downsample_alvo: float = 32) -> tuple[np.ndarray, float]:
        i, ds = self.nivel_mais_proximo(downsample_alvo)
        return self.ler_nivel(i), ds

    def janela_nativa(self, x0: int, y0: int, tamanho: int = TILE_NATIVO) -> np.ndarray:
        """Lê só uma janela do nível 0, sem carregar a lâmina inteira."""
        if self._nivel0 is None:
            za = zarr.open(self.tif.series[0].aszarr(), mode="r")
            self._nivel0 = za["0"] if hasattr(za, "array_keys") else za
        return np.asarray(self._nivel0[y0:y0 + tamanho, x0:x0 + tamanho])
