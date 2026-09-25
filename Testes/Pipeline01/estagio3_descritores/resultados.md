# Resultados 03 — Extração de descritores por patch (estágio 3)

**Lâmina:** `BRACS_748.svs`
**Script:** [descritores.py](descritores.py)
**k usado:** 32 (dentro do range documentado 8–32), reaproveitando a seleção do estágio 2 (banco v2)

## Método

Para cada um dos 32 patches selecionados no estágio 2, gera um achado textual: pega o embedding do patch **já calculado e cacheado no estágio 2** (nenhuma imagem recomputada, nenhuma GPU pra isso), compara contra o banco de frases "suspeito" (11 termos, ver `docs/questoes.md`/`resultados02.md`) e toma as **top-2** frases de maior similaridade como achado. Sempre inclui a coordenada do patch. Sem densidade nuclear/razão H&E ainda — começando só com contrastivo + coordenada, como `docs/pipelines.md` recomenda.

Saída: ~6 tokens/patch (bem abaixo dos 30–60 documentados — o achado é só 2 termos, sem frase natural em volta ainda).

## Achado: os 32 descritores saíram idênticos

Todos os 32 patches selecionados receberam exatamente o mesmo achado: **"high nuclear pleomorphism, mitotic figures"**. Investiguei se é homogeneidade real dos patches (top-32 são todos parecidos, plausível) ou problema de calibração do método — é as duas coisas, mas a segunda pesa mais do que devia.

**Confirmado, com números:** a similaridade média de cada frase, calculada sobre os 15.138 candidatos, varia sozinha entre 0,226 ("solid growth pattern") e 0,284 ("high nuclear pleomorphism") — uma diferença de 0,058 só por *qual frase é*, do tamanho da diferença entre patches diferentes. Ou seja, "high nuclear pleomorphism" e "mitotic figures" tendem a vencer **quase sempre**, independente do conteúdo real do patch — o clássico problema de similaridade bruta de CLIP não-calibrada entre classes.

**Mas não é só isso:** testando patches de posições bem diferentes no ranking do estágio 2 (pior colocado, meio do ranking, topo), o top-3 bruto *varia* — "necrosis" lidera pro patch pior colocado, "desmoplastic stroma"/"stromal invasion" pro do meio. O viés de frase domina especificamente **dentro do grupo top-32**, que já são os patches mais parecidos entre si por construção (foram selecionados exatamente por serem os mais "suspeitos"). Então parte do "problema" é esperado; parte é calibração ruim mesmo.

**Testei normalização (z-score por frase, contra a população dos 15.138):** muda a ordem — ex. "cribriform architecture" sobe pro patch pior colocado, "micropapillary architecture" pro do meio — mas **não tenho RoI-por-classe pareado ainda pra confirmar se o normalizado acerta mais que o bruto**. Só sei que é menos enviesado, não que é mais certo.

## k=128: a homogeneidade se confirma (e piora)

Testado com `--k 128`: **122 de 128 patches (95%) receberam a combinação idêntica** "high nuclear pleomorphism, mitotic figures". Não é efeito do top-32 restrito — o viés de frase domina mesmo com 4x mais patches.

## Normalização por z-score: implementada, resultado misto

Adicionei `--normalizar` ao script: calcula média/desvio de cada frase sobre os 15.138 candidatos e usa `(sim − média) / desvio` em vez da similaridade bruta pra rankear os achados.

**Resultado em k=128:** 8 combinações distintas em vez de 4 — mais variedade, mas ainda dominado por uma combinação (81/128 = 63% "mitotic figures, solid growth pattern").

**Desvio-padrão de cada frase, sobre os 15.138 candidatos** (do menor pro maior):

| Frase | Média | Desvio-padrão |
|---|---|---|
| necrosis | 0.271 | 0.0064 |
| stromal invasion | 0.273 | 0.0091 |
| nuclear crowding and stratification | 0.243 | 0.0094 |
| high nuclear pleomorphism | 0.284 | 0.0097 |
| desmoplastic stroma | 0.272 | 0.0100 |
| micropapillary architecture | 0.263 | 0.0103 |
| mitotic figures | 0.272 | 0.0107 |
| cribriform architecture | 0.265 | 0.0118 |
| tumor nests | 0.273 | 0.0120 |
| comedonecrosis | 0.258 | 0.0151 |
| solid growth pattern | 0.226 | 0.0196 |

