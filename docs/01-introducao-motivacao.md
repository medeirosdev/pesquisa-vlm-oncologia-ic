# Introdução e Motivação

## O problema

O câncer é uma das principais causas de morte no mundo, e o diagnóstico definitivo na maioria dos casos ainda depende da análise histopatológica: um patologista examina lâminas de tecido (frequentemente coradas com H&E — hematoxilina e eosina) sob microscópio ou em imagens digitalizadas de lâmina inteira (*Whole Slide Images*, WSI) para identificar padrões morfológicos associados a malignidade, grau e subtipo tumoral.

Esse processo enfrenta gargalos conhecidos:

- **Escassez de patologistas**, especialmente fora de grandes centros urbanos e em países/regiões de baixa renda — o Brasil apresenta distribuição muito desigual de patologistas por habitante entre regiões.
- **Alta carga de trabalho e variabilidade inter-observador**, que pode impactar tempo de resposta e consistência diagnóstica.
- **Barreiras de acesso** para populações distantes de centros de referência oncológica, aumentando o tempo entre coleta de amostra e diagnóstico — fator crítico em oncologia, onde velocidade de diagnóstico afeta prognóstico.

## Por que VLMs?

Modelos de Visão e Linguagem (VLMs) aprendem a associar imagens e texto em um espaço de representação comum (abordagens contrastivas, ex. CLIP) ou a gerar texto condicionado em imagem (abordagens generativas, ex. arquiteturas tipo LLaVA/BLIP). Aplicados à patologia digital, esses modelos permitem, por exemplo:

- **Classificação e triagem** de imagens histopatológicas via linguagem natural (zero-shot), sem exigir grandes conjuntos de dados rotulados especificamente para cada nova tarefa.
- **Geração de descrições/laudos preliminares** a partir de imagens de lâmina, potencialmente acelerando o fluxo de trabalho do patologista.
- **Resposta a perguntas visuais (VQA)** sobre achados em uma imagem, útil como ferramenta de apoio educacional e de segunda opinião.
- **Recuperação de casos similares** (image-text retrieval) para auxiliar em decisões diagnósticas por analogia.

A hipótese central deste projeto é que VLMs pré-treinados em larga escala — combinados com adaptação a dados de patologia — podem oferecer uma camada de **pré-diagnóstico assistido de baixo custo**, funcionando como ferramenta de triagem ou apoio em locais sem acesso imediato a um patologista especialista, sem pretender substituir o julgamento clínico humano.

## Por que modelos locais e eficientes?

"Democratizar" o acesso a essa análise não pode depender de mandar imagens de exames de pacientes para uma API de terceiros. Isso reposiciona uma parte central do projeto: em vez de assumir modelos gigantes hospedados por big techs como caminho natural, o projeto passa a priorizar **modelos pequenos, eficientes e executáveis localmente** — em hardware modesto (GPU de notebook, ou no máximo algo como um Mac mini de entrada), não em clusters de data center.

Isso é motivado por dois eixos que se reforçam:

- **Privacidade dos dados de saúde.** Dados de exames histopatológicos são dados pessoais sensíveis por natureza (LGPD, e no caso de comparação internacional, HIPAA). Enviar essas imagens a uma API externa é, na melhor das hipóteses, uma complicação regulatória, e na pior, um risco real de vazamento. Modelos que rodam localmente (na máquina do laboratório/hospital, ou em um cluster institucional) eliminam essa exposição por design — não é uma questão de "confiar" no provedor, é não depender dele. Essa é também a razão pela qual **aprendizado federado (federated learning)** é uma das direções mais discutidas em IA para saúde: permite treinar/adaptar modelos usando dados de múltiplas instituições sem que os dados brutos saiam de cada instituição.
- **Viabilidade prática de democratização.** Um posto de saúde ou laboratório sem orçamento para infraestrutura de nuvem consegue rodar um modelo pequeno em hardware comum; dificilmente vai operar (ou vai querer depender de) um modelo de dezenas/centenas de bilhões de parâmetros atrás de uma API paga. Se o objetivo é ampliar acesso, o modelo em si precisa ser barato de rodar.

Esse recorte também é uma aposta de pesquisa: existe uma lacuna na literatura sobre VLMs pequenos aplicados a patologia especificamente — a maior parte dos trabalhos de VLM em patologia (ver [02-fundamentacao-teorica.md](02-fundamentacao-teorica.md)) usa modelos de fundação de grande porte. Investigar até onde modelos pequenos conseguem chegar nessa tarefa, e que adaptações (arquiteturais, de treino, de dados) são necessárias para compensar a diferença de escala, é uma contribuição possível deste projeto — não só avaliar modelos existentes, mas também pensar em *como* fazer mais com menos.

## Escopo e limitações declaradas

Este projeto tem caráter de pesquisa exploratória (IC), não de desenvolvimento de produto clínico. Não se pretende validar o sistema para uso clínico real nem obter aprovação regulatória — o foco é acadêmico: entender capacidades, limitações, vieses e viabilidade técnica de VLMs neste domínio. Aspectos éticos (responsabilidade, viés de dados, risco de má utilização) são discutidos como parte integrante da metodologia, não como nota de rodapé.
