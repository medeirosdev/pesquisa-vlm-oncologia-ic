# Resultados — Pipeline Ideia 01

Estado em 14/11/2026. Um resumo de cada teste, com números, critério e se passou. Detalhes, tabelas completas e discussão ficam nos arquivos indicados em cada seção. Ordem cronológica dos testes: [linha_do_tempo.md](linha_do_tempo.md).

## Dados e métricas

**Dados**

| Conjunto | O que é | Uso |
|---|---|---|
| BRACS — 1ª leva | 8 lâminas, uma por classe (N, PB, UDH, FEA, ADH, DCIS, IC) + `BRACS_748` (IC) | ajuste e primeiros testes |
| BRACS — 2ª leva | 8 lâminas novas, pacientes diferentes da 1ª leva | teste fora da amostra |
| BRACS — DCIS+IC | `BRACS_773`, `BRACS_295`, com DCIS e IC na mesma lâmina | testes de DCIS vs. IC |
| BACH | 100 imagens *in situ* + 100 de invasivo, outra instituição (Porto) | generalização |
| NuCLS | 1.744 campos de mama do TCGA, núcleos classificados por patologista | validação do CellViT |
| TCGA-LUAD e TCGA-LUSC | lâminas de diagnóstico de pulmão (adenocarcinoma e carcinoma escamoso), NCI GDC, acesso aberto; 200 sorteadas | outro órgão: MIL e pré-laudo |
| LungHist700 | 691 imagens de microscópio de pulmão (normal, adenocarcinoma, escamoso), 45 pacientes; Diosdado et al., Sci Data 2024, CC BY 4.0 | descritor por patch do pulmão |
| PANDA | biópsias de próstata com grau ISUP 0–5 e máscara de rótulos, Radboud e Karolinska; Bulten et al., Nat Med 2022, CC BY-NC-SA 4.0 (Kaggle); 900 sorteadas | graduação: MIL, descritor, atenção na máscara, pré-laudo |

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

Detalhes: `Testes/Pipeline01/estagio1_filtro_tecido/resultados.md`, `Testes/Pipeline01/notas/resultados_multilaminas.md`.

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

Detalhes: `Testes/Pipeline01/estagio3_descritores/resultados.md`, `Testes/Pipeline01/descritor/bracs/experimento_frases.md`.

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

Detalhes: `Testes/Pipeline01/estagio3_descritores/resultados.md` (seções do plano UNI2-h), scripts em `Testes/Pipeline01/descritor/bracs/` e `Testes/Pipeline01/dcis_ic/`.

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

Script: `Testes/Pipeline01/lamina/bracs/lamina_inteira.py`, fixado antes (commit `c3bfa00`). Descritor "rois": hierarquia UNI2-h treinada com até 16 patches por RoI de treino do BRACS (23.669 patches de 3.402 RoIs; 1 recorte ilegível pulado). Classe da lâmina por regra de proporção sobre 2.000 patches sorteados (f_mal ≥ t_m → IC se f_ic ≥ t_ic, senão DCIS; senão f_at ≥ t_a → atípico; senão benigno), limiares escolhidos nas 18 lâminas de desenvolvimento. Critério: E2 > E0 e E2 > E1 em acurácia balanceada nas 57 lâminas do teste externo.

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

**Comparação com os números publicados** (lâmina inteira, 3 classes: benigno, atípico, maligno). Valores do projeto refeitos com o rótulo oficial em 07/11 (`lamina/bracs/rotulo_oficial.py`); a versão de 06/11 (`comparacao_literatura.py`) usava o agrupamento antigo e dava 0,496 e 0,523.

| Método | Treino | Teste | Acurácia balanceada (3 classes) |
|---|---|---|---|
| UNI + ABMIL (Chen et al., Nature Medicine 2024, Extended Data Table 19) | 395 lâminas | 87 lâminas | 0,687 (0,617–0,760) |
| ResNet-50 ImageNet + ABMIL (mesma tabela) | 395 lâminas | 87 lâminas | 0,552 (0,490–0,607) |
| Hierárquico, descritor com negativos (sem critério) | 79 lâminas | 57 das 87 | 0,560 |
| Classificador 4 classes, descritor com negativos | 79 lâminas | 57 das 87 | 0,518 |
| E0 — modelo de linguagem decide | — | 57 das 87 | 0,370 |

A comparação é indicativa, não direta: os conjuntos de teste e de treino diferem, e o UNI2-h usado aqui é outro modelo. Nas 7 classes, o mesmo artigo reporta 0,468 (0,393–0,550); a pipeline não prevê as 7. O UNI + ABMIL usa o mesmo agrupamento oficial. A distância até 0,687 sugere o que o MIL com as 379 lâminas de treino pode acrescentar. No artigo do ACMIL (arXiv 2311.07125, Tabela 1), com outra métrica (F1 macro em 3 classes, características SSL), ABMIL chega a 0,680 e ACMIL a 0,722.

## Rótulo oficial do BRACS: correção e reteste (07/11)

Script: `Testes/Pipeline01/lamina/bracs/rotulo_oficial.py`, fixado antes (commit `095320c`). Descritor, negativos (agora 34 lâminas: N, PB e UDH) e classificador da lâmina refeitos com o rótulo oficial; treino nas mesmas 79 lâminas, teste nas mesmas 57 (benigno 20, atípico 17, DCIS 8, IC 12).

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

Script: `Testes/Pipeline01/prelaudo/bracs/prelaudo_campos.py`, fixado antes (commit `21cb292`). A classe vem do classificador da lâmina (versão de 06/11, agrupamento antigo); o Gemma 3 4B recebe campos fixos (classe, probabilidades, confiança, proporções, 3 regiões) e só redige. A checagem automática compara cada número e coordenada do texto com a evidência que o modelo recebeu, e é aplicada também aos 57 pré-laudos antigos (modelo decidindo). Critério: classe do texto igual à sugerida em ≥ 90% e fração de números sem sustentação não maior que a dos antigos.

| | Pré-laudos novos (só redige) | Pré-laudos antigos (modelo decide) |
|---|---|---|
| Classe do texto igual à sugerida | **57/57** | — |
| Números checados / sem sustentação | 791 / **0** | 523 / 11 (2,1%, em 4 textos) |
| Coordenadas citadas / inventadas | 175 / **0** | 178 / 2 |
| Tempo médio por pré-laudo | 68 s | — |

**Passou.** O texto fica fiel aos campos: nos casos de confiança baixa, diz que a confiança é baixa e que as proporções são mistas. Limitações: a checagem não detecta achados morfológicos inventados (na leitura de 3 textos, não houve nenhum); e o texto quase só reorganiza os campos, acrescentando pouca informação. A classe final é a do classificador: com o rótulo oficial, 19/57 (acurácia balanceada 0,425) para a versão de 06/11 usada aqui; a versão corrigida com negativos chega a 29/57.

## Resposta em conjunto: benigno, atípico, "benigno ou atípico", maligno (07/11)

Script: `Testes/Pipeline01/lamina/bracs/resposta_em_conjunto.py`, fixado antes (commit `6392791`). Quando o classificador da lâmina (descritor com negativos, rótulo oficial) não separa benigno de atípico, responde "benigno ou atípico". Medem-se juntos o **acerto do conjunto** (a classe real está na resposta?) e as **respostas exatas** (uma classe só). A margem de recuo `d` foi escolhida no treino como a menor com acerto do conjunto ≥ 0,80; nenhuma chegou lá (máximo 0,797), e a regra usou a maior da grade, 0,45. Critério: nas 57, acerto do conjunto ≥ 0,75 e respostas exatas ≥ 0,50.

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

Script: `Testes/Pipeline01/lamina/bracs/concentracao_espacial.py`, fixado antes (commit `3a62bd4`). Hipótese vinda de dois mapas de calor: numa lesão, os patches suspeitos formam um foco; numa lâmina benigna, os falsos positivos ficam espalhados. Quatro atributos novos por lâmina, com os 8 vizinhos mais próximos de cada patch na amostra: enriquecimento dos suspeitos, dos malignos e dos atípicos (1 = espalhados ao acaso) e fração de suspeitos em foco. Descritor com negativos e rótulo oficial; os 12 atributos antigos conferem exatamente com `rotulo_oficial.py`. Critério: nas 37 lâminas benignas e atípicas do teste, AUC benigno × atípico com os atributos novos ≥ AUC sem eles + 0,05, e ≥ 0,70.

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

## MIL com atenção (ABMIL), 79 lâminas de treino (09/11)

Script: `Testes/Pipeline01/mil/mil_atencao.py`, fixado antes (commit `c701a1d`). O modelo aprende a classe da lâmina direto do rótulo, a partir dos embeddings do UNI2-h dos 2.000 patches da amostra, sem o descritor por patch. Atenção com porta (Ilse et al., 2018), 40 épocas, média de 5 sementes, sem ajuste de hiperparâmetro. Treino: as mesmas 79 lâminas (42 pacientes); teste: as mesmas 57 (31 pacientes, nenhum em comum com o treino). Critérios: C1 acurácia balanceada nas 4 classes > 0,505 (classificador com negativos); C2 AUC benigno × atípico ≥ 0,70.

| Nas 57 lâminas | Benigno (20) | Atípico (17) | DCIS (8) | IC (12) | Acertos | Acurácia balanceada | Passou? |
|---|---|---|---|---|---|---|---|
| Classificador + negativos (07/11) | 10 | 6 | 2 | 11 | 29/57 | 0,505 | referência |
| **ABMIL** | **15** | **10** | 2 | 11 | **38/57** | **0,626** (IC 95% 0,52–0,75) | **C1: sim** |

| | Descritor (melhor versão) | ABMIL |
|---|---|---|
| AUC benigno × atípico (37 lâminas) | 0,58 | **0,78** (C2: sim) |
| AUC maligno × resto | 0,83 | 0,88 |
| Acurácia balanceada em 3 classes | 0,52–0,56 | 0,68 |
| Resposta em conjunto (d = 0,45): acerto / exatas | 0,70 / 0,44 | 0,83 / 0,70 |

- **Passou nos dois critérios, com folga.** Aprender da lâmina inteira resolve boa parte do benigno × atípico, que o descritor por patch não separava (0,58 → 0,78).
- **Em 3 classes, 0,68**, perto do UNI + ABMIL publicado (0,687 com 395 lâminas de treino e as 87 de teste). A comparação continua indicativa: outro teste, outro modelo base, 57 lâminas.
- **O DCIS continua fraco** (2/8): 6 das 20 lâminas malignas saem como benignas ou atípicas; só 1 benigna ou atípica sai como maligna.
- **Confirmação em validação cruzada** (`mil/bracs/mil_validacao_cruzada.py`, fixado antes, commit `4666c80`): o mesmo MIL, sem mudança, em 5 partes por paciente nas 79 lâminas de treino, sem usar as 57. Critério: acurácia balanceada ≥ 0,55 e AUC benigno × atípico ≥ 0,70. **Passou:**

| Validação cruzada nas 79 | Benigno (34) | Atípico (17) | DCIS (11) | IC (17) | Acertos | Acurácia balanceada | AUC benigno × atípico | AUC maligno × resto |
|---|---|---|---|---|---|---|---|---|
| Classificador + negativos | 25 | 6 | 2 | 13 | 46/79 | 0,509 | 0,851 | 0,779 |
| **ABMIL** | 28 | 11 | 6 | 12 | **57/79** | **0,680** | **0,915** | **0,914** |

  No classificador com descritor, a AUC benigno × atípico de 0,85 na validação cruzada caiu para 0,58 no teste externo; no MIL, a queda foi menor (0,92 → 0,78).
- **Ressalvas:** 57 lâminas reaproveitadas em vários testes (nada foi ajustado nelas, e o MIL não usou nenhum limiar); intervalo largo. Treinado com 79 lâminas; as 379 de treino ainda não baixadas devem ajudar. A atenção por patch ficou salva para mapas de calor (`resultados/mil_atencao/`).

## A atenção do MIL cai nas lesões anotadas? (09/11)

Script: `Testes/Pipeline01/mil/bracs/atencao_nas_lesoes.py`, fixado antes (commit `87d2de8`). Nas 29 lâminas do teste externo com rótulo atípico, DCIS ou IC que têm anotação oficial de lesão, compara-se a fração dos 5% de patches de maior atenção que cai dentro das lesões anotadas com a fração de todos os patches da amostra que cai nelas (referência: o que um sorteio acertaria). Coordenadas do GeoJSON conferidas contra o estágio 1 (diferença de poucos pixels). Critério: acima da referência em ≥ 70% das lâminas e razão somada ≥ 2.

| 29 lâminas | Lâminas acima da referência | Topo na lesão (média) | Referência (média) | Razão |
|---|---|---|---|---|
| **Atenção do MIL** | 21 (72%) | 11,5% | 2,3% | **5,0** |
| P(não benigno) do descritor | 24 (83%) | 8,8% | 2,3% | 3,9 |

| Por classe (razão: MIL / descritor) | Lâminas | MIL acima da referência |
|---|---|---|
| Atípico | 14 | 9 (64%) — razão 8,8 / 6,6 |
| DCIS | 5 | 5 (100%) — razão 4,9 / 4,2 |
| IC | 10 | 7 (70%) — razão 4,3 / 3,1 |

**Passou.** Os patches que mais pesam na decisão do MIL estão 5 vezes mais dentro das lesões do que o acaso: a atenção serve de explicação e de roteador. O descritor também aponta para as lesões, em mais lâminas, mas com concentração menor. As frações absolutas são baixas porque as anotações cobrem só 2,3% dos patches da amostra e marcam regiões, não toda a lesão.

## Pré-laudo com o MIL e mapas de atenção (10/11)

Script: `Testes/Pipeline01/prelaudo/bracs/prelaudo_mil.py`, fixado antes (commit `29a4192`). A classe e a confiança vêm do MIL; as regiões citadas são os 3 patches de maior atenção, cada um com a descrição do descritor; o Gemma 3 4B só redige, com as instruções e a checagem de `prelaudo_campos.py`. Critério: classe do texto igual à sugerida em ≥ 90% e fração de números sem sustentação não maior que a dos pré-laudos antigos.

| 57 pré-laudos | Com o MIL | Modelo decide (antigo) |
|---|---|---|
| Classe do texto igual à sugerida | 57/57 | — |
| Números sem sustentação | 0 de 791 | 11 de 523 (2,1%) |
| Coordenadas inventadas | 0 de 267 | 2 de 178 |
| Classe final certa | 38/57 (acurácia balanceada 0,626) | 17/57 |
| Regiões citadas dentro da lesão anotada (lâminas não benignas com anotação) | 18 de 93 | 7 de 93 (regiões do descritor, `prelaudo_campos.py`) |

**Passou.** Problema que a checagem não pega: em 15 lâminas o MIL sugere benigno, mas regiões de maior atenção são descritas como atípicas ou malignas; só 1 dos 15 textos aponta a contradição, e os outros a justificam (ex.: BRACS_1003691, "a presença de um patch de ductal carcinoma in situ [...] influenciou a sugestão de benignidade"). Contagem por expressões no texto ("contradição", "no entanto", "embora"...), sem leitura completa dos 15. Mapas de atenção de 4 lâminas: `ferramentas/mapas_de_calor.py --atencao`, em `docs/visao_geral/img/mapa_atencao_*.jpg`.

## Generalização pra pulmão: TCGA LUAD × LUSC (11–12/11)

