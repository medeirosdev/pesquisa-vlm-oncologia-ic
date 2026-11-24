# Tarefas pendentes

Estado em 14/11/2026. Resultados em [resultados.md](resultados.md); histórico em [linha_do_tempo.md](linha_do_tempo.md); ideias em [brainstorming_melhorias.md](brainstorming_melhorias.md).

Ordem sugerida: 1) resolver a cobrança do GitHub; 2) baixar as 379 lâminas de treino e treinar o MIL com elas (o MIL com 79 lâminas já chegou a 38/57); 3) recuperar o DCIS; 4) refazer o pacote com cotas com o descritor corrigido; 5) confirmar nas 30 lâminas de teste não usadas.

Desde 07/11, todo teste usa o agrupamento oficial do BRACS (UDH em benigno). Resultados anteriores usam o agrupamento antigo e estão marcados em `resultados.md`.

## Testes em andamento

- [x] **Classificador da lâmina inteira**: refeito com o rótulo oficial (`lamina/bracs/rotulo_oficial.py`): com negativos, 29/57, acurácia balanceada 0,505 (passou por pouco). Ver `resultados.md`.
- [x] **Corrigir o agrupamento do UDH** (era atípico; no BRACS é benigno): código corrigido, testes de lâmina refeitos ou repontuados.
- [ ] **Pacote com cota fixa por classe** (`roteador/bracs/pacote_cotas.py`, pré-registro `b7505c7`): 8 benignos, 6 atípicos, 6 DCIS, 6 IC; braços A (suspeitos), B (cotas), C (cotas + proporção), com Gemma 3 4B decidindo, nas 61 de validação. Critério: acurácia balanceada C > A. Parou em 30 de 183 pré-laudos. **Precisa recomeçar do zero:** os prompts vêm do descritor com o agrupamento antigo. Regerar com `--etapa descrever` (descritor corrigido) e só então rodar `--etapa sintetizar` (~3 h; Ollama do HD).

Comandos (na pasta `Testes/Pipeline01`):

```
# Ollama do HD no ar (OLLAMA_MODELS=<HD>/Modelos/ollama OLLAMA_KEEP_ALIVE=0 <HD>/Modelos/ollama-bin/bin/ollama serve), depois:
CUDA_VISIBLE_DEVICES="" systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 .venv/bin/python roteador/bracs/pacote_cotas.py --etapa sintetizar
```

## Embeddings das lâminas (UNI2-h, amostra de 2.000 patches)

- [ ] **Validação: faltam 2 de 63** (`BRACS_1003660`, `BRACS_1003661`). As duas já estão no HD e abrem normalmente; falharam por falta de memória na GPU (ollama do HUC-Project rodando junto). Basta rodar de novo o comando da validação com a GPU livre (~2 min).
- [ ] **Treino: 379 lâminas** (`Testes/Pipeline01/dados/bracs/lista_treino.txt`).
  - Custo estimado pela validação: ~6,4 min por lâmina → ~40 h no total; GPU ~1,8 GB; RAM ~4–4,5 GB no pico; disco ~4,3 GB de embeddings (uma lâmina por vez, apagada depois); rede: algumas centenas de GB.
  - Retoma de onde parou; pode rodar em várias noites.
  - Antes de rodar: GPU livre (nada do HUC-Project nem outro ollama).

Comando (na pasta `Testes/Pipeline01`, HD montado, credenciais do FTP exportadas em `BRACS_FTP_USER` / `BRACS_FTP_PASS`):

