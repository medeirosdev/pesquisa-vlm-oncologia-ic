# Linha do tempo — IC VLMs na Oncologia

Estado em 13/10/2026. Datas tiradas do histórico de commits. Resultados de todos os testes, com números e critérios: [resultados.md](resultados.md).

## Em uma frase

Estamos testando a **Pipeline Ideia 01**: transformar uma lâmina histopatológica gigante numa descrição textual curta que um modelo local pequeno consiga ler — filtrando o fundo, escolhendo os poucos patches que importam, descrevendo cada um em texto e deixando o modelo sintetizar. Tudo roda em 16 lâminas do BRACS (duas levas de 8, pacientes diferentes), mais 2 lâminas com DCIS e IC juntos e um dataset de outra instituição (BACH). O estágio 1 funciona; o estágio 2 (escolha dos patches) fica em média no dobro do acaso, mas é inconsistente entre lâminas; no estágio 3, o zero-shot com frases fica em 53% nas categorias e no acaso no DCIS vs. IC, enquanto uma camada treinada em cima do UNI2-h separa DCIS de IC com AUC 0,95–0,99, inclusive em outra instituição.

## Linha do tempo

### Agosto — estrutura e direção

| Data | O que foi feito |
|---|---|
| 25/08 | Repositório criado, site MkDocs publicado via GitHub Pages |
| 28/08 | Abas Datasets (PathVQA como principal), Modelos Locais (catálogo de modelos pequenos) e Metodologia |
| — | Direção definida com o Prof. João: modelos **locais e eficientes**, por privacidade dos dados de saúde e pra rodar em hardware modesto |

### Início de setembro — a pipeline

| Data | O que foi feito |
|---|---|
| 01/09 | Abas Conceitos (quantização) e Questões; primeira versão da Pipeline Ideia 01 |
| 02/09 | Pipeline reescrita em 5 estágios: filtro de tecido → roteador top-k → descritores → agregação → síntese na VLM |
| 02/09 | Primeiro teste real: 6 filtros de tecido na lâmina `BRACS_748.svs` |

### Estágio 1 — filtro de tecido (resolvido)

| Data | O que foi feito |
|---|---|
| 11/09 | Métrica "% de tecido" trocada por **recall contra os 98 RoIs anotados** — a primeira não tinha verdade de campo |
| 11/09 | Resultado: 98/98 RoIs cobertos, 96% de cobertura média. Estágio **congelado** (Otsu na saturação + morfologia) |

A lâmina tinha 41.001 tiles; o filtro manteve 15.138 (descartou 63% da área, praticamente todo fundo e estroma sem epitélio).

### Estágio 2 — roteador top-k (primeira lâmina)

| Data | O que foi feito |
|---|---|
| 13/09 | Roteador com **QuiltNet-B-32**: pontua os 15.138 tiles contra um banco de frases, escolhe os k melhores |
| 13/09 | Curva custo × fidelidade de k=8 até k=1024 na `BRACS_748`: acerta ~3x mais que o acaso (precisão 0,33–0,62 contra 0,18 aleatório) |
| 13/09 | Banco v2 (benigno vs. suspeito): troca de precisão por recall, não é melhora limpa |

Achado importante: cobrir mais de 80% dos RoIs exige k ≥ 512, que custa ~23 mil tokens — bem longe dos "~1–2k tokens" que o desenho original previa. (Em várias lâminas, depois, o roteador se mostrou inconsistente — ver 25/09 e 26/09.)

### Estágio 3 — descrever cada patch (primeira lâmina)

| Data | O que foi feito |
|---|---|
| 13/09 | Descritor por patch: quase todos os patches recebem o **mesmo achado** ("high nuclear pleomorphism, mitotic figures") |
| 13/09 | Causa confirmada: viés de calibração do CLIP — algumas frases "ganham" sempre, independente da imagem |
| 13/09 | Estágio 4 (agregação) montado: mostrou que o "achado dominante" do pré-laudo muda completamente conforme a versão do estágio 3 usada |

