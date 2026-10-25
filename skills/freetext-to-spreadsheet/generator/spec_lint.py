#!/usr/bin/env python3
"""
Validates a sheet spec (see SPEC.md) and optionally compares an `adopt` spec with the live tab.

  spec_lint.py SPEC [SPEC...] [--live]

Exit code 1 if any error. Warnings never fail. --live needs the Google token (same one every skill here uses) and only
READS the header row of the tab.
"""
import argparse
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
KEBAB = re.compile(r'^[a-z][a-z0-9]*(-[a-z0-9]+)*$')
SNAKE = re.compile(r'^[a-z][a-z0-9_]*$')
TYPES = {'text', 'longtext', 'integer', 'number', 'percent', 'date', 'time', 'datetime', 'choice', 'boolean', 'link', 'formula'}
NUMERIC = {'integer', 'number', 'percent'}
PATTERNS = {'direct', 'form-trigger', 'import-trigger'}
COL_KEYS = {'key', 'header', 'type', 'required', 'default', 'choices', 'choices_from', 'min', 'max', 'formula', 'width', 'wrap',
            'note', 'llm', 'aliases'}


def lint(spec, path=''):
    E, W = [], []
    err = lambda m: E.append(m)
    warn = lambda m: W.append(m)

    if spec.get('spec_version') != 1:
        err('spec_version must be 1')
    sheet = spec.get('sheet') or {}
    for k in ('id', 'title', 'description', 'language', 'workbook', 'mode', 'layout'):
        if not sheet.get(k):
            err(f'[sheet].{k} is required')
    if sheet.get('id') and not KEBAB.match(sheet['id']):
        err(f'[sheet].id "{sheet["id"]}" must be kebab-case')
    if sheet.get('language') not in (None, 'fr', 'en'):
        err('[sheet].language must be "fr" or "en"')
    if sheet.get('mode') not in (None, 'create', 'adopt'):
        err('[sheet].mode must be "create" or "adopt"')
    layout = sheet.get('layout')
    if layout not in (None, 'table', 'custom'):
        err('[sheet].layout must be "table" or "custom"')
    wb = sheet.get('workbook')
    if wb:
        try:
            wbs = tomllib.load(open(os.path.join(HERE, 'workbooks.toml'), 'rb')).get('workbooks', {})
            if wb not in wbs:
                err(f'[sheet].workbook "{wb}" not found in workbooks.toml (known: {", ".join(wbs)})')
        except FileNotFoundError:
            err('workbooks.toml missing next to spec_lint.py')

    # ---- columns
    cols = spec.get('columns') or []
    keys = []
    if layout == 'table' and not cols:
        err('layout "table" needs at least one column')
    if layout == 'custom':
        cu = spec.get('custom') or {}
        if not cu.get('writer'):
            err('layout "custom" needs [custom].writer (the hand-written profile)')
        if not cu.get('why'):
            warn('[custom].why is empty — say why the sheet is not a flat table')
        if cols:
            warn('layout "custom": [[columns]] are informational only')
    headers = set()
    for i, c in enumerate(cols, 1):
        where = f'column #{i} ({c.get("key", "?")})'
        for bad in set(c) - COL_KEYS:
            err(f'{where}: unknown key "{bad}"')
        k, h, t = c.get('key'), c.get('header'), c.get('type')
        if not k or not SNAKE.match(k):
            err(f'{where}: key must be snake_case')
        elif k in keys:
            err(f'{where}: duplicate key')
        keys.append(k)
        if not h:
            err(f'{where}: header is required')
        elif h in headers:
            err(f'{where}: duplicate header "{h}"')
        headers.add(h)
        if t not in TYPES:
            err(f'{where}: type must be one of {sorted(TYPES)}')
            continue
        if t == 'choice':
            if bool(c.get('choices')) == bool(c.get('choices_from')):
                err(f'{where}: type choice needs exactly one of choices / choices_from')
        elif c.get('choices') or c.get('choices_from'):
            err(f'{where}: choices only allowed for type choice')
        if t == 'formula' and not c.get('formula'):
            err(f'{where}: type formula needs formula')
        if t != 'formula' and c.get('formula'):
            err(f'{where}: formula only allowed for type formula')
        if t not in NUMERIC and ('min' in c or 'max' in c):
            err(f'{where}: min/max only for integer/number/percent')
        if 'min' in c and 'max' in c and c['min'] > c['max']:
            err(f'{where}: min > max')
        d = c.get('default')
        if d in ('today', 'now'):
            if (d == 'today' and t != 'date') or (d == 'now' and t not in ('time', 'datetime')):
                err(f'{where}: default "{d}" not valid for type {t}')
        if t == 'formula' and c.get('required'):
            err(f'{where}: a formula column cannot be required')
        if not c.get('llm') and t in ('longtext',) and layout == 'table':
            pass  # llm hints are optional
    up = sheet.get('upsert_on') or []
    for u in up:
        if u not in keys:
            err(f'[sheet].upsert_on "{u}" is not a column key')

    # ---- references
    for r in spec.get('reference', []):
        for k in ('tab', 'key_column', 'used_by'):
            if not r.get(k):
                err(f'[[reference]] needs {k}')
        for u in r.get('used_by', []):
            if u not in keys:
                err(f'[[reference]] used_by "{u}" is not a column key')
    for c in cols:
        cf = c.get('choices_from')
        if cf and '!' not in cf:
            err(f'column {c.get("key")}: choices_from must look like "Tab!A2:A"')

    # ---- intake / channels
    intake = spec.get('intake') or {}
    pat = intake.get('pattern')
    if pat not in PATTERNS:
        err(f'[intake].pattern must be one of {sorted(PATTERNS)}')
    channels = spec.get('channels') or {}
    if not channels.get('skill', False):
        err('[channels].skill must be true')
    if channels.get('form') and pat != 'form-trigger':
        err('[channels].form = true needs pattern "form-trigger"')
    if pat == 'form-trigger' and not channels.get('form'):
        warn('pattern form-trigger without [channels].form = true')
    if pat == 'form-trigger' and not (intake.get('form') or {}).get('title'):
        err('[intake.form].title is required for form-trigger')
    if pat == 'import-trigger':
        imp = intake.get('import') or {}
        if not imp.get('tab'):
            err('[intake.import].tab is required for import-trigger')
        dc = imp.get('dsl_columns')
        if not dc:
            err('[intake.import].dsl_columns is required for import-trigger')
        for k in dc or []:
            if k not in keys:
                err(f'[intake.import].dsl_columns "{k}" is not a column key')
        for x in imp.get('dsl_extra_columns', []):
            if not x.get('name'):
                err('[intake.import].dsl_extra_columns entries need a name')
        if layout == 'custom':
            warn('import-trigger with layout custom: the DSL/trigger will still be hand-written')
    if pat == 'direct' and (intake.get('direct') or {}).get('parser', 'none') not in ('none', 'hand'):
        err('[intake.direct].parser must be "none" or "hand"')
    ap = spec.get('appsheet') or {}
    if channels.get('appsheet') and ap.get('mode') != 'runbook':
        err('[channels].appsheet = true needs [appsheet].mode = "runbook"')
    if ap.get('mode') == 'runbook' and not ap.get('app'):
        err('[appsheet].app (the existing app to extend) is required for a runbook')

    # ---- skill / life / safety
    sk = spec.get('skill') or {}
    if sk.get('name') and not KEBAB.match(sk['name']):
        err(f'[skill].name "{sk["name"]}" must be kebab-case')
    if not sk.get('name'):
        warn('[skill].name missing: defaults to [sheet].id')
    if len(sk.get('triggers', [])) < 3:
        err('[skill].triggers needs at least 3 phrases')
    if not sk.get('judgment'):
        warn('[skill].judgment is empty')
    if not (spec.get('life') or {}).get('domain'):
        err('[life].domain is required')
    saf = spec.get('safety') or {}
    if saf.get('never_invent') is not True:
        err('[safety].never_invent must be true')
    if sheet.get('mode') == 'adopt' and saf.get('keep_existing_layout') is not True:
        err('mode "adopt" requires [safety].keep_existing_layout = true')
    if saf.get('scratch_test') is not True:
        warn('[safety].scratch_test is not true: the generator would skip the scratch-tab proof')
    return E, W


