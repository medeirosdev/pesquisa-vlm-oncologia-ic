"""
MIL com atenção em grafo (GAT-MIL): o ABMIL de mil_atencao.py com uma camada de atenção entre patches vizinhos antes
do pooling. Genérico: serve pra qualquer dataset que tenha, por lâmina/biópsia, os embeddings dos patches
(amostra2000.npy), as coordenadas (amostra2000_xy.csv) e o lado do patch em pixels.

Por quê: o ABMIL trata a lâmina como um saco de patches, sem saber quem é vizinho de quem. Em vários diagnósticos a
arquitetura conta (no Gleason, glândulas separadas, fundidas ou ausentes). Aqui cada patch, antes de entrar no
pooling, mistura o próprio embedding com o dos vizinhos encostados, com um peso aprendido por vizinho.

Grafo: nó = patch da amostra; aresta entre patches cujos cantos distam no máximo 1 lado em x e em y (os 8 vizinhos
da grade), mais a aresta do patch com ele mesmo. Com amostra parcial (lâminas com mais de 2.000 patches de tecido),
parte dos vizinhos falta e o grafo fica mais esparso.

Modelo: 1.536 -> 256 (ReLU, dropout 0,25), como no ABMIL; uma camada GATv2 (Brody et al., 2022) com 4 cabeças de 64,
saída somada ao embedding (residual), ELU e dropout 0,25; depois a atenção com porta de 128 do ABMIL (Ilse et al.,
2018) e a camada de classe. Treino idêntico ao de mil_atencao.treinar: entropia cruzada com pesos balanceados, Adam
1e-4, decaimento 1e-4, 40 épocas, uma lâmina por passo, sem parada antecipada.
"""

import random

import numpy as np
import torch
from torch import nn

from mil_atencao import DECAIMENTO, EPOCAS, TAXA


def arestas_vizinhos(xy, lado):
    """Arestas (origem, destino) entre patches com |dx| <= lado e |dy| <= lado, incluindo o próprio patch."""
    xy = np.asarray(xy, dtype=np.int64)
    celula = {(int(x) // lado, int(y) // lado): i for i, (x, y) in enumerate(xy)}
    origem, destino = [], []
    for i, (x, y) in enumerate(xy):
        cx, cy = int(x) // lado, int(y) // lado
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                j = celula.get((cx + dx, cy + dy))
                if j is not None:
                    origem.append(j)
                    destino.append(i)
    return torch.tensor([origem, destino], dtype=torch.long)


class CamadaGATv2(nn.Module):
    def __init__(self, d, cabecas=4):
        super().__init__()
        self.c, self.dc = cabecas, d // cabecas
        self.w_origem = nn.Linear(d, d)
        self.w_destino = nn.Linear(d, d)
        self.a = nn.Parameter(torch.empty(cabecas, self.dc))
        nn.init.xavier_uniform_(self.a)

    def forward(self, h, arestas):
        n = h.shape[0]
        o, d = arestas[0], arestas[1]
        ho = self.w_origem(h).view(n, self.c, self.dc)
        hd = self.w_destino(h).view(n, self.c, self.dc)
        e = (nn.functional.leaky_relu(ho[o] + hd[d], 0.2) * self.a).sum(-1)  # (arestas, cabeças)
        maximo = torch.full((n, self.c), -torch.inf, device=h.device).scatter_reduce(
            0, d.unsqueeze(1).expand_as(e), e, reduce="amax", include_self=True)
        e = torch.exp(e - maximo[d])
        soma = torch.zeros(n, self.c, device=h.device).index_add_(0, d, e)
        alfa = e / soma[d]
        saida = torch.zeros(n, self.c, self.dc, device=h.device).index_add_(0, d, alfa.unsqueeze(-1) * ho[o])
        return saida.reshape(n, -1), alfa


class GATMIL(nn.Module):
    def __init__(self, d_in=1536, d_h=256, d_att=128, k=4, cabecas=4):
        super().__init__()
        self.proj = nn.Sequential(nn.Linear(d_in, d_h), nn.ReLU(), nn.Dropout(0.25))
        self.gat = CamadaGATv2(d_h, cabecas)
        self.pos_gat = nn.Sequential(nn.ELU(), nn.Dropout(0.25))
        self.att_v = nn.Sequential(nn.Linear(d_h, d_att), nn.Tanh())
        self.att_u = nn.Sequential(nn.Linear(d_h, d_att), nn.Sigmoid())
        self.att_w = nn.Linear(d_att, 1)
        self.cls = nn.Linear(d_h, k)

    def forward(self, x, arestas):
        h = self.proj(x)
        g, alfa = self.gat(h, arestas)
        h = self.pos_gat(h + g)
        a = torch.softmax(self.att_w(self.att_v(h) * self.att_u(h)).squeeze(-1), dim=0)
        return self.cls((a.unsqueeze(-1) * h).sum(0)), a, alfa


def treinar(X, G, y, semente, dispositivo, k=4):
    """Mesma receita de mil_atencao.treinar; G[i] = arestas da lâmina i (arestas_vizinhos)."""
    torch.manual_seed(semente)
    rng = random.Random(semente)
    modelo = GATMIL(k=k).to(dispositivo)
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
            logit, _, _ = modelo(X[i].to(dispositivo), G[i].to(dispositivo))
            perda(logit.unsqueeze(0), torch.tensor([y[i]], device=dispositivo)).backward()
            opt.step()
    return modelo
