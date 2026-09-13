A ideia central da Pipeline 01, em uma frase: transformar uma lâmina gigante numa descrição textual compacta que um modelo pequeno consegue ler — filtrando, selecionando e descrevendo, em vez de comprimir pixels.

Deixa eu reconstruir o porquê, porque a pipeline não faz sentido sem o problema que ela resolve.

O problema. Você quer um VLM rodando local, em hardware modesto, dando pré-diagnóstico de histopatologia. Mas uma WSI tem ~100.000×100.000 pixels, e um VLM local só engole imagem pequena (tile de 256px) e tem orçamento apertado de token/VRAM. Os dois não se encontram: a lâmina é grande demais pra passar pelo modelo, e quantizar (que democratiza o lado do texto) não ajuda o lado da imagem. Então a pergunta que a pipeline responde não é "como fazer o modelo ler a lâmina", é "como tornar a lâmina pequena o suficiente pro modelo, sem jogar fora o que decide o diagnóstico".

A ideia-chave. A resposta não é comprimir a imagem (JPEG, embedding, latente) — é selecionar e descrever. Você joga fora quase tudo (fundo, tecido irrelevante), fica com os poucos pedaços que importam, e converte cada um em texto barato, porque texto é o canal mais leve que entra num VLM. No fim, a lâmina de gigapixels vira ~1–2k tokens de texto + 1–3 imagens-âncora. Isso é a lâmina "domada".

É a imitação do patologista: ele não olha cada pixel dos 100k×100k — ele varre em baixo aumento, decide onde vale dar zoom, olha alguns campos, e escreve um laudo em palavras. A pipeline é isso, mecanizado.

Como cada estágio serve a essa ideia:

Filtro de tecido — descarta os 60–80% de fundo branco. Redução trivial e sem custo diagnóstico (é o que você acabou de fechar: descartar gordura/fundo não perde epitélio). Primeiro corte grosso.
Roteador → top-k — dos milhares de tiles com tecido, escolhe os poucos (8–32) que importam pra pergunta. É o "onde dar zoom". Este é o coração — é aqui que se decide quanto da lâmina você paga, e é onde mora a curva custo×fidelidade.
Extração por patch — cada patch escolhido vira texto ("núcleos pleomórficos, estroma denso, figuras de mitose"), via descritor contrastivo. É o passo que troca pixel caro por palavra barata. É a compressão de verdade — mas compressão semântica, não de sinal.
Agregação — junta os k blocos de texto + um cabeçalho da lâmina + 1–3 patches como âncora visual. Aqui a lâmina inteira já é um prompt enxuto.
Síntese na VLM — o modelo local lê essa evidência estruturada e raciocina uma vez pra escrever o pré-laudo. Separar "perceber" (3–4) de "decidir" (5) é o que evita o modelo ancorar num palpite precoce.

O que a distingue de fazer o óbvio. O caminho ingênuo seria rodar o VLM em cada tile e somar — caro e ruidoso. Ou treinar um projetor pra enfiar embeddings no VLM — o que te custou 8 ciclos de debug no PaperWVC. A Pipeline 01 evita os dois: sem treino, sem embedding no VLM, sem varrer a lâmina toda — só seleção agressiva + textualização. Ela aposta que "descrever em palavras os poucos lugares certos" carrega sinal diagnóstico suficiente, e essa aposta tem base no seu próprio PaperWVC (onde um dicionário de atributos bateu o VLM 7B).

A tese implícita, que é o que faz disso pesquisa e não engenharia: que existe um ponto na curva onde uma representação textual, esparsa e barata da lâmina é diagnosticamente suficiente — e que dá pra achar esse ponto medindo custo×fidelidade e a perda em cada seta (tecido→top-k→descritor→VLM). Se for verdade, você democratizou pré-diagnóstico em hardware modesto. Se não for, você mapeou exatamente onde a compressão quebra o diagnóstico — que também é um resultado publicável.

Em resumo: Pipeline 01 = filtrar o irrelevante, selecionar o que importa, descrever em texto, deixar o modelo raciocinar uma vez — com a hipótese de que descrição esparsa vence compressão de pixel quando o alvo é diagnóstico em hardware fraco.