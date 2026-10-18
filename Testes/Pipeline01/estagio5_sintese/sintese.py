"""
Estágio 5 — síntese. Um modelo de linguagem local (via Ollama) lê o prompt do estágio 4 (evidência
agregada dos patches) e as imagens das âncoras, e redige um rascunho de pré-laudo.

O rótulo real da lâmina (BRACS.xlsx) NÃO vai pro modelo: fica só no registro, pra comparação.

Precisa de um servidor Ollama rodando (localhost:11434) com o modelo baixado, ex.:
    OLLAMA_MODELS="<HD>/Modelos/ollama" "<HD>/Modelos/ollama-bin/bin/ollama" serve
    "<HD>/Modelos/ollama-bin/bin/ollama" pull medgemma:4b

Uso (venv do projeto):
    .venv/bin/python estagio5_sintese/sintese.py --svs BRACS_748 --modelo medgemma:4b
"""

import argparse
import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comum.lamina import dir_resultados, resolver_svs
from comum.rois import info_lamina

OLLAMA = "http://localhost:11434/api/chat"
OPCOES = {"temperature": 0.2, "seed": 0, "num_ctx": 8192}

INSTRUCOES = """Você redige um RASCUNHO de pré-laudo histopatológico de mama, para revisão por um patologista.

Você recebe evidência gerada automaticamente a partir de uma lâmina inteira corada em H&E:
- para cada patch analisado (quadrado de 128 µm, identificado pelas coordenadas [x,y] na lâmina), a categoria
  prevista (benigno, atípico ou maligno) com a probabilidade e, quando maligno, o subtipo previsto
  (ductal carcinoma in situ ou invasive carcinoma) com a probabilidade;
- contagens agregadas;
- até 3 imagens de patches (âncoras visuais).

Regras:
1. Use apenas a evidência fornecida. Não invente achados morfológicos que não estejam nela.
2. Se comentar as imagens, deixe claro que é uma impressão visual não verificada.
3. Aponte inconsistências na evidência (por exemplo, mistura de categorias, probabilidades baixas).
4. Escreva em português, de forma objetiva.

Responda nesta estrutura:
## Resumo da evidência
## Impressão diagnóstica sugerida
(com grau de confiança — alto, moderado ou baixo — justificado pelos números)
## Regiões para revisão prioritária
(coordenadas e o motivo)
## Limitações
(inclua que o texto foi gerado automaticamente e precisa de confirmação por patologista)

Termine com uma última linha exatamente neste formato, escolhendo uma única opção:
CLASSIFICAÇÃO FINAL: benigno | atípico | DCIS | carcinoma invasivo"""

CLASSES_FINAIS = {"benigno": "benigno", "atípico": "atipico", "atipico": "atipico", "dcis": "DCIS",
                  "carcinoma invasivo": "IC"}


def classificacao_final(texto):
    """Classe da linha 'CLASSIFICAÇÃO FINAL: ...' (benigno, atipico, DCIS, IC) ou None."""
    m = re.findall(r"CLASSIFICA[ÇC][ÃA]O FINAL\W*([^\n]+)", texto, flags=re.IGNORECASE)
    if not m:
        return None
    resp = m[-1].strip(" *_.:").lower()
    achadas = {v for k, v in CLASSES_FINAIS.items() if k in resp}
    return achadas.pop() if len(achadas) == 1 else None


def chamar(modelo, prompt, imagens):
    corpo = {"model": modelo, "stream": False, "options": OPCOES,
             "messages": [{"role": "system", "content": INSTRUCOES},
                          {"role": "user", "content": prompt, "images": imagens}]}
    req = urllib.request.Request(OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())


def rodar(svs=None, k=32, sufixo="_uni", modelo="medgemma:4b", com_imagens=True) -> dict:
    stem = resolver_svs(svs).stem
    e4, saida = dir_resultados(stem, "estagio4"), dir_resultados(stem, "estagio5")
    prompt = (e4 / f"estagio4_prompt_k{k}{sufixo}.txt").read_text(encoding="utf-8")
    ancoras = sorted((e4 / f"estagio4_prompt_k{k}{sufixo}_ancoras").glob("*.png")) if com_imagens else []
    imagens = [base64.b64encode(p.read_bytes()).decode() for p in ancoras]

    t0 = time.time()
    r = chamar(modelo, prompt, imagens)
    texto = r["message"]["content"]
    nome = f"prelaudo_k{k}{sufixo}_{modelo.replace(':', '-')}"
    (saida / f"{nome}.md").write_text(texto, encoding="utf-8")
    meta = {"lamina": stem, "rotulo_real_nao_enviado_ao_modelo": info_lamina(stem).get("rotulo"),
            "classificacao_final": classificacao_final(texto),
            "modelo": modelo, "opcoes": OPCOES, "imagens": [p.name for p in ancoras],
            "segundos": round(time.time() - t0, 1), "tokens_entrada": r.get("prompt_eval_count"),
            "tokens_saida": r.get("eval_count")}
    (saida / f"{nome}.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return {**meta, "texto": texto}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--svs")
    p.add_argument("--k", type=int, default=32)
    p.add_argument("--sufixo", default="_uni")
    p.add_argument("--modelo", default="medgemma:4b")
    p.add_argument("--sem-imagens", action="store_true")
    a = p.parse_args()
    r = rodar(a.svs, a.k, a.sufixo, a.modelo, not a.sem_imagens)
    print(r["texto"])
    print(f"\n[{r['modelo']} | {r['segundos']} s | rótulo real: {r['rotulo_real_nao_enviado_ao_modelo']}]")
