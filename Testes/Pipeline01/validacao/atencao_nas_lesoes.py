"""
A atenção do MIL (mil_atencao.py) cai nas lesões anotadas pelos patologistas? Teste de explicabilidade: os patches
que mais pesaram na decisão deveriam estar onde está a lesão.

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas: as do teste externo com rótulo atípico, DCIS ou IC que têm anotação oficial (GeoJSON exportado do
     .qpdata) de lesão (FEA, ADH, DCIS ou IC) e pelo menos um patch da amostra dentro dela.
  Patch "na lesão": centro do patch dentro de algum polígono de lesão (nomes "FEA…", "ADH…", "DCIS…", "Malignant…"). Atenção: a média das 5 sementes, já salva
     por mil_atencao.py. Patches de maior atenção: os 5% do topo da lâmina (pelo menos 5).
  Referência: fração de todos os patches da amostra que caem na lesão (o que um sorteio acertaria). As anotações
     do BRACS são quase todas retângulos e incluem tecido em volta da lesão; a referência desconta isso.
  Comparação: os 5% do topo por P(não benigno) do descritor com negativos (probabilidades salvas por
     concentracao_espacial.py).
  Critério de "funcionou": a fração do topo da atenção na lesão é maior que a referência em >= 70% das lâminas
     E a razão (somando todas as lâminas) topo/referência é >= 2.
  Também reportado (sem critério): o mesmo pro descritor; por classe.

Uso (venv do projeto; HD montado; só CPU):
    .venv/bin/python validacao/atencao_nas_lesoes.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np
from matplotlib.path import Path as Caminho

from comum.lamina import RESULTADOS_DIR, raiz_hd
from comum.rois import info_lamina

# nomes no GeoJSON: "DCIS-sure", "FEA-sure", "ADH-sure", "Malignant-sure"/"MALIGNANT" (= IC), e variações
LESOES = ("FEA", "ADH", "DCIS", "MALIGNANT")
FRACAO_TOPO = 0.05
MIN_TOPO = 5
MIN_LAMINAS = 0.70
RAZAO_MIN = 2.0
SAIDA = RESULTADOS_DIR / "atencao_nas_lesoes"


def poligonos_de_lesao(stem):
    f = Path(raiz_hd()) / "BRACS" / "anotacoes" / "geojson" / f"{stem}.geojson"
    if not f.exists():
        return []
    g = json.loads(f.read_text(encoding="utf-8"))
    saida = []
    for feat in (g["features"] if isinstance(g, dict) else g):
        nome = ((feat.get("properties", {}).get("classification") or {}).get("name") or "").upper()
        if not nome.startswith(LESOES):
            continue
        geo = feat["geometry"]
        aneis = [geo["coordinates"][0]] if geo["type"] == "Polygon" else [p[0] for p in geo["coordinates"]] if geo["type"] == "MultiPolygon" else []
        saida += [Caminho(np.array(a, float)) for a in aneis]
    return saida


def na_lesao(xy, polis):
    from comum.lamina import TILE_NATIVO
    centros = xy + TILE_NATIVO / 2
    dentro = np.zeros(len(xy), bool)
    for p in polis:
        dentro |= p.contains_points(centros)
    return dentro


def topo(valores):
    k = max(MIN_TOPO, int(round(FRACAO_TOPO * len(valores))))
    return np.argsort(-valores)[:k]


def main():
    from lamina_inteira import classe_final, laminas_teste
    SAIDA.mkdir(parents=True, exist_ok=True)
    linhas = {}
    for s in laminas_teste():
        real = classe_final(info_lamina(s)["rotulo"])
        if real == "benigno":
            continue
        polis = poligonos_de_lesao(s)
        if not polis:
            continue
        z = np.load(RESULTADOS_DIR / "concentracao_espacial" / "probs" / f"{s}_probs.npz")
        xy, p1 = z["xy"].astype(float), z["p1"]
        att = np.load(RESULTADOS_DIR / "mil_atencao" / f"{s}_atencao.npy")
        assert len(att) == len(xy), s
        dentro = na_lesao(xy, polis)
        if not dentro.any():
            continue
        ta, td = topo(att), topo(1 - p1[:, 0])
        linhas[s] = {"real": real, "n": int(len(xy)), "k_topo": int(len(ta)), "referencia": float(dentro.mean()),
                     "topo_atencao": float(dentro[ta].mean()), "topo_descritor": float(dentro[td].mean())}

    def resumir(chave, stems):
        ref = np.array([linhas[s]["referencia"] for s in stems])
        top = np.array([linhas[s][chave] for s in stems])
        return {"laminas": len(stems), "laminas_acima_da_referencia": int((top > ref).sum()),
                "fracao_acima": round(float((top > ref).mean()), 3),
                "media_topo": round(float(top.mean()), 3), "media_referencia": round(float(ref.mean()), 3),
                "razao_somada": round(float(top.sum() / ref.sum()), 2)}
    stems = sorted(linhas)
    resumo = {"atencao_mil": resumir("topo_atencao", stems), "descritor": resumir("topo_descritor", stems),
              "por_classe": {c: {"atencao_mil": resumir("topo_atencao", [s for s in stems if linhas[s]["real"] == c]),
                                 "descritor": resumir("topo_descritor", [s for s in stems if linhas[s]["real"] == c])}
                             for c in ("atipico", "DCIS", "IC") if any(linhas[s]["real"] == c for s in stems)},
              "por_lamina": linhas}
    a = resumo["atencao_mil"]
    resumo["funcionou"] = a["fracao_acima"] >= MIN_LAMINAS and a["razao_somada"] >= RAZAO_MIN
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    for nome in ("atencao_mil", "descritor"):
        print(f"{nome:<12} {resumo[nome]}")
    for c, v in resumo["por_classe"].items():
        print(f"  {c:<8} MIL {v['atencao_mil']} | descritor {v['descritor']}")
    print(f"Critério fixado antes (acima da referência em >= {MIN_LAMINAS:.0%} das lâminas e razão >= {RAZAO_MIN}): {'SIM' if resumo['funcionou'] else 'NÃO'}")


if __name__ == "__main__":
    main()
