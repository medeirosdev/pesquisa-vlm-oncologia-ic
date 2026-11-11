# Tarefas pendentes

Estado em 10/11/2026. Resultados em [resultados.md](resultados.md); histórico em [linha_do_tempo.md](linha_do_tempo.md); ideias em [brainstorming_melhorias.md](brainstorming_melhorias.md).

Ordem sugerida: 1) resolver a cobrança do GitHub e publicar a página; 2) baixar as 379 lâminas de treino e treinar o MIL com elas (o MIL com 79 lâminas já chegou a 38/57); 3) recuperar o DCIS; 4) refazer o pacote com cotas com o descritor corrigido; 5) confirmar nas 30 lâminas de teste não usadas.

Desde 07/11, todo teste usa o agrupamento oficial do BRACS (UDH em benigno). Resultados anteriores usam o agrupamento antigo e estão marcados em `resultados.md`.

## Testes em andamento

- [x] **Classificador da lâmina inteira**: refeito com o rótulo oficial (`validacao/rotulo_oficial.py`): com negativos, 29/57, acurácia balanceada 0,505 (passou por pouco). Ver `resultados.md`.
- [x] **Corrigir o agrupamento do UDH** (era atípico; no BRACS é benigno): código corrigido, testes de lâmina refeitos ou repontuados.
- [ ] **Pacote com cota fixa por classe** (`validacao/pacote_cotas.py`, pré-registro `b7505c7`): 8 benignos, 6 atípicos, 6 DCIS, 6 IC; braços A (suspeitos), B (cotas), C (cotas + proporção), com Gemma 3 4B decidindo, nas 61 de validação. Critério: acurácia balanceada C > A. Parou em 30 de 183 pré-laudos. **Precisa recomeçar do zero:** os prompts vêm do descritor com o agrupamento antigo. Regerar com `--etapa descrever` (descritor corrigido) e só então rodar `--etapa sintetizar` (~3 h; Ollama do HD).

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

- [x] **Triagem binária**: não passou. Rótulo oficial, com negativos: maligno × resto AUC 0,83, suspeito × benigno AUC 0,66; nos dois, o limiar do treino com sensibilidade ≥ 0,90 derruba a especificidade no teste.
- [x] **Abstenção**: passou, ganho pequeno (agrupamento antigo; não refeita).
- [x] **Concentração espacial dos patches suspeitos**: não passou (AUC benigno × atípico 0,58 → 0,61). Nas benignas, os falsos positivos também ficam agrupados.
- [ ] Confirmar a melhor versão nas 30 lâminas de teste oficiais ainda não usadas (exige baixar).
- [x] **Resposta em conjunto** (benigno, atípico, "benigno ou atípico", maligno): não passou (acerto do conjunto 0,70, respostas exatas 0,44). A métrica fica para os próximos testes; o alvo de 0,80 no treino foi alto demais.
- [x] **MIL com atenção, versão pequena (79 lâminas)**: passou nos dois critérios: 38/57, acurácia balanceada 0,626; benigno × atípico AUC 0,78 (descritor: 0,58). Confirmado em validação cruzada por paciente nas 79: 57/79, 0,680; benigno × atípico 0,92.
- [ ] ★ **MIL com as 379 lâminas de treino** (depois do download): mesmo modelo, critério fixado antes. Comparar também com CLAM/TransMIL.
- [x] **A atenção do MIL cai nas lesões?** Passou: os 5% de maior atenção ficam 5× mais nas lesões anotadas que o acaso (21 de 29 lâminas).
- [x] **Mapas de atenção do MIL**: 4 exemplos na página (`scripts/mapas_de_calor.py --atencao`).
- [x] **Pré-laudo com o MIL**: passou (57/57 classe igual; 0 números sem sustentação; 38/57 classe final). Mas em 15 lâminas "benigno" com região de atenção maligna/atípica, só 1 texto aponta a contradição.
- [ ] ★ **Sinalizar contradições nos campos** (ex.: "atenção: regiões de maior peso descritas como malignas, apesar da classe benigna") e medir de novo.
- [x] **Hierárquico no nível da lâmina**: rótulo oficial, com negativos, 31/57, 0,518 (0,560 em 3 classes), sem critério. Falta confirmar com critério fixado antes.

## Descritor

- [x] **Lâminas benignas como negativos**: o melhor até aqui. Rótulo oficial: 29/57, 0,505; falsos DCIS + IC nas benignas 21% → 7%.
- [ ] ★ **Recuperar o DCIS**: com os negativos, o DCIS fica em 1–2 de 8 lâminas.
- [ ] **Outros codificadores** (CONCH, Virchow2, H-optimus) no lugar do UNI2-h, sobretudo pro atípico. Exigem pedir acesso no Hugging Face.
- [ ] **Duas escalas** (40x + 10x): DCIS × IC e o atípico dependem da arquitetura do ducto. Exige baixar as lâminas de novo.
- [ ] Reduzir a confusão maligno → atípico; métrica pro estágio 2 em lâminas benignas/atípicas (da lista antiga).

## Explicabilidade

- [x] **Mapa de calor da lâmina**: `scripts/mapas_de_calor.py`; 4 exemplos na página. Falta refazer com o descritor corrigido e com negativos.
- [x] **Coeficientes do classificador da lâmina**: em `resultados/classificador_lamina/resumo.json`.

## Texto (estágio 5) e avaliação

- [x] **Modelo de linguagem só redige**, a partir de campos fixos (`validacao/prelaudo_campos.py`): passou (classe igual à sugerida em 57/57; 0 números sem sustentação, contra 2,1% nos antigos). Os campos vieram do classificador de 06/11 (agrupamento antigo); a checagem do texto não depende disso.
- [x] **Checagem automática do texto**: no mesmo script. Não detecta achados morfológicos inventados; isso fica para a leitura por patologista.
- [ ] Refazer os campos com o classificador corrigido (rótulo oficial + negativos) antes de usar os textos como exemplo.
- [ ] ★ **Avaliação por patologista**: 10–15 pré-laudos com rubrica (clareza, utilidade, erros, alucinações).
- [x] **Comparar com os números publicados no BRACS**: UNI + ABMIL, 3 classes, 0,687; aqui, 0,518 (0,560 no hierárquico), comparação indicativa. Ver `resultados.md`.

## Documentação e repositório

- [ ] **Publicar a página**: os commits estão no GitHub, mas a publicação falhou em 07/11 porque a conta está bloqueada por cobrança ("account is locked due to a billing issue"). Depois de resolver em GitHub → Settings → Billing, um novo push em `docs/` publica de novo.
- [ ] Atualizar `resultados.md`, `linha_do_tempo.md` e a página com o pacote com cotas quando for refeito.
- [ ] Decidir as edições de 07/11 ainda sem commit em `docs/` (datasets, pipelines, metodologia, modelos-locais, index), nos READMEs, na `linha_do_tempo.md` e no `brainstorming_melhorias.md`.

## Observação

- 24/10: os processos do HUC-Project que ocupavam a GPU foram parados (`gpu_queue.sh`, `05_local_llm_ollama.py --model gemma2:2b`, runner e `ollama serve`). Os jobs da fila do HUC precisam ser reiniciados lá quando for o caso.
