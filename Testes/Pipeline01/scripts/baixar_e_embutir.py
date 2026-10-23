"""
Baixa lâminas do BRACS uma a uma, calcula os embeddings do UNI2-h de uma amostra de 2.000 patches de
tecido (o mesmo formato de validacao/lamina_inteira.py) e apaga a lâmina — pra usar centenas de lâminas
sem ocupar centenas de GB. Retoma de onde parou (pula lâminas que já têm embeddings).

Credenciais do FTP: lidas das variáveis de ambiente BRACS_FTP_USER e BRACS_FTP_PASS (não ficam
no repositório).

Uso (venv do projeto, HD montado, no terminal):
    export BRACS_FTP_USER=...  BRACS_FTP_PASS=...
    .venv/bin/python scripts/baixar_e_embutir.py scripts/lista_validacao.txt
    .venv/bin/python scripts/baixar_e_embutir.py scripts/lista_treino.txt
Opção --manter: não apaga a lâmina depois de calcular os embeddings.
"""

import argparse
import os
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comum.lamina import Lamina, dir_resultados, ler_caminhos
from comum.tecido import grade_candidatos, mascara_tecido

FTP = "ftp://histoimage.na.icar.cnr.it/BRACS_WSI"
N_AMOSTRA = 2000


def ja_feita(stem):
    return (dir_resultados(stem, "uni2h") / f"amostra{N_AMOSTRA}.npy").exists()


def baixar(caminho_ftp, destino):
    for tentativa in range(1, 6):
        r = subprocess.run(["wget", "-q", "--continue", "--tries=3", "--timeout=60",
                            f"--user={os.environ['BRACS_FTP_USER']}", f"--password={os.environ['BRACS_FTP_PASS']}",
                            "-O", str(destino), f"{FTP}/{caminho_ftp}"])
        if r.returncode == 0:
            return True
        print(f"    download falhou (tentativa {tentativa}), de novo em 15 s", flush=True)
        time.sleep(15)
    return False


def embutir(svs):
    from comum.uni import embeddings_uni2h
    lamina = Lamina(svs)
    rgb, ds = lamina.thumbnail(32)
    xy = grade_candidatos(lamina, mascara_tecido(rgb), ds)
    amostra = sorted(random.Random(0).sample(xy, min(N_AMOSTRA, len(xy))))
    embeddings_uni2h(lamina, amostra, f"amostra{N_AMOSTRA}")
    return len(xy), len(amostra)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("lista")
    p.add_argument("--manter", action="store_true")
    a = p.parse_args()
    if not os.environ.get("BRACS_FTP_USER") or not os.environ.get("BRACS_FTP_PASS"):
        sys.exit("Exporte BRACS_FTP_USER e BRACS_FTP_PASS antes de rodar.")
    pasta = Path(ler_caminhos()["laminas_dir"])
    caminhos = [l.strip() for l in Path(a.lista).read_text(encoding="utf-8").splitlines() if l.strip()]
    falhas = []
    for i, c in enumerate(caminhos, 1):
        stem = Path(c).stem
        if ja_feita(stem):
            continue
        svs = pasta / f"{stem}.svs"
        t0 = time.time()
        try:
            if not svs.exists() and not baixar(c, svs):
                raise RuntimeError("download falhou")
            n_tecido, n = embutir(svs)
            print(f"[{i}/{len(caminhos)}] {stem}: {n} de {n_tecido} patches ({time.time() - t0:.0f} s)", flush=True)
        except Exception as e:  # noqa: BLE001 — registra e segue pra próxima lâmina
            falhas.append(stem)
            print(f"[{i}/{len(caminhos)}] {stem}: ERRO {type(e).__name__}: {e}", flush=True)
        finally:
            if svs.exists() and not a.manter and ja_feita(stem):
                svs.unlink()
    print(f"\nconcluído; falhas: {falhas if falhas else 'nenhuma'}")


if __name__ == "__main__":
    main()
