# Pipeline 01 em várias lâminas — consistência

Gerado por `scripts/rodar_todas_laminas.py` em 25/09/2026 17:08. Números por lâmina; detalhes em `resultados/<lamina>/`.

## Estágio 1 — filtro de tecido (recall contra RoIs anotados)

| Lâmina | Rótulo | Níveis da pirâmide | RoIs localizados | Classes dos RoIs | Cobertura média | RoIs ≥50% cobertos |
|---|---|---|---|---|---|---|
| BRACS_1003677 | IC | 1/4/16x | 1/1 | IC 1 | 100% | 100% |
| BRACS_1003718 | N | 1/4/8x | 1/1 | N 1 | 38% | 0% |
| BRACS_1271 | ADH | 1/4/16/32x | 16/16 | ADH 4, FEA 6, PB 2, UDH 4 | 90% | 100% |
| BRACS_1370 | PB | 1/4/16/32x | 5/5 | N 3, PB 2 | 96% | 100% |
| BRACS_1489 | DCIS | 1/4/16/32x | 18/18 | DCIS 18 | 87% | 100% |
| BRACS_1592 | UDH | 1/4/16/32x | 2/2 | N 1, UDH 1 | 74% | 100% |
| BRACS_1774 | FEA | 1/4/16/32x | 12/12 | FEA 8, PB 4 | 97% | 100% |
| BRACS_748 | IC | 1/4/16/32x | 98/98 | ADH 4, DCIS 84, IC 10 | 96% | 100% |

## Estágio 2 — roteador (banco v2)

| Lâmina | Candidatos | Precisão k=32 (aleatório) | Recall k=32 | Precisão k=256 (aleatório) | Recall k=256 |
|---|---|---|---|---|---|
| BRACS_1003677 | 616 | 0% (5%) | 0% | 4% (4%) | 100% |
| BRACS_1003718 | 76 | 4% (1%) | 100% | — (—) | — |
| BRACS_1271 | 2393 | 6% (7%) | 25% | 10% (7%) | 81% |
| BRACS_1370 | 2594 | 6% (3%) | 40% | 6% (4%) | 100% |
| BRACS_1489 | 1804 | 50% (35%) | 56% | 39% (34%) | 100% |
| BRACS_1592 | 229 | 9% (9%) | 100% | — (—) | — |
| BRACS_1774 | 4801 | 9% (1%) | 25% | 4% (2%) | 92% |
| BRACS_748 | 15138 | 56% (19%) | 18% | 55% (18%) | 59% |

## Estágio 3 — descritor nos k=32 patches do roteador

Categorias = quantos patches o descritor chamou de benigno / atípico / maligno.

| Lâmina | Rótulo | Bruto: categorias | Bruto: achado dominante (% patches) | Normalizado: categorias | Normalizado: achado dominante (% patches) |
|---|---|---|---|---|---|
| BRACS_1003677 | IC | 1 / 11 / 20 | atypical ductal hyperplasia, micropapillary architecture (47%) | 1 / 4 / 27 | desmoplastic stroma, micropapillary architecture (19%) |
| BRACS_1003718 | N | 18 / 4 / 0 | normal breast tissue, normal terminal duct lobular unit (18%) | 3 / 7 / 12 | columnar cell lesion with atypia, solid growth pattern (4%) |
| BRACS_1271 | ADH | 1 / 16 / 15 | atypical ductal hyperplasia, micropapillary architecture (31%) | 0 / 16 / 16 | irregular slit-like fenestrations, micropapillary architecture (12%) |
| BRACS_1370 | PB | 15 / 7 / 10 | normal breast tissue, normal terminal duct lobular unit (19%) | 0 / 15 / 17 | irregular slit-like fenestrations, mild nuclear atypia (9%) |
| BRACS_1489 | DCIS | 7 / 15 / 10 | focal atypical epithelial proliferation, mitotic figures (38%) | 0 / 8 / 24 | comedonecrosis, mitotic figures (12%) |
| BRACS_1592 | UDH | 25 / 4 / 3 | normal terminal duct lobular unit, partial duct involvement by atypical cells (19%) | 7 / 11 / 14 | micropapillary architecture, overlapping nuclei without atypia (6%) |
| BRACS_1774 | FEA | 0 / 21 / 11 | focal atypical epithelial proliferation, micropapillary architecture (22%) | 0 / 15 / 17 | mild nuclear atypia, overlapping nuclei without atypia (12%) |
| BRACS_748 | IC | 0 / 9 / 23 | high nuclear pleomorphism, irregular slit-like fenestrations (62%) | 0 / 25 / 7 | irregular slit-like fenestrations, solid growth pattern (25%) |

