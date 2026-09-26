# Linha do tempo — IC VLMs na Oncologia

Estado em 25/09/2026. Datas tiradas do histórico de commits.

## Em uma frase

Estamos testando a **Pipeline Ideia 01**: transformar uma lâmina histopatológica gigante numa descrição textual curta que um modelo local pequeno consiga ler — filtrando o fundo, escolhendo os poucos patches que importam, descrevendo cada um em texto e deixando o modelo sintetizar. Desde 25/09 tudo roda em 8 lâminas do BRACS, não só uma. O estágio 1 se confirma nas 8; o roteador (estágio 2) só funciona em lâmina maligna; o descritor (estágio 3) agora consegue dizer "benigno" e fica acima do acaso (53% nas 8 lâminas novas, contra 33%), mas ainda confunde maligno com atípico.

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

### 25/09 — várias lâminas e reorganização

| Data | O que foi feito |
|---|---|
| 25/09 | Baixadas 7 lâminas do BRACS pelo FTP oficial (uma por classe: N, PB, UDH, FEA, ADH, DCIS, IC) + as anotações `.qpdata` originais |
| 25/09 | `Testes/Pipeline01` reorganizado: uma pasta por estágio, código compartilhado em `comum/`, resultados por lâmina em `resultados/` |
| 25/09 | Scripts corrigidos pra lâminas com pirâmide diferente (nível escolhido pelo fator de redução, não pela posição) |
| 25/09 | Pipeline inteira rodada nas 8 lâminas — ver `Testes/Pipeline01/resultados_multilaminas.md` |
| 25/09 | Estágio 1 se confirma nas 8 (cobertura dos RoIs entre 74% e 100%; a exceção, 38% na lâmina normal, é efeito da caixa retangular em volta de um lóbulo pequeno) |
| 25/09 | Estágio 2 **não** se confirma: só fica claramente acima do acaso na lâmina de DCIS — o banco procura "suspeito", não acha lesão benigna/atípica |
| 25/09 | Estágio 3: descritor só tinha frases suspeitas (descrevia tecido normal como "stromal invasion"). Banco refeito com o espectro inteiro (benigno / atípico / maligno) |
| 25/09 | Resultado do descritor novo nas 8 lâminas: acerta a categoria em 51% (acaso = 33%) — benigno 65%, atípico 53%, maligno 33%. Normalização por z-score descartada (fica no acaso) |
| 25/09 | Pista da borda **não** se repete de forma consistente nas outras lâminas (poucos RoIs por lâmina, 2 a 16) |
| 25/09 | Viés pró-"benigno": tirar a frase genérica "normal breast tissue" piorou (51% → 45%), revertido. O atrator real era "normal terminal duct lobular unit" (o DCIS cresce dentro de lóbulos) |
| 25/09 | Frase do lóbulo trocada por "normal lobule with open lumina and two cell layers": média 52%, maligno 33% → 43%, benigno 65% → 52%. Erro que sobra: maligno → atípico |
| 25/09 | Mesmo truque nas outras frases, uma de cada vez (14 testadas, regra de aceite fixada antes: média +0,5 ponto). 2 aceitas: média 52% → 56,5%, maligno 43% → 59%, atípico 61% → 57%. Reescrever o nome da própria classe piorou. Ver `Testes/Pipeline01/validacao/experimento_frases.md` |
| 25/09 | Baixadas mais 8 lâminas (uma por classe + uma N extra), de pacientes que não aparecem na primeira leva — 16 lâminas no total |
| 25/09 | `recall_roi.py` passa a escolher a escala recorte → lâmina (na `BRACS_297` o nível 0 tem o dobro da resolução dos recortes; 0/31 → 31/31 RoIs localizados) |
| 25/09 | Teste fora da amostra, nas 8 lâminas novas: a troca do lóbulo se confirma (44,8% → 53,2%); as 2 trocas do experimento frase a frase não (53,2% → 52,7%) e foram retiradas |

## Onde paramos

