# Visão geral da Pipeline Ideia 01

Página estática (`index.html` + `img/`) com os cinco estágios da pipeline, as métricas, exemplos de resultado e os problemas de cada parte. Não depende de build: abre direto no navegador.

## Publicação

A pasta fica dentro de `docs/`, então é publicada junto com o site MkDocs (a Action `.github/workflows/docs.yml` roda `mkdocs gh-deploy` a cada push que altera `docs/`). O MkDocs copia o `index.html` e as imagens sem alterá-los; a página fica em `<site>/visao_geral/`.

## Regenerar as imagens

    cd Testes/Pipeline01
    .venv/bin/python scripts/gerar_imagens_visao_geral.py

O script lê as saídas já calculadas dos estágios (é preciso ter o HD com as lâminas montado).

## Licenças das imagens

- Lâminas: BRACS (Brancati et al., Database, 2022), CC BY-NC 4.0 — uso não comercial, com atribuição (feita no rodapé da página).
- Núcleos anotados: NuCLS (Amgad et al., GigaScience, 2022), CC0.
- BACH: CC BY-NC-ND, por isso nenhuma imagem dele é reproduzida; só os números.
