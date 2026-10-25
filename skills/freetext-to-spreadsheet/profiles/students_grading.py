"""
Profile: students-grading — results of a student for an exercise sheet / quiz / exam, per question: correct + autonomy.

Fills the wide "Students grading" tab of "Registre Financier — life/": 2 rows per student-day — a results row
(1 / 0 / blank per question) and, under it, the autonomy row (0-100 %, one unmerged cell per question). Correct /
Answered / % / Autonomy are sheet formulas, never written here. Row 2 = question labels, row 3 = expected-answer key of
the programme the header describes; column G = Programme (named link).

Ported 2026-09-21 from students-grading/scripts/students_grading.py: the helper functions below are copied verbatim;
input handling / LLM plumbing / CLI now come from the engine.

Structured input: --student --program --program-link [--date] + --csv FILE|- / --csv-text "..."  (CSV columns:
question, expected answer, correct, autonomy; optional n/nr/#/id = grid label). Free text: --text (LLM, never inventing).
Also: --header (list grid labels + key), --check --student S --date D, --dry-run.
"""
import csv
import datetime
import io
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from intake_engine import Profile  # noqa: E402

TAB = 'Students grading'

FIRST_ROW, LAST_ROW = 4, 1001           # student-days: 2 rows each (result row, autonomy row)

COL_DATE, COL_STUDENT, COL_PROG, COL_ITEM0 = 1, 2, 7, 8   # 1-based: A, B, G, H

A1 = f"'{TAB}'!"

TRUE = {'1', 'yes', 'y', 'true', 'right', 'correct', 'ok', '✓', '✔', 'oui', 'vrai', 'juste', 'v'}

FALSE = {'0', 'no', 'n', 'false', 'wrong', 'incorrect', '✗', '✘', 'x', 'non', 'faux'}

BLANK = {'', '-', 'n/a', 'na', 'not given', 'none', 'null', '?'}

HEADER_WORDS = {'question', 'q', 'expected', 'expected answer', 'expected_answer', 'answer', 'correct', 'result',
                'autonomy', 'autonomie', 'n', 'nr', 'no', '#', 'id', 'number', 'label'}


def col_letter(n):  # 1-based
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def norm_label(s):
    s = re.sub(r'\s+', ' ', str(s).strip().lower())
    m = re.match(r'^(\d+)[\s.\-]*([a-z]+)\)?$', s)
    return f'{m.group(1)}.{m.group(2)}' if m else re.sub(r'[\s()]+', '', s)


def norm_val(x):
    t = str(x).strip().casefold()
    try:
        return repr(float(t))
    except ValueError:
        return t


def parse_correct(s):
    t = str(s).strip().casefold()
    if t in BLANK:
        return None
    if t in TRUE:
        return 1
    if t in FALSE:
        return 0
    raise SystemExit(f'Unrecognised "correct" value: {s!r} (use 1/0, yes/no, right/wrong, or leave empty)')


def parse_autonomy(s):
    t = str(s).strip().replace('%', '').replace(',', '.')
    if t.casefold() in BLANK:
        return None
    v = float(t)
    if not 0 <= v <= 100:
        raise SystemExit(f'Autonomy out of range 0-100: {s!r}')
    return v / 100


def read_header(sh):
    v = sh.get_values(A1 + 'A2:AZ3')
    labels = (v[0] if v else [])[COL_ITEM0 - 1:]
    keys = (v[1] if len(v) > 1 else [])[COL_ITEM0 - 1:]
    n = 0
    while n < len(labels) and str(labels[n]).strip():
        n += 1
    labels = labels[:n]
    keys = (list(keys) + [''] * n)[:n]
    return labels, keys


