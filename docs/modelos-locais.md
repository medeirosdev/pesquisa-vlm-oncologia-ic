# Modelos locais para VLM em oncologia/histopatologia

Matriz de referência para a fase de seleção. Foco em rodar em hardware modesto.
**Links verificados** (passada de conferência em huggingface/github). Marcações:
✓ = página confirmada · ⚠️ = caminho provável, confirmar antes de baixar.

Licença/acesso: **Aberto** = download livre · **Gated** = cadastro no HF + aceite de termos (quase sempre não-comercial/acadêmico).

Quantização: para modelos < ~700M, fp16 já cabe em < 2 GB — quantizar não compensa. Só marco quantização onde é útil (7B+).

---

## 1. VLMs de patologia — CONTRASTIVOS (imagem+texto; classificação/retrieval zero-shot)

| Modelo | Params (~) | Arquitetura | Licença | Link | Status |
|---|---|---|---|---|---|
| **PLIP** | ~150M | CLIP ViT-B/32 (OpenPath) | Aberto | huggingface.co/vinid/plip | ✓ |
| **QuiltNet-B-32** | ~150M | CLIP ViT-B/32 (Quilt-1M) | MIT (aberto) | huggingface.co/wisdomik/QuiltNet-B-32 | ✓ |
| **QuiltNet-B-16 / -B-16-PMB** | ~150M | ViT-B/16 (PMB = torre PubMedBERT) | MIT | huggingface.co/wisdomik/QuiltNet-B-16 · /QuiltNet-B-16-PMB | ✓ |
| **CONCH** | ~200M | CoCa (ViT-B/16 + texto) | Gated (CC-BY-NC-ND) | huggingface.co/MahmoodLab/CONCH | ✓ |
| **KEEP** | ViT-L (embed 768) | CLIP + grafo de conhecimento; supera CONCH em vários zero-shot | MIT (aberto) | huggingface.co/Astaxanthin/KEEP | ✓ |
| **MUSK** | large | BEiT-3 (contrastivo + generativo) | Gated (CC-BY-NC-ND) | huggingface.co/xiangjx/musk | ✓ |
| **BiomedCLIP** | ~200M | ViT-B/16 + PubMedBERT (biomédico geral) | Aberto | huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224 | ✓ |
| **PathGen-CLIP / -L** | B / ViT-L-336 | CLIP (PathGen-1.6M) | Gated (pesquisa) | huggingface.co/datasets/jamessyx/PathGen | ⚠️ peso exato |
| **PathCLIP** | ~150M | CLIP do PathAsst | Aberto | github.com/superjamessyx/Generative-Foundation-AI-Assistant-for-Pathology | ✓ |

Nota CONCH: a versão pública teve o decoder generativo removido (precaução de PHI). Vision + text encoder intactos — classificação e retrieval OK; captioning nativo, não.
Slide-level generativo relacionado: **TITAN / CONCH v1.5** → huggingface.co/MahmoodLab/TITAN ✓ (gated).

---

## 2. VLMs de patologia — GENERATIVOS (VQA / laudo)

~7B: rodam local com quantização 4-bit (~6–8 GB). Sem quantização, ~16 GB.

| Modelo | Params | Base | Licença | Link | Quantização | Status |
|---|---|---|---|---|---|---|
| **Quilt-LLaVA** | ~7B | LLaVA-1.5 (Vicuna-7B) | Aberto (licença Llama) | huggingface.co/wisdomik/Quilt-Llava-v1.5-7b | bnb 4/8-bit; GGUF comunidade | ✓ |
| **LLaVA-Med** | ~7B | LLaVA + curriculum biomédico; variantes fine-tuned em PathVQA | Aberto (pesquisa) | github.com/microsoft/LLaVA-Med | bnb 4/8-bit | ✓ |
| **Pathology-LLaVA (PA-LLaVA)** | ~7B | LLaVA + encoder PLIP; só dados públicos | Aberto | huggingface.co/OpenFace-CQUPT/Pathology-LLaVA | bnb | ✓ |
| **PathChat** | grande | encoder patologia + LLM | Acesso restrito | solicitar (Mahmood Lab) | — | ⚠️ acesso |

---

## 3. Encoders de VISÃO pura (backbones — NÃO geram texto)

Só entram se você for montar seu próprio VLM por cima. Incluí os leves, que servem ao argumento de eficiência.

