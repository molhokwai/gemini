"""
Base class for profiles whose sheet is fed through an Apps Script trigger (Registre, Dépôt / vente).

Pipeline: free text -> LLM reformats it into the sheet's mini-DSL (text, not JSON; prompt = TARGETS[...]['dsl_doc'] in
_freetext-import-lib/append_import.py, the single source of truth, incl. the <calculate .../> Orange Money fee tags that
resolve_calculate_tags() replaces deterministically) -> ONE row [timestamp, DSL, "En attente", ""] is appended to the
sheet's *Import* tab -> the installable onChange trigger validates/matches and writes the real table -> we poll the
Import row's Statut/Résultat for up to 20 s. This code NEVER writes to the final table: every safety net of the trigger
(header matching, non-blocking validation, already-processed detection) applies exactly as for a human pasting the text
into the AppSheet Import form.

Extra flags: --dsl "<already formatted DSL>" (skip the LLM), --no-wait (don't poll). --dry-run prints the DSL only.
"""
import datetime
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'scripts'))
sys.path.insert(0, os.path.expanduser('~/.qwen/skills/_freetext-import-lib'))
from intake_engine import Profile  # noqa: E402
import append_import as ai  # noqa: E402


class ImportTriggerProfile(Profile):
    import_tab = ''            # the Import tab the trigger watches
    target_key = ''            # key in append_import.TARGETS (dsl_doc)
    dsl_doc = None             # generated profiles carry their own DSL prompt; otherwise append_import.TARGETS[target_key]['dsl_doc']
    initial_status = 'En attente'
    initial_result = ''
    poll_timeout = 20

    @property
    def tab(self):
        return self.import_tab

    def add_args(self, ap):
        ap.add_argument('--dsl', help='already-formatted DSL text: skip the LLM')
        ap.add_argument('--no-wait', action='store_true', help="don't poll for the trigger's result")

    def acquire(self, ctx):
        a = ctx.args
        if a.dsl is not None:
            dsl, source = a.dsl, 'dsl'
        else:
            text = self.read_text(ctx)
            if not text.strip():
                raise SystemExit('Texte vide — rien à importer.')
            dsl, source = ai.reformat_via_llm(text, self.dsl_doc or ai.TARGETS[self.target_key]['dsl_doc']), 'llm'
        raw = None
        if '<calculate' in dsl:
            raw, dsl = dsl, ai.resolve_calculate_tags(dsl)
        return {'rows': [{'dsl': dsl}], 'warnings': [], 'meta': {'raw': raw}, 'source': source, 'ok': True}

    def show(self, parsed, ctx):
        raw = parsed['meta'].get('raw')
        if raw:
            print('--- Texte brut (avant résolution des <calculate>) ---')
            print(raw)
            print('-----------------------')
        print('--- Texte reformaté ---')
        print(parsed['rows'][0]['dsl'])
        print('-----------------------')

    def append_import_row(self, ctx, dsl):
        stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        res = ctx.sheets.append_values(f"'{self.import_tab}'!A:D", [[stamp, dsl, self.initial_status, self.initial_result]])
        updated = res['updates']['updatedRange']                     # e.g. "'Import'!A15:D15"
        return int(''.join(c for c in updated.split('!')[1].split(':')[0] if c.isdigit()))

    def poll(self, ctx, row_num):
        deadline = time.time() + self.poll_timeout
        while time.time() < deadline:
            v = ctx.sheets.get_values(f"'{self.import_tab}'!C{row_num}:D{row_num}")
            row = v[0] if v else []
            statut = row[0] if len(row) > 0 else ''
            resultat = row[1] if len(row) > 1 else ''
            if statut == 'Traité':
                return statut, resultat
            time.sleep(2)
        return 'En attente', '(le trigger n\'a pas encore traité la ligne — vérifie "Résultat" dans quelques instants)'

    def write(self, parsed, ctx):
        row = self.append_import_row(ctx, parsed['rows'][0]['dsl'])
        print(f'Ligne {row} ajoutée à "{self.import_tab}". En attente du trigger...')
        if ctx.args.no_wait:
            return
        statut, resultat = self.poll(ctx, row)
        print(f'Statut : {statut}')
        print(resultat)

    def init(self, ctx):
        print(f'"{self.import_tab}" is created by the Apps Script setup of this sheet — nothing to initialise here.')

    def check(self, ctx):
        """Status of the most recent Import row (0 = processed)."""
        v = ctx.sheets.get_values(f"'{self.import_tab}'!A:D")
        if len(v) < 2:
            print('No import rows yet.')
            return 1
        last = v[-1] + [''] * (4 - len(v[-1]))
        print(f'Last row {len(v)}: {last[0]} — {last[2]} — {last[3]}')
        return 0 if last[2] == 'Traité' else 1
