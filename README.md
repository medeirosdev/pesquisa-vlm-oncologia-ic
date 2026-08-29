# OncoVLM

**Modelos de Visão e Linguagem (VLMs) na Oncologia: Democratizando o Pré-Diagnóstico e a Interpretação de Exames Histopatológicos**

Repositório de acompanhamento da Iniciação Científica (IC) — UNICAMP.

Documentação em [docs/](docs/), publicada como site com MkDocs.

## Estrutura

```
├── docs/
│   ├── index.md        # Início / sobre
│   └── datasets.md
├── mkdocs.yml
├── notebooks/
├── src/
├── data/                # não versionado, ver .gitignore
├── results/
├── requirements.txt      # dependências de ML
└── requirements-docs.txt  # dependências do MkDocs
```

## Rodar o site localmente

```bash
pip install -r requirements-docs.txt
mkdocs serve
```
