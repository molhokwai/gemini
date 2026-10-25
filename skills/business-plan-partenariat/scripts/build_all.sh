#!/usr/bin/env bash
# Usage: build_all.sh config.json dossier_sortie
# Variables facultatives: PYTHON (défaut python3), NODE_PATH (où trouver le module npm "docx")
set -e
CFG="$1"; OUT="${2:-.}"; HERE="$(cd "$(dirname "$0")" && pwd)"; PY="${PYTHON:-python3}"
mkdir -p "$OUT"
NAME=$($PY -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))['short_name'])" "$CFG")
# feuilles reprises dans la partie PLAN (config "plan_sheets"; défaut ci-dessous)
SHEETS=$($PY -c "import json,sys;c=json.load(open(sys.argv[1],encoding='utf-8'));print(','.join(c.get('plan_sheets',['Résumé','Achats-Charges','Investissement','Exploitation Mensuelle'])))" "$CFG")
XLSX="$OUT/Plan_Affaires_${NAME}.xlsx"
$PY "$HERE/build_xlsx.py" "$CFG" "$XLSX"
$PY "$HERE/recalc.py" "$XLSX" 90
$PY "$HERE/export_sheets.py" "$XLSX" "${XLSX%.xlsx}.plan.json" "$SHEETS"
node "$HERE/build_docx.js" "$CFG" "${XLSX%.xlsx}.computed.json" "$OUT/Proposition_Partenariat_${NAME}.docx" "${XLSX%.xlsx}.plan.json"
