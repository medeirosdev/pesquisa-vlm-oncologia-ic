"""
Põe no sys.path todas as pastas de código da Pipeline01 (dados/, descritor/, mil/, prelaudo/ etc.), pra que um script
importe outro pelo nome do módulo, esteja em que pasta estiver. Os nomes dos módulos .py são únicos na Pipeline01.

Uso, no topo de cada script:
    sys.path.insert(0, str(Path(__file__).resolve().parents[N]))   # N = níveis até Testes/Pipeline01
    import comum.caminhos  # noqa: E402,F401
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
IGNORAR = {".venv", "resultados", "__pycache__", "ideia", "notas", "comum"}


def _pastas(raiz):
    for p in sorted(raiz.iterdir()):
        if p.is_dir() and p.name not in IGNORAR and not p.name.startswith("."):
            if any(p.glob("*.py")):
                yield p
            yield from _pastas(p)


for _p in [RAIZ, *_pastas(RAIZ)]:
    if str(_p) not in sys.path:
        sys.path.append(str(_p))
