# Resultados — estágio 5 (síntese por modelo de linguagem local)

Primeira execução da pipeline completa (17/10/2026): roteador por frases (32 patches) → descritor hierárquico com UNI2-h (`estagio3_descritores/descritor_uni.py`) → agregação (estágio 4) → modelo de linguagem local via Ollama ([sintese.py](sintese.py)), com o prompt do estágio 4 e as 3 imagens âncora. Instruções fixas: usar só a evidência, dar grau de confiança justificado, listar regiões pra revisão, apontar inconsistências, deixar claro que é rascunho. O rótulo real não vai pro modelo. `temperature` 0,2, `seed` 0.

Modelos: MedGemma 4B e Gemma 3 4B (biblioteca oficial do Ollama, quantizados, ~3,4 GB cada). Ollama 0.40.6 rodando do HD (o instalado no sistema, 0.14.3, não baixa os modelos atuais).

Teste exploratório, sem critério fixado: 3 lâminas, pra ver se a pipeline roda de ponta a ponta e como o modelo usa a evidência.

| Lâmina (rótulo real) | Evidência do estágio 4 | MedGemma 4B | Gemma 3 4B |
|---|---|---|---|
| `BRACS_1489` (DCIS) | 29 malignos (quase todos DCIS), 3 atípicos | DCIS, confiança alta ✓ | DCIS, confiança moderada ✓ |
| `BRACS_748` (IC) | 32 malignos: 26 DCIS, 6 IC | DCIS (81% chamado de "probabilidade") ✗ | DCIS, com alerta pro componente invasivo ✗ |
| `BRACS_1370` (PB) | 19 benignos, 1 atípico, 12 malignos (falsos positivos) | DCIS e invasivo em confiança alta, benigno em moderada — incoerente ✗ | aponta a mistura de categorias e pede avaliação, sem concluir câncer (meio-termo) |
| Regiões destacadas | — | lista quase todos os 32 patches | 3 por lâmina |
| Tempo por pré-laudo | — | 115–224 s | 46–154 s |

- **A pipeline roda de ponta a ponta**, localmente, numa GPU de 4 GB.
- **O modelo segue a maioria dos patches.** Na `BRACS_748`, o componente invasivo (6 de 32 patches) define o diagnóstico (IC), mas os dois modelos sugerem DCIS. Isso é um problema da agregação, não só do modelo: pode virar uma regra explícita no estágio 4 (componente invasivo presente → destacar), a ser testada em lâminas que não foram usadas pra escrevê-la.
- **Os falsos positivos do estágio 3 passam pro texto.** Na lâmina benigna, o MedGemma afirma DCIS e invasivo com confiança alta; o Gemma 3 é mais cauteloso e aponta a inconsistência.
- **Gemma 3 foi melhor que MedGemma nesse teste:** prioriza 3 regiões em vez de listar tudo, usa linguagem mais cautelosa e é mais rápido. O MedGemma confunde fração de patches com probabilidade e organiza a impressão de forma incoerente.
- **Limitações:** 3 lâminas, uma execução por modelo; sem avaliação sistemática. Próximo passo: rodar nas 18 lâminas e comparar a impressão com o rótulo real.

Pré-laudos completos: `resultados/<lamina>/estagio5/prelaudo_k32_uni_<modelo>.md` (+ `.json` com tempo, tokens e o rótulo real). Os do teste exploratório ficaram em `resultados/<lamina>/estagio5/exploratorio_1710/`.

## Avaliação sistemática e regra do componente invasivo (17/10)

Script: [../validacao/prelaudo_avaliacao.py](../validacao/prelaudo_avaliacao.py), fixado antes (commit `acd789c`). Gemma 3 4B. Rótulo real = rótulo da lâmina no BRACS, agrupado em benigno / atípico / DCIS / IC.

- **A)** pipeline sem a regra (v1), nas 18 lâminas, descritiva.
- **B)** regra do componente invasivo no estágio 4 (v2: se ≥ 2 patches com carcinoma invasivo e P ≥ 0,90, o prompt diz "componente invasivo presente" e lembra que ele define o diagnóstico; senão, "componente invasivo não detectado"). Avaliada só nas 15 lâminas que não foram usadas pra criar a regra. Critério: v2 acerta mais lâminas IC que v1 e não perde acurácia.

**Correção do instrumento antes da análise** (commit `c50a4b2`): na primeira tentativa, 0 de 9 respostas trouxeram a linha "CLASSIFICAÇÃO FINAL" pedida; a classificação passou a ser extraída por uma segunda chamada curta ao mesmo modelo, só com o texto que ele gerou, em JSON restrito às 4 opções. O contexto caiu de 8192 pra 4096 tokens (com 8192 o Ollama chegou a ~6 GB de RAM e a 0,07 token/s). Critério, lâminas e modelo não mudaram. No teste da correção, uma lâmina (`BRACS_1003718`) teve o resultado visto antes da rodada completa; nada foi mudado por causa disso.

