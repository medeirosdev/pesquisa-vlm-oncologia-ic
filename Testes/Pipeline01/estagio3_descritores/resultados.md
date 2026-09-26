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
- **Ressalva:** as frases foram escolhidas olhando as mesmas 8 lâminas em que são avaliadas. O ganho de 52% → 56,5% precisa ser conferido em lâminas novas antes de valer como resultado. **Conferido logo abaixo: não se confirmou.**

### Teste fora da amostra: 8 lâminas novas

As trocas acima foram escolhidas olhando as mesmas 8 lâminas em que foram medidas. Pra saber se o ganho vale, foram baixadas mais 8 lâminas (uma por classe + uma N extra), todas de **pacientes que não aparecem na primeira leva** (lista em `scripts/baixar_laminas.sh --segunda-leva`), e o banco foi medido nelas **sem mexer em nenhuma frase** ([../validacao/teste_fora_da_amostra.py](../validacao/teste_fora_da_amostra.py)).

| Banco | 8 lâminas do ajuste | **8 lâminas novas** |
|---|---|---|
| Sem trocas | 50,7% | 44,8% |
| Só a troca do lóbulo | 52,0% | **53,2%** |
| Lóbulo + as 2 trocas do experimento | 56,5% | 52,7% |

Lâminas novas: 6.571 tiles rotulados (benigno 2.482, atípico 747, maligno 3.342).

Banco final (só lóbulo) nas 16 lâminas somadas: benigno 57%, atípico 46%, maligno 52%, **média 51,6%**.

- **A troca do lóbulo se confirma:** nas lâminas novas a média sobe de 44,8% pra 53,2% (maligno 46% → 61%). É a única mudança do banco que se sustenta fora da amostra.
- **As duas trocas do experimento frase a frase não se confirmam:** nas lâminas novas a média cai (53,2% → 52,7%); o maligno sobe (61% → 66%), mas o atípico cai (41% → 33%). O ganho de 52% → 56,5% era em boa parte ajuste às 8 lâminas. Pela regra fixada antes (+0,5 ponto), **foram retiradas**; o banco voltou a ter só a troca do lóbulo.
- **Lição de método:** com 1 lâmina por classe, escolher frases olhando o resultado superajusta rápido. Qualquer ajuste futuro do banco precisa ser conferido em lâminas separadas antes de ser mantido.
- **Os mesmos erros aparecem nas lâminas novas:** DCIS chamado de atípico (`BRACS_1512`: 331 de 772 tiles) e UDH chamado de benigno (`BRACS_1617`: 111 de 150).

Correção no caminho: na `BRACS_297` nenhum RoI era localizado (0/31) — o nível 0 dessa lâmina tem o dobro da resolução dos recortes de RoI. `recall_roi.py` agora escolhe a escala recorte → lâmina por lâmina (31/31 localizados).

### DCIS vs. IC olhando os 8 vizinhos do patch

Ideia: a diferença entre DCIS e IC é de *localização* (células dentro do ducto vs. no estroma), então um patch sozinho pode não mostrar, mas o patch com os vizinhos em volta pode. Script: [../validacao/dcis_ic_vizinhanca.py](../validacao/dcis_ic_vizinhanca.py). Zero-shot só entre os bancos DCIS e IC; variantes fixadas antes de rodar. Tiles rotulados das 16 lâminas: DCIS 3.553, IC 3.096. Métrica: acurácia balanceada, acaso = 50%.

| Variante | Todas somadas (DCIS / IC / balanceada) | `BRACS_748` — DCIS e IC na mesma lâmina |
|---|---|---|
| A — só o patch | 50% / 89% / 69,2% | 38% / 67% / 52,4% |
| B — média do patch + 8 vizinhos | 49% / 94% / 71,7% | 36% / 75% / 55,5% |
| C — voto dos 9 | 46% / 95% / 70,1% | 28% / 74% / 51,2% |
| D — média 5×5 (24 vizinhos) | 51% / 95% / 72,9% | 39% / 77% / 57,9% |

- **A vizinhança ajuda pouco, e só no IC.** A média 3×3 sobe 2,5 pontos no total e 3 na `BRACS_748`, mas o acerto em DCIS não se mexe (~50% no total, ~37% na 748). O modelo puxa pra IC, e a vizinhança reforça o que ele já acha.
- **O número "todas somadas" engana.** Quase todas as lâminas têm só uma das duas classes, e numa lâmina de uma classe só, suavizar pela vizinhança ajuda sempre que a lâmina já pende pro lado certo — não é sinal de localização. O teste justo é a `BRACS_748`, onde as duas convivem: lá, o patch sozinho está no acaso (52%) e a vizinhança leva a no máximo 58%.
- **Amostra pequena:** os tiles vizinhos são muito correlacionados; na 748 o IC vem de só 10 RoIs. Os 3–5 pontos de ganho não dão pra distinguir de ruído.
- **Leitura:** o gargalo não é o campo de visão, é o zero-shot não reconhecer DCIS (a frase de IC ganha na maioria dos patches de DCIS). Olhar mais vizinhos não resolve isso com a média dos embeddings do CLIP, que dilui a arquitetura em vez de descrevê-la.

