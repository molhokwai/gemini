"""
TableProfile — a Profile driven entirely by a sheet spec (see generator/SPEC.md), for `layout = "table"` sheets.

Generated profiles (profiles/<id>.py, produced by `intake.py --new-sheet SPEC --apply`) are a few lines: they embed the spec dict and
instantiate this class. Everything typed lives here, once:

  - coercion per column type (date/time/datetime/integer/number/percent/boolean/choice/text/link), with WARNINGS, never guesses;
    an out-of-range or unreadable value is left EMPTY + warned (like the Taïna ratings), a missing `required` value stops and asks
  - defaults (`today` / `now`), choice canonicalisation, non-blocking reference checks (`[[reference]]`)
  - LLM prompt generated from the columns (`llm` hints, choices, formats, never-invent rule)
  - inputs: --text/--file/stdin (LLM), --json (object | list | {"rows": [...]}), --csv/--csv-text (header names or aliases)
  - writer: append (engine default) or UPSERT on `upsert_on`; formula columns are written per row from `formula` ({row})

Optional hooks: a sibling `<id>_hooks.py` may define `parse_structured(profile, text, ctx)` and/or `normalize_row(profile, row, warnings, ctx)`.
"""
import csv
import datetime
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intake_engine import Profile, Column, col_letter  # noqa: E402

TYPE_KIND = {'date': 'date', 'datetime': 'datetime', 'time': 'time', 'percent': 'percent'}
TRUE = {'1', 'yes', 'y', 'true', 'oui', 'vrai', 'ok', 'x', '✓', '✔', 'right', 'correct'}
FALSE = {'0', 'no', 'n', 'non', 'false', 'faux', '✗', '✘', 'wrong'}
EMPTY = {'', '-', '—', '?', 'n/a', 'na', 'none', 'null', 'aucun', 'aucune', 'rien'}
MONTHS = {'janv': 1, 'jan': 1, 'january': 1, 'janvier': 1, 'févr': 2, 'fev': 2, 'fév': 2, 'feb': 2, 'february': 2, 'février': 2,
          'mars': 3, 'mar': 3, 'march': 3, 'avr': 4, 'apr': 4, 'april': 4, 'avril': 4, 'mai': 5, 'may': 5,
          'juin': 6, 'jun': 6, 'june': 6, 'juil': 7, 'jul': 7, 'july': 7, 'juillet': 7, 'août': 8, 'aout': 8, 'aug': 8, 'august': 8,
          'sept': 9, 'sep': 9, 'september': 9, 'septembre': 9, 'oct': 10, 'october': 10, 'octobre': 10,
          'nov': 11, 'november': 11, 'novembre': 11, 'déc': 12, 'dec': 12, 'december': 12, 'décembre': 12}


def norm(s):
    return re.sub(r'[^a-z0-9]+', '', str(s).casefold().translate(str.maketrans('éèêëàâäôöûüîïç', 'eeeeaaaoouuiic')))


# ------------------------------------------------------------------ pure coercions (unit-testable)

def parse_date(s, today=None):
    t = str(s).strip().casefold()
    today = today or datetime.date.today()
    if t in ('today', "aujourd'hui", 'aujourdhui'):
        return today
    if t in ('yesterday', 'hier'):
        return today - datetime.timedelta(days=1)
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', t)
    try:
        if m:
            return datetime.date(int(m[1]), int(m[2]), int(m[3]))
        m = re.search(r'(\d{1,2})[/.](\d{1,2})[/.](\d{4})', t)
        if m:
            return datetime.date(int(m[3]), int(m[2]), int(m[1]))
        m = re.search(r'(\d{1,2})\s+([a-zéûô]+)\.?\s+(\d{4})', t)
        if m and m[2] in MONTHS:
            return datetime.date(int(m[3]), MONTHS[m[2]], int(m[1]))
    except ValueError:
        return None
    return None


def parse_time(s):
    t = str(s).strip().lower()
    m = re.search(r'\b(\d{1,2})\s*[:h]\s*(\d{2})?\s*(am|pm)?', t) or re.search(r'\b(\d{1,2})()\s*(am|pm)\b', t)
    if not m:
        return None
    hour, minute, ap = int(m[1]), int(m[2] or 0), m[3]
    if ap == 'pm' and hour < 12:
        hour += 12
    if ap == 'am' and hour == 12:
        hour = 0
    return f'{hour:02d}:{minute:02d}' if hour < 24 and minute < 60 else None


