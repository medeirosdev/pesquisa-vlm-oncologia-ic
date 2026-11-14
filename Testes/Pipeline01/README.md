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
| `dados/` | Por dataset (`bracs/`, `tcga/`, `lunghist700/`, `panda/`): listas, download e embeddings do UNI2-h |
| `descritor/` | Descritor por patch: banco de frases e camada treinada no BRACS (`bracs/`), pulmão (`pulmao/`) |
| `roteador/` | Testes do estágio 2 (escolha dos patches) no BRACS |
| `lamina/` | Decisão da lâmina inteira sem MIL (classificador, agregação, resposta em conjunto) no BRACS |
| `mil/` | MIL com atenção (`mil_atencao.py`) e testes por dataset (`bracs/`, `tcga/`, `panda/`); `gat_mil/`: MIL com atenção em grafo |
| `prelaudo/` | Pré-laudo por dataset (`bracs/`, `tcga/`, `panda/`) |
| `dcis_ic/` | DCIS × carcinoma invasivo: vizinhança, núcleos, BACH |
| `nucleos/` | Núcleos com o CellViT e validação no NuCLS |
| `ferramentas/` | Rodar a pipeline em todas as lâminas, mapas de calor, imagens da página, exportação |
| `notas/` | Registro dos testes de validação, problemas de métrica e tabela de todas as lâminas |
| `resultados/<lamina>/<estagio>/` | Saídas de cada lâmina (fora do git) |

Cada estágio tem um `resultados.md` com o que foi testado e o que deu. [notas/resultados_multilaminas.md](notas/resultados_multilaminas.md) junta os números de todas as lâminas.

## Como rodar

Tudo a partir desta pasta, com o venv dela (`.venv/`). Os caminhos das lâminas, RoIs e modelos estão em `Caminhos/caminhos.md`, na raiz do projeto.

```bash
# uma etapa, uma lâmina (nome ou caminho completo; sem --svs usa a lâmina padrão do caminhos.md)
.venv/bin/python estagio1_filtro_tecido/recall_roi.py --svs BRACS_1370
.venv/bin/python estagio2_roteador/roteador_topk.py --svs BRACS_1370 --banco v2

# a pipeline inteira em todas as lâminas baixadas
.venv/bin/python ferramentas/rodar_todas_laminas.py

# baixar mais lâminas (credenciais do FTP do BRACS por variável de ambiente)
BRACS_FTP_USER=... BRACS_FTP_PASS=... bash dados/bracs/baixar_laminas.sh
```

A ordem importa: o estágio 1 (`recall_roi.py`) gera a verdade de campo que todos os outros usam, e o estágio 2 gera os embeddings que o 3, o 4 e a validação reaproveitam.

## Dependências do venv

`numpy`, `opencv-python-headless`, `tifffile`, `imagecodecs`, `zarr`, `scikit-image`, `matplotlib`, `open_clip_torch`, `openpyxl`. O teste do KEEP (`descritor/bracs/teste_modelo_keep.py`) também precisa de `transformers` e `torchvision`, e ainda não roda por conflito de versão — ver o docstring dele.
