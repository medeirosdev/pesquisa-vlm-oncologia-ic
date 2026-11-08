# Resultados — Pipeline Ideia 01

Estado em 07/11/2026. Um resumo de cada teste, com números, critério e se passou. Detalhes, tabelas completas e discussão ficam nos arquivos indicados em cada seção. Ordem cronológica dos testes: [linha_do_tempo.md](linha_do_tempo.md).

## Dados e métricas

**Dados**

| Conjunto | O que é | Uso |
|---|---|---|
| BRACS — 1ª leva | 8 lâminas, uma por classe (N, PB, UDH, FEA, ADH, DCIS, IC) + `BRACS_748` (IC) | ajuste e primeiros testes |
| BRACS — 2ª leva | 8 lâminas novas, pacientes diferentes da 1ª leva | teste fora da amostra |
| BRACS — DCIS+IC | `BRACS_773`, `BRACS_295`, com DCIS e IC na mesma lâmina | testes de DCIS vs. IC |
| BACH | 100 imagens *in situ* + 100 de invasivo, outra instituição (Porto) | generalização |
| NuCLS | 1.744 campos de mama do TCGA, núcleos classificados por patologista | validação do CellViT |

> **Correção de 07/11/2026 — agrupamento das classes.** Até 06/11, o projeto colocava o UDH em atípico. No BRACS, benigno = N, PB, UDH; atípico = FEA, ADH; maligno = DCIS, IC (as contagens do artigo só fecham assim, e o FTP oficial guarda o UDH na pasta de benignos). Os resultados por patch e por lâmina anteriores a essa data usam o agrupamento antigo e estão marcados. As tabelas de pré-laudo foram repontuadas com o rótulo oficial; os testes da decisão da lâmina foram refeitos (seção "Rótulo oficial do BRACS").

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

**Segunda rodada (13/10) — métrica sem RoIs:** fração dos 32 patches escolhidos com tumor (≥ 20 núcleos neoplásicos, CellViT + classificação treinada no NuCLS), 7 lâminas malignas.

| Lâmina | Frases (atual) | UNI2-h "não benigno" | UNI2-h por categoria (novo) | Sorteio |
|---|---|---|---|---|
| `BRACS_1003677` | 0,88 | 0,66 | 0,75 | 0,83 |
| `BRACS_1489` | 0,69 | 0,91 | 0,56 | 0,51 |
| `BRACS_748` | 0,97 | 0,88 | 0,38 | 0,24 |
| `BRACS_1512` | 0,78 | 0,91 | 0,56 | 0,49 |
| `BRACS_297` | 1,00 | 0,91 | 0,59 | 0,37 |
| `BRACS_773` | 0,97 | 0,94 | 0,41 | 0,62 |
| `BRACS_295` | 0,75 | 1,00 | 0,50 | 0,59 |
| **Média** | **0,86** | **0,88** | **0,54** | **0,52** |

- Roteador novo (UNI2-h por categoria): **não passou** (0,54, igual ao sorteio) — por desenho ele reserva patches pra benigno e atípico, e a métrica de tumor não é adequada pra ele.
- Os roteadores antigos acham muito tumor (0,86 e 0,88 contra 0,52 do sorteio): a "falha" do estágio 2 vinha em boa parte da métrica por RoI.

Detalhes: `Testes/Pipeline01/estagio2_roteador/`, `Testes/Pipeline01/estagio3_descritores/resultados.md` (seções "Estágio 2 com o UNI2-h" e "Estágio 2, segunda rodada").

## Estágio 3 — descrição dos patches

### Benigno / atípico / maligno

*Agrupamento antigo (UDH em atípico); ver a correção de 07/11.*

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

### Descritor hierárquico (categoria → DCIS/IC → texto), 4 classes finais, 18 lâminas, lâmina de fora

*Agrupamento antigo (UDH em atípico); ver a correção de 07/11.*