def parse_number(s):
    m = re.search(r'-?\d+(?:[.,]\d+)?', str(s).replace(' ', '').replace(' ', ''))
    return float(m[0].replace(',', '.')) if m else None


def coerce(col, value, warnings, today=None, now=None):
    """One raw value -> the value to write ('' = leave empty). Never raises; appends to `warnings`."""
    t, h = col['type'], col['header']
    if value is None:
        return ''
    if isinstance(value, str):
        value = value.strip()
        if value.casefold() in EMPTY:
            return ''
    if t in ('text', 'longtext', 'link'):
        return str(value)
    if t == 'date':
        d = parse_date(value, today)
        if d is None:
            warnings.append(f'{h}: "{value}" is not a readable date — left empty')
            return ''
        return d.isoformat()
    if t == 'time':
        r = parse_time(value)
        if r is None:
            warnings.append(f'{h}: "{value}" is not a readable time — left empty')
            return ''
        return r
    if t == 'datetime':
        if str(value).strip().casefold() == 'now':
            return (now or datetime.datetime.now()).strftime('%Y-%m-%d %H:%M')
        d, r = parse_date(value, today), parse_time(re.sub(r'\d{4}-\d{2}-\d{2}', '', str(value)))
        if d is None:
            warnings.append(f'{h}: "{value}" is not a readable date-time — left empty')
            return ''
        return f'{d.isoformat()} {r or "00:00"}'
    if t in ('integer', 'number', 'percent'):
        n = parse_number(value)
        if n is None:
            warnings.append(f'{h}: "{value}" is not a number — left empty')
            return ''
        if t == 'percent':
            n = n / 100.0                      # input is 0-100 ("60", "60%"); stored as a fraction
            lo, hi = (col.get('min', 0) / 100.0 if 'min' in col else 0), (col.get('max', 100) / 100.0 if 'max' in col else 1)
        else:
            lo, hi = col.get('min'), col.get('max')
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            warnings.append(f'{h}: {value} is outside [{lo}, {hi}] — left empty')
            return ''
        if t == 'integer':
            if n != int(n):
                warnings.append(f'{h}: {value} is not a whole number — left empty')
                return ''
            return int(n)
        return round(n, 6) if t == 'percent' else (int(n) if n == int(n) else n)
    if t == 'boolean':
        v = str(value).strip().casefold()
        if v in TRUE:
            return 1
        if v in FALSE:
            return 0
        warnings.append(f'{h}: "{value}" is not yes/no — left empty')
        return ''
    if t == 'choice':
        choices = col.get('choices') or col.get('_resolved_choices') or []
        for c in choices:
            if norm(c) == norm(value):
                return c
        if choices:
            warnings.append(f'{h}: "{value}" is not one of {choices} — kept as written, check it')
        return str(value)
    return str(value)