Pergunta: a mesma receita de classificação da lâmina (patches de tecido de 128 µm, UNI2-h congelado, MIL com atenção, mesma configuração de treino), retreinada com lâminas de outro órgão, funciona? O MIL é treinado do zero com as lâminas de pulmão; o modelo treinado na mama não é reaproveitado. Tarefa: adenocarcinoma (TCGA-LUAD) × carcinoma escamoso (TCGA-LUSC), lâminas de diagnóstico do TCGA (acesso aberto). Fixado antes de baixar (commit `4d1d4de`): 100 pacientes de cada projeto, uma lâmina por paciente, sorteio com semente 0; treino 60 + 60, teste 40 + 40, pacientes diferentes; lado do patch em pixels pela resolução da lâmina; modelo e treino de `mil_atencao.py`, com 2 classes. Critério: AUC ≥ 0,85 E acurácia balanceada ≥ 0,75 no teste. Scripts: `Testes/Pipeline01/dados/tcga/tcga_baixar_e_embutir.py`, `Testes/Pipeline01/mil/tcga/tcga_mil.py`.

| Teste (78 lâminas) | Resultado |
|---|---|
| AUC LUAD × LUSC | **0,981** (IC 95% 0,953–1,0) |
| Acurácia balanceada | **0,949** |
| Acerto por classe | LUAD 37/39, LUSC 37/39 |
| Acerto por resolução | 0,25 µm/px (40x): 64/68; 0,50 µm/px (20x): 8/8; 0,23 µm/px: 2/2 |

**Passou.** Ficaram de fora 3 das 200 lâminas: 2 sem resolução no arquivo (a regra exige o lado de 128 µm; `TCGA-05-5428`, treino, e `TCGA-05-5429`, teste) e 1 com download incompleto (`TCGA-O2-A52V`, LUSC, teste). Treino: 119 lâminas.

Leitura: LUAD × LUSC é uma tarefa mais fácil que a do BRACS (dois carcinomas de morfologia bem diferente, sem a fronteira benigno × atípico); serve pra mostrar que a receita de classificação não depende de nada específico da mama, não que o problema da mama esteja resolvido. Este teste cobre só a decisão da lâmina; descritor e pré-laudo no pulmão estão na seção seguinte. Uma primeira execução (12/11, 01h24) caiu antes de calcular qualquer número: a internet caiu às 00h31 no meio do download e o teste rodou sem lâminas LUSC no conjunto de teste; o download foi retomado e o teste rodou de novo, sem mudança na regra.

## Pulmão: descritor por patch e pré-laudo (13–14/11)

Pergunta: o resto da pipeline (descritor por patch, campos, pré-laudo redigido pelo modelo de linguagem) também funciona no pulmão? Fixado antes de rodar (commit `7725c6e`). Scripts: `Testes/Pipeline01/dados/lunghist700/escala_lunghist.py`, `Testes/Pipeline01/descritor/pulmao/pulmao_descritor.py`, `Testes/Pipeline01/prelaudo/tcga/tcga_descritor_prelaudo.py`. Resultados em `Testes/Pipeline01/resultados/{lunghist700,tcga_prelaudo}/`.

O que muda em relação à mama: o descritor é treinado no LungHist700 (classes normal, adenocarcinoma, escamoso; rótulo por imagem), não nas regiões anotadas do BRACS; os campos não têm a regra do componente invasivo nem as medidas de núcleo; as instruções do modelo de linguagem são a versão do pulmão, com uma regra a mais (apontar regiões cuja classe difere do tipo sugerido). O MIL é o da seção anterior, retreinado pra gravar a atenção (mesma classe nas 78 lâminas, diferença máxima de 0,0005 na probabilidade).

**Escala do LungHist700.** O artigo não informa µm/px (só 20x e 40x). Estimada pelo diâmetro mediano dos núcleos inflamatórios (CellViT, probabilidade ≥ 0,8) contra o BRACS (MPP do cabeçalho): 4,278 µm no BRACS (1.203 núcleos); 40x, 0,232 µm/px (213 núcleos); 20x, 0,383 µm/px (574 núcleos). Conferência sem critério: a razão 20x/40x deveria ficar perto de 2 e ficou em **1,65**; não está explicado. Mantida a regra fixada (escala medida separada por aumento).

| Teste | Critério | Resultado |
|---|---|---|
| D1: descritor nos 10 pacientes de teste do LungHist700 (931 patches) | acurácia balanceada ≥ 0,80 | **passou: 0,926** (normal 259/259, adeno 351/404, escamoso 244/268; por imagem, 0,993 em 114 imagens) |
| D2: descritor nas 3 regiões de maior atenção do MIL, 78 lâminas de teste do TCGA | maioria das 3 com a classe real em ≥ 80% das lâminas | **não passou: 58/78 (0,744)**; LUAD 21/39, LUSC 37/39 |
| P: pré-laudo, 78 textos | tipo do texto = tipo do MIL em ≥ 90%, 0 números sem sustentação, 0 coordenadas inventadas | **passou**: 78/78; 0 de 1.035 números; 0 de 436 coordenadas |

Leitura:
- O descritor acerta no próprio conjunto (D1) e falha no TCGA nas lâminas de adenocarcinoma: das 117 regiões de maior atenção nessas lâminas, 36 saem como pulmão normal e 21 como escamoso; em 7 lâminas as 3 saem normal, em 6 as 3 saem escamoso. Sozinho (proporção de patches por classe), separa LUAD × LUSC com AUC 0,875, contra 0,98 do MIL. Hipóteses não verificadas: padrão lepídico (o adenocarcinoma cresce sobre as paredes alveolares e lembra pulmão normal) e diferença de imagem (LungHist700 é foto de microscópio de um hospital; TCGA é lâmina escaneada de vários centros). Só um patologista olhando as regiões resolve.
- Discordância: em 27 lâminas pelo menos uma das 3 regiões tem classe diferente do tipo sugerido; só 3 textos apontam a discordância (contagem por expressões: "discord", "no entanto", "embora", "diverg", "contradi", "porém", "entretanto"). A maioria lista as regiões com a classe, sem comentar (ex.: TCGA-NJ-A4YF, impressão "adenocarcinoma" com as 3 regiões listadas como escamoso). A regra nova nas instruções não resolveu o problema visto na mama.
- Classe da região no texto (exploratório, sem critério fixado antes): das 234 regiões citadas, 216 aparecem na mesma linha com a classe dos campos, 2 com a classe trocada (ambas em TCGA-78-7153: campos "pulmão normal", texto "carcinoma escamoso") e 16 o script não decide. A checagem automática confere números e coordenadas, não a classe ligada a cada região.
- Execução: a redação parou duas vezes por tempo esgotado (30 min por chamada) com a memória da máquina cheia, e a máquina reiniciou; retomada do ponto em que parou, sem mudança na regra. Tempo médio por texto: 46 s.

## Próstata: PANDA, grau ISUP (14/11)

Pergunta: a mesma receita (patches de 128 µm, UNI2-h congelado, MIL com atenção, descritor por patch, pré-laudo) funciona numa tarefa de graduação, e não só de tipo? Dados: PANDA (Bulten et al., Nature Medicine 2022; CC BY-NC-SA 4.0), biópsias de próstata com grau ISUP 0–5 e máscara de rótulos, de dois centros. Fixado antes de baixar (commit `97c2f53`): treino = 600 biópsias do Radboud (100 por ISUP), teste = 300 do Karolinska (50 por ISUP), sorteio com semente 0; centros diferentes porque o PANDA não informa o paciente (5.160 biópsias do Radboud vêm de 1.028 pacientes). Scripts: `Testes/Pipeline01/dados/panda/panda_baixar_e_embutir.py`, `Testes/Pipeline01/mil/panda/panda_mil.py`, `Testes/Pipeline01/prelaudo/panda/panda_descritor_prelaudo.py`. Resultados em `Testes/Pipeline01/resultados/{panda_mil,panda_prelaudo}/`.

| Teste | Critério | Resultado |
|---|---|---|
| M1: grau ISUP pelo MIL, 300 biópsias do Karolinska | kappa quadrático ≥ 0,60 | **não passou: 0,237** (IC 95% 0,138–0,336) |
| M2: benigno × câncer pelo MIL | AUC ≥ 0,85 | **passou: 0,940** (IC 95% 0,912–0,966) |
| D1: descritor por patch (benigno, Gleason 3, 4, 5; treino nas máscaras do Radboud), patches do Karolinska | AUC benigno × câncer ≥ 0,85 | **não passou: 0,775** (48.363 patches de câncer, 53.553 benignos) |
| A: 3 regiões de maior atenção do MIL na máscara, 250 biópsias com câncer | ≥ 2 das 3 no câncer em ≥ 80% das biópsias | **não passou: 190/250 (0,76)**; por acaso, 0,43 |
| P: pré-laudo, 60 textos (10 por ISUP) | ISUP do texto = ISUP do MIL em ≥ 90%, 0 números sem sustentação, 0 coordenadas inventadas | **passou**: 60/60; 0 de 628 números; 0 de 315 coordenadas |

Também reportado (sem critério): AUC ISUP 1 × ISUP ≥ 2 de 0,888; acurácia exata 0,270 e a ±1 grau 0,617. Acerto por ISUP real (de 50 cada): 0 → 4, 1 → 21, 2 → 7, 3 → 39, 4 → 3, 5 → 7. Matriz de confusão (linhas = real 0–5, colunas = previsto 0–5): `[4,3,2,38,0,3] [1,21,2,25,1,0] [1,7,7,35,0,0] [1,3,6,39,1,0] [0,2,2,41,3,2] [1,1,4,31,6,7]`. O descritor acerta câncer × benigno em 528 das 668 regiões de maior atenção com tecido rotulado. ISUP do texto igual ao real: 22/60. Em 35 das 60 biópsias pelo menos uma região tem classe que discorda do grau sugerido; 1 texto aponta a discordância.

Leitura:
- O MIL separa câncer de benigno em outro centro (M2), mas não gradua: prevê ISUP 3 em 209 das 300 biópsias, inclusive em 38 das 50 benignas e em 31 das 50 de ISUP 5. Hipóteses não separadas por este teste: troca de centro (coloração e escâner diferentes; treino só no Radboud) e falta de informação espacial (o MIL não sabe a posição dos patches, e o Gleason é arquitetura das glândulas). O teste seguinte (GAT-MIL) foi desenhado pra separar as duas.
- A atenção cai no câncer bem acima do acaso (0,76 contra 0,43), mas abaixo do critério.
- O pré-laudo continua fiel aos campos (P), e por isso repete o erro do MIL; como no pulmão e na mama, quase nunca aponta quando a região discorda do grau sugerido.
- Máscaras: 16 biópsias de treino do Radboud não têm máscara no PANDA (confirmado pela resposta do Kaggle); ficaram de fora só do treino do descritor (584 biópsias). As 300 de teste têm máscara.
- Execução: (1) a primeira tentativa de download falhou nas primeiras biópsias porque o Kaggle CLI 2.x grava o arquivo noutra pasta; corrigido só o caminho (commit `747763b`). (2) No fim do download, o Kaggle limitou as requisições (erro 429): as últimas 39 biópsias (todas Karolinska ISUP 5) falharam e 1 máscara foi tratada como inexistente. Uma rodada com 861 biópsias foi descartada sem registro dos números; o script passou a esperar e tentar de novo no 429 (commit `9fedbee`), as biópsias sem máscara foram reprocessadas (1 recuperou a máscara) e tudo rodou de novo com as 900. (3) A máquina reiniciou durante o treino do descritor; retomado desse passo. Nenhuma mudança na regra. Espaço usado no HD: 29 GB.

## Próstata: MIL com atenção em grafo (GAT-MIL) × ABMIL (14/11)

Pergunta: o colapso em ISUP 3 vem da falta de informação espacial (o ABMIL trata a biópsia como um saco de patches) ou da troca de centro? GAT-MIL: cada patch ligado aos 8 vizinhos da grade (média de 7,1 arestas por patch, contando o próprio; todas as biópsias do PANDA cabem na amostra, então o grafo é completo); uma camada de atenção entre vizinhos (GATv2, 4 cabeças, residual) antes do pooling do ABMIL; mesma receita de treino, 5 sementes, nenhum ajuste. Fixado antes de rodar (commit `6c698d7`): G1, entre centros (treino nas 600 do Radboud, teste nas 300 do Karolinska); G2, dentro do centro (validação cruzada em 5 partes nas 600 do Radboud, estratificada por ISUP). Critério de cada um: kappa(GAT-MIL) − kappa(ABMIL) > 0 com o limite inferior do IC 95% pareado (bootstrap, 2.000) > 0. Scripts: `Testes/Pipeline01/mil/gat_mil/gat_mil.py` (genérico) e `Testes/Pipeline01/mil/gat_mil/gat_mil_panda.py`. Resultados em `Testes/Pipeline01/resultados/gat_mil_panda/`.

| Cenário | Kappa ABMIL | Kappa GAT-MIL | Diferença (IC 95%) | Critério |
|---|---|---|---|---|
| G1: Radboud → Karolinska (300) | 0,237 (0,138–0,336) | **0,436** (0,330–0,540) | **+0,199** (0,114–0,289) | **passou** |
| G2: dentro do Radboud (600) | 0,784 (0,739–0,827) | **0,806** (0,762–0,846) | **+0,021** (0,002–0,042) | **passou** |

Também reportado (sem critério), ABMIL → GAT-MIL: G1, AUC benigno × câncer 0,940 → 0,963, acurácia exata 0,270 → 0,370, a ±1 grau 0,617 → 0,710, previstos como ISUP 3 209 → 129 de 300, benignas certas 4 → 12 de 50, ISUP 5 certas 7 → 14 de 50; G2, AUC 0,957 → 0,968, acurácia exata 0,592 → 0,613. O kappa do ABMIL no G1 é o mesmo do `panda_mil.py` (0,237).

Leitura:
- Pela leitura combinada escrita antes, G1 e G2 passando = a informação espacial ajuda, inclusive em outro centro. O ganho é grande entre centros (+0,20) e pequeno dentro do centro (+0,02, com o limite inferior do IC quase em zero).
- O problema maior continua sendo a troca de centro: dentro do Radboud os dois modelos graduam bem (kappa ~0,80), no Karolinska caem pra 0,24–0,44. Não está separado se o ganho do GAT-MIL no G1 vem da arquitetura das glândulas ou de a mistura com os vizinhos deixar o embedding menos sensível à coloração; as duas coisas são compatíveis com o resultado.
- Ressalva do G2: o PANDA não informa o paciente, e a mesma pessoa pode cair no treino e no teste de uma parte; isso infla os dois modelos igualmente.
- Próximo passo: repetir a comparação no BRACS e no TCGA (o código do GAT-MIL é genérico) e atacar a troca de centro (normalização de cor ou treino com os dois centros).

## GAT-MIL no BRACS e no TCGA (14/11)

Pergunta: o ganho do GAT-MIL no PANDA se repete na mama e no pulmão? Fixado antes de rodar (commit `6b21cbd`). Diferença do PANDA: no BRACS e no TCGA a amostra de 2.000 patches cobre só parte do tecido (23 de 136 lâminas do BRACS e 19 de 197 do TCGA cabem inteiras), então o grafo liga cada patch aos até 8 patches da amostra mais próximos com centro a até 3 lados (384 µm); média de 6,1 vizinhos por patch no BRACS e 5,5 no TCGA. Mesmos modelos e receita. Script: `Testes/Pipeline01/mil/gat_mil/gat_mil_bracs_tcga.py`. Resultados em `Testes/Pipeline01/resultados/gat_mil_bracs_tcga/`.

| Cenário | ABMIL | GAT-MIL | Diferença (IC 95%) | Critério |
|---|---|---|---|---|
| B1: BRACS, 79 → 57, acurácia balanceada (4 classes) | 0,626 | 0,597 | −0,029 (−0,077 a 0,0) | GAT-MIL > ABMIL: **não passou** |
| B2: BRACS, validação cruzada por paciente nas 79 | 0,680 | 0,636 | −0,045 (−0,123 a 0,030) | GAT-MIL > ABMIL: **não passou** |
| T1: TCGA, 119 → 78, AUC LUAD × LUSC | 0,981 | 0,981 | 0,000 (−0,010 a 0,011) | não piora (limite > −0,02): **passou** |

