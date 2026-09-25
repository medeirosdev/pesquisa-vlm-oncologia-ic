# Problemas encontrados até aqui, e o problema de métrica que ficou por baixo de todos

## Os 5 testes que falharam do mesmo jeito

Testando o estágio 3 (achado textual por patch) contra a classe real do RoI (ADH/DCIS/IC):

1. **Bruto** (similaridade máxima, banco único "suspeito") — não discrimina DCIS de IC.
2. **Normalizado** (z-score por frase) — muda qual frase domina, não resolve.
3. **Ensemble de prompts** (vários templates por frase, sugestão do Prof. João) — piora a diversidade sozinho, não resolve combinado com normalização.
4. **Banco de frases por classe** (ADH/DCIS/IC com critério diagnóstico real — WHO/critérios de Page) — pior ainda: 23,9% de acurácia contra 80,2% de um baseline que só chuta a classe majoritária.
5. Em todos: o viés de calibração persiste — ora uma frase domina sempre, ora um banco de classe inteiro domina sempre, independente da imagem real.

## O problema de fundo, que só apareceu ao perguntar "como medimos acerto"

Todos os 5 testes usaram a mesma métrica: **o achado do patch bate com a classe do RoI em que ele caiu?** Isso tem um problema conceitual, não só técnico:

**Classe é rótulo de lesão inteira (nível arquitetural), não de patch (nível citológico).** A diferença real entre DCIS (carcinoma *in situ*) e IC (carcinoma invasivo) não é "como a célula parece" — é se a camada mioepitelial ao redor do ducto está intacta ou rompida. Isso é uma informação de **borda/arquitetura**, frequentemente confirmada só com imuno-histoquímica (marcadores como p63, calponina) — não necessariamente visível em H&E, e menos ainda dentro de um patch de 256px sorteado do meio da lesão.

**Consequência:** um patch bem no centro de uma região DCIS e um patch bem no centro de uma região IC podem ser citologicamente idênticos. Se for esse o caso, **nenhum modelo classifica isso a partir de 1 patch isolado** — não é fraqueza do QuiltNet-B-32, é a pergunta errada pro nível de dado que se tem.

Isso muda a leitura dos 5 testes: o resultado negativo pode ser, em parte, sobre a tarefa ser malformulada (pedir do patch algo que só a região inteira carrega), não só sobre o modelo ser fraco.

## O que isso implica pro próximo teste

Se a informação discriminativa está no **padrão agregado**, não no patch pontual, o teste certo é: descrever + classificar cada patch, **juntar as evidências de todos os patches de uma mesma região**, e classificar a região a partir do agregado — não do patch isolado. Ver `agregacao_por_roi.py` e o resultado correspondente, feito logo em seguida a este registro.

## Teste da hipótese de agregação — resultado, e também negativo

[agregacao_por_roi.py](agregacao_por_roi.py): agrupei os candidatos por RoI individual (98 RoIs, ≥3 patches cada) e testei duas formas de juntar a evidência antes de classificar — média dos embeddings de imagem do RoI inteiro, e voto majoritário das classificações por patch.

| Método | Acurácia | Baseline (classe majoritária) |
|---|---|---|
| Por patch (sem agregar) | 24,3% (n=3.068 patches) | — |
| Média de embeddings por RoI | 27,6% (27/98) | 85,7% |
| Voto majoritário por RoI | 27,6% (27/98) | 85,7% |

**Melhora marginal (24,3% → 27,6%), longe de resolver.** E isso aponta pra uma explicação mais específica do que "falta contexto": média e voto são as duas formas mais simples de agregação, e as duas são **invariantes à posição** — tratam o RoI como um saco de patches, sem noção de onde cada um está dentro da região. Se o que realmente separa DCIS de IC é uma relação espacial (a borda do ducto — camada mioepitelial rompida ou não), nenhuma das duas consegue recuperar isso, porque ambas jogam fora justamente a posição relativa dos patches antes de decidir.

**Isso refina a hipótese registrada acima:** não é só "1 patch tem pouca informação, muitos patches têm mais" — é que o tipo de agregação importa, e agregação que preserva estrutura espacial (ex. olhar especificamente os patches na borda da região, não o interior) provavelmente é necessária, não qualquer agregação.

## Agregação por borda — primeira melhora real

[agregacao_por_borda.py](agregacao_por_borda.py): separei os patches de cada RoI em "borda" (dentro de 512px do limite da caixa) e "interior" (resto), classificando cada grupo separado (mesma classificação por argmax de média de embedding).

| Grupo | Acurácia | RoIs avaliados |
|---|---|---|
| Interior | 10,0% | 7/70 |
| Todos juntos | 27,6% | 27/98 |
| **Borda** | **36,7%** | **36/98** |

**Borda supera tanto o interior quanto a mistura dos dois.** Ainda longe do baseline de 85,7%, mas é a primeira melhora real depois de 6 tentativas — e bate com a hipótese: o sinal que discrimina DCIS de IC parece mesmo mais concentrado perto do limite da lesão do que no meio dela. Ressalva importante: "borda da caixa retangular" é só uma aproximação de "borda real do tecido" — só temos bounding box, não o contorno de verdade da lesão, então parte do "interior" classificado como borda (ou vice-versa) é erro de aproximação geométrica, não do método em si.

## Itens que continuam em aberto, independente do resultado do próximo teste

- Testar CONCH/KEEP no lugar do QuiltNet-B-32 — ainda vale descartar "modelo fraco" como explicação, mesmo que a explicação principal seja a formulação da tarefa.
- A ideia de hierarquia do Prof. João (benigno/maligno → evidência) continua sem implementar.
- Só uma lâmina local (BRACS_748) — nenhum desses resultados foi confirmado em outra amostra.
