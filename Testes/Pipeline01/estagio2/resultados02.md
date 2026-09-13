# Resultados 02 — Roteador top-k (estágio 2)

**Lâmina testada:** `BRACS_748.svs` (mesma do estágio 1)
**Script:** [roteador_topk.py](roteador_topk.py)
**Modelo:** QuiltNet-B-32 (CLIP ViT-B/32 treinado no Quilt-1M), via `open_clip`, GPU
**Banco de frases:** `tumor nests`, `necrosis`, `high nuclear pleomorphism`, `mitotic figures`, `dense atypical stroma` (o mesmo banco já especificado para o estágio 3 em `docs/pipelines.md`)

## Método

Sobre os tiles com tecido do estágio 1 (máscara Otsu-S + morfologia), foi montada uma grade de tiles de 512px no nível nativo da pirâmide (~40x), lidos por janela via zarr — sem carregar a lâmina inteira em memória — e reduzidos a 256px (~20x, a magnificação de trabalho documentada). Cada tile foi pontuado pela maior similaridade contrastiva contra o banco de frases. Um gate de diversidade espacial (supressão gulosa por distância mínima entre centros) evita selecionar tiles vizinhos quase idênticos.

**Simplificação registrada:** não há mecanismo de saliência/atenção treinado disponível — o modo "rótulo fixo" (BRACS) usa a mesma similaridade contrastiva do modo VQA (banco de frases fixo em vez do texto de uma pergunta). É uma aproximação de saliência, não saliência de verdade.

**15.138 tiles candidatos** com tecido suficiente (grade de 512px). Pontuação de todos em **135s** na GPU disponível (~8,9ms/tile) — confirma que este estágio é barato mesmo em hardware modesto, ordem de grandeza abaixo de rodar uma VLM geradora por tile.

## Curva custo × fidelidade

Ground-truth: os mesmos 98 RoIs anotados usados na validação do estágio 1. Um tile "acerta" se sua caixa se sobrepõe à caixa de algum RoI.

| k | tiles selecionados | precisão@k | recall@k | RoIs cobertos |
|---|---|---|---|---|
| 8 | 8 | 0.62 | 0.05 | 5/98 |
| 16 | 16 | 0.50 | 0.07 | 7/98 |
| 32 | 32 | 0.62 | 0.19 | 19/98 |
| 64 | 64 | 0.56 | 0.33 | 32/98 |

**Baseline aleatório** (200 amostras de k tiles aleatórios entre os 15.138 candidatos, mesma métrica): precisão média **0.18** para qualquer k testado.

→ O roteador acerta **~3x mais que o acaso** em todos os valores de k — sinal real, não ruído.

Ver [outputs/BRACS_748/estagio2_topk_overlay.png](outputs/BRACS_748/estagio2_topk_overlay.png) (tiles selecionados em laranja): visualmente, a seleção se concentra na mesma região roxo-densa onde estão os RoIs reais, consistente com o número.

## Leitura honesta do resultado

Precisão fica estável em ~0.5–0.6 (não sobe com k) e recall cresce devagar com k (33% em k=64, de um total de 98 RoIs). Duas explicações prováveis, não mutuamente exclusivas:

1. **Os RoIs do BRACS são exemplos curados**, não uma anotação exaustiva de "todo pixel diagnosticamente relevante". Um tile "errado" (fora de qualquer caixa de RoI) pode ainda estar em tecido epitelial genuinamente atípico que só não foi um dos 98 recortes escolhidos pelo patologista para anotar — ou seja, parte do que a métrica chama de "erro" pode não ser erro real do roteador.
2. **O banco de frases é genérico** (não específico por classe BRACS) — não diferencia "isso é um ADH" de "isso é um DCIS", só "isso parece atípico". Pra discriminar entre as 7 classes do BRACS, provavelmente precisa de um banco de frases por classe ou um modelo mais específico.

## Em aberto

- Repetir com um banco de frases mais específico (por classe BRACS) e comparar a curva.
- Testar KEEP ou CONCH (candidatos mais fortes na aba Modelos Locais) no lugar do QuiltNet-B-32, mesma metodologia, comparar a curva custo×fidelidade entre eles.
- Como no estágio 1: bloqueado por dado pra repetir em outras lâminas (só há uma `.svs` local).
