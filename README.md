# OncoVLM

**Modelos de Visão e Linguagem (VLMs) na Oncologia: Democratizando o Pré-Diagnóstico e a Interpretação de Exames Histopatológicos**

Repositório de acompanhamento da Iniciação Científica (IC).

- **Aluno(a):** _[a preencher]_
- **Orientador(a):** _[a preencher]_
- **Instituição:** UNICAMP
- **Status:** 🟡 Em andamento — fase de revisão bibliográfica

## Resumo do projeto

O diagnóstico histopatológico em oncologia depende de análise visual especializada de lâminas por patologistas, um recurso escasso e desigualmente distribuído (especialmente fora de grandes centros). Modelos de Visão e Linguagem (VLMs) — que combinam compreensão de imagem e texto, geralmente derivados de arquiteturas contrastivas (CLIP) ou generativas (LLaVA, BLIP) — surgem como ferramenta promissora para apoiar (não substituir) esse processo, oferecendo pré-diagnóstico assistido, geração de laudos preliminares e triagem de casos.

Este projeto investiga o estado da arte de VLMs aplicados à patologia digital, avalia modelos pré-treinados em tarefas histopatológicas oncológicas e explora sua adaptação/uso para ampliar o acesso a esse tipo de análise.

A documentação completa é publicada como um site com **MkDocs** — ver [docs/](docs/) ou rodar localmente (instruções abaixo).

## Estrutura do repositório

```
onco-vlm/
├── docs/                   # Conteúdo do site MkDocs
│   ├── index.md
│   ├── 00-resumo.md
│   ├── 01-introducao-motivacao.md
│   ├── 02-fundamentacao-teorica.md
│   ├── 03-objetivos.md
│   ├── 04-metodologia.md
│   ├── 05-datasets.md
│   ├── 06-cronograma.md
│   └── 07-referencias.md
├── mkdocs.yml               # Configuração do site de documentação
├── notebooks/                # Notebooks de exploração e experimentos
├── src/                       # Código-fonte (scripts, pipelines, modelos)
├── data/                       # Dados locais (ignorado pelo git, ver .gitignore)
├── results/                     # Resultados, figuras, métricas
├── requirements.txt              # Dependências do projeto (ML)
├── requirements-docs.txt          # Dependências do site de documentação (MkDocs)
└── README.md
```

## Como começar

**Ambiente de desenvolvimento (código/experimentos):**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dados devem ser baixados manualmente conforme instruções em [docs/05-datasets.md](docs/05-datasets.md) e colocados em `data/` (não versionado — arquivos de imagem histopatológica costumam ser grandes e/ou ter restrições de licença/uso).

**Site de documentação (MkDocs):**

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

Abre em `http://127.0.0.1:8000`. Para gerar o site estático: `mkdocs build` (saída em `site/`, já ignorado pelo git).

## Roteiro de leitura da documentação

1. [Resumo](docs/00-resumo.md) — visão geral em um parágrafo
2. [Introdução e Motivação](docs/01-introducao-motivacao.md) — por que este projeto importa
3. [Fundamentação Teórica](docs/02-fundamentacao-teorica.md) — VLMs, patologia digital, trabalhos relacionados
4. [Objetivos](docs/03-objetivos.md) — objetivo geral e específicos
5. [Metodologia](docs/04-metodologia.md) — fases do projeto, passo a passo
6. [Datasets](docs/05-datasets.md) — bases de dados públicas relevantes
7. [Cronograma](docs/06-cronograma.md) — planejamento temporal
8. [Referências](docs/07-referencias.md) — bibliografia

## Licença

_A definir._ Código próprio pode ser licenciado (ex.: MIT) independentemente dos datasets utilizados, que possuem suas próprias licenças de uso — verificar cada uma individualmente antes de redistribuir dados.