Também reportado (sem critério), ABMIL → GAT-MIL: B1, por classe benigno 15 → 15/20, atípico 10 → 8/17, DCIS 2 → 2/8, IC 11 → 11/12; AUC benigno × atípico 0,782 → 0,812; maligno × resto 0,881 → 0,907. B2, AUC benigno × atípico 0,915 → 0,856; maligno × resto 0,914 → 0,926. TCGA, acurácia balanceada 0,949 → 0,962. Os números do ABMIL reproduzem os de `mil_atencao.py` (0,626) e `mil_validacao_cruzada.py` (0,680).

Leitura:
- Na mama, a vizinhança não ajudou: as duas diferenças são negativas, com IC cruzando zero ou encostando nele. No pulmão, empate (a tarefa já está no teto).
- Diferenças que podem explicar, não testadas: o grafo da mama e do pulmão é parcial (vizinhos a até 384 µm entre os patches sorteados, não o tecido contínuo do PANDA); o rótulo do BRACS é o da lesão mais grave, muitas vezes pequena, e a arquitetura em volta dela importa menos que a própria lesão; treino com só 79 lâminas. Pra testar a primeira, seria preciso recalcular os embeddings de todo o tecido.

## Próstata: troca de centro, padronização por centro × normalização de cor (14/11)

Pergunta: a queda do Radboud pro Karolinska (kappa ~0,80 → 0,24 com o ABMIL e 0,44 com o GAT-MIL) diminui com uma correção que não usa rótulo do centro novo? Fixado antes de rodar (commit `27f0508`). Treino nas 600 do Radboud, teste nas 300 do Karolinska, mesmos modelos e receita. Braços: R0, embeddings originais; R1, padronização por centro (cada dimensão do embedding menos a média e dividida pelo desvio, calculados nos patches do próprio centro; no Karolinska, nas 300 de teste, sem rótulo); R2, normalização de cor de Reinhard (espaço Lab, alvo = cor média das 600 de treino) e embeddings recalculados. Critérios, com o GAT-MIL: N1, kappa(R1) − kappa(R0) > 0 com limite inferior do IC 95% > 0; N2, idem pra R2. Scripts: `Testes/Pipeline01/mil/panda/panda_centro.py` e `Testes/Pipeline01/dados/panda/panda_embutir_reinhard.py`. Resultados em `Testes/Pipeline01/resultados/panda_centro/`.

| Braço | Kappa ABMIL (IC 95%) | Kappa GAT-MIL (IC 95%) |
|---|---|---|
| R0: original | 0,237 (0,138–0,336) | 0,439 (0,341–0,534) |
| R1: padronização por centro | 0,540 (0,446–0,631) | 0,609 (0,515–0,699) |
| R2: normalização de cor (Reinhard) | 0,275 (0,174–0,368) | 0,225 (0,117–0,339) |

| Diferença | ABMIL (IC 95%) | GAT-MIL (IC 95%) | Critério (GAT-MIL) |
|---|---|---|---|
| R1 − R0 | +0,303 (0,196 a 0,400) | +0,170 (0,067 a 0,269) | N1: **passou** |
| R2 − R0 | +0,038 (−0,077 a 0,147) | −0,214 (−0,317 a −0,102) | N2: **não passou** |

Também reportado (sem critério), GAT-MIL R0 → R1 → R2: acurácia exata 0,360 → 0,457 → 0,317; a ±1 grau 0,683 → 0,790 → 0,663; previstos como ISUP 3 142 → 38 → 128 de 300; benignas certas 16 → 26 → 1 de 50; ISUP 5 certas 12 → 29 → 25 de 50. AUC benigno × câncer 0,947 → 0,957 → 0,933. O kappa do GAT-MIL em R0 (0,439) difere do de `gat_mil_panda.py` (0,436) por não determinismo da GPU na soma por arestas.

Leitura:
- A padronização por centro resolve boa parte da queda: o colapso em ISUP 3 some (142 → 38 previstos), e o melhor resultado entre centros passa a ser 0,61 (GAT-MIL + R1). O ganho soma com o do GAT-MIL (os dois juntos são melhores que cada um). Custo: precisa de um lote de lâminas do centro novo (sem rótulo) antes de usar.
- A normalização de cor não ajudou e, com o GAT-MIL, piorou: quase nenhuma benigna certa (1 de 50), e muitas viram ISUP 2–5. A diferença entre centros que atrapalha o modelo não é (só) a cor média; e a normalização de Reinhard pode tirar informação da coloração que o modelo usava.
- Ainda longe do dentro do centro (~0,80). Próximos: rede de grafos (seção seguinte); combinar R1 com treino nos dois centros.

## Próstata: rede de grafos × ABMIL × GAT-MIL (14/11)

Pergunta: olhar a biópsia inteira, escolher pontos de interesse e montar um grafo local denso em cada ponto, ligado aos outros pontos por distância (ideia proposta em 14/11/2026), gradua melhor que o ABMIL? Pontos: até 16 por biópsia, os patches de maior atenção de um ABMIL que não viu a biópsia (no treino, atenção fora da parte em validação cruzada em 5 partes; no teste, o ABMIL treinado nas 600), com centros a pelo menos 1 mm; em cada ponto, janela de 7 × 7 patches com uma camada GATv2 e pooling; os pontos formam um grafo completo com uma camada de atenção que diminui com a distância (peso aprendido, em mm); pooling e classe. Mesma receita de treino, 5 sementes, nenhum ajuste, embeddings originais. Fixado antes de rodar (commit `da1d4b8`): H1, entre centros (600 Radboud → 300 Karolinska); H2, dentro do Radboud (validação cruzada nas mesmas 5 partes do GAT-MIL). Critério de cada um: kappa(rede de grafos) − kappa(ABMIL) > 0 com limite inferior do IC 95% pareado > 0. Scripts: `Testes/Pipeline01/mil/rede_grafos/rede_grafos.py` (genérico) e `Testes/Pipeline01/mil/rede_grafos/rede_grafos_panda.py`. Resultados em `Testes/Pipeline01/resultados/rede_grafos_panda/`.

| Cenário | ABMIL | GAT-MIL | Rede de grafos | Rede − ABMIL (IC 95%) | Rede − GAT-MIL (IC 95%) | Critério |
|---|---|---|---|---|---|---|
| H1: Radboud → Karolinska (300) | 0,237 | 0,420 | 0,442 | +0,205 (0,104 a 0,310) | +0,021 (−0,056 a 0,099) | **passou** |
| H2: dentro do Radboud, validação cruzada (600) | 0,784 | 0,795 | 0,809 | +0,025 (−0,002 a 0,051) | +0,014 (−0,014 a 0,045) | **não passou** (por pouco) |

Também reportado (sem critério): pontos por biópsia, média 9,8 (mínimo 1; poucas biópsias comportam 16 pontos a 1 mm); as janelas cobrem 67% dos patches (contando repetição). H1, ABMIL → GAT-MIL → rede: AUC benigno × câncer 0,940 → 0,960 → 0,959; acurácia exata 0,270 → 0,370 → 0,353; previstos como ISUP 3 209 → 124 → 101 de 300. H2: AUC 0,957 → 0,970 → 0,969; acurácia exata 0,592 → 0,633 → 0,627. Os kappas do GAT-MIL (0,420 e 0,795) diferem dos de `gat_mil_panda.py` (0,436 e 0,806) por não determinismo da GPU.

Leitura:
- Entre centros, a rede de grafos ganha do ABMIL com folga e empata com o GAT-MIL, olhando só as janelas em volta de ~10 pontos. Dentro do Radboud, o maior kappa dos três, mas a diferença pro ABMIL não chega a ser provada.
- A escolha dos pontos pela atenção não perde o que importa pro grau: com 2/3 dos patches, o resultado fica no nível do GAT-MIL com todos. A vantagem esperada (ver o tecido em volta das regiões suspeitas) aparece mais em lâminas grandes e com amostra parcial, como as do BRACS, onde o GAT-MIL não ajudou.
- Não testado aqui: a rede de grafos com a padronização por centro (o melhor braço da troca de centro); protótipos por classe.

## Rim: TCGA-RCC, 3 subtipos, treino e teste em hospitais diferentes (14–15/11)

Pergunta: a receita (UNI2-h + MIL) funciona num terceiro órgão, e funciona em hospitais que o modelo nunca viu? Tarefa: carcinoma de células claras (TCGA-KIRC) × papilífero (TCGA-KIRP) × cromófobo (TCGA-KICH), lâminas de diagnóstico, 100 pacientes por subtipo (semente 0), amostra de 2.000 patches de 128 µm. No TCGA de rim cada hospital mandou um subtipo só, então um modelo pode acertar aprendendo o "jeito" do hospital (coloração, escâner, preparo). Por isso a divisão principal é por hospital: dentro de cada subtipo, hospitais inteiros vão pro teste até ter pelo menos 40 pacientes; nenhum hospital do teste está no treino. Comparação sem critério: divisão aleatória 60/40, como no pulmão. A padronização por hospital não foi testada: com um subtipo por hospital, subtrair a média do hospital subtrai a média do subtipo. Fixado antes de baixar (commit `e9efc8e`). Critérios: R1, MIL nos hospitais novos com acurácia balanceada ≥ 0,80 e AUC macro ≥ 0,90; R2, GAT-MIL não pior (limite inferior do IC da diferença de acurácia balanceada > −0,05). Scripts: `Testes/Pipeline01/dados/tcga/lista_tcga_rim.py`, `Testes/Pipeline01/mil/tcga/rim_mil.py`. Resultados em `Testes/Pipeline01/resultados/rim_mil/`.

| Cenário | Modelo | Acurácia balanceada (IC 95%) | AUC macro (IC 95%) | Células claras | Papilífero | Cromófobo |
|---|---|---|---|---|---|---|
| Hospitais novos (137) | **MIL** | **0,953** (0,915–0,983) | **0,987** (0,968–0,999) | 49/54 | 39/41 | 42/42 |
| Hospitais novos (137) | GAT-MIL | 0,945 (0,905–0,979) | 0,986 (0,967–0,999) | 49/54 | 38/41 | 42/42 |
| Aleatório (119) | MIL | 0,983 (0,956–1,0) | 1,000 (0,999–1,0) | 39/40 | 38/39 | 40/40 |
| Aleatório (119) | GAT-MIL | 0,975 (0,943–1,0) | 0,999 (0,998–1,0) | 39/40 | 38/39 | 39/40 |

- **R1: passou** (0,953 e 0,987). **R2: passou** (GAT-MIL − MIL: −0,008, IC −0,026 a 0,0).
- Efeito do hospital: a acurácia balanceada do MIL cai de 0,983 (sorteio aleatório) para 0,953 (hospitais novos). Pequena, mas existe: parte do acerto no sorteio aleatório vem de reconhecer o hospital.
- Erros nos hospitais novos (MIL): 5 de 54 lâminas de células claras (2 como papilífero, 3 como cromófobo) e 2 de 41 papilíferos (como células claras); cromófobo 42/42.
- Ficou de fora 1 das 300 lâminas, sem resolução no arquivo (`TCGA-UZ-A9PQ`, papilífero, treino). Download e embeddings: ~17 h, limitados pelo GDC.
- Comparação indicativa: o artigo do CLAM (Lu et al., Nature Biomedical Engineering 2021) reporta AUC ~0,99 nos três subtipos do TCGA, com divisão aleatória.

Leitura: como no pulmão, subtipar carcinomas de morfologia bem distinta é fácil pra receita, inclusive em hospitais novos. A vizinhança (GAT-MIL, com o grafo parcial da amostra) não acrescenta. Os testes difíceis continuam sendo a mama (benigno × atípico) e a graduação.

## Pulmão: só o núcleo × núcleo com contexto, dataset do orientador (19/11)

Pergunta: dá pra separar adenocarcinoma de carcinoma epidermoide só pelo núcleo, sem o tecido em volta (como na citologia)? E quanto o contexto acrescenta? Dataset do orientador (não público): 52 pacientes (25 adenocarcinoma, 27 epidermoide), 1.647 campos de biópsia H&E de 620 × 480 px (20 a 40 por paciente) e 5.593 imagens de núcleo isolado sobre fundo branco (100 a 131 por paciente). Achado antes do teste: as imagens da pasta de "citologia" são núcleos recortados dos próprios campos de biópsia (nome do arquivo = campo + número do núcleo; cada recorte aparece pixel a pixel no seu campo, erro máximo 0,005 por pixel nos 5.593). Então não é uma coleta citológica independente, e sim o núcleo da biópsia sem o tecido em volta. Isso permite comparar o mesmo núcleo com e sem contexto.

Avaliação por paciente: 5 repetições de validação cruzada em 5 partes estratificadas; probabilidade final de cada paciente = média das 5 repetições; IC 95% por bootstrap por paciente (2.000). Braços: T1, medidas clássicas dos núcleos (forma, cor, textura GLCM; média e desvio por paciente) + regressão logística; T2, MIL sobre os campos de biópsia (UNI2-h); T3, MIL sobre os núcleos, com tudo fora do núcleo pintado de branco (janela de 448 px reduzida à metade); T4, MIL sobre as mesmas janelas sem pintar (núcleo + tecido em volta; os pixels do núcleo são idênticos aos de T3). Fixado antes de rodar (commits `a225cd8` e `7bf1908`, este só pra caber 1 núcleo maior que a janela). Critérios: P1, T2 com acurácia balanceada ≥ 0,80; P2, T3 com AUC acima do acaso (limite inferior do IC > 0,5); P3, T4 − T3 > 0 na AUC com IC > 0; P4, T3 − T1 > 0 na AUC com IC > 0. Scripts: `Testes/PulmaoFlorindo/preparar.py`, `Testes/PulmaoFlorindo/testar.py`.

| Braço | AUC (IC 95%) | Acurácia balanceada (IC 95%) | Adeno | Epidermoide |
|---|---|---|---|---|
| T1 clássico nos núcleos | 0,599 (0,442–0,750) | 0,518 (0,382–0,653) | 12/25 | 15/27 |
| T2 biópsia, MIL | 0,942 (0,867–0,996) | **0,886** (0,789–0,962) | 23/25 | 23/27 |
| T3 só núcleo, MIL | 0,479 (0,305–0,643) | 0,532 (0,402–0,656) | 9/25 | 19/27 |
| T4 núcleo + contexto, MIL | **0,948** (0,879–0,996) | 0,866 (0,766–0,952) | 22/25 | 23/27 |
| T3 na escala original | 0,447 (0,285–0,615) | 0,492 (0,369–0,616) | 7/25 | 19/27 |
| T4 na escala original | 0,862 (0,738–0,959) | 0,809 (0,697–0,905) | 21/25 | 21/27 |
| Média dos embeddings + logística, biópsia | 0,939 | 0,886 | 23/25 | 23/27 |
| Média dos embeddings + logística, só núcleo | 0,529 | 0,555 | 12/25 | 17/27 |
| Média dos embeddings + logística, contexto | 0,930 | 0,847 | 22/25 | 22/27 |
| Fusão T2 + T3 | 0,911 | 0,866 | 22/25 | 23/27 |

