#!/usr/bin/env python3
"""
/freetext-to-spreadsheet (alias /sheet-intake) — CLI.

  intake.py --list-profiles
  intake.py --profile NAME --describe
  intake.py --profile NAME [common flags] [profile flags]
  intake.py --new-sheet SPEC.toml (--plan | --verify | --scratch-test | --apply [--only ...])   # sheet generator, see generator/SPEC.md

Common flags: --text T | --file F | (stdin) | --json J, --date D, --init, --check, --dry-run, --llm, --no-llm.
Profile flags depend on the profile: intake.py --profile NAME --help.
"""
import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(os.path.dirname(HERE), 'profiles')
sys.path.insert(0, HERE)
import intake_engine as eng  # noqa: E402


def list_profiles():
    return sorted(f[:-3].replace('_', '-') for f in os.listdir(PROFILES_DIR) if f.endswith('.py') and not f.startswith('_'))


def load_profile(name):
    path = os.path.join(PROFILES_DIR, name.replace('-', '_') + '.py')
    if not os.path.isfile(path):
        raise SystemExit(f'Unknown profile "{name}". Available: {", ".join(list_profiles())}')
    spec = importlib.util.spec_from_file_location('profile_' + name.replace('-', '_'), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PROFILE


def main():
    if '--new-sheet' in sys.argv:                       # generator: intake.py --new-sheet SPEC (--plan|--verify|--scratch-test|--apply)
        i = sys.argv.index('--new-sheet')
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'generator'))
        import generate
        return generate.main(sys.argv[i + 1:])
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument('--profile')
    pre.add_argument('--list-profiles', action='store_true')
    pre.add_argument('--describe', action='store_true')
    known, _ = pre.parse_known_args()
    if known.list_profiles or not known.profile:
        print('Profiles:')
        for n in list_profiles():
            print(f'  {n:<20} {load_profile(n).description}')
        if not known.list_profiles:
            print('\nUsage: intake.py --profile NAME [...]   (add --help after --profile NAME for its flags)')
        return 0
    profile = load_profile(known.profile)
    if known.describe:
        print(f'{profile.name}: {profile.description}\nTab: {profile.tab or "(custom)"}')
        for c in profile.columns:
            print(f'  {c.key:<16} {c.kind:<9} {c.header}')
        return 0

    ap = argparse.ArgumentParser(prog=f'intake.py --profile {profile.name}', description=profile.description,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--profile', help='profile name')
    ap.add_argument('--text')
    ap.add_argument('--file')
    ap.add_argument('--json', dest='json_in')
    ap.add_argument('--date', help='YYYY-MM-DD (profile default rules apply)')
    ap.add_argument('--init', action='store_true', help='create the target tab if missing')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-llm', action='store_true')
    ap.add_argument('--llm', action='store_true')
    profile.add_args(ap)
    args = ap.parse_args()
    return eng.run(profile, args)


if __name__ == '__main__':
    sys.exit(main() or 0)
