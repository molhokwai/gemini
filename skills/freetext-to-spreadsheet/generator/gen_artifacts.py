"""Text artifacts generated from a sheet spec: profile module, DSL prompt, dedicated SKILL.md, runbook, life-log entries. Pure string builders (no I/O)."""
import datetime
import pprint
import re

from gen_appsscript import sample_dsl, _sample

L = {   # language strings
    'fr': {
        'use': "Utilise cette skill chaque fois que l'utilisateur veut enregistrer / noter / logger des données dans cette feuille — expressions comme",
        'when': 'Quand elle est invoquée', 'commands': 'Commandes', 'judgment': 'Points de jugement', 'infra': 'Infrastructure liée',
        'never': "N'invente JAMAIS une valeur absente du texte source : laisse le champ vide. Une valeur requise manquante → demande-la.",
        'preview': "Pour un texte libre, lance d'abord `--dry-run`, montre l'aperçu et les avertissements (`!`) à l'utilisateur, puis relance sans `--dry-run`.",
        'setup': "Si le script se plaint d'un jeton OAuth ou d'une clé LLM manquants, arrête-toi et renvoie vers `~/.qwen/skills/_freetext-import-lib/README.md`.",
        'report': "Rapporte : les lignes écrites, les champs laissés vides, tous les avertissements.",
        'dsl': "Le texte est reformaté en mini-DSL puis soumis via l'onglet Import : un trigger Apps Script valide et écrit la vraie table (avertissements non bloquants).",
        'form': "Un Google Form (voir le runbook) alimente aussi la feuille via un trigger `onFormSubmit`.",
        'direct': "La skill écrit directement dans la feuille.", 'notfor': 'Pas pour',
    },
    'en': {
        'use': 'Use this skill whenever the user wants to log / save / record data in this sheet — phrases like',
        'when': 'When invoked', 'commands': 'Commands', 'judgment': 'Judgment calls', 'infra': 'Related infrastructure',
        'never': 'NEVER invent a value that is not in the source text: leave the field empty. A missing required value → ask for it.',
        'preview': 'For free text, run `--dry-run` first, show the user the preview and every `!` warning, then run again without `--dry-run`.',
        'setup': 'If the script complains about a missing OAuth token or LLM key, stop and point to `~/.qwen/skills/_freetext-import-lib/README.md`.',
        'report': 'Report: the rows written, the fields left empty, every warning.',
        'dsl': "The text is reformatted into a mini-DSL and submitted through the Import tab: an Apps Script trigger validates it and writes the real table (non-blocking warnings).",
        'form': 'A Google Form (see the runbook) also feeds the sheet through an `onFormSubmit` trigger.',
        'direct': 'The skill writes straight into the sheet.', 'notfor': 'Not for',
    },
}

APPSHEET_TYPE = {'text': 'Text', 'longtext': 'LongText', 'integer': 'Number', 'number': 'Number', 'percent': 'Percent', 'date': 'Date', 'time': 'Time',
                 'datetime': 'DateTime', 'choice': 'Enum (or Ref to the reference tab)', 'boolean': 'Yes/No', 'link': 'Url', 'formula': '(computed in the sheet — Show: off)'}


def _profile_spec(spec):
    """The subset of the spec the runtime needs (no skill/life/appsheet text)."""
    keep = ('spec_version', 'sheet', 'columns', 'reference', 'intake', 'safety')
    return {k: spec[k] for k in keep if k in spec}


