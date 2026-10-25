#!/usr/bin/env python3
"""
Engine of /freetext-to-spreadsheet (a.k.a. /sheet-intake): turns text or structured data into rows of a Google Sheet.

One pipeline, many sheets. A *profile* (profiles/<name>.py, class Profile subclass, instance exported as PROFILE)
describes ONE target sheet and supplies only what is specific to it; the engine owns everything common:

    input (--text/--file/stdin, --json, or profile-specific like --csv)
      -> profile.parse_structured()        # deterministic parser for known shapes; None => not recognised
      -> else LLM extraction               # profile.llm_prompt() + profile.from_llm() — never invents values
      -> profile.finalize()                # normalisation, defaults, warnings
      -> profile.show()                    # preview (also what --dry-run prints)
      -> profile.write()                   # default: append rows to the tab, formatting per column kind

Common CLI flags (added by the engine): --text --file --json --date --init --check --dry-run --llm --no-llm.
A profile adds its own flags in add_args() and may add actions in extra_actions().

Parsed = {'rows': [dict, ...], 'warnings': [str, ...], 'meta': {...}, 'source': 'structured'|'llm'|'json'|..., 'ok': bool}
"""
import datetime
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.expanduser('~/.qwen/skills/_freetext-import-lib'))
from intake_common import Sheets, llm_json  # noqa: E402

KIND_FORMATS = {                       # column kind -> (Sheets number-format type, pattern)
    'date': ('DATE', 'yyyy-mm-dd'),
    'datetime': ('DATE_TIME', 'yyyy-mm-dd hh:mm'),
    'time': ('TIME', 'hh:mm'),
    'percent': ('PERCENT', '0%'),
}


class Column:
    def __init__(self, key, header, kind='text', width=None, wrap=False):
        self.key, self.header, self.kind, self.width, self.wrap = key, header, kind, width, wrap


class Ctx:
    """Everything a profile hook may need."""
    def __init__(self, args, sheets):
        self.args = args
        self.sheets = sheets
        self.today = datetime.date.today()
        self.text = ''


def col_letter(n):  # 1-based
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


