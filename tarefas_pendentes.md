# Tarefas pendentes

Estado em 26/10/2026. Resultados em [resultados.md](resultados.md); histórico em [linha_do_tempo.md](linha_do_tempo.md); ideias em [brainstorming_melhorias.md](brainstorming_melhorias.md).

Ordem sugerida: 1) retomar os testes em andamento; 2) triagem binária com abstenção; 3) mapas de calor; 4) descritor com lâminas benignas como negativos; 5) MIL, depois do download do treino.

## Testes em andamento (pausados em 25/10, retomam de onde pararam)

- [ ] **Classificador da lâmina inteira** (`validacao/classificador_lamina.py`, pré-registro `6b0ad76`, correção de memória `0b4af6b`): 12 atributos do descritor + logística, 4 classes; treino em 79 lâminas (61 validação + 18 desenvolvimento), teste nas 57. Critério: acurácia balanceada > 0,406. Parou em 3 de 18 lâminas de desenvolvimento (~30 min pra terminar; só CPU).
- [ ] **Pacote com cota fixa por classe** (`validacao/pacote_cotas.py`, pré-registro `b7505c7`): 8 benignos, 6 atípicos, 6 DCIS, 6 IC; braços A (suspeitos), B (cotas), C (cotas + proporção), com Gemma 3 4B decidindo, nas 61 de validação. Critério: acurácia balanceada C > A. Parou em 30 de 183 pré-laudos (~3 h; precisa do Ollama do HD).

Comandos (na pasta `Testes/Pipeline01`):

```
CUDA_VISIBLE_DEVICES="" systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 .venv/bin/python validacao/classificador_lamina.py
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

- [ ] ★ **Triagem binária**: "precisa de atenção (atípico ou maligno) ou não?", com alta sensibilidade. Uso mais realista (priorizar a fila do patologista no SUS). Mesmos atributos do classificador da lâmina.
- [ ] ★ **Abstenção ("não sei")**: quando o classificador hesita, a lâmina vai direto ao patologista. Reportar acerto × cobertura.
- [ ] **MIL com atenção** (ABMIL/CLAM; TransMIL depois) nas lâminas de treino, depois que os embeddings do treino estiverem prontos. A atenção também escolhe os patches (roteador) e explica a decisão.
- [ ] **Hierárquico no nível da lâmina**: benigno × não benigno → atípico × maligno → DCIS × IC (sugestão do Prof. João).

## Descritor

- [ ] ★ **Lâminas benignas como negativos**: numa lâmina N/PB nenhum patch é atípico nem maligno (o rótulo da lâmina é o da lesão mais grave), então todos os patches dela são exemplos benignos garantidos. Retreinar o descritor com eles pra cortar os falsos DCIS/IC (ex.: 115 patches "IC" na BRACS_1261, benigna). Usar lâminas de treino, não as de validação.
- [ ] **Outros codificadores** (CONCH, Virchow2, H-optimus) no lugar do UNI2-h, sobretudo pro atípico. Exigem pedir acesso no Hugging Face.
- [ ] **Duas escalas** (40x + 10x): DCIS × IC e o atípico dependem da arquitetura do ducto. Exige baixar as lâminas de novo.
- [ ] Reduzir a confusão maligno → atípico; métrica pro estágio 2 em lâminas benignas/atípicas (da lista antiga).

## Explicabilidade

- [ ] ★ **Mapa de calor da lâmina**: cada patch pintado pela classe e probabilidade prevista. Coordenadas e probabilidades dos 2.000 patches já existem (`resultados/pacote_cotas/*_probs.npz`); figuras pra página e pro orientador.
- [ ] **Coeficientes do classificador da lâmina** (já saem em `resultados/classificador_lamina/resumo.json`): qual atributo pesa em cada classe.

## Texto (estágio 5) e avaliação

- [ ] **Modelo de linguagem só redige**, a partir de campos fixos (classe do classificador, confiança, regiões); não decide a classe.
- [ ] **Checagem automática do texto**: números e classe citados batem com a evidência (mede alucinação).
- [ ] ★ **Avaliação por patologista**: 10–15 pré-laudos com rubrica (clareza, utilidade, erros, alucinações).
- [ ] **Comparar com os números publicados no BRACS** (classificação da lâmina em 7 e em 3 classes), pra saber o que é um bom resultado.

## Documentação e repositório

- [ ] Terminar a página `docs/visao_geral`: topo, estágio 2 (pacote com cotas) e estágio 3 (descritor das RoIs) já editados, sem commit; falta a seção "Decisão da lâmina" (regra de 22/10 + classificador) e a tabela final.
- [ ] Atualizar `resultados.md` e `linha_do_tempo.md` com os dois testes em andamento quando terminarem.
- [ ] Enviar ao GitHub os commits locais ainda não enviados (desde `c611a32`).

## Observação

- 24/10: os processos do HUC-Project que ocupavam a GPU foram parados (`gpu_queue.sh`, `05_local_llm_ollama.py --model gemma2:2b`, runner e `ollama serve`). Os jobs da fila do HUC precisam ser reiniciados lá quando for o caso.