**Correção de leitura (registrada pra não repetir o erro):** a primeira hipótese — que "solid growth pattern" dominaria por ter *baixa* variância — estava invertida. É a frase de *maior* desvio-padrão do banco inteiro, junto com "comedonecrosis". Ou seja, normalizar não está inflando uma frase quase-constante; está privilegiando as duas frases que **de fato variam** patch a patch (potencialmente as mais informativas), em detrimento de frases quase-constantes como "necrosis" e "stromal invasion" (std ~0,006–0,009, quase ruído). Se isso é correto (as frases de maior variância carregam mais sinal real) ou é exagero da normalização (variância alta podendo ser artefato de outra coisa) — não dá pra saber sem checar contra classe real do patch.

## 25/09 — o descritor não conseguia dizer "normal"; corrigido e testado em 8 lâminas

Rodando a pipeline em 8 lâminas (ver [../resultados_multilaminas.md](../resultados_multilaminas.md)), apareceu uma falha de desenho: o banco do descritor só tinha frases suspeitas, então até a lâmina de tecido normal (`BRACS_1003718`) saía descrita como "desmoplastic stroma, stromal invasion". Não existia frase que permitisse dizer "normal".

**Correção:** o descritor passou a usar `BANCO_DESCRITOR` (em `comum/bancos.py`), com o espectro inteiro organizado nas três categorias oficiais do BRACS — benigno (N, PB + gordura e estroma fibroso, 12 frases), atípico (UDH, FEA, ADH, 15 frases) e maligno (o antigo banco suspeito + DCIS e IC, 19 frases). Cada patch recebe também uma **categoria sugerida**: a categoria cuja frase mais parecida tem a maior similaridade.

**Teste** ([../validacao/categoria_descritor.py](../validacao/categoria_descritor.py)): a categoria sugerida bate com a categoria real do RoI? Todos os tiles rotulados das 8 lâminas, somados:

| Categoria real | Bruto: acerto | Normalizado: acerto |
|---|---|---|
| Benigno (159 tiles) | 65% | 24% |
| Atípico (225 tiles) | 53% | 37% |
| Maligno (3.307 tiles) | 33% | 39% |
| **Média das 3** | **51%** | **33%** |

Chute aleatório entre 3 categorias = 33%.

- **Bruto: primeiro sinal acima do acaso** nos testes do estágio 3 (51% contra 33%), e agora ele diz "normal": na lâmina PB, o achado dominante virou "normal breast tissue, normal terminal duct lobular unit" e 88% dos tiles benignos foram reconhecidos.
- **O viés de calibração não sumiu, mudou de direção.** Antes "high nuclear pleomorphism" ganhava sempre; agora "normal breast tissue" puxa muito — 1.367 dos 3.307 tiles malignos foram chamados de benignos. O ponto fraco agora é reconhecer o maligno.
- **Normalizado fica exatamente no acaso (33%) — descartado pra essa tarefa.** O z-score é calculado dentro da própria lâmina, então numa lâmina toda benigna "benigno" vira o normal dela e deixa de se destacar. A normalização apaga o sinal absoluto que interessa aqui. Isso resolve a pendência "bruto ou normalizado" que estava em aberto desde o teste de k=128.

### Atacando o viés pró-"benigno" — três versões comparadas

Mesmo teste (`categoria_descritor.py`, descritor bruto, todos os tiles rotulados das 8 lâminas):

| Categoria | Original | Sem "normal breast tissue" | **Lóbulo específico** (atual) |
|---|---|---|---|
| Benigno | 65% | 47% | 52% |
| Atípico | 53% | 54% | 61% |
| Maligno | 33% | 35% | 43% |
| **Média** | 51% | 45% | **52%** |

