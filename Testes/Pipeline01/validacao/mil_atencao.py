"""
MIL com atenção (ABMIL), em escala pequena: aprende a classe da lâmina direto do rótulo, a partir dos embeddings do
UNI2-h dos patches, sem passar pelo descritor por patch. Motivo: com o descritor, benigno × atípico fica perto do
acaso no nível da lâmina (AUC 0,58 em concentracao_espacial.py). Se mesmo com só 79 lâminas de treino o MIL separar
melhor, vale baixar as 379 lâminas de treino do BRACS.

Fixado ANTES de rodar (commit anterior aos resultados):
  Dados: a amostra de até 2.000 patches de cada lâmina (embeddings UNI2-h, 1.536 números por patch). Treino: as 79
     lâminas de classificador_lamina.py (61 de validação + 18 de desenvolvimento). Teste: as 57 do teste externo.
     Rótulo oficial do BRACS, 4 classes (benigno = N, PB, UDH; atípico = FEA, ADH; DCIS; IC).
  Modelo (Ilse et al., 2018, atenção com porta): 1.536 -> 256 (ReLU, dropout 0,25); atenção com porta de 128;
     soma ponderada dos patches -> 4 classes. Entropia cruzada com pesos balanceados por classe. Adam, taxa 1e-4,
     decaimento 1e-4, 40 épocas, uma lâmina por passo, sem parada antecipada. Cinco modelos (sementes 0 a 4);
     a probabilidade final é a média dos cinco.
  Métricas nas 57:
     acurácia balanceada nas 4 classes;
     AUC benigno × atípico nas 37 lâminas dessas duas classes, com r = P(atípico) / (P(benigno) + P(atípico));
     AUC maligno × resto, com P(DCIS) + P(IC).
  Critérios de "funcionou":
     C1: acurácia balanceada nas 4 classes > 0,505 (classificador da lâmina com negativos, rotulo_oficial.py);
     C2: AUC benigno × atípico >= 0,70 (com o descritor: 0,58).
  Também reportado (sem critério): acerto por classe; intervalo de 95% da acurácia balanceada por bootstrap agrupado
     por paciente; resposta em conjunto (regra e d de resposta_em_conjunto.py, d = 0,45); atenção por patch,
     salva pra mapas de calor.
  As 57 lâminas já foram usadas em vários testes; a confirmação depende das 30 de teste ainda não usadas.

Uso (venv do projeto; GPU se houver, senão CPU; poucos minutos):
    .venv/bin/python validacao/mil_atencao.py
"""

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "estagio3_descritores"))

import numpy as np
import torch
from torch import nn

from comum.lamina import RESULTADOS_DIR
from comum.rois import info_lamina

EPOCAS = 40
SEMENTES = [0, 1, 2, 3, 4]
TAXA = 1e-4
DECAIMENTO = 1e-4
BA_REF = 0.505
AUC_MIN = 0.70
N_BOOTSTRAP = 2000
SAIDA = RESULTADOS_DIR / "mil_atencao"


class ABMIL(nn.Module):
    def __init__(self, d_in=1536, d_h=256, d_att=128, k=4):
        super().__init__()
        self.proj = nn.Sequential(nn.Linear(d_in, d_h), nn.ReLU(), nn.Dropout(0.25))
        self.att_v = nn.Sequential(nn.Linear(d_h, d_att), nn.Tanh())
        self.att_u = nn.Sequential(nn.Linear(d_h, d_att), nn.Sigmoid())
        self.att_w = nn.Linear(d_att, 1)
        self.cls = nn.Linear(d_h, k)

    def forward(self, x):
        h = self.proj(x)
        a = torch.softmax(self.att_w(self.att_v(h) * self.att_u(h)).squeeze(-1), dim=0)
        return self.cls((a.unsqueeze(-1) * h).sum(0)), a


def treinar(X, y, semente, dispositivo):
    torch.manual_seed(semente)
    rng = random.Random(semente)
    modelo = ABMIL().to(dispositivo)
    cont = np.bincount(y, minlength=4)
    peso = torch.tensor(len(y) / (4 * np.maximum(cont, 1)), dtype=torch.float32, device=dispositivo)
    opt = torch.optim.Adam(modelo.parameters(), lr=TAXA, weight_decay=DECAIMENTO)
    perda = nn.CrossEntropyLoss(weight=peso)
    idx = list(range(len(X)))
    for _ in range(EPOCAS):
        modelo.train()
        rng.shuffle(idx)
        for i in idx:
            opt.zero_grad()
            logit, _ = modelo(X[i].to(dispositivo))
            perda(logit.unsqueeze(0), torch.tensor([y[i]], device=dispositivo)).backward()
            opt.step()
    return modelo