### Tentativas de destravar o estágio 3 (DCIS vs. IC na `BRACS_748`)

| Data | Tentativa | Resultado |
|---|---|---|
| 16/09 | Similaridade bruta | não discrimina |
| 16/09 | Normalização por z-score | não discrimina |
| 16/09 | Ensemble de prompts (sugestão do Prof. João) | não discrimina |
| 16/09 | Ensemble + normalização | não discrimina |
| 18/09 | Banco de frases por classe (critério diagnóstico real) | 23,9% de acurácia — pior que chutar sempre DCIS (80,2%) |
| 18/09 | Agregação de todos os patches do RoI | 27,6% — melhora marginal |
| 23/09 | Agregação só pelos patches da borda do RoI | 36,7% — melhora (interior: 10%); não se repetiu depois em outras lâminas |
| 23/09 | Trocar QuiltNet por KEEP (modelo mais forte) | **não concluído** — conflitos de versão (`timm`, `transformers`) |

### 25/09 — várias lâminas, reorganização e banco de frases

| Data | O que foi feito |
|---|---|
| 25/09 | BRACS documentado na aba Datasets |
| 25/09 | Baixadas 7 lâminas do BRACS pelo FTP oficial (uma por classe: N, PB, UDH, FEA, ADH, DCIS, IC) + as anotações `.qpdata` originais |
| 25/09 | `Testes/Pipeline01` reorganizado: uma pasta por estágio, código compartilhado em `comum/`, resultados por lâmina em `resultados/` |
| 25/09 | Scripts corrigidos pra lâminas com pirâmide diferente (nível escolhido pelo fator de redução, não pela posição) |
| 25/09 | Pipeline inteira rodada nas 8 lâminas — ver `Testes/Pipeline01/resultados_multilaminas.md` |
| 25/09 | Estágio 1 se confirma nas 8 (cobertura dos RoIs entre 74% e 100%; a exceção, 38% na lâmina normal, é efeito da caixa retangular em volta de um lóbulo pequeno) |
| 25/09 | Estágio 2 nas 8: só claramente acima do acaso na lâmina de DCIS |
| 25/09 | Estágio 3: descritor só tinha frases suspeitas (descrevia tecido normal como "stromal invasion"). Banco refeito com o espectro inteiro (benigno / atípico / maligno) |
| 25/09 | Resultado do descritor novo nas 8 lâminas: acerta a categoria em 51% (acaso = 33%) — benigno 65%, atípico 53%, maligno 33%. Normalização por z-score descartada (fica no acaso) |
| 25/09 | Pista da borda **não** se repete de forma consistente nas outras lâminas (poucos RoIs por lâmina, 2 a 16) |
| 25/09 | Viés pró-"benigno": tirar a frase genérica "normal breast tissue" piorou (51% → 45%), revertido. O atrator real era "normal terminal duct lobular unit" (o DCIS cresce dentro de lóbulos) |
| 25/09 | Frase do lóbulo trocada por "normal lobule with open lumina and two cell layers": média 52%, maligno 33% → 43%, benigno 65% → 52% |
| 25/09 | Mesmo truque nas outras frases, uma de cada vez (14 testadas, regra fixada antes: média +0,5 ponto). 2 aceitas: média 52% → 56,5%. Reescrever o nome da própria classe piorou. Ver `Testes/Pipeline01/validacao/experimento_frases.md` |
| 25/09 | Baixadas mais 8 lâminas (uma por classe + uma N extra), de pacientes que não aparecem na primeira leva — 16 lâminas no total |
| 25/09 | `recall_roi.py` passa a escolher a escala recorte → lâmina (na `BRACS_297` o nível 0 tem o dobro da resolução dos recortes; 0/31 → 31/31 RoIs localizados) |
| 25/09 | Teste fora da amostra, nas 8 lâminas novas: a troca do lóbulo se confirma (44,8% → 53,2%); as 2 trocas do experimento frase a frase não (53,2% → 52,7%) e foram retiradas |
| 25/09 | Estágios 1 e 2 nas lâminas novas: filtro se confirma (cobertura 83–99%). Roteador acima do acaso em 4 das 8 novas, sem padrão por classe — a conclusão "só funciona em lâmina maligna" não se sustenta |
| 25/09 | DCIS vs. IC com os 8 vizinhos do patch (média dos embeddings 3×3): ganho pequeno (na `BRACS_748`, 52% → 55,5%; 5×5: 58%), só no IC |
| 25/09 | DCIS vs. IC com os vizinhos como contexto (tipo de tecido em volta): na `BRACS_748` o IC está cercado de tumor (77%), o contrário da hipótese; a relação não se repete entre lâminas |

