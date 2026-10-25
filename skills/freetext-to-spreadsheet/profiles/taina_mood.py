"""
Profile: taina-mood — daily mood/sleep observation log about Taïna ("Suivi humeur Taïna" tab of the
"Registre Financier — life/" sheet), kept as a record for a child psychiatrist. NOT a diagnostic tool.

Ported 2026-09-21 from taina-bipolar-disorder-log/scripts/log_entry.py: the numbered-template parser, normalisers and
extraction prompt below are copied verbatim; sheet plumbing / LLM plumbing / CLI now come from the engine.

Accepted input (any of): the numbered form `1. a) 22:00 b) 06:30 c) 8.5 d) Normal 2. a) 15:00 ...` (multi-line or inline),
`*` bullets, the filled-in template with labels, several episodes as `2. i) a) .. b) ..  ii) a) .. b) ..`, --json, or
free text (LLM). Sections: 1 sleep, 2 low episode, 3 high episode, 4 daily 1-5 ratings, 5 notes.
"""
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from intake_engine import Profile, Column  # noqa: E402

COLUMNS = [  # (key, header)
    ('date', 'Date'),
    ('logged_at', 'Enregistré à'),
    ('sleep_start', 'Endormie (heure)'),
    ('sleep_end', 'Réveil (heure)'),
    ('sleep_hours', 'Heures de sommeil'),
    ('wake_energy', 'Énergie au réveil'),
    ('low_start', 'Épisode bas — début'),
    ('low_end', 'Épisode bas — fin'),
    ('low_trigger', 'Épisode bas — déclencheur'),
    ('low_behaviors', 'Épisode bas — comportements'),
    ('high_start', 'Épisode haut — début'),
    ('high_end', 'Épisode haut — fin'),
    ('high_trigger', 'Épisode haut — déclencheur'),
    ('high_behaviors', 'Épisode haut — comportements'),
    ('irritability', 'Irritabilité (1-5)'),
    ('anxiety', 'Anxiété (1-5)'),
    ('focus', 'Concentration (1-5)'),
    ('notes', 'Notes (médicaments, routine, plaintes physiques)'),
]
KEYS = [k for k, _ in COLUMNS]
TIME_KEYS = ['sleep_start', 'sleep_end', 'low_start', 'low_end', 'high_start', 'high_end']
RATING_KEYS = ['irritability', 'anxiety', 'focus']

SECTIONS = {
    1: ['sleep_start', 'sleep_end', 'sleep_hours', 'wake_energy'],
    2: ['low_start', 'low_end', 'low_trigger', 'low_behaviors'],
    3: ['high_start', 'high_end', 'high_trigger', 'high_behaviors'],
    4: ['irritability', 'anxiety', 'focus'],
    5: ['notes'],
}

# label keywords (matched on word boundaries) used when a filled-in template item carries its label
LABELS = {
    'wake_energy': ['energy', 'énergie', 'energie'],
    'sleep_start': ['fell asleep', 'endormi', 'coucher', 'bedtime'],
    'sleep_end': ['woke', 'wake', 'réveil', 'reveil', 'lever'],
    'sleep_hours': ['total hours', 'total', 'heures'],
    'low_start': ['start', 'début', 'debut'],
    'low_end': ['end time', 'end', 'fin'],
    'low_trigger': ['trigger', 'déclencheur', 'declencheur', 'cause'],
    'low_behaviors': ['behavior', 'behaviour', 'comportement'],
    'irritability': ['irritab'],
    'anxiety': ['anxi', 'worry', 'inquiét', 'inquiet'],
    'focus': ['focus', 'concentr', 'attention'],
    'notes': ['notes', 'medication', 'médicament'],
}
LABELS['high_start'], LABELS['high_end'] = LABELS['low_start'], LABELS['low_end']
LABELS['high_trigger'], LABELS['high_behaviors'] = LABELS['low_trigger'], LABELS['low_behaviors']