### DCIS vs. IC usando os vizinhos como contexto

A média acima mistura os vizinhos; a ideia original era outra: **olhar o que está em volta** do patch. Hipótese: no DCIS o tumor está dentro do ducto (em volta: mais tumor e parede de ducto); no IC está no meio do estroma (em volta: estroma). Script: [../validacao/dcis_ic_contexto.py](../validacao/dcis_ic_contexto.py), com tudo fixado antes de rodar:

1. Cada tile recebe um tipo de tecido por zero-shot (tumor / estroma / ducto / gordura; vizinho fora da grade de tecido = "sem tecido").
2. Descritivo: composição dos 8 vizinhos dos tiles DCIS vs. IC.
3. Regra fixa: IC se ≥ metade dos vizinhos com tecido for estroma.
4. Regressão logística com [score DCIS−IC do patch + composição dos vizinhos], treinada deixando uma lâmina de fora por vez.

**Composição dos vizinhos — o contrário da hipótese:**

| Vizinhos de um tile de… | Tumor | Estroma | Ducto | Sem tecido |
|---|---|---|---|---|
| DCIS (todas) | 32% | 19% | 40% | 8% |
| IC (todas) | 36% | 11% | 51% | 2% |
| DCIS (`BRACS_748`) | 36% | 29% | 31% | 4% |
| IC (`BRACS_748`) | **77%** | 7% | 10% | 7% |

**Acurácia balanceada (acaso = 50%):**

| Método | Todas somadas | `BRACS_748` |
|---|---|---|
| Patch sozinho (zero-shot) | 69,2% | 52,4% |
| Regra fixa (estroma em volta → IC) | 44,7% | 39,0% |
| Logística só com o score do patch | 75,0% | 52,4% |
| Logística com patch + contexto | 33,4% | 31,9% |

- **Na `BRACS_748` o contexto é bem diferente entre DCIS e IC, mas ao contrário do esperado:** o IC está cercado de *tumor* (77%), e o DCIS é que tem estroma em volta. Provável razão: os RoIs de IC dessa lâmina são massas sólidas de tumor, e a caixa de um RoI de DCIS pega o estroma entre os ductos. E um tile tem ~128 µm — a infiltração do IC no estroma acontece numa escala menor, *dentro* do tile, não entre tiles.
- **A relação não se repete entre lâminas:** nas lâminas somadas a diferença quase some. Por isso a logística com contexto, treinada nas outras lâminas, fica abaixo do acaso na lâmina deixada de fora — o que ela aprende numa lâmina não vale na outra.
- **O classificador de tipo de tecido é fraco:** metade dos tiles de IC (1.603 de 3.096) é chamada de "ducto". Com o tipo de tecido errado, o contexto vira ruído.
- **Hipótese nova, que precisa de lâminas novas pra ser testada:** "tile de tumor cercado de tumor → IC" separa bem na `BRACS_748`, mas foi vista *depois* de olhar os dados — não vale como resultado. Teste justo: lâminas com DCIS e IC juntos que ainda não foram usadas (ex.: `BRACS_773`, DCIS 36 + IC 78 RoIs; `BRACS_295`, DCIS 45 + IC 17), com a regra fixada antes.

### Teste da hipótese "tumor cercado de tumor → IC" em lâminas novas

A hipótese saiu da `BRACS_748` depois de olhar os dados, então foi testada em duas lâminas novas com DCIS e IC juntos (`BRACS_773`, `BRACS_295`, pacientes novos). A regra e o critério foram fixados e commitados **antes do download** ([../validacao/dcis_ic_regra_tumor.py](../validacao/dcis_ic_regra_tumor.py)): IC se ≥ 50% dos 8 vizinhos forem tumor; "funcionou" = supera o patch sozinho nas duas lâminas.

| Lâmina | Patch sozinho (DCIS / IC / balanceada) | Regra do tumor (DCIS / IC / balanceada) |
|---|---|---|
| `BRACS_773` (DCIS 610, IC 4.529 tiles) | 15% / 88% / 51,7% | 75% / 34% / 54,7% |
| `BRACS_295` (DCIS 806, IC 1.268 tiles) | 46% / 52% / 48,9% | 96% / 14% / 55,1% |
| Somadas | 33% / 80% / 56,3% | 87% / 30% / 58,4% |

Vizinhos que são tumor, em média:

| Lâmina | DCIS | IC |
|---|---|---|
| `BRACS_748` (onde a hipótese surgiu) | 36% | 77% |
| `BRACS_773` | 28% | 33% |
| `BRACS_295` | 10% | 18% |

