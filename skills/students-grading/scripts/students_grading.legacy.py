#!/usr/bin/env python3
"""
Fills the "Students grading" tab of "Registre Financier — life/" (wide layout, 2 rows per student-day):

    row r   : Date | Student | Correct | Answered | % | Autonomy | Programme | <one result cell per question>   (1 / 0 / blank)
    row r+1 : "↳ Autonomy %"                                              | <one autonomy cell per question>  (fraction, shown as %)

Correct / Answered / % / Autonomy are sheet formulas — never written here. Row 2 holds the question labels
("1. i)"...), row 3 the expected-answer key of the programme the header describes.

Structured input (CSV): student + programme name + programme link + list of [question, expected answer, correct, autonomy].
Unstructured input (--text): an LLM turns the text into the same structure (never inventing values), then the same path runs.

Usage:
  students_grading.py --student Dang --program "<name>" --program-link URL [--date YYYY-MM-DD] --csv FILE|-  [--comment "..."] [--dry-run]
  students_grading.py --text "Dang did exercise 1 all right, exercise 2 wrong, autonomy 60%..." [--student ..] [--program ..] [--program-link ..] [--date ..] [--dry-run]
  students_grading.py --header                 print the grid's question labels and expected-answer key
  students_grading.py --check --student S --date D   exit 0 if a row exists for that student and date

CSV columns (header row optional; without one the order is question, expected, correct, autonomy):
  question, expected answer, correct (1/0, yes/no, right/wrong, ✓/✗; empty = not given), autonomy (0-100, "60%" ok; empty = not given)
  optional: n / nr / # / id = the grid label of the question ("1.i", "2. iv)"), used to place it in the right column.
  Without it, the k-th CSV row goes to the k-th question column of the grid.

If a question's expected answer differs from the grid's key row, the result is still written and a cell note
"<question> -> <expected>" is attached to that result cell, so nothing is lost when the programme changes.
"""
import argparse
import csv
import datetime
import io
import os
import re
import sys

sys.path.insert(0, os.path.expanduser('~/.qwen/skills/_freetext-import-lib'))
from intake_common import Sheets, llm_json  # noqa: E402

TAB = 'Students grading'
FIRST_ROW, LAST_ROW = 4, 1001           # student-days: 2 rows each (result row, autonomy row)
COL_DATE, COL_STUDENT, COL_PROG, COL_ITEM0 = 1, 2, 7, 8   # 1-based: A, B, G, H
A1 = f"'{TAB}'!"

TRUE = {'1', 'yes', 'y', 'true', 'right', 'correct', 'ok', '✓', '✔', 'oui', 'vrai', 'juste', 'v'}
FALSE = {'0', 'no', 'n', 'false', 'wrong', 'incorrect', '✗', '✘', 'x', 'non', 'faux'}
BLANK = {'', '-', 'n/a', 'na', 'not given', 'none', 'null', '?'}


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


HEADER_WORDS = {'question', 'q', 'expected', 'expected answer', 'expected_answer', 'answer', 'correct', 'result',
                'autonomy', 'autonomie', 'n', 'nr', 'no', '#', 'id', 'number', 'label'}


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


