#!/usr/bin/env python3
"""Check the documentation tree of a bundle (devtask-docs-tree skill, verification step).

Usage:  python3 check_docs.py <bundle-dir> <bundle-path-as-written-in-headers>
  e.g.  python3 check_docs.py pm/tasks/analysis-α-implementation/mansa-ai-trainings-offer \
                              ./pm/tasks/analysis-α-implementation/mansa-ai-trainings-offer

Checks, for every .md under 00. Documentation/ and 00. Architecture/:
- the <thisfile path="..."> equals the file's own path;
- sibling/parent/related targets exist;
- the "-- <basename> --" banner is the file's basename and its "=" underline has the same length;
and that every [..](<..>) link of 00. Documentation/00. Treeview.md resolves.
Exit code 1 when anything is wrong.
"""
import glob, os, re, sys

bundle, rel = sys.argv[1], sys.argv[2].rstrip('/')
os.chdir(bundle)
bad = 0
files = sorted(glob.glob('00. Documentation/**/*.md', recursive=True) + glob.glob('00. Architecture/**/*.md', recursive=True))
for f in files:
    lines = open(f, encoding='utf-8').read().split('\n')
    head = '\n'.join(lines[:8])
    m = re.search(r'path="' + re.escape(rel) + r'/(.+?)"', head)
    if not m or m.group(1) != f:
        print('PATH mismatch:', f); bad += 1
    for target in re.findall(r'(?:sibling|parent|related)="' + re.escape(rel) + r'/([^"]+)"', head):
        if not os.path.exists(target):
            print('ATTR target missing:', f, '->', target); bad += 1
    idx = [k for k, x in enumerate(lines) if x.startswith('-- ')]
    title = os.path.basename(f)[:-3]
    if not idx or lines[idx[0]] != f'-- {title} --' or lines[idx[0] + 1] != '=' * len(lines[idx[0]]):
        print('BANNER wrong:', f); bad += 1
tv = '00. Documentation/00. Treeview.md'
if os.path.exists(tv):
    for link in re.findall(r'\]\(<([^>]+)>\)', open(tv, encoding='utf-8').read()):
        if not os.path.exists(os.path.normpath(os.path.join('00. Documentation', link))):
            print('Treeview link broken:', link); bad += 1
print(f'{len(files)} files checked, problems: {bad}')
sys.exit(1 if bad else 0)
