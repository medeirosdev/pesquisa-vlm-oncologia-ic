"""
Exporta os contornos das anotações oficiais do BRACS (.qpdata, projetos do QuPath) pra GeoJSON,
um arquivo por lâmina, legível sem o QuPath (coordenadas no nível 0).

Precisa do QuPath (via paquo), num ambiente separado no HD:
    export PAQUO_QUPATH_DIR="/media/medeiros/HD 1TB/Modelos/qupath/QuPath-0.5.1"
    "/media/medeiros/HD 1TB/venvs/paquo/bin/python" scripts/exportar_anotacoes.py

Entrada: <laminas_dir>/anotacoes/extraidas/**/*.qpdata (zips train/val/test do FTP, extraídos).
Saída:   <laminas_dir>/anotacoes/geojson/<lamina>.geojson + resumo_classes.json
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jpype
from paquo.java import start_jvm

from comum.lamina import ler_caminhos

start_jvm()
File = jpype.JClass("java.io.File")
PathIO = jpype.JClass("qupath.lib.io.PathIO")
GsonTools = jpype.JClass("qupath.lib.io.GsonTools")


def main():
    base = Path(ler_caminhos()["laminas_dir"]) / "anotacoes"
    saida = base / "geojson"
    saida.mkdir(exist_ok=True)
    gson = GsonTools.getInstance()
    classes, por_lamina, falhas = Counter(), {}, []
    arquivos = sorted((base / "extraidas").rglob("*.qpdata"))
    for p in arquivos:
        try:
            objs = list(PathIO.readHierarchy(File(str(p.resolve()))).getAnnotationObjects())
        except Exception as e:  # noqa: BLE001 — registra e segue
            falhas.append((p.name, str(e)[:200]))
            continue
        feats = [json.loads(str(gson.toJson(o))) for o in objs]
        (saida / f"{p.stem}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}),
                                                 encoding="utf-8")
        c = Counter(str(o.getPathClass()) for o in objs)
        classes.update(c)
        por_lamina[p.stem] = dict(c)
    resumo = {"n_arquivos": len(arquivos), "n_exportados": len(por_lamina), "classes": dict(classes),
              "falhas": falhas, "por_lamina": por_lamina}
    (saida / "resumo_classes.json").write_text(json.dumps(resumo, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(por_lamina)} de {len(arquivos)} exportadas; falhas: {len(falhas)}")
    print("classes:", dict(classes.most_common()))


if __name__ == "__main__":
    main()