- **P1: passou** (0,886). **P2: não passou** (AUC 0,479, no acaso). **P3: passou** (T4 − T3: +0,470, IC 0,294 a 0,650). **P4: não passou** (T3 − T1: −0,120, IC −0,353 a 0,117; os dois no acaso).
- O mesmo núcleo, com o tecido em volta (janela de ~450 px no campo original), vai do acaso a AUC 0,95, no nível do campo inteiro (T2 − T4: −0,006, IC −0,022 a 0,007). Correção (26/11, na revisão da pipeline): essa janela tem 448 × 448 px reduzidos à metade, o mesmo tamanho e escala de um recorte do campo, e cobre ~67% da área do campo; então T4 ≈ T2 acontece por construção e não é um achado separado. O número de "contexto em volta do núcleo" é o da escala original (janela de 224 px, ~17% do campo): AUC 0,862, +0,415 sobre o núcleo sozinho (IC 0,211 a 0,607).
- Nem o UNI2-h nem as medidas clássicas acham o subtipo no núcleo isolado. Juntar os núcleos à biópsia (fusão) não acrescenta: são os mesmos pixels.
- Ressalvas: 52 pacientes (IC largos); as máscaras dos núcleos vêm de uma segmentação antiga e o contorno pode ter cortado parte da cromatina da borda; um só conjunto, sem outro hospital.

Leitura: neste conjunto, o subtipo está no arranjo do tecido em volta do núcleo, não no núcleo. Para a "citologia" deste dataset (núcleo isolado), nenhum dos métodos funciona; o caminho, se houver, passa por recuperar contexto (janela em volta do núcleo), e não por super-resolução do núcleo.

## Pré-laudo: aviso de discordância pronto nos campos, pulmão e próstata (19–20/11)

Pergunta: se a discordância entre a classe sugerida e uma região de maior atenção for calculada por código e entrar nos campos como uma linha de AVISO pronta, o pré-laudo passa a apontá-la? Antes, com a regra só nas instruções ("aponte essa discordância"), o texto quase nunca apontava (pulmão 3 de 27, próstata 1 de 35). Mesmos documentos, campos, modelo (Gemma 3 4B) e opções dos testes anteriores: 78 lâminas de pulmão (TCGA) e 60 biópsias de próstata (PANDA); muda só a seção de avisos nos campos e a regra 5 das instruções ("reproduza cada AVISO na seção ## Avisos de discordância"). Discordância: pulmão, região com classe do descritor diferente do tipo sugerido; próstata, região benigna com ISUP ≥ 1 ou região com Gleason com ISUP 0. Medida "aponta" por expressões na linha da coordenada (ou na seguinte), aplicada igual aos textos antigos e novos. Fixado antes de rodar (commit `ff94d74`). Critérios em cada órgão: W1, aponta em ≥ 90% dos documentos com região discordante; W2, falso alarme ≤ 10% nos documentos sem região discordante; W3, classe extraída = sugerida em ≥ 90%, 0 números sem sustentação, 0 coordenadas inventadas. Script: `Testes/Pipeline01/prelaudo/aviso_discordancia.py`.

| | Pulmão antes | Pulmão com aviso | Próstata antes | Próstata com aviso |
|---|---|---|---|---|
| Documentos com região discordante que apontam (W1) | 5/27 | **27/27** | 11/35 | **35/35** |
| Regiões discordantes apontadas, uma a uma | 12/64 | 64/64 | 23/75 | 75/75 |
| Contagem antiga por expressões | 3/27 | 27/27 | 1/35 | 35/35 |
| Falso alarme em documentos sem discordância (W2) | 3/51 | **0/51** | 8/25 | **0/25** |
| Classe extraída = sugerida (W3) | 78/78 | 78/78 | 60/60 | 60/60 |
| Números sem sustentação / coordenadas inventadas (W3) | 0 / 0 | 0 de 893 / 0 de 276 | 0 / 0 | 0 de 424 / 0 de 216 |
| Avisos em região que não discorda (depois dos resultados) | — | 2 linhas, 1 documento | — | 16 linhas, 9 documentos |
| Classe trocada numa coordenada (depois dos resultados) | 2 linhas | 0 | 0 | 3 linhas, 3 documentos |

- **W1, W2 e W3: passaram nos dois órgãos.** O texto passa a reproduzir todos os avisos (64/64 e 75/75 regiões), sem avisar nos documentos sem discordância.
- Lendo os textos depois, apareceu um efeito que W2 não mede (W2 só olha documentos sem nenhuma região discordante): dentro de documentos que têm aviso, o modelo às vezes copia o formato do AVISO para uma região que não discorda. No pulmão, 1 documento ("adenocarcinoma, o que discorda do tipo sugerido adenocarcinoma"); na próstata, 9 de 60, a maioria regiões de Gleason 3 ou 4 em biópsias ISUP ≥ 1, e em 3 delas o texto troca a classe da região (Gleason 4 escrito como benigno). Contagem feita depois dos resultados (`--etapa extra`, sem critério); a checagem de W3 confere números e coordenadas, não o par coordenada–classe.
- Tempo médio por texto: 75,5 s (pulmão) e 49,9 s (próstata), com a GPU dividida com outro processo.

Leitura: com o aviso calculado por código, o pré-laudo deixa de esconder a discordância nos dois órgãos. O modelo reproduz o que está pronto, mas não deve decidir o que é discordante: na próstata, ele ainda acrescenta avisos falsos e, em 3 documentos, troca a classe da região. O próximo passo natural é inserir a seção de avisos por código, sem passar pelo modelo, e conferir o par coordenada–classe na checagem automática.

## Pré-laudo: avisos colados por código e pré-laudo em inglês, pulmão e próstata (20/11)

Pergunta: com a seção de avisos substituída por código pelas linhas calculadas (o modelo redige o resto), somem os avisos espúrios e as trocas de classe vistas na etapa anterior? E o pré-laudo em inglês (campos traduzidos por código, instruções em inglês, mesmo modelo) mantém a fidelidade? Mesmos documentos (pulmão 78, próstata 60) e mesmo modelo (Gemma 3 4B, temperatura 0,2, semente 0); na próstata, os campos vêm do ABMIL sem padronização, como nas rodadas anteriores. A checagem passa a conferir também o par coordenada–classe de cada região citada. Os títulos de seção ("## Avisos de discordância") não contam como aviso. Fixado antes de rodar (commit `cca50ab`). Critérios: K1 (português, colado), 0 trocas de classe, 0 avisos em região concordante, todas as regiões discordantes na seção, 0 números não sustentados e 0 coordenadas inventadas; K2 (inglês, colado), classe extraída igual à sugerida em ≥ 90% e as mesmas condições. Script: `Testes/Pipeline01/prelaudo/avisos_por_codigo.py`.

| | Pulmão PT | Pulmão EN | Próstata PT | Próstata EN |
|---|---|---|---|---|
| Classe extraída = sugerida | 78/78 | 78/78 | 60/60 | 60/60 |
| Regiões discordantes na seção de avisos | 64/64 | 64/64 | 75/75 | 75/75 |
| Documentos com aviso em região concordante (texto do modelo → colado) | 1 → **0** | 4 → **0** | 9 → **0** | 10 → **0** |
| Documentos com classe da região trocada (texto do modelo → colado) | 0 → 0 | 0 → 0 | 3 → **0** | 3 → **0** |
| Números não sustentados | 0/891 | 0/574 | 0/408 | 0/388 |
| Coordenadas inventadas | 0/274 | **1/284** | 0/200 | 0/276 |
| Critério | **K1 passou** | **K2 não passou** | **K1 passou** | **K2 passou** |

- Colar a seção resolve o que a etapa anterior deixou: os avisos espúrios e as trocas de classe estavam todos no texto que o modelo escreveu na seção de avisos e somem quando ela é substituída. O modelo escreveu a seção em todos os documentos (78/78, 60/60), e a colagem só substitui o conteúdo.
- K2 não passou no pulmão por uma coordenada: num documento (TCGA-67-3771) o modelo copiou na lista "Regions for priority review" a região [22815,28392] como [22815,28913]. Fora da seção de avisos, o texto continua escrito pelo modelo; a checagem automática acusa o erro (o documento sai marcado), mas o critério pedia zero.
- O texto em inglês é mais curto (574 números checados contra 891 no pulmão). Contado depois, sem critério: a seção de resumo da evidência sai vazia em parte dos documentos, nos dois idiomas (inglês: pulmão 3/78, próstata 32/60; português: 10/78 e 33/60); o conteúdo não se perde, porque os campos e os avisos continuam no documento, mas o texto fica mais pobre.
- Tempo: a rodada em inglês travou no meio (o modelo carregado do HD com só 5 de 35 camadas na GPU e o swap cheio; um pedido estourou 30 min) e foi retomada do ponto onde parou; a média registrada (pulmão 18 s, próstata 64 s por laudo) inclui esse trecho lento.

Leitura: a seção de avisos deve sair do código, e com isso a classe e os avisos ficam fiéis nos dois idiomas. O que ainda depende do modelo é copiar as coordenadas fora dessa seção; a lista de regiões para revisão também pode ser montada por código.

## Pré-laudo final: lista de regiões colada por código, GAT-MIL padronizado na próstata e aviso × erro do MIL (20/11)

Três perguntas, com critérios fixados antes de rodar (commit `8d4e6fc`). Scripts: `Testes/Pipeline01/prelaudo/prelaudo_final.py` e `Testes/Pipeline01/prelaudo/aviso_erro.py`.

**1. Lista de regiões colada por código (pulmão).** Depois da colagem dos avisos, o conteúdo da seção "Regiões para revisão prioritária" também é trocado pelas 3 regiões dos campos. Aplicado aos mesmos textos brutos do pulmão, sem chamar o modelo de novo. Critério F1 (cada idioma): 0 trocas de classe, 0 avisos em região concordante, todas as regiões discordantes na seção, 0 números sem sustentação e 0 coordenadas inventadas.

| Pulmão (78) | Português | Inglês |
|---|---|---|
| Classe trocada; aviso em região concordante | 0; 0 | 0; 0 |
| Regiões discordantes na seção | 64/64 | 64/64 |
| Números sem sustentação | 0/1.125 | 0/808 |
| Coordenadas inventadas | 0/439 | 0/331 (antes da colagem: 2/292) |
| F1 | **passou** | **passou** |

**2. Próstata com o modelo melhor (GAT-MIL com embeddings padronizados por centro).** Retreinado com a mesma receita do braço R1 de `panda_centro.py`, agora guardando probabilidades e atenção por biópsia. O kappa nas 300 biópsias do Karolinska ficou em 0,570 (antes 0,609; o treino do GAT na GPU não é determinístico). A previsão não colapsa mais em ISUP 3 (previstos por ISUP 0–5: 33, 44, 84, 37, 53, 49). Nas mesmas 60 biópsias do pré-laudo: ISUP sugerido 8, 6, 18, 11, 8 e 9 (antes, com o ABMIL, 40 de 60 em ISUP 3); sugerido = real em 30/60; 30 com região discordante. Sem critério: em 227 de 250 biópsias com câncer e máscara, pelo menos 2 das 3 regiões de maior atenção do GAT-MIL estão no câncer (0,91; ABMIL 190/250 = 0,76; acaso 0,43). Pré-laudos com esse modelo, avisos e regiões colados por código (critério F2: classe igual à sugerida em ≥ 90% e as condições de F1, em cada idioma):

| Próstata, GAT-MIL padronizado (60) | Português | Inglês |
|---|---|---|
| Classe extraída = sugerida | 60/60 | 56/60 |
| Classe trocada; aviso em região concordante (texto do modelo → colado, em documentos) | 2 → 0; 7 → 0 | 4 → 0; 14 → 0 |
| Regiões discordantes na seção | 55/55 | 55/55 |
| Números sem sustentação | 0/595 | 0/395 |
| Coordenadas inventadas | 0/262 | 0/247 |
| F2 | **passou** | **passou** |

- Lendo os 4 textos em inglês em que a classe extraída diferiu: a impressão escrita é a sugerida nos 4 ("ISUP 2", "ISUP 1", "ISUP 2", "ISUP 2"); o erro é da segunda chamada, que extrai a classe do texto. Fiel por leitura: 60/60.
- Antes da colagem, o modelo de novo escreveu avisos em regiões que não discordam (7 documentos em português, 14 em inglês) e trocou a classe da região (2 e 4); a colagem tira tudo.
- Contado depois, sem critério: o resumo da evidência sai vazio em 30 de 60 (português) e 42 de 60 (inglês).
- A rodada foi interrompida duas vezes (HD desmontado; fim da sessão) e retomada de onde parou.

**3. O aviso marca os erros do MIL?** O aviso é calculado por código, então foi medido em todas as lâminas de teste: pulmão, 78 com o ABMIL; próstata, 300 com o GAT-MIL padronizado (erro = câncer × benigno trocado). Critério E: taxa de erro maior nas lâminas com aviso, Fisher unilateral p < 0,05.

| | Pulmão (78; 4 erros) | Próstata (300; 35 erros câncer × benigno) |
|---|---|---|
| Taxa de erro com aviso / sem aviso | **4/27 (0,148) / 0/51 (0)** | **27/169 (0,160) / 8/131 (0,061)** |
| Erros com aviso (sensibilidade) | 4/4 | 27/35 (0,77) |
| Risco relativo (IC 95%) | — (nenhum erro sem aviso) | 2,62 (1,31 a 7,49) |
| Fisher unilateral | p = 0,012 | p = 0,006 |
| E | **passou** | **passou** |
| Confiança não alta como sinal: erros pegos | 1/4 | 28/35 |
| Aviso dentro das lâminas com confiança alta: erro com / sem aviso | 3/24 / 0/51 | 6/90 / 1/81 |
| Aviso ou confiança não alta: erros pegos | 4/4 | 34/35 |

- No pulmão, a confiança do MIL pega só 1 dos 4 erros (3 deles têm probabilidade alta); o aviso pega os 4. Com 4 erros, o resultado é frágil.
- Na próstata, o aviso é frequente (169 de 300, especificidade 0,46) e a confiança sozinha já pega quase tanto (28/35); juntos pegam 34 de 35. Sem critério: o aviso também separa erro de ISUP exato (0,65 × 0,43) e erro de 2 ou mais graus (0,29 × 0,09).

Leitura: o aviso não é só um enfeite do texto; nas lâminas com aviso o MIL erra mais, nos dois órgãos. No pulmão ele pega erros que a confiança não pega; na próstata ele soma com a confiança.

## Atenção do MIL: teste de remoção e de suficiência, pulmão e próstata (20/11)

Pergunta: a atenção do MIL aponta os patches que sustentam a decisão? No TCGA não há anotação de região, então no pulmão a atenção só tinha sido mostrada nos mapas; na próstata ela foi conferida nas máscaras (190 de 250 biópsias, acaso 0,43). Este teste não precisa de anotação: se a atenção é fiel ao modelo, tirar os patches de maior atenção deve derrubar a probabilidade da classe prevista mais do que tirar patches sorteados (remoção), e ficar só com eles deve sustentar a classe melhor do que ficar com patches sorteados (suficiência). Mesmos modelos das rodadas que geraram a atenção dos pré-laudos (ABMIL, 5 sementes, retreinados; classe prevista igual em 78/78 e 300/300); ordem dos patches pela atenção salva. Fixado antes de rodar (commit `cca50ab`). Critérios, em cada órgão: X1, (queda tirando os 10% de maior atenção − queda tirando 10% sorteados) > 0 com IC 95% acima de 0; X2, (probabilidade só com os 20 de maior atenção − só com 20 sorteados) > 0 com IC acima de 0. Script: `Testes/Pipeline01/mil/remocao_atencao.py`.

| | Pulmão (78 lâminas) | Próstata (300 biópsias) |
|---|---|---|
| X1: remoção, top 10% − sorteio (IC 95%) | **+0,120** (0,052 a 0,195) | **+0,203** (0,173 a 0,234) |
| Queda tirando 10%: atenção / sorteio | 0,120 / 0,000 | 0,208 / 0,005 |
| Classe muda tirando 10%: atenção / sorteio | 14,1% / 0% | 39,3% / 3,3% |
| X2: suficiência, top 20 − sorteio (IC 95%) | **−0,091** (−0,171 a −0,011) | **+0,188** (0,165 a 0,211) |
| P(classe) só com 20: atenção / sorteio | 0,855 / 0,946 | 0,688 / 0,501 |