- **Pelo critério fixado antes, passou** (+3 e +6 pontos, nas duas lâminas). E a direção se repete: nas duas, os tiles de IC têm mais tumor em volta que os de DCIS.
- **Mas o efeito é fraco:** a diferença entre DCIS e IC (5–8 pontos) é muito menor que na 748 (41 pontos). O limiar de 50% veio da 748; nas lâminas novas quase nenhum tile passa dele, então a regra troca o viés — de "quase tudo IC" pra "quase tudo DCIS" — e a balanceada fica em ~55%, perto do acaso.
- **A quantidade de "tumor" muda muito entre lâminas** (10% a 77% dos vizinhos), o que aponta de novo pro classificador de tipo de tecido e pra diferenças de lâmina, não só pra biologia.
- **Leitura:** há um sinal de contexto na direção certa, mas pequeno e dependente da lâmina; como regra com limiar fixo, não serve. Usar *a diferença relativa dentro da lâmina* (em vez de limiar absoluto) seria o próximo teste — e precisaria de outras lâminas novas, já que estas duas agora foram vistas.

Correção no caminho: um recorte de RoI do dataset local está truncado (`BRACS_773_UDH_20.png`); `recall_roi.py` agora pula recortes ilegíveis com aviso.

### DCIS vs. IC pela posição dos núcleos (CellViT) — primeiro sinal forte

O CellViT (CellViT-256, pesos oficiais x40, tipos de núcleo do PanNuke) segmenta e classifica cada núcleo: neoplásico, inflamatório, conjuntivo, morto, epitelial. Não tem classe "mioepitelial", então a camada é inferida pelo arranjo: no DCIS o tumor tem **uma fronteira lisa** com o estroma (membrana basal e camada mioepitelial no meio), e poucos núcleos neoplásicos encostam em núcleos conjuntivos; no IC o tumor se infiltra e os dois se misturam em pequena escala.

Scripts: [../validacao/nucleos_cellvit.py](../validacao/nucleos_cellvit.py) (segmentação, janela de 1024 px centrada no tile) e [../validacao/dcis_ic_nucleos.py](../validacao/dcis_ic_nucleos.py) (teste). Roda num ambiente separado no HD (`venvs/cellvit`), porque o CellViT exige numpy < 2 e opencv fixo. ~1 s por tile na RTX 3050 (1,5 GB de GPU).

**Fixado antes de rodar** (commit `24cde37`): 250 tiles por classe em cada lâmina com DCIS e IC juntos (`BRACS_748`, `BRACS_773`, `BRACS_295`); só entram tiles com ≥ 20 núcleos neoplásicos; medida = fração dos núcleos neoplásicos com um núcleo conjuntivo a ≤ 20 µm; critério = AUC > 0,5 (IC maior) nas três lâminas.

| Lâmina | Tiles com tumor (DCIS / IC) | Mediana DCIS | Mediana IC | **AUC** | AUC do QuiltNet zero-shot, mesmos tiles |
|---|---|---|---|---|---|
| `BRACS_748` | 135 / 219 | 0,41 | 0,80 | **0,72** | 0,50 |
| `BRACS_773` | 127 / 169 | 0,28 | 0,68 | **0,84** | 0,58 |
| `BRACS_295` | 142 / 212 | 0,48 | 0,59 | **0,66** | 0,50 |

- **Passou no critério nas três lâminas, e é o primeiro método que separa DCIS de IC de forma consistente.** Nos mesmos tiles, o zero-shot do QuiltNet fica no acaso.
- **O sinal vem do arranjo, não da quantidade:** as medidas secundárias (número de núcleos neoplásicos, fração de conjuntivos no tile) não separam de forma consistente — a AUC delas muda de lado entre lâminas.
- **Filtro de tumor pesa:** quase metade dos tiles "DCIS" não tem 20 núcleos neoplásicos — é estroma entre ductos dentro da caixa do RoI. Na pipeline, a medida só faz sentido depois de achar onde há tumor.
- **Ressalvas:** tiles vizinhos são correlacionados (a AUC por tile superestima a confiança); a `BRACS_295` separa menos (0,66); 20 µm foi escolhido por critério histológico, não ajustado — e não deve ser ajustado olhando estas lâminas. A camada mioepitelial não é medida diretamente, só inferida.

## Em aberto

- O erro que sobrou ainda é maligno → atípico, e se repete nas lâminas novas. Separar DCIS de ADH/UDH é questão de arquitetura (ducto inteiro preenchido vs. parcialmente), não de célula isolada — ver `validacao/problemas_e_metrica.md`.
- Achar quais frases estão "mortas" (nunca ganham) e se vale tirar ou trocar.
- Investigar por que "necrosis", "stromal invasion" e "nuclear crowding" têm desvio-padrão tão baixo — são achados genuinamente raros, ou o encoder não tem boa resolução pra eles?
- Ainda sem H&E/densidade nuclear — só entram se a curva pedir, como documentado.
