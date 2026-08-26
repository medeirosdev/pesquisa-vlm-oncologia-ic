# Objetivos

## Objetivo geral

Investigar e aplicar Modelos de Visão e Linguagem (VLMs) como ferramenta de apoio ao pré-diagnóstico e à interpretação de exames histopatológicos oncológicos, avaliando seu potencial para ampliar (democratizar) o acesso a esse tipo de análise em contextos com escassez de patologistas especializados.

## Objetivos específicos

1. **Revisão bibliográfica sistemática** sobre VLMs em patologia computacional e diagnóstico assistido por IA em oncologia.
2. **Levantamento e caracterização de datasets públicos** de histopatologia, com e sem anotação textual, relevantes para treino/avaliação de VLMs.
3. **Avaliação baseline (zero-shot / few-shot)** de VLMs pré-treinados de propósito geral e específicos de patologia em tarefas de classificação e/ou VQA sobre imagens histopatológicas oncológicas.
4. **Adaptação de domínio (fine-tuning ou prompt-tuning)** de um VLM selecionado, quando os recursos computacionais e os dados disponíveis permitirem.
5. **Construção de um protótipo demonstrativo** (proof-of-concept) que ilustre o uso do modelo em um fluxo de pré-diagnóstico assistido (ex.: interface simples de upload de imagem + resposta do modelo).
6. **Análise crítica de desempenho, limitações e vieses**, incluindo variação por tipo de tecido/câncer, origem dos dados de treino, e implicações éticas do uso desse tipo de ferramenta como apoio (não substituto) ao diagnóstico humano.

## Fora de escopo

- Validação clínica ou regulatória do sistema.
- Uso do protótipo com dados de pacientes reais fora de datasets públicos/anonimizados.
- Treinamento de um VLM do zero (foco em adaptação/avaliação de modelos pré-treinados, dado o custo computacional).