- **X1 passou nos dois órgãos; X2 passou na próstata e não passou no pulmão.** Tirar os patches de maior atenção derruba a decisão; tirar a mesma quantidade sorteada quase não muda nada.
- No pulmão, ficar só com os 20 patches de maior atenção sustenta a classe pior do que 20 sorteados. Separando pela classe prevista (análise feita depois dos resultados, sem critério): nas 39 lâminas previstas como carcinoma escamoso a atenção é fiel (remoção +0,264, suficiência +0,093, nenhuma lâmina com diferença negativa); nas 39 previstas como adenocarcinoma, não (remoção −0,024, suficiência −0,276; diferença negativa em 28% e 41% das lâminas). Na próstata, o mesmo nas 8 biópsias previstas como ISUP 0 (remoção −0,263, suficiência −0,089), contra +0,216 e +0,196 nas 292 previstas com câncer.
- Leitura (hipótese): o MIL decide como um detector da classe "positiva" (escamoso no pulmão, câncer na próstata); a outra classe é a ausência dessa evidência. Nas lâminas da classe "por ausência", os patches de maior atenção são os mais parecidos com a classe positiva, e não evidência a favor da classe prevista. Isso é coerente com o descritor ter descrito como normal ou escamoso as regiões de maior atenção em 18 de 39 lâminas de adenocarcinoma, e com os avisos de discordância se concentrarem nessas lâminas.
- Ressalva: tirar patches muda a distribuição que o modelo viu no treino; o sorteio serve de controle para isso.

Leitura: a atenção é fiel ao modelo quando a classe prevista é a que o modelo detecta (escamoso, câncer) e não deve ser lida como "onde está a evidência" quando a classe prevista é a outra (adenocarcinoma, benigno). No pré-laudo, as "regiões que mais pesaram" de uma lâmina de adenocarcinoma são, em geral, as mais suspeitas de escamoso.

## Atenção do GAT-MIL padronizado (próstata) e classe do pré-laudo extraída por código (20/11)

Dois testes com critérios fixados antes de rodar (commit `d9dcb0f`). Scripts: `Testes/Pipeline01/mil/remocao_atencao_gat.py` e `Testes/Pipeline01/prelaudo/extracao_codigo.py`.

**Remoção e suficiência com o GAT-MIL.** O teste anterior usou o ABMIL; os pré-laudos da próstata usam o GAT-MIL padronizado. Mesma receita retreinada (os pesos da rodada dos pré-laudos não foram guardados; o treino na GPU não é determinístico): classe prevista igual à daquela rodada em 259/300, atenção com Spearman médio 0,952. Depois de tirar patches, o grafo é refeito só com os que ficam. Critérios Y1 e Y2: os mesmos de X1 e X2.

| Próstata, 300 biópsias | ABMIL (antes) | GAT-MIL padronizado |
|---|---|---|
| Remoção, 10% de maior atenção − sorteio (IC 95%) | +0,203 (0,173 a 0,234) | **+0,310** (0,268 a 0,356) |
| Queda tirando 10%: atenção / sorteio | 0,208 / 0,005 | 0,316 / 0,005 |
| Classe muda tirando 10%: atenção / sorteio | 39,3% / 3,3% | 55,0% / 4,6% |
| Suficiência, 20 de maior atenção − sorteio (IC 95%) | +0,188 (0,165 a 0,211) | **+0,124** (0,086 a 0,160) |
| P(classe) só com 20: atenção / sorteio | 0,688 / 0,501 | 0,649 / 0,525 |
| Critério | X1, X2 passaram | **Y1, Y2 passaram** |

- Separado pela classe prevista (reportado, sem critério): nas 35 previstas como ISUP 0, remoção −0,207 e suficiência −0,305; nas 265 com câncer, +0,379 e +0,180. O mesmo padrão do ABMIL e do pulmão: a atenção sustenta a decisão quando a classe prevista é a que o modelo detecta (câncer), não quando é a ausência dela.

**Classe extraída por código.** A classe sai da primeira linha da seção de impressão (nome de classe que aparece primeiro; na próstata, o primeiro "ISUP" com dígito); o modelo só é usado se a regra não achar nada. Aplicada aos pré-laudos finais, sem gerar texto novo. Critério C: classe = sugerida em ≥ 90%, em cada órgão e idioma.

| | Pulmão PT | Pulmão EN | Próstata PT | Próstata EN |
|---|---|---|---|---|
| Resolvidos pela regra | 78/78 | 78/78 | 60/60 | 60/60 |
| Classe = sugerida (antes, só o modelo) | 78/78 (78/78) | 78/78 (78/78) | 60/60 (60/60) | **60/60 (56/60)** |
| C | passou | passou | passou | passou |

- Nos 4 textos em que a regra e o modelo discordam (próstata, inglês), a regra está certa nos 4: o texto é fiel à classe em todos os 276 pré-laudos finais.

## Segundo modelo de linguagem: Llama 3.2 3B na configuração final do pré-laudo (20–23/11)

Pergunta: a fidelidade vem da colagem e da checagem por código, ou de uma propriedade do Gemma 3 4B? Mesmos documentos, campos, instruções, colagem (avisos e regiões) e opções de geração; muda só o modelo que redige (Llama 3.2 3B, de outra família). Classe lida por código na primeira linha da impressão; se a regra não achar, segunda chamada ao mesmo Llama em JSON restrito. Fixado antes de rodar (commit `117ad6f`). Critério L, em cada órgão e idioma: classe = sugerida em ≥ 90% e as condições de F1. Script: `Testes/Pipeline01/prelaudo/segundo_modelo.py`. A rodada foi interrompida três vezes (HD desmontado, fim de sessão) e retomada de onde parou.

| Llama 3.2 3B | Pulmão PT | Pulmão EN | Próstata PT | Próstata EN |
|---|---|---|---|---|
| Classe = sugerida (resolvida pela regra) | 57/78 (0/78) | 78/78 (78/78) | 60/60 (0/60) | 60/60 (59/60) |
| Regiões discordantes na seção de avisos | 64/64 | 64/64 | 55/55 | 55/55 |
| Documentos com aviso em região concordante | 1 | 0 | 0 | 0 |
| Documentos com classe trocada | 0 | 0 | 0 | 0 |
| Números sem sustentação | 0/659 | 0/614 | 0/477 | **1/536** |
| Coordenadas inventadas | 0/346 | 0/298 | 0/281 | 0/238 |
| L | **não passou** | **passou** | **passou** | **não passou** |

- Em português, o Llama escreveu os títulos das seções como `### Título` ou em negrito, não como `## Título` (a seção de avisos com o título esperado em 17 de 78 e 14 de 60 documentos). Com isso, a colagem não achou a seção para substituir: a seção calculada entrou no fim do texto, mas a versão escrita pelo modelo ficou. A regra da classe também não achou a impressão (0/78, 0/60), e a extração pelo Llama errou 21 dos 78 no pulmão.
- Lendo a impressão com qualquer formato de título (depois, sem critério): a classe escrita é a sugerida em todos os 276 laudos (nos 2 casos em que a primeira linha diverge, ela é só uma frase de abertura e a classe vem na linha seguinte). O erro do pulmão em português é da extração, não do texto.
- O aviso espúrio (pulmão, português) está no resumo escrito pelo modelo, que cita uma coordenada concordante junto de "além disso"/"no entanto".
- O número sem sustentação (próstata, inglês) é um "69%" calculado pelo modelo (100% − 31%), que não está nos campos.
- Antes da colagem, o Llama deixa de apontar boa parte das regiões discordantes (pulmão PT 37/64, EN 0/64; próstata PT 19/55, EN 42/55); com a colagem, todas aparecem nos quatro casos.

Leitura: a colagem por código faz o mesmo trabalho com o Llama (todos os avisos certos, nenhuma troca de classe, nenhuma coordenada inventada), mas depende de o modelo usar os títulos pedidos; com outro formato, a seção do modelo fica no texto e a extração da classe falha. O caminho seguro é o código montar as seções críticas (decisão, avisos, regiões) e o modelo escrever só o resumo e as limitações, ou normalizar os títulos antes de colar. A checagem de números pega o único número calculado.

## Próstata: 5 execuções do desenho 2 × 2 (ABMIL ou GAT-MIL × embeddings originais ou padronizados) (25/11)

Pergunta, a partir da revisão do paper: o resultado do GAT-MIL padronizado se repete (uma execução deu kappa 0,609, outra 0,570, e o mínimo fixado era 0,60)? E o ganho vem do grafo ou da padronização? Mesmas 600 de treino (Radboud) e 300 de teste (Karolinska); 5 execuções, a execução r com as sementes 5r a 5r + 4. Fixado antes de rodar (commit `2e0c884`). Critérios: S1, GAT-MIL padronizado − ABMIL original > 0 em todas as execuções; S2, média do GAT-MIL padronizado ≥ 0,60. Script: `Testes/Pipeline01/mil/panda/panda_repeticoes.py`.

| Média de 5 execuções | ABMIL original | GAT-MIL original | ABMIL padronizado | GAT-MIL padronizado |
|---|---|---|---|---|
| Kappa quadrático (média ± desvio) | 0,295 ± 0,052 | 0,448 ± 0,075 | 0,590 ± 0,031 | **0,649 ± 0,040** |
| AUC benigno × câncer | 0,953 | 0,960 | 0,957 | 0,970 |
| Especificidade (benignas chamadas de benignas) | 0,08 | 0,27 | 0,44 | 0,62 |
| Sensibilidade ao câncer | 0,994 | 0,993 | 0,978 | 0,966 |
| Acurácia exata (ISUP) | 0,285 | 0,358 | 0,404 | 0,461 |

- **S1 passou** (diferença de +0,27 a +0,41 nas 5 execuções) e **S2 passou** (0,649).
- O efeito maior é da padronização (no GAT-MIL, +0,13 a +0,30 por execução); o grafo acrescenta menos (com padronização, +0,04 a +0,09).
- O 0,570 da rodada que gerou os pré-laudos ficou abaixo das 5 execuções (0,621 a 0,719): foi uma execução baixa, não a regra.
- Mesmo o melhor modelo chama de câncer 38% das biópsias benignas (especificidade 0,62); o ABMIL original, 92%.

## Pulmão com divisão por centro de origem (25/11)

Pergunta, a partir da revisão do paper: na amostra do TCGA nenhum dos 54 centros de origem mandou as duas classes, e 65 das 80 lâminas de teste vinham de centros também presentes no treino; a AUC de 0,981 pode estar inflada pelo centro. Aqui as 197 lâminas são previstas em validação cruzada de 5 partes agrupada por centro (53 centros; nenhum centro em duas partes), ABMIL com 5 sementes. Fixado antes de rodar (commit `2e0c884`; a correção de memória do `37f9d66` foi feita antes de qualquer resultado). Critérios: Z1, AUC ≥ 0,85 e acurácia balanceada ≥ 0,75; Z2, erro maior nas lâminas com aviso, Fisher p < 0,05. Script: `Testes/Pipeline01/mil/tcga/pulmao_por_centro.py`.

| | Divisão aleatória (78 de teste) | Divisão por centro (197) |
|---|---|---|
| AUC (IC 95%) | 0,981 (0,953–1,0) | **0,947** (0,910–0,976) |
| Acurácia balanceada (IC 95%) | 0,949 | **0,893** (0,848–0,934) |
| Acerto adenocarcinoma / escamoso | — | 86/98 / 90/99 |
| Erros | 4 | 21 |
| Erro com aviso / sem aviso | 4/27 / 0/51 | **16/69 (0,23) / 5/128 (0,04)**, p = 0,0001 |

- **Z1 passou** e **Z2 passou**. Com centros novos, a AUC cai de 0,98 para 0,95: parte do resultado anterior vinha do centro, mas o subtipo continua sendo reconhecido.
- Com 21 erros, o resultado aviso × erro deixa de se apoiar em 4: 16 dos 21 erros têm aviso. Os avisos continuam concentrados nas lâminas previstas como adenocarcinoma (58 de 69).

## O aviso contra as linhas de base (25/11)

Pergunta, a partir da revisão: o aviso acrescenta algo à confiança do classificador para achar os erros? Pulmão: as 197 lâminas da divisão por centro (21 erros). Próstata: as 300 de teste, GAT-MIL padronizado da execução 0 de `panda_repeticoes.py` (30 erros câncer × benigno). Sinais: aviso (número de regiões discordantes), confiança (1 − probabilidade da classe prevista), sementes (desvio entre as 5 sementes), classe prevista ("por ausência") e a combinação confiança + aviso (regressão logística fora da amostra). Fixado antes de rodar (commit `2e0c884`). Critérios: B1, AUROC do aviso com IC acima de 0,5; B2, AUROC(combinação) − AUROC(confiança) > 0 com IC acima de 0. Script: `Testes/Pipeline01/prelaudo/aviso_linhas_base.py`.

| AUROC para achar erro (IC 95%) | Pulmão (21 erros) | Próstata (30 erros) |
|---|---|---|
| Aviso | **0,765** (0,648–0,862) | **0,715** (0,616–0,809) |
| Confiança | 0,769 (0,646–0,871) | 0,779 (0,685–0,860) |
| Discordância entre as 5 sementes | 0,777 (0,652–0,882) | **0,913** (0,874–0,944) |
| Classe prevista | 0,470 | 0,567 |
| Combinação confiança + aviso | 0,725 | 0,807 |
| Erros pegos marcando tantas lâminas quanto o aviso (k) | k = 69: aviso 16, confiança 16, sementes 16, acaso 7,4 | k = 168: aviso 25, confiança 27, sementes 30, acaso 16,8 |

- **B1 passou** nos dois órgãos: o aviso acha erros bem acima do acaso.
- **B2 não passou** em nenhum: somar o aviso à confiança não melhora (pulmão −0,045, IC −0,207 a 0,107; próstata +0,028, IC −0,016 a 0,068). Na mesma taxa de marcação, o aviso pega o mesmo que a confiança no pulmão e um pouco menos na próstata.
- A discordância entre as 5 sementes, que já existe e não custa nada, é o melhor sinal na próstata (AUROC 0,913; pega os 30 erros marcando 168).
- A classe prevista sozinha não marca erro (0,47 e 0,57), então o aviso não é só um disfarce da classe.

Leitura: o aviso é informativo e explicável (aponta a região que contradiz a decisão), mas como sinal de triagem não acrescenta à incerteza do próprio classificador; para triagem, a discordância entre sementes é melhor. No paper, a contribuição do aviso deve ser a de explicação honesta, não a de detector de erro superior.

## Seções montadas pelo código e linha de base sem modelo de linguagem (25–26/11)

Pergunta, a partir da revisão: o que o modelo de linguagem acrescenta a um template, e quantos erros ele comete quando escreve livremente? Braço T: o laudo inteiro montado pelo código a partir dos campos, sem modelo de linguagem. Braço M: o código monta impressão, avisos, regiões e limitações; o modelo escreve só o parágrafo de resumo da evidência, e as medidas são feitas só nesse parágrafo. Documentos da configuração final (pulmão 78, próstata 60 com o GAT-MIL padronizado), português e inglês, Gemma 3 4B e Llama 3.2 3B. Fixado antes de rodar (commit `193cc67`). Critério Q, em cada um dos 8 casos (modelo × órgão × idioma): no parágrafo, 0 números sem sustentação, 0 coordenadas inventadas, 0 classes trocadas e 0 avisos em região concordante; e classe lida = sugerida em 100%. Script: `Testes/Pipeline01/prelaudo/secoes_por_codigo.py`.

