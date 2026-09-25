# Resultados 01 — Filtros de segmentação de tecido (estágio 1)

**Lâmina testada:** `BRACS_748.svs` (dataset BRACS, caminho em `Caminhos/caminhos.md`)
**Script:** [filtro_tecido.py](filtro_tecido.py)
**Nível da pirâmide usado:** ~32× de downsample (3797×2768), conforme recomendado em `docs/pipelines.md`

## Filtros testados

| # | Filtro | % tecido detectado | Tempo |
|---|---|---|---|
| 01 | Otsu na saturação (receita documentada) | 36.12% | 246 ms |
| 02 | Otsu na saturação + limpeza morfológica | 36.72% | 242 ms |
| 03 | Otsu-S combinado com V (tentativa de recuperar tecido pálido) | 37.30% | 491 ms |
| 04 | Yen na saturação | 40.98% | 292 ms |
| 05 | Triangle na saturação | 40.98% | 316 ms |
| 06 | Distância euclidiana ao branco (RGB), baseline ingênuo | 41.54% | 680 ms |

Ver [resultados/BRACS_748/estagio1/comparacao_grid.png](../resultados/BRACS_748/estagio1/comparacao_grid.png) para a grade visual e `resultados/BRACS_748/estagio1/estatisticas.json` para os números brutos.

## Achado

Todos os 6 filtros erram do mesmo jeito: a região rosa-clara à esquerda da lâmina (tecido real) fica majoritariamente fora da máscara em todos eles, enquanto a região roxo-escura à direita é capturada de forma limpa.

Medição direta nos canais HSV (regiões de amostra, thumbnail no nível 32×):

| Região | S médio | S desvio | V médio | V desvio |
|---|---|---|---|---|
| Tecido claro (esquerda, mal capturado) | 36.5 | 38.0 | 222.5 | 22.4 |
| Tecido escuro (direita, bem capturado) | 56.2 | 38.3 | 194.2 | 36.4 |
| Fundo branco | 0.6 | 0.6 | 239.8 | 2.5 |

- Limiar de Otsu (S) calculado para a lâmina inteira: **39.0**
- O tecido claro tem S médio 36.5 — cai bem em cima do limiar, por isso boa parte dele é descartada.
- A tentativa de recuperação via canal V (filtro 03: também aceitar pixels com V abaixo de um limiar, supondo que tecido pálido é mais escuro que o fundo) não resolveu: o limiar de V calculado foi 212, e o tecido claro tem V médio 222 — mais claro que o limiar de resgate, não mais escuro. Esse tecido não é "escuro e pouco saturado" (perfil de tecido adiposo); é "claro e pouco saturado", um caso que a heurística de V não cobre.

Isso reproduz na prática a armadilha já registrada em `docs/pipelines.md` (estágio 1): Otsu global falha em lâmina com tecido tênue.

> **Correção de enquadramento:** a análise acima mede "% de tecido detectado", uma métrica sem ground-truth — não existe um "% certo" pra comparar os 6 filtros entre si, e "perder tecido claro" não é necessariamente um erro. O teste que realmente importa é abaixo.

## Teste de recall contra RoIs reais (verdade de campo)

BRACS_748 tem 98 RoIs anotados por patologista. O `.qpdata` original (projeto QuPath) não foi encontrado no disco — o que existe localmente são os 98 recortes já extraídos pelo dataset oficial **BRACS_RoI** (`Dados Gerais/BRACSDataset/.../BRACS_RoI/latest_version/{train,val}/<classe>/BRACS_748_<classe>_<n>.png`), cobrindo as classes epiteliais do BRACS (ADH, DCIS, IC nesta lâmina).

**Método** ([recall_roi.py](recall_roi.py)): cada um dos 98 recortes foi localizado na lâmina por template matching contra o nível ~16× da pirâmide (`cv2.matchTemplate`, assumindo o recorte em resolução full-res), convertido para as coordenadas do nível ~32× (o mesmo da máscara), e comparado à máscara de tecido: recall = fração da área do RoI coberta por "tecido".

**Resultado:**

| Filtro | 98/98 localizados (correlação ≥ 0.5) | Cobertura média | RoIs com ≥50% coberto | RoIs com ≥90% coberto |
|---|---|---|---|---|
| 01 Otsu-S | 98/98 | 0.95 | 100% | 84% |
| 02 Otsu-S + morfologia | 98/98 | 0.96 | 100% | 87% |

Todos os 98 recortes foram localizados com alta confiança (correlação média bem acima de 0.5, muitos ≥0.9). Ver [resultados/BRACS_748/estagio1/roi_overlay.png](../resultados/BRACS_748/estagio1/roi_overlay.png) (boxes amarelos) e detalhe por RoI em `resultados/BRACS_748/estagio1/recall_roi.csv`.

**Confirmação visual:** no overlay, os 98 boxes caem exclusivamente na região roxo-densa — nenhum RoI anotado cai na região clara à esquerda. Um zoom em alta resolução dessa região clara ([resultados/BRACS_748/estagio1/zoom_regiao_clara_page3.png](../resultados/BRACS_748/estagio1/zoom_regiao_clara_page3.png)) mostra feixes de colágeno ondulados, tecido conjuntivo fibroso, sem estruturas glandulares/ductais e sem núcleos aglomerados — não é o tecido celular que o roteador do estágio 2 precisa (não é exatamente gordura clássica com vacúolos redondos, mas é claramente estroma não-epitelial).

## Conclusão

Recall alto (100% ≥50%, ~85% ≥90%) confirma: **"perder a região clara" é comportamento correto, não bug.** Estágio 1 está congelado — usar Otsu-S + morfologia (mais rápido entre os que empatam, 242ms). Próximo passo é o estágio 2 (roteador top-k), onde mora a curva custo×fidelidade de verdade.

## Em aberto

- Repetir o recall em 2–3 lâminas de classes diferentes, pra ver se o padrão de recall alto se mantém fora da BRACS_748 (único item que ainda vale rodar — não investir mais em variante de Otsu).
  - **Bloqueado por dado:** só há uma `.svs` baixada localmente (`BRACS_748`). O dataset `BRACS_RoI` já tem recortes de outras 317 lâminas, mas sem a WSI original não dá pra gerar máscara de tecido nem localizar os RoIs nela — falta baixar mais `.svs` do BRACS.
  - Os dois scripts já aceitam `--svs /caminho/lamina.svs` (saída organizada em `resultados/<nome_da_lamina>/`), então assim que outra `.svs` estiver disponível o teste é só rodar `filtro_tecido.py --svs ... && recall_roi.py --svs ...`.
