"""
Próstata, teste externo do Karolinska: o aviso de discordância ainda marca os erros do MIL nas 500 biópsias nunca
usadas, na distribuição natural? (plano do handoff, §5 item 2, "aviso × erro no externo", que ficou de fora de
panda_externo.py.) Também confere, sem critério, se a atenção cai no câncer anotado no externo.

Fixado ANTES de rodar (commit anterior aos resultados):
  Dados: as 500 biópsias externas de dados/panda/lista_panda_externo.tsv (embeddings, coordenadas e frações de máscara
     em resultados/panda_externo/<image_id>/), como em panda_externo.py.
  Modelo: GAT-MIL padronizado (gat_mil.treinar, k = 6, 40 épocas, sementes 0 a 4) retreinado nas 600 do Radboud com a
     padronização do Radboud, como em panda_externo.py; externo padronizado pelo lote externo inteiro (caso a).
     Probabilidade e atenção = média das 5 sementes. O retreino não é idêntico ao de panda_externo.py; o kappa e a AUC
     deste retreino são reportados ao lado.
  Classificador de patches: o mesmo de panda_descritor_prelaudo.etapa_descrever (logística multinomial nos patches das
     600 do Radboud rotulados pela máscara, até 60 por biópsia, sorteio com semente 0), refeito aqui e aplicado aos
     embeddings externos originais (não padronizados). Conferência: nas 300 de desenvolvimento, as probabilidades
     refeitas devem bater com resultados/panda_prelaudo/<id>_descritor.npy (diferença máxima reportada).
  Regiões e aviso: as 3 regiões de maior atenção com centros a >= 192 µm (tcga_descritor_prelaudo.gate_um), a classe
     do classificador de patches em cada uma e o aviso pela mesma regra (aviso_discordancia.discordantes: ISUP 0 com
     região de Gleason, ou ISUP >= 1 com região benigna).
  Critério E_ext: erro câncer × benigno com taxa maior nas biópsias com aviso que nas sem aviso, Fisher unilateral
     p < 0,05 (o mesmo critério E, aviso_erro.comparar).
  Também reportado (sem critério): o mesmo para erro de grau exato e erro >= 2 graus; confiança >= 0,70 e
     "aviso ou confiança < 0,70" (comparar); biópsias com ISUP >= 1 e máscara com >= 2 das 3 regiões no câncer
     (panda_descritor_prelaudo.no_cancer) e o esperado por acaso.
  Limites conhecidos: um centro; o PANDA não identifica pacientes.

Uso (venv do projeto; GPU): .venv/bin/python mil/panda/panda_externo_aviso.py
Saída: resultados/panda_externo/aviso_erro.json
"""

import csv
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR  # noqa: E402

PASTA_EXT = RESULTADOS_DIR / "panda_externo"
LISTA_EXT = Path(__file__).resolve().parents[2] / "dados" / "panda" / "lista_panda_externo.tsv"
K = 6


