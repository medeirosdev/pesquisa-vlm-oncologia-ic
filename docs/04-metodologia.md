# Metodologia

O projeto está organizado em fases sequenciais, com algumas sobreposições esperadas. Cada fase está associada a um item do [cronograma](06-cronograma.md).

## Fase 1 — Revisão bibliográfica e fundamentação teórica

- Levantar literatura sobre VLMs (arquiteturas contrastivas e generativas) e sobre patologia computacional.
- Mapear modelos de fundação já aplicados à patologia digital (ver [02-fundamentacao-teorica.md](02-fundamentacao-teorica.md)).
- Organizar referências em gerenciador bibliográfico (Zotero/Mendeley) — consolidar em [07-referencias.md](07-referencias.md).
- **Entregável:** documento de revisão bibliográfica (pode compor a introdução do relatório final).

## Fase 2 — Levantamento de datasets e infraestrutura

- Identificar, documentar e avaliar viabilidade de acesso aos datasets listados em [05-datasets.md](05-datasets.md).
- Verificar licenças de uso e requisitos de credenciamento (alguns datasets médicos exigem cadastro/aprovação).
- Definir ambiente computacional (GPU local, Google Colab, cluster institucional, créditos cloud).
- Configurar ambiente de desenvolvimento (`requirements.txt`, controle de versão de dados quando aplicável).
- **Entregável:** pelo menos 1–2 datasets baixados/acessíveis e explorados (estatísticas descritivas, exemplos visualizados).

## Fase 3 — Avaliação baseline (zero-shot / few-shot)

- Selecionar 2–3 VLMs pré-treinados para comparação (ex.: um modelo geral tipo CLIP, e um ou mais modelos específicos de patologia, se disponíveis publicamente).
- Definir tarefas de avaliação (classificação de tipo de tecido/malignidade, VQA, retrieval).
- Rodar avaliação zero-shot e registrar métricas (ver métricas em [02-fundamentacao-teorica.md](02-fundamentacao-teorica.md)).
- **Entregável:** tabela comparativa de desempenho baseline entre modelos e tarefas.

## Fase 4 — Adaptação de domínio

- Com base nos resultados da Fase 3, decidir estratégia de adaptação: fine-tuning completo, fine-tuning parcial (ex. LoRA/adapters), ou prompt-tuning.
- Treinar/adaptar o modelo selecionado usando partição de treino de um ou mais datasets.
- Avaliar em partição de teste held-out, comparando com o baseline zero-shot.
- **Entregável:** modelo adaptado + relatório de ganho (ou não) de desempenho em relação ao baseline.

## Fase 5 — Protótipo demonstrativo

- Construir uma interface simples (ex.: notebook interativo, ou app web minimalista) que receba uma imagem histopatológica e retorne uma saída do modelo (classificação, resposta a pergunta, ou descrição textual).
- Objetivo é ilustrativo/acadêmico, não um produto pronto para uso clínico.
- **Entregável:** protótipo funcional + vídeo/screenshot de demonstração.

## Fase 6 — Avaliação crítica e discussão

- Analisar desempenho por subgrupo (tipo de câncer, origem do dataset, qualidade da imagem) para identificar possíveis vieses.
- Discutir limitações técnicas e éticas do uso de VLMs como ferramenta de pré-diagnóstico (falsos negativos/positivos, excesso de confiança do usuário no modelo, necessidade de supervisão humana).
- **Entregável:** seção de discussão do relatório final.

## Fase 7 — Redação final

- Consolidar relatório final da IC (formato exigido pela instituição/agência de fomento, se aplicável).
- Revisar toda a documentação deste repositório para refletir o estado final do projeto.
- Avaliar possibilidade de submissão a evento científico (congresso de iniciação científica, workshop de IA em saúde).
