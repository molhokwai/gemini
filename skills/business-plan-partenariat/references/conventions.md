# Conventions du plan Excel et pièges connus

## Couleurs et formats
- Police bleue + fond jaune: valeur saisie. Vert: lien vers une autre feuille. Noir: formule.
- Devise: suffixe " f" (config `currency_suffix`). Pourcentages stockés en fractions.
- Jamais de texte commençant par "=" (devient une formule: #VALUE!/#N/A).
- Noms de feuilles avec espaces: toujours entre apostrophes dans les formules.

## Structure (feuilles)
Résumé · Paramètres · Achats-Charges · Investissement (matériel, Seed = matériel + 1re semaine, Total = matériel + 1er mois) · Ventes · Compte de Résultat (bloc hebdo puis mensuel) · Répartition Bénéfices (aperçu hebdo + mensuel) · Exploitation Mensuelle · Exploitation Hebdomadaire.
Les numéros de lignes sont fixes dans le script (constantes R_*, ACH_TOT, INV_*, VEN_TOT, CR_*): si on ajoute une ligne, mettre à jour ces constantes.

## Logique de bascule (phase 1 → phase 2)
- ROI = Investissement total ÷ (CA/jour ou bénéfice/jour selon `roi_basis`) = jours ouvrés.
- Semaine de bascule = ⌈jours ÷ jours/semaine⌉; mois de bascule = arrondi au plus proche (min. 1). Les deux sont surchargeables via `switch_week` / `switch_month` et modifiables dans Paramètres.
- Cas cantine "plats préparés": le partenaire était à 55 % jusqu'au 5e mois, puis 45 % (le ROI y est cumulé sur la part de bénéfice, pas sur le CA): dans ce cas, renseigner `switch_month` explicitement.
- Attention calendaire: "≈ 3 semaines" (jours calendaires) ≠ 5 semaines ouvrées (5 j/semaine). Le skill utilise les jours ouvrés; dire clairement lequel dans le document.

## Barème de partenaire (variante cantine)
Proposition à paliers: 50 % d'investissement → 30 % des bénéfices; 75 % → 37,5 %; 100 % → 45 %, pour X années, paiement chaque début de mois. Pour ce cas, utiliser `partner_capital_share` + phases, et ajouter le barème dans `extra_clauses`.

## Lignes/colonnes masquées
`hidden: {"Feuille": {"rows": [..], "columns": ["C"]}}` dans le config. Si l'utilisateur travaille dans Google Sheets, l'état masqué n'est pas lisible via l'API Drive: lui demander lesquelles.

## Google Sheets / Drive
- Impossible de modifier le contenu d'une feuille Google existante; l'upload de gros fichiers via MCP échoue souvent.
- Livrer le .xlsx avec SendUserFile et expliquer: Fichier → Importer → Remplacer la feuille de calcul.

## Activité hors restauration (ex. formation en ligne) — clés optionnelles (ajoutées 2026-10-06, MANSA Learn)
- Charge variable dans `ingredients`: `"pct_of_revenue": 0.02` (ex. frais Notch Pay) ou `"per_unit": 500` (coût par unité vendue) à la place de `monthly_cost`; écrite en formule liée aux Ventes.
- `labels`: `charges_title`, `charges_note`, `equipment` (ex. « Démarrage »), `first_month`, `costs` — remplacent les libellés « Ingrédients / Matériel / Approvisionnement ».
- Textes du .docx: `project_text` (§1), `assumptions_text` (sous §3), `payback_text` (§4).
- Volumes faibles (apprenants / mois): `volume_per_day` = volume mensuel ÷ (jours/semaine × semaines/mois); le dire dans `assumptions_text`.
- Retour mesuré sur la part de l'investisseur (pas sur le bénéfice total): calculer le mois et le fixer par `switch_month` (arrondi au-dessus, jamais au plus proche).
- `split.roi_on_partner_share: true`: le retour se mesure sur ce que le partenaire reçoit (bénéfice × sa part de Phase 1); les bascules semaine et mois sont alors arrondies au-dessus, sans `switch_month` à fixer à la main.