1. **Tirar a frase mais genérica ("normal breast tissue") piorou** (51% → 45%). Ela ajudava a reconhecer benigno de verdade e não era ela que puxava o maligno: na lâmina de DCIS continuaram exatamente os mesmos 444 tiles malignos chamados de benignos. Hipótese errada, revertida.
2. **O atrator real era "normal terminal duct lobular unit"**: ganhava em 440 dos 444 erros da lâmina de DCIS e em 825 dos 865 da `BRACS_748`. Faz sentido — o DCIS cresce *dentro* de ductos e lóbulos, então a arquitetura geral parece a de um lóbulo normal, só que cheio de células. O modelo reconhece a estrutura e não o conteúdo; é o mesmo problema de fundo do DCIS vs. IC.
3. **Versão atual:** a frase foi trocada por "normal lobule with open lumina and two cell layers" — descreve justamente o que o DCIS não tem. Maligno subiu de 33% pra 43% (tiles malignos chamados de benignos: 1.367 → 651; na lâmina de DCIS, 444 → 24). Mas parte do erro só mudou de lugar: 432 tiles da lâmina de DCIS agora saem como atípicos (erro "vizinho" no espectro, ADH → DCIS, mas ainda erro). E o benigno caiu (65% → 52%), principalmente na lâmina de UDH.

Ganho na média é pequeno (51% → 52%), mas a pior categoria saiu de 33% pra 43% — pra triagem, deixar de não enxergar o maligno pesa mais. Mantida essa versão (`SUBSTITUICOES_DO_DESCRITOR` em `comum/bancos.py`).

### Mesmo truque nas outras frases, uma de cada vez

Registro completo, frase por frase: [../validacao/experimento_frases.md](../validacao/experimento_frases.md) (script `validacao/experimento_frases.py`, que reusa os embeddings do cache, então cada teste leva segundos).

**Regra fixada antes de rodar:** uma troca só fica se a média das 3 categorias subir ≥ 0,5 ponto. Guloso: cada troca é testada em cima das já aceitas. 14 candidatas testadas, **2 aceitas**:

| Troca | Benigno | Atípico | Maligno | Média |
|---|---|---|---|---|
| Partida (lóbulo específico) | 52% | 61% | 43% | 52,0% |
| + "focal atypical epithelial proliferation" → "focal atypical proliferation involving part of a duct" | 53% | 58% | 54% | 54,7% |
| + "high nuclear pleomorphism" → "large pleomorphic nuclei with prominent nucleoli" | 53% | 57% | 59% | **56,5%** |

Confirmado rodando a pipeline inteira de novo (mesmos números). Tiles malignos chamados de atípicos: 1.239 → 781; de benignos: 651 → 563.

- **O que funcionou foi, de novo, tirar um atrator:** "focal atypical epithelial proliferation" puxava tile de DCIS pra atípico (no top-32 da lâmina de DCIS, 21 de 32 saíam atípicos; agora 4). A versão nova diz que é *parte* do ducto — o que o DCIS não é.
- **O que não funcionou:** reescrever o nome da própria classe piorou nos dois casos testados ("ductal carcinoma in situ" → "duct completely filled by atypical cells": maligno 43% → 37%; "atypical ductal hyperplasia" → "atypical cells partially filling a duct": atípico 61% → 36%). O nome da classe parece ser a âncora mais forte que o modelo tem.
- **Várias trocas deram Δ = 0,00:** a frase velha e a nova nunca ganham em nenhum tile — são frases "mortas" no banco. Trocar só ajuda onde a frase já está ganhando.
- **Custo:** o atípico caiu 61% → 57%, e no top-32 da lâmina FEA os patches atípicos caíram de 21 pra 15.
- **Ressalva:** as frases foram escolhidas olhando as mesmas 8 lâminas em que são avaliadas. O ganho de 52% → 56,5% precisa ser conferido em lâminas novas antes de valer como resultado.

## Em aberto

- Conferir o banco atual em lâminas que não foram usadas pra escolher as frases.
- O erro que sobrou ainda é maligno → atípico (781 tiles). Separar DCIS de ADH/UDH é questão de arquitetura (ducto inteiro preenchido vs. parcialmente), não de célula isolada — ver `validacao/problemas_e_metrica.md`.
- Achar quais frases estão "mortas" (nunca ganham) e se vale tirar ou trocar.
- Investigar por que "necrosis", "stromal invasion" e "nuclear crowding" têm desvio-padrão tão baixo — são achados genuinamente raros, ou o encoder não tem boa resolução pra eles?
- Ainda sem H&E/densidade nuclear — só entram se a curva pedir, como documentado.