def extract_via_llm(text, labels, keys, args):
    today = datetime.date.today().isoformat()
    grid = '; '.join(f'{norm_label(l)} (key {k})' for l, k in zip(labels, keys)) or '(no grid header)'
    system = (
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
    data = llm_json(system, text)
    if isinstance(data, list):
        data = {'rows': data}
    rows = []
    for r in data.get('rows') or []:
        rows.append({'n': (str(r['n']) if r.get('n') else None), 'question': r.get('question') or '',
                     'expected': '' if r.get('expected') is None else str(r.get('expected')),
                     'correct': None if r.get('correct') is None else (1 if str(r['correct']).strip().casefold() in TRUE else 0),
                     'autonomy': None if r.get('autonomy') in (None, '') else parse_autonomy(r['autonomy'])})
    return data, rows


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--student')
    ap.add_argument('--program', help='programme name (shown in the Programme cell)')
    ap.add_argument('--program-link', help='URL of the programme document (Google Doc / Drive file)')
    ap.add_argument('--date', help='YYYY-MM-DD (default: today)')
    ap.add_argument('--comment')
    ap.add_argument('--csv', help='CSV file, or - for stdin')
    ap.add_argument('--csv-text', help='CSV content passed inline')
    ap.add_argument('--text', help='free text to structure with the LLM (or - for stdin)')
    ap.add_argument('--header', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    sh = Sheets()
    sid = sh.sheet_id(TAB)
    if sid is None:
        raise SystemExit(f'Tab "{TAB}" not found')
    labels, keys = read_header(sh)

    if a.header:
        print(f'{len(labels)} question columns in "{TAB}":')
        for l, k in zip(labels, keys):
            print(f'  {norm_label(l):>6}  key={k}')
        return

    day = a.date or datetime.date.today().isoformat()
    if a.check:
        if not a.student:
            raise SystemExit('--check needs --student (and optionally --date)')
        row, exists = find_row(sh, a.student, day, a.program or '')
        print(f'row {row}' if exists else 'no entry')
        sys.exit(0 if exists else 1)

    student, program, link, comment = a.student, a.program, a.program_link, a.comment
    if a.text is not None:
        text = sys.stdin.read() if a.text == '-' else a.text
        data, rows = extract_via_llm(text, labels, keys, a)
        student = student or data.get('student')
        program = program or data.get('program')
        link = link or data.get('program_link')
        comment = comment or data.get('comment')
        day = a.date or data.get('date') or day
        print('LLM extraction:', {k: data.get(k) for k in ('student', 'date', 'program', 'program_link', 'comment')}, f'{len(rows)} rows')
    elif a.csv is not None or a.csv_text is not None:
        rows = read_csv_rows(sys.stdin.read() if a.csv == '-' else (open(a.csv, encoding='utf-8').read() if a.csv else a.csv_text))
    else:
        raise SystemExit('Give --csv/--csv-text, --text, --header or --check')
    if not student:
        raise SystemExit('Missing student name (--student, or present in the text)')
    if not program:
        raise SystemExit('Missing programme name (--program, or present in the text)')
    if not rows:
        raise SystemExit('No question rows to write')
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(day)):
        raise SystemExit(f'Bad date {day!r} (use YYYY-MM-DD)')

    # ---- map rows to grid columns
    by_label = {norm_label(l): i for i, l in enumerate(labels)}
    n_cols = len(labels)
    results = [''] * n_cols
    autonomy = [''] * n_cols
    notes = {}      # column index -> note text, only where the key differs from the grid's key row
    seen = set()
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
    answered = [x for x in results if x != '']
    aut_vals = [x for x in autonomy if x != '']

    row, exists = find_row(sh, student, day, program)
    print(f'{"Updating" if exists else "New"} student-day: {student} {day} — rows {row}/{row + 1} — programme "{program}"')
    print(f'  {len(answered)} answered, {sum(answered)} correct'
          + (f' ({sum(answered) / len(answered):.0%})' if answered else '')
          + (f', mean autonomy {sum(aut_vals) / len(aut_vals):.0%}' if aut_vals else ''))
    if notes:
        print(f'  ! {len(notes)} expected answer(s) differ from the grid key row (another programme?) — kept as cell notes')
    if a.dry_run:
        print('  (dry run — nothing written)')
        return

    # ---- write
    last_col = COL_ITEM0 + n_cols - 1
    if not exists:
        sh.put_values(A1 + f'A{row}:B{row}', [[day, student]])
    sh.put_values(A1 + f'{col_letter(COL_ITEM0)}{row}:{col_letter(last_col)}{row}', [results])
    sh.put_values(A1 + f'{col_letter(COL_ITEM0)}{row + 1}:{col_letter(last_col)}{row + 1}', [autonomy])
    reqs = [{'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                        'startColumnIndex': COL_ITEM0 - 1, 'endColumnIndex': last_col},
                             'rows': [{'values': [{} for _ in range(n_cols)]}], 'fields': 'note'}}]   # reset notes on the row
    for i, txt in notes.items():
        reqs.append({'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                               'startColumnIndex': COL_ITEM0 - 1 + i, 'endColumnIndex': COL_ITEM0 + i},
                                    'rows': [{'values': [{'note': txt}]}], 'fields': 'note'}})
    if comment:
        reqs.append({'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                               'startColumnIndex': COL_STUDENT - 1, 'endColumnIndex': COL_STUDENT},
                                    'rows': [{'values': [{'note': comment}]}], 'fields': 'note'}})
    sh.batch(reqs)

    # ---- programme cell (named link / chip) — keep an existing cell that already shows this programme
    cur = sh.get_values(A1 + f'G{row}')
    cur_txt = cur[0][0] if cur and cur[0] else ''
    if cur_txt != program:
        cell = None
        if link:
            try:
                sh.batch([{'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                                     'startColumnIndex': COL_PROG - 1, 'endColumnIndex': COL_PROG},
                                          'rows': [{'values': [chip_cell(program, link)]}], 'fields': 'userEnteredValue,chipRuns'}}])
                cell = 'chip'
            except SystemExit:
                sh.batch([{'updateCells': {'range': {'sheetId': sid, 'startRowIndex': row - 1, 'endRowIndex': row,
                                                     'startColumnIndex': COL_PROG - 1, 'endColumnIndex': COL_PROG},
                                          'rows': [{'values': [link_cell(program, link)]}], 'fields': 'userEnteredValue,textFormatRuns'}}])
                cell = 'link'
        else:
            sh.put_values(A1 + f'G{row}', [[program]])
            cell = 'text'
        print(f'  programme cell: {cell}')
    print('Done.')


if __name__ == '__main__':
    main()
