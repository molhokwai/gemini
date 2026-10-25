# Points à confirmer avec l'utilisateur (ne pas bloquer: choisir une valeur par défaut et la signaler)
1. Prix, volumes/jour, jours/semaine, semaines/mois.
2. Liste exacte du matériel (quantités, prix) et des achats récurrents (coût/mois).
3. Qui finance quoi et quelle part (`partner_capital_share`).
4. Partage des bénéfices avant/après ROI et base du ROI (CA ou bénéfice).
5. Dates de démarrage/achats, ville, emplacement, modalités de paiement.
6. Lignes/colonnes à masquer. Nom de fichier (orthographe!).
7. Feuilles à reprendre dans le PLAN (défaut: Résumé, Achats-Charges, Investissement, Exploitation Mensuelle) et lien du tableur (`spreadsheet_url`).

# Vérifications finales
- recalc.py: 0 erreur. Résumé = chiffres du message de l'utilisateur (investissement, CA/jour, profit).
- Contrôles: phases = 100 %; Répartition = profit; Exploitation hebdo/mensuelle cohérentes.
- Docx: PROPOSITION sur 1 page, lien du tableur présent (pas d'emplacement rouge), PLAN lisible (paysage si large); rendu vérifié en image; chiffres identiques à computed.json.
- Livrer par SendUserFile; en 2 phrases: chiffres clés + hypothèses prises (ex. phase 2 supposée).