FR_MONTHS = {'janv': 1, 'jan': 1, 'févr': 2, 'fev': 2, 'fév': 2, 'feb': 2, 'mars': 3, 'mar': 3,
             'avr': 4, 'apr': 4, 'mai': 5, 'may': 5, 'juin': 6, 'jun': 6, 'juil': 7, 'jul': 7,
             'août': 8, 'aout': 8, 'aug': 8, 'sept': 9, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12,
             'dec': 12}
EMPTY_VALUES = {'', '-', '—', '?', 'n/a', 'na', 'none', 'aucun', 'aucune', 'rien', 'nil'}

# ------------------------------------------------------------------ normalization

def parse_date(s):
    s = (s or '').strip().lower()
    m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r'(\d{1,2})[/.](\d{1,2})[/.](\d{4})', s)
    if m:
        return datetime.date(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r'(\d{1,2})\s+([a-zéûô]+)\.?\s+(\d{4})', s)
    if m:
        for prefix, num in sorted(FR_MONTHS.items(), key=lambda kv: -len(kv[0])):
            if m[2].startswith(prefix):
                return datetime.date(int(m[3]), num, int(m[1]))
    return None


def norm_time(s):
    s = (s or '').strip()
    if not s:
        return ''
    t = s.lower()
    m = re.search(r'\b(\d{1,2})\s*[:h]\s*(\d{2})\s*(am|pm)?', t) or re.search(r'\b(\d{1,2})()\s*(am|pm)\b', t)
    if not m and re.fullmatch(r'(\d{1,2})\s*h', t):
        m = re.match(r'(\d{1,2})()()', t)
    if not m:
        return s
    hour, minute, ampm = int(m[1]), int(m[2] or 0), m[3]
    if ampm == 'pm' and hour < 12:
        hour += 12
    if ampm == 'am' and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return s
    return f'{hour:02d}:{minute:02d}'


def _minutes(hhmm):
    h, m = hhmm.split(':')
    return int(h) * 60 + int(m)


def norm_hours(s):
    s = str(s or '').strip()
    if not s:
        return ''
    m = re.search(r'(\d+)\s*[h:]\s*(\d{2})\b', s.lower())  # 8h30 / 8:30 = 8.5 h
    if m:
        return round(int(m[1]) + int(m[2]) / 60, 2)
    m = re.search(r'\d+(?:[.,]\d+)?', s)
    return round(float(m[0].replace(',', '.')), 2) if m else s


def norm_rating(s, warnings, key):
    s = str(s or '').strip()
    if not s:
        return ''
    m = re.search(r'\d+', s)
    if m and 1 <= int(m[0]) <= 5:
        return int(m[0])
    warnings.append(f'{key}: "{s}" is not a 1-5 rating — left empty')
    return ''


def norm_energy(s):
    t = (s or '').strip()
    low = t.lower()
    for word, label in (('sluggish', 'Sluggish'), ('lent', 'Sluggish'), ('fatigu', 'Sluggish'),
                        ('hyper', 'Hyperactive'), ('normal', 'Normal')):
        if low.startswith(word) or low == word:
            return label
    return t


def normalize(fields, warnings):
    out = {k: '' for k in KEYS}
    for k, v in fields.items():
        if k in out and v is not None:
            out[k] = str(v).strip() if not isinstance(v, (int, float)) else v
    for k in TIME_KEYS:
        out[k] = norm_time(out[k])
    out['sleep_hours'] = norm_hours(out['sleep_hours'])
    if out['sleep_hours'] == '' and re.fullmatch(r'\d\d:\d\d', out['sleep_start']) \
            and re.fullmatch(r'\d\d:\d\d', out['sleep_end']):
        out['sleep_hours'] = round(((_minutes(out['sleep_end']) - _minutes(out['sleep_start'])) % 1440) / 60, 2)
        warnings.append('sleep_hours computed from the two times')
    for k in RATING_KEYS:
        out[k] = norm_rating(out[k], warnings, k)
    out['wake_energy'] = norm_energy(out['wake_energy'])
    return out