| Método | Benigno | Atípico | DCIS | IC | Média | Passou? |
|---|---|---|---|---|---|---|
| Hierarquia com frases (zero-shot) | 57% | 46% | 16% | 50% | 42,3% | referência |
| **Hierarquia com UNI2-h** | 58% | 14% | **78%** | **74%** | **55,8%** | sim (critério: média maior) |

Acaso = 25%. O atípico continua sendo o ponto fraco. Saída em texto: `[x0,y0] (maligno 0.93) invasive carcinoma 0.88` — código em `Testes/Pipeline01/estagio3_descritores/descritor_uni.py`.

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

**Terceira rodada — medidas mais robustas** (mesmos tipos, 844 campos; critério: Spearman ≥ 0,7 e viés pequeno):

| Medida | Spearman | Viés | Passou? |
|---|---|---|---|
| ≥ 1 vizinho de estroma a ≤ 20 µm (atual) | 0,35 | +0,16 | não |
| Distância mediana ao estroma | 0,37 | −6,8 µm | não |
| ≥ 3 vizinhos de estroma a ≤ 20 µm | 0,27 | +0,06 | não |

Decisão: os núcleos ficam como sinal, sem número no texto. Limite: os campos do NuCLS (~71 µm) são pequenos pra uma medida de vizinhança.

## Estágio 5 — pré-laudo por modelo de linguagem local (exploratório)

Pipeline completa: roteador → descritor hierárquico UNI2-h → agregação → modelo local (Ollama), 3 lâminas, sem critério fixado.

| Lâmina (rótulo real) | MedGemma 4B | Gemma 3 4B |
|---|---|---|
| `BRACS_1489` (DCIS) | DCIS ✓ | DCIS ✓ |
| `BRACS_748` (IC) | DCIS ✗ | DCIS, com alerta pro invasivo ✗ |
| `BRACS_1370` (PB) | DCIS e invasivo, confiança alta ✗ | aponta inconsistência, sem concluir câncer |

O modelo segue a maioria dos patches (na lâmina de IC, o componente invasivo é minoria) e repete os falsos positivos do estágio 3. Gemma 3 prioriza melhor e é mais cauteloso que MedGemma.

### Avaliação sistemática do pré-laudo e regra do componente invasivo (Gemma 3 4B)

Classificação final do pré-laudo (benigno / atípico / DCIS / IC) contra o rótulo da lâmina no BRACS, repontuada com o rótulo oficial (entre parênteses, o valor com o agrupamento antigo).

| | Sem regra (v1) | Com regra (v2) | Passou? |
|---|---|---|---|
| 18 lâminas | 6/18 (33%): benigno 1/7, atípico 0/4, DCIS 2/2, IC 3/5 | — | descritivo |
| 15 lâminas fora das usadas pra criar a regra | 5/15 (33%), IC 3/4 | **9/15 (60%), IC 4/4** (antes: 10/15) | **sim** (critério: mais IC e acurácia não menor) |

Regra (estágio 4): se ≥ 2 patches com carcinoma invasivo e P ≥ 0,90, o prompt diz "componente invasivo presente" e que ele define o diagnóstico; senão, "não detectado". Sem a regra, o modelo chama de maligno 17 de 18 lâminas; com ela, 10 de 15. Benignas: 1 → 4 de 6. O atípico continua errado (0/4).

**Teste externo** — 57 lâminas do conjunto de teste oficial do BRACS (31 pacientes nunca usados), pipeline congelada:

| | Sem regra | Com regra | Passou? |
|---|---|---|---|
| 57 lâminas | 14/57 (25%), IC 5/12 (antes: 13/57) | **17/57 (30%), IC 7/12** (antes: 16/57) | sim, por pouco |
| Benigno / atípico | 1/20 · 1/17 | 1/20 · 1/17 | — |
| Respostas malignas | 55 de 57 | 55 de 57 | — |