| Parágrafo livre (braço M) | Classe lida = sugerida | Números sem sustentação (documentos) | Coordenadas inventadas | Classe trocada | Aviso em região concordante (documentos marcados) | Palavras |
|---|---|---|---|---|---|---|
| Gemma, pulmão, pt | 78/78 | 5 (3) | 0 | 0 | 12 (8) | 60 |
| Gemma, pulmão, en | 78/78 | 5 (3) | 1 | 0 | 22 (11) | 57 |
| Gemma, próstata, pt | 60/60 | 5 (5) | 0 | 0 | 24 (15) | 63 |
| Gemma, próstata, en | 60/60 | 0 (0) | 0 | 0 | 31 (18) | 67 |
| Llama, pulmão, pt | 78/78 | 27 (7) | 0 | 0 | 16 (6) | 65 |
| Llama, pulmão, en | 78/78 | 26 (7) | 0 | 0 | 11 (5) | 70 |
| Llama, próstata, pt | 60/60 | 36 (9) | 0 | 0 | 3 (1) | 68 |
| Llama, próstata, en | 60/60 | 18 (6) | 1 | 0 | 5 (3) | 61 |

- **Q não passou em nenhum dos 8 casos.** Nenhuma classe trocada e classe lida certa em todos os 552 laudos (a impressão é montada pelo código); os erros estão nos números e nos avisos do parágrafo livre.
- O braço T passa por construção na mesma checagem (0 em tudo, 64/64 e 55/55 regiões discordantes na seção de avisos, 276/276 classes lidas), com um resumo de 55–74 palavras, do mesmo tamanho do parágrafo dos modelos.
- Números: o Llama erra 4 a 7 vezes mais que o Gemma (18–36 contra 0–5) e converte unidades que não existem nos campos (por exemplo 25,4, 3048, 4572: coordenadas em pixels tratadas como polegadas ou milímetros); o Gemma erra pouco (3–5 documentos por caso) e em inglês na próstata não erra nenhum.
- Avisos em região concordante: a medida foi feita para a seção de avisos, uma linha por região, e no parágrafo livre ela conta também frases que citam regiões concordantes e discordantes juntas ou que negam o aviso ("No discordant warnings were identified, and regions [...]"). Contagem feita depois dos resultados, sem critério: dos documentos marcados, 13 de 67 têm uma negação do aviso na frase; separar os falsos positivos da medida dos erros reais pede leitura manual, que não foi feita. Os números da tabela são, portanto, um limite superior.

Leitura: tirando o modelo de linguagem, o laudo fica correto por construção e com o mesmo tamanho; com ele, mesmo escrevendo só um parágrafo, aparecem números sem sustentação, poucos com o Gemma e muitos com o Llama. O texto livre do modelo é o único lugar em que ainda há erro; no paper, o template deve ser a linha de base, e o parágrafo do modelo, se mantido, precisa vir marcado como texto não verificado.

## Classe por ausência: para que lado empurram os patches de maior atenção (26/11)

Pergunta, a partir da revisão: nas lâminas previstas como a classe que o MIL parece decidir pela falta de evidência (adenocarcinoma no pulmão, ISUP 0 na próstata), os patches de maior atenção empurram contra a classe prevista? O classificador é linear sobre a soma ponderada, então a margem (logit da classe prevista menos o da outra) se decompõe exatamente por patch; a contribuição assinada de cada patch é positiva quando ele empurra a favor da classe prevista. Pulmão: as 197 lâminas com a divisão por centro, ABMIL. Próstata: as 300 de teste, GAT-MIL padronizado. 5 sementes. Fixado antes de rodar (commit `57a2a59`). Critérios: H1 (pulmão) e H3 (próstata), nas lâminas "por ausência", contribuição dos 20 de maior atenção (fração da soma de |contribuição| da lâmina) < 0 com IC < 0; H2 (pulmão), suficiência na margem (só os 20 de maior atenção − só 20 sorteados) < 0 com IC < 0. Script: `Testes/Pipeline01/mil/ausencia.py`.

| Média por lâmina (IC 95%) | Pulmão, previstas adenocarcinoma (95) | Pulmão, previstas escamoso (102) | Próstata, previstas ISUP 0 (35) | Próstata, previstas ISUP ≥ 1 (265) |
|---|---|---|---|---|
| Contribuição dos 20 de maior atenção | **−0,002** (−0,022 a 0,018) | 0,437 (0,406 a 0,468) | **0,366** (0,312 a 0,421) | 0,671 (0,641 a 0,699) |
| Contribuição de 20 sorteados | 0,012 | 0,009 | 0,068 | 0,052 |
| Remoção na margem (10% de maior atenção − 10% sorteados) | −0,08 (−0,39 a 0,20) | 7,47 (6,61 a 8,38) | −3,05 (−3,62 a −2,54) | 4,34 (3,80 a 4,86) |
| Suficiência na margem (20 de maior atenção − 20 sorteados) | **−1,98** (−3,36 a −0,62) | 5,76 (5,15 a 6,43) | −2,79 (−3,58 a −1,98) | 2,98 (2,53 a 3,41) |
| Composição pelo descritor (fração da outra classe tumoral, top − sorteio) | +0,070 (0,032 a 0,108) | −0,274 | — | — |

- **H1 não passou:** nas lâminas previstas como adenocarcinoma, os 20 de maior atenção não empurram contra a classe; empurram para lado nenhum (contribuição líquida zero, contra 44% da soma nas previstas como escamoso). Tirar os 10% de maior atenção também não muda a margem.
- **H2 passou:** sozinhos, os 20 de maior atenção sustentam o adenocarcinoma pior que 20 sorteados (−1,98 em logit), o achado antigo, agora fixado antes e fora do teto da probabilidade. Eles têm 7 pontos percentuais a mais de patches que o descritor chama de escamoso.
- **H3 não passou:** na próstata, nas previstas como ISUP 0, os patches de maior atenção empurram a favor do benigno (0,366), ao contrário da hipótese. Ainda assim, a remoção e a suficiência na margem são negativas (−3,05 e −2,79): tirar esses patches não enfraquece o benigno, e só eles o sustentam pior que um sorteio. No GAT-MIL a característica de cada patch já mistura os vizinhos e a atenção é renormalizada quando os patches mudam, então a decomposição e as perturbações podem discordar; a causa não foi testada.

Leitura: no pulmão, nas lâminas de adenocarcinoma, a atenção alta não é a evidência da decisão (contribuição líquida zero, mais patches parecidos com escamoso); a decisão vem do conjunto, como na leitura "por ausência", mas não por patches que empurram contra. Na próstata a hipótese não se sustenta pela decomposição. No pré-laudo, as regiões de maior atenção das lâminas "por ausência" não devem ser apresentadas como evidência da classe prevista.

## Aviso por grau na próstata e proporções do classificador de patches (26/11)

Perguntas da revisão: (1) a regra da próstata só compara benigno com Gleason; um aviso por padrão incompatível com o grau previsto marca os erros de grau? (2) Como a proporção de cada padrão, que vai no laudo, se distribui pela classe real? Próstata: 300 biópsias de teste, GAT-MIL padronizado, execução 0. Fixado antes de rodar (commit `db8b6ab`). Aviso de grau, nas previstas como ISUP ≥ 1: alguma região com padrão incompatível pela definição do ISUP (ISUP 1 com Gleason 4 ou 5; ISUP 2–3 com Gleason 5; ISUP 5 com Gleason 3; ISUP 4 nunca). Critério G: erro de grau (ISUP previsto ≠ real) maior com aviso, Fisher unilateral p < 0,05. Script: `Testes/Pipeline01/prelaudo/aviso_grau_descritor.py`.

| Previstas como ISUP ≥ 1 (266) | Com aviso de grau (30) | Sem (236) | Fisher |
|---|---|---|---|
| Erro de grau | 17 (57%) | 137 (58%) | p = 0,64 |
| Erro de 2 ou mais graus | 9 (30%) | 50 (21%) | p = 0,19 |

- **G não passou**: o aviso de grau não marca mais erros de grau. Avisos por grau previsto: ISUP 1, 16/46; ISUP 5, 12/60; ISUP 2–3, 2/109.
- Mas, quando aparece, ele aponta a direção do erro: com padrão mais alto que o grau (ISUP 1 com Gleason 4/5, 18 biópsias), o grau real fica em média +0,94 acima do previsto; com padrão mais baixo (ISUP 5 com Gleason 3, 12), −1,75 abaixo. Análise sem critério.

| Proporção mediana dos patches (classificador de patches) | | | | |
|---|---|---|---|---|
| Pulmão | normal | adenocarcinoma | escamoso | classe tumoral mais frequente = tipo real |
| Adenocarcinoma real (98) | 0,36 | 0,58 | 0,02 | 91/98 |
| Escamoso real (99) | 0,22 | 0,27 | 0,38 | 64/99 |
| Próstata | benigno | Gleason 3 | Gleason 4 | Gleason 5 |
| ISUP 0 real | 0,95 | 0,01 | 0,02 | 0,00 |
| ISUP 3 real | 0,80 | 0,03 | 0,14 | 0,00 |
| ISUP 5 real | 0,73 | 0,03 | 0,20 | 0,00 |

- No pulmão, o classificador de patches chama parte do escamoso de adenocarcinoma; a classe tumoral mais frequente erra o tipo em 35 de 99 escamosos. Na próstata, "benigno" domina até no ISUP 5, Gleason 4 cresce com o grau e Gleason 3 e 5 quase nunca aparecem.

Leitura: a proporção de padrões é informativa no conjunto (cresce com a classe real), mas não pode ser lida como fração de tumor da lâmina, sobretudo na próstata; no laudo, ela deve vir como "segundo o classificador de patches", com essa ressalva. O aviso de grau não serve como sinal de erro, mas indica para que lado o grau pode estar errado quando aparece.

## Aviso tumoral × aviso de tecido normal, e calibração da confiança (26/11)

Perguntas da revisão: (1) uma região de pulmão normal numa lâmina de adenocarcinoma (ou benigna numa biópsia com câncer) é esperada; os erros se concentram nos avisos em que a região é do outro tipo de tumor? (2) Quão calibrada é a confiança que vai no laudo? Mesmos dados de `aviso_linhas_base.py` (pulmão: 197 lâminas por centro; próstata: 300, GAT-MIL padronizado, execução 0). Fixado antes de rodar (commit `a2132c4`; correção dos códigos de classe do pulmão antes de qualquer resultado, `65bc7ff`). Critério T (pulmão): taxa de erro com aviso tumoral maior que com aviso só de pulmão normal, Fisher unilateral p < 0,05. Próstata e calibração: descritivas. Script: `Testes/Pipeline01/prelaudo/aviso_tumoral_calibracao.py`.

| Aviso | Pulmão: lâminas (erros) | Próstata: biópsias (erros) |
|---|---|---|
| Tumoral (outro tipo de tumor; Gleason com ISUP 0 previsto) | 35 (10; 29%) | 4 (2) |
| Só tecido não tumoral (pulmão normal; benigno com ISUP ≥ 1) | 34 (6; 18%) | 164 (23; 14%) |
| Sem aviso | 128 (5) | 132 (5) |

- **T não passou** (p = 0,22). O aviso de tecido normal também marca erros (6 dos 21 do pulmão); separar os dois tipos não deixa o aviso mais preciso. Na próstata, o aviso tumoral só existe nas previstas como ISUP 0, então a comparação se confunde com a classe.

| Calibração (confiança = probabilidade da classe prevista) | Pulmão (binário) | Próstata (grau exato, 6 classes) |
|---|---|---|
| Confiança média / acerto médio | 0,973 / 0,893 | 0,742 / 0,463 |
| ECE antes → depois da escala de temperatura | 0,092 → 0,036 | 0,279 → 0,089 |
| Temperatura (5 partes) | 2,97–3,57 | 3,95–4,27 |
| Faixa "alta" (≥ 0,70) antes: lâminas (acerto) | 190 (0,90) | 177 (0,53) |
| Faixa "alta" depois | 176 (0,93) | 14 (0,57) |

- A confiança do laudo é superconfiante nos dois órgãos, muito mais na próstata, em que "alta" acerta o grau exato em só 53%. Depois de calibrar, 232 das 300 biópsias caem na faixa baixa (< 0,50). Na próstata a temperatura foi ajustada no próprio Karolinska (transdutivo); no pulmão, nas partes por centro.
- A temperatura não muda a ordem das lâminas, então não muda o AUROC da confiança nem os resultados de B1/B2.

Leitura: a confiança que vai no laudo precisa ser calibrada antes de ser apresentada como "alta"; sem isso, na próstata ela engana. O aviso de tecido normal deve continuar no laudo: ele também marca erros.

## Células nas regiões de maior atenção (CellViT), próstata (26/11)

Pergunta: os dados de células que o CellViT dá em cada região que vai para o pré-laudo (número de núcleos, proporção de cada tipo, área nuclear) têm sentido? Na próstata, a máscara do Karolinska separa câncer de tecido benigno. Regiões: as 3 de maior atenção do GAT-MIL padronizado nas 300 biópsias de teste (900 regiões). CellViT-256 x40 com os pesos públicos (tipos do PanNuke), sem treino, numa janela de 256 µm ampliada para 0,25 µm/px; contam os núcleos com centro na própria região (128 µm). Fixado antes de rodar (commit `d26c31f`). Critério N: AUC câncer × benigno da fração de núcleos neoplásicos ≥ 0,70, com limite inferior do IC 95% > 0,5 (bootstrap por biópsia), nas regiões com ≥ 5 núcleos. Script: `Testes/Pipeline01/prelaudo/celulas_regioes.py`.

| Medida por região (mediana) | Câncer (659 regiões) | Benigno (187) | AUC câncer × benigno |
|---|---|---|---|
| Fração de núcleos neoplásicos | 0,062 | 0,000 | **0,756** (0,721–0,792) |
| Número de núcleos (região de 128 µm) | 88 | 39 | 0,856 |
| Área nuclear mediana (µm²) | 28,9 | 24,1 | 0,713 |
| Fração conjuntivo / epitelial / inflamatório | 0,44 / 0,10 / 0,03 | 0,66 / 0,23 / 0,04 | — |

- **N passou** (AUC 0,756, IC 0,721–0,792). De fora: 53 regiões sem rótulo claro na máscara e 1 com menos de 5 núcleos.
- O número de núcleos separa melhor que a fração neoplásica (0,856): as regiões de câncer são mais celulares.
- Os valores absolutos dos tipos não podem ser lidos literalmente: mesmo nas regiões de câncer, a fração neoplásica mediana é 6% e a maior parte dos núcleos vira "conjuntivo" (44%). Na mama (NuCLS), o CellViT original também trocava tumor por outro tipo (sensibilidade 0,46). Causas prováveis: os pesos foram treinados a 0,25 µm/px e o Karolinska tem 0,45 µm/px (janela ampliada), e o PanNuke tem poucas lâminas de próstata.
- Por classe do classificador de patches, a fração neoplásica sobe de benigno (0,00) para Gleason 3 (0,12) e Gleason 4 (0,15); Gleason 5 tem só 9 regiões.
- Tempo: mediana de 1,2 s por região na GPU (~4 s por lâmina para 3 regiões).

Leitura: os dados de células nas regiões são informativos para comparar regiões (mais núcleos, núcleos maiores e mais "neoplásicos" no câncer), mas os tipos do CellViT sem retreino não servem como contagem diagnóstica. No laudo, o número de núcleos e a área são os dados mais confiáveis; a proporção de tipos deve vir com essa ressalva.

## MIL com atenção por classe (multi-ramo), pulmão e próstata (26/11)

