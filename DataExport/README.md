# DataExport

Dados de núcleos (CellViT) exportados do Pipeline Ideia 01 para outro projeto. Nada foi recalculado: os arquivos reformatam resultados já existentes. Gerados por `Testes/Pipeline01/scripts/exportar_dataexport.py`.

## Pedido

> O que precisa do seu pipeline (Fase 3 em diante):
> Não consigo rodar o CellViT aqui. Não tenho GPU, e este ambiente normalmente não consegue baixar lâminas do BRACS ou do TCGA. Eu precisaria do que o pipeline já gera:
>
> Por lâmina ou ROI: um CSV ou GeoJSON com a posição (x, y) e a classe de cada núcleo, e a probabilidade da classe se tiver.
> O MPP (µm/pixel) de cada lâmina e o rótulo BRACS (N, ..., DCIS, IC).
> Se já existir, a comparação CellViT × NuCLS para a classe inflamatória. Se não existir, os mesmos CSVs nas imagens do NuCLS, junto com as anotações, e eu calculo precisão e recall.

## Conteúdo

Modelo: CellViT-256-x40 (pesos oficiais, treinado no PanNuke). Tipos: `neoplasico`, `inflamatorio`, `conjuntivo`, `morto`, `epitelial` (`?` = tipo fora do mapa).

### `bracs_laminas.csv`

Uma linha por lâmina: rótulo BRACS da lâmina, conjunto oficial, MPP (lido do cabeçalho do `.svs`), número de tiles e de núcleos por classe.

### `bracs_nucleos/<lâmina>.csv.gz`

Um núcleo por linha.

| Coluna | Significado |
|---|---|
| `lamina` | BRACS_295, BRACS_748 ou BRACS_773 |
| `tile_x0`, `tile_y0` | canto do tile de 512 × 512 px (nível 0) |
| `classe_tile` | classe da RoI anotada no BRACS que contém o tile (`DCIS` ou `IC`) |
| `x`, `y` | centro do núcleo, em px do nível 0 da lâmina |
| `tipo`, `prob` | tipo previsto pelo CellViT e probabilidade do tipo |
| `no_tile` | 1 se o núcleo está dentro do tile de 512 px; 0 se está na margem (o CellViT roda numa janela de 1024 px centrada no tile) |

Os núcleos da margem podem aparecer repetidos quando as janelas de tiles vizinhos se sobrepõem. Para contar núcleos, usar só `no_tile = 1`.

Amostra: 250 tiles sorteados por classe (DCIS, IC) em cada lâmina, semente 0, entre os tiles que caem numa RoI anotada (sobreposição ≥ 0,5). A BRACS_748 tem 257 tiles de IC salvos (7 além do sorteio). Sem filtro por número de núcleos (no teste original, só entravam tiles com ≥ 20 núcleos neoplásicos). Origem: `validacao/dcis_ic_nucleos.py`.

### `nucls/`

NuCLS (Amgad et al., GigaScience 2022; CC0): 1.744 campos de mama do TCGA, conjunto corrigido por patologista. Origem: `validacao/nucls_cellvit.py`.

- `cellvit_por_fov.csv.gz`: núcleos do CellViT em cada campo, em µm a partir do canto do campo. Sem probabilidade. Imagens reamostradas de 0,2 para 0,25 µm/px antes do CellViT.
- `nucls_cellvit.json`: resultado original (núcleos anotados por classe, fração detectada e matriz de confusão anotado → CellViT).
- `cellvit_x_nucls_por_classe.csv`: precisão e recall por classe, calculados da matriz de confusão.

Pareamento: centro da caixa anotada com o núcleo do CellViT mais próximo a até 5 µm, um para um. Núcleos `AMBIGUOUS` ficam de fora. Correspondência de classes: sTIL + macrófago + neutrófilo + eosinófilo → `inflamatorio`; `tumor_any` → `neoplasico`; fibroblasto + endotélio → `conjuntivo`; epitélio ductal + mioepitélio → `epitelial`.

| Classe | Anotados | Detectados | Recall (entre pareados) | Precisão (entre pareados) |
|---|---|---|---|---|
| inflamatorio | 20.594 | 92,9% | 0,375 | 0,908 |

## Limites

- Apenas 3 lâminas do BRACS têm núcleos com posição salva, todas com rótulo de lâmina IC e do conjunto de treino. Não há lâminas N, PB, UDH, FEA, ADH ou DCIS (rótulo de lâmina) com núcleos exportados.
- No NuCLS, a precisão só conta os núcleos do CellViT pareados com um núcleo anotado. Detecções sem par não entram, porque as bordas dos campos podem ter núcleos sem anotação.
- O PanNuke também vem do TCGA. Pode haver lâminas em comum com o NuCLS, o que deixaria a comparação otimista.
- As anotações do NuCLS não foram copiadas; estão na fonte oficial (CC0).