A regra se confirma no IC, mas a pipeline chama quase tudo de maligno: o acerto total fica perto do acaso de 4 classes (25%). O ganho nas benignas visto no desenvolvimento não se repetiu. Conferência de 20 pré-laudos: a extração erra em ~10%, e em metade o texto não se decide por uma classe (a extração escolhe DCIS); várias lâminas benignas têm evidência com predominância de patches benignos. Detalhes: `Testes/Pipeline01/estagio5_sintese/resultados.md`.

## Classificação da lâmina inteira e descritor treinado nas RoIs (22/10)

*Agrupamento antigo (UDH em atípico); ver a correção de 07/11.*

Script: `Testes/Pipeline01/validacao/lamina_inteira.py`, fixado antes (commit `c3bfa00`). Descritor "rois": hierarquia UNI2-h treinada com até 16 patches por RoI de treino do BRACS (23.669 patches de 3.402 RoIs; 1 recorte ilegível pulado). Classe da lâmina por regra de proporção sobre 2.000 patches sorteados (f_mal ≥ t_m → IC se f_ic ≥ t_ic, senão DCIS; senão f_at ≥ t_a → atípico; senão benigno), limiares escolhidos nas 18 lâminas de desenvolvimento. Critério: E2 > E0 e E2 > E1 em acurácia balanceada nas 57 lâminas do teste externo.

| | Benigno (13) | Atípico (24) | DCIS (8) | IC (12) | Acertos | Acurácia balanceada | Passou? |
|---|---|---|---|---|---|---|---|
| E0 — pipeline atual (modelo de linguagem + regra) | 0 | 1 | 8 | 7 | 16/57 | 0,41 | referência |
| E1 — regra de proporção + descritor atual | 11 | 0 | 0 | 7 | 18/57 | 0,36 | — |
| E2 — regra de proporção + descritor das RoIs | 5 | 10 | 0 | 7 | 22/57 | 0,35 | **não** |

- **Repontuado com o rótulo oficial (07/11):** E1 25/57 (acurácia balanceada 0,37; benigno 18/20, atípico 0/17), E2 19/57 (0,31; benigno 7/20, atípico 5/17). Parte do ganho no atípico vinha das lâminas UDH, que são benignas.
- **O descritor das RoIs melhora o atípico:** 1 → 10 de 24 lâminas no agrupamento antigo (nos patches das RoIs de validação: benigno 77%, atípico 41%, maligno 89%). E2 tem o maior número de lâminas certas.
- **Os limiares se ajustaram demais às 18 lâminas de desenvolvimento** (acurácia balanceada 0,87 lá, 0,35 no teste). O limiar de IC ficou em 5% (`t_ic` = 0,05 em E2, 0,10 em E1): E1 e E2 nunca dizem DCIS (0 de 8). Só havia 2 lâminas de DCIS no desenvolvimento.
- **Cada versão acerta classes diferentes:** E0 os malignos, E1 as benignas, E2 o atípico.
- **Próximo passo:** calibrar ou aprender a decisão da lâmina com mais lâminas rotuladas — as 65 de validação oficiais do BRACS (baixadas por partes, guardando só os embeddings), sem tocar nas de teste.

## Decisão da lâmina inteira por classificador (26/10 a 06/11)

*Agrupamento antigo (UDH em atípico). Refeito com o rótulo oficial em 07/11: ver a seção seguinte.*

Todos os testes usam as 57 lâminas do teste externo, com critério fixado em commit antes de rodar (`6b0ad76`, `21cb292`). Treino em 79 lâminas (61 de validação oficial + 18 de desenvolvimento). Atributos da lâmina: 12 números calculados a partir do descritor sobre até 2.000 patches (frações por classe, médias e percentis altos das probabilidades). Métrica: acurácia balanceada nas 4 classes (acaso = 0,25).