def profile_py(spec, spec_name, spec_hash):
    sid = spec['sheet']['id'].replace('-', '_')
    pattern = spec['intake']['pattern']
    head = f'# GENERATED from {spec_name} — spec hash {spec_hash} — edit the spec and regenerate; hooks go in {sid}_hooks.py (parse_structured / normalize_row)\n'
    if pattern == 'import-trigger' and spec['sheet']['layout'] == 'table':
        imp = spec['intake']['import']
        return head + f'''import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from _import_trigger import ImportTriggerProfile  # noqa: E402


def _dsl():
    with open(os.path.join(_HERE, {spec['sheet']['id'] + '.dsl.txt'!r}), encoding='utf-8') as f:
        return f.read().split('\\n# GENERATED-BODY-HASH')[0]


class P(ImportTriggerProfile):
    name = {spec['sheet']['id']!r}
    description = {spec['sheet']['description']!r}
    import_tab = {imp['tab']!r}
    dsl_doc = _dsl()


PROFILE = P()
'''
    return head + f'''import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, '..', 'scripts'))
from table_profile import TableProfile  # noqa: E402

SPEC = {pprint.pformat(_profile_spec(spec), width=150, sort_dicts=False)}
SPEC['_hooks_path'] = os.path.join(_HERE, {sid + '_hooks.py'!r})


class P(TableProfile):
    pass


PROFILE = P(SPEC)
'''


def dsl_doc(spec, spec_name, spec_hash):
    lang = spec['sheet']['language']
    keymap = {c['key']: c for c in spec['columns']}
    imp = spec['intake']['import']
    heads = [keymap[k]['header'] for k in imp['dsl_columns']] + [x['name'] for x in imp.get('dsl_extra_columns', [])]
    fr = lang == 'fr'
    out = [(f'Format cible ("{imp["tab"]}", pour "{spec["sheet"]["title"]}" — {spec["sheet"]["description"]}) :' if fr else
            f'Target format ("{imp["tab"]}", for "{spec["sheet"]["title"]}" — {spec["sheet"]["description"]}):'), '',
           '## <date, ex: "13 sept 2026">' if fr else '## <date, e.g. "13 Sept 2026">',
           ('<noms de colonnes séparés par virgules, un sous-ensemble de : ' if fr else '<column names separated by commas, a subset of: ') + ', '.join(heads) + '>',
           ('<une ligne de données par enregistrement, valeurs séparées par virgules, dans le même ordre que les colonnes déclarées>' if fr else
            '<one data line per record, comma-separated values in the same order as the declared columns>'), '',
           'Règles :' if fr else 'Rules:']
    for k in imp['dsl_columns']:
        c = keymap[k]
        if c['type'] == 'choice' and c.get('choices'):
            out.append(f'- "{c["header"]}" ' + ('est un des : ' if fr else 'is one of: ') + ', '.join(c['choices']) + '.')
        if c.get('llm'):
            out.append(f'- "{c["header"]}" : {c["llm"]}')
    for x in imp.get('dsl_extra_columns', []):
        out.append(f'- "{x["name"]}" ' + ('peut être déclaré (utilisé pour rapprocher, non stocké) : ' if fr else 'may be declared (used for matching, not stored): ') + x.get('note', ''))
    for k, c in keymap.items():
        if k not in imp['dsl_columns'] and c['type'] != 'formula':
            if c['type'] == 'date' and imp.get('date_blocks', True):
                out.append(f'- "{c["header"]}" : ' + ("vient de l'en-tête « ## <date> » du bloc — ne la déclare pas comme colonne." if fr else 'comes from the block\'s "## <date>" header — do not declare it as a column.'))
            else:
                out.append(f'- ' + ('Ne déclare JAMAIS' if fr else 'NEVER declare') + f' "{c["header"]}" ' + ('— rempli automatiquement.' if fr else '— filled automatically.'))
    for r in imp.get('default_rules', []):
        out.append(f'- {r.get("column", "")} : {r.get("rule", "")}')
    if imp.get('date_blocks', True):
        out.append('- Plusieurs blocs "## <date>" possibles si le texte couvre plusieurs jours.' if fr else '- Several "## <date>" blocks are allowed if the text covers several days.')
    out.append("- N'invente JAMAIS une valeur absente du texte source ; en cas de doute laisse-la de côté plutôt que de deviner." if fr else
               '- NEVER invent a value that is not in the source text; when unsure leave it out rather than guess.')
    out += ['', 'Exemple :' if fr else 'Example:', sample_dsl(spec)]
    return '\n'.join(out)


