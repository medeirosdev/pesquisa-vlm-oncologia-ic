# Brainstorming — melhorias e testes novos por estágio

Estado em 19/10/2026, depois do teste externo (57 lâminas do conjunto de teste oficial do BRACS). Resultados de todos os testes em [resultados.md](resultados.md); ordem cronológica em [linha_do_tempo.md](linha_do_tempo.md).

## Diagnóstico

O gargalo está antes do modelo de linguagem. No teste externo, a pipeline chamou 55 das 57 lâminas de malignas: acerta DCIS (8/8) e carcinoma invasivo (7/12), mas erra quase todas as benignas (0/13) e atípicas (1/24). Três pontos se somam:

1. **Descritor (estágio 3):** gera falsos positivos malignos (ex.: estroma com uma fenda no tecido classificado como "carcinoma invasivo, 1,00") e quase nunca diz "atípico".
2. **Roteador (estágio 2):** escolhe os patches que mais parecem suspeitos; em lâminas benignas e atípicas, puxa justamente os patches que o descritor erra.
3. **Decisão final (estágios 4 e 5):** poucos patches malignos bastam pra lâmina inteira virar maligna, mesmo com a maioria benigna. O modelo de linguagem raramente se compromete com uma classe, e a extração resolve a dúvida como DCIS.

Uma classificação no nível da lâmina inteira ataca os três pontos de uma vez: usa todos os patches, aprende com o rótulo da lâmina e entrega uma decisão mensurável. O modelo de linguagem passaria a só redigir o texto.

## Dado disponível que muda as opções

O conjunto de RoIs do BRACS (recortes das regiões anotadas por patologistas) já está no HD, separado por classe:

| | N | PB | UDH | FEA | ADH | DCIS | IC | Total |
|---|---|---|---|---|---|---|---|---|
| Treino | 357 | 714 | 387 | 624 | 387 | 665 | 521 | 3.655 |
| Validação | 46 | 43 | 46 | 49 | 41 | 40 | 47 | 312 |

O descritor atual é treinado com os patches rotulados de 18 lâminas (972 patches atípicos, quase todos de 3 lâminas). As RoIs de teste não estão no disco, o que evita vazamento do conjunto de teste.

## Ideias por estágio

Custo = tempo de máquina e de trabalho. Impacto = o quanto deve mexer no gargalo atual.

### Estágio 1 — filtro de tecido (já funciona)

| Ideia | Motivo | Custo | Impacto |
|---|---|---|---|
| Detectar artefatos (dobras, desfoque, marca de caneta, bolhas) | Patches com artefato geram falsos positivos, como o da fenda no tecido | médio | médio |
| Testar normalização de cor (Macenko, Vahadane) | Medir se a variação de coloração entre lâminas afeta o descritor | baixo | baixo a médio |

### Estágio 2 — escolha dos patches

| Ideia | Motivo | Custo | Impacto |
|---|---|---|---|
| Classificar todos os patches com o UNI2-h e escolher os de maior confiança em cada classe encontrada | A escolha passa a representar a lâmina, não só o que parece suspeito | baixo | alto |
| Usar a atenção de um modelo de lâmina inteira (MIL) como roteador | Os patches que mais pesaram na decisão viram as âncoras do texto; explicável | médio | alto |
| Incluir patches em que o classificador hesita | O texto mostraria onde há dúvida, útil pra revisão | baixo | médio |
| Métrica pra lâminas benignas e atípicas (acerto em RoIs benignas/atípicas, proporção por classe) | Hoje só há métrica boa pra lâminas malignas | baixo | médio |

### Estágio 3 — descritor (o gargalo)

| Ideia | Motivo | Custo | Impacto |
|---|---|---|---|
| **Treinar o descritor com as 3.655 RoIs de treino**, em vez das 18 lâminas | Multiplica os exemplos, sobretudo do atípico (UDH 387, FEA 624, ADH 387) | baixo (embeddings do UNI2-h + uma camada) | alto |
| Calibrar as probabilidades e permitir "não sei" (abstenção) | Hoje sai "1,00" até no erro; calibração com abstenção reduz falsos positivos | baixo | médio a alto |
| Mais de uma escala (40x + 10x ou 5x) | DCIS × IC e o atípico dependem da arquitetura do ducto, que um patch de 128 µm não mostra | médio | médio a alto |
| MLP pequena no lugar da regressão logística | Com milhares de exemplos, um classificador um pouco maior pode ajudar | baixo | médio |
| Medidas nucleares pro atípico (tamanho, forma e variação dos núcleos tumorais) | Atipia é em parte morfologia nuclear; o tipo "tumor" do CellViT já está bom (0,83 / 0,88) | médio | médio |
| Comparar outros encoders (CONCH, Virchow2, H-optimus) com o UNI2-h | Confirmar se o UNI2-h é o melhor pro atípico | médio | médio |

