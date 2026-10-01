# Resultados — Pipeline Ideia 01

Estado em 30/09/2026. Um resumo de cada teste, com números, critério e se passou. Detalhes, tabelas completas e discussão ficam nos arquivos indicados em cada seção. Ordem cronológica dos testes: [linha_do_tempo.md](linha_do_tempo.md).

## Dados e métricas

**Dados**

| Conjunto | O que é | Uso |
|---|---|---|
| BRACS — 1ª leva | 8 lâminas, uma por classe (N, PB, UDH, FEA, ADH, DCIS, IC) + `BRACS_748` (IC) | ajuste e primeiros testes |
| BRACS — 2ª leva | 8 lâminas novas, pacientes diferentes da 1ª leva | teste fora da amostra |
| BRACS — DCIS+IC | `BRACS_773`, `BRACS_295`, com DCIS e IC na mesma lâmina | testes de DCIS vs. IC |
| BACH | 100 imagens *in situ* + 100 de invasivo, outra instituição (Porto) | generalização |
| NuCLS | 1.744 campos de mama do TCGA, núcleos classificados por patologista | validação do CellViT |

**Métricas**

- **Acerto por categoria / média:** % de tiles classificados certo em cada categoria real, e a média entre as categorias (benigno / atípico / maligno: acaso = 33%).
- **AUC:** probabilidade de um tile (ou imagem) de IC ter pontuação maior que um de DCIS. 0,5 = acaso; 1,0 = separação perfeita.
- **Lâmina de fora:** quando há treino, o método é treinado sem a lâmina avaliada.
- **Controle com rótulos embaralhados:** o mesmo treino com rótulos sorteados; mostra o que se obtém por sorte.
- **Critério fixado antes:** a partir de 25/09, a regra e o critério de cada teste são commitados antes de rodar.

## Estágio 1 — filtro de tecido

| Teste | Resultado | Situação |
|---|---|---|
| Recall contra os 98 RoIs da `BRACS_748` (11/09) | 98/98 RoIs cobertos, 96% de cobertura | resolvido, congelado |
| 16 lâminas (25/09) | cobertura dos RoIs 74–100% (exceção: 38% numa lâmina N, efeito da caixa retangular) | confirmado |

Detalhes: `Testes/Pipeline01/estagio1_filtro_tecido/resultados.md`, `Testes/Pipeline01/resultados_multilaminas.md`.

## Estágio 2 — escolha dos patches (roteador)

| Teste | Resultado | Passou? |
|---|---|---|
| Roteador por frases (suspeito − benigno), `BRACS_748` (13/09) | precisão 0,33–0,62 contra 0,18 do sorteio | sim, nessa lâmina |
| Mesmo roteador, 16 lâminas (25/09) | acima do sorteio em 8 das 16, sem padrão por classe | inconsistente |
| Roteador UNI2-h (1 − P(benigno)), só RoIs de lesão, 11 lâminas, k = 32 (26/09) | precisão média 0,20 contra 0,21 do atual e 0,11 do sorteio; vence o atual em 4 de 11 | **não** (critério: vencer em ≥ 8 de 11) |

Limite da métrica: os RoIs não marcam toda a lesão da lâmina — um patch de tumor fora do RoI conta como erro.

Detalhes: `Testes/Pipeline01/estagio2_roteador/`, `Testes/Pipeline01/estagio3_descritores/resultados.md` (seção "Estágio 2 com o UNI2-h").

## Estágio 3 — descrição dos patches

### Benigno / atípico / maligno

| Método | 8 lâminas novas (benigno / atípico / maligno / média) | Passou? |
|---|---|---|
| Zero-shot, banco original | — / — / — / 44,8% | referência |
| Zero-shot, troca da frase do lóbulo (25/09) | 57% / 41% / 61% / **53,2%** | sim — única troca que se sustentou fora da amostra |
| Zero-shot, + 2 trocas do experimento frase a frase | 52,7% | não — melhoravam só nas lâminas usadas pra escolhê-las |
| Zero-shot com ensemble de frases (26/09) | 60% / 27% / 71% / 52,7% | não |
| UNI2-h + regressão logística (26/09) | 56% / 17% / 93% / 55,2% | passou por 2 pontos, **dentro do ruído** (controle embaralhado: 42%) |
| QuiltNet + regressão logística (26/09) | 40,5% | não |

Detalhes: `Testes/Pipeline01/estagio3_descritores/resultados.md`, `Testes/Pipeline01/validacao/experimento_frases.md`.

### DCIS vs. IC no BRACS (AUC, lâmina avaliada fora do treino)

