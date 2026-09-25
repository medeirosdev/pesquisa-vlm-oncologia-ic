# Resultados 02 — Roteador top-k (estágio 2)

**Lâmina testada:** `BRACS_748.svs` (mesma do estágio 1)
**Script:** [roteador_topk.py](roteador_topk.py)
**Modelo:** QuiltNet-B-32 (CLIP ViT-B/32 treinado no Quilt-1M), via `open_clip`, GPU
**Banco de frases (v1, usado nesta primeira rodada):** `tumor nests`, `necrosis`, `high nuclear pleomorphism`, `mitotic figures`, `dense atypical stroma` (o mesmo banco já especificado para o estágio 3 em `docs/pipelines.md`), score = similaridade máxima. Ver seção "Banco v2" mais abaixo para a versão expandida (benigno/suspeito) e a comparação.

## Método

Sobre os tiles com tecido do estágio 1 (máscara Otsu-S + morfologia), foi montada uma grade de tiles de 512px no nível nativo da pirâmide (~40x), lidos por janela via zarr — sem carregar a lâmina inteira em memória — e reduzidos a 256px (~20x, a magnificação de trabalho documentada). Cada tile foi pontuado pela maior similaridade contrastiva contra o banco de frases. Um gate de diversidade espacial (supressão gulosa por distância mínima entre centros) evita selecionar tiles vizinhos quase idênticos.

**Simplificação registrada:** não há mecanismo de saliência/atenção treinado disponível — o modo "rótulo fixo" (BRACS) usa a mesma similaridade contrastiva do modo VQA (banco de frases fixo em vez do texto de uma pergunta). É uma aproximação de saliência, não saliência de verdade.

**15.138 tiles candidatos** com tecido suficiente (grade de 512px). Pontuação de todos em **135s** na GPU disponível (~8,9ms/tile) — confirma que este estágio é barato mesmo em hardware modesto, ordem de grandeza abaixo de rodar uma VLM geradora por tile.

## Curva custo × fidelidade

Ground-truth: os mesmos 98 RoIs anotados usados na validação do estágio 1. Um tile "acerta" se sua caixa se sobrepõe à caixa de algum RoI.

| k | tiles selecionados | % da lâmina | precisão@k | recall@k | RoIs cobertos | tokens de texto estimados |
|---|---|---|---|---|---|---|
| 8 | 8 | 0.05% | 0.62 | 0.05 | 5/98 | ~360 |
| 16 | 16 | 0.11% | 0.50 | 0.07 | 7/98 | ~720 |
| 32 | 32 | 0.21% | 0.62 | 0.19 | 19/98 | ~1.440 |
| 64 | 64 | 0.42% | 0.56 | 0.33 | 32/98 | ~2.880 |
| 128 | 128 | 0.85% | 0.48 | 0.51 | 50/98 | ~5.760 |
| 256 | 256 | 1.69% | 0.43 | 0.69 | 68/98 | ~11.520 |
| 512 | 512 | 3.38% | 0.35 | 0.82 | 80/98 | ~23.040 |
| 1024 | 1024 | 6.76% | 0.33 | 0.92 | 90/98 | ~46.080 |

(Estimativa de tokens: ~45 tokens/patch, meio da faixa de 30–60 documentada para o estágio 3. Curva completa em `resultados/BRACS_748/estagio2/estagio2_curva.json`.)

**Baseline aleatório** (200 amostras de k tiles aleatórios entre os 15.138 candidatos, mesma métrica): precisão média **0.18** para qualquer k testado — o roteador fica **~2–3x acima do acaso** em toda a faixa testada.

Ver overlays: [k=64](../resultados/BRACS_748/estagio2/estagio2_topk_overlay.png) · [k=512](../resultados/BRACS_748/estagio2/estagio2_topk512_overlay.png) · [k=1024](../resultados/BRACS_748/estagio2/estagio2_topk1024_overlay.png).

## Leitura honesta do resultado

**O trade-off é real e mensurável:** recall sobe de 5% (k=8) pra 92% (k=1024), mas com retorno decrescente — cada dobra de k rende cada vez menos recall novo (+18pp, +18pp, +13pp, +10pp por dobra de 128→1024) enquanto a precisão cai de 0,62 pra 0,33. Não existe "k certo" universal — é uma escolha de orçamento: em k≈256–512 já se cobre 69–82% dos achados anotados gastando 2–3% da lâmina; ir além de 512 custa caro (dobra os tokens) pra ganhar cada vez menos recall.

**Ponto de atenção que a curva expõe:** em k=1024 o custo estimado (~46k tokens de texto) já é grande pra um modelo de contexto modesto — o "1–2k tokens" documentado no estágio 4 vale pra k≈32–64, não pra k=1024. Se a meta for cobertura alta (>80% dos achados), a pipeline não fica mais tão "enxuta" quanto o desenho original sugeria.

