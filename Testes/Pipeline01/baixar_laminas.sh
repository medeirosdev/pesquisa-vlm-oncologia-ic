#!/usr/bin/env bash
# Baixa lâminas (WSI .svs) do BRACS pelo FTP oficial do ICAR-CNR.
#
# Credenciais NÃO ficam aqui (repositório público): exporte antes de rodar
#   export BRACS_FTP_USER=...  BRACS_FTP_PASS=...
#
# Uso:
#   bash baixar_laminas.sh                    # primeira leva recomendada (1 por classe)
#   bash baixar_laminas.sh train/Group_MT/Type_IC/BRACS_1003677.svs ...   # lâminas específicas
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
