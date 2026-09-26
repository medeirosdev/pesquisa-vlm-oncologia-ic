"""
Roda a Pipeline 01 inteira em todas as lâminas baixadas e junta tudo numa tabela, pra ver
se os resultados que apareceram na BRACS_748 se repetem nas outras.

Por lâmina: estágio 1 (filtro + recall contra RoIs), estágio 2 (roteador, banco v2),
estágio 3 (descritores, bruto e normalizado, k=32), estágio 4 (agregação) e validação
(classificação por patch, por RoI e pela borda). Uma lâmina que falha não para as outras.

Saídas: resultados/consolidado.json e resultados_multilaminas.md (versionado).

Uso:
    .venv/bin/python scripts/rodar_todas_laminas.py
    .venv/bin/python scripts/rodar_todas_laminas.py --laminas BRACS_1370 BRACS_1592
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
for sub in ("", "estagio1_filtro_tecido", "estagio2_roteador", "estagio3_descritores",
            "estagio4_agregacao", "validacao"):
    sys.path.insert(0, str(PIPELINE_DIR / sub))

import agregacao_por_borda  # noqa: E402
import agregacao_por_roi  # noqa: E402
import agregador  # noqa: E402
import banco_por_classe  # noqa: E402
import categoria_descritor  # noqa: E402
import descritores  # noqa: E402
import filtro_tecido  # noqa: E402
import recall_roi  # noqa: E402
import roteador_topk  # noqa: E402
from comum.lamina import RESULTADOS_DIR, listar_laminas  # noqa: E402
from comum.rois import info_lamina  # noqa: E402

K_DESCRITORES = 32


def rodar_lamina(stem: str) -> dict:
    r = {"lamina": stem, **info_lamina(stem)}
    etapas = [
        ("filtro", lambda: filtro_tecido.rodar(stem)),
        ("recall", lambda: recall_roi.rodar(stem)),
        ("roteador", lambda: roteador_topk.rodar(stem, "v2")),
        ("descritor_bruto", lambda: descritores.rodar(stem, K_DESCRITORES)),
        ("descritor_norm", lambda: descritores.rodar(stem, K_DESCRITORES, normalizar=True)),
        ("agregacao", lambda: agregador.rodar(stem, K_DESCRITORES, ["", "_norm"])),
        ("categoria", lambda: categoria_descritor.rodar(stem)),
        ("por_patch", lambda: banco_por_classe.rodar(stem)),
        ("por_roi", lambda: agregacao_por_roi.rodar(stem)),
        ("borda", lambda: agregacao_por_borda.rodar(stem)),
    ]
    for nome, funcao in etapas:
        t0 = time.time()
        try:
            saida = funcao()
            if nome.startswith("descritor"):
                saida = {k: v for k, v in saida.items() if k != "descritores"}
            r[nome] = saida
            print(f"  {nome}: ok ({time.time() - t0:.0f}s)")
        except Exception as e:
            r[nome] = {"erro": f"{type(e).__name__}: {e}"}
            print(f"  {nome}: ERRO {type(e).__name__}: {e}")
            traceback.print_exc(limit=1)
    return r


def pct(v):
    return "—" if v is None else f"{100 * v:.0f}%"


def ponto_curva(roteador, k):
    for p in roteador.get("curva", []):
        if p["k"] == k:
            return p
    return None


def escrever_tabela(resultados: list[dict]):
    linhas = ["# Pipeline 01 em várias lâminas — consistência", "",
              f"Gerado por `scripts/rodar_todas_laminas.py` em {time.strftime('%d/%m/%Y %H:%M')}. "
              "Números por lâmina; detalhes em `resultados/<lamina>/`.", ""]

    linhas += ["## Estágio 1 — filtro de tecido (recall contra RoIs anotados)", "",
               "| Lâmina | Rótulo | Níveis da pirâmide | RoIs localizados | Classes dos RoIs | Cobertura média | RoIs ≥50% cobertos |",
               "|---|---|---|---|---|---|---|"]
    for r in resultados:
        rc = r.get("recall", {})
        if "erro" in rc or not rc:
            linhas.append(f"| {r['lamina']} | {r['rotulo']} | — | erro: {rc.get('erro', '—')} | | | |")
            continue
        classes = ", ".join(f"{c} {n}" for c, n in rc["classes"].items())
        linhas.append(f"| {r['lamina']} | {r['rotulo']} | {'/'.join(map(str, rc['niveis_piramide']))}x | "
                      f"{rc['rois_localizados']}/{rc['rois_total']} | {classes} | "
                      f"{pct(rc['cobertura_media'])} | {pct((rc['pct_rois_cobertura_ge_50'] or 0) / 100 if rc['cobertura_media'] is not None else None)} |")

    linhas += ["", "## Estágio 2 — roteador (banco v2)", "",
               "| Lâmina | Candidatos | Precisão k=32 (aleatório) | Recall k=32 | Precisão k=256 (aleatório) | Recall k=256 |",
               "|---|---|---|---|---|---|"]
    for r in resultados:
        ro = r.get("roteador", {})
        if "erro" in ro or not ro:
            linhas.append(f"| {r['lamina']} | erro | | | | |")
            continue
        p32, p256 = ponto_curva(ro, 32), ponto_curva(ro, 256)
        fmt = lambda p, campo: "—" if not p else pct(p[campo])
        linhas.append(f"| {r['lamina']} | {ro['candidatos']} | {fmt(p32, 'precisao')} ({fmt(p32, 'precisao_aleatoria')}) | "
                      f"{fmt(p32, 'recall')} | {fmt(p256, 'precisao')} ({fmt(p256, 'precisao_aleatoria')}) | {fmt(p256, 'recall')} |")

    def cats(d):
        return " / ".join(str(d.get(c, 0)) for c in ("benigno", "atipico", "maligno"))

    linhas += ["", "## Estágio 3 — descritor nos k=32 patches do roteador", "",
               "Categorias = quantos patches o descritor chamou de benigno / atípico / maligno.", "",
               "| Lâmina | Rótulo | Bruto: categorias | Bruto: achado dominante (% patches) | "
               "Normalizado: categorias | Normalizado: achado dominante (% patches) |",
               "|---|---|---|---|---|---|"]
    for r in resultados:
        b, n = r.get("descritor_bruto", {}), r.get("descritor_norm", {})
        if "erro" in b or "erro" in n or not b:
            linhas.append(f"| {r['lamina']} | {r['rotulo']} | erro | | | |")
            continue
        linhas.append(f"| {r['lamina']} | {r['rotulo']} | {cats(b['categorias_selecionados'])} | "
                      f"{', '.join(b['combinacao_mais_comum'])} ({b['pct_combinacao_mais_comum']:.0f}%) | "
                      f"{cats(n['categorias_selecionados'])} | "
                      f"{', '.join(n['combinacao_mais_comum'])} ({n['pct_combinacao_mais_comum']:.0f}%) |")

    linhas += ["", "## Validação — o descritor acerta a categoria (benigno / atípico / maligno)?", "",
               "Todos os tiles que caem dentro de RoIs anotados, não só o top-k. "
               "Baseline = sempre chutar a categoria majoritária.", "",
               "| Lâmina | Categorias reais (b / a / m) | Bruto: acurácia | Bruto: previstas (b / a / m) | "
               "Normalizado: acurácia | Normalizado: previstas (b / a / m) | Baseline |",
               "|---|---|---|---|---|---|---|"]
    for r in resultados:
        c = r.get("categoria", {})
        if "erro" in c or not c:
            linhas.append(f"| {r['lamina']} | erro | | | | | |")
            continue
        linhas.append(f"| {r['lamina']} | {cats(c['distribuicao_real'])} (n={c['n_patches_rotulados']}) | "
                      f"{pct(c['bruto']['acuracia'])} | {cats(c['bruto']['preditas'])} | "
                      f"{pct(c['norm']['acuracia'])} | {cats(c['norm']['preditas'])} | {pct(c['baseline_maioria'])} |")

    linhas += ["", "## Validação — classificação por banco de frases de classe", "",
               "\"Presentes\" = argmax só entre as classes que existem nos RoIs da lâmina; "
               "\"7 classes\" = entre todos os bancos. Baseline = sempre chutar a classe majoritária.", "",
               "| Lâmina | Por patch (presentes / 7 classes / baseline) | Por RoI (presentes / baseline) | "
               "Borda (presentes) | Interior (presentes) |",
               "|---|---|---|---|---|"]
    for r in resultados:
        pp, pr, bo = r.get("por_patch", {}), r.get("por_roi", {}), r.get("borda", {})
        if any("erro" in x for x in (pp, pr, bo)):
            linhas.append(f"| {r['lamina']} | erro | | | |")
            continue
        borda = bo.get("borda_classes_presentes", {})
        interior = bo.get("interior_classes_presentes", {})
        linhas.append(
            f"| {r['lamina']} | {pct(pp.get('acuracia_classes_presentes'))} / {pct(pp.get('acuracia_7_classes'))} / "
            f"{pct(pp.get('baseline_maioria'))} (n={pp.get('n_patches_rotulados')}) | "
            f"{pct(pr.get('acuracia_media_classes_presentes'))} / {pct(pr.get('baseline_maioria'))} (n={pr.get('n_rois')}) | "
            f"{pct(borda.get('acuracia'))} (n={borda.get('n_rois', 0)}) | {pct(interior.get('acuracia'))} (n={interior.get('n_rois', 0)}) |")

    (PIPELINE_DIR / "resultados_multilaminas.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--laminas", nargs="+", help="nomes das lâminas (padrão: todas em laminas_dir)")
    a = parser.parse_args()
    stems = a.laminas or [p.stem for p in listar_laminas()]

    resultados = []
    for stem in stems:
        print(f"=== {stem} ===")
        resultados.append(rodar_lamina(stem))
        RESULTADOS_DIR.mkdir(exist_ok=True)
        (RESULTADOS_DIR / "consolidado.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False),
                                                         encoding="utf-8")
        escrever_tabela(resultados)
    print(f"\nTabela em {PIPELINE_DIR / 'resultados_multilaminas.md'}")


if __name__ == "__main__":
    main()
