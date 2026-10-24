# Tarefas pendentes

Estado em 24/10/2026. Resultados em [resultados.md](resultados.md); histórico em [linha_do_tempo.md](linha_do_tempo.md); ideias em [brainstorming_melhorias.md](brainstorming_melhorias.md).

## Embeddings das lâminas (UNI2-h, amostra de 2.000 patches)

- [ ] **Validação: faltam 2 de 63** (`BRACS_1003660`, `BRACS_1003661`). As duas já estão no HD e abrem normalmente; falharam por falta de memória na GPU (ollama do HUC-Project rodando junto). Basta rodar de novo o comando da validação com a GPU livre (~2 min).
- [ ] **Treino: 379 lâminas** (`Testes/Pipeline01/scripts/lista_treino.txt`).
  - Custo estimado pela validação: ~6,4 min por lâmina → ~40 h no total; GPU ~1,8 GB; RAM ~4–4,5 GB no pico; disco ~4,3 GB de embeddings (uma lâmina por vez, apagada depois); rede: algumas centenas de GB.
  - Retoma de onde parou; pode rodar em várias noites.
  - Antes de rodar: GPU livre (nada do HUC-Project nem outro ollama).

Comando (na pasta `Testes/Pipeline01`, HD montado, credenciais do FTP exportadas em `BRACS_FTP_USER` / `BRACS_FTP_PASS`):

```
systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 \
  .venv/bin/python scripts/baixar_e_embutir.py scripts/lista_validacao.txt   # ou lista_treino.txt
```

## Experimentos

- [ ] Calibrar ou aprender a decisão da lâmina inteira nas lâminas de validação (embeddings `amostra2000`), sem tocar nas 57 do teste. Fixar regra e critério em commit antes de rodar.
- [ ] MIL com atenção (ABMIL/CLAM) nas lâminas de treino, depois que os embeddings do treino estiverem prontos.

## Documentação e repositório

- [ ] Atualizar a página `docs/visao_geral` com o resultado de 22/10 (lâmina inteira + descritor das RoIs).
- [ ] Enviar ao GitHub os commits locais ainda não enviados (desde `c611a32`).

## Observação

- 24/10: os processos do HUC-Project que ocupavam a GPU foram parados (`gpu_queue.sh`, `05_local_llm_ollama.py --model gemma2:2b`, runner e `ollama serve`). Os jobs da fila do HUC precisam ser reiniciados lá quando for o caso.