### 26/09 — núcleos (CellViT), UNI2-h e anotações

| Data | O que foi feito |
|---|---|
| 26/09 | Hipótese "tumor cercado de tumor → IC" em 2 lâminas novas com DCIS e IC (`BRACS_773`, `BRACS_295`), regra fixada antes do download: passa no critério (+3 e +6 pontos), mas o efeito é fraco (~55%) e o limiar não transfere entre lâminas |
| 26/09 | CellViT-256 instalado (ambiente separado no HD). DCIS vs. IC pela fração de núcleos neoplásicos encostados em conjuntivos (≤ 20 µm), fixada antes: AUC 0,72 / 0,84 / 0,66, contra 0,50 / 0,58 / 0,50 do QuiltNet nos mesmos tiles |
| 26/09 | UNI2-h baixado. Teste 1 (DCIS vs. IC, treina em 2 lâminas e testa na 3ª): UNI2-h + logística AUC 0,96 / 0,96 / 0,99; QuiltNet + a mesma logística 0,83 / 0,95 / 0,84. O gargalo era comparar a imagem com texto |
| 26/09 | Teste 2 (benigno / atípico / maligno, 16 lâminas, treina em 15): 55,2% nas 8 novas contra 53,2% das frases — dentro do ruído (controle embaralhado: 42%). Maligno 93%, atípico 17% |
| 26/09 | Teste 3 (UNI2-h + núcleos juntos, DCIS vs. IC): não acrescenta nada |
| 26/09 | Ensemble de frases refeito com as métricas atuais: DCIS vs. IC continua perto do acaso (0,54–0,57); categorias sem mudança (52,7% contra 53,2%). Não passou |
| 26/09 | Anotações `.qpdata` lidas com o QuPath (via `paquo`) e exportadas pra GeoJSON, 387 de 387 lâminas. Totais por classe batem com o artigo, mas a maioria é o próprio retângulo — o rótulo do BRACS é da região. Push dos commits pro GitHub |
| 26/09 | Roteador com UNI2-h (1 − P(benigno)), métrica só com RoIs de lesão: não passou — precisão@32 média 0,20 contra 0,21 do atual (sorteio 0,11), vence em 4 de 11 lâminas |

### 27/09 a 30/09 — generalização e validação dos núcleos

| Data | O que foi feito |
|---|---|
| 27/09 | Teste 4: classificador DCIS vs. IC treinado só no BRACS, aplicado sem retreino no BACH (Portugal): UNI2-h AUC 0,95 por imagem — generaliza. QuiltNet + logística cai pra 0,57; núcleos 0,63 |
| 30/09 | Validação do método 3 no NuCLS (núcleos anotados por patologista), pergunta do Prof. João: o CellViT acha 82–93% dos núcleos, mas chama só 46% do tumor de neoplásico e mais da metade do seu "conjuntivo" é linfócito ou tumor. A medida não bate com a dos anotadores (Spearman 0,28, viés +0,24). Os valores do método 3 não são confiáveis como número |
| 30/09 | Método 3, segunda versão: classificação do tipo de núcleo treinada no NuCLS (5 folds, hospitais separados). Tumor: sensibilidade 0,46 → 0,83, valor preditivo 0,88. Mas o "conjuntivo" ainda erra metade e a medida não passa (Spearman 0,35, viés +0,16) |

