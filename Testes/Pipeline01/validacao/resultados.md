# Estágio 4-teste — validação do estágio 3 contra classe real

**Pergunta:** entre o achado bruto (similaridade máxima) e o normalizado (z-score) do estágio 3, qual discrimina melhor entre classes reais do BRACS?

**Método** ([validacao_classe.py](validacao_classe.py)): os RoIs do BRACS_RoI já vêm com classe no nome do arquivo. Para cada um dos 128 patches selecionados no estágio 2, verifica se cai dentro de algum RoI anotado — se cair, herda a classe real daquele RoI. Não assume "classe X deveria dar achado Y" (isso seria inventar ground-truth de patologia) — só mede se cada método é consistente dentro da classe e diferente entre classes.

## Resultado

70/128 patches selecionados caem dentro de um RoI anotado (só classes ADH, DCIS e IC aparecem entre os RoIs deste slide; nenhum patch selecionado caiu dentro de um RoI de ADH — os 4 RoIs de ADH da lâmina não foram priorizados pelo roteador no top-128).

| Achado dominante | DCIS (n=53) | IC (n=17) |
|---|---|---|
| Bruto | high nuclear pleomorphism, mitotic figures (51/53) | high nuclear pleomorphism, mitotic figures (17/17) |
| Normalizado | solid growth pattern, mitotic figures (25/53) | solid growth pattern, mitotic figures (6/17) |

**As duas versões dão o mesmo achado dominante pras duas classes.** DCIS (carcinoma in situ, não invasivo) e IC (carcinoma invasivo) são clinicamente bem diferentes — um descritor útil deveria, no mínimo, mostrar alguma diferença de padrão entre elas. Nenhuma das duas versões mostra.

## Conclusão

**A pergunta "bruto ou normalizado" estava mal colocada.** Não é que um dos dois esteja certo e o outro errado — **nenhum dos dois tem validade discriminativa demonstrada** por classe, pelo menos entre DCIS e IC nesta lâmina. A normalização mudou qual frase domina (de "high nuclear pleomorphism" pra "solid growth pattern"), mas não resolveu o problema de fundo: o mecanismo (top-2 frases por similaridade CLIP zero-shot, banco genérico, um patch isolado por vez) não parece ter resolução suficiente pra discriminar subtipos do espectro BRACS.

Isso muda o que vale investir a seguir — não é mais "escolher entre as duas versões que já tenho", é repensar o mecanismo:

## Teste extra: ensemble de prompts (sugestão do orientador, Prof. João) — também não resolveu

Ideia dele: em vez de uma frase fixa por conceito, usar vários templates ("histopathology image showing {}", "H&E stained tissue with {}" etc.) e tirar a média dos embeddings — técnica clássica de ensemble do próprio paper do CLIP, pra reduzir a idiossincrasia de uma formulação específica. Implementado em `descritores.py --ensemble` (5 templates por frase).

**Achado colateral, antes do resultado principal:** a primeira rodada do teste de classe deu "ensemble: 2/2" (parecia discriminar!). Investigando, era **falso positivo** — o agrupamento por achado estava sensível à ordem das frases (`tuple` em vez de `frozenset`), e DCIS/IC tinham exatamente as mesmas duas frases, só em ordem trocada. Corrigido o agrupamento pra ordem-insensível antes de aceitar qualquer resultado.

**Com a correção, as 4 variantes testadas dão o mesmo veredito:**

| Variante | Achado dominante DCIS | Achado dominante IC | Discrimina? |
|---|---|---|---|
| Bruto | high nuclear pleomorphism, mitotic figures | mesmo | não (1/2) |
| Normalizado | mitotic figures, solid growth pattern | mesmo | não (1/2) |
| Ensemble | high nuclear pleomorphism, mitotic figures | mesmo | não (1/2) |
| Ensemble + normalizado | comedonecrosis, mitotic figures | mesmo | não (1/2) |

Ensemble sozinho até **reduziu** a diversidade bruta de achados entre patches (a média de templates estabiliza/denoisa uma frase, mas não resolve o viés *entre* frases diferentes — que é o problema de fundo). Combinado com normalização, fica no meio do caminho. Em nenhuma combinação a discriminação DCIS/IC aparece.

## Conclusão consolidada

Testei 4 variantes (bruto, normalizado, ensemble, ensemble+normalizado) — **nenhuma discrimina DCIS de IC**. Isso fortalece a hipótese de que o problema não está na forma de agregar/calibrar a similaridade (essas 4 são todas variações de "pegar similaridade CLIP e rankear"), e sim em algum destes:

## Banco de frases por classe — testado, e piorou

Ideia: em vez de um banco genérico "suspeito", um banco dedicado por classe (ADH, DCIS, IC), com termos de critério diagnóstico real (WHO/critérios de Page — ex. DCIS: "intact myoepithelial cell layer"; IC: "loss of myoepithelial cell layer, stromal invasion"; ADH: "monomorphic epithelial cell population, mild nuclear atypia"). Classificação = argmax da similaridade máxima entre os 3 bancos. Implementado em [banco_por_classe.py](banco_por_classe.py), testado contra **todos os 15.138 candidatos** (não só o top-128 do roteador) — 2.711 caem dentro de exatamente 1 RoI anotado, dando uma amostra bem maior (2.174 DCIS, 501 IC, 36 ADH).

**Acurácia: 23,9% (649/2.711) — pior que o baseline ingênuo de sempre prever a classe majoritária (80,2%, já que DCIS domina a amostra).**

Matriz de confusão (linha = real, coluna = predita):

| real \ predita | ADH | DCIS | IC |
|---|---|---|---|
| ADH (n=36) | 3 | 18 | 15 |
| DCIS (n=2174) | 1103 | 544 | 527 |
| IC (n=501) | 314 | 85 | 102 |

O banco de **ADH vence o argmax na maioria das vezes**, mesmo pra patches que são DCIS ou IC de verdade (1.103/2.174 DCIS reais caem em ADH; 314/501 IC reais também). É o mesmo viés de calibração já visto nos testes anteriores — só que agora manifestado entre bancos de classe inteiros, não entre frases individuais de um banco só. Separar por classe não eliminou o viés, só mudou o nível em que ele aparece.

**Isso é evidência mais forte ainda de que o problema é o modelo (QuiltNet-B-32) ou a abordagem zero-shot em si, não a forma de organizar/calibrar as frases.** Já são 5 variações testadas (bruto, normalizado, ensemble, ensemble+normalizado, banco-por-classe) — todas com o mesmo tipo de falha de fundo.

## Em aberto

- ~~Banco de frases por classe~~ — testado acima, piorou (23,9% vs. baseline de 80,2%). Descartado como solução isolada.
- **Testar se o problema é o modelo, não o banco/agregação** — repetir com CONCH ou KEEP (mais fortes que QuiltNet-B-32, já catalogados na aba Modelos Locais) e ver se discriminam melhor DCIS/IC/ADH com o mesmo método de classificação por argmax. Essa é agora a hipótese mais provável, depois de 5 variações de banco/agregação terem falhado do mesmo jeito.
- **Aceitar que patch isolado pode não ser suficiente** — talvez a discriminação real só apareça olhando o padrão agregado de vários patches (arquitetura, não achado pontual), não um patch de cada vez. Conecta com a questão de "independência espacial" já registrada em `docs/pipelines.md`, e com a ideia de hierarquia (benigno/maligno → evidência) que o Prof. João também sugeriu — ainda não implementada.
- Também bloqueado pelo mesmo motivo de sempre: só uma lâmina local, não dá pra saber se esse resultado é específico da BRACS_748.