## Validação — o descritor acerta a categoria (benigno / atípico / maligno)?

Todos os tiles que caem dentro de RoIs anotados, não só o top-k. Baseline = sempre chutar a categoria majoritária.

| Lâmina | Categorias reais (b / a / m) | Bruto: acurácia | Bruto: previstas (b / a / m) | Normalizado: acurácia | Normalizado: previstas (b / a / m) | Baseline |
|---|---|---|---|---|---|---|
| BRACS_1003677 | 0 / 0 / 25 (n=25) | 12% | 13 / 9 / 3 | 8% | 21 / 2 / 2 | 100% |
| BRACS_1003718 | 1 / 0 / 0 (n=1) | 100% | 1 / 0 / 0 | 0% | 0 / 0 / 1 | 100% |
| BRACS_1271 | 33 / 135 / 0 (n=168) | 60% | 38 / 125 / 5 | 39% | 19 / 73 / 76 | 80% |
| BRACS_1370 | 94 / 0 / 0 (n=94) | 88% | 83 / 5 / 6 | 30% | 28 / 24 / 42 | 100% |
| BRACS_1489 | 0 / 0 / 626 (n=626) | 7% | 444 / 138 / 44 | 46% | 150 / 190 / 286 | 100% |
| BRACS_1592 | 15 / 7 / 0 (n=22) | 55% | 19 / 3 / 0 | 27% | 3 / 11 / 8 | 68% |
| BRACS_1774 | 16 / 47 / 0 (n=63) | 43% | 16 / 33 / 14 | 24% | 10 / 21 / 32 | 75% |
| BRACS_748 | 0 / 36 / 2656 (n=2692) | 39% | 933 / 689 / 1070 | 38% | 311 / 1352 / 1029 | 99% |

## Validação — classificação por banco de frases de classe

"Presentes" = argmax só entre as classes que existem nos RoIs da lâmina; "7 classes" = entre todos os bancos. Baseline = sempre chutar a classe majoritária.

| Lâmina | Por patch (presentes / 7 classes / baseline) | Por RoI (presentes / baseline) | Borda (presentes) | Interior (presentes) |
|---|---|---|---|---|
| BRACS_1003677 | — / 12% / 100% (n=25) | — / 100% (n=1) | — (n=0) | — (n=0) |
| BRACS_1003718 | — / 100% / 100% (n=1) | — / — (n=0) | — (n=0) | — (n=0) |
| BRACS_1271 | 15% / 11% / 49% (n=168) | 25% / 38% (n=16) | 25% (n=16) | 0% (n=5) |
| BRACS_1370 | 66% / 57% / 66% (n=94) | 60% / 60% (n=5) | 60% (n=5) | 100% (n=3) |
| BRACS_1489 | — / 2% / 100% (n=626) | — / 100% (n=18) | — (n=0) | — (n=0) |
| BRACS_1592 | 59% / 55% / 68% (n=22) | 50% / 50% (n=2) | 50% (n=2) | 0% (n=1) |
| BRACS_1774 | 33% / 0% / 75% (n=63) | 42% / 67% (n=12) | 42% (n=12) | — (n=0) |
| BRACS_748 | 24% / 10% / 80% (n=2692) | 27% / 86% (n=98) | 39% (n=98) | 9% (n=69) |
