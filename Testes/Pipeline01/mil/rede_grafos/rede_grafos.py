"""
Rede de grafos (ideia proposta em 14/11/2026): em vez de um grafo sobre patches sorteados, o modelo olha primeiro a
lâmina inteira, escolhe pontos de interesse, monta um grafo local denso em volta de cada ponto e liga os pontos numa
rede, com as distâncias entre eles. Genérico: serve pra qualquer dataset com embeddings de todos os patches de tecido
em volta dos pontos escolhidos (no PANDA, todas as biópsias já têm todos os patches).

Etapas:
  1. Pontos de interesse: os patches de maior atenção de um MIL (ABMIL) que não viu a lâmina; escolha gulosa por
     atenção decrescente, com centros a pelo menos DIST_MIN_UM um do outro, até N_PONTOS.
  2. Grafo local: em volta de cada ponto, todos os patches de tecido numa janela de 7 x 7 patches (3 pra cada lado),
     ligados aos vizinhos encostados (8 vizinhos) e a si mesmos. Uma camada GATv2 (gat_mil.CamadaGATv2, residual,
     ELU, dropout 0,25) e um pooling com atenção com porta resumem cada janela num vetor.
  3. Rede dos pontos: os vetores das janelas são nós de um grafo completo entre os pontos; uma camada de atenção
     GATv2 com um termo que diminui a atenção com a distância entre os pontos (peso aprendido, em mm); depois pooling
     com atenção com porta e a camada de classe.
  (Protótipos por classe, a quarta parte da ideia, ficam pra uma versão seguinte.)
"""

import random

import numpy as np
import torch
from torch import nn

from gat_mil import CamadaGATv2
from mil_atencao import DECAIMENTO, EPOCAS, TAXA

N_PONTOS = 16
MEIA_JANELA = 3        # 7 x 7 patches
DIST_MIN_UM = 1000.0
LADO_UM = 128.0


def pontos_de_interesse(celulas, atencao, n=N_PONTOS, dist_min_um=DIST_MIN_UM):
    """celulas: (N, 2) posição de cada patch na grade (em patches). Devolve índices dos patches escolhidos."""
    escolhidos = []
    for i in np.argsort(-atencao, kind="stable"):
        c = celulas[i]
        if all(np.hypot(*(c - celulas[j])) * LADO_UM >= dist_min_um for j in escolhidos):
            escolhidos.append(int(i))
            if len(escolhidos) == n:
                break
    return escolhidos


def montar(xy, lado, atencao):
    """Estrutura de uma lâmina: janelas (índices dos patches), arestas locais (já com o deslocamento do lote),
    segmento de cada nó local, posição dos pontos em mm."""
    celulas = np.asarray(xy, dtype=np.int64) // int(lado)
    por_celula = {(int(x), int(y)): i for i, (x, y) in enumerate(celulas)}
    pontos = pontos_de_interesse(celulas, np.asarray(atencao))
    nos, seg, origem, destino = [], [], [], []
    for p, i in enumerate(pontos):
        cx, cy = celulas[i]
        janela = [por_celula[(cx + dx, cy + dy)] for dx in range(-MEIA_JANELA, MEIA_JANELA + 1)
                  for dy in range(-MEIA_JANELA, MEIA_JANELA + 1) if (cx + dx, cy + dy) in por_celula]
        base = len(nos)
        local = {j: base + k for k, j in enumerate(janela)}
        for j in janela:
            jx, jy = celulas[j]
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    v = por_celula.get((jx + dx, jy + dy))
                    if v is not None and v in local:
                        origem.append(local[v])
                        destino.append(local[j])
        nos += janela
        seg += [p] * len(janela)
    pos_mm = celulas[pontos] * LADO_UM / 1000.0
    return {"nos": torch.tensor(nos, dtype=torch.long), "seg": torch.tensor(seg, dtype=torch.long),
            "arestas": torch.tensor([origem, destino], dtype=torch.long),
            "pos_mm": torch.tensor(pos_mm, dtype=torch.float32), "pontos": pontos}


def softmax_segmentos(e, seg, n):
    maximo = torch.full((n,), -torch.inf, device=e.device).scatter_reduce(0, seg, e, reduce="amax", include_self=True)
    e = torch.exp(e - maximo[seg])
    return e / torch.zeros(n, device=e.device).index_add_(0, seg, e)[seg]