def read_csv_rows(text):
    rows = [r for r in csv.reader(io.StringIO(text.strip('\n'))) if any(c.strip() for c in r)]
    if not rows:
        raise SystemExit('Empty CSV')
    first = [c.strip().casefold() for c in rows[0]]
    if len(set(first) & HEADER_WORDS) >= 2:
        idx = {}
        for i, h in enumerate(first):
            if h in ('question', 'q'):
                idx['question'] = i
            elif h in ('expected', 'expected answer', 'expected_answer', 'answer'):
                idx['expected'] = i
            elif h in ('correct', 'result'):
                idx['correct'] = i
            elif h in ('autonomy', 'autonomie'):
                idx['autonomy'] = i
            elif h in ('n', 'nr', 'no', '#', 'id', 'number', 'label'):
                idx['n'] = i
        body = rows[1:]
    else:
        idx = {'question': 0, 'expected': 1, 'correct': 2, 'autonomy': 3}
        body = rows
    out = []
    for r in body:
        get = lambda k: r[idx[k]].strip() if k in idx and idx[k] < len(r) else ''
        out.append({'n': get('n') or None, 'question': get('question'), 'expected': get('expected'),
                    'correct': parse_correct(get('correct')), 'autonomy': parse_autonomy(get('autonomy'))})
    return out


def find_row(sh, student, day, program):
    """Row of the existing student-day (same date + student + programme text or empty programme), else first free result row."""
    v = sh.get_values(A1 + f'A{FIRST_ROW}:G{LAST_ROW}')
    first_empty = None
    for i in range(0, LAST_ROW - FIRST_ROW + 1, 2):
        r = v[i] if i < len(v) else []
        r = list(r) + [''] * (COL_PROG - len(r))
        date_s, stu, prog = str(r[0]).strip(), str(r[COL_STUDENT - 1]).strip(), str(r[COL_PROG - 1]).strip()
        if stu == student and date_s == day and (prog == '' or prog == program):
            return FIRST_ROW + i, True
        if first_empty is None and stu == '':
            first_empty = FIRST_ROW + i
    if first_empty is None:
        raise SystemExit(f'No free row left before row {LAST_ROW}')
    return first_empty, False


def chip_cell(name, url):
    mime = None
    low = (url + ' ' + name).lower()
    if 'docs.google.com/document' in low:
        mime = 'application/vnd.google-apps.document'
    elif 'docs.google.com/spreadsheets' in low:
        mime = 'application/vnd.google-apps.spreadsheet'
    elif name.lower().endswith('.docx'):
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif name.lower().endswith('.pdf'):
        mime = 'application/pdf'
    props = {'uri': url}
    if mime:
        props['mimeType'] = mime
    return {'userEnteredValue': {'stringValue': name},
            'chipRuns': [{'chip': {'richLinkProperties': props}}, {'startIndex': len(name)}]}


def link_cell(name, url):
    return {'userEnteredValue': {'stringValue': name}, 'textFormatRuns': [{'format': {'link': {'uri': url}}}]}

# ------------------------------------------------------------------ profile