### Outubro — descritor hierárquico e estágio 2

| Data | O que foi feito |
|---|---|
| 13/10 | Caminhos do HD passam a ser descobertos pelo rótulo do volume (o sistema montou o HD como `HD 1TB1`; funciona com os dois nomes). UNI2-h vai pra GPU já em meia precisão |
| 13/10 | Descritor hierárquico com UNI2-h (sugestão do Prof. João: categoria → DCIS/IC → texto por tabela fixa): 55,8% nas 4 classes finais (18 lâminas, lâmina de fora), contra 42,3% da mesma hierarquia com frases. DCIS 16% → 78%, IC 50% → 74%; atípico 46% → 14% |

## Onde paramos

1. **Estágio 1 resolvido:** cobertura dos RoIs de 74–100% nas 16 lâminas.
2. **Estágio 2 inconsistente:** os dois roteadores (frases e UNI2-h) escolhem em média o dobro de patches em lesão do que o sorteio, mas nenhum ganha de forma consistente. A métrica é limitada: os RoIs não marcam toda a lesão.
3. **Estágio 3, benigno / atípico / maligno:** ~53–55% nas lâminas novas (acaso = 33%), com zero-shot ou com UNI2-h; o atípico é o ponto fraco.
4. **Estágio 3, DCIS vs. IC:** com treino, o UNI2-h separa bem (0,96–0,99 no BRACS, 0,95 no BACH). O QuiltNet com treino parecia bom no BRACS mas não generaliza (0,57 no BACH). O zero-shot com frases fica no acaso.
5. **Método 3 (núcleos):** tem sinal pra separar DCIS de IC, mas os valores da medida não são confiáveis (validação no NuCLS). Treinar a classificação no NuCLS resolveu o tipo do tumor (0,83 / 0,88), mas não a medida (Spearman 0,35): o erro no "conjuntivo" e a própria construção da medida (um vizinho errado já conta) seguram o resultado.
6. **Problema de métrica registrado:** o rótulo do BRACS é da região marcada, não do patch; a maioria das anotações oficiais é retângulo — ver `Testes/Pipeline01/validacao/problemas_e_metrica.md`.

**Estado técnico a saber:**
- Venv do projeto (`Testes/Pipeline01/.venv`): QuiltNet e UNI2-h; `transformers==4.34.0` e `timm==1.0.17` instalados na tentativa do KEEP.
- CellViT: ambiente separado no HD (`/media/medeiros/HD 1TB/venvs/cellvit`, exige numpy < 2); pesos em `Modelos/cellvit/` (Zenodo 15094831).
- QuPath/paquo: ambiente separado no HD (`venvs/paquo`), QuPath 0.5.1 em `Modelos/qupath/`.
- UNI2-h: pesos em `Modelos/UNI2H/pytorch_model.bin`.
- GPU de 4 GB: UNI2-h e QuiltNet não cabem juntos com o desktop aberto — rodar um de cada vez.

## O que precisa ser feito

**Estágios 2 e 3:**

- [x] Reduzir o viés pró-"benigno" do descritor — maligno de 33% pra 43% trocando a frase do lóbulo normal
- [ ] Reduzir a confusão maligno → atípico — se repete nas lâminas novas
- [x] Conferir o banco de frases em lâminas que não foram usadas pra escolhê-las — só a troca do lóbulo se sustentou
- [ ] Repensar o estágio 2: checar com o CellViT se os patches escolhidos têm tumor (métrica sem RoI); ou classificar todos os patches com o UNI2-h e escolher os de maior confiança por categoria
- [ ] Terminar o teste do KEEP — de preferência num venv separado
- [x] Implementar a hierarquia sugerida pelo Prof. João — `estagio3_descritores/descritor_uni.py`: 55,8% contra 42,3% das frases nas 4 classes finais
- [x] Ler as anotações `.qpdata` (via QuPath) — maioria é retângulo; contorno livre sobretudo no UDH
- [ ] Usar os contornos livres (UDH, parte do FEA/ADH) pra rotular melhor o atípico
- [x] Descritor do estágio 3 com a saída do classificador em texto (tabela fixa rótulo → nome) — junto com a hierarquia
- [ ] Rodar o descritor hierárquico em todas as lâminas e passar pro estágio 4

