---
name: business-plan-partenariat
description: Génère un plan d'affaires Excel paramétrable (investissement, charges, ventes, exploitation hebdo/mensuelle, partage des bénéfices avant/après ROI) et une proposition de partenariat Word pour un investisseur — page de garde + table des matières, la proposition sur une page avec le lien vers le tableur, puis le plan (les feuilles choisies). À utiliser dès que l'utilisateur veut un plan similaire pour une nouvelle activité (cantine, gaufres, crêpes, jus, commerce, formation en ligne) ou un autre partenaire, même sans dire "skill".
---

# Plan d'affaires + proposition de partenariat

Processus de MANSA/MENGUE (cantine, puis gaufres & crêpes avec Mr Nolan, puis MANSA Learn avec Kader), rendu reproductible.

## Format de la proposition (défaut, `layout: "full"`, modèle: proposition Nolan Crêpes+Gaufres)
1. **Page de garde**: titre, sous-titre (activité — partenaire), **TABLE DES MATIÈRES** (liens internes).
2. **PROPOSITION DE PARTENARIAT › PROPOSITION**: à l'attention de / préparé par, projet, investissement, prévisions, ROI et partage, modalités, signatures — **une page** — puis **toujours le lien vers le tableur** (après les signatures).
3. **PLAN**: le lien vers le tableur, puis une section par feuille choisie (`plan_sheets`), avec ses tableaux; une feuille large (> 7 colonnes) passe en **paysage**, coupée en tableaux de 12 périodes. Pied de page « page X / N ».

`layout: "one_page"`: l'ancienne proposition seule, sur une page.

## Étapes
1. **Recueillir les données** (voir `references/checklist.md`). Si l'utilisateur colle un message (ex. WhatsApp), en extraire prix, volumes, achats, matériel, dates. Ne poser des questions que pour ce qui change le résultat; sinon prendre une valeur par défaut et la signaler. Demander aussi:
   - **les feuilles à reprendre dans le PLAN**, au choix parmi: Résumé, Paramètres, Achats-Charges, Investissement, Ventes, Compte de Résultat, Répartition Bénéfices, Exploitation Mensuelle, Exploitation Hebdomadaire. **Défaut: Résumé, Achats-Charges, Investissement, Exploitation Mensuelle** (`plan_sheets`).
   - **le lien du tableur** (`spreadsheet_url`): Google Sheets ou fichier Drive. S'il n'existe pas encore: générer, déposer le .xlsx (Drive), récupérer son lien, renseigner `spreadsheet_url`, régénérer le .docx. Sans lien, le document porte « [lien du tableur à ajouter] » en rouge et le script affiche un avertissement: ne jamais livrer ainsi sans le dire.
2. **Créer le config**: copier `assets/config.exemple.json`, remplacer les valeurs (activité, partenaire, produits, ingrédients, matériel, partage, dates, `plan_sheets`, `spreadsheet_url`).
3. **Générer**: `bash scripts/build_all.sh config.json dossier_sortie` (variables `PYTHON`, `NODE_PATH` si `openpyxl` / `docx` sont dans un venv ou un `node_modules` à part)
   - `build_xlsx.py`: classeur 100 % formules, avec `.computed.json` des chiffres clés.
   - `recalc.py`: recalcul LibreOffice (0 erreur exigé).
   - `export_sheets.py`: les feuilles `plan_sheets`, recalculées, en blocs (titres, notes, tableaux) → `.plan.json`.
   - `build_docx.js`: la proposition, mêmes chiffres.
4. **Vérifier**: ouvrir le Résumé recalculé, comparer aux chiffres de l'utilisateur; convertir le docx en PDF puis en images (`soffice --convert-to pdf`, `pdftoppm`) et contrôler: la PROPOSITION tient sur une page, le lien est présent, les tableaux du PLAN sont lisibles (paysage pour les feuilles larges).
5. **Livrer** (fichiers + lien). Résumer en 2-3 phrases: investissement, CA, bénéfice/mois, ROI, hypothèses prises (ex. pourcentages de phase 2, jours ouvrés).

## Règles
- Français; montants en "f" (FCFA); l'utilisateur est le conseil de MANSA/MENGUE.
- Proposition: la partie PROPOSITION ≤ 1 page. Variante à paliers (50/75/100 % → 30/37,5/45 %): via `extra_clauses`.
- Toujours le lien vers le tableur dans la proposition.
- Toujours signaler les hypothèses non confirmées et le piège jours ouvrés vs calendaires (`references/conventions.md`).
- Lignes cachées: `hidden` dans le config (elles sont aussi omises du PLAN); demander lesquelles si le fichier vient de Google Sheets.
- Livrer en .xlsx; pour Google Sheets: Fichier → Importer → Remplacer la feuille de calcul.
- Activité hors restauration, ROI sur la part du partenaire: clés optionnelles dans `references/conventions.md`.
- Étendre le script (nouvelles feuilles, plats × combinaisons) en mettant à jour les constantes de lignes.