| Modelo | Params | Arquitetura | Licença | Link | Status |
|---|---|---|---|---|---|
| **Midnight-12k** | leve | destilado (kaiko) | Aberto | huggingface.co/kaiko-ai/midnight | ✓ |
| **Virchow2G Mini** | 22M | destilado do Virchow2G (1.9B) | Gated | huggingface.co/paige-ai (buscar Virchow2G-Mini) | ⚠️ repo exato |
| **CTransPath** | ~28M | Swin (leve) | Aberto | github.com/Xiyue-Wang/TransPath | ⚠️ não reverificado |
| **Phikon** | ~86M | ViT-B (iBOT) | Owkin non-commercial | huggingface.co/owkin/phikon | ✓ |
| **Phikon-v2** | ~300M | ViT-L (embed 1024) | Owkin non-commercial | huggingface.co/owkin/phikon-v2 | ✓ |
| **Hibou-B / -L** | 86M / 300M | ViT (DINOv2) | Aberto | huggingface.co/histai/hibou-b · /hibou-L | ✓ |
| **UNI** | ~300M | ViT-L/16 (DINOv2) | Gated | huggingface.co/MahmoodLab/UNI | ✓ |
| **UNI2-h** | ~680M | ViT-h | Gated | huggingface.co/MahmoodLab/UNI2-h | ✓ |
| **Virchow / Virchow2** | 632M | ViT-H (DINOv2) | Gated (CC-BY-NC-ND) | huggingface.co/paige-ai/Virchow · /Virchow2 | ✓ |
| **Prov-GigaPath** | 1.1B | ViT-g (embed 1536) | Gated (Apache-2.0) | huggingface.co/prov-gigapath/prov-gigapath | ✓ |
| **H-optimus-0** | 1.1B | ViT-g (embed 1536) | Gated (Apache-2.0) | huggingface.co/bioptimus/H-optimus-0 | ✓ |
| **H-optimus-1** | 1.1B | ViT-g | Gated (CC-BY-NC-ND) | huggingface.co/bioptimus/H-optimus-1 | ✓ |

Para o argumento de eficiência, os leves (Midnight, Virchow2G Mini, CTransPath, Phikon) são os mais interessantes de defender — o ganho ao subir para 1.1B costuma ser pequeno.

---

## 4. VLMs pequenos GENÉRICOS (para fine-tuning em patologia)

**MedGemma é o mais relevante:** é médico, da família Gemma que você já usa, e o encoder SigLIP dele foi pré-treinado incluindo **histopatologia** (avaliado em PathMCQA — mama, cérvix, próstata).

| Modelo | Params | Licença | Link | Quantização | Status |
|---|---|---|---|---|---|
| **MedGemma-4B-it** | 4B (multimodal) | Health AI Dev Foundations terms | huggingface.co/google/medgemma-4b-it | GGUF comunidade (ex.: SandLogicTechnologies/MedGemma-4B-IT-GGUF) | ✓ |
| **MedGemma-1.5-4B-it** | 4B (multimodal, mais novo) | Health AI Dev Foundations terms | huggingface.co/google/medgemma-1.5-4b-it | via transformers | ✓ |
| **Gemma 3-4B-it** | 4B (multimodal) | Gemma | huggingface.co/google/gemma-3-4b-it | GGUF oficial | ✓ |
| **Qwen2.5-VL-3B-Instruct** | 3B | Apache-2.0 | huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct | AWQ oficial + GGUF | ✓ |
| **Qwen2.5-VL-7B-Instruct** | 7B | Apache-2.0 | huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct | AWQ oficial + GGUF | ✓ |
| **Qwen3-VL-4B / -8B** | 4B / 8B | Apache-2.0 | github.com/QwenLM/Qwen3-VL | FP8 oficial | ✓ |
| **InternVL2-8B** (série 1B–8B) | 8B | MIT | huggingface.co/OpenGVLab/InternVL2-8B | AWQ / GGUF comunidade | ✓ |
| **SmolVLM-500M / -Instruct (2B)** | 0.5B / 2B | Apache-2.0 | huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct · /SmolVLM-Instruct | GGUF (llama.cpp/MLX) | ✓ (500M) |
| **MiniCPM-V 2.6** | 8B (SigLip-400M + Qwen2-7B) | uso pesquisa | huggingface.co/openbmb/MiniCPM-V-2_6 | int4 oficial / GGUF | ✓ |
| **Moondream2** | ~1.9B | Apache-2.0 | huggingface.co/vikhyatk/moondream2 | GGUF | ✓ |
| **Phi-3.5-vision** | ~4.2B | MIT (comercial+pesquisa) | huggingface.co/microsoft/Phi-3.5-vision-instruct | ONNX / bnb | ✓ |

Nota GGUF em VLM: o backbone de texto é quantizado, mas o encoder de visão (mmproj) fica em F16 — quantizá-lo gera artefatos. A economia de memória vem do lado do texto, não da imagem.

---

## Ponto de partida recomendado

- **Contrastivo** (classificação/retrieval): CONCH (SOTA, gated) + QuiltNet e PLIP (abertos). KEEP para resultado recente e forte, e é MIT.
- **Generativo** (VQA/laudo): Quilt-LLaVA aberto, 4-bit; comparar com LLaVA-Med.
- **Adaptar base pequena**: MedGemma-4B (médico + Gemma que você domina, encoder já viu histopatologia) ou Qwen2.5-VL-3B (Apache-2.0, AWQ pronto).

Fontes vivas: github.com/lingxitong/Awesome-AI4DigitalPathology · leaderboard PathVLM-Eval (huggingface.co/spaces/gilalnauman/PathVLMs) · tabelas de encoders no github.com/mahmoodlab/trident.

## Itens a confirmar antes de usar
- **PathGen-CLIP**: peso exato (org jamessyx no HF; dataset é gated).
- **Virchow2G Mini**: repo exato dentro de paige-ai.
- **CTransPath**: não reverificado nesta passada (repo provável: Xiyue-Wang/TransPath).
- Contagens de params com "~" são aproximadas — valor exato no model card.