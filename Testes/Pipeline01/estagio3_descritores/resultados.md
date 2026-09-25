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

## Em aberto

- Reduzir o viés pró-"benigno" do bruto: testar tirar "normal breast tissue" (a frase mais genérica, provável atrator) ou pesar as categorias — medindo com o mesmo `categoria_descritor.py`.
- Investigar por que "necrosis", "stromal invasion" e "nuclear crowding" têm desvio-padrão tão baixo — são achados genuinamente raros, ou o encoder não tem boa resolução pra eles?
- Ainda sem H&E/densidade nuclear — só entram se a curva pedir, como documentado.