| Lâmina | Rótulo BRACS | Real | Sem regra (v1) | Com regra (v2) |
|---|---|---|---|---|
| `BRACS_1003677` | IC | IC | IC ✓ | IC ✓ |
| `BRACS_297` | IC | IC | IC ✓ | IC ✓ |
| `BRACS_295` | IC | IC | IC ✓ | IC ✓ |
| `BRACS_773` | IC | IC | DCIS ✗ | IC ✓ |
| `BRACS_1512` | DCIS | DCIS | DCIS ✓ | DCIS ✓ |
| `BRACS_1003718` | N | benigno | IC ✗ | benigno ✓ |
| `BRACS_1507` | N | benigno | benigno ✓ | benigno ✓ |
| `BRACS_1641` | N | benigno | DCIS ✗ | benigno ✓ |
| `BRACS_1320` | PB | benigno | DCIS ✗ | benigno ✓ |
| `BRACS_1592` | UDH | atípico | DCIS ✗ | atípico ✓ |
| `BRACS_1617` | UDH | atípico | IC ✗ | IC ✗ |
| `BRACS_1271` | ADH | atípico | IC ✗ | DCIS ✗ |
| `BRACS_1494` | ADH | atípico | IC ✗ | IC ✗ |
| `BRACS_1774` | FEA | atípico | DCIS ✗ | DCIS ✗ |
| `BRACS_743` | FEA | atípico | DCIS ✗ | DCIS ✗ |
| `BRACS_748` (usada na regra) | IC | IC | DCIS ✗ | — |
| `BRACS_1489` (usada na regra) | DCIS | DCIS | DCIS ✓ | — |
| `BRACS_1370` (usada na regra) | PB | benigno | DCIS ✗ | — |

| | Sem regra (v1) | Com regra (v2) |
|---|---|---|
| **A)** 18 lâminas | 6/18 (33%) — benigno 1/5, atípico 0/6, DCIS 2/2, IC 3/5 | — |
| **B)** 15 lâminas fora | 5/15 (33%) — IC 3/4 | **10/15 (67%)** — IC **4/4** |

- **B passou no critério** (IC 3 → 4 de 4; acurácia 5 → 10 de 15).
- **Sem a regra, o modelo é alarmista:** chama de DCIS ou carcinoma invasivo quase tudo — 17 das 18 respostas são malignas, com só 7 lâminas malignas.
- **O maior ganho da regra veio das lâminas benignas** (1 → 4 de 4), não só do IC: a linha "componente invasivo não detectado" deixa o modelo menos alarmista. Não era o efeito esperado quando a regra foi escrita.
- **O atípico continua errado** (1 de 6 com a regra): o descritor quase não reconhece atípico, e duas lâminas atípicas (`BRACS_1617`, `BRACS_1494`) viram carcinoma invasivo — a regra também propaga os falsos positivos de IC do estágio 3.
- **Ressalvas:** 15 lâminas, uma execução por versão, um só modelo; diferença de 5 lâminas. O rótulo da lâmina no BRACS é o da lesão mais grave anotada, não um laudo completo.

## Teste externo: 57 lâminas do conjunto de teste oficial do BRACS (18/10)

Pipeline congelada, sem nenhum ajuste ([../validacao/prelaudo_teste_externo.py](../validacao/prelaudo_teste_externo.py), fixado antes do download, commit `30059dd`): lâminas do conjunto de teste oficial, de pacientes nunca usados, uma por paciente e por classe — 57 lâminas de 31 pacientes. Critério: com a regra, mais acertos no total e pelo menos tantos IC quanto sem ela.

| | Sem regra (v1) | Com regra (v2) |
|---|---|---|
| **57 lâminas** | 13/57 (23%) | **16/57 (28%)** |
| Benigno (13) | 0 | 0 |
| Atípico (24) | 1 | 1 |
| DCIS (8) | 7 | 8 |
| IC (12) | 5 | 7 |
| Respostas malignas | 55 de 57 | 55 de 57 |
| Uma lâmina por paciente (31) | 7/31 | 10/31 |

- **Passou no critério, por pouco** (3 lâminas a mais; IC 5 → 7 de 12).
- **A pipeline chama quase tudo de maligno:** 55 das 57 respostas são DCIS ou carcinoma invasivo, com e sem regra. Benignas 0 de 13, atípicas 1 de 24. O acerto total (23–28%) fica perto do acaso de 4 classes (25%).
- **O ganho da regra nas lâminas benignas, visto nas 15 lâminas de desenvolvimento (1 → 4 de 4), não se repetiu** (0 → 0 de 13). O que se manteve foi o ganho no IC.
- **O problema está antes do modelo de linguagem:** o roteador escolhe os patches que parecem suspeitos e o descritor quase nunca diz "atípico"; o modelo recebe evidência maligna e escreve maligno.
- **A extração da classificação também erra:** na `BRACS_1641` sem a regra, o texto sugere lesão benigna e a extração em formato restrito devolveu DCIS. Parte das diferenças entre versões pode vir da extração; falta conferir uma amostra à mão.

### Conferência da extração da classificação (amostra de 20 pré-laudos do teste externo, 18/10)

Sorteio com semente 0 entre os 114 pré-laudos; a impressão diagnóstica escrita pelo modelo comparada com a classificação extraída em JSON (julgamento feito na análise, sem patologista):

| Situação | Quantos |
|---|---|
| Texto e extração batem | 8 de 20 |
| Extração contraria o texto (ex.: "carcinoma invasivo com DCIS como componente" → DCIS) | 2 de 20 |
| O texto não se decide por uma classe (ex.: "predominância de tecido benigno sugere benignidade, no entanto a presença de DCIS requer investigação") e a extração escolhe DCIS | 10 de 20 |

- A extração erra em ~10% dos casos; não explica sozinha o resultado.
- Em metade dos pré-laudos o modelo não se compromete com uma classe, e a extração resolve quase sempre como DCIS.
- Em várias lâminas benignas e atípicas a evidência diz "predominância de tecido benigno": o problema está em parte na decisão final (poucos patches malignos fazem a lâmina inteira virar maligna), não só nos falsos positivos do estágio 3.
- Próximo teste: classe final por regra explícita sobre as proporções de patches (limiar escolhido nas 18 lâminas de desenvolvimento, testado nas 57 do teste oficial), com o modelo de linguagem só redigindo o texto.
