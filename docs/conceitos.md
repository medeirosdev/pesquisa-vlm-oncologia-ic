# Conceitos

Referência técnica dos conceitos usados no projeto: definição, exemplo, formalização matemática e artigos de referência.

## Quantização

**O que é**

Quantização é a técnica de reduzir a precisão numérica dos pesos (e por vezes das ativações) de um modelo — tipicamente de ponto flutuante de 16 ou 32 bits (FP16/FP32) para representações de menor precisão, como inteiros de 8 bits (INT8), 4 bits (INT4) ou formatos de ponto flutuante reduzido (FP8). O objetivo é reduzir o uso de memória e acelerar a inferência, com perda controlada de acurácia.

**Exemplo**

Um modelo de 7 bilhões de parâmetros em FP16 ocupa cerca de 14 GB de memória (2 bytes por parâmetro). Quantizado para INT4, o mesmo modelo passa a ocupar cerca de 3,5–4 GB (considerando o overhead de escala/zero-point por grupo de pesos) — o que viabiliza rodá-lo em uma GPU de notebook com 6–8 GB de VRAM em vez de exigir uma GPU de servidor.

**A matemática por trás**

A forma mais comum é a quantização afim (*uniform/affine quantization*). Um valor real \(x\) (peso ou ativação) é mapeado para um inteiro \(q\) de \(b\) bits por:

\[
q = \text{round}\left(\frac{x}{s}\right) + z
\]

onde \(s\) (*scale*) é o fator de escala e \(z\) (*zero-point*) é o deslocamento inteiro que representa o valor real zero no espaço quantizado. A dequantização, usada para recuperar uma aproximação de \(x\) na hora do cálculo, é:

\[
\hat{x} = s \cdot (q - z)
\]

\(s\) e \(z\) são calculados a partir do intervalo \([x_{min}, x_{max}]\) dos valores a quantizar:

\[
s = \frac{x_{max} - x_{min}}{2^{b} - 1}, \qquad z = \text{round}\left(\frac{-x_{min}}{s}\right)
\]

O erro de quantização \(x - \hat{x}\) fica limitado a \(\pm s/2\) no caso ideal. Métodos mais avançados (GPTQ, AWQ) não quantizam peso a peso de forma ingênua: usam informação de segunda ordem (aproximação da Hessiana da função de perda) ou estatísticas de ativação para identificar quais pesos são mais sensíveis, minimizando o impacto na saída do modelo em vez do erro bruto de arredondamento.

**Artigos de referência**

- Dettmers et al., 2022 — *LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale* — [arXiv:2208.07339](https://arxiv.org/abs/2208.07339)
- Frantar et al., 2022 — *GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers* — [arXiv:2210.17323](https://arxiv.org/abs/2210.17323)
- Lin et al., 2023 — *AWQ: Activation-aware Weight Quantization for LLM Compression and Acceleration* — [arXiv:2306.00978](https://arxiv.org/abs/2306.00978)
