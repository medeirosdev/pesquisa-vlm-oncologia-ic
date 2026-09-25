# Datasets

## Dataset principal: PathVQA

Primeiro dataset a ser testado — benchmark padrão para VQA em patologia, o que torna os resultados comparáveis com outros trabalhos da área.

He et al., 2020 — *PathVQA: 30000+ Questions for Medical Visual Question Answering*. 5.004 imagens e 32.795 pares pergunta-resposta (perguntas abertas e sim/não), construído a partir de dois livros-texto de patologia ("Textbook of Pathology", "Basic Pathology") e da biblioteca digital PEIR.

- Artigo: [arXiv 2003.10286](https://arxiv.org/abs/2003.10286)
- Repositório oficial: [github.com/UCSD-AI4H/PathVQA](https://github.com/UCSD-AI4H/PathVQA)
- HuggingFace: [flaviagiammarino/path-vqa](https://huggingface.co/datasets/flaviagiammarino/path-vqa)

## Dataset em uso nos testes da Pipeline 01: BRACS

**BRACS** (*BReAst Carcinoma Subtyping*) — dataset de histopatologia de mama em H&E, anotado por consenso de três patologistas. É o dataset usado em todos os testes da Pipeline Ideia 01 até agora (estágios 1 a 4).

Brancati et al., 2022 — *BRACS: A Dataset for BReAst Carcinoma Subtyping in H&E Histology Images*, publicado na revista *Database* (Oxford Academic).

- Artigo: [arXiv 2111.04740](https://arxiv.org/abs/2111.04740)
- Site oficial: [bracs.icar.cnr.it](https://www.bracs.icar.cnr.it/) (distribuído pelo ICAR-CNR, Itália)

**Tamanho:** 547 lâminas inteiras (WSI) de 189 pacientes, e 4.537 regiões de interesse (RoIs) recortadas a partir de 387 dessas lâminas (151 pacientes).

**Duas partes, usadas de formas diferentes no projeto:**

- **WSI** — lâminas inteiras em `.svs`, formato piramidal. Usadas pra testar a pipeline de ponta a ponta (filtro de tecido, roteador, descritores).
- **BRACS_RoI** — recortes já extraídos pelo próprio dataset, um por região anotada, organizados por classe. Usados como verdade de campo (ground-truth) pra validar os estágios da pipeline.

**Sete classes, agrupadas em três categorias** (classificação oficial do BRACS):

| Categoria | Classe | Sigla |
|---|---|---|
| Benigno | Normal | N |
| Benigno | Patológico benigno | PB |
| Atípico | Hiperplasia ductal usual | UDH |
| Atípico | Atipia epitelial plana | FEA |
| Atípico | Hiperplasia ductal atípica | ADH |
| Maligno | Carcinoma ductal *in situ* | DCIS |
| Maligno | Carcinoma invasivo | IC |

> **Atenção à sigla "IC":** aqui significa *Invasive Carcinoma* (carcinoma invasivo), a classe mais grave do espectro — não tem relação com "IC" de Iniciação Científica.

**Uso atual no projeto:** até agora, só uma lâmina do BRACS está baixada localmente — `BRACS_748.svs` —, com 98 RoIs anotados nela (84 DCIS, 10 IC, 4 ADH — só três das sete classes aparecem nesta lâmina especificamente). Caminhos locais registrados em `Caminhos/caminhos.md`. Repetir os testes em mais lâminas depende de baixar mais `.svs` do dataset.

## Outras fontes (para o futuro)

| Dataset | Tamanho | Link | Descrição |
|---|---|---|---|
| **Quilt-1M** | ~1M pares imagem-texto | [github.com/wisdomikezogwo/quilt1m](https://github.com/wisdomikezogwo/quilt1m) · artigo [arXiv 2306.11207](https://arxiv.org/abs/2306.11207) | Duas versões: reescalada (512×512, ~36GB, no Zenodo) e full (tamanho original, ~110GB, via formulário no Google Drive). A reescalada já serve para fine-tuning contrastivo e é bem mais gerenciável. |
| **PathCap** | ~207–223k | [github.com/superjamessyx/Generative-Foundation-AI-Assistant-for-Pathology](https://github.com/superjamessyx/Generative-Foundation-AI-Assistant-for-Pathology) | Projeto PathAsst. Liberado no HuggingFace (link no README do repo). Majoritariamente PubMed Central + livros, então qualidade de caption tende a ser melhor que a de redes sociais. |
| **PathGen-1.6M** | 1.6M | [huggingface.co/datasets/jamessyx/PathGen](https://huggingface.co/datasets/jamessyx/PathGen) | Gated: exige login no HF e aceitar termos (uso não-comercial, só pesquisa, com obrigação de citar). Boa parte são índices, não imagens — usa os nomes/IDs para puxar imagens de Quilt-1M, PathCap, OpenPath e TCGA. Depende de já ter acesso aos outros três. |
| **PatchGastricADC22** | 262.777 patches de 991 WSI | [github.com/masatsuneki/histopathology-image-caption](https://github.com/masatsuneki/histopathology-image-caption) · [Zenodo](https://zenodo.org/record/6550925) | Adenocarcinoma gástrico, captions extraídas diretamente de laudos diagnósticos reais. Patch-level (roda em hardware modesto), texto clínico de verdade, single-organ (estômago), subexplorado comparado a PCam/NCT-CRC. Bom candidato para a fase de baseline de captioning/retrieval. |
| **HISTAI** | 60k+ WSI | HuggingFace · artigo [arXiv 2505.12120](https://arxiv.org/abs/2505.12120) (2025) | Multi-institucional, laudos moderadamente estruturados, diversidade de tecidos. Novo e pouco usado. Contra: é WSI-scale (exige tiling/agregação). Cuidado: em parte dos casos o diagnóstico está na coluna "Conclusion" em vez de "Diagnosis" nos metadados do HF — não aparece no paper. |
