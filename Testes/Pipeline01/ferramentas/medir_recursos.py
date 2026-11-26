"""
Quanto custa rodar a pipeline num computador comum? Medição de tempo e memória de cada etapa, por lâmina, no notebook
do projeto (GPU de 4 GB), com a GPU e só com a CPU. Sustenta (ou não) a proposta de uma pipeline que roda num
computador acessível a um hospital, sem nuvem e sem enviar dados do paciente para fora.

Fixado ANTES de medir (commit anterior às medidas; medição descritiva, sem critério de passou/não passou):
  Lâminas: as 3 primeiras lâminas de teste do pulmão (tcga_descritor_prelaudo.laminas_teste, na ordem da lista), baixadas
     do GDC para o HD, medidas e apagadas.
  Etapas, cronometradas separadamente para cada lâmina:
     1. abrir a lâmina, miniatura, máscara de tecido e grade de patches;
     2. UNI2-h em até 2.000 patches de tecido (amostra com semente 0), leitura dos patches incluída:
        GPU (meia precisão, lote do projeto); CPU (precisão simples) só nos primeiros 64 patches, com o tempo das 2.000
        estimado por proporção (marcado como estimado);
     3. decisão: os 5 ABMIL (treinados nas lâminas de treino do pulmão; o tempo de treino também é medido, uma vez),
        GPU e CPU;
     4. descritor (regressão logística do LungHist700) nos patches;
     5. pré-laudo: Gemma 3 4B pelo Ollama com os campos e as instruções finais, uma chamada (pulmão, português),
        com a GPU (como o Ollama decidir) e só com a CPU (num_gpu = 0).
  Memória: pico de memória da GPU pelo PyTorch (etapas 2 e 3) e pelo nvidia-smi durante o modelo de linguagem; pico
     de RAM do processo Python (ru_maxrss) e do processo do Ollama (VmHWM).
  Também registrado: modelo da GPU e da CPU, RAM total, versão do Ollama e quantização do modelo de linguagem.
  Correção depois da primeira execução, antes de qualquer medida do modelo de linguagem: o Ollama não conseguiu memória
     na GPU porque o PyTorch ainda guardava a VRAM das etapas 2 e 3, e a chamada falhou (erro 500); o vigia da VRAM não
     parava e o script não saiu. Agora o UNI2-h e os ABMIL saem da memória e o cache da GPU é liberado antes da etapa 5
     (num hospital as etapas também rodariam em sequência), e o vigia para mesmo com erro. As etapas 1 a 4 não mudaram.

Uso (venv do projeto; HD montado; Ollama no ar): .venv/bin/python ferramentas/medir_recursos.py
Saída: resultados/recursos/resumo.json
"""

import csv
import json
import platform
import random
import resource
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import comum.caminhos  # noqa: E402,F401

import numpy as np  # noqa: E402

from comum.lamina import RESULTADOS_DIR, Lamina, raiz_hd  # noqa: E402

SAIDA = RESULTADOS_DIR / "recursos"
N_LAMINAS, N_CPU = 3, 64


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"erro: {e}"


def ollama_pid():
    out = sh("pgrep -x ollama")
    return out.split()[0] if out else None


def vmhwm(pid):
    try:
        for l in open(f"/proc/{pid}/status"):
            if l.startswith("VmHWM"):
                return round(int(l.split()[1]) / 1024, 1)
    except Exception:  # noqa: BLE001
        return None


