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

Pré-laudos completos: `resultados/<lamina>/estagio5/prelaudo_k32_uni_<modelo>.md` (+ `.json` com tempo, tokens e o rótulo real).