| Forma de decidir | Benigno (13) | Atípico (24) | DCIS (8) | IC (12) | Acertos | Acurácia balanceada | IC 95% | Passou? |
|---|---|---|---|---|---|---|---|---|
| E0 — modelo de linguagem decide (referência) | 0 | 1 | 8 | 7 | 16/57 | 0,406 | — | — |
| Classificador 4 classes, descritor das RoIs | 2 | 5 | 4 | 10 | 21/57 | 0,424 | 0,31–0,53 | sim (> 0,406), dentro do ruído |
| Hierárquico (benigno → atípico → DCIS/IC), descritor das RoIs | 7 | 3 | 2 | 10 | 22/57 | 0,437 | — | sim (> 0,424), por pouco |
| **Classificador 4 classes, descritor com negativos benignos** | 6 | 9 | 1 | 11 | **27/57** | **0,470** | 0,36–0,59 | **sim** (> 0,424) |
| Hierárquico, descritor com negativos (exploratório, sem critério) | 6 | 11 | 1 | 11 | 29/57 | 0,490 | — | — |

- **Triagem binária (benigno × precisa de atenção): não passou.** Critério: sensibilidade ≥ 0,90 e especificidade ≥ 0,40. Resultado: sensibilidade 0,95 (42/44), especificidade 0 (0/13), AUC 0,52. Com o descritor com negativos, sem critério (exploratório): sensibilidade 0,98, especificidade 0,15 (2/13), AUC 0,65. Lâminas atípicas são quase todas tecido benigno com lesão pequena; os atributos por lâmina diluem essa lesão.
- **Abstenção ("não sei"): passou, ganho pequeno.** Com limiar escolhido no treino, decide em 56% das lâminas (32/57), com acurácia balanceada 0,478 contra 0,424 em todas. A curva de acerto por cobertura oscila (0,41 a 0,50), sem subir de forma regular; com 57 lâminas, a diferença é pequena demais para concluir.
- **Lâminas benignas como negativos: passou.** Até 500 patches de cada uma das 26 lâminas benignas do treino entram como exemplos benignos no descritor (sem usar os do mesmo paciente ao descrever uma lâmina). A fração de patches falsos DCIS + IC nas lâminas benignas do teste caiu de 23% para 7%, sem perda nos patches malignos das RoIs de validação (89%). Custo: o DCIS cai para 1 de 8 lâminas; a maioria vai para benigno ou atípico.
- **Ressalva:** as 57 lâminas já foram usadas em vários testes. Nada foi ajustado nelas, mas repetir comparações no mesmo conjunto aumenta a chance de um ganho por acaso, e os intervalos se sobrepõem. A confirmação deve usar as 30 lâminas de teste oficiais ainda não usadas.

**Comparação com os números publicados** (lâmina inteira, 3 classes: benigno, atípico, maligno). Valores do projeto refeitos com o rótulo oficial em 07/11 (`validacao/rotulo_oficial.py`); a versão de 06/11 (`comparacao_literatura.py`) usava o agrupamento antigo e dava 0,496 e 0,523.

| Método | Treino | Teste | Acurácia balanceada (3 classes) |
|---|---|---|---|
| UNI + ABMIL (Chen et al., Nature Medicine 2024, Extended Data Table 19) | 395 lâminas | 87 lâminas | 0,687 (0,617–0,760) |
| ResNet-50 ImageNet + ABMIL (mesma tabela) | 395 lâminas | 87 lâminas | 0,552 (0,490–0,607) |
| Hierárquico, descritor com negativos (sem critério) | 79 lâminas | 57 das 87 | 0,560 |
| Classificador 4 classes, descritor com negativos | 79 lâminas | 57 das 87 | 0,518 |
| E0 — modelo de linguagem decide | — | 57 das 87 | 0,370 |

A comparação é indicativa, não direta: os conjuntos de teste e de treino diferem, e o UNI2-h usado aqui é outro modelo. Nas 7 classes, o mesmo artigo reporta 0,468 (0,393–0,550); a pipeline não prevê as 7. O UNI + ABMIL usa o mesmo agrupamento oficial. A distância até 0,687 sugere o que o MIL com as 379 lâminas de treino pode acrescentar. No artigo do ACMIL (arXiv 2311.07125, Tabela 1), com outra métrica (F1 macro em 3 classes, características SSL), ABMIL chega a 0,680 e ACMIL a 0,722.

