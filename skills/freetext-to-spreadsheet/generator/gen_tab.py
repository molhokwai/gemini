"""Tab creation and verification from a sheet spec (layout = "table"). Uses the shared Sheets client; never touches an existing tab in create()."""
import os
import sys

sys.path.insert(0, os.path.expanduser('~/.qwen/skills/_freetext-import-lib'))
from intake_common import Sheets  # noqa: E402

FORMATS = {'date': ('DATE', 'yyyy-mm-dd'), 'datetime': ('DATE_TIME', 'yyyy-mm-dd hh:mm'), 'time': ('TIME', 'hh:mm'), 'percent': ('PERCENT', '0%')}


def col_letter(n):
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def workbook_id(spec, wbs):
    return wbs[spec['sheet']['workbook']]


def create_tab(sh, spec, title=None):
    """Creates the tab (header, formats, validation, notes, widths, frozen rows). Refuses if it already exists. Returns the sheetId."""
    title = title or spec['sheet']['title']
    if sh.sheet_id(title) is not None:
        raise SystemExit(f'Tab "{title}" already exists — mode "adopt" verifies, it never recreates.')
    cols = spec['columns']
    n = len(cols)
    frozen = spec['sheet'].get('frozen_rows', 1)
    sid = sh.batch([{'addSheet': {'properties': {'title': title, 'gridProperties': {'frozenRowCount': frozen, 'columnCount': max(n, 1) + 2}}}}])[0]['replies'][0]['addSheet']['properties']['sheetId']
    rng = lambda c0, c1, r0=1, r1=None: {k: v for k, v in {'sheetId': sid, 'startRowIndex': r0, 'endRowIndex': r1, 'startColumnIndex': c0, 'endColumnIndex': c1}.items() if v is not None}
    reqs = [{'repeatCell': {'range': rng(0, n, 0, 1), 'cell': {'userEnteredFormat': {'textFormat': {'bold': True}, 'backgroundColor': {'red': .96, 'green': .96, 'blue': .97}, 'wrapStrategy': 'WRAP'}},
                            'fields': 'userEnteredFormat(textFormat,backgroundColor,wrapStrategy)'}}]
    for i, c in enumerate(cols):
        t = c['type']
        if t in FORMATS:
            ty, pat = FORMATS[t]
            reqs.append({'repeatCell': {'range': rng(i, i + 1), 'cell': {'userEnteredFormat': {'numberFormat': {'type': ty, 'pattern': pat}}}, 'fields': 'userEnteredFormat.numberFormat'}})
        if t == 'longtext' or c.get('wrap'):
            reqs.append({'repeatCell': {'range': rng(i, i + 1), 'cell': {'userEnteredFormat': {'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat.wrapStrategy'}})
        if c.get('width'):
            reqs.append({'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i + 1}, 'properties': {'pixelSize': c['width']}, 'fields': 'pixelSize'}})
        rule = None
        if t == 'choice':
            if c.get('choices'):
                rule = {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in c['choices']]}, 'showCustomUi': True, 'strict': True}
            elif c.get('choices_from'):
                rule = {'condition': {'type': 'ONE_OF_RANGE', 'values': [{'userEnteredValue': '=' + c['choices_from']}]}, 'showCustomUi': True, 'strict': True}
        elif t in ('integer', 'number') and ('min' in c or 'max' in c):
            lo, hi = c.get('min', -1e12), c.get('max', 1e12)
            rule = {'condition': {'type': 'NUMBER_BETWEEN', 'values': [{'userEnteredValue': str(lo)}, {'userEnteredValue': str(hi)}]}, 'strict': True}
        elif t == 'percent':
            lo, hi = c.get('min', 0) / 100.0, c.get('max', 100) / 100.0
            rule = {'condition': {'type': 'NUMBER_BETWEEN', 'values': [{'userEnteredValue': str(lo)}, {'userEnteredValue': str(hi)}]}, 'strict': True}
        elif t == 'boolean':
            rule = {'condition': {'type': 'NUMBER_BETWEEN', 'values': [{'userEnteredValue': '0'}, {'userEnteredValue': '1'}]}, 'inputMessage': '1 = yes, 0 = no, empty = not given', 'strict': True}
        if rule:
            reqs.append({'setDataValidation': {'range': rng(i, i + 1), 'rule': rule}})
        if c.get('note'):
            reqs.append({'updateCells': {'range': rng(i, i + 1, 0, 1), 'rows': [{'values': [{'note': c['note']}]}], 'fields': 'note'}})
    sh.batch(reqs)
    sh.put_values(f"'{title}'!A1:{col_letter(n)}1", [[c['header'] for c in cols]], input_option='RAW')
    return sid


def verify_tab(sh, spec, title=None):
    """Read-only drift check: declared headers vs the live header row. Returns (errors, infos)."""
    title = title or spec['sheet']['title']
    if sh.sheet_id(title) is None:
        return [f'tab "{title}" does not exist'], []
    live = (sh.get_values(f"'{title}'!1:1") or [[]])[0]
    E, I = [], []
    for i, c in enumerate(spec.get('columns', [])):
        got = live[i] if i < len(live) else None
        if got != c['header']:
            E.append(f'drift at column {i + 1}: spec "{c["header"]}" vs live {got!r}')
    extra = len(live) - len(spec.get('columns', []))
    if extra > 0:
        I.append(f'{extra} extra live column(s) to the right, tolerated: {live[len(spec.get("columns", [])):]}')
    return E, I