Pergunta, a partir da revisão: no ABMIL a atenção é única para todas as classes; com um ramo de atenção por classe (como no CLAM multi-ramo, sem a perda de agrupamento), os 20 patches de maior atenção do ramo da classe prevista passam a sustentar a decisão também nas lâminas "por ausência" (previstas como adenocarcinoma no pulmão ou ISUP 0 na próstata)? Pulmão: 197 lâminas nas 5 partes por centro de `pulmao_por_centro.py`, comparado ao ABMIL nas mesmas partes e sementes. Próstata: 600 biópsias do Radboud (treino) e 300 do Karolinska (teste), embeddings padronizados por centro, comparado ao ABMIL padronizado nas mesmas 5 sementes (0 a 4). Fixado antes de rodar (commit `db8b6ab`). Critérios: M1, pulmão por centro com AUC ≥ 0,85 e acurácia balanceada ≥ 0,75; M2 (pulmão), nas previstas como adenocarcinoma, suficiência na margem (20 de maior atenção do ramo da classe − 20 sorteados) > 0 com limite inferior do IC 95% > 0; M3 (próstata), o mesmo nas previstas como ISUP 0. Script: `Testes/Pipeline01/mil/mil_multiramo.py`.

| Órgão e modelo | Desempenho | Suficiência na margem, "por ausência" (IC 95%) | Suficiência na margem, classe "positiva" (IC 95%) |
|---|---|---|---|
| Pulmão, multi-ramo | AUC **0,945**, AB **0,878** | adeno (n = 96): **−1,92** (−3,23 a −0,64) | escamoso (n = 101): +5,90 (5,24 a 6,65) |
| Pulmão, ABMIL (comparador) | AUC 0,947, AB 0,893 | adeno (n = 95): −2,06 (−3,42 a −0,79) | escamoso (n = 102): +5,97 (5,35 a 6,69) |
| Próstata, multi-ramo padronizado | κ quadrático 0,721 (sem critério) | ISUP 0 (n = 39): **−3,05** (−3,73 a −2,41) | ISUP ≥ 1 (n = 261): +2,28 (1,92 a 2,66) |
| Próstata, ABMIL padronizado | κ quadrático 0,540 | ISUP 0 (n = 21): −2,09 (−2,66 a −1,56) | ISUP ≥ 1 (n = 279): +2,18 (1,89 a 2,48) |

- **M1 passou** (AUC 0,945 e acurácia balanceada 0,878 no pulmão por centro).
- **M2 não passou** (−1,92, IC −3,23 a −0,64, quase idêntico ao −2,06 do ABMIL) e **M3 não passou** (−3,05, IC −3,73 a −2,41; ABMIL −2,09).
- Sem critério: na próstata, o κ quadrático do multi-ramo padronizado ficou em 0,721 (ABMIL padronizado 0,540 nas mesmas sementes); é um número exploratório no conjunto de desenvolvimento do Karolinska (300 biópsias balanceadas), sujeito à confirmação no conjunto externo.

Leitura: dar um ramo de atenção para cada classe não resolve o comportamento de "classe por ausência"; o achado de suficiência negativa nessas lâminas não depende de a atenção ser única.

## Sementes do modelo de linguagem, grafo fixo no GAT-MIL e checagem semântica do texto (26–27/11)

**Sementes (critério R, commit `db8b6ab`; `prelaudo/secoes_sementes.py`).** O parágrafo do modelo foi gerado de novo com as sementes 1 e 2 (temperatura 0,2), além da 0. Documentos com número sem sustentação, somados nos 4 casos (órgão × idioma): Gemma 11 / 12 / 8, Llama 29 / 31 / 23 nas sementes 0 / 1 / 2. **R passou**: a diferença entre os modelos não depende da semente. Faixas por caso em `resultados/secoes_por_codigo/sementes.json`.

**GAT-MIL com grafo fixo (critério F, commit `0eed00e`; `mil/gat_grafo_fixo.py`).** Próstata, previstas como ISUP 0 (35): suficiência na margem com o grafo fixo −2,92 (IC −3,33 a −2,48), com o grafo refeito −2,74; remoção −3,37 e −3,85. Grupo positivo (265): +2,32 e +2,54. **F não passou**: a discordância entre a decomposição (+0,37 a favor do benigno) e as perturbações não vem de refazer o grafo. Com o multi-ramo (M3), a suficiência negativa na classe "por ausência" se mantém em três modelos.

**Checagem semântica (critério V, commits `be4c2da` e a correção do S1; `prelaudo/checagem_semantica.py`).** Sobre os parágrafos já gerados, sem rodar modelo de linguagem. S1: afirmação de predominância conferida contra a maior proporção dos campos. S2: aviso em região concordante refeito por frase (uma coordenada, expressão de discordância, sem negação). Correção depois da primeira execução, antes de registrar: o S1 pegava a primeira menção da classe na frase, e não a primeira depois da expressão, como definido.

| Parágrafos com S1 (predominância contraditória), sementes 0 / 1 / 2 | Pulmão pt | Pulmão en | Próstata pt | Próstata en |
|---|---|---|---|---|
| Gemma | 27 / 23 / 26 | 14 / 12 / 11 | 17 / 19 / 18 | 4 / 2 / 6 |
| Llama | 6 / 11 / 7 | 10 / 8 / 10 | 6 / 9 / 4 | 1 / 4 / 2 |

- **V passou**: S1 e S2 dão 0 no resumo do template nos 4 casos.
- S2 deu 0 em todos os parágrafos (teste sintético confirma que o detector dispara): a contagem antiga de "aviso em região concordante" no texto livre (12 a 53 por caso) era toda de frases com várias regiões juntas ou com negação.
- S1 pega o erro da Fig. 4 (TCGA-55-6987, "predominância de adenocarcinoma, 32,7%" com pulmão normal 66,7%) e outros do mesmo tipo ("predominant findings are Gleason 4, 20.7%" com 649 patches benignos). É um limite superior: falsos positivos conhecidos (vistos nos exemplos, regra não alterada) por flexão de gênero ("benigna" não casa com "benigno") e por frases sobre o peso das regiões, não sobre proporções. Exemplos em `resultados/checagem_semantica/exemplos.json`.

Leitura: o texto livre do modelo traz também erros de sentido que a checagem de existência não via, mais frequentes no Gemma (que escreve mais sobre proporções); o template não os tem. A medida antiga de aviso em região concordante no texto livre deve ser trocada pela S2.

## Remoção e suficiência no pulmão com a divisão por centro (27/11)

Pergunta, a partir da revisão 02: a Fig. 3 do pulmão (remoção e suficiência da atenção, na probabilidade) usava a divisão aleatória, que vaza o centro de origem; o padrão se mantém com a validação cruzada por centro? Mesmo teste de `remocao_atencao.py` nas 197 lâminas, nas 5 partes por centro de `pulmao_por_centro.py` (5 sementes; classe prevista igual à de `pulmao_centro` em 197/197). Fixado antes de rodar (commit `76f2b7e`). Critérios X1c e X2c (os mesmos X1 e X2). Script: `Testes/Pipeline01/mil/remocao_atencao_centro.py`.

| Diferença pareada (maior atenção − sorteio), IC 95% | Todas (197) | Previstas adenocarcinoma (95) | Previstas escamoso (102) |
|---|---|---|---|
| Remoção, 10% | **+0,200** (0,149 a 0,251) | −0,017 (−0,031 a −0,006) | +0,401 (0,322 a 0,486) |
| Suficiência, 20 patches | −0,032 (−0,090 a 0,025) | −0,267 (−0,347 a −0,187) | +0,186 (0,136 a 0,240) |

- **X1c passou** e **X2c não passou**, como na divisão aleatória (+0,120 e −0,091). O padrão por classe prevista se repete: nas previstas como adenocarcinoma, os patches de maior atenção sustentam a classe pior que sorteados (−0,267; antes −0,276).
- Leitura: o achado da "classe por ausência" no pulmão não vem da divisão aleatória contaminada. A Fig. 3 passa a usar esta divisão no pulmão.

## Próstata: teste externo do Karolinska e reexecução com um modelo único (27/11)

Perguntas da revisão 02: (1) o GAT-MIL padronizado foi escolhido olhando as 300 biópsias do Karolinska; ele se mantém em biópsias nunca usadas? (2) a padronização usa um lote artificialmente balanceado (50 por grau); como fica na distribuição natural e com lotes pequenos? (3) as tabelas misturavam execuções diferentes. Teste externo: 500 biópsias do Karolinska nunca usadas, sorteadas na distribuição natural (ISUP 0–5: 170 / 180 / 65 / 22 / 45 / 18; 0 falhas de download). Modelo congelado (GAT-MIL padronizado, sementes 0–4, treinado nas 600 do Radboud); as 300 antigas passam a se chamar desenvolvimento. Fixado antes de baixar (commit `2b2bfc0`). Critérios: K1, kappa quadrático ≥ 0,60 e AUC câncer ≥ 0,85 no externo com a padronização do lote inteiro; K2, com lotes de 25 biópsias, mediana do kappa ≥ kappa(lote inteiro) − 0,05. Scripts: `dados/panda/panda_externo_baixar.py`, `mil/panda/panda_externo.py`.

| | Desenvolvimento (300, balanceado) | Externo (500, natural), lote inteiro | Externo, só estatística do Radboud | Externo, multi-ramo |
|---|---|---|---|---|
| Kappa quadrático | 0,631 | **0,265** (0,183–0,345) | 0,280 | 0,361 |
| AUC câncer × benigno | 0,962 | 0,943 (0,922–0,961) | 0,896 | 0,937 |
| Sensibilidade (câncer) / especificidade (benigno) | 0,956 / 0,52 | 0,988 / 0,29 | 0,961 / 0,41 | 0,994 / 0,37 |
| Acurácia de grau exato | 0,443 | 0,378 | 0,396 | 0,402 |

- **K1 não passou**: no teste intocado, na distribuição natural, o kappa cai de 0,63 para 0,27. A detecção de câncer se mantém (AUC 0,94), mas a graduação não: das 170 biópsias benignas, só 50 são chamadas de benignas, e 89 viram ISUP 3 ou 4.
- **K2 passou**, mas sem valor prático: com lotes de 10, 25 e 50 biópsias, a mediana do kappa é 0,20, 0,26 e 0,24, perto do lote inteiro, que já é baixo. A padronização pelo centro novo não ajuda na distribuição natural (0,27 contra 0,28 só com o Radboud).
- Calibração: temperatura ajustada no desenvolvimento (4,47) e aplicada ao externo: ECE 0,325 → 0,041. Depois de calibrar, só 9 das 500 biópsias ficam na faixa "alta" (acerto 0,78).
- Multi-ramo padronizado (sem critério): 0,361 no externo, contra 0,721 no desenvolvimento.
- Leitura: o kappa de 0,65 do GAT-MIL padronizado foi otimista; o ganho da padronização dependia do lote balanceado do desenvolvimento, como a revisão apontou. O kappa depende da prevalência dos graus, então desenvolvimento e externo não se comparam diretamente, mas a especificidade e a acurácia exata também caem. No paper, a próstata passa a sustentar a detecção de câncer entre centros, não a graduação.

**Reexecução com um modelo único (r0; `prelaudo/prostata_r0.py`, mesmo commit).** Todas as etapas da próstata com o GAT-MIL padronizado da execução 0 (kappa 0,621 no desenvolvimento, 30 erros câncer × benigno): aviso × erro **E passou** (erro 14,9% com aviso × 3,8% sem, p = 0,0009); pré-laudos com avisos e regiões colados **F2 passou** em português e inglês (0 trocas, 0 avisos em região concordante, 0 números e coordenadas inventados no texto colado); seções pelo código **Q não passou** (como antes; Gemma pt 18 números sem sustentação, Llama pt 43). Células (N) com este modelo: **N passou** (seção seguinte). Checagem semântica nos parágrafos de r0 (etapa `checagem_semantica`, commit `92682ee`, sem rodar modelo de linguagem): S2 = 0; S1 em 18 / 6 parágrafos (Gemma pt / en) e 6 / 4 (Llama); V passou. Os critérios recalculados mantiveram o resultado anterior. Saídas em `resultados/{aviso_erro_r0, prelaudo_final_r0, secoes_por_codigo_r0, celulas_regioes_r0}`.

## Células nas regiões: pulmão (NP), próstata com o modelo único (N) e células dentro do laudo (T0) (27/11)

Perguntas da revisão 02 (item D): o CellViT dá dados com sentido também no pulmão, onde não há máscara? Com o modelo único da próstata, o resultado N se mantém? E as células podem entrar no laudo sem trazer erro?

- **Pulmão (critério NP, commit `1cac057`; `prelaudo/celulas_pulmao.py`).** As 78 lâminas dos pré-laudos foram baixadas de novo do GDC, uma por vez; só as janelas de 256 µm das 3 regiões foram guardadas (234 janelas, 0 falhas). Sem máscara, a referência é o classificador de patches: regiões chamadas de tumor (adenocarcinoma ou escamoso) × pulmão normal, nas regiões com ≥ 5 núcleos (198 × 30). Fração de núcleos neoplásicos: AUC **0,837** (IC 0,687–0,961); **NP passou**. Número de núcleos 0,785; área nuclear mediana 0,848. Medianas por padrão da região: escamoso 89% neoplásicos e área 46,0 µm²; adenocarcinoma 46% e 23,9 µm²; pulmão normal 20%, 20,5 núcleos e 19,8 µm².
- **Próstata com o modelo único (critério N, commit `2b2bfc0`; `prelaudo/prostata_r0.py`).** 900 regiões (561 reaproveitadas por coordenada idêntica, 339 segmentadas); 846 com rótulo claro na máscara (660 câncer, 186 benigno). Fração neoplásica: AUC **0,747** (0,708–0,782); **N passou** (antes 0,756). Número de núcleos 0,826 (antes 0,856); área 0,683 (antes 0,713). No câncer, só 6,9% dos núcleos são chamados de neoplásicos (mediana), como antes.
- **Células no laudo (critério T0, commit `04b799c`; `prelaudo/template_celulas.py`).** O template ganhou, abaixo de cada região, uma linha com o número de núcleos, a área mediana e os tipos, com a ressalva "tipos do CellViT sem retreino" (pasta nova `secoes_por_codigo/template_celulas/`). Nos 4 casos (órgão × idioma): 0 classes trocadas, 0 avisos em região concordante, 0 coordenadas inventadas, 0 números sem sustentação nas seções vindas dos campos, classe lida 138/138 por idioma; **T0 passou**. Os parágrafos do modelo de linguagem não mudaram (foram gerados sem as células).
- Execução: a GPU estava ocupada por outro projeto, então as primeiras 126 janelas do pulmão rodaram na CPU (fp32, ~20 s por janela) e as demais, e a próstata, na GPU depois de um reinício (fp16, ~1,4 s). O CellViT é o mesmo; a diferença numérica entre fp32 e fp16 não foi medida. Uma avaliação parcial (126 de 234 janelas) gerada por engano durante o reinício foi guardada à parte como `resumo_parcial_126_de_234_nao_usar.json` e não é usada.

Leitura: no pulmão, os tipos do CellViT acompanham o padrão da região (o escamoso tem núcleos maiores e quase todos chamados de neoplásicos); na próstata, número e área separam, mas os tipos não servem como contagem. As células agora entram no laudo pelo código, sem erro.

## Custo da pipeline num notebook (26/11)

Pergunta: quanto custa rodar a pipeline num computador comum, com GPU e só com CPU? Notebook com RTX 3050 Laptop (4 GB), i5-11400H (6 núcleos, 12 threads), 15,4 GB de RAM. 3 lâminas de teste do pulmão (464 MB a 2,9 GB; 11.760 a 31.066 patches de tecido; 2.000 sorteados), cada etapa cronometrada separadamente. Medição descritiva, sem critério; o que seria medido foi fixado antes (commit `57a2a59`), com duas correções antes de qualquer medida do modelo de linguagem (`edad449`: liberar a VRAM do PyTorch antes do Ollama; `f704763`: converter o UNI2-h na CPU). As tentativas anteriores falharam por falta de memória na GPU, duas delas porque outro projeto usava a GPU; esta rodou com a máquina ociosa (nenhum outro processo na GPU, carga < 3 por 5 minutos). Script: `Testes/Pipeline01/ferramentas/medir_recursos.py`.