## Rótulo oficial do BRACS: correção e reteste (07/11)

Script: `Testes/Pipeline01/validacao/rotulo_oficial.py`, fixado antes (commit `095320c`). Descritor, negativos (agora 34 lâminas: N, PB e UDH) e classificador da lâmina refeitos com o rótulo oficial; treino nas mesmas 79 lâminas, teste nas mesmas 57 (benigno 20, atípico 17, DCIS 8, IC 12).

| Forma de decidir | Benigno (20) | Atípico (17) | DCIS (8) | IC (12) | Acertos | Acurácia balanceada (4 classes) | 3 classes | Passou? |
|---|---|---|---|---|---|---|---|---|
| E0 — modelo de linguagem decide (repontuado) | 1 | 1 | 8 | 7 | 17/57 | 0,423 | 0,370 | referência |
| Classificador + negativos de 06/11 (repontuado) | 9 | 8 | 1 | 11 | 29/57 | 0,491 | 0,524 | referência do C1 |
| Classificador, descritor das RoIs | 7 | 3 | 3 | 11 | 24/57 | 0,455 | 0,425 | — |
| **Classificador + negativos (refeito)** | 10 | 6 | 2 | 11 | 29/57 | **0,505** (IC 95% 0,40–0,63) | 0,518 | **C1: sim, por pouco** |
| Hierárquico + negativos (refeito, sem critério) | 10 | 9 | 1 | 11 | 31/57 | 0,518 | 0,560 | — |

| Versão binária (descritor com negativos) | AUC | Limiar do treino (sens. ≥ 0,90) | Limiar 0,5 | Passou? |
|---|---|---|---|---|
| Maligno × resto (C2) | 0,83 | sens. 20/20, espec. 0/37 | sens. 13/20, espec. 30/37 (43/57) | **não** |
| Suspeito (FEA, ADH, DCIS, IC) × benigno (C3) | 0,66 | sens. 35/37, espec. 5/20 | sens. 26/37, espec. 10/20 (36/57) | **não** |

- **A correção não muda o quadro geral:** tirar a decisão do modelo de linguagem e usar negativos benignos continua sendo a melhor combinação (17 → 29 de 57 lâminas; 0,42 → 0,51). Os patches falsos DCIS + IC nas 20 benignas do teste caem de 21% para 7%.
- **Maligno × resto separa bem (AUC 0,83), mas o limiar não transfere:** o limiar que garante 90% de sensibilidade no treino zera a especificidade no teste. Dizer sempre "não maligno" já acerta 37/57.
- **Benigno × atípico continua o ponto fraco** (AUC 0,66). Na validação cruzada do treino, a AUC é 0,88; a queda para 0,66 no teste mostra que a estimativa no treino é otimista.
- **Por patch, nas RoIs de validação** (rótulo oficial): benigno 84% → 88% com negativos; atípico 35% → 37%; maligno 90% → 87%.

## Modelo de linguagem só redige, com checagem automática do texto (07/11)

Script: `Testes/Pipeline01/validacao/prelaudo_campos.py`, fixado antes (commit `21cb292`). A classe vem do classificador da lâmina (versão de 06/11, agrupamento antigo); o Gemma 3 4B recebe campos fixos (classe, probabilidades, confiança, proporções, 3 regiões) e só redige. A checagem automática compara cada número e coordenada do texto com a evidência que o modelo recebeu, e é aplicada também aos 57 pré-laudos antigos (modelo decidindo). Critério: classe do texto igual à sugerida em ≥ 90% e fração de números sem sustentação não maior que a dos antigos.

