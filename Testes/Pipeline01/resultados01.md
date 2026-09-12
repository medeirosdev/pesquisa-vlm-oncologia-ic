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

Ver [outputs/comparacao_grid.png](outputs/comparacao_grid.png) para a grade visual e `outputs/estatisticas.json` para os números brutos.

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

Isso reproduz na prática a armadilha já registrada em `docs/pipelines.md` (estágio 1): Otsu global falha em lâmina com tecido tênue, e um limiar fixo calibrado ou um Otsu local por região tendem a ser mais confiáveis que o Otsu adaptativo global nesse caso.

## Em aberto

- Testar Otsu local (por blocos/regiões) em vez de global.
- Testar um limiar de S fixo mais baixo (ex. 15–20) calibrado manualmente, e conferir se não introduz ruído de fundo.
- Repetir o teste em outras lâminas do BRACS para ver se esse padrão (tecido claro perto do limiar) se repete ou é específico desta amostra.
