"""
Células nas regiões de maior atenção, pulmão (revisão 02, item D): o CellViT nas 3 regiões que vão para o pré-laudo das
78 lâminas de teste do pulmão, como já feito na próstata (celulas_regioes.py).

Antes: as lâminas do TCGA foram apagadas depois de extrair os embeddings, e o CellViT só rodou na próstata. O TCGA é
público: aqui cada lâmina é baixada de novo do GDC, só as janelas das 3 regiões são recortadas e guardadas, e a lâmina é
apagada.

Fixado ANTES de rodar (commit anterior aos resultados):
  Lâminas e regiões: as 78 lâminas de teste da divisão aleatória (tcga_descritor_prelaudo.laminas_teste, as dos
     pré-laudos); as 3 regiões dos campos (resultados/aviso_discordancia/pulmao/<file_id>_campos.txt, coordenada do
     canto superior esquerdo do patch, classe do classificador de patches).
  Janela: 256 µm centrada na região (lado em pixels = 256 / mpp), lida no nível 0 e redimensionada para 0,25 µm/px
     (1.024 px); guardada como PNG em resultados/celulas_pulmao/janelas/.
  CellViT: o mesmo de celulas_regioes.py (CellViT-256 x40, pesos públicos do PanNuke, sem retreino); contam os núcleos
     com centro no quadrado central de 128 µm. Medidas por região: número de núcleos, fração de cada tipo, área nuclear
     mediana (µm²).
  Sem máscara de câncer no TCGA. Critério NP (as medidas acompanham o padrão da região): AUC da fração de núcleos
     neoplásicos entre regiões que o classificador de patches chama de tumor (adenocarcinoma ou escamoso) e regiões
     chamadas de pulmão normal >= 0,70, com limite inferior do IC 95% > 0,5 (bootstrap por lâmina, 2.000, semente 0),
     nas regiões com >= 5 núcleos.
  Também reportado (sem critério): a mesma AUC para número de núcleos e área; medianas por padrão e por tipo real da
     lâmina; tempo por região; lâminas que falharem no download.
  Limites conhecidos: a referência é o classificador de patches, que ficou abaixo do critério no pulmão (74% das regiões
     com a classe real); o CellViT não foi treinado no TCGA de pulmão.

Uso:
    .venv/bin/python prelaudo/celulas_pulmao.py --etapa recortar                          # rede; retoma
    "<HD>/venvs/cellvit/bin/python" prelaudo/celulas_pulmao.py --etapa cellvit           # GPU
    .venv/bin/python prelaudo/celulas_pulmao.py --etapa avaliar
Saída: resultados/celulas_pulmao/{janelas/, regioes.json, nucleos.json, resumo.json, por_regiao.json}
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

SAIDA = RESULTADOS_DIR / "celulas_pulmao"
JAN = SAIDA / "janelas"
MPP_CELLVIT, JANELA_UM, REGIAO_UM = 0.25, 256.0, 128.0
JANELA_PX = int(JANELA_UM / MPP_CELLVIT)
REG_INI = int((JANELA_UM - REGIAO_UM) / 2 / MPP_CELLVIT)
REG_FIM = REG_INI + int(REGIAO_UM / MPP_CELLVIT)
TIPOS = {1: "neoplasico", 2: "inflamatorio", 3: "conjuntivo", 4: "morto", 5: "epitelial"}
REGIAO = re.compile(r"^\s+\[(\d+),(\d+)\] (.+?) ([\d.]+)$", re.M)
MIN_NUCLEOS, AUC_MIN, N_BOOT = 5, 0.70, 2000


def etapa_recortar():
    import cv2
    from comum.lamina import Lamina, raiz_hd
    from tcga_baixar_e_embutir import baixar
    from tcga_descritor_prelaudo import PASTA, laminas_teste
    JAN.mkdir(parents=True, exist_ok=True)
    arq = SAIDA / "regioes.json"
    regs = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    tmp = Path(raiz_hd()) / "TCGA_pulmao_tmp"
    tmp.mkdir(exist_ok=True)
    camp = RESULTADOS_DIR / "aviso_discordancia" / "pulmao"
    for n, l in enumerate(laminas_teste(), 1):
        k = l["file_id"]
        if k in regs:
            continue
        meta = json.loads((PASTA / k / "meta.json").read_text(encoding="utf-8"))
        campos = (camp / f"{k}_campos.txt").read_text(encoding="utf-8")
        svs = tmp / l["file_name"]
        try:
            baixar(l, svs)
            lam = Lamina(svs)
            lado_r, mpp = meta["lado_px"], meta["mpp"]
            lado = int(round(JANELA_UM / mpp))
            out = []
            for o, (x, y, cl, p) in enumerate(REGIAO.findall(campos), 1):
                cx, cy = int(x) + lado_r / 2, int(y) + lado_r / 2
                x0, y0 = int(round(cx - lado / 2)), int(round(cy - lado / 2))
                img = np.full((lado, lado, 3), 255, np.uint8)
                sx0, sy0 = max(x0, 0), max(y0, 0)
                sx1, sy1 = min(x0 + lado, lam.largura), min(y0 + lado, lam.altura)
                img[sy0 - y0: sy1 - y0, sx0 - x0: sx1 - x0] = lam.janela_nativa(sx0, sy0, tamanho=lado)[: sy1 - sy0, : sx1 - sx0][..., :3]
                img = cv2.resize(img, (JANELA_PX, JANELA_PX), interpolation=cv2.INTER_AREA if lado > JANELA_PX else cv2.INTER_CUBIC)
                cv2.imwrite(str(JAN / f"{k}_{o}.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
                out.append({"ordem": o, "classe_descritor": cl, "prob": float(p), "projeto": l["projeto"]})
            lam.tif.close()
            regs[k] = out
        except Exception as e:  # noqa: BLE001 — registra e segue
            regs[k] = {"falha": f"{type(e).__name__}: {e}"}
        finally:
            if svs.exists():
                svs.unlink()
        arq.write_text(json.dumps(regs, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[{n}] {l['paciente']}: {'falha' if 'falha' in regs[k] else 'ok'}", flush=True)


def etapa_cellvit():
    import cv2
    import torch
    from nucleos_cellvit import carregar_modelo, segmentar
    regs = json.loads((SAIDA / "regioes.json").read_text(encoding="utf-8"))
    arq = SAIDA / "nucleos.json"
    feito = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo, media, desvio = carregar_modelo(dev)
    for k, v in regs.items():
        if not isinstance(v, list):
            continue
        for r in v:
            chave = f"{k}_{r['ordem']}"
            if chave in feito:
                continue
            t0 = time.time()
            img = cv2.cvtColor(cv2.imread(str(JAN / f"{chave}.png")), cv2.COLOR_BGR2RGB)
            nuc = []
            for c in segmentar(modelo, media, desvio, img, dev).values():
                cx, cy = c["centroid"][0], c["centroid"][1]
                if REG_INI <= cx < REG_FIM and REG_INI <= cy < REG_FIM:
                    area = float(cv2.contourArea(np.asarray(c["contour"], np.int32))) * MPP_CELLVIT ** 2
                    nuc.append({"tipo": TIPOS.get(int(c["type"]), "?"), "area_um2": round(area, 1)})
            feito[chave] = {"nucleos": nuc, "segundos": round(time.time() - t0, 2)}
        arq.write_text(json.dumps(feito), encoding="utf-8")
    print(f"pronto: {len(feito)} regiões")


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return float("nan")
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))


def etapa_avaliar():
    regs = json.loads((SAIDA / "regioes.json").read_text(encoding="utf-8"))
    nuc = json.loads((SAIDA / "nucleos.json").read_text(encoding="utf-8"))
    linhas = []
    for k, v in regs.items():
        if not isinstance(v, list):
            continue
        for r in v:
            f = nuc.get(f"{k}_{r['ordem']}")
            if f is None:
                continue
            ns = f["nucleos"]
            n = len(ns)
            linhas.append({"lamina": k, **r, "n_nucleos": n, "segundos": f["segundos"],
                           **{f"frac_{t}": (sum(x["tipo"] == t for x in ns) / n if n else 0.0) for t in TIPOS.values()},
                           "area_mediana_um2": float(np.median([x["area_um2"] for x in ns])) if n else None,
                           "tumor": r["classe_descritor"] != "pulmão normal"})
    ok = [x for x in linhas if x["n_nucleos"] >= MIN_NUCLEOS]
    lams = sorted({x["lamina"] for x in ok})
    por = {b: [x for x in ok if x["lamina"] == b] for b in lams}

    def a(ch, sub):
        return auc([x[ch] for x in sub if x["tumor"]], [x[ch] for x in sub if not x["tumor"]])
    rng = random.Random(0)
    boot = [a("frac_neoplasico", [x for b in (rng.choice(lams) for _ in lams) for x in por[b]]) for _ in range(N_BOOT)]
    boot = np.array([v for v in boot if np.isfinite(v)])
    a0 = a("frac_neoplasico", ok)
    ic = [round(float(np.percentile(boot, 2.5)), 3), round(float(np.percentile(boot, 97.5)), 3)]

    def med(sub):
        return {"n": len(sub), **{c: round(float(np.median([x[c] for x in sub if x[c] is not None])), 3)
                                  for c in ("n_nucleos", "frac_neoplasico", "frac_inflamatorio", "frac_conjuntivo",
                                            "frac_epitelial", "area_mediana_um2")}} if sub else {"n": 0}
    res = {"laminas_ok": len({x["lamina"] for x in linhas}),
           "laminas_falha": sum(1 for v in regs.values() if not isinstance(v, list)),
           "regioes": len(linhas), "avaliadas": len(ok),
           "tumor": sum(x["tumor"] for x in ok), "pulmao_normal": sum(not x["tumor"] for x in ok),
           "auc_frac_neoplasico": round(a0, 3), "auc_frac_neoplasico_ic95": ic,
           "auc_n_nucleos": round(a("n_nucleos", ok), 3), "auc_area_mediana": round(a("area_mediana_um2", ok), 3),
           "mediana_por_padrao": {c: med([x for x in linhas if x["classe_descritor"] == c])
                                  for c in ("adenocarcinoma", "carcinoma escamoso", "pulmão normal")},
           "mediana_por_tipo_real": {p: med([x for x in linhas if x["projeto"] == p]) for p in ("TCGA-LUAD", "TCGA-LUSC")},
           "segundos_por_regiao_mediana": round(float(np.median([x["segundos"] for x in linhas])), 2) if linhas else None}
    res["criterio_NP"] = bool(a0 >= AUC_MIN and ic[0] > 0.5)
    (SAIDA / "resumo.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    (SAIDA / "por_regiao.json").write_text(json.dumps(linhas, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    print(f"NP {'SIM' if res['criterio_NP'] else 'NÃO'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--etapa", choices=["recortar", "cellvit", "avaliar"], required=True)
    a = p.parse_args()
    {"recortar": etapa_recortar, "cellvit": etapa_cellvit, "avaliar": etapa_avaliar}[a.etapa]()
