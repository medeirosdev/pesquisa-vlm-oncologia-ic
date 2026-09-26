# Pipeline 01 em várias lâminas — consistência

Gerado por `scripts/rodar_todas_laminas.py` em 25/09/2026 21:54. Números por lâmina; detalhes em `resultados/<lamina>/`.

## Estágio 1 — filtro de tecido (recall contra RoIs anotados)

| Lâmina | Rótulo | Níveis da pirâmide | RoIs localizados | Classes dos RoIs | Cobertura média | RoIs ≥50% cobertos |
|---|---|---|---|---|---|---|
| BRACS_1003677 | IC | 1/4/16x | 1/1 | IC 1 | 100% | 100% |
| BRACS_1003718 | N | 1/4/8x | 1/1 | N 1 | 38% | 0% |
| BRACS_1271 | ADH | 1/4/16/32x | 16/16 | ADH 4, FEA 6, PB 2, UDH 4 | 90% | 100% |
| BRACS_1320 | PB | 1/4/16/64x | 20/20 | N 2, PB 18 | 99% | 100% |
| BRACS_1370 | PB | 1/4/16/32x | 5/5 | N 3, PB 2 | 96% | 100% |
| BRACS_1489 | DCIS | 1/4/16/32x | 18/18 | DCIS 18 | 87% | 100% |
| BRACS_1494 | ADH | 1/4/16/32x | 55/55 | ADH 11, FEA 1, N 2, PB 5, UDH 36 | 88% | 91% |
| BRACS_1507 | N | 1/4/16/64x | 10/10 | N 10 | 90% | 90% |
| BRACS_1512 | DCIS | 1/4/16/32x | 25/25 | DCIS 25 | 83% | 100% |
| BRACS_1592 | UDH | 1/4/16/32x | 2/2 | N 1, UDH 1 | 74% | 100% |
| BRACS_1617 | UDH | 1/4/16/32x | 16/16 | N 2, PB 3, UDH 11 | 99% | 100% |
| BRACS_1641 | N | 1/4/16/32x | 4/4 | N 4 | 94% | 100% |
| BRACS_1774 | FEA | 1/4/16/32x | 12/12 | FEA 8, PB 4 | 97% | 100% |
| BRACS_297 | IC | 1/4/16/32x | 31/31 | IC 22, N 7, PB 2 | 99% | 100% |
| BRACS_743 | FEA | 1/4/16/32x | 28/28 | FEA 8, N 1, PB 19 | 94% | 100% |
| BRACS_748 | IC | 1/4/16/32x | 98/98 | ADH 4, DCIS 84, IC 10 | 96% | 100% |

## Estágio 2 — roteador (banco v2)

| Lâmina | Candidatos | Precisão k=32 (aleatório) | Recall k=32 | Precisão k=256 (aleatório) | Recall k=256 |
|---|---|---|---|---|---|
| BRACS_1003677 | 616 | 0% (5%) | 0% | 4% (4%) | 100% |
| BRACS_1003718 | 76 | 4% (1%) | 100% | — (—) | — |
| BRACS_1271 | 2393 | 6% (7%) | 25% | 10% (7%) | 81% |
| BRACS_1320 | 15280 | 31% (6%) | 30% | 15% (7%) | 60% |
| BRACS_1370 | 2594 | 6% (3%) | 40% | 6% (4%) | 100% |
| BRACS_1489 | 1804 | 50% (35%) | 56% | 39% (34%) | 100% |
| BRACS_1494 | 4689 | 25% (9%) | 14% | 18% (12%) | 64% |
| BRACS_1507 | 4309 | 22% (7%) | 50% | 16% (7%) | 100% |
| BRACS_1512 | 4828 | 12% (16%) | 12% | 16% (16%) | 80% |
| BRACS_1592 | 229 | 9% (9%) | 100% | — (—) | — |
| BRACS_1617 | 3494 | 12% (6%) | 25% | 9% (6%) | 88% |
| BRACS_1641 | 1265 | 9% (9%) | 100% | 9% (10%) | 100% |
| BRACS_1774 | 4801 | 9% (1%) | 25% | 4% (2%) | 92% |
| BRACS_297 | 12323 | 59% (23%) | 29% | 41% (23%) | 71% |
| BRACS_743 | 22685 | 0% (4%) | 0% | 1% (4%) | 11% |
| BRACS_748 | 15138 | 56% (19%) | 18% | 55% (18%) | 59% |

## Estágio 3 — descritor nos k=32 patches do roteador

Categorias = quantos patches o descritor chamou de benigno / atípico / maligno.