class TableProfile(Profile):
    def __init__(self, spec):
        self.spec = spec
        sh = spec['sheet']
        self.name = sh['id']
        self.description = sh['description']
        self.tab = sh['title']
        self.cols = spec.get('columns', [])
        self.key_index = {c['key']: i for i, c in enumerate(self.cols)}
        self.columns = [Column(c['key'], c['header'], TYPE_KIND.get(c['type'], 'text'), c.get('width'), bool(c.get('wrap')) or c['type'] == 'longtext')
                        for c in self.cols]
        self.upsert_on = sh.get('upsert_on') or []
        self.date_key = next((c['key'] for c in self.cols if c['type'] == 'date'), 'date')
        self.hooks = None
        hp = spec.get('_hooks_path')
        if hp and os.path.isfile(hp):
            import importlib.util
            s = importlib.util.spec_from_file_location(f'{self.name}_hooks', hp)
            self.hooks = importlib.util.module_from_spec(s)
            s.loader.exec_module(self.hooks)
        self._ref_cache = {}

    # ---- CLI
    def add_args(self, ap):
        ap.add_argument('--csv', help='CSV file (or - for stdin); header names or aliases select the columns')
        ap.add_argument('--csv-text', help='CSV content inline')

    # ---- LLM prompt from the spec
    def llm_prompt(self, ctx):
        sp = self.spec
        lines = [f'You extract data from free text (any language) into JSON rows for a spreadsheet: {self.description}.',
                 'Reply with JSON only (no prose, no code fences): {"rows": [ { <fields> }, ... ]} — one object per record described in the text.',
                 'Fields (each a string, number or null when the text does not say):']
        for c in self.cols:
            if c['type'] == 'formula':
                continue
            desc = {'date': 'date "YYYY-MM-DD"', 'time': 'time "HH:MM" 24h', 'datetime': 'date-time "YYYY-MM-DD HH:MM"',
                    'integer': 'whole number', 'number': 'number', 'percent': 'number 0-100 (percent)', 'boolean': 'yes/no',
                    'text': 'text', 'longtext': 'text (keep the writer\'s words)', 'link': 'URL', 'choice': 'one of the allowed values'}[c['type']]
            extra = ''
            if c['type'] == 'choice':
                ch = c.get('choices') or c.get('_resolved_choices')
                extra = f' — allowed: {json.dumps(ch, ensure_ascii=False)}' if ch else ' — must match the reference list'
            if 'min' in c or 'max' in c:
                extra += f' — range {c.get("min", "")}..{c.get("max", "")}'
            hint = f' — {c["llm"]}' if c.get('llm') else ''
            lines.append(f'- {c["key"]} ({c["header"]}): {desc}{extra}{hint}')
        rules = ['Rules: never invent or infer a value the text does not contain; leave it null instead.']
        if any(c.get('default') in ('today', 'now') for c in self.cols):
            rules.append(f'Today is {ctx.today.isoformat()}; resolve "today"/"yesterday" against it. Dates/times not stated stay null (defaults are applied later).')
        lines += rules
        return '\n'.join(lines)

    # ---- input
    def _rows_from_csv(self, text):
        rd = list(csv.reader(io.StringIO(text.strip('\n'))))
        if not rd:
            raise SystemExit('Empty CSV')
        by_name = {}
        for c in self.cols:
            for n in [c['header'], c['key']] + list(c.get('aliases', [])):
                by_name[norm(n)] = c['key']
        head = [by_name.get(norm(h)) for h in rd[0]]
        if not any(head):
            raise SystemExit(f'CSV header matches no column (expected some of: {", ".join(c["header"] for c in self.cols)})')
        unknown = [h for h, k in zip(rd[0], head) if not k and h.strip()]
        rows = [{k: v for k, v in zip(head, r) if k} for r in rd[1:] if any(x.strip() for x in r)]
        return rows, [f'CSV column "{u}" ignored (not in the sheet)' for u in unknown]

    def acquire(self, ctx):
        a = ctx.args
        if a.csv is not None or a.csv_text is not None:
            text = sys.stdin.read() if a.csv == '-' else (open(os.path.expanduser(a.csv), encoding='utf-8').read() if a.csv else a.csv_text)
            rows, warns = self._rows_from_csv(text)
            return {'rows': rows, 'warnings': warns, 'meta': {}, 'source': 'csv', 'ok': True}
        return super().acquire(ctx)

    def parse_structured(self, text, ctx):
        if self.hooks and hasattr(self.hooks, 'parse_structured'):
            return self.hooks.parse_structured(self, text, ctx)
        return None

    def from_llm(self, data, ctx, source='llm'):
        if isinstance(data, dict):
            data = data.get('rows', [data])
        return {'rows': [r for r in data if isinstance(r, dict)], 'warnings': [], 'meta': {}, 'source': source, 'ok': True}

    # ---- normalisation
    def _reference_values(self, ctx, ref):
        k = ref['tab']
        if k not in self._ref_cache:
            v = ctx.sheets.get_values(f"'{ref['tab']}'!1:1000")
            head = v[0] if v else []
            idx = next((i for i, h in enumerate(head) if norm(h) == norm(ref['key_column'])), None)
            self._ref_cache[k] = {norm(r[idx]) for r in v[1:] if idx is not None and len(r) > idx and r[idx]} if idx is not None else None
        return self._ref_cache[k]

    def finalize(self, parsed, ctx):
        today, now = ctx.today, datetime.datetime.now()
        if ctx.args.date:
            forced = parse_date(ctx.args.date, today)
            if forced is None:
                raise SystemExit(f'Unreadable --date: {ctx.args.date}')
            today = forced
        # choices coming from a reference range
        for c in self.cols:
            cf = c.get('choices_from')
            if cf and '_resolved_choices' not in c:
                tab, rng = cf.split('!', 1)
                try:
                    c['_resolved_choices'] = [r[0] for r in ctx.sheets.get_values(f"'{tab.strip(chr(39))}'!{rng}") if r and r[0]]
                except SystemExit:
                    c['_resolved_choices'] = []
        out, warnings = [], parsed['warnings']
        for i, raw in enumerate(parsed['rows'], 1):
            row, w = {}, []
            for c in self.cols:
                if c['type'] == 'formula':
                    continue
                v = raw.get(c['key'])
                if v in (None, '') or (isinstance(v, str) and v.strip().casefold() in EMPTY):
                    d = c.get('default')
                    if d == 'today':
                        v = today.isoformat()
                    elif d == 'now':
                        v = now.strftime('%Y-%m-%d %H:%M') if c['type'] == 'datetime' else now.strftime('%H:%M')
                    elif d not in (None, ''):
                        v = d
                row[c['key']] = coerce(c, v, w, today, now)
            if self.hooks and hasattr(self.hooks, 'normalize_row'):
                row = self.hooks.normalize_row(self, row, w, ctx) or row
            for c in self.cols:
                if c.get('required') and row.get(c['key'], '') == '':
                    raise SystemExit(f'Row {i}: missing required "{c["header"]}" — ask the user for it, do not guess.')
            for ref in self.spec.get('reference', []):
                vals = self._reference_values(ctx, ref)
                if vals is None:
                    continue
                for k in ref['used_by']:
                    v = row.get(k, '')
                    if v != '' and norm(v) not in vals:
                        w.append(f'{self.cols[self.key_index[k]]["header"]}: "{v}" not found in "{ref["tab"]}" — kept, check it')
            warnings += [f'row {i}: {m}' for m in w] if len(parsed['rows']) > 1 else w
            out.append(row)
        parsed['rows'] = out
        return parsed

    # ---- write: append (engine) or upsert; formula columns per row
    def _formula_cols(self):
        return [(i, c) for i, c in enumerate(self.cols) if c['type'] == 'formula']

    def _write_formulas(self, ctx, r):
        for i, c in self._formula_cols():
            ctx.sheets.put_values(f"'{self.tab}'!{col_letter(i + 1)}{r}", [[c['formula'].replace('{row}', str(r))]])

    def write(self, parsed, ctx):
        sh = ctx.sheets
        if sh.sheet_id(self.tab) is None:
            self.init(ctx)
        if not self.upsert_on and not self._formula_cols():
            return super().write(parsed, ctx)
        sid = sh.sheet_id(self.tab)
        last = col_letter(len(self.cols))
        for row in parsed['rows']:
            vals = [('' if c['type'] == 'formula' else row.get(c['key'], '')) for c in self.cols]
            target = None
            if self.upsert_on:
                existing = sh.get_values(f"'{self.tab}'!A2:{last}")
                ki = [self.key_index[k] for k in self.upsert_on]
                want = [norm(row.get(k, '')) for k in self.upsert_on]
                for n, ex in enumerate(existing, 2):
                    ex = list(ex) + [''] * (len(self.cols) - len(ex))
                    if [norm(ex[i]) for i in ki] == want:
                        target = n
                        break
            if target:
                for i, c in enumerate(self.cols):                     # never overwrite formula cells on update
                    if c['type'] != 'formula':
                        sh.put_values(f"'{self.tab}'!{col_letter(i + 1)}{target}", [[vals[i]]])
                print(f'Updated row {target} of "{self.tab}" (upsert on {", ".join(self.upsert_on)}).')
            else:
                url_tab = __import__('urllib.parse').parse.quote(chr(39) + self.tab + chr(39), safe='')
                res = sh.call('POST', f"{sh.base}/values/{url_tab}!A:{last}:append?valueInputOption=USER_ENTERED&insertDataOption=OVERWRITE", {'values': [vals]})
                r = int(re.search(r'![A-Z]+(\d+)', res['updates']['updatedRange'])[1])
                fmt = self._fmt_requests(sid, r - 1, r)
                if fmt:
                    sh.batch(fmt)
                self._write_formulas(ctx, r)
                print(f'Appended to "{self.tab}": {res["updates"]["updatedRange"]}')

    def check(self, ctx):
        idx = self.key_index.get(self.date_key)
        if idx is None:
            print('No date column: nothing to check.')
            return 1
        day = (parse_date(ctx.args.date, ctx.today) if ctx.args.date else ctx.today)
        vals = ctx.sheets.get_values(f"'{self.tab}'!{col_letter(idx + 1)}2:{col_letter(idx + 1)}")
        found = day.isoformat() in {r[0].strip() for r in vals if r}
        print(f'{"Entry found" if found else "No entry"} for {day.isoformat()}.')
        return 0 if found else 1
