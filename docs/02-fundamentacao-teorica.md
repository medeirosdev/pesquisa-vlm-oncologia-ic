# Fundamentação Teórica

## Modelos de Visão e Linguagem (VLMs)

VLMs são modelos treinados para relacionar conteúdo visual (imagens) e textual (linguagem natural) em um espaço de representação compartilhado, ou para gerar texto condicionado a imagens. Duas famílias são especialmente relevantes para este projeto:

- **Contrastivos (estilo CLIP)** — treinam um codificador de imagem e um codificador de texto para que pares imagem-texto correspondentes fiquem próximos em um espaço de *embedding* comum, e pares não correspondentes fiquem distantes. Permitem classificação **zero-shot** (comparar a imagem com *embeddings* de possíveis descrições textuais) e recuperação imagem↔texto.
- **Generativos multimodais (estilo LLaVA/BLIP)** — acoplam um codificador de imagem a um modelo de linguagem (LLM), permitindo gerar texto livre a partir de uma imagem: descrições, respostas a perguntas (VQA), laudos.

## VLMs aplicados à patologia computacional

A patologia digital vinha sendo tratada majoritariamente com CNNs supervisionadas para tarefas específicas (classificação binária, segmentação de núcleos, detecção de metástase). Trabalhos recentes têm adaptado a abordagem VLM para esse domínio, treinando modelos contrastivos ou generativos sobre pares imagem-texto extraídos de fontes como:

- Vídeos educacionais de patologia (transcrições + frames)
- Livros-texto e atlas de patologia (legendas de figuras)
- Redes sociais acadêmicas (posts de patologistas com imagem + descrição)
- Relatórios/laudos associados a lâminas (quando disponíveis com anonimização adequada)

Isso resulta em modelos capazes de: classificar tipo/subtipo tumoral via prompt textual, recuperar casos similares, responder perguntas sobre uma imagem (VQA patológico) e gerar descrições preliminares.

**Modelos e trabalhos de referência a estudar em profundidade** (revisar e completar citações formais em [07-referencias.md](07-referencias.md)):

- CLIP (Radford et al.) — base contrastiva geral, ponto de partida conceitual.
- PLIP — *Pathology Language-Image Pretraining*, adaptação do CLIP a imagens histopatológicas com legendas de redes sociais.
- CONCH — modelo de fundação visão-linguagem para patologia computacional.
- MI-Zero — classificação zero-shot em imagens de lâmina inteira (WSI) usando VLMs.
- Quilt-1M / QuiltNet — grande dataset e modelo treinados a partir de vídeos educacionais de patologia.
- PathVQA — benchmark de VQA para patologia.
- Modelos generativos aplicados a patologia (assistentes conversacionais sobre imagens de lâmina).

> **Nota metodológica:** os nomes acima devem ser conferidos e citados formalmente (autores, ano, veículo de publicação, DOI/arXiv) durante a fase de revisão bibliográfica — ver [04-metodologia.md](04-metodologia.md), Fase 1. Evitar citar detalhes bibliográficos de memória sem checagem na fonte primária.

## Desafios específicos do domínio

- **Imagens gigapixel** — uma WSI pode ter dezenas de gigapixels, exigindo estratégias de *patching* (recorte em blocos menores) e agregação (ex. *multiple instance learning*) incompatíveis com o uso direto de encoders de imagem convencionais (que operam em resolução fixa, tipicamente 224–336px).
- **Escassez de dados pareados imagem-texto de qualidade** no domínio médico, por restrições de privacidade (LGPD/HIPAA) e custo de anotação especializada.
- **Vocabulário técnico e ambiguidade clínica** — termos de patologia têm significado preciso e alta especificidade; erros de VLMs generalistas nesse vocabulário podem ser sutis e perigosos.
- **Viés e generalização** — modelos treinados em datasets predominantemente de um país/etnia/tipo de scanner podem não generalizar bem para outras populações ou equipamentos, um ponto crítico ao se falar em "democratização".

## Métricas de avaliação relevantes

- Classificação: acurácia, F1, AUC-ROC (por classe e macro).
- Recuperação (retrieval): Recall@K, mAP.
- VQA: acurácia de resposta, métricas de similaridade textual (quando resposta é aberta).
- Geração de texto/laudo: métricas de sobreposição (BLEU/ROUGE) como proxy fraco, complementadas por avaliação qualitativa/humana quando possível.
- Calibração e abstenção: capacidade do modelo de indicar incerteza — especialmente relevante para uso como ferramenta de triagem, não decisão final.