# ------------------------------------------------------------------ structured parser

def _is_header(line):
    stripped = re.sub(r'\([^)]*\)', '', line).strip()
    letters = re.sub(r'[^A-Za-zÀ-ÿ]', '', stripped)
    return len(letters) >= 4 and stripped == stripped.upper()


def _split_sections(text):
    marker = re.compile(r'(?:^|(?<=\s))(\d{1,2})[.)](?=\s|$)', re.M)
    accepted, last = [], 0
    for m in marker.finditer(text):
        n = int(m[1])
        at_line_start = not text[:m.start()].split('\n')[-1].strip()
        # strictly increasing; a skipped number ("nothing to report" there) must start its line
        if last < n <= 5 and (n == last + 1 or at_line_start):
            accepted.append((n, m.start(), m.end()))
            last = n
    sections = {}
    for i, (n, _, end) in enumerate(accepted):
        stop = accepted[i + 1][1] if i + 1 < len(accepted) else len(text)
        sections[n] = text[end:stop].strip()
    return sections


def _split_items(body):
    """Returns (items, splittable)."""
    lines = body.split('\n')
    if len(lines) > 1 and _is_header(lines[0].strip()):
        body = '\n'.join(lines[1:]).strip()
    letter = re.compile(r'(?:^|(?<=\s))([a-h])[.)](?=\s|$)', re.M)
    accepted, last = [], -1
    for m in letter.finditer(body):
        idx = ord(m[1]) - ord('a')
        if idx > last:  # increasing letters; an omitted letter (e.g. no c) before d)) just leaves that slot empty
            accepted.append((idx, m.start(), m.end()))
            last = idx
    if accepted:
        items = [''] * (last + 1)
        for i, (idx, _, end) in enumerate(accepted):
            stop = accepted[i + 1][1] if i + 1 < len(accepted) else len(body)
            items[idx] = body[end:stop].strip()
        return items, True
    bullet = re.compile(r'^\s*(?:[*\-•·▪◦]|\d+\))\s+(.*)$')
    items = []
    for line in body.split('\n'):
        m = bullet.match(line)
        if m:
            items.append(m[1].strip())
        elif items and line.strip():
            items[-1] += ' ' + line.strip()
    if items:
        return items, True
    return ([body.strip()] if body.strip() else []), False


def _match_label(item, section_keys):
    m = re.match(r'^([^:\n]{2,160}):\s*(.*)$', item, re.S)
    if not m:
        return None, item
    label = m[1].lower()
    for key in section_keys:
        for kw in LABELS.get(key, []):
            if re.search(r'\b' + re.escape(kw), label):
                return key, m[2].strip()
    return None, item


ROMAN = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x']


def _split_episodes(body):
    """`i) ... ii) ... iii) ...` (sequential, lowercase) -> list of episode blocks; None if no i) marker."""
    marker = re.compile(r'(?:^|(?<=\s))(i{1,3}|iv|vi{0,3}|ix|x)[.)](?=\s|$)', re.M)
    accepted = []
    for m in marker.finditer(body):
        if len(accepted) < len(ROMAN) and m[1] == ROMAN[len(accepted)]:
            accepted.append((m.start(), m.end()))
    if not accepted:
        return None
    return [body[end:(accepted[i + 1][0] if i + 1 < len(accepted) else len(body))].strip()
            for i, (_, end) in enumerate(accepted)]


def _parse_block(body, keys, n, warnings):
    """One a)/b)/c)... (or bullet) block -> (fields, splittable)."""
    items, splittable = _split_items(body)
    fields = {}
    if not splittable:
        return fields, False
    for idx, item in enumerate(items):
        key, value = _match_label(item, keys)
        if key is None:
            if idx >= len(keys):
                fields['notes'] = (fields.get('notes', '') + f' | [{n}.{chr(97 + idx)}] {item}').strip(' |')
                warnings.append(f'section {n}: extra item {chr(97 + idx)} moved to notes')
                continue
            key = keys[idx]
        if value.strip().lower() not in EMPTY_VALUES:
            fields[key] = value.strip()
    return fields, True