| Método | `BRACS_748` | `BRACS_773` | `BRACS_295` | Passou? |
|---|---|---|---|---|
| Zero-shot com frases (QuiltNet) | 0,50 | 0,58 | 0,50 | — (acaso) |
| Zero-shot com ensemble de frases | 0,55 | 0,57 | 0,54 | não |
| Média dos embeddings com os 8 vizinhos (só `BRACS_748`) | 55,5% bal. | — | — | ganho pequeno, só no IC |
| Vizinhos como contexto (tipo de tecido em volta) | abaixo do acaso | — | — | não |
| Regra "tumor cercado de tumor → IC" | — | 54,7% bal. | 55,1% bal. | passou no critério, efeito fraco |
| Núcleos (CellViT), sem treino | 0,72 | 0,84 | 0,66 | sim (AUC > 0,5 nas três) |
| QuiltNet + regressão logística | 0,83 | 0,95 | 0,84 | — |
| **UNI2-h + regressão logística** | **0,96** | **0,96** | **0,99** | sim (UNI2-h > QuiltNet nas três) |
| UNI2-h + núcleos juntos | 0,96 | 0,96 | 0,99 | não — não acrescenta |

Controle com rótulos embaralhados: AUC média 0,38–0,46.

### DCIS vs. IC em outra instituição (BACH), treino só no BRACS

| Método | AUC por imagem | Passou? |
|---|---|---|
| **UNI2-h + regressão logística** | **0,95** | sim (critério: ≥ 0,80) |
| Núcleos (CellViT), sem treino | 0,63 | — |
| QuiltNet + regressão logística | 0,57 | — (não generaliza) |

Detalhes: `Testes/Pipeline01/estagio3_descritores/resultados.md` (seções do plano UNI2-h), scripts em `Testes/Pipeline01/validacao/`.

### Validação do método 3 (núcleos) contra anotação de patologista — NuCLS

| Parte | Resultado | Passou? |
|---|---|---|
| Detecção dos núcleos | 82–93% dos núcleos anotados encontrados | — |
| Tipo "neoplásico" | sensibilidade 0,46, valor preditivo 0,86 (37% do tumor vira "epitelial") | — |
| Tipo "conjuntivo" | sensibilidade 0,80, valor preditivo 0,44 (muito linfócito e tumor chamados de conjuntivo) | — |
| Medida (fração de tumor com estroma a ≤ 20 µm), 610 campos | anotação 0,10 × CellViT 0,34; Spearman 0,28; viés +0,24 | **não** (critério: Spearman ≥ 0,7 e viés ≤ 0,10) |

Leitura: a medida tem sinal pra separar DCIS de IC, mas os valores não são confiáveis como número.

**Segunda versão — classificação de núcleos treinada no NuCLS** (detecção do CellViT; tipo por logística nos tokens do CellViT; 5 folds oficiais, treino e teste em hospitais diferentes):

| | CellViT original | Treinado no NuCLS | Passou? |
|---|---|---|---|
| Tumor: sensibilidade / valor preditivo | 0,46 / 0,86 | **0,83 / 0,88** | — |
| Conjuntivo: sensibilidade / valor preditivo | 0,80 / 0,44 | 0,72 / 0,52 | — |
| Medida: Spearman / viés | 0,28 / +0,24 | 0,35 / +0,16 | **não** |

O tipo do tumor ficou bom; o "conjuntivo" continua errando metade, e a medida (um único vizinho errado a ≤ 20 µm já conta como contato) amplifica esse erro.

## Anotações oficiais do BRACS

- `.qpdata` lidas com o QuPath e exportadas pra GeoJSON: 387 de 387 lâminas; totais por classe iguais aos do artigo.
- A maioria é retângulo, não contorno da lesão (nas lâminas usadas: DCIS 160 de 208, IC 127 de 128). O rótulo é da região marcada.

Detalhes: `Testes/Pipeline01/validacao/problemas_e_metrica.md`.

## Conclusões até aqui

1. O filtro de tecido funciona.
2. A escolha dos patches é inconsistente, com qualquer das pontuações testadas.
3. Comparar a imagem com frases (zero-shot) é o gargalo do estágio 3: fica no acaso no DCIS vs. IC, mesmo quando o embedding contém a informação.
4. Uma camada treinada em cima do UNI2-h separa DCIS de IC e generaliza pra outra instituição; no atípico, falta dado.
5. A medida dos núcleos separa DCIS de IC, mas os valores não são confiáveis: mesmo com a classificação de núcleos treinada no NuCLS (tumor 0,83 / 0,88), a medida não bate com a anotação (Spearman 0,35).