| | Pré-laudos novos (só redige) | Pré-laudos antigos (modelo decide) |
|---|---|---|
| Classe do texto igual à sugerida | **57/57** | — |
| Números checados / sem sustentação | 791 / **0** | 523 / 11 (2,1%, em 4 textos) |
| Coordenadas citadas / inventadas | 175 / **0** | 178 / 2 |
| Tempo médio por pré-laudo | 68 s | — |

**Passou.** O texto fica fiel aos campos: nos casos de confiança baixa, diz que a confiança é baixa e que as proporções são mistas. Limitações: a checagem não detecta achados morfológicos inventados (na leitura de 3 textos, não houve nenhum); e o texto quase só reorganiza os campos, acrescentando pouca informação. A classe final é a do classificador: com o rótulo oficial, 19/57 (acurácia balanceada 0,425) para a versão de 06/11 usada aqui; a versão corrigida com negativos chega a 29/57.

## Resposta em conjunto: benigno, atípico, "benigno ou atípico", maligno (07/11)

Script: `Testes/Pipeline01/validacao/resposta_em_conjunto.py`, fixado antes (commit `6392791`). Quando o classificador da lâmina (descritor com negativos, rótulo oficial) não separa benigno de atípico, responde "benigno ou atípico". Medem-se juntos o **acerto do conjunto** (a classe real está na resposta?) e as **respostas exatas** (uma classe só). A margem de recuo `d` foi escolhida no treino como a menor com acerto do conjunto ≥ 0,80; nenhuma chegou lá (máximo 0,797), e a regra usou a maior da grade, 0,45. Critério: nas 57, acerto do conjunto ≥ 0,75 e respostas exatas ≥ 0,50.

| Nas 57 lâminas | Acerto do conjunto | Respostas exatas |
|---|---|---|
| Sem recuo (3 classes) | 0,53 | 1,00 |
| **Com recuo (d = 0,45)** | **0,70** (IC 95% 0,59–0,81) | 0,44 |
| Só benignas e atípicas, sem recuo | 0,43 | 1,00 |
| Só benignas e atípicas, com recuo | 0,70 | 0,30 |

| Classe real | benigno | atípico | benigno ou atípico | maligno |
|---|---|---|---|---|
| Benigno (20) | 0 | 2 | 13 | 5 |
| Atípico (17) | 0 | 0 | 13 | 4 |
| Maligno (20) | — | — | 6 | 14 |

**Não passou** (0,70 e 0,44). Com o recuo máximo, a resposta vira na prática "maligno × não maligno": 26 das 37 lâminas benignas e atípicas recebem "benigno ou atípico", o que é verdadeiro mas pouco específico. Os erros que importam continuam: 6 de 20 malignas caem em "benigno ou atípico", e 9 benignas ou atípicas são chamadas de malignas. No treino, a curva mostra a troca: d = 0,20 dava 0,77 de acerto do conjunto com 80% de respostas exatas; o alvo de 0,80 era alto demais para o que o classificador separa hoje. A métrica fica pronta para os próximos testes (concentração espacial, MIL, as 30 lâminas de teste não usadas).

## Concentração espacial dos patches suspeitos (08/11)

Script: `Testes/Pipeline01/validacao/concentracao_espacial.py`, fixado antes (commit `3a62bd4`). Hipótese vinda de dois mapas de calor: numa lesão, os patches suspeitos formam um foco; numa lâmina benigna, os falsos positivos ficam espalhados. Quatro atributos novos por lâmina, com os 8 vizinhos mais próximos de cada patch na amostra: enriquecimento dos suspeitos, dos malignos e dos atípicos (1 = espalhados ao acaso) e fração de suspeitos em foco. Descritor com negativos e rótulo oficial; os 12 atributos antigos conferem exatamente com `rotulo_oficial.py`. Critério: nas 37 lâminas benignas e atípicas do teste, AUC benigno × atípico com os atributos novos ≥ AUC sem eles + 0,05, e ≥ 0,70.

