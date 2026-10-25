#!/usr/bin/env python3
"""Extract the real map of a Nuxt-style app, as raw material for the Treeview and the
module technical analyses (devtask-docs-tree skill, step 1).

Usage:  python3 extract_app_map.py <app-repo-root> [> map.txt]

Prints: pages (+ header doc comment, components, calls), FE API functions (method, route,
callers), server routes (guard -> service), services (events, repos, header doc), error codes
per file, tables per schema file, test names. Assumes the layout used by the MANSA platform:
app/pages, app/features/*/api/*.api.ts (an exported object of methods calling apiFetch()),
server/api, server/services, server/database/schema (Drizzle sqliteTable/pgTable).
Adapt the globs for another stack — the method (code first, then prose) stays the same.
Callers are found by searching `<apiObject>.<fn>(` — NOT a bare `.fn(`, which gives false
positives (e.g. every `.get(` in the app).
"""
import glob, os, re, subprocess, sys

root = sys.argv[1] if len(sys.argv) > 1 else '.'
os.chdir(root)

def doc(s, n=420):
    m = re.search(r'/\*\*(.*?)\*/', s, re.S)
    return ' '.join(m.group(1).replace('*', ' ').split())[:n] if m else ''

print('# PAGES')
for f in sorted(glob.glob('app/pages/**/*.vue', recursive=True)):
    s = open(f, encoding='utf-8').read()
    tpl = s.split('<template>', 1)[1] if '<template>' in s else ''
    comps = sorted(set(re.findall(r'<([A-Z]\w+)', tpl)))
    calls = sorted(set(re.findall(r'\b(\w+Api\.\w+|use[A-Z]\w+)\(', s)))
    print(f'== {f[len("app/pages"):]}\n   doc: {doc(s)}\n   comps: {", ".join(comps)}\n   calls: {", ".join(calls)}')

print('\n# FE API FUNCTIONS (method route <- callers)')
for f in sorted(glob.glob('app/features/*/api/*.ts')):
    s = open(f, encoding='utf-8').read()
    obj = re.search(r'export const (\w+)\s*=', s)
    name = obj.group(1) if obj else '?'
    print(f'== {f} ({name})')
    for m in re.finditer(r'\n  (\w+)\(([^)]*)\)[^{]*\{(.*?)\n  \},', s, re.S):
        fn, body = m.group(1), m.group(3)
        url = re.search(r"\(\s*[`'\"]([^`'\"]+)[`'\"]", body)
        meth = re.search(r"method:\s*'(\w+)'", body)
        out = subprocess.run(['grep', '-rln', f'{name}\\.{fn}(', 'app', '--include=*.vue', '--include=*.ts'],
                             capture_output=True, text=True).stdout.split()
        callers = [c[4:] for c in out if '/api/' not in c]
        print(f'   {fn}: {meth.group(1) if meth else "?"} {url.group(1) if url else "?"}  <- {", ".join(callers) or "(none found)"}')

print('\n# SERVER ROUTES (guard -> service)')
for f in sorted(glob.glob('server/api/**/*.ts', recursive=True)):
    s = open(f, encoding='utf-8').read()
    svc = re.findall(r"import \{([^}]+)\} from '[./]+services/([\w/]+)'", s)
    guard = ('admin' if 'requireAdmin' in s else 'user' if 'requireUser' in s
             else 'optional' if 'optionalUser' in s else 'public')
    print(f"   {f[len('server/api'):-3]:55} [{guard}] -> " + '; '.join(f'{p}:{n.strip()}' for n, p in svc))

print('\n# SERVICES (events | repos | doc)')
for f in sorted(glob.glob('server/services/**/*.ts', recursive=True)):
    s = open(f, encoding='utf-8').read()
    ev = sorted(set(re.findall(r"bus\.emit\('(\w+)'", s)))
    repos = sorted(set(re.findall(r'create(\w+Repo)\b', s)))
    print(f"== {f[len('server/services/'):]} | events: {','.join(ev) or '-'} | repos: {','.join(repos) or '-'}\n   doc: {doc(s, 600)}")

print('\n# ERROR CODES (AppError code(status))')
for f in sorted(glob.glob('server/**/*.ts', recursive=True)):
    s = open(f, encoding='utf-8').read()
    codes = sorted(set(re.findall(r"AppError\(\s*'([a-z_]+)'(?:[^)]*?,\s*(\d{3}))?", s)))
    if codes:
        print(f'   {f}: ' + ' '.join(f'{c}({st})' if st else c for c, st in codes))

print('\n# TABLES (per schema file)')
for f in sorted(glob.glob('server/database/schema/*.ts')):
    s = open(f, encoding='utf-8').read().replace('\n', ' ')
    t = re.findall(r"(?:sqlite|pg)Table\(\s*'([a-z_]+)'", s)
    if t: print(f'   {os.path.basename(f)[:-3]}: {" ".join(t)}')

print('\n# EVENT SUBSCRIBERS')
print(subprocess.run(['grep', '-rn', r"bus.on('\|\.on('", 'server', '--include=*.ts'], capture_output=True, text=True).stdout)

print('# TESTS')
for d in ['tests/unit', *sorted(glob.glob('tests/components/*'))]:
    if os.path.isdir(d):
        names = sorted(n[:-8] for n in os.listdir(d) if n.endswith('.test.ts'))
        print(f'   {d}: {" ".join(names)}')
