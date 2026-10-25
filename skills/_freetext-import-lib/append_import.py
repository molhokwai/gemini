#!/usr/bin/env python3
"""
Reformats free text into the mini-DSL the existing "Import" (JM) / "Import Registre" (Finance)
Apps Script triggers already understand, then appends it as a new row via the Sheets API
(values.append) — never writes to "Dépôt / vente" or "Registre" directly, so the existing
triggers' matching/validation/graceful-degradation logic runs exactly as it does for a human
pasting text into the AppSheet form. See life/50-work/66-freetext-import-skills-request.md for
the design rationale (Solution 1: reformat only, submit through the existing trigger).

Usage:
  python3 append_import.py --target jm        --text "..."
  python3 append_import.py --target registre  --text "..."
  echo "..." | python3 append_import.py --target registre

Depends on sheets_oauth.py (same directory) for Sheets API access, and on the provider-router
skill (~/.qwen/skills/provider-router/scripts/route_provider.py) for the secondary LLM.
LLM API keys are loaded from the nkensa project's .env.local (never hardcoded, never printed).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sheets_oauth import get_access_token

PROVIDER_ROUTER_SCRIPT = os.path.expanduser(
    '~/.qwen/skills/provider-router/scripts/route_provider.py'
)
PROVIDER_ROUTER_CONFIG = os.path.expanduser(
    '~/.qwen/skills/provider-router/scripts/providers.json'
)
ENV_LOCAL_PATH = (
    '/media/nkensa/win11/Users/Nkensa/GDrive-local/Tree/Workspaces/2/emelit/src/dev/projects'
    '/nkensa/.env.local'
)

SPREADSHEET_ID = '1_0FPWIfXnybS2C4B0BM0E05_zXniLqjFL9DU06au-PE'  # "Registre Financier — life/"


def _load_env_local(path):
    """Minimal KEY="VALUE" .env parser (stdlib only) — loads API keys into os.environ so the
    route_provider.py subprocess (which reads them by name) sees them, without requiring the
    calling shell to have exported anything first. Never overrides a var already set in the
    environment (lets an explicit `export` win, e.g. for testing a different key)."""
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env_local(ENV_LOCAL_PATH)

TARGETS = {
    'jm': {
        'sheet': 'Import',
        'dsl_doc': '''Format cible ("Import", pour "Dépôt / vente" — livraisons/collectes JM) :

## <date, ex: "1 sept 2026">
<noms de colonnes séparés par virgules, un sous-ensemble de : Nom, Lieu, Livré, Vendu, Collecté, Solde, Notes>
<une ligne de données par point, valeurs séparées par virgules, dans le même ordre que les colonnes déclarées>

Règles :
- Ne déclare JAMAIS de colonne "Nr" — le trigger le résout tout seul par recherche du "Nom" dans "Points de dépôt / vente" (2026-09-15 : Nr est une référence dure, jamais un nombre à deviner depuis le texte).
- Le nom du point (colonne "Nom") doit correspondre autant que possible à un nom réel de "Points de dépôt / vente" (le trigger tolère un nom non reconnu — il ajoute quand même la ligne avec un avertissement — mais un nom exact évite l'avertissement, et est nécessaire pour que Nr se résolve correctement).
- Les valeurs numériques (Livré, Vendu, Collecté) peuvent inclure du texte autour (ex: "14 livrées") — le texte est ignoré, seul le nombre est gardé par le trigger. Écris-les simplement, sans sur-nettoyer.
- Peut contenir plusieurs blocs "## <date>" si le texte source couvre plusieurs jours/points sans date commune.
- N'invente JAMAIS un point, une quantité ou une date qui n'est pas clairement dans le texte source. En cas de doute sur une valeur, laisse-la de côté plutôt que de deviner.

Exemple :
## 1 sept 2026
Nom, Lieu, Livré
Américain, Carr Fouda - Messassi, 14 livrées''',
    },
    'registre': {
        'sheet': 'Import Registre',
        'dsl_doc': '''Format cible ("Import Registre", pour "Registre" — transactions/événements personnels et JM) :

## <date, ex: "13 sept 2026">
<noms de colonnes séparés par virgules, un sous-ensemble de : Heure, Type, Domaine life/, Poste, Source, Bénéficiaire, Montant prévu, Montant réel, Statut, Compte, Réf. life/, Notes>
<une ligne de données par transaction/événement, valeurs séparées par virgules, dans le même ordre que les colonnes déclarées>

Règles :
- "Type" vaut "transaction" (mouvement d'argent) ou "événement" (fait à logger sans montant).
- "Domaine life/" est un des : 00-META, 10-MISSION, 20-FAMILY, 30-ADMIN, 40-FINANCE, 50-WORK, 52-JM, 53-CANTINE, 60-HEALTH, 70-WRITINGS, 90-INBOX.
  (SPOT: life/40-finance/README.md § "Domaine life/ — valid values for Registre" — edit there first, then mirror here.)
- "Statut" vaut "prévu", "réel" ou "annulé".
- "Compte" (si transaction) est un des : Cash, Orange Money, Banque, Autre, Cantine. Exception délibérée à la règle "n'invente rien" ci-dessous : si le texte source ne précise aucun moyen de paiement, utilise "Cash" par défaut (le compte le plus courant pour une dépense non précisée) plutôt que de laisser le champ vide.
- "Heure" : exception délibérée similaire (2026-09-17) — si le texte source ne précise aucune heure, utilise l'heure actuelle indiquée plus haut par défaut plutôt que de laisser le champ vide.
- Frais Orange Money (2026-09-17, mis à jour 2026-09-17 après un deuxième run raté — voir life/40-finance/46-frais-orange-money.md pour les formules et leur source). NE calcule JAMAIS toi-même un montant de frais — deux runs de suite se sont trompés (104f au lieu de 64f, puis confusion entre les deux formules) alors qu'un script Python fait ce calcul de façon fiable. Émets à la place, exactement à la place du nombre dans "Montant prévu"/"Montant réel" (avec un "-" devant si c'est une sortie d'argent, ex: `-<calculate .../>`), une balise :
  `<calculate what="transaction_fees|withdrawal_fees" source_amount="<montant concerné>" compte="Orange Money" transaction_type="transfer|deposit"/>`
  — un script la remplace ensuite par la vraie valeur avant l'envoi. "source_amount" est TOUJOURS un montant connu du texte source, JAMAIS le résultat d'une autre balise `<calculate>` — pas de balises imbriquées, pas de chaînage.
  - Un DÉPÔT (espèces <-> Orange Money, entre comptes de l'utilisateur lui-même) est TOUJOURS gratuit (le script renvoie 0 pour `transaction_type="deposit"`) — mais n'ajoute même pas de ligne de frais dans ce cas, seulement les deux lignes du virement interne (montants opposés, un "Compte" différent de chaque côté, "Poste" = "Virement interne" — voir la règle plus bas).
  - Un TRANSFERT Orange Money vers un tiers (Bénéficiaire ≠ l'utilisateur), UNIQUEMENT si le texte source précise explicitement que le paiement passe par Orange Money, génère PAR DÉFAUT TROIS lignes (même date/heure, même Bénéficiaire pour les lignes 1 et 3) — voir l'exemple complet plus bas :
    1. La ligne de transaction principale telle que décrite dans le texte : Bénéficiaire = le tiers, "Montant réel" = -<montant principal>, "Compte" = Orange Money.
    2. Frais de transfert — TOUJOURS ajoutée (c'est ce que L'UTILISATEUR paie pour envoyer) : "Poste" = "Frais Orange Money", "Compte" = Orange Money, "Montant réel" = `-<calculate what="transaction_fees" transaction_type="transfer" source_amount="<montant principal>" compte="Orange Money"/>`, "Notes" = "Frais de transfert Orange Money — voir life/40-finance/46-frais-orange-money.md".
    3. Complément pour frais de retrait — ajoutée PAR DÉFAUT, SAUF si le texte source contient une note explicite du type "pas de frais de retrait" / "sans complément retrait" / "retrait gratuit" (dans ce cas, omets cette ligne 3) : c'est ce que LE BÉNÉFICIAIRE paiera pour retirer, donc l'utilisateur lui envoie ce montant en plus pour qu'il/elle reçoive le plein montant net. Même Bénéficiaire que la ligne 1 (2026-09-17 : "Poste" = "Frais Orange Money", comme la ligne 2 — pas le Poste de la ligne 1), "Compte" = Orange Money, "Montant réel" = `-<calculate what="withdrawal_fees" source_amount="<montant principal>" compte="Orange Money"/>`, "Notes" = "Complément pour frais de retrait Orange Money du bénéficiaire — voir life/40-finance/46-frais-orange-money.md".
  - IMPORTANT, source de la confusion du run précédent : ne confonds JAMAIS les deux "what". "transaction_fees" (avec `transaction_type="transfer"`) sert UNIQUEMENT à la ligne 2 (le frais que L'UTILISATEUR paie). "withdrawal_fees" sert UNIQUEMENT à la ligne 3 (le complément pour LE BÉNÉFICIAIRE). Les deux balises utilisent le même `source_amount` = le montant principal de la ligne 1, jamais un autre nombre.
  - Un retrait d'espèces fait directement par l'utilisateur depuis son propre compte Orange Money (pas un envoi à un tiers) utilise `what="withdrawal_fees"` seul, sans lignes 1/2/3 (ce n'est pas un transfert). PIÈGE VÉCU (2026-09-18, oubliée une première fois) : ce cas s'applique AUSSI quand le texte décrit d'abord une entrée d'argent reçue sur Orange Money (qui elle-même ne coûte rien — recevoir est gratuit), PUIS dit que ce même argent a été retiré/dépensé en espèces — ce sont deux lignes distinctes, pas une seule : la ligne d'entrée (positive, sans frais) ET une ligne de frais de retrait séparée (négative, `what="withdrawal_fees"`, `source_amount` = le montant reçu/retiré). Ne saute pas la seconde ligne juste parce que l'argent est arrivé comme un "revenu" plutôt que comme un "transfert vers un tiers" — le retrait qui a suivi a son propre coût, indépendant de la façon dont l'argent est arrivé. Exemple :
    ## 18 sept 2026
    Heure, Type, Domaine life/, Poste, Source, Bénéficiaire, Montant prévu, Montant réel, Statut, Compte, Réf. life/, Notes
    13:05, transaction, 40-FINANCE, Virement reçu, Chérie, , , 3054, réel, Orange Money, , Reçu de Chérie via Orange Money
    13:05, transaction, 40-FINANCE, Frais Orange Money, , , , -<calculate what="withdrawal_fees" source_amount="3054" compte="Orange Money"/>, réel, Orange Money, , Frais de retrait — voir life/40-finance/46-frais-orange-money.md
    (puis les dépenses en espèces qui suivent, sur Compte = Cash, séparément)
  - N'invente JAMAIS de frais pour Cash, Banque, ou tout paiement dont le moyen n'est pas explicitement précisé comme "Orange Money" dans le texte source, et n'utilise `<calculate>` que pour ces deux "what", jamais pour un autre calcul (ex: ne l'utilise jamais pour additionner plusieurs montants).
- "Montant prévu"/"Montant réel" : nombres seuls (pas de texte autour), positif = entrée, négatif = sortie (Bénéficiaire rempli → négatif ; Source rempli → positif). "Source" et "Bénéficiaire" sont mutuellement exclusifs — jamais les deux remplis sur la même ligne. "Compte" est le compte débité/crédité (toujours pertinent si connu) ; "Source" ne sert qu'à nommer *l'origine d'une entrée d'argent* (ex: un virement reçu de quelqu'un) — jamais l'outil de paiement d'une sortie, ce rôle est déjà tenu par "Compte".
- "Virement interne" (2026-10-02) : tout mouvement d'argent entre deux comptes de l'utilisateur lui-même (dépôt d'espèces sur Orange Money, retrait Orange Money en espèces, Cash <-> Banque…) s'écrit en DEUX lignes de montants opposés, même date/heure, un "Compte" différent de chaque côté, avec "Poste" = "Virement interne" sur les deux (jamais "Retrait", "Retrait espèces", "Dépôt"…) et sans Source ni Bénéficiaire. Pour un retrait Orange Money, ces deux lignes s'ajoutent à la ligne de frais de retrait (qui garde "Poste" = "Frais Orange Money"). Le tableau de bord du Registre exclut ce Poste des entrées/sorties : ne l'utilise JAMAIS pour de l'argent qui sort vers un tiers ou qui arrive d'un tiers. Exemple (retrait de 32000f) :
    19:00, transaction, 40-FINANCE, Virement interne, , , , -32000, réel, Orange Money, , Retrait en espèces
    19:00, transaction, 40-FINANCE, Virement interne, , , , 32000, réel, Cash, , Retrait en espèces
    19:00, transaction, 40-FINANCE, Frais Orange Money, , , , -<calculate what="withdrawal_fees" source_amount="32000" compte="Orange Money"/>, réel, Orange Money, , Frais de retrait — voir life/40-finance/46-frais-orange-money.md
- Ne déclare JAMAIS "Solde après" — c'est une formule calculée automatiquement, toute valeur serait ignorée par le trigger.
- N'invente JAMAIS un montant, un poste ou une date qui n'est pas clairement dans le texte source. En cas de doute, laisse le champ vide plutôt que de deviner (sauf "Compte" — voir règle ci-dessus).

Exemple :
## 13 sept 2026
Heure, Type, Domaine life/, Poste, Source, Bénéficiaire, Montant prévu, Montant réel, Statut, Compte, Réf. life/, Notes
08:30, transaction, 40-FINANCE, Nourriture, , Marché Mvog-Ada, , -5000, réel, Cash, , Légumes + poisson

Exemple avec un transfert Orange Money vers un tiers (montant principal 30000, texte source :
"30000f envoyés à Paul via Orange Money") — les TROIS lignes par défaut, même date/heure :
## 13 sept 2026
Heure, Type, Domaine life/, Poste, Source, Bénéficiaire, Montant prévu, Montant réel, Statut, Compte, Réf. life/, Notes
14:00, transaction, 40-FINANCE, Aide, , Paul, , -30000, réel, Orange Money, ,
14:00, transaction, 40-FINANCE, Frais Orange Money, , , , -<calculate what="transaction_fees" transaction_type="transfer" source_amount="30000" compte="Orange Money"/>, réel, Orange Money, , Frais de transfert Orange Money — voir life/40-finance/46-frais-orange-money.md
14:00, transaction, 40-FINANCE, Frais Orange Money, , Paul, , -<calculate what="withdrawal_fees" source_amount="30000" compte="Orange Money"/>, réel, Orange Money, , Complément pour frais de retrait Orange Money du bénéficiaire — voir life/40-finance/46-frais-orange-money.md''',
    },
}

# 2026-09-17 : le LLM s'est trompé en calculant lui-même un frais Orange Money (104f au lieu de
# 64f) — plutôt que de lui faire refaire l'arithmétique, il émet une balise <calculate .../> dans
# le texte reformaté (voir dsl_doc ci-dessus) que ce script résout ensuite ici, déterministe.
# Formules : life/40-finance/46-frais-orange-money.md (vérifiées contre un reçu réel).
CALCULATE_TAG_RE = re.compile(r'<calculate\s+([^/>]*)/>')
CALCULATE_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _compute_transaction_fee(amount, compte, transaction_type):
    """Transfert vers un compte Orange Money : 0,2 % (taxe TTA) + 4f, tous montants 50-500 000f.
    Recalé le 2026-09-19 sur deux reçus réels (192 000f -> 388f, 2026-08-27) et le retrait ci-dessous,
    et sur la page officielle orangemoney.orange.cm ("0% + 0,2% + 4frs") ; remplace le barème
    0,5 % / 1 000f fourni le 2026-09-17, contredit par ces reçus."""
    if compte != 'Orange Money':
        raise SystemExit(f'<calculate> : aucune formule de frais connue pour le compte "{compte}".')
    if transaction_type == 'deposit':
        return 0
    if transaction_type == 'transfer':
        if not 50 <= amount <= 500000:
            raise SystemExit(f'<calculate> : montant {amount} hors des paliers connus pour transaction_fees (transfer).')
        return round(amount * 0.002) + 4
    raise SystemExit(
        f'<calculate> : transaction_type "{transaction_type}" inconnu pour transaction_fees '
        '(attendu : transfer|deposit).'
    )


def _compute_withdrawal_fee(amount, compte):
    """Retrait de son compte Orange Money. Palier 5 000-399 999f : 1 % + 0,2 % (TTA) + 4f = 1,2 % + 4f,
    vérifié par un reçu SMS réel (retrait de 32 000f -> 388f, 2026-09-19). Les deux paliers forfaitaires
    (< 5 000f : 50f ; >= 400 000f : 3 500f) sont NON VÉRIFIÉS — anciennes valeurs conservées faute de
    reçu ; à recaler si un retrait réel les contredit."""
    if compte != 'Orange Money':
        raise SystemExit(f'<calculate> : aucune formule de frais de retrait connue pour le compte "{compte}".')
    if 50 <= amount <= 4999:
        return 50
    if 5000 <= amount <= 399999:
        return round(amount * 0.012) + 4
    if 400000 <= amount <= 505000:
        return 3500
    raise SystemExit(f'<calculate> : montant {amount} hors des paliers connus pour withdrawal_fees.')


def resolve_calculate_tags(dsl_text):
    """Replaces every <calculate what="..." .../> placeholder the LLM left in the reformatted
    text with the actual computed number, using the deterministic formulas above instead of
    trusting the LLM's own arithmetic."""

    def _replace(match):
        attrs = dict(CALCULATE_ATTR_RE.findall(match.group(1)))
        what = attrs.get('what')
        compte = attrs.get('compte', '')
        try:
            amount = float(attrs['source_amount'])
        except (KeyError, ValueError):
            raise SystemExit(f'<calculate> : "source_amount" manquant ou invalide dans {match.group(0)!r}.')
        if what == 'transaction_fees':
            fee = _compute_transaction_fee(amount, compte, attrs.get('transaction_type', ''))
        elif what == 'withdrawal_fees':
            fee = _compute_withdrawal_fee(amount, compte)
        else:
            raise SystemExit(f'<calculate> : "what={what}" inconnu (attendu : transaction_fees|withdrawal_fees).')
        return str(fee)

    return CALCULATE_TAG_RE.sub(_replace, dsl_text)