### Classificação da lâmina inteira (nova, entre os estágios 3 e 4)

| Ideia | Motivo | Custo | Impacto |
|---|---|---|---|
| Linha de base simples: proporções e quantis das probabilidades de todos os patches + regressão logística | Rápida, explicável, usa a lâmina toda | baixo | alto |
| Regra explícita de proporção ("maligno só se > X% dos patches forem malignos"), limiar escolhido nas lâminas de treino | Ataca direto o "um patch maligno vira tudo" | muito baixo | médio a alto |
| MIL com atenção (ABMIL, CLAM; TransMIL depois) sobre os embeddings do UNI2-h | Padrão atual pra classificar lâminas inteiras; também gera o mapa de atenção (roteador) | alto (precisa de muitas lâminas de treino) | alto |
| Hierárquico no nível da lâmina: benigno / atípico / maligno → DCIS ou IC | Segue a sugestão do Prof. João | médio | alto |

Dados pro MIL: o BRACS tem 395 lâminas de treino e 65 de validação; baixar todas não cabe no HD (171 GB livres). Alternativa: baixar uma lâmina, calcular os embeddings do UNI2-h (~50 MB por lâmina), apagar a lâmina e seguir. Com ~2.000 patches amostrados por lâmina, ~10 a 15 horas de GPU.

### Estágio 4 — agregação

| Ideia | Motivo | Custo | Impacto |
|---|---|---|---|
| Classe final vinda do classificador da lâmina inteira, não do modelo de linguagem | Decisão mensurável, reproduzível e explicável | baixo | alto |
| Mandar ao prompt a proporção na lâmina toda, além dos 32 patches | O texto reflete a lâmina, não só a amostra suspeita | baixo | médio |
| Reportar a incerteza (ex.: "confiança baixa: só 4% dos patches malignos") | Evita que o modelo de linguagem transforme um sinal fraco em "carcinoma" | baixo | médio |

### Estágio 5 — síntese (pré-laudo)

| Ideia | Motivo | Custo | Impacto |
|---|---|---|---|
| Modelo de linguagem só redige, a partir de campos estruturados (classe, confiança, regiões) | Elimina a indecisão e o problema da extração | baixo | alto |
| Checagem automática de consistência (números e classe do texto vs. evidência) | Pega alucinações e erros como "81% de probabilidade" | baixo | médio |
| Testar outros modelos (Qwen2.5 3B/7B, Phi, MedGemma com campos estruturados) | Comparar a qualidade do texto, não a decisão | médio | médio |
| Avaliação do texto por patologista, com rubrica (clareza, utilidade, erros, alucinações) | É a métrica que importa pro pré-laudo | médio (depende de pessoa) | alto |

### Avaliação e método (todos os estágios)

- Usar as divisões oficiais do BRACS: treino pra treinar, validação pra escolher limiares, teste só no fim. As 57 lâminas do teste externo já foram usadas uma vez; um teste novo idealmente usa as 30 lâminas de teste ainda não usadas.
- Métricas adequadas ao desbalanceamento: acurácia balanceada, macro-F1, AUC benigno × maligno, com intervalos de confiança por bootstrap agrupado por paciente.
- Comparar com os resultados publicados no BRACS: a classificação da lâmina inteira em 7 classes é reconhecidamente difícil, e isso dá a referência do que é um bom número.
- Manter a regra de fixar critério e registrar em commit antes de rodar.

## Prioridades sugeridas

1. **Treinar o descritor com as RoIs de treino do BRACS.** Barato (dados já no HD); ataca o atípico e os falsos positivos. Medir nas 57 lâminas do teste externo contra o descritor atual, mudando só isso na pipeline.
2. **Classificação da lâmina inteira com a linha de base simples** (proporções + logística, ou regra de proporção), treinada nas lâminas de desenvolvimento, como decisão final; o modelo de linguagem só redige.
3. **MIL com atenção**, baixando as lâminas de treino por partes. Passo maior; também resolve o roteador pela atenção.

Os itens 1 e 2 devem caber em um a dois dias de trabalho, e os dois são testáveis com critério fixado antes.