def build_rows(daily, lows, highs):
    """Sheet rows for one day. Row 1 carries the day-level data (sleep, ratings, notes) plus episode 1 of
    each kind; row k>1 carries the k-th low and/or high episode only."""
    rows = []
    for i in range(max(len(lows), len(highs), 1)):
        row = dict(daily) if i == 0 else {}
        if i < len(lows):
            row.update(lows[i])
        if i < len(highs):
            row.update(highs[i])
        rows.append(row)
    return rows


def _episode_fields(ep, prefix):
    """{'start': .., 'end': .., 'trigger': .., 'behaviors': ..} (or already-prefixed keys) -> prefixed keys."""
    out = {}
    for k, v in (ep or {}).items():
        k = k if k.startswith(prefix + '_') else f'{prefix}_{k}'
        if v not in (None, ''):
            out[k] = v
    return out


def rows_from_dict(d):
    """JSON / LLM dict -> rows. Optional `low_episodes` / `high_episodes` lists of episode dicts."""
    lows = [_episode_fields(e, 'low') for e in d.get('low_episodes') or []]
    highs = [_episode_fields(e, 'high') for e in d.get('high_episodes') or []]
    daily = {k: v for k, v in d.items() if k not in ('low_episodes', 'high_episodes')}
    return build_rows(daily, [e for e in lows if e], [e for e in highs if e])


def parse_structured(text):
    """Returns (rows, warnings, date_or_None, ok). ok=False -> caller should try the LLM.
    Sections 2 and 3 take either one episode (`2. a) .. b) ..`) or several (`2. i) a) .. b) ..  ii) a) .. b) ..`)."""
    warnings = []
    date = None
    m = re.search(r'(?im)^\s*date\s*[:\-]\s*(.*)$', text)
    if m:
        date = parse_date(m[1])
        text = text[:m.start()] + text[m.end():]
    sections = _split_sections(text)
    if not sections:
        return [{}], ['no numbered sections found'], date, False
    daily, lows, highs, ok = {}, [], [], True
    for n, body in sections.items():
        keys = SECTIONS.get(n)
        if not keys:
            warnings.append(f'section {n} ignored (template has 5 sections)')
            continue
        if n == 5:
            items, _ = _split_items(body)
            joined = ' | '.join(i for i in items if i.lower() not in EMPTY_VALUES)
            _, joined = _match_label(joined, ['notes']) if items else (None, joined)
            daily['notes'] = joined
            continue
        blocks = _split_episodes(body) if n in (2, 3) else None
        parsed = []
        for block in (blocks if blocks is not None else [body]):
            fields, splittable = _parse_block(block, keys, n, warnings)
            if not splittable:
                if block.strip():
                    warnings.append(f'section {n}: content not split into a)/b)/c) or bullets')
                    ok = False
                continue
            if fields:
                parsed.append(fields)
        if n == 2:
            lows = parsed
        elif n == 3:
            highs = parsed
        elif parsed:
            daily.update(parsed[0])
    if not (any(daily.values()) or lows or highs):
        ok = False
    return build_rows(daily, lows, highs), warnings, date, ok