class PoolingPorta(nn.Module):
    def __init__(self, d, d_att=128):
        super().__init__()
        self.v = nn.Sequential(nn.Linear(d, d_att), nn.Tanh())
        self.u = nn.Sequential(nn.Linear(d, d_att), nn.Sigmoid())
        self.w = nn.Linear(d_att, 1)

    def forward(self, h, seg, n):
        a = softmax_segmentos(self.w(self.v(h) * self.u(h)).squeeze(-1), seg, n)
        return torch.zeros(n, h.shape[1], device=h.device).index_add_(0, seg, a.unsqueeze(-1) * h), a


class CamadaDistancia(nn.Module):
    """GATv2 num grafo completo entre os pontos, com -softplus(w) * distância (mm) somado ao escore da aresta."""

    def __init__(self, d, cabecas=4):
        super().__init__()
        self.c, self.dc = cabecas, d // cabecas
        self.w_origem, self.w_destino = nn.Linear(d, d), nn.Linear(d, d)
        self.a = nn.Parameter(torch.empty(cabecas, self.dc))
        nn.init.xavier_uniform_(self.a)
        self.w_dist = nn.Parameter(torch.zeros(cabecas))

    def forward(self, h, pos_mm):
        n = h.shape[0]
        ho = self.w_origem(h).view(n, self.c, self.dc)
        hd = self.w_destino(h).view(n, self.c, self.dc)
        e = (nn.functional.leaky_relu(hd.unsqueeze(1) + ho.unsqueeze(0), 0.2) * self.a).sum(-1)  # (destino, origem, c)
        e = e - nn.functional.softplus(self.w_dist) * torch.cdist(pos_mm, pos_mm).unsqueeze(-1)
        alfa = torch.softmax(e, dim=1)
        return torch.einsum("ijc,jcd->icd", alfa, ho).reshape(n, -1), alfa


class RedeGrafos(nn.Module):
    def __init__(self, d_in=1536, d_h=256, k=4, cabecas=4):
        super().__init__()
        self.proj = nn.Sequential(nn.Linear(d_in, d_h), nn.ReLU(), nn.Dropout(0.25))
        self.gat_local = CamadaGATv2(d_h, cabecas)
        self.pos_local = nn.Sequential(nn.ELU(), nn.Dropout(0.25))
        self.pool_local = PoolingPorta(d_h)
        self.gat_pontos = CamadaDistancia(d_h, cabecas)
        self.pos_pontos = nn.Sequential(nn.ELU(), nn.Dropout(0.25))
        self.pool_pontos = PoolingPorta(d_h)
        self.cls = nn.Linear(d_h, k)

    def forward(self, x, g):
        h = self.proj(x[g["nos"]])
        h = self.pos_local(h + self.gat_local(h, g["arestas"])[0])
        n = len(g["pontos"])
        z, _ = self.pool_local(h, g["seg"], n)
        z = self.pos_pontos(z + self.gat_pontos(z, g["pos_mm"])[0])
        v, a = self.pool_pontos(z, torch.zeros(n, dtype=torch.long, device=z.device), 1)
        return self.cls(v[0]), a


def para(g, dispositivo):
    return {k: (v.to(dispositivo) if torch.is_tensor(v) else v) for k, v in g.items()}


def treinar(X, G, y, semente, dispositivo, k=4):
    """Mesma receita de mil_atencao.treinar; G[i] = montar(...) da lâmina i."""
    torch.manual_seed(semente)
    rng = random.Random(semente)
    modelo = RedeGrafos(k=k).to(dispositivo)
    cont = np.bincount(y, minlength=k)
    peso = torch.tensor(len(y) / (k * np.maximum(cont, 1)), dtype=torch.float32, device=dispositivo)
    opt = torch.optim.Adam(modelo.parameters(), lr=TAXA, weight_decay=DECAIMENTO)
    perda = nn.CrossEntropyLoss(weight=peso)
    idx = list(range(len(X)))
    for _ in range(EPOCAS):
        modelo.train()
        rng.shuffle(idx)
        for i in idx:
            opt.zero_grad()
            logit, _ = modelo(X[i].to(dispositivo), para(G[i], dispositivo))
            perda(logit.unsqueeze(0), torch.tensor([y[i]], device=dispositivo)).backward()
            opt.step()
    return modelo