class Profile:
    # ---- declarative part -------------------------------------------------------------------------------------
    name = ''
    description = ''
    tab = ''
    columns = []                      # list[Column] — used by the default writer / init / show / check
    date_key = 'date'                 # column used by the default check()
    show_empty_exclude = ()           # column keys not reported as "empty" in the preview
    row_label = 'row'

    # ---- CLI --------------------------------------------------------------------------------------------------
    def add_args(self, ap):
        """Add profile-specific flags to the argparse parser."""

    def extra_actions(self, ctx):
        """Handle profile-specific action flags (e.g. --header). Return True if handled (engine then stops)."""
        return False

    # ---- input --------------------------------------------------------------------------------------------------
    def read_text(self, ctx):
        a = ctx.args
        if a.text is not None:
            return a.text
        if a.file:
            return open(os.path.expanduser(a.file), encoding='utf-8').read()
        return sys.stdin.read()

    def parse_structured(self, text, ctx):
        """Deterministic parser for the shapes this sheet knows. Return a Parsed dict (with 'ok') or None."""
        return None

    def llm_prompt(self, ctx):
        raise SystemExit(f'Profile "{self.name}" has no free-text (LLM) mode.')

    def from_llm(self, data, ctx, source='llm'):
        """JSON coming from the LLM (or --json) -> Parsed."""
        raise NotImplementedError

    def acquire(self, ctx):
        a = ctx.args
        if a.json_in is not None:
            return self.from_llm(json.loads(a.json_in), ctx, source='json')
        text = self.read_text(ctx)
        if not text.strip():
            raise SystemExit('Empty input — nothing to log.')
        ctx.text = text
        parsed = None if a.llm else self.parse_structured(text, ctx)
        if parsed is not None and parsed.get('ok', True):
            return parsed
        if a.no_llm:
            if parsed is None:
                raise SystemExit('Input not recognised and --no-llm is set.')
            parsed['warnings'].append('structured parse incomplete and --no-llm set — using what was parsed')
            return parsed
        print('(input not in a script-ready structure — extracting with the LLM)', file=sys.stderr)
        return self.from_llm(llm_json(self.llm_prompt(ctx), text), ctx, source='llm')

    # ---- post-processing / preview ----------------------------------------------------------------------------------
    def finalize(self, parsed, ctx):
        """Normalise rows, apply defaults, append warnings. Return the (mutated) Parsed."""
        return parsed

    def show(self, parsed, ctx):
        rows = parsed['rows']
        for i, row in enumerate(rows):
            print(f'--- Parsed ({parsed["source"]}) — {self.row_label} {i + 1}/{len(rows)} ---')
            for c in self.columns:
                v = row.get(c.key, '')
                print(f'{c.header:<48} {v if v != "" else "·"}')
            if i == 0:
                empty = [c.header for c in self.columns if row.get(c.key, '') == '' and c.key not in self.show_empty_exclude]
                if empty:
                    print(f'Empty (fine if not observed): {", ".join(empty)}')

    # ---- sheet plumbing (default writer: append rows) ----------------------------------------------------------------
    def _fmt_requests(self, sid, start_row, end_row):
        reqs = []
        for i, c in enumerate(self.columns):
            if c.kind in KIND_FORMATS:
                t, p = KIND_FORMATS[c.kind]
                rng = {'sheetId': sid, 'startRowIndex': start_row, 'startColumnIndex': i, 'endColumnIndex': i + 1}
                if end_row is not None:
                    rng['endRowIndex'] = end_row
                reqs.append({'repeatCell': {'range': rng, 'cell': {'userEnteredFormat': {'numberFormat': {'type': t, 'pattern': p}}},
                                            'fields': 'userEnteredFormat.numberFormat'}})
        return reqs

    def init(self, ctx):
        sh = ctx.sheets
        if sh.sheet_id(self.tab) is not None:
            print(f'Tab "{self.tab}" already exists.')
            return
        reply = sh.batch([{'addSheet': {'properties': {'title': self.tab, 'gridProperties': {'frozenRowCount': 1}}}}])
        sid = reply[0]['replies'][0]['addSheet']['properties']['sheetId']
        n = len(self.columns)
        reqs = [{'repeatCell': {'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': n},
                                'cell': {'userEnteredFormat': {'textFormat': {'bold': True},
                                                               'backgroundColor': {'red': .96, 'green': .96, 'blue': .97},
                                                               'wrapStrategy': 'WRAP'}},
                                'fields': 'userEnteredFormat(textFormat,backgroundColor,wrapStrategy)'}}]
        reqs += self._fmt_requests(sid, 1, None)
        for i, c in enumerate(self.columns):
            if c.wrap:
                reqs.append({'repeatCell': {'range': {'sheetId': sid, 'startRowIndex': 1, 'startColumnIndex': i, 'endColumnIndex': i + 1},
                                            'cell': {'userEnteredFormat': {'wrapStrategy': 'WRAP'}}, 'fields': 'userEnteredFormat.wrapStrategy'}})
            if c.width:
                reqs.append({'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': i, 'endIndex': i + 1},
                                                           'properties': {'pixelSize': c.width}, 'fields': 'pixelSize'}})
        sh.batch(reqs)
        sh.put_values(f"'{self.tab}'!A1:{col_letter(n)}1", [[c.header for c in self.columns]], input_option='RAW')
        print(f'Tab "{self.tab}" created.')

    def write(self, parsed, ctx):
        sh = ctx.sheets
        sh.sheet_id(self.tab) is None and self.init(ctx)
        sid = sh.sheet_id(self.tab)
        last = col_letter(len(self.columns))
        for row in parsed['rows']:
            url = (f"{sh.base}/values/{urllib.parse.quote(chr(39) + self.tab + chr(39), safe='')}!A:{last}:append"
                   '?valueInputOption=USER_ENTERED&insertDataOption=OVERWRITE')
            updated = sh.call('POST', url, {'values': [[row.get(c.key, '') for c in self.columns]]})['updates']['updatedRange']
            r = int(re.search(r'![A-Z]+(\d+)', updated)[1])          # 1-based
            fmt = self._fmt_requests(sid, r - 1, r)                    # inserted rows would inherit the header's format
            if fmt:
                sh.batch(fmt)
            print(f'Appended to "{self.tab}": {updated}')

    def check(self, ctx):
        """Exit-code style check used by --check. Default: is there a row for the given date (--date, default today)?"""
        idx = [c.key for c in self.columns].index(self.date_key)
        day = ctx.args.date or ctx.today.isoformat()
        vals = ctx.sheets.get_values(f"'{self.tab}'!{col_letter(idx + 1)}2:{col_letter(idx + 1)}")
        found = day in {r[0].strip() for r in vals if r}
        print(f'{"Entry found" if found else "No entry"} for {day}.')
        return 0 if found else 1


def run(profile, args):
    """Common pipeline. `args` = parsed argparse namespace (common + profile flags)."""
    ctx = Ctx(args, Sheets())
    if args.init:
        profile.init(ctx)
        return 0
    if args.check:
        return profile.check(ctx)
    if profile.extra_actions(ctx):
        return 0
    parsed = profile.acquire(ctx)
    parsed.setdefault('warnings', [])
    parsed = profile.finalize(parsed, ctx)
    profile.show(parsed, ctx)
    for w in parsed['warnings']:
        print(f'! {w}')
    if args.dry_run:
        print(f'(dry run — {len(parsed["rows"])} row(s), nothing written)')
        return 0
    profile.write(parsed, ctx)
    return 0
