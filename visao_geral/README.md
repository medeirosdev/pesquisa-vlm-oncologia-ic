# Visão geral da Pipeline Ideia 01

Página estática (`index.html` + `img/`) com os cinco estágios da pipeline, as métricas, exemplos de resultado e os problemas de cada parte. Não depende de build: abre direto no navegador.

## Hospedar no GitHub Pages

Em *Settings → Pages* do repositório, escolher a branch e a pasta que contém este `index.html`. Se o site MkDocs já ocupa o GitHub Pages do repositório, uma alternativa é copiar esta pasta para `docs/visao_geral/`: o MkDocs copia arquivos estáticos e a página fica em `<site>/visao_geral/`.

## Regenerar as imagens

    cd Testes/Pipeline01
    .venv/bin/python scripts/gerar_imagens_visao_geral.py

O script lê as saídas já calculadas dos estágios (é preciso ter o HD com as lâminas montado).

## Licenças das imagens

- Lâminas: BRACS (Brancati et al., Database, 2022), CC BY-NC 4.0 — uso não comercial, com atribuição (feita no rodapé da página).
- Núcleos anotados: NuCLS (Amgad et al., GigaScience, 2022), CC0.
- BACH: CC BY-NC-ND, por isso nenhuma imagem dele é reproduzida; só os números.