**Núcleos (método 3):**

- [x] Instalar o CellViT e testar "núcleos neoplásicos encostados em conjuntivo" — AUC 0,72 / 0,84 / 0,66 em 3 lâminas
- [x] Validar contra núcleos anotados (NuCLS) — os valores não são confiáveis (Spearman 0,28)
- [x] Treinar a classificação do tipo de núcleo no NuCLS (divisão treino/teste oficial) e medir de novo — tumor ficou bom (0,83 / 0,88); medida não passou (Spearman 0,35)
- [ ] Decidir o papel do método 3: medida mais robusta (ex.: contar só tumor com vários vizinhos de estroma, ou distância média ao estroma) testada no NuCLS, ou usar os núcleos só como sinal e não como número no texto
- [ ] Confirmar a medida em outras lâminas com DCIS e IC juntos

**Plano UNI2-h (26/09):**

- [x] Teste 1 — DCIS vs. IC: UNI2-h 0,96 / 0,96 / 0,99; QuiltNet + logística 0,83 / 0,95 / 0,84
- [x] Teste 2 — benigno / atípico / maligno: 55,2% nas 8 novas, dentro do ruído; maligno 93%, atípico 17%
- [x] Teste 3 — UNI2-h + núcleos juntos: não acrescenta
- [x] Teste 4 — generalização (BACH): UNI2-h 0,95; QuiltNet 0,57; núcleos 0,63

**Frentes paradas há mais tempo:**

- [ ] **Baseline zero-shot no PathVQA** — nunca começou; é o resultado mais rápido e comparável com outros artigos
- [ ] **Estágio 5** — rodar o prompt do estágio 4 numa VLM de verdade (MedGemma-4B ou similar)

**Limitações que afetam tudo:**

- [x] Baixar mais lâminas do BRACS — 16 lâminas + 2 com DCIS e IC juntos
- [ ] Mais lâminas por classe — com 2 lâminas por classe, os números por lâmina ainda são pequenos
- [x] Responder ao Prof. João sobre o ensemble, a borda e os resultados em várias lâminas — rascunho em `rascunhos/` (não versionado)

## Onde está cada coisa

| O quê | Onde |
|---|---|
| **Resultados de todos os testes** | [resultados.md](resultados.md) |
| Documentação pública | `docs/` (site MkDocs) |
| Como rodar os testes, estrutura das pastas | `Testes/Pipeline01/README.md` |
| Descrição da Pipeline 01 | `docs/pipelines.md`, `Testes/Pipeline01/ideia/` |
| Código compartilhado | `Testes/Pipeline01/comum/` |
| Estágios 1 a 4 | `Testes/Pipeline01/estagio1_filtro_tecido/` … `estagio4_agregacao/` |
| Testes de validação | `Testes/Pipeline01/validacao/` |
| Detalhes de cada teste do estágio 3 | `Testes/Pipeline01/estagio3_descritores/resultados.md` |
| Resultados por lâmina (gerado) | `Testes/Pipeline01/resultados_multilaminas.md` |
| Baixar lâminas, rodar tudo, exportar anotações | `Testes/Pipeline01/scripts/` |
| Caminhos das lâminas, RoIs e modelos | `Caminhos/caminhos.md` |
| Núcleos segmentados (CellViT) | `Testes/Pipeline01/resultados/<lamina>/nucleos/` |
| Datasets externos | HD: `Dados Gerais/BACH`, `Dados Gerais/NuCLS`; anotações do BRACS em `BRACS/anotacoes/geojson` |
