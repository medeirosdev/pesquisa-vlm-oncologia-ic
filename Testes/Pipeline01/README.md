# Pipeline 01 — testes

Transformar uma lâmina gigante (WSI) num texto curto que um modelo local pequeno consiga ler: filtrar o fundo, escolher os poucos patches que importam, descrever cada um em texto e juntar tudo num prompt. A ideia completa está em [ideia/IDEIA01Pipeline.md](ideia/IDEIA01Pipeline.md).

## Pastas

| Pasta | O que tem |
|---|---|
| `ideia/` | Descrição da pipeline e imagem de referência |
| `comum/` | Código usado por todos os estágios: caminhos, abrir lâmina, nível da pirâmide, RoIs, filtros de tecido, modelo (QuiltNet) e bancos de frases |
| `estagio1_filtro_tecido/` | Filtro de tecido e recall contra os RoIs anotados |
| `estagio2_roteador/` | Roteador top-k (escolhe os patches) |
| `estagio3_descritores/` | Achado textual por patch |
| `estagio4_agregacao/` | Junta tudo num prompt |
| `validacao/` | Testes do estágio 3 contra a classe real dos RoIs, e o registro dos problemas de métrica |
| `scripts/` | Baixar lâminas do BRACS e rodar a pipeline em todas |
| `resultados/<lamina>/<estagio>/` | Saídas de cada lâmina (fora do git) |

Cada estágio tem um `resultados.md` com o que foi testado e o que deu. [resultados_multilaminas.md](resultados_multilaminas.md) junta os números de todas as lâminas.

## Como rodar

Tudo a partir desta pasta, com o venv dela (`.venv/`). Os caminhos das lâminas, RoIs e modelos estão em `Caminhos/caminhos.md`, na raiz do projeto.

```bash
# uma etapa, uma lâmina (nome ou caminho completo; sem --svs usa a lâmina padrão do caminhos.md)
.venv/bin/python estagio1_filtro_tecido/recall_roi.py --svs BRACS_1370
.venv/bin/python estagio2_roteador/roteador_topk.py --svs BRACS_1370 --banco v2

# a pipeline inteira em todas as lâminas baixadas
.venv/bin/python scripts/rodar_todas_laminas.py

# baixar mais lâminas (credenciais do FTP do BRACS por variável de ambiente)
BRACS_FTP_USER=... BRACS_FTP_PASS=... bash scripts/baixar_laminas.sh
```

A ordem importa: o estágio 1 (`recall_roi.py`) gera a verdade de campo que todos os outros usam, e o estágio 2 gera os embeddings que o 3, o 4 e a validação reaproveitam.

## Dependências do venv

`numpy`, `opencv-python-headless`, `tifffile`, `imagecodecs`, `zarr`, `scikit-image`, `matplotlib`, `open_clip_torch`, `openpyxl`. O teste do KEEP (`validacao/teste_modelo_keep.py`) também precisa de `transformers` e `torchvision`, e ainda não roda por conflito de versão — ver o docstring dele.