def skill_md(spec, spec_name, spec_hash):
    sh, sk = spec['sheet'], spec.get('skill', {})
    lang, t = sh['language'], L[sh['language']]
    name = sk.get('name') or sh['id']
    trig = ', '.join(f'"{x}"' for x in sk.get('triggers', []))
    not_for = f' {t["notfor"]}: {sk["not_for"]}.' if sk.get('not_for') else ''
    desc = f'{sh["description"]} (tab "{sh["title"]}"). {t["use"]} {trig}.{not_for}'.replace('\n', ' ')
    pat = spec['intake']['pattern']
    E = 'python3 ~/.qwen/skills/freetext-to-spreadsheet/scripts/intake.py --profile ' + sh['id']
    cmds = [f'```bash', f'{E} --dry-run --text "<free text>"      # preview, writes nothing', f'{E} --text "<free text>"']
    if pat == 'import-trigger':
        cmds += [f'{E} --dsl "<approved DSL>"                  # submit exactly the reviewed DSL, skipping the LLM', f'{E} --check                              # status of the latest Import row']
    else:
        cmds += [f'{E} --json \'{{"rows": [ ... ]}}\'', f'{E} --csv file.csv', f'{E} --check [--date YYYY-MM-DD]']
    cmds.append('```')
    how = {'direct': t['direct'], 'form-trigger': t['direct'] + ' ' + t['form'], 'import-trigger': t['dsl']}[pat]
    cols = '\n'.join(f'- `{c["key"]}` — {c["header"]} ({c["type"]}{", required" if c.get("required") else ""}){" — " + c["llm"] if c.get("llm") else ""}' for c in spec['columns'])
    judg = '\n'.join(f'- {j}' for j in sk.get('judgment', [])) or '-'
    infra = [f'- Profile: `~/.qwen/skills/freetext-to-spreadsheet/profiles/{sh["id"].replace("-", "_")}.py` (generated from `{spec_name}`)']
    if pat != 'direct' and sh['layout'] == 'table':
        infra.append(f'- Apps Script source + deployment runbook: `life/{spec["life"]["domain"]}/apps-script/` and `life/{spec["life"]["domain"]}/{sh["id"]}-runbook.md`')
    body = f'''---
name: {name}
description: {desc}
---

# {sh["title"]}

{sh["description"]}. {how}

## {t["when"]}
1. {t["preview"]}
2. {t["report"]}
3. {t["never"]}

## {t["commands"]}
{chr(10).join(cmds)}

Columns:
{cols}

## {t["judgment"]}
{judg}
- {t["setup"]}

## {t["infra"]}
{chr(10).join(infra)}
'''
    return body


