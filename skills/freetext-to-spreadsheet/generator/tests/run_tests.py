#!/usr/bin/env python3
"""
Regression suite of the sheet generator.   python3 generator/tests/run_tests.py [--offline]

  1. coercion unit tests (table_profile.coerce) ............ offline
  2. spec lint: examples/tests specs ok + injected errors caught ... offline
  3. --verify on the adopted real sheets (taina-mood, jm-livraison) ... online, read-only
  4. --scratch-test on the three test specs (direct / form-trigger / import-trigger) ... online, creates and deletes throwaway tabs
Test proofs it records in generator/.scratch are removed at the end (they are not real proofs of anything but the test specs).
"""
import copy
import datetime
import glob
import os
import subprocess
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.dirname(HERE)
ROOT = os.path.dirname(GEN)
sys.path.insert(0, GEN)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from spec_lint import lint  # noqa: E402
from table_profile import coerce  # noqa: E402

fails = []


def check(name, ok, detail=''):
    print(f'  {"PASS" if ok else "FAIL"}  {name}' + (f'   [{detail}]' if detail and not ok else ''))
    if not ok:
        fails.append(name)


def unit():
    print('1. coercions')
    T, N = datetime.date(2026, 9, 21), datetime.datetime(2026, 9, 21, 18, 30)
    cases = [('date', 'hier', {}, '2026-09-20', 0), ('date', '1 sept 2026', {}, '2026-09-01', 0), ('date', '21/09/2026', {}, '2026-09-21', 0), ('date', 'banana', {}, '', 1),
             ('time', '8h30', {}, '08:30', 0), ('time', '7:15 pm', {}, '19:15', 0), ('time', '25:99', {}, '', 1),
             ('integer', '3', {'min': 1, 'max': 5}, 3, 0), ('integer', '4,5', {'min': 1, 'max': 5}, '', 1), ('integer', '9', {'min': 1, 'max': 5}, '', 1),
             ('number', '12,5 kg', {}, 12.5, 0), ('percent', '60%', {}, 0.6, 0), ('percent', '150', {'min': 0, 'max': 100}, '', 1),
             ('boolean', 'oui', {}, 1, 0), ('boolean', 'non', {}, 0, 0), ('boolean', 'peut-être', {}, '', 1),
             ('choice', 'normal', {'choices': ['Sluggish', 'Normal']}, 'Normal', 0), ('choice', 'Zzz', {'choices': ['A']}, 'Zzz', 1),
             ('datetime', 'now', {}, '2026-09-21 18:30', 0), ('text', '  hello ', {}, 'hello', 0), ('text', 'n/a', {}, '', 0)]
    for t, v, kw, exp, nw in cases:
        w = []
        r = coerce({'type': t, 'header': 'H', **kw}, v, w, T, N)
        check(f'{t} {v!r}', r == exp and (len(w) >= 1 if nw else not w), f'{r!r} {w}')


def lint_tests():
    print('2. spec lint')
    for p in sorted(glob.glob(os.path.join(GEN, 'examples', '*.spec.toml')) + glob.glob(os.path.join(HERE, 'specs', '*.spec.toml'))):
        E, W = lint(tomllib.load(open(p, 'rb')), p)
        check(f'{os.path.basename(p)} lints clean', not E, '; '.join(E))
    base = tomllib.load(open(os.path.join(GEN, 'examples', 'taina-mood.spec.toml'), 'rb'))
    mutations = {
        'kebab id': lambda s: s['sheet'].update(id='Bad_Id'),
        'duplicate key': lambda s: s['columns'].append(dict(s['columns'][0])),
        'choice without choices': lambda s: s['columns'][5].pop('choices'),
        'min > max': lambda s: s['columns'][14].update(min=9, max=2),
        'form channel on direct pattern': lambda s: s['channels'].update(form=True),
        'fewer than 3 triggers': lambda s: s['skill'].update(triggers=['one']),
        'never_invent off': lambda s: s['safety'].update(never_invent=False),
        'unknown pattern': lambda s: s['intake'].update(pattern='magic'),
        'adopt without keep_existing_layout': lambda s: s['safety'].update(keep_existing_layout=False),
    }
    for name, mut in mutations.items():
        s = copy.deepcopy(base)
        mut(s)
        E, _ = lint(s)
        check(f'lint catches: {name}', bool(E))


def run(args, timeout=600):
    return subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'intake.py')] + args, capture_output=True, text=True, timeout=timeout)


def online():
    print('3. --verify on adopted real sheets (read-only)')
    for n in ('taina-mood', 'jm-livraison'):
        r = run(['--new-sheet', os.path.join(GEN, 'examples', n + '.spec.toml'), '--verify'])
        check(f'verify {n}', r.returncode == 0, r.stdout[-300:] + r.stderr[-200:])
    print('4. scratch tests (throwaway tabs)')
    for n in ('gentest-direct', 'gentest-form', 'gentest-import'):
        r = run(['--new-sheet', os.path.join(HERE, 'specs', n + '.spec.toml'), '--scratch-test'])
        last = [l for l in r.stdout.strip().splitlines() if l.startswith('scratch-test')]
        check(f'scratch-test {n}: {last[-1] if last else r.stderr[-200:]}', r.returncode == 0)
    for p in glob.glob(os.path.join(GEN, '.scratch', 'gentest*')):
        os.remove(p)


if __name__ == '__main__':
    unit()
    lint_tests()
    if '--offline' not in sys.argv:
        online()
    print(f'\n{"ALL PASSED" if not fails else str(len(fails)) + " FAILED: " + ", ".join(fails)}')
    sys.exit(1 if fails else 0)
