# business-plan-partenariat (skill Kimi Code CLI)

Installation: copier ce dossier dans `~/.qwen/skills/` (global) ou `.kimi-code/skills/` (projet).
Prérequis: Python 3 + `openpyxl`, Node.js + `npm i docx`, LibreOffice (`soffice`) pour le recalcul.

Utilisation directe sans Kimi Code:
    cp assets/config.exemple.json mon_projet.json   # puis éditer
    bash scripts/build_all.sh mon_projet.json ./sortie

Sorties: Plan_Affaires_<short_name>.xlsx (+ .computed.json, .plan.json), Proposition_Partenariat_<short_name>.docx
(page de garde + table des matières, proposition d'une page avec le lien du tableur, puis les feuilles choisies)
