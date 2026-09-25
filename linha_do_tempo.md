# Linha do tempo — IC VLMs na Oncologia

Estado em 25/09/2026. Datas tiradas do histórico de commits.

## Em uma frase

Estamos testando a **Pipeline Ideia 01**: transformar uma lâmina histopatológica gigante numa descrição textual curta que um modelo local pequeno consiga ler — filtrando o fundo, escolhendo os poucos patches que importam, descrevendo cada um em texto e deixando o modelo sintetizar. Os estágios 1 e 2 funcionam; o 3 (descrever o patch) travou num problema que ainda não resolvemos.

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

### Estágio 2 — roteador top-k (funciona)

| Data | O que foi feito |
|---|---|
| 13/09 | Roteador com **QuiltNet-B-32**: pontua os 15.138 tiles contra um banco de frases, escolhe os k melhores |
| 13/09 | Curva custo × fidelidade de k=8 até k=1024: acerta ~3x mais que o acaso (precisão 0,33–0,62 contra 0,18 aleatório) |
| 13/09 | Banco v2 (benigno vs. suspeito): troca de precisão por recall, não é melhora limpa |

Achado importante: cobrir mais de 80% dos RoIs exige k ≥ 512, que custa ~23 mil tokens — bem longe dos "~1–2k tokens" que o desenho original previa.

### Estágio 3 — descrever cada patch (travado)

| Data | O que foi feito |
|---|---|
| 13/09 | Descritor por patch: quase todos os patches recebem o **mesmo achado** ("high nuclear pleomorphism, mitotic figures") |
| 13/09 | Causa confirmada: viés de calibração do CLIP — algumas frases "ganham" sempre, independente da imagem |
| 13/09 | Estágio 4 (agregação) montado: mostrou que o "achado dominante" do pré-laudo muda completamente conforme a versão do estágio 3 usada |

### Tentativas de destravar o estágio 3

Teste: o achado do patch discrimina as classes reais do RoI (DCIS vs. IC)?

| Data | Tentativa | Resultado |
|---|---|---|
| 16/09 | Similaridade bruta | não discrimina |
| 16/09 | Normalização por z-score | não discrimina |
| 16/09 | Ensemble de prompts (sugestão do Prof. João) | não discrimina |
| 16/09 | Ensemble + normalização | não discrimina |
| 18/09 | Banco de frases por classe (critério diagnóstico real) | 23,9% de acurácia — pior que chutar sempre DCIS (80,2%) |
| 18/09 | Agregação de todos os patches do RoI | 27,6% — melhora marginal |
| 23/09 | **Agregação só pelos patches da borda do RoI** | **36,7%** — primeira melhora real (interior: 10%) |
| 23/09 | Trocar QuiltNet por KEEP (modelo mais forte) | **não concluído** — conflitos de versão (`timm`, `transformers`) |
| 25/09 | BRACS documentado na aba Datasets | — |

## Onde paramos

1. **Pergunta aberta principal:** por que nenhuma forma de descrever um patch isolado consegue separar DCIS de IC?
2. **Hipótese mais forte hoje:** a diferença entre DCIS e IC está na **borda** da lesão (camada mioepitelial intacta ou rompida), não na aparência da célula. Um patch do meio da lesão não carrega essa informação — o teste da borda (36,7% contra 10% do interior) apoia isso.
3. **Hipótese ainda não descartada:** o QuiltNet-B-32 é fraco demais. O teste com KEEP ficou pela metade.
4. **Problema de métrica registrado:** a classe é rótulo da lesão inteira, não do patch — ver `Testes/Pipeline01/estagio4teste/problemas_e_metrica.md`.

**Estado técnico a saber:** no venv de `Testes/Pipeline01/.venv` foram instalados `transformers==4.34.0` e `timm==1.0.17` na tentativa do KEEP. O QuiltNet não depende do `transformers`, mas vale conferir que ele ainda roda antes do próximo teste.

## O que precisa ser feito

**Pra fechar a pergunta do estágio 3:**

- [ ] Terminar o teste do KEEP — de preferência num venv separado, pra não quebrar o do QuiltNet
- [ ] Aprofundar a pista da borda: testar margens diferentes, pesar a borda em vez de usar só ela
- [ ] Implementar a hierarquia sugerida pelo Prof. João: primeiro benigno/maligno, depois a evidência

**Frentes paradas há mais tempo:**

- [ ] **Baseline zero-shot no PathVQA** — nunca começou; é o resultado mais rápido e comparável com outros artigos
- [ ] **Estágio 5** — rodar o prompt do estágio 4 numa VLM de verdade (MedGemma-4B ou similar)

**Limitações que afetam tudo:**

- [ ] Baixar mais lâminas do BRACS — hoje só há uma (`BRACS_748`), então nenhum resultado foi confirmado em outra amostra
- [ ] Responder ao Prof. João sobre o resultado do ensemble e da borda

## Onde está cada coisa

| O quê | Onde |
|---|---|
| Documentação pública | `docs/` (site MkDocs) |
| Descrição da Pipeline 01 | `docs/pipelines.md`, `Testes/Pipeline01/IDEIA01Pipeline.md` |
| Estágio 1 | `Testes/Pipeline01/estagio1/` |
| Estágio 2 | `Testes/Pipeline01/estagio2/` |
| Estágio 3 | `Testes/Pipeline01/estagio3/` |
| Estágio 4 | `Testes/Pipeline01/estagio4/` |
| Testes de validação do estágio 3 | `Testes/Pipeline01/estagio4teste/` |
| Caminhos da lâmina, RoIs e modelos | `Caminhos/caminhos.md` |