def chamar_llm(campos, instrucoes, cpu):
    import sintese
    from tcga_descritor_prelaudo import MODELO
    opcoes = dict(sintese.OPCOES, **({"num_gpu": 0} if cpu else {}))
    corpo = {"model": MODELO, "stream": False, "options": opcoes,
             "messages": [{"role": "system", "content": instrucoes}, {"role": "user", "content": campos}]}
    vram, parar = [], [False]
    import threading

    def vigiar():
        while not parar[0]:
            v = sh("nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits")
            if v.isdigit():
                vram.append(int(v))
            time.sleep(0.5)
    th = threading.Thread(target=vigiar, daemon=True)
    th.start()
    t0 = time.time()
    req = urllib.request.Request(sintese.OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            resp = json.loads(r.read())
    finally:
        parar[0] = True
        th.join()
    dt = time.time() - t0
    return {"segundos": round(dt, 1), "tokens_gerados": resp.get("eval_count"),
            "tokens_por_segundo": round(resp["eval_count"] / (resp["eval_duration"] / 1e9), 2) if resp.get("eval_duration") else None,
            "vram_pico_mib_nvidia_smi": max(vram) if vram else None, "ram_pico_ollama_mib": vmhwm(ollama_pid())}


def main():
    import torch
    from aviso_discordancia import instrucoes
    from comum.tecido import mascara_tecido
    from comum.uni import LOTE, _preparar, carregar_uni2h
    from mil_atencao import SEMENTES, treinar
    from pulmao_descritor import aplicar_todos
    from tcga_baixar_e_embutir import N_AMOSTRA, baixar, grade, mpp
    from tcga_descritor_prelaudo import PASTA, laminas_teste
    from tcga_mil import CLASSES, LISTA
    SAIDA.mkdir(parents=True, exist_ok=True)
    gpu = torch.cuda.is_available()
    info = {"gpu": torch.cuda.get_device_name(0) if gpu else None,
            "vram_total_mib": round(torch.cuda.get_device_properties(0).total_memory / 2**20) if gpu else None,
            "cpu": sh("lscpu | grep 'Model name' | sed 's/Model name:\\s*//'"), "nucleos": sh("nproc"),
            "ram_total_gib": round(int(sh("grep MemTotal /proc/meminfo | awk '{print $2}'")) / 2**20, 1),
            "sistema": platform.platform(), "torch": torch.__version__,
            "ollama": sh("curl -s localhost:11434/api/version"),
            "modelo_linguagem": sh("curl -s localhost:11434/api/show -d '{\"model\":\"gemma3:4b\"}' | python3 -c "
                                   "\"import sys,json;d=json.load(sys.stdin)['details'];print(d.get('parameter_size'),d.get('quantization_level'))\"")}
    print(info, flush=True)

    # treino dos 5 ABMIL (uma vez) com as lâminas de treino do pulmão
    linhas = list(csv.DictReader(open(LISTA, encoding="utf-8"), delimiter="\t"))
    tr = [l for l in linhas if l["conjunto"] == "treino" and (PASTA / l["file_id"] / "meta.json").exists()]
    Xtr = [torch.from_numpy(np.load(PASTA / l["file_id"] / "amostra2000.npy")) for l in tr]
    ytr = np.array([CLASSES.index(l["projeto"]) for l in tr])
    t0 = time.time()
    modelos = [treinar(Xtr, ytr, s, "cuda" if gpu else "cpu", k=2).eval() for s in SEMENTES]
    info["treino_5_abmil_segundos"] = round(time.time() - t0, 1)
    del Xtr

    uni = carregar_uni2h()
    tmp = Path(raiz_hd()) / "TCGA_pulmao_tmp"
    tmp.mkdir(exist_ok=True)
    por = []
    for l in laminas_teste()[:N_LAMINAS]:
        svs = tmp / l["file_name"]
        baixar(l, svs)
        r = {"tamanho_mb": round(svs.stat().st_size / 2**20)}
        t0 = time.time()
        lam = Lamina(svs)
        res = mpp(lam)
        lado = int(round(128.0 / res))
        rgb, ds = lam.thumbnail(32)
        xy = grade(lam, mascara_tecido(rgb), ds, lado)
        amostra = sorted(random.Random(0).sample(xy, min(N_AMOSTRA, len(xy))))
        r.update({"etapa1_tecido_s": round(time.time() - t0, 2), "patches_tecido": len(xy), "patches_amostra": len(amostra),
                  "mpp": res})
        # 2. UNI2-h na GPU
        if gpu:
            torch.cuda.reset_peak_memory_stats()
            uni = uni.cuda().half()
            torch.cuda.synchronize()
            t0, embs = time.time(), []
            for i in range(0, len(amostra), LOTE):
                lote = np.stack([_preparar(lam.janela_nativa(x0, y0, lado)) for x0, y0 in amostra[i:i + LOTE]])
                with torch.no_grad():
                    embs.append(uni(torch.from_numpy(lote).cuda().half()).float().cpu().numpy())
            torch.cuda.synchronize()
            r["etapa2_uni_gpu_s"] = round(time.time() - t0, 1)
            r["etapa2_vram_pico_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)
            E = np.concatenate(embs)
        # 2. UNI2-h na CPU (64 patches, estimado para a amostra inteira)
        uni_cpu = uni.cpu().float()
        t0 = time.time()
        for i in range(0, N_CPU, 16):
            lote = np.stack([_preparar(lam.janela_nativa(x0, y0, lado)) for x0, y0 in amostra[i:i + 16]])
            with torch.no_grad():
                uni_cpu(torch.from_numpy(lote))
        dt = time.time() - t0
        r["etapa2_uni_cpu_64_s"] = round(dt, 1)
        r["etapa2_uni_cpu_amostra_s_estimado"] = round(dt / N_CPU * len(amostra), 0)
        uni = uni_cpu
        lam.tif.close()
        svs.unlink()
        x = torch.from_numpy(E)
        # 3. decisão
        for disp in (["cuda", "cpu"] if gpu else ["cpu"]):
            if disp == "cuda":
                torch.cuda.reset_peak_memory_stats()
            t0 = time.time()
            with torch.no_grad():
                p = np.mean([float(torch.softmax(m.to(disp)(x.to(disp))[0], 0)[1]) for m in modelos])
            if disp == "cuda":
                torch.cuda.synchronize()
                r["etapa3_vram_pico_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)
            r[f"etapa3_mil_{disp}_s"] = round(time.time() - t0, 3)
        r["p_lusc"] = round(p, 4)
        # 4. descritor
        t0 = time.time()
        aplicar_todos([E])
        r["etapa4_descritor_s_com_treino_lunghist700"] = round(time.time() - t0, 1)
        por.append(r)
        print(r, flush=True)

    # libera a GPU para o modelo de linguagem
    del modelos, uni, uni_cpu, x, E
    import gc
    gc.collect()
    if gpu:
        torch.cuda.empty_cache()

    # 5. pré-laudo (campos reais de um documento do pulmão, português)
    from aviso_discordancia import SAIDA as SAIDA_AVISO, documentos
    k = documentos("pulmao")[0][0]
    campos = (SAIDA_AVISO / "pulmao" / f"{k}_campos.txt").read_text(encoding="utf-8")
    info["etapa5_llm_gpu"] = chamar_llm(campos, instrucoes("pulmao"), cpu=False)
    info["etapa5_llm_cpu"] = chamar_llm(campos, instrucoes("pulmao"), cpu=True)
    info["ram_pico_python_mib"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    resumo = {"maquina": info, "por_lamina": por,
              "medias": {c: round(float(np.mean([r[c] for r in por if c in r])), 2)
                         for c in por[0] if isinstance(por[0][c], (int, float))}}
    (SAIDA / "resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