| | Sem os espaciais (12 atributos) | Com os espaciais (16) |
|---|---|---|
| AUC benigno × atípico (37 lâminas) | 0,582 | 0,609 (diferença: IC 95% −0,04 a +0,10) |
| AUC suspeito × benigno (57) | 0,655 | 0,674 |
| Classificador, 4 classes (57) | 29/57, 0,505 | 30/57, 0,524 |
| Hierárquico, 4 classes (57) | 31/57, 0,518 | 31/57, 0,518 |

**Não passou.** A hipótese não se sustentou: nas lâminas benignas do teste, os patches suspeitos também ficam agrupados, cerca de 4 vezes acima do acaso, quase como nas atípicas (4,5). Os falsos positivos não são espalhados; vêm em regiões inteiras de tecido que o descritor confunde. Os dois mapas que sugeriram a ideia não representavam o conjunto.

| Média no teste | Enriquecimento dos suspeitos | dos malignos | dos atípicos | Suspeitos em foco |
|---|---|---|---|---|
| Benigno | 3,96 | 2,90 | 5,09 | 0,04 |
| Atípico | 4,51 | 3,76 | 6,28 | 0,04 |
| DCIS | 4,04 | 6,14 | 7,53 | 0,07 |
| IC | 1,49 | 1,67 | 2,53 | 0,51 |

No IC, o enriquecimento é baixo porque os suspeitos ocupam metade da lâmina: com tanta área suspeita, a razão contra o acaso fica perto de 1. Sem os atributos espaciais, a AUC benigno × atípico só nessas 37 lâminas é 0,58, perto do acaso: o descritor por patch, como está, não separa as duas classes no nível da lâmina.

## Anotações oficiais do BRACS

- `.qpdata` lidas com o QuPath e exportadas pra GeoJSON: 387 de 387 lâminas; totais por classe iguais aos do artigo.
- A maioria é retângulo, não contorno da lesão (nas lâminas usadas: DCIS 160 de 208, IC 127 de 128). O rótulo é da região marcada.

Detalhes: `Testes/Pipeline01/validacao/problemas_e_metrica.md`.

## Conclusões até aqui

1. O filtro de tecido funciona.
2. A escolha dos patches parecia inconsistente pela métrica de RoIs, mas, medindo pelos núcleos, os roteadores acham tumor em 86–88% dos patches escolhidos nas lâminas malignas (sorteio: 52%).
3. Comparar a imagem com frases (zero-shot) é o gargalo do estágio 3: fica no acaso no DCIS vs. IC, mesmo quando o embedding contém a informação.
4. Uma camada treinada em cima do UNI2-h separa DCIS de IC e generaliza pra outra instituição; no atípico, falta dado.
5. A medida dos núcleos separa DCIS de IC, mas os valores não são confiáveis: mesmo com a classificação de núcleos treinada no NuCLS (tumor 0,83 / 0,88), a medida não bate com a anotação (Spearman 0,35).
6. A pipeline roda de ponta a ponta até o pré-laudo, mas em lâminas novas (57 do teste oficial) chama 55 de 57 de malignas: acerta DCIS e IC (com a regra, 8/8 e 7/12) e erra quase todas as benignas e atípicas, ficando em 17 de 57 (rótulo oficial). A regra do componente invasivo ajuda no IC; o problema principal está nos estágios 2 e 3, que mandam evidência maligna de lâminas benignas e atípicas.
7. Tirar a decisão do modelo de linguagem e treinar o descritor com lâminas benignas como negativos leva o acerto de 17 para 29 de 57 lâminas (acurácia balanceada 0,42 → 0,51, rótulo oficial), e os patches falsos malignos nas lâminas benignas caem de 21% para 7%. Ainda está abaixo do publicado com MIL (0,52–0,56 contra 0,69 em 3 classes, comparação indicativa). Separar benigno de atípico no nível da lâmina continua sendo o ponto mais difícil.