```
systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 \
  .venv/bin/python dados/bracs/baixar_e_embutir.py dados/bracs/lista_validacao.txt   # ou lista_treino.txt
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
- [x] **Mapas de atenção do MIL**: 4 exemplos na página (`ferramentas/mapas_de_calor.py --atencao`).
- [x] **Pré-laudo com o MIL**: passou (57/57 classe igual; 0 números sem sustentação; 38/57 classe final). Mas em 15 lâminas "benigno" com região de atenção maligna/atípica, só 1 texto aponta a contradição.
- [x] **Generalização pra pulmão (TCGA LUAD × LUSC)**: passou. Mesma receita (UNI2-h + MIL, mesma configuração), retreinada com lâminas de pulmão: AUC 0,981, acurácia balanceada 0,949 em 78 lâminas de teste (197 de 200 baixadas). Tarefa mais fácil que a da mama.
- [x] **Pulmão: descritor e pré-laudo** (LungHist700 + TCGA): D1 passou (descritor no LungHist700, 0,926); D2 não passou (regiões de maior atenção com a classe certa em 58/78; LUAD 21/39); P passou (78/78 tipo igual, 0 números sem sustentação, 0 coordenadas inventadas), mas só 3 de 27 textos apontam região discordante.
- [ ] Pulmão: entender por que o descritor chama de "normal" ou "escamoso" as regiões de maior atenção do adenocarcinoma (olhar os patches; patologista); conferir a escala do LungHist700 (razão 20x/40x 1,65, esperado ~2).
- [x] **Próstata (PANDA, grau ISUP 0–5)**: treino 600 do Radboud, teste 300 do Karolinska. M2 passou (benigno × câncer AUC 0,940); M1 não passou (kappa 0,237: prevê ISUP 3 em 209 de 300); D1 não passou (descritor 0,775); A não passou (atenção no câncer em 76%, acaso 43%); P passou (60/60), mas 1 de 35 textos aponta região discordante.
- [x] **GAT-MIL no PANDA** (atenção entre patches vizinhos + ABMIL, `mil/gat_mil/`, pré-registro `6c698d7`): passou nos dois. Entre centros, kappa 0,237 → 0,436; dentro do Radboud, 0,784 → 0,806.
- [x] **GAT-MIL no BRACS e no TCGA** (pré-registro `6b21cbd`): BRACS não passou (79 → 57: 0,626 → 0,597; validação cruzada: 0,680 → 0,636; diferenças sem significância); TCGA empatou (AUC 0,981 nos dois; critério de não piorar passou).
- [ ] GAT-MIL na mama com o grafo do tecido inteiro (embeddings de todos os patches, não só da amostra de 2.000), se valer o custo.
- [x] **PANDA, troca de centro** (pré-registro `27f0508`): N1 passou (padronização dos embeddings por centro, GAT-MIL 0,439 → 0,609; ABMIL 0,237 → 0,540); N2 não passou (normalização de cor de Reinhard, GAT-MIL 0,439 → 0,225).
- [ ] PANDA: ainda longe do dentro do centro (~0,80). Testar padronização por centro + treino com os dois centros (separando pacientes).
- [x] **Rede de grafos no PANDA** (pré-registro `da1d4b8`): H1 passou (entre centros, 0,237 → 0,442; contra o GAT-MIL, empate: 0,420); H2 não passou por pouco (dentro do Radboud, 0,784 → 0,809, IC da diferença −0,002 a 0,051).
- [ ] Rede de grafos com a padronização por centro; rede de grafos no BRACS (rebaixar as 61 lâminas de validação e embutir as janelas em volta dos pontos); protótipos por classe.
- [x] **Rim (TCGA-RCC, 3 subtipos), treino e teste em hospitais diferentes** (pré-registro `e9efc8e`): R1 passou (MIL nos hospitais novos: acurácia balanceada 0,953, AUC macro 0,987; no sorteio aleatório, 0,983); R2 passou (GAT-MIL 0,945, não pior). A padronização por hospital não se aplica no TCGA (um subtipo por hospital).
- [ ] **Glioma (TCGA-LGG e GBM, grau 2 × 3 × 4), MIL × GAT-MIL × rede de grafos sobre o tecido inteiro** (`mil/tcga/glioma_grafos.py`; G1: AUC grau 4 ≥ 0,90; G2 e G3: kappa maior que o do MIL com IC > 0): parado a pedido em 16/11, com 135 de 180 lâminas embutidas no HD (a 127 falhou no download e precisa ser refeita); retomar a fila de embutir e depois rodar o teste.
- [x] **Pulmão, dataset do orientador (adeno × epidermoide, 52 pacientes): só o núcleo × núcleo com contexto** (pré-registro `a225cd8`): P1 passou (biópsia, acurácia balanceada 0,886); P2 não passou (só o núcleo, AUC 0,479); P3 passou (núcleo + contexto, AUC 0,948; +0,47); P4 não passou (clássico 0,599, também no acaso). A pasta de "citologia" são núcleos recortados da própria biópsia: confirmar com o orientador se existe uma coleta citológica de verdade.
- [ ] Pulmão (orientador): quanto contexto basta? Janelas de tamanhos diferentes em volta do núcleo (224, 336, 448 px) e onde o MIL põe a atenção.
- [ ] **Ovário (UBC-OCEAN)**: o download pede aceitar as regras da competição no Kaggle (kaggle.com/competitions/UBC-OCEAN/rules). Conferir no train.csv se há informação de centro.
- [x] ★ **Sinalizar contradições nos campos**: aviso pronto nos campos, pulmão 27/27 e próstata 35/35 documentos apontam a discordância, 0 falso alarme, W1–W3 passaram (19–20/11).
- [x] **Avisos inseridos por código, não redigidos**: 0 avisos espúrios e 0 trocas de classe nos dois órgãos, em português (K1 passou) e em inglês (K2 passou na próstata; no pulmão, 1 coordenada copiada errada fora da seção) (20/11).
- [x] **Lista de regiões para revisão montada por código**: pulmão, F1 passou em português e em inglês, 0 coordenadas inventadas (20/11).
- [x] ★ **O aviso marca os erros do MIL?** Sim, nos dois órgãos (E passou): pulmão 4/27 com aviso × 0/51 sem; próstata, câncer × benigno 16% × 6% (20/11).
- [x] ★ **Pré-laudo da próstata com o modelo melhor**: GAT-MIL padronizado, avisos e regiões colados; F2 passou em português (60/60) e em inglês (56/60, os 4 por erro da extração), 0 avisos espúrios, trocas e coordenadas inventadas (20/11).
- [x] **Extração da classe mais robusta**: classe lida por código na impressão; 276/276 pré-laudos finais com a classe da decisão (C passou) (20/11).
- [x] **Teste de remoção da atenção com o GAT-MIL na próstata**: Y1 +0,310 e Y2 +0,124, os dois passaram; negativo nas previstas como ISUP 0 (20/11).
- [x] **Segundo modelo de linguagem**: Llama 3.2 3B; L passou em 2 de 4 (falhas: títulos fora do formato em português e um número calculado em inglês); avisos, classe e coordenadas certos nos 4 (23/11).
- [ ] **Seções críticas montadas pelo código**: o código escreve impressão, avisos e regiões; o modelo escreve só resumo e limitações (ou normalizar títulos `###`/negrito antes de colar). Com o Llama em português, a colagem dependia do título.
- [ ] **Atenção nas lâminas "por ausência"**: no pulmão, a atenção das lâminas previstas como adenocarcinoma não sustenta a classe (suficiência −0,276). Testar atenção por classe (uma cabeça por classe) ou mostrar, nessas lâminas, os patches que mais puxam para a classe prevista.
- [x] **Hierárquico no nível da lâmina**: rótulo oficial, com negativos, 31/57, 0,518 (0,560 em 3 classes), sem critério. Falta confirmar com critério fixado antes.