| Lâmina | Rótulo | Bruto: categorias | Bruto: achado dominante (% patches) | Normalizado: categorias | Normalizado: achado dominante (% patches) |
|---|---|---|---|---|---|
| BRACS_1003677 | IC | 0 / 11 / 21 | atypical ductal hyperplasia, micropapillary architecture (47%) | 1 / 4 / 27 | desmoplastic stroma, micropapillary architecture (19%) |
| BRACS_1003718 | N | 11 / 10 / 1 | fibroadenoma, normal breast tissue (14%) | 3 / 7 / 12 | columnar cell lesion with atypia, solid growth pattern (4%) |
| BRACS_1271 | ADH | 1 / 16 / 15 | atypical ductal hyperplasia, micropapillary architecture (31%) | 0 / 16 / 16 | irregular slit-like fenestrations, micropapillary architecture (12%) |
| BRACS_1320 | PB | 1 / 5 / 26 | ductal carcinoma in situ, high nuclear pleomorphism (31%) | 1 / 13 / 18 | high nuclear pleomorphism, irregular slit-like fenestrations (9%) |
| BRACS_1370 | PB | 14 / 7 / 11 | high nuclear pleomorphism, normal breast tissue (22%) | 0 / 15 / 17 | irregular slit-like fenestrations, mild nuclear atypia (9%) |
| BRACS_1489 | DCIS | 0 / 21 / 11 | focal atypical epithelial proliferation, mitotic figures (44%) | 0 / 8 / 24 | comedonecrosis, mitotic figures (12%) |
| BRACS_1494 | ADH | 0 / 11 / 21 | high nuclear pleomorphism, infiltrating tumor cells within stroma (25%) | 0 / 10 / 22 | irregular slit-like fenestrations, mitotic figures (50%) |
| BRACS_1507 | N | 1 / 12 / 19 | atypical ductal hyperplasia, micropapillary architecture (28%) | 0 / 8 / 24 | micropapillary architecture, mild nuclear atypia (19%) |
| BRACS_1512 | DCIS | 0 / 7 / 25 | high nuclear pleomorphism, mitotic figures (28%) | 0 / 2 / 30 | comedonecrosis, mitotic figures (25%) |
| BRACS_1592 | UDH | 7 / 14 / 11 | high nuclear pleomorphism, partial duct involvement by atypical cells (25%) | 9 / 10 / 13 | micropapillary architecture, overlapping nuclei without atypia (6%) |
| BRACS_1617 | UDH | 7 / 19 / 6 | high nuclear pleomorphism, partial duct involvement by atypical cells (16%) | 0 / 8 / 24 | mild nuclear atypia, solid growth pattern (6%) |
| BRACS_1641 | N | 1 / 17 / 14 | focal atypical epithelial proliferation, micropapillary architecture (22%) | 0 / 12 / 20 | irregular slit-like fenestrations, micropapillary architecture (19%) |
| BRACS_1774 | FEA | 0 / 21 / 11 | focal atypical epithelial proliferation, high nuclear pleomorphism (25%) | 0 / 15 / 17 | mild nuclear atypia, overlapping nuclei without atypia (12%) |
| BRACS_297 | IC | 0 / 0 / 32 | infiltrating tumor cells within stroma, micropapillary architecture (88%) | 0 / 1 / 31 | micropapillary architecture, mild nuclear atypia (38%) |
| BRACS_743 | FEA | 0 / 0 / 32 | desmoplastic stroma, focal atypical epithelial proliferation (44%) | 0 / 5 / 27 | columnar cell lesion with atypia, desmoplastic stroma (31%) |
| BRACS_748 | IC | 0 / 9 / 23 | high nuclear pleomorphism, irregular slit-like fenestrations (62%) | 0 / 25 / 7 | irregular slit-like fenestrations, solid growth pattern (25%) |

## Validação — o descritor acerta a categoria (benigno / atípico / maligno)?

Todos os tiles que caem dentro de RoIs anotados, não só o top-k. Baseline = sempre chutar a categoria majoritária.

