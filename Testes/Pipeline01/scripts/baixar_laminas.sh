#!/usr/bin/env bash
# Baixa lâminas (WSI .svs) do BRACS pelo FTP oficial do dataset.
#
# Credenciais NÃO ficam aqui (repositório público): exporte antes de rodar
#   export BRACS_FTP_USER=...  BRACS_FTP_PASS=...
#
# Uso:
#   bash baixar_laminas.sh                    # primeira leva recomendada (1 por classe)
#   bash baixar_laminas.sh train/Group_MT/Type_IC/BRACS_1003677.svs ...   # lâminas específicas
#   bash baixar_laminas.sh --segunda-leva     # 8 lâminas novas pra teste fora da amostra
#   bash baixar_laminas.sh --anotacoes        # só as anotações oficiais (~2,4 MB)

set -euo pipefail

: "${BRACS_FTP_USER:?exporte BRACS_FTP_USER}"
: "${BRACS_FTP_PASS:?exporte BRACS_FTP_PASS}"

FTP="ftp://histoimage.na.icar.cnr.it"
DESTINO="/media/medeiros/HD 1TB/BRACS"
DESTINO_ANOT="$DESTINO/anotacoes"

# Primeira leva: 1 lâmina por classe (rótulo da lâmina), só entre as que já têm
# recorte de RoI local (pra dar pra validar), priorizando tamanho pequeno e
# RoIs de mais de uma classe. Total ~5,1 GB.
RECOMENDADAS=(
  "train/Group_BT/Type_N/BRACS_1003718.svs"    # 0,07 GB | RoIs: N 1
  "train/Group_BT/Type_PB/BRACS_1370.svs"      # 0,87 GB | RoIs: PB 2, N 3
  "val/Group_BT/Type_UDH/BRACS_1592.svs"       # 0,85 GB | RoIs: UDH 1, N 1
  "train/Group_AT/Type_FEA/BRACS_1774.svs"     # 0,85 GB | RoIs: FEA 8, PB 4
  "val/Group_AT/Type_ADH/BRACS_1271.svs"       # 0,67 GB | RoIs: ADH 4, FEA 6, UDH 4, PB 2
  "train/Group_MT/Type_DCIS/BRACS_1489.svs"    # 1,16 GB | RoIs: DCIS 18
  "train/Group_MT/Type_IC/BRACS_1003677.svs"   # 0,18 GB | RoIs: IC 1
)

# Segunda leva: lâminas pra conferir o banco de frases ajustado na primeira (teste fora da amostra).
# Todas com recorte de RoI local, de pacientes que não aparecem na primeira leva nem entre si.
# Uma por classe + uma N extra (benigno é a categoria com menos tiles).
SEGUNDA_LEVA=(
  "train/Group_BT/Type_N/BRACS_1507.svs"       # paciente 54  | RoIs: N 10
  "train/Group_BT/Type_N/BRACS_1641.svs"       # paciente 69  | RoIs: N 4
  "train/Group_BT/Type_PB/BRACS_1320.svs"      # paciente 31  | RoIs: PB 18, N 2
  "train/Group_BT/Type_UDH/BRACS_1617.svs"     # paciente 44  | RoIs: UDH 11, PB 3, N 2
  "train/Group_AT/Type_FEA/BRACS_743.svs"      # paciente 102 | RoIs: FEA 8, PB 19, N 1
  "train/Group_AT/Type_ADH/BRACS_1494.svs"     # paciente 49  | RoIs: ADH 11, UDH 36, PB 5, N 2, FEA 1
  "train/Group_MT/Type_DCIS/BRACS_1512.svs"    # paciente 48  | RoIs: DCIS 25
  "train/Group_MT/Type_IC/BRACS_297.svs"       # paciente 114 | RoIs: IC 22, N 7, PB 2
)

if [[ "${1:-}" == "--segunda-leva" ]]; then set -- "${SEGUNDA_LEVA[@]}"; fi

if [[ "${1:-}" == "--anotacoes" ]]; then
  mkdir -p "$DESTINO_ANOT"
  for f in train.zip val.zip test.zip; do
    wget --continue --user="$BRACS_FTP_USER" --password="$BRACS_FTP_PASS" \
      -O "$DESTINO_ANOT/$f" "$FTP/BRACS_WSI_Annotations/$f"
  done
  echo "Anotações em $DESTINO_ANOT"
  exit 0
fi

if [[ $# -gt 0 ]]; then LISTA=("$@"); else LISTA=("${RECOMENDADAS[@]}"); fi

mkdir -p "$DESTINO"
echo "Espaço livre: $(df -h "$DESTINO" | awk 'NR==2 {print $4}')"

for caminho in "${LISTA[@]}"; do
  nome="$(basename "$caminho")"
  echo "==> $nome"
  for tentativa in 1 2 3 4 5; do
    wget --continue --tries=3 --timeout=60 \
      --user="$BRACS_FTP_USER" --password="$BRACS_FTP_PASS" \
      -O "$DESTINO/$nome" "$FTP/BRACS_WSI/$caminho" && break
    echo "falhou (tentativa $tentativa), tentando de novo em 10s..."
    sleep 10
  done
done

echo "Concluído. Lâminas em $DESTINO"
