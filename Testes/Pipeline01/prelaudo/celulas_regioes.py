"""
Células nas regiões de maior atenção: o CellViT dá, para cada região que vai para o pré-laudo, o número de núcleos, a
proporção de cada tipo e a área nuclear. São dados que o patologista confere de olho, ao contrário dos embeddings.
Antes de pôr esses números no laudo, conferimos se eles têm sentido onde há referência: na próstata, a máscara do
Karolinska separa câncer de tecido benigno.

Fixado ANTES de rodar (commit anterior aos resultados):
  Regiões: as 3 regiões de maior atenção do GAT-MIL padronizado (prelaudo_final.regioes_gat: centros a >= 192 µm),
     em todas as biópsias de teste do Karolinska com máscara. Rótulo da região pela máscara, como no critério A
     (panda_descritor_prelaudo.rotulo_karolinska): câncer se >= 50% da área tem tecido rotulado e a fração de câncer
     nesse tecido é >= 0,5; benigno se a fração de câncer é 0; de fora no meio ou sem tecido rotulado.
  CellViT: CellViT-256 x40 (pesos oficiais, tipos do PanNuke: neoplásico, inflamatório, conjuntivo, morto,
     epitelial), sem treino. Janela de 256 µm centrada na região, lida no nível 0 e redimensionada para 0,25 µm/px
     (1024 px); contam os núcleos com centro no quadrado central de 128 µm (a própria região).
  Medidas por região: número de núcleos; fração de cada tipo; área nuclear mediana (µm²).
  Critério N (próstata): AUC câncer × benigno da fração de núcleos neoplásicos >= 0,70, com limite inferior do IC 95%
     > 0,5 (bootstrap por biópsia, 2.000, semente 0), nas regiões com >= 5 núcleos.
  Também reportado (sem critério): a mesma AUC para número de núcleos e área mediana; as medidas por classe do
     descritor; as regiões das 60 biópsias dos pré-laudos; o tempo por região; quantas regiões ficam de fora.
  Limites conhecidos: o Karolinska foi escaneado a ~0,45 µm/px e o CellViT foi treinado a 0,25 µm/px (a janela é
     ampliada); o tipo "neoplásico" do CellViT acertou 46% dos núcleos tumorais na mama (NuCLS, valor preditivo 0,86);
     a máscara é por região, não por célula.

Uso:
    .venv/bin/python prelaudo/celulas_regioes.py --etapa regioes                     # lista as regiões (venv do projeto)
    "<HD>/venvs/cellvit/bin/python" prelaudo/celulas_regioes.py --etapa cellvit     # GPU, venv do CellViT
    .venv/bin/python prelaudo/celulas_regioes.py --etapa avaliar
Saída: resultados/celulas_regioes/
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "celulas_regioes"
MPP_CELLVIT = 0.25
JANELA_UM, REGIAO_UM = 256.0, 128.0
JANELA_PX = int(JANELA_UM / MPP_CELLVIT)          # 1024
REG_INI = int((JANELA_UM - REGIAO_UM) / 2 / MPP_CELLVIT)  # 256
REG_FIM = REG_INI + int(REGIAO_UM / MPP_CELLVIT)          # 768
TIPOS = {1: "neoplasico", 2: "inflamatorio", 3: "conjuntivo", 4: "morto", 5: "epitelial"}
MIN_NUCLEOS = 5
AUC_MIN, N_BOOT = 0.70, 2000


def etapa_regioes():
    from panda_descritor_prelaudo import biopsias_prelaudo, rotulo_karolinska
    from panda_mil import biopsias
    from prelaudo_final import regioes_gat
    SAIDA.mkdir(parents=True, exist_ok=True)
    laudo = {l["image_id"] for l in biopsias_prelaudo()}
    _, prontas = biopsias()
    out = []
    for l in prontas:
        if l["conjunto"] != "teste":
            continue
        meta = json.loads((RESULTADOS_DIR / "panda" / l["image_id"] / "meta.json").read_text(encoding="utf-8"))
        if not meta.get("mascara"):
            continue
        fr, _, reg = regioes_gat(l)
        for k, d in enumerate(reg):
            r = rotulo_karolinska(fr[d["i"]]) if fr is not None else None
            out.append({"image_id": l["image_id"], "isup": int(l["isup_grade"]), "no_laudo": l["image_id"] in laudo,
                        "ordem": k + 1, "cx": float(d["cx"]), "cy": float(d["cy"]), "mpp": meta["mpp"],
                        "classe_descritor": d["classe"], "mascara": {1: "cancer", 0: "benigno", None: "fora"}[r]})
    (SAIDA / "regioes.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(out)} regiões de {len({r['image_id'] for r in out})} biópsias; "
          f"câncer {sum(r['mascara'] == 'cancer' for r in out)}, benigno {sum(r['mascara'] == 'benigno' for r in out)}")


def etapa_cellvit():
    import cv2
    import torch
    from comum.lamina import Lamina
    from comum.lamina import raiz_hd
    from nucleos_cellvit import carregar_modelo, segmentar
    pasta_panda = Path(raiz_hd()) / "Dados Gerais" / "PANDA"
    regs = json.loads((SAIDA / "regioes.json").read_text(encoding="utf-8"))
    arq = SAIDA / "nucleos.json"
    feito = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, media, desvio = carregar_modelo(dev)
    abertas = {}
    for r in regs:
        chave = f"{r['image_id']}_{r['ordem']}"
        if chave in feito:
            continue
        t0 = time.time()
        if r["image_id"] not in abertas:
            abertas.clear()
            abertas[r["image_id"]] = Lamina(pasta_panda / "train_images" / f"{r['image_id']}.tiff")
        lam = abertas[r["image_id"]]
        lado = int(round(JANELA_UM / r["mpp"]))
        x0, y0 = int(round(r["cx"] - lado / 2)), int(round(r["cy"] - lado / 2))
        img = np.full((lado, lado, 3), 255, np.uint8)
        sx0, sy0 = max(x0, 0), max(y0, 0)
        sx1, sy1 = min(x0 + lado, lam.largura), min(y0 + lado, lam.altura)
        pedaco = lam.janela_nativa(sx0, sy0, tamanho=lado)[: sy1 - sy0, : sx1 - sx0]
        img[sy0 - y0: sy1 - y0, sx0 - x0: sx1 - x0] = pedaco[..., :3]
        img = cv2.resize(img, (JANELA_PX, JANELA_PX), interpolation=cv2.INTER_CUBIC)
        cel = segmentar(modelo, media, desvio, img, dev)
        nuc = []
        for c in cel.values():
            cx, cy = c["centroid"][0], c["centroid"][1]
            if REG_INI <= cx < REG_FIM and REG_INI <= cy < REG_FIM:
                area = float(cv2.contourArea(np.asarray(c["contour"], np.int32))) * MPP_CELLVIT ** 2
                nuc.append({"tipo": TIPOS.get(int(c["type"]), "?"), "area_um2": round(area, 1)})
        feito[chave] = {"nucleos": nuc, "segundos": round(time.time() - t0, 2)}
        if len(feito) % 50 == 0:
            arq.write_text(json.dumps(feito), encoding="utf-8")
            print(f"  {len(feito)}/{len(regs)}", flush=True)
    arq.write_text(json.dumps(feito), encoding="utf-8")
    print(f"pronto: {len(feito)} regiões")


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def medidas(nuc):
    n = len(nuc)
    fr = {t: (sum(x["tipo"] == t for x in nuc) / n if n else 0.0) for t in TIPOS.values()}
    return {"n_nucleos": n, **{f"frac_{t}": round(v, 4) for t, v in fr.items()},
            "area_mediana_um2": round(float(np.median([x["area_um2"] for x in nuc])), 1) if n else None}


def etapa_avaliar():
    regs = json.loads((SAIDA / "regioes.json").read_text(encoding="utf-8"))
    nuc = json.loads((SAIDA / "nucleos.json").read_text(encoding="utf-8"))
    linhas = []
    for r in regs:
        f = nuc.get(f"{r['image_id']}_{r['ordem']}")
        if f is not None:
            linhas.append({**r, **medidas(f["nucleos"]), "segundos": f["segundos"]})
    ok = [x for x in linhas if x["mascara"] in ("cancer", "benigno") and x["n_nucleos"] >= MIN_NUCLEOS]
    bios = sorted({x["image_id"] for x in ok})
    por_bio = {b: [x for x in ok if x["image_id"] == b] for b in bios}

    def auc_de(chave, sub):
        return auc([x[chave] for x in sub if x["mascara"] == "cancer"], [x[chave] for x in sub if x["mascara"] == "benigno"])

    rng = random.Random(0)
    boot = []
    for _ in range(N_BOOT):
        sub = [x for b in (rng.choice(bios) for _ in bios) for x in por_bio[b]]
        boot.append(auc_de("frac_neoplasico", sub))
    boot = np.array([v for v in boot if np.isfinite(v)])
    a0 = auc_de("frac_neoplasico", ok)
    ic = [round(float(np.percentile(boot, 2.5)), 3), round(float(np.percentile(boot, 97.5)), 3)]

    def resumo_grupo(sub):
        return {"n": len(sub), **{k: round(float(np.median([x[k] for x in sub if x[k] is not None])), 3) for k in
                                 ("n_nucleos", "frac_neoplasico", "frac_inflamatorio", "frac_conjuntivo", "frac_epitelial",
                                  "area_mediana_um2")}} if sub else {"n": 0}

    res = {"regioes": len(regs), "medidas": len(linhas), "biopsias": len({x["image_id"] for x in linhas}),
           "avaliadas_criterio": len(ok), "cancer": sum(x["mascara"] == "cancer" for x in ok),
           "benigno": sum(x["mascara"] == "benigno" for x in ok),
           "de_fora": {"mascara_fora": sum(x["mascara"] == "fora" for x in linhas),
                       "menos_de_5_nucleos": sum(x["mascara"] != "fora" and x["n_nucleos"] < MIN_NUCLEOS for x in linhas)},
           "auc_frac_neoplasico": round(a0, 3), "auc_frac_neoplasico_ic95": ic,
           "auc_n_nucleos": round(auc_de("n_nucleos", ok), 3),
           "auc_area_mediana": round(auc_de("area_mediana_um2", ok), 3),
           "mediana_por_mascara": {m: resumo_grupo([x for x in ok if x["mascara"] == m]) for m in ("cancer", "benigno")},
           "mediana_por_classe_descritor": {c: resumo_grupo([x for x in linhas if x["classe_descritor"] == c and x["n_nucleos"] > 0])
                                            for c in ("benigno", "gleason3", "gleason4", "gleason5")},
           "regioes_dos_prelaudos": resumo_grupo([x for x in linhas if x["no_laudo"] and x["n_nucleos"] > 0]),
           "segundos_por_regiao_mediana": round(float(np.median([x["segundos"] for x in linhas])), 2)}
    res["criterio_N"] = bool(a0 >= AUC_MIN and ic[0] > 0.5)
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "por_regiao.json").write_text(json.dumps(linhas, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"N {'SIM' if res['criterio_N'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["regioes", "cellvit", "avaliar"], required=True)
    a = p.parse_args()
    {"regioes": etapa_regioes, "cellvit": etapa_cellvit, "avaliar": etapa_avaliar}[a.etapa]()