| Lâmina | Categorias reais (b / a / m) | Bruto: acurácia | Bruto: previstas (b / a / m) | Normalizado: acurácia | Normalizado: previstas (b / a / m) | Baseline |
|---|---|---|---|---|---|---|
| BRACS_1003677 | 0 / 0 / 25 (n=25) | 12% | 12 / 10 / 3 | 4% | 24 / 0 / 1 | 100% |
| BRACS_1003718 | 1 / 0 / 0 (n=1) | 0% | 0 / 1 / 0 | 0% | 0 / 0 / 1 | 100% |
| BRACS_1271 | 33 / 135 / 0 (n=168) | 63% | 29 / 132 / 7 | 39% | 19 / 72 / 77 | 80% |
| BRACS_1320 | 1031 / 0 / 0 (n=1031) | 69% | 711 / 79 / 241 | 31% | 315 / 179 / 537 | 100% |
| BRACS_1370 | 94 / 0 / 0 (n=94) | 83% | 78 / 9 / 7 | 33% | 31 / 23 / 40 | 100% |
| BRACS_1489 | 0 / 0 / 626 (n=626) | 27% | 24 / 432 / 170 | 46% | 149 / 191 / 286 | 100% |
| BRACS_1494 | 50 / 477 / 0 (n=527) | 44% | 23 / 245 / 259 | 28% | 79 / 147 / 301 | 91% |
| BRACS_1507 | 305 / 0 / 0 (n=305) | 51% | 156 / 89 / 60 | 17% | 53 / 85 / 167 | 100% |
| BRACS_1512 | 0 / 0 / 772 (n=772) | 34% | 127 / 379 / 266 | 38% | 215 / 260 / 297 | 100% |
| BRACS_1592 | 15 / 7 / 0 (n=22) | 36% | 2 / 19 / 1 | 27% | 4 / 11 / 7 | 68% |
| BRACS_1617 | 68 / 150 / 0 (n=218) | 38% | 165 / 41 / 12 | 23% | 48 / 46 / 124 | 69% |
| BRACS_1641 | 121 / 0 / 0 (n=121) | 65% | 79 / 21 / 21 | 23% | 28 / 30 / 63 | 100% |
| BRACS_1774 | 16 / 47 / 0 (n=63) | 44% | 7 / 41 / 15 | 22% | 11 / 20 / 32 | 75% |
| BRACS_297 | 150 / 0 / 2570 (n=2720) | 70% | 482 / 448 / 1790 | 52% | 432 / 925 / 1363 | 94% |
| BRACS_743 | 757 / 120 / 0 (n=877) | 39% | 319 / 348 / 210 | 37% | 307 / 259 / 311 | 86% |
| BRACS_748 | 0 / 36 / 2656 (n=2692) | 46% | 636 / 797 / 1259 | 38% | 299 / 1359 / 1034 | 99% |

## Validação — classificação por banco de frases de classe

"Presentes" = argmax só entre as classes que existem nos RoIs da lâmina; "7 classes" = entre todos os bancos. Baseline = sempre chutar a classe majoritária.

| Lâmina | Por patch (presentes / 7 classes / baseline) | Por RoI (presentes / baseline) | Borda (presentes) | Interior (presentes) |
|---|---|---|---|---|
| BRACS_1003677 | — / 12% / 100% (n=25) | — / 100% (n=1) | — (n=0) | — (n=0) |
| BRACS_1003718 | — / 100% / 100% (n=1) | — / — (n=0) | — (n=0) | — (n=0) |
| BRACS_1271 | 15% / 11% / 49% (n=168) | 25% / 38% (n=16) | 25% (n=16) | 0% (n=5) |
| BRACS_1320 | 12% / 8% / 90% (n=1031) | 10% / 90% (n=20) | 10% (n=20) | 10% (n=20) |
| BRACS_1370 | 66% / 57% / 66% (n=94) | 60% / 60% (n=5) | 60% (n=5) | 100% (n=3) |
| BRACS_1489 | — / 2% / 100% (n=626) | — / 100% (n=18) | — (n=0) | — (n=0) |
| BRACS_1494 | 14% / 11% / 72% (n=527) | 13% / 67% (n=54) | 13% (n=55) | 40% (n=10) |
| BRACS_1507 | — / 52% / 100% (n=305) | — / 100% (n=10) | — (n=0) | — (n=0) |
| BRACS_1512 | — / 3% / 100% (n=772) | — / 100% (n=25) | — (n=0) | — (n=0) |
| BRACS_1592 | 59% / 55% / 68% (n=22) | 50% / 50% (n=2) | 50% (n=2) | 0% (n=1) |
| BRACS_1617 | 11% / 11% / 69% (n=218) | 12% / 69% (n=16) | 12% (n=16) | 0% (n=4) |
| BRACS_1641 | — / 78% / 100% (n=121) | — / 100% (n=4) | — (n=0) | — (n=0) |
| BRACS_1774 | 33% / 0% / 75% (n=63) | 42% / 67% (n=12) | 42% (n=12) | — (n=0) |
| BRACS_297 | 60% / 49% / 94% (n=2720) | 65% / 71% (n=31) | 58% (n=31) | 75% (n=28) |
| BRACS_743 | 21% / 12% / 82% (n=877) | 7% / 68% (n=28) | 14% (n=28) | 15% (n=20) |
| BRACS_748 | 24% / 10% / 80% (n=2692) | 27% / 86% (n=98) | 39% (n=98) | 9% (n=69) |
