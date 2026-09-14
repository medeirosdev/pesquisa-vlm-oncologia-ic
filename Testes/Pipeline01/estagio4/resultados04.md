# Resultados 04 — Agregação (estágio 4)

**Lâmina:** `BRACS_748.svs` | **k:** 32 (padrão documentado)
**Script:** [agregador.py](agregador.py)

## O que faz

Sem modelo novo — só monta o prompt final a partir do que já existe: os blocos de texto do estágio 3, um cabeçalho slide-level (contagens agregadas dos próprios achados) e 1–3 patches de maior score do roteador como âncora visual (docs/pipelines.md: não mais que isso, token visual cresce rápido).

## Tamanho bateu com o documentado

| Versão | Tokens de texto | Tokens visuais (~3 âncoras) | Total |
|---|---|---|---|
| Bruto | 244 | ~1.200 | ~1.444 |
| Normalizado | 236 | ~1.200 | ~1.436 |

Fica dentro do "~1–2k tokens" que `docs/pipelines.md` prevê pra saída da agregação, em k=32.

## O estágio 4 herda o problema do estágio 3 — e agora dá pra ver o efeito real

Como a agregação só resume o que o estágio 3 entregou, a decisão pendente (similaridade bruta vs. normalizada por z-score) muda o que o **cabeçalho slide-level** — a parte que resume tudo pra quem for ler — efetivamente afirma:

**Bruto:**
```
- high nuclear pleomorphism: 32/32 patches (100%)
- mitotic figures: 32/32 patches (100%)
Achado dominante: high nuclear pleomorphism (100% dos patches)
```

**Normalizado:**
```
- mitotic figures: 28/32 patches (88%)
- solid growth pattern: 24/32 patches (75%)
- comedonecrosis: 11/32 patches (34%)
- high nuclear pleomorphism: 1/32 patches (3%)
Achado dominante: mitotic figures (88% dos patches)
```

Mesmos 32 patches, mesmas coordenadas, mesmas imagens-âncora — dois "achados dominantes" praticamente opostos (`high nuclear pleomorphism` em 100% dos patches no bruto vira 3% no normalizado). Isso não é um detalhe cosmético: é o tipo de frase que iria direto pra um pré-laudo gerado por uma VLM no estágio 5. **A pendência do estágio 3 deixou de ser uma nota de rodapé técnica — ela decide o que o sistema alegaria ter encontrado.**

As âncoras visuais (mesmas 3 coordenadas nos dois casos, porque a seleção vem do roteador do estágio 2, que não muda entre bruto/normalizado) estão em `outputs/BRACS_748/estagio4_prompt_k32{,_norm}_ancoras/`.

## Em aberto

- Isso reforça, com um exemplo concreto, a prioridade já registrada no estágio 3: decidir bruto vs. normalizado (ou achar uma terceira opção) antes de avançar pro estágio 5 — sem isso, o pré-laudo final é uma moeda jogada entre duas narrativas diferentes pros mesmos dados.
- Ainda não testei o prompt agregado numa VLM de verdade (estágio 5) — os dois arquivos `.txt` gerados aqui são exatamente o que entraria lá.
