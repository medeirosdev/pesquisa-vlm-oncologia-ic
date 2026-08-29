OmniPathoVQA: Benchmarking pathology vision–language models with Encyclopedia-scale knowledge

Quilt-1M (~1M) — github.com/wisdomikezogwo/quilt1m
Duas vias: versão reescalada (imagens em 512×512, ~36 GB) no Zenodo, e versão full (imagens em tamanho original, ~110 GB) via formulário de acesso no Google Drive. A reescalada já serve pra fine-tuning contrastivo e é bem mais gerenciável.

PathCap (~207–223k) — github.com/superjamessyx/Generative-Foundation-AI-Assistant-for-Pathology
Projeto PathAsst. O dataset está liberado no HuggingFace (link no README do repo). Majoritariamente PubMed Central + livros, então qualidade de caption tende a ser melhor que a de social media.

PathGen-1.6M (1.6M) — huggingface.co/datasets/jamessyx/PathGen
Gated: exige login no HF e aceitar termos (uso não-comercial, só pesquisa, com obrigação de citar). E atenção ao que ele de fato entrega: o repo jamessyx/PathGen_init deixa claro que boa parte são índices, não imagens — você usa os nomes/IDs pra puxar as imagens de Quilt-1M, PathCap, OpenPath e do TCGA. Ou seja, PathGen depende de você já ter acesso aos outros três.


PatchGastricADC22 — github.com/masatsuneki/histopathology-image-caption
Esse é o que eu olharia primeiro. São 262.777 patches de 991 WSI de adenocarcinoma gástrico, com captions extraídas diretamente de laudos diagnósticos reais. É patch-level (roda em hardware modesto), tem texto clínico de verdade, é single-organ (estômago) e é genuinamente subexplorado comparado a PCam/NCT-CRC. Encaixa quase perfeito na sua fase de baseline de captioning/retrieval.

HISTAI — no HuggingFace (paper: arXiv 2505.12120), 2025
60k+ WSI multi-institucional com laudos moderadamente estruturados e diversidade de tecidos. Novo e ainda pouco usado. Contra: é WSI-scale, então puxa todo o problema de tiling/agregação que mencionei. Um detalhe de qualidade que já foi apontado: em parte dos casos o diagnóstico está na coluna "Conclusion", não na "Diagnosis", e isso só aparece nos metadados do HF, não no paper — o tipo de armadilha que "dataset novo" traz.



Colocar:
https://github.com/masatsuneki/histopathology-image-caption esse é bao


Dataset Open
PatchGastricADC22:
zenodo.org/record/6550925



Datasets padrões para comparar papers depois:
PathVQA He et al., 2020, arXiv 2003.10286).