def live_check(spec):
    """Compare declared headers with the live tab (read-only). Returns (errors, infos)."""
    sheet = spec['sheet']
    if sheet.get('mode') != 'adopt' or sheet.get('layout') != 'table':
        return [], [f'live check skipped (mode={sheet.get("mode")}, layout={sheet.get("layout")})']
    sys.path.insert(0, os.path.expanduser('~/.qwen/skills/_freetext-import-lib'))
    from intake_common import Sheets
    wbs = tomllib.load(open(os.path.join(HERE, 'workbooks.toml'), 'rb'))['workbooks']
    sh = Sheets(wbs[sheet['workbook']])
    live = (sh.get_values(f"'{sheet['title']}'!1:1") or [[]])[0]
    declared = [c['header'] for c in spec['columns']]
    E, I = [], []
    for i, h in enumerate(declared):
        got = live[i] if i < len(live) else None
        if got != h:
            E.append(f'drift at column {i + 1}: spec "{h}" vs live {got!r}')
    if len(live) > len(declared):
        I.append(f'{len(live) - len(declared)} extra live column(s) to the right, tolerated: {live[len(declared):]}')
    return E, I


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('specs', nargs='+')
    ap.add_argument('--live', action='store_true', help='compare adopt specs with the live tab header (read-only)')
    a = ap.parse_args()
    bad = 0
    for p in a.specs:
        try:
            spec = tomllib.load(open(p, 'rb'))
        except (tomllib.TOMLDecodeError, OSError) as e:
            print(f'{p}: cannot parse — {e}')
            bad += 1
            continue
        E, W = lint(spec, p)
        I = []
        if a.live and not E:
            LE, I = live_check(spec)
            E += LE
        status = 'FAIL' if E else 'ok'
        print(f'{os.path.basename(p)}: {status}  ({len(spec.get("columns", []))} columns, pattern {spec.get("intake", {}).get("pattern")}, layout {spec.get("sheet", {}).get("layout")})')
        for m in E:
            print(f'   ERROR  {m}')
        for m in W:
            print(f'   warn   {m}')
        for m in I:
            print(f'   info   {m}')
        bad += bool(E)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