class StudentsGrading(Profile):
    name = 'students-grading'
    description = 'Per-question results + autonomy of a student for an exercise sheet / quiz / exam (tab "Students grading")'
    tab = TAB

    def add_args(self, ap):
        ap.add_argument('--student')
        ap.add_argument('--program', help='programme name (shown in the Programme cell)')
        ap.add_argument('--program-link', help='URL of the programme document (Google Doc / Drive file)')
        ap.add_argument('--comment')
        ap.add_argument('--csv', help='CSV file, or - for stdin')
        ap.add_argument('--csv-text', help='CSV content passed inline')
        ap.add_argument('--header', action='store_true', help='list the grid question labels and key')

    # ---- actions
    def extra_actions(self, ctx):
        if not ctx.args.header:
            return False
        labels, keys = read_header(ctx.sheets)
        print(f'{len(labels)} question columns in "{TAB}":')
        for l, k in zip(labels, keys):
            print(f'  {norm_label(l):>6}  key={k}')
        return True

    def check(self, ctx):
        a = ctx.args
        if not a.student:
            raise SystemExit('--check needs --student (and optionally --date)')
        day = a.date or datetime.date.today().isoformat()
        row, exists = find_row(ctx.sheets, a.student, day, a.program or '')
        print(f'row {row}' if exists else 'no entry')
        return 0 if exists else 1

    # ---- input
    def acquire(self, ctx):
        a = ctx.args
        if a.csv is not None or a.csv_text is not None:
            text = sys.stdin.read() if a.csv == '-' else (open(a.csv, encoding='utf-8').read() if a.csv else a.csv_text)
            return {'rows': read_csv_rows(text), 'warnings': [], 'meta': {}, 'source': 'csv', 'ok': True}
        if a.text is None and a.json_in is None:
            raise SystemExit('Give --csv/--csv-text, --text, --json, --header or --check')
        return super().acquire(ctx)

    def llm_prompt(self, ctx):
        labels, keys = read_header(ctx.sheets)
        today = datetime.date.today().isoformat()
        grid = '; '.join(f'{norm_label(l)} (key {k})' for l, k in zip(labels, keys)) or '(no grid header)'
        return (
            'You extract grading data from free text (any language) into JSON for a spreadsheet. Reply with JSON only, '
            'no prose, no code fences.\n'
            'Schema: {"student": str|null, "date": "YYYY-MM-DD"|null, "program": str|null, "program_link": str|null, '
            '"comment": str|null, "rows": [{"n": str|null, "question": str|null, "expected": str|null, '
            '"correct": 1|0|null, "autonomy": number 0-100|null}]}\n'
            'Rules: NEVER invent values — anything not stated is null. "correct" is 1 for right, 0 for wrong, null if the '
            'question was not given or not mentioned. "autonomy" is 0-100 (0 = needed full help, 100 = did it alone). '
            'One row per question. When the text speaks about a whole exercise ("exercise 1 all right", "exercise 2 all wrong '
            'except the third"), expand it into one row per question of that exercise using the grid labels below '
            '(labels look like "1.i", "1.ii", "2.i"). Use "n" = the grid label whenever the text identifies a question '
            'that way. Resolve relative dates ("today", "yesterday") against today = ' + today + '.\n'
            'Grid labels of the current programme: ' + grid)

    def from_llm(self, data, ctx, source='llm'):
        if isinstance(data, list):
            data = {'rows': data}
        rows = []
        for r in data.get('rows') or []:
            rows.append({'n': (str(r['n']) if r.get('n') else None), 'question': r.get('question') or '',
                         'expected': '' if r.get('expected') is None else str(r.get('expected')),
                         'correct': None if r.get('correct') is None else (1 if str(r['correct']).strip().casefold() in TRUE else 0),
                         'autonomy': None if r.get('autonomy') in (None, '') else parse_autonomy(r['autonomy'])})
        meta = {k: data.get(k) for k in ('student', 'date', 'program', 'program_link', 'comment')}
        print('LLM extraction:', meta, f'{len(rows)} rows')
        return {'rows': rows, 'warnings': [], 'meta': meta, 'source': source, 'ok': True}

    # ---- planning (no writes)
    def finalize(self, parsed, ctx):
        a, m = ctx.args, parsed['meta']
        student = a.student or m.get('student')
        program = a.program or m.get('program')
        link = a.program_link or m.get('program_link')
        comment = a.comment or m.get('comment')
        day = a.date or m.get('date') or datetime.date.today().isoformat()
        rows = parsed['rows']
        if not student:
            raise SystemExit('Missing student name (--student, or present in the text)')
        if not program:
            raise SystemExit('Missing programme name (--program, or present in the text)')
        if not rows:
            raise SystemExit('No question rows to write')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(day)):
            raise SystemExit(f'Bad date {day!r} (use YYYY-MM-DD)')
        labels, keys = read_header(ctx.sheets)
        by_label = {norm_label(l): i for i, l in enumerate(labels)}
        n_cols = len(labels)
        results, autonomy, notes, seen = [''] * n_cols, [''] * n_cols, {}, set()
        for k, r in enumerate(rows):
            if r['n']:
                i = by_label.get(norm_label(r['n']))
                if i is None:
                    raise SystemExit(f'Question label {r["n"]!r} is not in the grid header ({", ".join(list(by_label)[:6])}...)')
            else:
                i = k
                if i >= n_cols:
                    raise SystemExit(f'{len(rows)} questions but the grid has {n_cols} question columns — extend the header first')
            if i in seen:
                raise SystemExit(f'Two rows map to the same column ({labels[i]})')
            seen.add(i)
            results[i] = '' if r['correct'] is None else r['correct']
            autonomy[i] = '' if r['autonomy'] is None else r['autonomy']
            if r['expected'] != '' and norm_val(r['expected']) != norm_val(keys[i]):
                notes[i] = f'{r["question"] or labels[i]} -> {r["expected"]}'
        row, exists = find_row(ctx.sheets, student, day, program)
        parsed['plan'] = dict(student=student, program=program, link=link, comment=comment, day=day, n_cols=n_cols,
                              results=results, autonomy=autonomy, notes=notes, row=row, exists=exists)
        return parsed

    def show(self, parsed, ctx):
        p = parsed['plan']
        answered = [x for x in p['results'] if x != '']
        aut = [x for x in p['autonomy'] if x != '']
        print(f'{"Updating" if p["exists"] else "New"} student-day: {p["student"]} {p["day"]} — rows {p["row"]}/{p["row"] + 1}'
              f' — programme "{p["program"]}"')
        print(f'  {len(answered)} answered, {sum(answered)} correct'
              + (f' ({sum(answered) / len(answered):.0%})' if answered else '')
              + (f', mean autonomy {sum(aut) / len(aut):.0%}' if aut else ''))
        if p['notes']:
            parsed['warnings'].append(f'{len(p["notes"])} expected answer(s) differ from the grid key row (another programme?) — kept as cell notes')

    # ---- write
    def write(self, parsed, ctx):
        sh, p = ctx.sheets, parsed['plan']
        sid = sh.sheet_id(TAB)
        row, n_cols = p['row'], p['n_cols']
        last_col = COL_ITEM0 + n_cols - 1
        if not p['exists']:
            sh.put_values(A1 + f'A{row}:B{row}', [[p['day'], p['student']]])
        sh.put_values(A1 + f'{col_letter(COL_ITEM0)}{row}:{col_letter(last_col)}{row}', [p['results']])
        sh.put_values(A1 + f'{col_letter(COL_ITEM0)}{row + 1}:{col_letter(last_col)}{row + 1}', [p['autonomy']])
        reqs = [{'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                            'startColumnIndex': COL_ITEM0 - 1, 'endColumnIndex': last_col},
                                 'rows': [{'values': [{} for _ in range(n_cols)]}], 'fields': 'note'}}]   # reset notes on the row
        for i, txt in p['notes'].items():
            reqs.append({'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                                   'startColumnIndex': COL_ITEM0 - 1 + i, 'endColumnIndex': COL_ITEM0 + i},
                                        'rows': [{'values': [{'note': txt}]}], 'fields': 'note'}})
        if p['comment']:
            reqs.append({'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                                   'startColumnIndex': COL_STUDENT - 1, 'endColumnIndex': COL_STUDENT},
                                        'rows': [{'values': [{'note': p['comment']}]}], 'fields': 'note'}})
        sh.batch(reqs)
        cur = sh.get_values(A1 + f'G{row}')
        cur_txt = cur[0][0] if cur and cur[0] else ''
        if cur_txt != p['program']:            # keep an existing cell (e.g. a smart chip) that already shows this programme
            cell = None
            rng = {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row, 'startColumnIndex': COL_PROG - 1, 'endColumnIndex': COL_PROG}
            if p['link']:
                try:
                    sh.batch([{'updateCells': {'range': rng, 'rows': [{'values': [chip_cell(p['program'], p['link'])]}], 'fields': 'userEnteredValue,chipRuns'}}])
                    cell = 'chip'
                except SystemExit:
                    sh.batch([{'updateCells': {'range': rng, 'rows': [{'values': [link_cell(p['program'], p['link'])]}], 'fields': 'userEnteredValue,textFormatRuns'}}])
                    cell = 'link'
            else:
                sh.put_values(A1 + f'G{row}', [[p['program']]])
                cell = 'text'
            print(f'  programme cell: {cell}')
        print('Done.')


PROFILE = StudentsGrading()
