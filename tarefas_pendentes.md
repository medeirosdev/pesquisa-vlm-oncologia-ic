# Tarefas pendentes

Estado em 06/11/2026. Resultados em [resultados.md](resultados.md); histórico em [linha_do_tempo.md](linha_do_tempo.md); ideias em [brainstorming_melhorias.md](brainstorming_melhorias.md).

Ordem sugerida: 1) terminar a redação e a checagem do texto; 2) terminar o pacote com cotas; 3) concentração espacial e recuperar o DCIS; 4) MIL, depois do download do treino; 5) confirmar nas 30 lâminas de teste não usadas.

## Testes em andamento (pausados em 25/10, retomam de onde pararam)

- [x] **Classificador da lâmina inteira**: 21/57, acurácia balanceada 0,424 (passou, dentro do ruído). Ver `resultados.md`.
- [ ] **Pacote com cota fixa por classe** (`validacao/pacote_cotas.py`, pré-registro `b7505c7`): 8 benignos, 6 atípicos, 6 DCIS, 6 IC; braços A (suspeitos), B (cotas), C (cotas + proporção), com Gemma 3 4B decidindo, nas 61 de validação. Critério: acurácia balanceada C > A. Parou em 30 de 183 pré-laudos (~3 h; precisa do Ollama do HD). Rodar depois da redação, um de cada vez.

Comandos (na pasta `Testes/Pipeline01`):

```
# Ollama do HD no ar (OLLAMA_MODELS=<HD>/Modelos/ollama OLLAMA_KEEP_ALIVE=0 <HD>/Modelos/ollama-bin/bin/ollama serve), depois:
CUDA_VISIBLE_DEVICES="" systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 .venv/bin/python validacao/pacote_cotas.py --etapa sintetizar
```

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

## Decisão da lâmina (o gargalo)

- [x] **Triagem binária**: não passou (sensibilidade 0,95, especificidade 0, AUC 0,52; com negativos, exploratório: 0,98, 0,15, 0,65).
- [x] **Abstenção**: passou, ganho pequeno (decide em 56% das lâminas, 0,478 contra 0,424).
- [ ] ★ **Concentração espacial dos patches suspeitos** como atributo da lâmina (hipótese vinda de dois mapas de calor: na lâmina de IC formam um bloco; na benigna ficam espalhados). Pode ajudar a separar benigno de atípico, o ponto mais fraco. Fixar critério antes.
- [ ] Confirmar a melhor versão nas 30 lâminas de teste oficiais ainda não usadas (exige baixar).
- [ ] **MIL com atenção** (ABMIL/CLAM; TransMIL depois) nas lâminas de treino, depois que os embeddings do treino estiverem prontos. A atenção também escolhe os patches (roteador) e explica a decisão.
- [x] **Hierárquico no nível da lâmina**: passou por pouco (0,437); com negativos, exploratório, 0,490 (29/57). Falta confirmar com critério fixado antes.

## Descritor

- [x] **Lâminas benignas como negativos**: passou, o melhor até aqui (27/57, 0,470; falsos DCIS + IC nas benignas 23% → 7%).
- [ ] ★ **Recuperar o DCIS**: com os negativos, o DCIS caiu de 4 para 1 de 8 lâminas.
- [ ] **Outros codificadores** (CONCH, Virchow2, H-optimus) no lugar do UNI2-h, sobretudo pro atípico. Exigem pedir acesso no Hugging Face.
- [ ] **Duas escalas** (40x + 10x): DCIS × IC e o atípico dependem da arquitetura do ducto. Exige baixar as lâminas de novo.
- [ ] Reduzir a confusão maligno → atípico; métrica pro estágio 2 em lâminas benignas/atípicas (da lista antiga).

## Explicabilidade

- [x] **Mapa de calor da lâmina**: `scripts/mapas_de_calor.py`; 4 exemplos na página. Falta refazer com o descritor com negativos.
- [x] **Coeficientes do classificador da lâmina**: em `resultados/classificador_lamina/resumo.json`.

## Texto (estágio 5) e avaliação

- [ ] **Modelo de linguagem só redige**, a partir de campos fixos: rodando em 06/11 (`validacao/prelaudo_campos.py --etapa redigir`, 57 pré-laudos). Depois: `--etapa checar`.
- [ ] **Checagem automática do texto**: pronta no mesmo script; roda quando a redação terminar.
- [ ] ★ **Avaliação por patologista**: 10–15 pré-laudos com rubrica (clareza, utilidade, erros, alucinações).
- [x] **Comparar com os números publicados no BRACS**: UNI + ABMIL, 3 classes, 0,687; aqui, 0,496 (indicativa). Ver `resultados.md`.

## Documentação e repositório

- [ ] Página `docs/visao_geral`: atualizada com a seção "Decisão da lâmina", figuras e tabela final; falta o resultado da redação e do pacote com cotas, e publicar.
- [ ] Atualizar `resultados.md` e `linha_do_tempo.md` com a redação e o pacote com cotas quando terminarem.
- [ ] Enviar ao GitHub os commits locais ainda não enviados (desde `c611a32`).

## Observação

- 24/10: os processos do HUC-Project que ocupavam a GPU foram parados (`gpu_queue.sh`, `05_local_llm_ollama.py --model gemma2:2b`, runner e `ollama serve`). Os jobs da fila do HUC precisam ser reiniciados lá quando for o caso.