def runbook_md(spec, spec_name, spec_hash, gid):
    sh, pat = spec['sheet'], spec['intake']['pattern']
    ap = spec.get('appsheet', {}) or {}
    out = [f'# Runbook — {sh["title"]} (spec `{sh["id"]}`)', '', f'*Generated from `{spec_name}` — spec hash {spec_hash}. Steps marked **[HUMAN]** cannot be automated: they need your click in the browser.*', '']
    if pat in ('form-trigger', 'import-trigger'):
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/script.scriptapp']
        if pat == 'form-trigger':
            scopes.insert(0, 'https://www.googleapis.com/auth/forms')
        js = f'{sh["id"]}-{"form" if pat == "form-trigger" else "import"}.gs'
        out += ['## 1. Apps Script deployment', '',
                f'Source: `life/{spec["life"]["domain"]}/apps-script/{js}` (sheet addressed by gid `{gid}`; renaming the tab is safe).', '',
                '1. Open https://script.google.com/home/projects/create → a new **standalone** project; name it after the sheet.',
                '2. Project Settings → tick **Show "appsscript.json" manifest file in editor**. Set `oauthScopes` to exactly:',
                '   ```', '   ' + '\n   '.join(f'"{s}",' for s in scopes).rstrip(','), '   ```',
                '3. Replace `Code.gs` with the generated file (check the spec hash in its header). Click into the editor, `ctrl+s` (the Save button alone can leave "Unsaved changes").',
                '4. The Run dropdown lists only `main` (the trigger handler is set on `globalThis`). Set `var MODE = \'setup\';`, save, Run. **[HUMAN]** first run asks for authorization: *Review permissions → choose the account → Advanced → Go to <project> → Allow*.',
                '5. Set `MODE = \'test\'`, save, Run: ' + ('parses a sample DSL and logs the result, nothing is written.' if pat == 'import-trigger' else 'submits a fake response (values start with TEST); check the row, then clear the row and run `MODE = \'cleanup\'`.'),
                '6. Put `MODE = \'status\'` back and save (harmless default).', '',
                'Gotchas (see the `google-workspace` skill): the account-switcher popup can cover the toolbar and swallow clicks; the function dropdown may ignore programmatic selection — that is why only `main` is listed.', '']
    if ap.get('mode') == 'runbook':
        out += [f'## 2. AppSheet (extend the existing app "{ap.get("app", "")}" — never create a second one)', '',
                '**[HUMAN]** AppSheet apps cannot be created or edited through an API; the file picker in *Add data* only responds to a real click.', '',
                '1. Editor → Data → Tables → **Add new table** → pick the workbook, tick the tab' + (f' "{sh["title"]}"' if pat != 'import-trigger' else f's "{spec["intake"]["import"]["tab"]}" and "{sh["title"]}"') + '.',
                '2. Open each table, click the refresh icon by *View data source* → **Regenerate structure** (safe: only the app\'s own column definitions).',
                '3. Set column types:', '', '| column | AppSheet type |', '|---|---|']
        out += [f'| {c["header"]} | {APPSHEET_TYPE[c["type"]]} |' for c in spec['columns']]
        if pat == 'import-trigger':
            out.append(f'| {spec["intake"]["import"]["tab"]}.Texte | **LongText** (a Text field silently drops pasted line breaks) |')
            out.append(f'| {spec["intake"]["import"]["tab"]}.Horodatage | DateTime |')
        out += ['', '4. Views wanted: ' + (', '.join(ap.get('views', [])) or 'form') + '. For an import form: one LongText input + auto Horodatage/Statut ("En attente").',
                '5. Run *Manage → Deploy → Run deployment check*; treat it as authoritative over the live link (a stale cache can show the "plan update needed" banner even when checks pass). If stuck: toggle prototype ↔ deployed.',
                '6. Snapshot before/after with *Manage → Versions* (it only covers the app definition, never the data).', '']
    if len(out) <= 3:
        out += ['Nothing to deploy for this pattern: the skill writes directly into the sheet.', '']
    return '\n'.join(out)


def life_event(spec, spec_name, spec_hash, artifacts, now=None):
    now = now or datetime.datetime.now()
    dom = spec['life']['domain']
    top = dom.split('/')[0]
    m = re.match(r'(\d\d)-(.+)', top)
    code = f'{m[1]} {m[2].upper()}' if m else top
    lines = [f'## {now:%Y-%m-%d %H:%M} · {code} · Sheet generated — {spec["sheet"]["title"]} ({spec["sheet"]["id"]})', '',
             '- status: done', '- tags: generator, sheet-spec, tooling', '',
             f'Generated from `{spec_name}` (spec hash {spec_hash}; pattern {spec["intake"]["pattern"]}, mode {spec["sheet"]["mode"]}). Artifacts:']
    lines += [f'- {a}' for a in artifacts]
    lines += ['', 'Apps Script deployment and AppSheet steps, if any, are human/browser steps described in the runbook.', '']
    return '\n'.join(lines), code


def open_loop_row(spec, code, today):
    ol = spec['life'].get('open_loop', 'none')
    if ol == 'none':
        return None
    freq = {'daily': 'quotidien', 'weekly': 'hebdomadaire'}.get(ol, ol)
    return (f'| {today:%Y-%m-%d} | {code} | Saisir les données de « {spec["sheet"]["title"]} » via `/{spec["skill"].get("name") or spec["sheet"]["id"]}` | {freq} | '
            f'`life/{spec["life"]["domain"]}` |')
