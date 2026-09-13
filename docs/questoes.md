# Questões

Com o problema definido, uma das formas de atacar para resolver é sendo criativo com o modelo
OU com as informações, ou seja, além de se fazer a pergunta: como tornar os modelos locais
acessíveis e capazes de diagnóstico? fazer também: como tornar as imagens mais acessíveis para os modelos locais, é outra forma de abordar o problema.

- Como representar uma imagem de maneira mais eficiente, já que algumas imagens histopatológicas são gigantescas, como criar uma representação eficiente, acessível e rápida
para modelos locais?


- Ideia: Pesquisar como é feito um diagnóstico com um médico, ver como
funciona seu reasoning de fato para tentar se inspirar na pipeline, como é feito no
LightGlue com a comparação de imagens

- Ideia: em vez de só pegar os top-k patches isolados, definir um raio e juntar
patches de regiões próximas numa área só, gerando um descritor da área em vez de
um por patch, e comparar contra a abordagem atual (patch a patch).
  - Decisão em aberto antes de implementar: juntar na **imagem** (recortar uma
  área maior e rodar pelo encoder) arrisca perder detalhe fino, porque a área
  precisa ser reduzida pra caber na entrada do modelo — é compressão de pixel
  de novo, pela porta dos fundos. Juntar no **texto** (manter os patches
  pequenos, mas agregar/deduplicar os achados de patches próximos) evita esse
  risco e é mais barato em token.
  - Reformulação possível: agrupar por proximidade espacial primeiro, e k
  passa a significar "k clusters" em vez de "k patches" — cada cluster gera
  um descritor só. Usa a mesma validação de recall contra RoI já construída
  no estágio 2, só muda o que conta como unidade selecionada.