def main():
    import torch
    import gat_mil
    from aviso_discordancia import discordantes
    from aviso_erro import CONF_ALTA, P_MAX, comparar
    from categoria_uni import logistica_multinomial
    from gat_mil_panda import carregar as carregar_xg
    from panda_descritor_prelaudo import (CLASSES, MAX_POR_BIOPSIA, N_REGIOES, NOME_PT, PASTA, SAIDA as SAIDA_DESC,
                                          carregar, no_cancer, rotulo_radboud)
    from panda_externo import auc, kappa_q, padronizar
    from panda_mil import biopsias
    from tcga_descritor_prelaudo import gate_um

    _, prontas = biopsias()
    yv = {l["image_id"]: int(l["isup_grade"]) for l in prontas}
    tr_l = [l for l in prontas if l["conjunto"] == "treino"]
    dev_l = [l for l in prontas if l["conjunto"] == "teste"]
    tr = [l["image_id"] for l in tr_l]
    ext_lista = list(csv.DictReader(open(LISTA_EXT, encoding="utf-8"), delimiter="\t"))
    ext = [l["image_id"] for l in ext_lista if (PASTA_EXT / l["image_id"] / "meta.json").exists()]
    yv.update({l["image_id"]: int(l["isup_grade"]) for l in ext_lista})

    # --- classificador de patches, refeito como em panda_descritor_prelaudo.etapa_descrever
    rng, Xd, yd = random.Random(0), [], []
    for l in tr_l:
        _, _, fr = carregar(l)
        if fr is None:
            continue
        X = np.load(PASTA / l["image_id"] / "amostra2000.npy")
        idx = [i for i in range(len(fr)) if rotulo_radboud(fr[i]) is not None]
        for i in sorted(rng.sample(idx, min(MAX_POR_BIOPSIA, len(idx)))):
            Xd.append(X[i])
            yd.append(rotulo_radboud(fr[i]))
    blocos = [np.load(PASTA / l["image_id"] / "amostra2000.npy") for l in dev_l]
    blocos += [np.load(PASTA_EXT / i / "amostra2000.npy") for i in ext]
    P_all = np.asarray(logistica_multinomial(np.stack(Xd), np.array(yd), np.concatenate(blocos), k=4, probabilidades=True))
    Ps = np.split(P_all, np.cumsum([len(b) for b in blocos])[:-1])
    dif = max(float(np.abs(P - np.load(SAIDA_DESC / f"{l['image_id']}_descritor.npy")).max())
              for l, P in zip(dev_l, Ps[:len(dev_l)]))
    P_ext = dict(zip(ext, Ps[len(dev_l):]))
    print(f"classificador de patches refeito; diferença máxima no desenvolvimento: {dif:.2e}", flush=True)

    # --- modelo congelado, com atenção
    X, G = carregar_xg(tr)
    meta_ext, xy_ext, fr_ext = {}, {}, {}
    for i in ext:
        X[i] = torch.from_numpy(np.load(PASTA_EXT / i / "amostra2000.npy"))
        xy_ext[i] = np.loadtxt(PASTA_EXT / i / "amostra2000_xy.csv", delimiter=",", skiprows=1, dtype=np.int64).reshape(-1, 2)
        meta_ext[i] = json.loads((PASTA_EXT / i / "meta.json").read_text(encoding="utf-8"))
        G[i] = gat_mil.arestas_vizinhos(xy_ext[i], meta_ext[i]["lado_px"])
        f = PASTA_EXT / i / "mascara_frac.npy"
        fr_ext[i] = np.load(f).astype(np.float32) if f.exists() else None
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    Xtr = padronizar(X, tr, tr)
    ytr = np.array([yv[i] for i in tr])
    Xa = padronizar(X, ext, ext)
    P = {i: np.zeros(K) for i in ext}
    A = {i: np.zeros(len(X[i])) for i in ext}
    for s in range(5):
        m = gat_mil.treinar([Xtr[i] for i in tr], [G[i] for i in tr], ytr, s, dev, k=K).eval()
        with torch.no_grad():
            for i in ext:
                logit, a, _ = m(Xa[i].to(dev), G[i].to(dev))
                P[i] += torch.softmax(logit, 0).cpu().numpy() / 5
                A[i] += a.cpu().numpy() / 5
        print(f"  semente {s} pronta", flush=True)

    real = np.array([yv[i] for i in ext])
    pred = np.array([int(P[i].argmax()) for i in ext])
    esc = np.array([1 - P[i][0] for i in ext])
    aviso, e_cb, e_ex, e_2, conf, ok, n_c, acaso = [], [], [], [], [], 0, 0, []
    for j, i in enumerate(ext):
        lado, mpp = meta_ext[i]["lado_px"], meta_ext[i]["mpp"]
        ps = [{"i": t, "x0": int(x), "y0": int(y), "cx": x + lado / 2, "cy": y + lado / 2, "atencao": float(a),
               "classe": CLASSES[int(p.argmax())], "prob": float(p.max())}
              for t, ((x, y), p, a) in enumerate(zip(xy_ext[i], P_ext[i], A[i]))]
        reg = gate_um(sorted(ps, key=lambda d: -d["atencao"]), mpp, N_REGIOES)
        g = int(pred[j])
        campos = "\n".join(f"  [{d['x0']},{d['y0']}] {NOME_PT[d['classe']]} {d['prob']:.2f}" for d in reg)
        aviso.append(bool(discordantes("prostata", g, campos)))
        e_cb.append((g == 0) != (real[j] == 0))
        e_ex.append(g != real[j])
        e_2.append(abs(g - real[j]) >= 2)
        conf.append(P[i][g] >= CONF_ALTA)
        fr = fr_ext[i]
        if real[j] >= 1 and fr is not None:
            n_c += 1
            ok += sum(no_cancer(fr[d["i"]]) for d in reg) >= 2
            q = float(np.mean([no_cancer(f) for f in fr]))
            acaso.append(3 * q ** 2 * (1 - q) + q ** 3)
    out = {"n": len(ext), "kappa_quadratico_deste_retreino": round(kappa_q(real, pred), 3),
           "auc_cancer_deste_retreino": round(auc(esc[real >= 1], esc[real == 0]), 3),
           "classificador_de_patches_diferenca_max_desenvolvimento": dif,
           "cancer_x_benigno": comparar(aviso, e_cb, conf),
           "erro_isup_exato": comparar(aviso, e_ex, conf), "erro_2_ou_mais_graus": comparar(aviso, e_2, conf),
           "regioes_no_cancer_2_de_3": f"{ok}/{n_c}", "esperado_por_acaso": round(float(np.mean(acaso)), 3) if acaso else None}
    a = out["cancer_x_benigno"]["aviso"]
    out["criterio_E_ext"] = bool(a["taxa_erro_com_sinal"] > a["taxa_erro_sem_sinal"] and a["fisher_p_unilateral"] < P_MAX)
    (PASTA_EXT / "aviso_erro.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("erro_isup_exato", "erro_2_ou_mais_graus")}, indent=1,
                     ensure_ascii=False))
    print(f"E_ext {'SIM' if out['criterio_E_ext'] else 'NÃO'}")


if __name__ == "__main__":
    main()