def _route_provider(state_path):
    result = subprocess.run(
        [sys.executable, PROVIDER_ROUTER_SCRIPT, '--task-type', 'other',
         '--state', state_path, '--config', PROVIDER_ROUTER_CONFIG],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f'provider-router : {result.stderr.strip()}')
    return json.loads(result.stdout.strip())


def _mark_provider_failed(provider, state_path, reason):
    subprocess.run(
        [sys.executable, PROVIDER_ROUTER_SCRIPT, '--mark-failed', provider,
         '--state', state_path, '--reason', reason],
        capture_output=True, text=True,
    )


def _call_llm(base_url, model, api_key, system_prompt, user_text):
    body = json.dumps({
        'model': model,
        'temperature': 0.2,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_text},
        ],
    }).encode('utf-8')
    req = urllib.request.Request(
        base_url.rstrip('/') + '/chat/completions',
        data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return data['choices'][0]['message']['content'].strip()


def reformat_via_llm(free_text, dsl_doc):
    """Tries each available provider in the 'other' chain in order, per provider-router, until
    one succeeds. Uses a fresh per-invocation state file so a failure here never persists across
    unrelated future runs (matches provider-router's own 'fresh run = clean slate' semantics)."""
    now = datetime.datetime.now()
    today = now.strftime('%Y-%m-%d (%A)')
    heure_actuelle = now.strftime('%H:%M')
    system_prompt = (
        'Tu convertis du texte libre en un mini-format structuré, pour import automatique dans '
        'un tableur. Réponds UNIQUEMENT avec le texte au format demandé — aucune explication, '
        'aucun bloc de code markdown, aucun texte avant ou après.\n\n'
        f'Date du jour (pour résoudre "aujourd\'hui"/"hier"/etc.) : {today}\n'
        f'Heure actuelle (pour défaut de "Heure" si applicable) : {heure_actuelle}\n\n'
        f'{dsl_doc}'
    )

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        state_path = f.name
    try:
        json.dump({'failed': {}}, open(state_path, 'w'))
        last_error = None
        for _ in range(4):  # at most 4 providers in any chain
            try:
                cfg = _route_provider(state_path)
            except SystemExit as e:
                raise SystemExit(
                    f'{e}\n(échec précédent : {last_error})' if last_error else str(e)
                )
            api_key = os.environ.get(cfg['api_key_env'])
            try:
                return reformat_result(cfg, api_key, system_prompt, free_text)
            except (urllib.error.HTTPError, urllib.error.URLError) as e:
                last_error = f'{cfg["provider"]}: {e}'
                _mark_provider_failed(cfg['provider'], state_path, str(e))
        raise SystemExit(f'Tous les fournisseurs ont échoué. Dernière erreur : {last_error}')
    finally:
        os.unlink(state_path)


def reformat_result(cfg, api_key, system_prompt, free_text):
    return _call_llm(cfg['base_url'], cfg['model'], api_key, system_prompt, free_text)


def sheets_request(method, url, access_token, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {access_token}'},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f'Sheets API {method} {url} : {e.code} {e.read().decode("utf-8")}')


def append_row(sheet_name, dsl_text, access_token):
    horodatage = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    url = (
        f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/'
        f'{urllib.parse.quote(sheet_name, safe="")}!A:D:append'
        '?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS'
    )
    body = {'values': [[horodatage, dsl_text, 'En attente', '']]}
    result = sheets_request('POST', url, access_token, body)
    updated_range = result['updates']['updatedRange']  # e.g. "Import!A15:D15"
    row_num = int(''.join(c for c in updated_range.split('!')[1].split(':')[0] if c.isdigit()))
    return row_num


def poll_result(sheet_name, row_num, access_token, timeout_s=20):
    """The existing installable 'On change' trigger processes new rows automatically — poll
    briefly for it to finish so the user gets immediate feedback, same as watching the AppSheet
    form's Résultat field fill in."""
    url = (
        f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/'
        f'{urllib.parse.quote(sheet_name, safe="")}!C{row_num}:D{row_num}'
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        result = sheets_request('GET', url, access_token)
        values = result.get('values', [[]])
        row = values[0] if values else []
        statut = row[0] if len(row) > 0 else ''
        resultat = row[1] if len(row) > 1 else ''
        if statut == 'Traité':
            return statut, resultat
        time.sleep(2)
    return 'En attente', '(le trigger n\'a pas encore traité la ligne — vérifie "Résultat" dans quelques instants)'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--target', choices=list(TARGETS), required=True)
    p.add_argument('--text', help='Free text to reformat and import. Reads stdin if omitted.')
    args = p.parse_args()

    free_text = args.text if args.text is not None else sys.stdin.read()
    if not free_text.strip():
        raise SystemExit('Texte vide — rien à importer.')

    target = TARGETS[args.target]
    access_token = get_access_token()

    dsl_text = reformat_via_llm(free_text, target['dsl_doc'])
    if '<calculate' in dsl_text:
        print('--- Texte brut (avant résolution des <calculate>) ---')
        print(dsl_text)
        dsl_text = resolve_calculate_tags(dsl_text)
        print('-----------------------')
    print('--- Texte reformaté ---')
    print(dsl_text)
    print('-----------------------')

    row_num = append_row(target['sheet'], dsl_text, access_token)
    print(f'Ligne {row_num} ajoutée à "{target["sheet"]}". En attente du trigger...')

    statut, resultat = poll_result(target['sheet'], row_num, access_token)
    print(f'Statut : {statut}')
    print(resultat)


if __name__ == '__main__':
    main()
