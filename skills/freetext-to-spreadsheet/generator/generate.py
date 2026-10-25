#!/usr/bin/env python3
"""
Sheet generator — `intake.py --new-sheet SPEC.toml <command>`  (spec format: generator/SPEC.md)

  --plan          list what would be created / updated / left alone; writes nothing (reads the workbook)
  --verify        compare the spec with the live tab (drift report); the only thing `adopt` ever does to a tab
  --scratch-test  create a throwaway tab from the spec, prove profile + generated Apps Script logic on it, delete it, record a proof marker
  --apply [--only tab,profile,scripts,skill,runbook,life]   generate; refuses without a matching scratch proof when [safety].scratch_test

Path overrides (tests): --skills-dir D, --repo-dir D.   Generated files end with `GENERATED-BODY-HASH: <sha8>`: a file edited by hand, or a
foreign hand-written file, is never overwritten — the new version goes to `<file>.new` and is reported.
Apps Script is NOT deployed here (browser + consent are human steps): the runbook lists them.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'scripts'))
sys.path.insert(0, os.path.expanduser('~/.qwen/skills/_freetext-import-lib'))
from spec_lint import lint  # noqa: E402
import gen_tab  # noqa: E402
import gen_appsscript as gas  # noqa: E402
import gen_artifacts as gar  # noqa: E402
from intake_common import Sheets  # noqa: E402

ONLY = ('tab', 'profile', 'scripts', 'skill', 'runbook', 'life')
MARK = {'py': '# GENERATED-BODY-HASH: {}', 'js': '// GENERATED-BODY-HASH: {}', 'md': '<!-- GENERATED-BODY-HASH: {} -->', 'txt': '# GENERATED-BODY-HASH: {}'}
MARK_RE = re.compile(r'(?:#|//|<!--) GENERATED-BODY-HASH: ([0-9a-f]{8})(?: -->)?\n?$')


def sha8(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()[:8]


# ------------------------------------------------------------------ spec + paths
class Paths:
    def __init__(self, skills_dir=None, repo_dir=None):
        cfg = tomllib.load(open(os.path.join(HERE, 'workbooks.toml'), 'rb'))
        self.wbs = cfg['workbooks']
        self.skills = os.path.expanduser(skills_dir or os.environ.get('INTAKE_SKILLS_DIR') or '~/.qwen/skills')
        self.repo = os.path.expanduser(repo_dir or os.environ.get('INTAKE_REPO_DIR') or cfg.get('paths', {}).get('repo', ''))
        self.scratch = os.path.join(HERE, '.scratch')


def load_spec(path):
    raw = open(path, 'rb').read()
    try:
        spec = tomllib.loads(raw.decode('utf-8'))
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f'{path}: cannot parse — {e}')
    errors, warnings = lint(spec, path)
    if errors:
        raise SystemExit(f'{os.path.basename(path)} has {len(errors)} spec error(s):\n  ' + '\n  '.join(errors))
    return spec, os.path.basename(path), hashlib.sha256(raw).hexdigest()[:8], warnings


# ------------------------------------------------------------------ protected file writes
def with_marker(kind, body):
    body = body.rstrip('\n') + '\n'
    return body + MARK[kind].format(sha8(body)) + '\n'


def file_state(path, new_text):
    if not os.path.exists(path):
        return 'NEW'
    cur = open(path, encoding='utf-8').read()
    m = MARK_RE.search(cur)
    if not m:
        return 'FOREIGN'                       # hand-written file that has no generated marker
    if sha8(cur[:m.start()]) != m.group(1):
        return 'HAND-EDITED'
    return 'UNCHANGED' if cur == new_text else 'UPDATE'


def write_protected(path, kind, body, dry=False):
    text = with_marker(kind, body)
    st = file_state(path, text)
    target = path
    if st in ('FOREIGN', 'HAND-EDITED'):
        target = path + '.new'
    if not dry and st != 'UNCHANGED':
        os.makedirs(os.path.dirname(target), exist_ok=True)
        open(target, 'w', encoding='utf-8').write(text)
    return st, target


# ------------------------------------------------------------------ artifact list
def artifacts(spec, spec_name, h, P, gid):
    sh, pat, lay = spec['sheet'], spec['intake']['pattern'], spec['sheet']['layout']
    sid = sh['id'].replace('-', '_')
    dom = spec['life']['domain']
    ss_id = P.wbs[sh['workbook']]
    out = []
    if lay == 'table':
        out.append(('profile', 'py', os.path.join(P.skills, 'freetext-to-spreadsheet', 'profiles', f'{sid}.py'), lambda: gar.profile_py(spec, spec_name, h)))
        if pat == 'import-trigger':
            out.append(('profile', 'txt', os.path.join(P.skills, 'freetext-to-spreadsheet', 'profiles', f'{sh["id"]}.dsl.txt'), lambda: gar.dsl_doc(spec, spec_name, h)))
            out.append(('scripts', 'js', os.path.join(P.repo, 'life', dom, 'apps-script', f'{sh["id"]}-import.gs'), lambda: gas.import_gs(spec, ss_id, gid, spec_name, h)))
        if pat == 'form-trigger':
            out.append(('scripts', 'js', os.path.join(P.repo, 'life', dom, 'apps-script', f'{sh["id"]}-form.gs'), lambda: gas.form_gs(spec, ss_id, gid, spec_name, h)))
    out.append(('skill', 'md', os.path.join(P.skills, spec['skill'].get('name') or sh['id'], 'SKILL.md'), lambda: gar.skill_md(spec, spec_name, h)))
    if pat in ('form-trigger', 'import-trigger') or (spec.get('appsheet') or {}).get('mode') == 'runbook':
        out.append(('runbook', 'md', os.path.join(P.repo, 'life', dom, f'{sh["id"]}-runbook.md'), lambda: gar.runbook_md(spec, spec_name, h, gid)))
    return out


def live_gid(sh, spec, title=None):
    return sh.sheet_id(title or spec['sheet']['title'])


# ------------------------------------------------------------------ commands
def cmd_verify(spec, P):
    sh = Sheets(P.wbs[spec['sheet']['workbook']])
    if spec['sheet']['layout'] == 'custom':
        print('layout custom: nothing to verify generically (the hand-written profile owns the layout).')
        return 0
    E, I = gen_tab.verify_tab(sh, spec)
    for m in E:
        print('  DRIFT ', m)
    for m in I:
        print('  info  ', m)
    print('verify:', 'FAIL (drift)' if E else 'ok — live header matches the spec')
    return 1 if E else 0


def proof_path(P, spec):
    return os.path.join(P.scratch, spec['sheet']['id'] + '.ok')


def cmd_plan(spec, spec_name, h, P, only):
    sh = Sheets(P.wbs[spec['sheet']['workbook']])
    exists = sh.sheet_id(spec['sheet']['title']) is not None
    mode = spec['sheet']['mode']
    print(f'Plan for {spec["sheet"]["id"]} (mode {mode}, pattern {spec["intake"]["pattern"]}, layout {spec["sheet"]["layout"]}, spec hash {h}):')
    if 'tab' in only and spec['sheet']['layout'] == 'table':
        if mode == 'create':
            print(f'  tab      {"EXISTS — apply verifies the header, never recreates" if exists else "CREATE"}  "{spec["sheet"]["title"]}"')
        else:
            print(f'  tab      {"VERIFY ONLY" if exists else "MISSING — adopt needs an existing tab"}  "{spec["sheet"]["title"]}"')
    for what, kind, path, render in artifacts(spec, spec_name, h, P, live_gid(sh, spec) or 0):
        if what not in only:
            continue
        st = file_state(path, with_marker(kind, render()))
        extra = {'FOREIGN': ' (hand-written file exists → new version goes to .new)', 'HAND-EDITED': ' (edited by hand → new version goes to .new)'}.get(st, '')
        print(f'  {what:<8} {st:<11} {path}{extra}')
    if 'life' in only:
        print(f'  life     LOG         life/{spec["life"]["domain"]}/events/ (+ open loop: {spec["life"].get("open_loop", "none")})')
    proof = proof_path(P, spec)
    ok = os.path.isfile(proof) and open(proof).read().strip() == h
    print(f'  scratch proof: {"present for this spec hash" if ok else "MISSING — run --scratch-test before --apply"}')
    return 0


# ---- scratch test
NODE_HARNESS = r'''
const fs = require('fs'), vm = require('vm');
const [file, testsJson] = process.argv.slice(2);
const T = JSON.parse(testsJson);
const ctx = { console, Logger: { log() {} }, Utilities: { formatDate: d => d.toISOString().slice(0, 10) } };
vm.createContext(ctx); vm.runInContext(fs.readFileSync(file, 'utf8'), ctx);
const out = [];
const isDate = v => Object.prototype.toString.call(v) === '[object Date]';   // realm-independent (values come from the vm sandbox)
const t = (name, cond, detail) => out.push([name, !!cond, detail || '']);
const run = e => vm.runInContext(e, ctx);
try {
  ctx.__cfg = run('CFG');
  if (T.kind === 'import') {
    const cfg = ctx.__cfg, heads = T.dslHeads;
    let r = run('parseImportText_(CFG.sampleDsl, CFG, null)');
    t('sample DSL parses to 1 record, no warnings', r.records.length === 1 && r.warnings.length === 0, JSON.stringify(r.warnings));
    t('processed line gets a checkmark', /✅\s*$/m.test(r.annotated));
    ctx.__t = 'x';
    r = run('parseImportText_(CFG.sampleDsl.replace(/\\n([^\\n]*)$/, "\\n$1 ✅"), CFG, null)');
    t('a line already marked with a checkmark is skipped', r.records.length === 0);
    r = run('parseImportText_(CFG.sampleDsl.replace(/\\n/, "\\n").replace(/(\\n[^\\n]*\\n)/, "$1"), CFG, null)');
    const lines = cfg.sampleDsl.split('\n');
    const withBad = lines[0] + '\n' + lines[1] + ', Zzz\n' + lines[2] + ', whatever';
    ctx.__d = withBad; r = run('parseImportText_(__d, CFG, null)');
    t('unknown column -> warning, row still added', r.warnings.some(w => /zzz/i.test(w)) && r.records.length === 1, JSON.stringify(r.warnings));
    if (T.lastTextHead) {
      ctx.__d = lines[0] + '\n' + T.dslHeads.join(', ') + '\n' + T.dslHeads.map((h, i) => i === T.dslHeads.length - 1 ? 'alpha, beta, gamma' : T.sampleVals[i]).join(', ');
      r = run('parseImportText_(__d, CFG, null)');
      t('last column absorbs extra commas', r.records[0] && r.records[0].values[T.lastTextKey] === 'alpha, beta, gamma', JSON.stringify(r.records[0] && r.records[0].values));
    }
    if (T.dateKey) {
      r = run('parseImportText_(CFG.sampleDsl, CFG, null)');
      const dv = r.records[0].values[T.dateKey];
      t('block date fills the date column', isDate(dv) && dv.getFullYear() === 2026 && dv.getMonth() === 0 && dv.getDate() === 2, String(dv));
    }
    if (T.requiredHeader) {
      ctx.__d = '## 2 janv 2026\n' + T.dslHeadsWithoutRequired.join(', ') + '\n' + T.dslValsWithoutRequired.join(', ');
      r = run('parseImportText_(__d, CFG, null)');
      t('missing required value -> warning, row still added', r.warnings.length >= 1 && r.records.length === 1, JSON.stringify(r.warnings));
    }
    if (T.choiceKey) {
      ctx.__d = '## 2 janv 2026\n' + T.choiceHead + '\n' + 'not-a-choice';
      r = run('parseImportText_(__d, CFG, null)');
      t('value outside the allowed list -> warning, kept', r.warnings.length >= 1 && r.records.length === 1, JSON.stringify(r.warnings));
    }
  } else {
    const today = new Date(2026, 0, 2), now = new Date(2026, 0, 2, 9, 30);
    ctx.__a = T.answers; ctx.__today = today; ctx.__now = now;
    let r = run('answersToValues_(__a, CFG, __today, __now)');
    for (const [k, exp] of Object.entries(T.expect)) {
      const v = r.values[k];
      const same = exp === '__DATE__' ? (isDate(v) && v.getFullYear() === 2026) : (typeof exp === 'number' ? Math.abs(v - exp) < 1e-9 : v === exp);
      t('answer -> ' + k + ' = ' + JSON.stringify(exp), same, JSON.stringify(v));
    }
    ctx.__a = {}; r = run('answersToValues_(__a, CFG, __today, __now)');
    if (T.defaultDateKey) t('empty date -> default today', isDate(r.values[T.defaultDateKey]));
    t('empty answers give no crash and no warnings', true);
  }
} catch (e) { t('harness ran without exception', false, String(e && e.stack || e)); }
console.log(JSON.stringify(out));
'''


def _find_node():
    n = shutil.which('node')
    if n:
        return n
    for cand in (os.path.expanduser('~/.config/nvm/versions/node'),):
        if os.path.isdir(cand):
            for v in sorted(os.listdir(cand), reverse=True):
                p = os.path.join(cand, v, 'bin', 'node')
                if os.path.isfile(p):
                    return p
    return None


def _sample_row(spec):
    row = {}
    for c in spec['columns']:
        if c['type'] == 'formula' or c.get('choices_from') and not c.get('required'):
            continue
        row[c['key']] = gas._sample(c)
    return row


def _expected_display(c, v):
    t = c['type']
    if t == 'percent':
        return f'{int(float(v))}%'
    if t == 'boolean':
        return '1'
    if t in ('integer', 'number'):
        return str(int(float(v))) if float(v) == int(float(v)) else str(float(v))
    return v


def cmd_scratch_test(spec, spec_name, h, P):
    if spec['sheet']['layout'] == 'custom':
        raise SystemExit('scratch-test covers layout "table"; a custom sheet keeps its own hand-written tests.')
    import table_profile as tp
    import intake_engine as eng
    import argparse as ap_
    sh = Sheets(P.wbs[spec['sheet']['workbook']])
    ss_id = P.wbs[spec['sheet']['workbook']]
    pat, sid = spec['intake']['pattern'], spec['sheet']['id']
    tmp, tmp_imp = f'__gentest_{sid}__'[:99], f'__gentest_{sid}_import__'[:99]
    results, made = [], []
    T = lambda name, ok, detail='': (results.append((name, bool(ok), detail)), print(f'  {"PASS" if ok else "FAIL"}  {name}' + (f'   [{detail}]' if detail and not ok else '')))
    print(f'Scratch test for {sid} (pattern {pat}) on throwaway tab "{tmp}":')
    try:
        for t_ in (tmp, tmp_imp):
            if sh.sheet_id(t_) is not None:
                raise SystemExit(f'Leftover scratch tab "{t_}" exists — delete it first.')
        gid = gen_tab.create_tab(sh, spec, tmp)
        made.append(gid)
        E, I = gen_tab.verify_tab(sh, spec, tmp)
        T('tab created from the spec; header equals the spec', not E, '; '.join(E))
        spec2 = copy.deepcopy(spec)
        spec2['sheet']['title'] = tmp
        cols = spec['columns']
        # ---- profile round-trip (direct + form-trigger use TableProfile; import-trigger checks the DSL side)
        if pat in ('direct', 'form-trigger'):
            prof = tp.TableProfile(spec2)
            row = _sample_row(spec)
            ns = ap_.Namespace(text=None, file=None, json_in=json.dumps({'rows': [row]}), date=None, init=False, check=False, dry_run=False, no_llm=False, llm=False, csv=None, csv_text=None)
            import contextlib, io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                eng.run(prof, ns)
            got = (sh.get_values(f"'{tmp}'!A2:{gen_tab.col_letter(len(cols))}2") or [[]])[0]
            got = list(got) + [''] * (len(cols) - len(got))
            bad = []
            for i, c in enumerate(cols):
                if c['key'] in row and c['type'] not in ('formula',):
                    exp = _expected_display(c, row[c['key']])
                    if str(got[i]) != exp:
                        bad.append(f'{c["header"]}: got {got[i]!r} expected {exp!r}')
            T('--json row written and every typed cell reads back as expected', not bad, '; '.join(bad))
            fcols = [(i, c) for i, c in enumerate(cols) if c['type'] == 'formula']
            if fcols:
                fv = sh.get_values(f"'{tmp}'!A2:{gen_tab.col_letter(len(cols))}2", 'FORMULA')[0]
                T('formula columns written per row', all(len(fv) > i and str(fv[i]).startswith('=') for i, _ in fcols))
            if spec['sheet'].get('upsert_on'):
                keyrow = {k: row[k] for k in spec['sheet']['upsert_on'] if k in row}
                edit = next((c for c in cols if c['type'] in ('text', 'longtext') and c['key'] not in keyrow and c['type'] != 'formula'), None)
                if edit:
                    r2 = dict(row); r2[edit['key']] = 'TEST UPDATED'
                    ns.json_in = json.dumps({'rows': [r2]})
                    with contextlib.redirect_stdout(buf):
                        eng.run(prof, ns)
                    allv = sh.get_values(f"'{tmp}'!A:A")
                    upd = sh.get_values(f"'{tmp}'!{gen_tab.col_letter(cols.index(edit) + 1)}2")
                    T('upsert: a second run updates the same row (no duplicate)', len(allv) == 2 and upd and upd[0][0] == 'TEST UPDATED', f'rows={len(allv)}')
            req = [c for c in cols if c.get('required') and c['type'] != 'formula' and 'default' not in c]   # a default legitimately fills a missing value
            if req:
                miss = {k: v for k, v in row.items() if k != req[0]['key']}
                ns.json_in = json.dumps({'rows': [miss]}); ns.dry_run = True
                try:
                    with contextlib.redirect_stdout(buf):
                        eng.run(prof, ns)
                    T('missing required value stops and asks', False, 'no error raised')
                except SystemExit as e:
                    T('missing required value stops and asks', 'required' in str(e).lower(), str(e))
            num = next((c for c in cols if c['type'] in ('integer', 'number') and ('max' in c)), None)
            if num:
                badrow = dict(row); badrow[num['key']] = str(num['max'] + 1000)
                ns.json_in = json.dumps({'rows': [badrow]}); ns.dry_run = True
                w = io.StringIO()
                with contextlib.redirect_stdout(w):
                    eng.run(prof, ns)
                T('out-of-range number -> warning, left empty', 'outside' in w.getvalue())
            ns.json_in = None; ns.csv_text = ','.join(c['header'] for c in cols if c['key'] in row) + '\n' + ','.join(str(row[c['key']]) for c in cols if c['key'] in row); ns.dry_run = True
            w = io.StringIO()
            with contextlib.redirect_stdout(w):
                eng.run(prof, ns)
            T('--csv-text input parses through headers', 'Parsed (csv)' in w.getvalue())
        else:
            dsl = gar.dsl_doc(spec, spec_name, h)
            keymap = {c['key']: c for c in cols}
            T('DSL prompt names every DSL column', all(keymap[k]['header'] in dsl for k in spec['intake']['import']['dsl_columns']))
            T('DSL prompt carries the never-invent rule', 'invent' in dsl.lower() or 'invente' in dsl.lower())
            # profile side: append a pre-processed row to a throwaway Import tab and poll it
            sh.batch([{'addSheet': {'properties': {'title': tmp_imp}}}])
            made.append(sh.sheet_id(tmp_imp))
            sh.put_values(f"'{tmp_imp}'!A1:D1", [['Horodatage', 'Texte', 'Statut', 'Résultat']])
            import importlib.util
            spec_p = importlib.util.spec_from_file_location('gen_p', os.path.join(HERE, '..', 'profiles', '_import_trigger.py'))
            mod = importlib.util.module_from_spec(spec_p); spec_p.loader.exec_module(mod)
            prof = mod.ImportTriggerProfile()
            prof.import_tab, prof.initial_status, prof.initial_result, prof.name = tmp_imp, 'Traité', 'scratch', sid
            ns = ap_.Namespace(text=None, file=None, json_in=None, date=None, init=False, check=False, dry_run=False, no_llm=False, llm=False, dsl=gas.sample_dsl(spec), no_wait=False)
            import contextlib, io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                eng.run(prof, ns)
            T('profile appends a DSL row to the Import tab and reads its status back', 'Statut : Traité' in buf.getvalue())
        # ---- generated Apps Script: syntax + logic under node
        node = _find_node()
        if pat in ('form-trigger', 'import-trigger') and node:
            js = (gas.import_gs if pat == 'import-trigger' else gas.form_gs)(spec, ss_id, gid, spec_name, h)
            f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
            f.write(js); f.close()
            r = subprocess.run([node, '--check', f.name], capture_output=True, text=True)
            T('generated Apps Script passes node --check', r.returncode == 0, r.stderr[:300])
            decl = [l for l in js.split('\n') if l.startswith('function ')]
            T('only `main` is a top-level function declaration', decl == ['function main() {'], str(decl))
            tests = _js_tests(spec, pat)
            hp = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
            hp.write(NODE_HARNESS); hp.close()
            r = subprocess.run([node, hp.name, f.name, json.dumps(tests)], capture_output=True, text=True)
            os.unlink(hp.name)
            try:
                for name, ok, detail in json.loads(r.stdout.strip().splitlines()[-1]):
                    T('JS: ' + name, ok, detail)
            except (ValueError, IndexError):
                T('JS unit tests ran', False, (r.stderr or r.stdout)[:400])
            os.unlink(f.name)
        elif pat in ('form-trigger', 'import-trigger'):
            print('  (node not found: generated JS not executed)')
    finally:
        for g in made:
            try:
                sh.batch([{'deleteSheet': {'sheetId': g}}])
            except SystemExit:
                pass
        print('  throwaway tab(s) deleted.')
    ok = bool(results) and all(r[1] for r in results)
    if ok:
        os.makedirs(P.scratch, exist_ok=True)
        open(proof_path(P, spec), 'w').write(h + '\n')
    print(f'scratch-test: {"PASS" if ok else "FAIL"} ({sum(r[1] for r in results)}/{len(results)})' + (' — proof recorded' if ok else ''))
    return 0 if ok else 1


def _js_tests(spec, pat):
    cols = spec['columns']
    keymap = {c['key']: c for c in cols}
    if pat == 'import-trigger':
        imp = spec['intake']['import']
        dk = imp['dsl_columns']
        heads = [keymap[k]['header'] for k in dk]
        vals = [gas._sample(keymap[k]) for k in dk]
        last = keymap[dk[-1]]
        t = {'kind': 'import', 'dslHeads': heads, 'sampleVals': vals}
        if last['type'] in ('text', 'longtext'):
            t.update(lastTextHead=True, lastTextKey=dk[-1])
        d = next((c for c in cols if c['type'] == 'date'), None)
        if d:
            t['dateKey'] = d['key']
        req = next((c for c in cols if c.get('required') and c['type'] not in ('formula', 'date') and c['key'] in dk), None)
        if req and len(dk) > 1:
            keep = [k for k in dk if k != req['key']]
            t.update(requiredHeader=req['header'], dslHeadsWithoutRequired=[keymap[k]['header'] for k in keep], dslValsWithoutRequired=[gas._sample(keymap[k]) for k in keep])
        ch = next((c for c in cols if c['type'] == 'choice' and c.get('choices') and c['key'] in dk), None)
        if ch:
            t.update(choiceKey=ch['key'], choiceHead=ch['header'])
        return t
    answers, expect = {}, {}
    for c in cols:
        if c['type'] == 'formula':
            continue
        s = gas._sample(c)
        answers[c['header']] = {'boolean': 'Yes'}.get(c['type'], s)
        if c['type'] == 'boolean':
            expect[c['key']] = 1
        elif c['type'] in ('integer', 'number'):
            expect[c['key']] = float(s)
        elif c['type'] == 'percent':
            expect[c['key']] = float(s) / 100
        elif c['type'] in ('text', 'longtext', 'link', 'choice'):
            expect[c['key']] = s
        elif c['type'] == 'date':
            expect[c['key']] = '__DATE__'
    dd = next((c['key'] for c in cols if c['type'] == 'date' and c.get('default') == 'today'), None)
    return {'kind': 'form', 'answers': answers, 'expect': expect, 'defaultDateKey': dd}


# ---- apply
def cmd_apply(spec, spec_name, h, P, only, force_no_proof=False):
    sh = Sheets(P.wbs[spec['sheet']['workbook']])
    mode, lay = spec['sheet']['mode'], spec['sheet']['layout']
    if (spec.get('safety') or {}).get('scratch_test') and lay == 'table' and not force_no_proof:
        proof = proof_path(P, spec)
        if not (os.path.isfile(proof) and open(proof).read().strip() == h):
            raise SystemExit('Refusing to apply: no scratch-test proof for this spec hash. Run --scratch-test first ([safety].scratch_test = true).')
    done = []
    gid = None
    if 'tab' in only and lay == 'table':
        if mode == 'create' and sh.sheet_id(spec['sheet']['title']) is None:
            gid = gen_tab.create_tab(sh, spec)
            done.append(f'tab "{spec["sheet"]["title"]}" created (gid {gid})')
        else:                                    # adopt, or create re-run: the tab exists -> verify only (never recreate / restructure)
            E, I = gen_tab.verify_tab(sh, spec)
            if E:
                raise SystemExit('Refusing to apply: the live tab drifted from the spec (adopt never restructures):\n  ' + '\n  '.join(E))
            gid = live_gid(sh, spec)
            done.append(f'tab "{spec["sheet"]["title"]}" verified ({mode}, gid {gid})')
    gid = gid or live_gid(sh, spec) or 0
    if lay == 'table' and not gid and ({'scripts', 'runbook'} & only):
        raise SystemExit(f'Refusing to generate Apps Script/runbook: tab "{spec["sheet"]["title"]}" does not exist yet, so its gid is unknown. Apply with the tab first (--only tab, or no --only).')
    for what, kind, path, render in artifacts(spec, spec_name, h, P, gid):
        if what not in only:
            continue
        st, target = write_protected(path, kind, render())
        done.append(f'{what}: {st} → {target}')
    if 'life' in only:
        done += log_life(spec, spec_name, h, P, list(done))
    for d in done:
        print(' ', d)
    print('Next (human/browser steps, see the runbook): deploy the Apps Script (authorize), and AppSheet if requested.' if spec['intake']['pattern'] != 'direct' else 'Done.')
    return 0


def log_life(spec, spec_name, h, P, arts):
    out = []
    if not P.repo or not os.path.isdir(P.repo):
        return ['life: skipped (repo dir not found)']
    now = datetime.datetime.now()
    event, code = gar.life_event(spec, spec_name, h, [a for a in arts if not a.startswith('life')], now)
    ev_path = os.path.join(P.repo, 'life', spec['life']['domain'], 'events', f'{now:%Y-%m}.md')
    os.makedirs(os.path.dirname(ev_path), exist_ok=True)
    head = f'# {code} — {now:%Y-%m}\n\n'
    cur = open(ev_path, encoding='utf-8').read() if os.path.exists(ev_path) else head
    if not cur.startswith('# '):
        cur = head + cur
    first_nl = cur.index('\n\n') + 2 if '\n\n' in cur else len(cur)
    if spec['sheet']['id'] in cur and f'Sheet generated — {spec["sheet"]["title"]}' in cur and h in cur:
        out.append('life: event already logged for this spec hash')
    else:
        open(ev_path, 'w', encoding='utf-8').write(cur[:first_nl] + event + '\n' + cur[first_nl:])
        out.append(f'life: event logged in {os.path.relpath(ev_path, P.repo)}')
    row = gar.open_loop_row(spec, code, now.date())
    if row:
        ol = os.path.join(P.repo, 'life', '00-meta', 'open-loops.md')
        if os.path.exists(ol):
            t = open(ol, encoding='utf-8').read()
            if f'/{spec["skill"].get("name") or spec["sheet"]["id"]}`' not in t:
                if 'Last synced:' in t:
                    t = t.replace('Last synced:', row + '\nLast synced:', 1)
                    t = re.sub(r'Last synced: [\d-]+\.', f'Last synced: {now:%Y-%m-%d}.', t)
                    open(ol, 'w', encoding='utf-8').write(t)
                    out.append('life: open loop added to 00-meta/open-loops.md')
                    push = os.path.join(P.repo, 'pm', 'scripts', 'push-to-drive.sh')
                    if os.path.isfile(push):
                        subprocess.run(['bash', push, 'life', '00-meta/open-loops.md'], cwd=P.repo, capture_output=True)
                        out.append('life: open-loops.md pushed to Drive')
            else:
                out.append('life: open loop already present')
    return out


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog='intake.py --new-sheet', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('spec')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--plan', action='store_true')
    g.add_argument('--verify', action='store_true')
    g.add_argument('--scratch-test', action='store_true')
    g.add_argument('--apply', action='store_true')
    ap.add_argument('--only', help='comma list of: ' + ','.join(ONLY))
    ap.add_argument('--skills-dir')
    ap.add_argument('--repo-dir')
    a = ap.parse_args(argv)
    spec, name, h, warns = load_spec(a.spec)
    for w in warns:
        print('  warn ', w)
    P = Paths(a.skills_dir, a.repo_dir)
    # adopt: the sheet, its Apps Script and its AppSheet already exist -> by default only verify the tab and generate profile/skill/life;
    # scripts and runbook are opt-in via --only
    default = set(ONLY) - ({'scripts', 'runbook'} if spec['sheet']['mode'] == 'adopt' else set())
    only = set(a.only.split(',')) if a.only else default
    bad = only - set(ONLY)
    if bad:
        raise SystemExit(f'--only: unknown {sorted(bad)}')
    if a.plan:
        return cmd_plan(spec, name, h, P, only)
    if a.verify:
        return cmd_verify(spec, P)
    if a.scratch_test:
        return cmd_scratch_test(spec, name, h, P)
    return cmd_apply(spec, name, h, P, only)


if __name__ == '__main__':
    sys.exit(main())
