# Datasets

Levantamento inicial de datasets públicos relevantes. Para cada um, **verificar antes de usar**: licença de uso, necessidade de credenciamento/cadastro, formato dos arquivos (imagens de campo/patch vs. *Whole Slide Images* gigapixel) e se há anotação textual (necessária para treino de VLM) ou apenas rótulos categóricos (úteis para avaliação, não para treino contrastivo/generativo).

> Links devem ser conferidos manualmente na Fase 2 (ver [04-metodologia.md](04-metodologia.md)) — páginas de datasets científicos mudam de endereço com frequência.

## Datasets multimodais (imagem + texto) — específicos para VLM

Estes são os mais diretamente relevantes para treinar ou avaliar um VLM, pois contêm pares imagem-texto.

| Dataset | Descrição | Observações |
|---|---|---|
| **Quilt-1M** | ~1M pares imagem-texto de histopatologia extraídos de vídeos educacionais (YouTube) e outras fontes | Um dos maiores datasets multimodais de patologia disponíveis publicamente; verificar licença de uso |
| **PathVQA** | Dataset de perguntas e respostas visuais (VQA) sobre imagens de patologia, derivado de livros-texto e recursos didáticos | Útil para avaliação de VQA |
| **ARCH** | Pares imagem-legenda extraídos de livros-texto e artigos científicos de patologia | Menor escala que Quilt-1M |
| **OpenPath** | Pares imagem-texto de patologia coletados de redes sociais (usado no treino do PLIP) | Verificar disponibilidade pública e termos de uso |

## Datasets de classificação/segmentação (rótulos categóricos)

Úteis como benchmark de avaliação (mesmo sem texto associado, servem para testar classificação zero-shot via prompts) ou para gerar dados de fine-tuning supervisionado.

| Dataset | Tipo de câncer / tecido | Tarefa | Fonte |
|---|---|---|---|
| **CAMELYON16 / CAMELYON17** | Linfonodo — metástase de câncer de mama | Detecção/classificação de metástase em WSI | camelyon16.grand-challenge.org / camelyon17.grand-challenge.org |
| **PatchCamelyon (PCam)** | Derivado do CAMELYON16, em patches | Classificação binária (tumor/normal) | Amplamente usado como benchmark leve |
| **BACH** (Breast Cancer Histology) | Mama | Classificação em 4 classes (normal, benigno, in situ, invasivo) | Grand Challenge |
| **BreakHis** | Mama | Classificação benigno/maligno, múltiplos níveis de ampliação | — |
| **NCT-CRC-HE-100K** | Colorretal | Classificação de tipos de tecido (9 classes) | — |
| **PANDA** (Prostate cANcer graDe Assessment) | Próstata | Graduação de Gleason / ISUP | Kaggle (kaggle.com/c/prostate-cancer-grade-assessment) |
| **TCGA** (The Cancer Genome Atlas) | Múltiplos tipos de câncer | WSI + dados clínicos/genômicos | GDC Data Portal (portal.gdc.cancer.gov) |

## Critérios para priorização

1. **Disponibilidade imediata** (sem processo de credenciamento demorado) — priorizar na Fase 2.
2. **Presença de texto associado** — obrigatório para qualquer etapa de treino/fine-tuning de VLM; datasets só-imagem servem para avaliação zero-shot via prompts fixos.
3. **Tamanho e diversidade** — cobertura de múltiplos tipos de câncer aumenta a validade das conclusões sobre generalização.
4. **Formato gerenciável** — WSI gigapixel exigem pipeline de *patching*; datasets já em patches (ex. PCam, NCT-CRC-HE-100K) reduzem a complexidade de engenharia na fase inicial.

## Checklist por dataset (preencher conforme avança a Fase 2)

- [ ] Link oficial conferido e funcional
- [ ] Licença de uso lida e compatível com o projeto
- [ ] Cadastro/credenciamento necessário? (sim/não, status)
- [ ] Tamanho total em disco
- [ ] Download realizado
- [ ] Exploração inicial feita (estatísticas, exemplos visualizados em notebook)