1. **O descritor separa benigno / atípico / maligno acima do acaso: 53% em 8 lâminas que não foram usadas pra escolher as frases (acaso = 33%).** Só a troca da frase do lóbulo se sustentou fora da amostra; o atípico é a categoria mais fraca nas lâminas novas (41%). O erro que sobra é maligno chamado de atípico — de novo uma questão de arquitetura (ducto inteiro preenchido ou não).
2. **O roteador só funciona em lâmina maligna.** Numa lâmina benigna ou atípica ele escolhe patches no nível do acaso.
3. **DCIS vs. IC continua sem solução**, e a pista da borda, que funcionou na `BRACS_748`, não se repetiu nas outras lâminas.
4. **O QuiltNet-B-32 pode ser fraco demais** — o teste com KEEP ficou pela metade.
5. **Problema de métrica registrado:** a classe é rótulo da lesão inteira, não do patch — ver `Testes/Pipeline01/validacao/problemas_e_metrica.md`. As anotações `.qpdata` recém-baixadas têm o contorno real das lesões, mas precisam do QuPath pra serem lidas.

**Estado técnico a saber:** no venv de `Testes/Pipeline01/.venv` foram instalados `transformers==4.34.0` e `timm==1.0.17` na tentativa do KEEP. Conferido em 25/09: o QuiltNet continua rodando.

## O que precisa ser feito

**Estágios 2 e 3:**

- [x] Reduzir o viés pró-"benigno" do descritor — maligno de 33% pra 43% trocando a frase do lóbulo normal
- [ ] Reduzir a confusão maligno → atípico (medido com `validacao/categoria_descritor.py`) — se repete nas lâminas novas
- [x] Conferir o banco de frases em lâminas que não foram usadas pra escolhê-las — 8 lâminas novas; só a troca do lóbulo se sustentou
- [ ] Roteador que funcione também em lâmina benigna/atípica (hoje o banco v2 só procura "suspeito")
- [ ] Terminar o teste do KEEP — de preferência num venv separado, pra não quebrar o do QuiltNet
- [ ] Implementar a hierarquia sugerida pelo Prof. João: primeiro benigno/maligno, depois a evidência — o descritor por categoria já é um primeiro passo nessa direção
- [ ] Ler as anotações `.qpdata` (via QuPath) pra ter o contorno real das lesões em vez de caixas

**Frentes paradas há mais tempo:**

- [ ] **Baseline zero-shot no PathVQA** — nunca começou; é o resultado mais rápido e comparável com outros artigos
- [ ] **Estágio 5** — rodar o prompt do estágio 4 numa VLM de verdade (MedGemma-4B ou similar)

**Limitações que afetam tudo:**

- [x] Baixar mais lâminas do BRACS — 16 lâminas desde 25/09, duas por classe (três N)
- [ ] Mais lâminas por classe — com 2 lâminas por classe, e 2 a 16 RoIs em várias delas, os números por lâmina ainda são pequenos
- [ ] Responder ao Prof. João sobre o ensemble, a borda e os resultados em várias lâminas

## Onde está cada coisa

| O quê | Onde |
|---|---|
| Documentação pública | `docs/` (site MkDocs) |
| Como rodar os testes, estrutura das pastas | `Testes/Pipeline01/README.md` |
| Descrição da Pipeline 01 | `docs/pipelines.md`, `Testes/Pipeline01/ideia/` |
| Código compartilhado | `Testes/Pipeline01/comum/` |
| Estágios 1 a 4 | `Testes/Pipeline01/estagio1_filtro_tecido/` … `estagio4_agregacao/` |
| Testes de validação do estágio 3 | `Testes/Pipeline01/validacao/` |
| Resultados em todas as lâminas | `Testes/Pipeline01/resultados_multilaminas.md` |
| Baixar lâminas, rodar tudo | `Testes/Pipeline01/scripts/` |
| Caminhos das lâminas, RoIs e modelos | `Caminhos/caminhos.md` |