| Etapa, por lâmina | GPU | Só CPU | Memória (pico) |
|---|---|---|---|
| 1. Tecido e grade de patches | 0,4–2,7 s | (mesmo) | — |
| 2. UNI2-h em 2.000 patches | 86, 130 e 92 s (mediana 92 s) | 30, 52 e 32 min (estimado por 64 patches; mediana 32 min) | GPU 1,7–2,65 GB |
| 3. MIL (5 ABMIL) | 0,03–0,06 s | 0,04–0,06 s | GPU 54 MB |
| 4. Classificador de patches (inclui treinar a logística no LungHist700) | 1,5–2,0 s | (mesmo) | — |
| 5. Gemma 3 4B (Q4_K_M), um laudo de ~300 tokens | 14,6 tokens/s (~21 s de geração; 100 s no total com o carregamento do modelo a partir do HD externo) | 9,1 tokens/s (~33 s de geração; 84 s no total) | GPU até 2,9 GB no total do nvidia-smi |
| Treino dos 5 ABMIL (119 lâminas, uma vez) | 107 s | — | — |

RAM do processo Python: pico de 5,2 GB.

- Por lâmina, com GPU: ~1,5 min do UNI2-h + poucos segundos do resto + ~20 s do modelo de linguagem (sem ele, com o template, ~1,5 min). Só com CPU: ~30 min do UNI2-h + ~0,5 min do modelo de linguagem. A etapa cara é a extração dos embeddings; MIL e classificador de patches são desprezíveis.
- A segunda lâmina ficou ~1,7× mais lenta que as outras na GPU e na CPU; coincidiu com um aviso de falta de memória no alocador do PyTorch às 14:48 (o processo seguiu). Numa tentativa anterior com a máquina livre (00:12, registro sobrescrito), as mesmas lâminas 2 e 3 deram ~76 s na GPU e ~52 s por 64 patches na CPU; a variação entre execuções é, portanto, de até ~1,7×.
- Problemas da medição do modelo de linguagem: o tempo total na GPU inclui carregar o modelo do HD externo, e só a velocidade de geração (tokens/s, medida pelo próprio Ollama) é limpa; a RAM do Ollama foi lida no processo servidor e não no processo que roda o modelo (38 MB, inválido); o pico de VRAM é o total do nvidia-smi e inclui o contexto CUDA do Python.

Leitura: a pipeline cabe num notebook com GPU de 4 GB, com ~2 min por lâmina; só com CPU é viável para poucas lâminas por dia (~30 min cada).

## Anotações oficiais do BRACS

- `.qpdata` lidas com o QuPath e exportadas pra GeoJSON: 387 de 387 lâminas; totais por classe iguais aos do artigo.
- A maioria é retângulo, não contorno da lesão (nas lâminas usadas: DCIS 160 de 208, IC 127 de 128). O rótulo é da região marcada.

Detalhes: `Testes/Pipeline01/notas/problemas_e_metrica.md`.

## Conclusões até aqui

1. O filtro de tecido funciona.
2. A escolha dos patches parecia inconsistente pela métrica de RoIs, mas, medindo pelos núcleos, os roteadores acham tumor em 86–88% dos patches escolhidos nas lâminas malignas (sorteio: 52%).
3. Comparar a imagem com frases (zero-shot) é o gargalo do estágio 3: fica no acaso no DCIS vs. IC, mesmo quando o embedding contém a informação.
4. Uma camada treinada em cima do UNI2-h separa DCIS de IC e generaliza pra outra instituição; no atípico, falta dado.
5. A medida dos núcleos separa DCIS de IC, mas os valores não são confiáveis: mesmo com a classificação de núcleos treinada no NuCLS (tumor 0,83 / 0,88), a medida não bate com a anotação (Spearman 0,35).
6. A pipeline roda de ponta a ponta até o pré-laudo, mas em lâminas novas (57 do teste oficial) chama 55 de 57 de malignas: acerta DCIS e IC (com a regra, 8/8 e 7/12) e erra quase todas as benignas e atípicas, ficando em 17 de 57 (rótulo oficial). A regra do componente invasivo ajuda no IC; o problema principal está nos estágios 2 e 3, que mandam evidência maligna de lâminas benignas e atípicas.
7. Tirar a decisão do modelo de linguagem e treinar o descritor com lâminas benignas como negativos leva o acerto de 17 para 29 de 57 lâminas (acurácia balanceada 0,42 → 0,51, rótulo oficial), e os patches falsos malignos nas lâminas benignas caem de 21% para 7%. Ainda está abaixo do publicado com MIL (0,52–0,56 contra 0,69 em 3 classes, comparação indicativa). Separar benigno de atípico no nível da lâmina continua sendo o ponto mais difícil.
8. Um MIL com atenção, treinado direto no rótulo de só 79 lâminas, supera tudo o que passa pelo descritor por patch: 38 de 57 lâminas (acurácia balanceada 0,63), e benigno × atípico sobe de AUC 0,58 para 0,78. É o caminho principal daqui pra frente; falta mais treino (379 lâminas) e confirmação nas 30 lâminas de teste não usadas.
9. A receita de classificação da lâmina (UNI2-h + MIL, mesma configuração), retreinada com lâminas de pulmão, funciona em outro órgão: no TCGA, adenocarcinoma × carcinoma escamoso, AUC 0,98 e acurácia balanceada 0,95 em 78 lâminas de teste, com lâminas de 20x e 40x. A tarefa é mais fácil que a da mama. No pulmão, o pré-laudo manteve os números e coordenadas fiéis (78 textos), mas o descritor por patch, treinado em outro conjunto (LungHist700), descreveu mal as regiões de maior atenção nas lâminas de adenocarcinoma (21 de 39), e o texto quase nunca aponta quando a região discorda do tipo sugerido (3 de 27).
10. Numa tarefa de graduação (próstata, PANDA, treino num centro e teste em outro), a mesma receita detecta câncer (AUC 0,94) mas não gradua (kappa 0,24, quase tudo vira ISUP 3). Dentro do mesmo centro gradua bem (kappa 0,78), então o problema principal é a troca de centro. Dar ao MIL a vizinhança dos patches (GAT-MIL) melhora a graduação nos dois cenários, muito entre centros (kappa 0,24 → 0,44) e pouco dentro do centro (0,78 → 0,81). Na mama (BRACS) a mesma ideia não ajudou (acurácia balanceada 0,63 → 0,60, sem diferença provada) e no pulmão empatou, com o grafo montado só sobre a amostra de patches. Padronizar os embeddings por centro (média e desvio dos patches do próprio centro, sem rótulo) leva o kappa entre centros a 0,54 (ABMIL) e 0,61 (GAT-MIL); normalizar a cor (Reinhard) não ajuda. A rede de grafos (pontos de interesse pela atenção, grafo local em cada ponto, rede dos pontos com distância) chega ao nível do GAT-MIL olhando só as janelas em volta dos pontos (entre centros, 0,44). No rim (TCGA-RCC, 3 subtipos), a receita funciona em hospitais que nunca viu (acurácia balanceada 0,95, AUC 0,99; no sorteio aleatório, 0,98). O pré-laudo continua fiel aos campos (60/60) e continua sem apontar regiões discordantes (1 de 35).
11. No dataset de pulmão do orientador (52 pacientes, adenocarcinoma × epidermoide), a receita acerta pelo campo de biópsia (acurácia balanceada 0,89, AUC 0,94), mas o núcleo isolado, que é o que a pasta de "citologia" contém (núcleos recortados da própria biópsia), fica no acaso, tanto com o UNI2-h (AUC 0,48) quanto com medidas clássicas de forma, cor e textura (0,60). O mesmo núcleo, com o tecido em volta (janela de 224 px, ~17% do campo), vai a AUC 0,86; com uma janela do tamanho de um recorte do campo, 0,95, igual ao campo inteiro por construção. A informação do subtipo está no contexto, não no núcleo.
12. O pré-laudo passa a apontar todas as regiões que contradizem a classe sugerida quando o aviso vem pronto nos campos, calculado por código: pulmão 27 de 27 documentos (antes 5) e próstata 35 de 35 (antes 11), sem falso alarme nos documentos sem discordância e com números, coordenadas e classe fiéis. O modelo ainda acrescenta avisos em regiões que não discordam (próstata, 9 de 60 documentos) e troca a classe da região em 3; a seção de avisos deve ser inserida por código, não redigida. Com a seção colada por código, os avisos espúrios e as trocas de classe somem (0 nos dois órgãos, em português e em inglês); em inglês, uma coordenada copiada errada fora da seção de avisos (1 de 284, pulmão) fez o critério do pulmão não passar.
13. A atenção do MIL é fiel ao modelo pelo teste de remoção nos dois órgãos (tirar os 10% de maior atenção derruba a probabilidade da classe prevista; tirar 10% sorteados não), mas no pulmão os 20 patches de maior atenção sustentam a classe pior do que 20 sorteados. A diferença está nas lâminas previstas como adenocarcinoma (e nas biópsias previstas como benignas): o MIL decide como um detector da classe "positiva", e nessas lâminas as regiões de maior atenção são as mais parecidas com a outra classe, não a evidência da classe prevista (hipótese, análise feita depois dos resultados).
14. O aviso de discordância marca os erros do MIL: nas lâminas com aviso o MIL erra mais, no pulmão (4 de 27 contra 0 de 51, todos os erros com aviso, inclusive 3 com confiança alta) e na próstata (câncer × benigno, 16% contra 6%, risco relativo 2,6). Com a lista de regiões também colada por código, o pré-laudo do pulmão fica sem nenhuma coordenada inventada nos dois idiomas. Na próstata, o GAT-MIL padronizado deixa de colapsar em ISUP 3 e a atenção dele cai no câncer em 91% das biópsias (ABMIL 76%); os pré-laudos feitos com ele passam no critério nos dois idiomas, sem aviso espúrio, classe trocada ou coordenada inventada. Com a classe lida do texto por código, a impressão bate com a decisão em todos os 276 pré-laudos finais. A atenção do GAT-MIL também passa nos testes de remoção e de suficiência (+0,310 e +0,124), com a mesma exceção das biópsias previstas como benignas.
15. Com outro modelo de linguagem (Llama 3.2 3B), a colagem por código mantém os avisos e as coordenadas certos e nenhuma classe trocada nos quatro casos, mas o critério passou só em dois: em português o Llama usa outros títulos de seção, e a colagem e a leitura da classe, que dependem do título, falham (a impressão escrita está certa em todos os laudos); em inglês na próstata ele escreve um número calculado (69%). As seções críticas devem ser montadas pelo código, não localizadas no texto do modelo.
16. Com todas as seções críticas montadas pelo código e o modelo escrevendo só o parágrafo de resumo, a classe lida fica certa em 552 de 552 laudos e nenhuma classe é trocada, mas o parágrafo livre ainda traz números sem sustentação (Gemma em 0 a 5 documentos por caso, Llama em 6 a 9) e o critério não passou em nenhum caso. Um template sem modelo de linguagem, do mesmo tamanho, passa por construção. A pipeline com divisão por centro de origem mantém a decisão do pulmão (AUC 0,947) e o aviso continua marcando os erros (16 de 21), mas como sinal de triagem não acrescenta à confiança do classificador; a discordância entre as 5 sementes é melhor na próstata (AUROC 0,913).
17. Pela decomposição exata da margem, nas lâminas previstas como adenocarcinoma os 20 patches de maior atenção têm contribuição líquida zero para a decisão (nas previstas como escamoso, 44% da soma) e, sozinhos, sustentam o adenocarcinoma pior que patches sorteados (−1,98 em logit). A atenção alta nessas lâminas não é evidência da classe prevista. Na próstata, nas biópsias previstas como benignas, os patches de maior atenção empurram a favor do benigno pela decomposição, mas falham nos testes de remoção e suficiência; as duas medidas discordam ali.
18. A pipeline inteira cabe num notebook com GPU de 4 GB (RTX 3050): ~2 min por lâmina, quase tudo na extração dos embeddings pelo UNI2-h (mediana 92 s em 2.000 patches, pico de 2,65 GB de VRAM); MIL e classificador de patches levam segundos, e o Gemma 3 4B gera um laudo a 14,6 tokens/s (~20 s). Só com CPU, ~30 min por lâmina.
19. Os dados de células do CellViT nas regiões de maior atenção têm sentido na próstata: a fração de núcleos neoplásicos separa regiões de câncer de benignas (AUC 0,756; o número de núcleos, 0,856), mas os tipos sem retreino não servem como contagem (mesmo no câncer, só 6% dos núcleos são chamados de neoplásicos). Número e área dos núcleos são os dados mais confiáveis para o laudo.
20. A confiança que vai no laudo é superconfiante (ECE 0,09 no pulmão e 0,28 na próstata; na próstata, "alta" acerta o grau exato em só 53%) e precisa ser calibrada; a escala de temperatura leva o ECE a 0,04 e 0,09. Separar o aviso tumoral do aviso de tecido normal não o torna mais preciso (pulmão, 29% × 18% de erro, p = 0,22).
21. Um aviso por padrão de Gleason incompatível com o grau previsto não marca mais erros de grau (57% × 58%), mas indica a direção do erro quando aparece (+0,9 grau com padrão mais alto, −1,75 com mais baixo). A proporção de padrões do classificador de patches cresce com a classe real, mas não é fração de tumor: na próstata, "benigno" domina até no ISUP 5.
22. A diferença de erros entre os modelos de linguagem não depende da semente (Gemma 8–12 documentos com número sem sustentação, Llama 23–31). A suficiência negativa da classe "por ausência" se mantém com atenção por classe e com o grafo fixo. Uma checagem semântica mostra que o texto livre também erra o sentido (predominância invertida, como no exemplo do paper), e que a contagem antiga de aviso em região concordante era falso positivo.
23. Refeitos com a divisão por centro, os testes de remoção e suficiência do pulmão repetem o padrão da divisão aleatória (remoção +0,20; suficiência −0,27 nas previstas como adenocarcinoma): o achado não vem do vazamento de centro.
24. Num teste externo intocado do Karolinska (500 biópsias, distribuição natural), o GAT-MIL padronizado mantém a detecção de câncer (AUC 0,94) mas não gradua (kappa 0,27, contra 0,63 no conjunto em que foi escolhido; especificidade 0,29); a padronização pelo centro novo não ajuda fora do lote balanceado. O kappa da próstata reportado antes era otimista. Com um modelo único, o aviso continua marcando erros (14,9% × 3,8%) e os pré-laudos colados continuam fiéis.
25. Um MIL com atenção por classe (multi-ramo, um ramo por classe) mantém o desempenho no pulmão por centro (AUC 0,945, acurácia balanceada 0,878; M1 passou), mas não resolve a "classe por ausência": a suficiência na margem continua negativa nas lâminas previstas como adenocarcinoma (−1,92; M2 não passou) e nas biópsias previstas como ISUP 0 (−3,05; M3 não passou). O achado não depende da atenção única. (Sem critério: κ quadrático 0,721 na próstata nas 300 de desenvolvimento, contra 0,540 do ABMIL padronizado.)
26. O CellViT dá dados com sentido nos dois órgãos: no pulmão, a fração de núcleos neoplásicos separa as regiões de tumor das de pulmão normal (AUC 0,84) e acompanha o padrão (escamoso com núcleos maiores); na próstata, com o modelo único, o resultado se mantém (0,75; número de núcleos 0,83). As linhas de células entram no laudo montado pelo código sem nenhum erro.
