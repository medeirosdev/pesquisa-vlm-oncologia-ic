# Experimento: trocar frases do descritor uma de cada vez

Rodado em 25/09/2026 17:24 por `experimento_frases.py`, sobre 3691 tiles rotulados de 8 lâminas (benigno 159, atípico 225, maligno 3307).

**Regra de aceite (fixada antes):** a troca fica se a média das 3 categorias subir ≥ 0.5 ponto. Guloso: cada troca é testada em cima das já aceitas.

**Ressalva:** as frases foram ajustadas olhando as mesmas lâminas em que são avaliadas — o ganho pode não se repetir em lâminas novas.

Ponto de partida: benigno 52.2%, atípico 60.9%, maligno 42.8%, **média 51.98%**.

| # | Categoria | Frase atual | Candidata | Benigno | Atípico | Maligno | Média | Δ média | Decisão |
|---|---|---|---|---|---|---|---|---|---|
| 1 | maligno | ductal carcinoma in situ | duct completely filled by atypical cells | 54.1% | 61.3% | 36.6% | 50.67% | -1.31 | **rejeitada** |
| 2 | atipico | atypical ductal hyperplasia | atypical cells partially filling a duct | 65.4% | 35.6% | 43.1% | 48.03% | -3.95 | **rejeitada** |
| 3 | atipico | focal atypical epithelial proliferation | focal atypical proliferation involving part of a duct | 52.8% | 57.8% | 53.6% | 54.72% | +2.74 | **aceita** |
| 4 | atipico | mild nuclear atypia | mild uniform nuclear atypia | 52.8% | 57.8% | 53.6% | 54.72% | +0.00 | **rejeitada** |
| 5 | atipico | usual ductal hyperplasia | heterogeneous streaming cells with peripheral slit-like spaces | 52.8% | 57.8% | 53.6% | 54.72% | +0.00 | **rejeitada** |
| 6 | atipico | flat epithelial atypia | one to few layers of atypical columnar cells lining acini | 52.8% | 57.8% | 53.6% | 54.73% | +0.01 | **rejeitada** |
| 7 | maligno | high nuclear pleomorphism | large pleomorphic nuclei with prominent nucleoli | 52.8% | 57.3% | 59.4% | 56.51% | +1.79 | **aceita** |
| 8 | maligno | invasive carcinoma | irregular infiltrating glands without myoepithelial cells | 52.8% | 57.3% | 59.4% | 56.51% | +0.00 | **rejeitada** |
| 9 | maligno | tumor nests | solid nests of malignant cells in desmoplastic stroma | 52.8% | 57.3% | 59.2% | 56.45% | -0.06 | **rejeitada** |
| 10 | benigno | unremarkable breast lobules | small lobules with open acini and bland nuclei | 54.1% | 56.4% | 58.2% | 56.25% | -0.26 | **rejeitada** |
| 11 | benigno | normal breast parenchyma | normal breast parenchyma with loose intralobular stroma | 59.1% | 51.6% | 51.2% | 53.95% | -2.56 | **rejeitada** |
| 12 | benigno | fibroadenoma | fibroadenoma with compressed slit-like ducts in cellular stroma | 52.8% | 57.3% | 59.4% | 56.51% | +0.00 | **rejeitada** |
| 13 | benigno | sclerosing adenosis | sclerosing adenosis with compressed glands and preserved myoepithelial cells | 52.8% | 57.3% | 59.5% | 56.55% | +0.04 | **rejeitada** |
| 14 | benigno | apocrine metaplasia | apocrine cells with abundant granular eosinophilic cytoplasm | 52.8% | 57.8% | 59.3% | 56.65% | +0.14 | **rejeitada** |

**Final:** benigno 52.8%, atípico 57.3%, maligno 59.4%, **média 56.51%** (partida: 51.98%).

Trocas aceitas (2): "focal atypical epithelial proliferation" → "focal atypical proliferation involving part of a duct"; "high nuclear pleomorphism" → "large pleomorphic nuclei with prominent nucleoli"