def auc(pos, neg):
    return float(np.mean([(a > b) + 0.5 * (a == b) for a in pos for b in neg]))


def main():
    from lamina_inteira import FINAIS, acuracia_balanceada, amostra, classe_final, laminas_dev, laminas_teste
    from pacote_cotas import laminas as laminas_val
    from pacote_cotas import pacientes
    from resposta_em_conjunto import contem, responder, tres
    SAIDA.mkdir(parents=True, exist_ok=True)
    treino, teste = laminas_val() + laminas_dev(), laminas_teste()
    real = {s: classe_final(info_lamina(s)["rotulo"]) for s in treino + teste}
    pac = pacientes()
    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    Xtr = [torch.from_numpy(amostra(s)) for s in treino]
    ytr = np.array([FINAIS.index(real[s]) for s in treino])
    Xte = {s: torch.from_numpy(amostra(s)) for s in teste}

    probs = {s: np.zeros(4) for s in teste}
    atencao = {s: np.zeros(len(Xte[s])) for s in teste}
    for semente in SEMENTES:
        modelo = treinar(Xtr, ytr, semente, dispositivo)
        modelo.eval()
        with torch.no_grad():
            for s in teste:
                logit, a = modelo(Xte[s].to(dispositivo))
                probs[s] += torch.softmax(logit, 0).cpu().numpy() / len(SEMENTES)
                atencao[s] += a.cpu().numpy() / len(SEMENTES)
        print(f"  semente {semente} pronta", flush=True)
    for s in teste:
        np.save(SAIDA / f"{s}_atencao.npy", atencao[s].astype(np.float32))

    pred = {s: FINAIS[int(probs[s].argmax())] for s in teste}
    r, p = [real[s] for s in teste], [pred[s] for s in teste]
    ba = acuracia_balanceada(r, p)
    ba_ = [s for s in teste if real[s] in ("benigno", "atipico")]
    razao = {s: probs[s][1] / (probs[s][0] + probs[s][1]) for s in ba_}
    auc_bxa = auc([razao[s] for s in ba_ if real[s] == "atipico"], [razao[s] for s in ba_ if real[s] == "benigno"])
    mal = {s: probs[s][2] + probs[s][3] for s in teste}
    auc_mal = auc([mal[s] for s in teste if real[s] in ("DCIS", "IC")], [mal[s] for s in teste if real[s] not in ("DCIS", "IC")])
    grupos = {}
    for s in teste:
        grupos.setdefault(pac[s], []).append(s)
    chaves, rng, boot = sorted(grupos), random.Random(0), []
    for _ in range(N_BOOTSTRAP):
        am = [s for g in (rng.choice(chaves) for _ in chaves) for s in grupos[g]]
        boot.append(acuracia_balanceada([real[s] for s in am], [pred[s] for s in am]))
    conj = {s: responder(probs[s], 0.45) for s in teste}
    resumo = {"acuracia_balanceada_4_classes": round(ba, 3),
              "ic95": [round(float(np.percentile(boot, 2.5)), 3), round(float(np.percentile(boot, 97.5)), 3)],
              "acertos": f"{sum(a == b for a, b in zip(r, p))}/57",
              "por_classe": {c: f"{sum(a == b == c for a, b in zip(r, p))}/{r.count(c)}" for c in FINAIS},
              "preditas": dict(Counter(p)),
              "auc_benigno_x_atipico": round(auc_bxa, 3), "auc_maligno_x_resto": round(auc_mal, 3),
              "resposta_em_conjunto_d045": {
                  "acerto_do_conjunto": round(float(np.mean([contem(conj[s], tres(real[s])) for s in teste])), 3),
                  "respostas_exatas": round(float(np.mean([" ou " not in conj[s] for s in teste])), 3)},
              "por_lamina": {s: {"real": real[s], "predito": pred[s], "probabilidades": np.round(probs[s], 3).tolist()} for s in teste},
              "dispositivo": dispositivo}
    resumo["criterios"] = {"C1": ba > BA_REF, "C2": auc_bxa >= AUC_MIN}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"acurácia balanceada (4 classes): {resumo['acuracia_balanceada_4_classes']} IC95 {resumo['ic95']} | {resumo['acertos']} | {resumo['por_classe']} | {resumo['preditas']}")
    print(f"AUC benigno × atípico: {resumo['auc_benigno_x_atipico']} | AUC maligno × resto: {resumo['auc_maligno_x_resto']}")
    print(f"resposta em conjunto (d = 0,45): {resumo['resposta_em_conjunto_d045']}")
    print(f"Critérios fixados antes (C1: bal > {BA_REF}; C2: AUC benigno × atípico >= {AUC_MIN}): {resumo['criterios']}")


if __name__ == "__main__":
    main()