Duas explicações prováveis pra precisão nunca passar de ~0,6, não mutuamente exclusivas:

1. **Os RoIs do BRACS são exemplos curados**, não uma anotação exaustiva de "todo pixel diagnosticamente relevante". Um tile "errado" (fora de qualquer caixa de RoI) pode ainda estar em tecido epitelial genuinamente atípico que só não foi um dos 98 recortes escolhidos pelo patologista para anotar — ou seja, parte do que a métrica chama de "erro" pode não ser erro real do roteador.
2. **O banco de frases é genérico** (não específico por classe BRACS) — não diferencia "isso é um ADH" de "isso é um DCIS", só "isso parece atípico". Pra discriminar entre as 7 classes do BRACS, provavelmente precisa de um banco de frases por classe ou um modelo mais específico.

## Banco v2: benigno/suspeito, score = margem

Motivação (ver `docs/questoes.md`): o banco v1 só tem frases "suspeitas" — não existe opção "nada disso", então até tecido normal recebe uma similaridade máxima razoável com alguma das 5. O banco v2 separa em dois grupos e o score vira uma margem, não um máximo isolado:

```python
BANCO_V2 = {
    "benigno": ["normal duct epithelium", "normal lobular tissue", "adipose tissue",
                "benign fibrous stroma", "usual ductal hyperplasia"],
    "suspeito": ["tumor nests", "necrosis", "comedonecrosis", "high nuclear pleomorphism",
                 "nuclear crowding and stratification", "mitotic figures", "cribriform architecture",
                 "micropapillary architecture", "solid growth pattern", "stromal invasion",
                 "desmoplastic stroma"],
}
score = max_similaridade(suspeito) − max_similaridade(benigno)
```

Os embeddings de imagem já calculados na rodada v1 foram reaproveitados (salvos em `estagio2_embeddings.npy`) — trocar de banco não custou reprocessar as imagens, só o lado de texto (segundos, não minutos).

| k | v1 precisão / recall | v2 precisão / recall |
|---|---|---|
| 8 | 0.62 / 0.05 | 0.38 / 0.03 |
| 16 | 0.50 / 0.07 | 0.50 / 0.08 |
| 32 | 0.62 / 0.19 | 0.56 / 0.18 |
| 64 | 0.56 / 0.33 | 0.52 / 0.27 |
| 128 | 0.48 / 0.51 | 0.55 / 0.44 |
| 256 | 0.43 / 0.69 | 0.55 / 0.60 |
| 512 | 0.35 / 0.82 | 0.44 / 0.84 |
| 1024 | 0.33 / 0.92 | 0.34 / 0.97 |

Overlay: [k=1024, banco v2](../resultados/BRACS_748/estagio2/estagio2_topk_overlay_v2.png).

**Não é vitória limpa — é um trade-off diferente, não estritamente melhor:**

- **k baixo (8–64):** v1 tem recall e/ou precisão iguais ou levemente melhores que v2. A margem contra "benigno" parece descartar alguns tiles verdadeiros que o v1 (só o máximo) ainda pegava.
- **k médio (128–256):** v2 ganha em precisão (0.55 vs 0.43–0.48) mas perde em recall (0.44–0.60 vs 0.51–0.69) — mais seletivo, mais "limpo", mas cobre menos RoIs no mesmo orçamento.
- **k alto (512–1024):** v2 empata ou supera o v1 nos dois eixos ao mesmo tempo (ex. k=512: precisão 0.44 vs 0.35, recall 0.84 vs 0.82).

Ou seja: a margem contra benigno ajuda a discriminar melhor quando o orçamento de patches é generoso, mas em orçamento apertado (k≤64, o regime mais realista pro "hardware modesto") não há ganho claro — pode até piorar levemente. Não dá pra dizer "banco v2 é melhor" sem qualificar em que k.

## Em aberto

- Achar o "cotovelo" da curva com mais granularidade entre 128 e 512 (ex. 192, 384) — a região onde o retorno decrescente começa a valer a pena parar.
- Investigar por que o banco v2 perde pro v1 em k baixo — testar pesos diferentes na margem (ex. penalizar benigno menos) em vez de subtração direta 1:1.
- Repetir com um banco de frases específico por classe BRACS (não só benigno/suspeito) e comparar a curva.
- Testar KEEP ou CONCH (candidatos mais fortes na aba Modelos Locais) no lugar do QuiltNet-B-32, mesma metodologia, comparar a curva custo×fidelidade entre eles.
- Como no estágio 1: bloqueado por dado pra repetir em outras lâminas (só há uma `.svs` local).