EXTRACTION_PROMPT = '''You extract a caregiver's daily mood/sleep observations about a child into JSON, for a log that will be shown to a child psychiatrist.

Return ONLY one JSON object (no markdown fence, no commentary) with exactly these keys, each a string, an integer (ratings) or null when the text does not say:
- date: "YYYY-MM-DD" (today is {today}; resolve "yesterday" etc.)
- sleep_start: time she fell asleep last night, "HH:MM" 24h
- sleep_end: time she woke up, "HH:MM" 24h
- sleep_hours: total hours slept (number)
- wake_energy: "Sluggish" | "Normal" | "Hyperactive" (as observed on waking)
- low_start, low_end: start/end of a depressive/low episode (crying, despondent, withdrawn), "HH:MM" 24h
- low_trigger: what triggered it, or that there was no reason ("none/unprovoked") — only if stated
- low_behaviors: behaviors observed during the low episode, in the caregiver's own words
- high_start, high_end: start/end of a manic/high episode (hyper-energetic, euphoric, very irritable), "HH:MM" 24h
- high_trigger, high_behaviors: same as above for the high episode
- low_episodes / high_episodes: use these arrays INSTEAD of the flat low_*/high_* fields whenever the text describes more than one episode of that kind. Each item is {"start": "HH:MM"|null, "end": "HH:MM"|null, "trigger": string|null, "behaviors": string|null}, in chronological order, keeping every episode's own times, trigger and behaviors separate (never merge two episodes into one field). Never fill both the array and the flat fields for the same kind.
- irritability, anxiety, focus: integers 1-5 (5 = most severe), only if a rating is given
- notes: everything else worth keeping — medication given, routine changes, physical complaints, how the shift between episodes happened (e.g. "crying on the floor to singing and jumping within 10 minutes"), other observations

Rules: never invent or infer a value that the text does not contain; never diagnose, interpret or advise; keep the caregiver's wording for behaviors and notes.'''


# ------------------------------------------------------------------ profile

def _kind(key):
    if key == 'date':
        return 'date'
    if key == 'logged_at':
        return 'datetime'
    return 'time' if key in TIME_KEYS else 'text'


_WIDTH = {'low_trigger': 260, 'low_behaviors': 260, 'high_trigger': 260, 'high_behaviors': 260, 'notes': 320}
_WRAP = set(_WIDTH)


class TainaMood(Profile):
    name = 'taina-mood'
    description = 'Daily mood/sleep observations about Taïna for a child psychiatrist (tab "Suivi humeur Taïna")'
    tab = 'Suivi humeur Taïna'
    columns = [Column(k, h, _kind(k), _WIDTH.get(k), k in _WRAP) for k, h in COLUMNS]
    show_empty_exclude = ('notes',)

    def parse_structured(self, text, ctx):
        rows, warnings, date, ok = parse_structured(text)
        return {'rows': rows, 'warnings': warnings, 'meta': {'date': date}, 'source': 'structured', 'ok': ok}

    def llm_prompt(self, ctx):
        return EXTRACTION_PROMPT.replace('{today}', ctx.today.isoformat())

    def from_llm(self, data, ctx, source='llm'):
        return {'rows': rows_from_dict(data), 'warnings': [], 'meta': {'date': parse_date(str(data.get('date') or ''))},
                'source': source, 'ok': True}

    def finalize(self, parsed, ctx):
        date = parsed['meta'].get('date')
        if ctx.args.date:
            date = parse_date(ctx.args.date)
            if date is None:
                raise SystemExit(f'Unreadable --date: {ctx.args.date}')
        date = date or ctx.today
        logged_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
        finished = []
        for fields in parsed['rows']:
            row_warnings = []
            fields = normalize(fields, row_warnings)
            fields['date'] = date.isoformat()
            fields['logged_at'] = logged_at
            finished.append(fields)
            parsed['warnings'] += row_warnings
        parsed['rows'] = finished
        return parsed

    def check(self, ctx):
        day = (parse_date(ctx.args.date) or ctx.today) if ctx.args.date else ctx.today
        vals = ctx.sheets.get_values(f"'{self.tab}'!A2:A")
        found = day.isoformat() in {r[0].strip() for r in vals if r}
        print(f'{"Entry found" if found else "No entry"} for {day.isoformat()}.')
        return 0 if found else 1


PROFILE = TainaMood()
