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

## Em aberto

- Decidir entre similaridade bruta (simples, mas com viés de frase confirmado) e normalizada por z-score (menos enviesada, não validada) — precisa de alguma checagem contra classe real do patch pra desempatar.
- Testar achados em k maior (128, 256) pra ver se a homogeneidade de "todos iguais" se mantém fora do top-32 mais restrito.
- Adicionar frase neutra tipo "non-specific epithelium" ao banco, pra dar uma saída pra patches que não casam bem com nenhum achado específico.
- Ainda sem H&E/densidade nuclear — só entram se a curva pedir, como documentado.