## Descritor

- [x] **Lâminas benignas como negativos**: o melhor até aqui. Rótulo oficial: 29/57, 0,505; falsos DCIS + IC nas benignas 21% → 7%.
- [ ] ★ **Recuperar o DCIS**: com os negativos, o DCIS fica em 1–2 de 8 lâminas.
- [ ] **Outros codificadores** (CONCH, Virchow2, H-optimus) no lugar do UNI2-h, sobretudo pro atípico. Exigem pedir acesso no Hugging Face.
- [ ] **Duas escalas** (40x + 10x): DCIS × IC e o atípico dependem da arquitetura do ducto. Exige baixar as lâminas de novo.
- [ ] Reduzir a confusão maligno → atípico; métrica pro estágio 2 em lâminas benignas/atípicas (da lista antiga).

## Explicabilidade

- [x] **Mapa de calor da lâmina**: `ferramentas/mapas_de_calor.py`; 4 exemplos na página. Falta refazer com o descritor corrigido e com negativos.
- [x] **Coeficientes do classificador da lâmina**: em `resultados/classificador_lamina/resumo.json`.

## Texto (estágio 5) e avaliação

- [x] **Modelo de linguagem só redige**, a partir de campos fixos (`prelaudo/bracs/prelaudo_campos.py`): passou (classe igual à sugerida em 57/57; 0 números sem sustentação, contra 2,1% nos antigos). Os campos vieram do classificador de 06/11 (agrupamento antigo); a checagem do texto não depende disso.
- [x] **Checagem automática do texto**: no mesmo script. Não detecta achados morfológicos inventados; isso fica para a leitura por patologista.
- [ ] Refazer os campos com o classificador corrigido (rótulo oficial + negativos) antes de usar os textos como exemplo.
- [ ] ★ **Avaliação por patologista**: 10–15 pré-laudos com rubrica (clareza, utilidade, erros, alucinações).
- [x] **Comparar com os números publicados no BRACS**: UNI + ABMIL, 3 classes, 0,687; aqui, 0,518 (0,560 no hierárquico), comparação indicativa. Ver `resultados.md`.

## Documentação e repositório

- [ ] **Publicação automática da página**: o deploy pelo GitHub Actions falha porque a conta está bloqueada por cobrança ("account is locked due to a billing issue"). Enquanto isso, a página é publicada à mão com `mkdocs gh-deploy` a partir de uma cópia limpa do último commit. Depois de resolver em GitHub → Settings → Billing, um push em `docs/` volta a publicar sozinho.
- [ ] Atualizar `resultados.md`, `linha_do_tempo.md` e a página com o pacote com cotas quando for refeito.
- [ ] Decidir as edições de 07/11 ainda sem commit em `docs/` (datasets, pipelines, metodologia, modelos-locais, index), nos READMEs, na `linha_do_tempo.md` e no `brainstorming_melhorias.md`.

## Observação

- 24/10: os processos do HUC-Project que ocupavam a GPU foram parados (`gpu_queue.sh`, `05_local_llm_ollama.py --model gemma2:2b`, runner e `ollama serve`). Os jobs da fila do HUC precisam ser reiniciados lá quando for o caso.
