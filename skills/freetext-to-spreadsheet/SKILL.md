---
name: freetext-to-spreadsheet
description: Generic "text or structured data → rows of a Google Sheet" engine with one profile per target sheet (taina-mood, students-grading, registre, jm-livraison). Use when the user wants to log/save/record data into one of the Sheets-backed logs and either names this skill (also reachable as /sheet-intake), asks "which sheets can I log into?", passes data for a profile that has no dedicated skill, or wants to add a NEW profile for another sheet ("make the same thing for ..."). For a request that clearly matches a dedicated skill — a finance transaction (freetext-to-registre), a JM delivery/collection (freetext-to-jm-livraison-collecte), Taïna's mood (taina-bipolar-disorder-log), a student's results (students-grading) — prefer that skill; they run on this same engine.
---

# Freetext → spreadsheet (alias: /sheet-intake)

One pipeline, one profile per sheet. The engine (`scripts/intake_engine.py`) does the common work; a profile (`profiles/<name>.py`) only says what is specific to one sheet. Full contract and checklist: `profiles/README.md`.

```
input (--text / --file / stdin / --json / profile-specific such as --csv)
  → deterministic parse of the shapes the sheet knows      (profile.parse_structured)
  → else LLM extraction — never inventing values           (profile.llm_prompt / from_llm)
  → normalise + defaults + warnings                        (profile.finalize)
  → preview, exactly what --dry-run prints                 (profile.show)
  → write                                                  (default: append rows with per-column formats)
```

## Use it

```bash
E=~/.qwen/skills/freetext-to-spreadsheet/scripts/intake.py
python3 $E --list-profiles                         # what can be logged, and into which tab
python3 $E --profile <name> --describe             # columns of the target tab
python3 $E --profile <name> --help                 # that profile's own flags
python3 $E --profile <name> --dry-run  <input flags>   # ALWAYS first for free text
python3 $E --profile <name> <input flags>          # real write
python3 $E --profile <name> --init                 # create the tab (header + formats) if missing
python3 $E --profile <name> --check [--date D]     # already logged? (exit 0 = yes)
```

Common input flags: `--text "..."`, `--file F`, stdin, `--json '{...}'`, `--date YYYY-MM-DD`, `--llm` (force LLM), `--no-llm`. Profiles add their own (students-grading: `--student --program --program-link --csv --csv-text --comment --header`).

Generated profiles are built on `scripts/table_profile.py` (typed coercion, upsert, formula columns, CSV/JSON/text input, optional `<id>_hooks.py`). Profiles today:
| profile | target tab | note |
|---|---|---|
| `taina-mood` | Suivi humeur Taïna | daily mood/sleep observations for a child psychiatrist — record only, never a diagnosis; numbered-template parser + LLM fallback. Dedicated skill: `taina-bipolar-disorder-log` |
| `students-grading` | Students grading | per-question results + autonomy per student-day; CSV or free text. Dedicated skill: `students-grading` |
| `registre` | Import Registre → Registre | finance/life transactions and events, via the trigger. Dedicated skill: `freetext-to-registre` |
| `jm-livraison` | Import → Dépôt / vente | JM deliveries/sales/collections, via the trigger. Dedicated skill: `freetext-to-jm-livraison-collecte` |

## Procedure
1. Pick the profile (`--list-profiles`); if the user's data matches a dedicated skill's domain, use that skill's instructions (same engine underneath).
2. Free text → run `--dry-run` first, show the user the parsed preview and every `!` warning, then run for real. Structured data (CSV/JSON) can go straight through, still reporting the summary.
3. Report: rows written / the range, the values that were left empty, warnings. Never guess a missing required value (student, programme, date) — ask.
4. Setup problems (missing OAuth token/client secret, no LLM key): stop and point to `~/.qwen/skills/_freetext-import-lib/README.md` — one-time infra, not something to work around per run.

## No profile fits → generate a new sheet system from a spec
Full contract: `generator/SPEC.md`. Workflow (never skip a step; never restructure a sheet the user built — use `mode = "adopt"`, which only verifies):
1. **Draft the spec** with the user (`generator/examples/*.spec.toml` are models; test specs in `generator/tests/specs/`): columns + types, how data gets in — `direct` (skill writes the table), `form-trigger` (Google Form + Apps Script) or `import-trigger` (text DSL → Import tab → Apps Script trigger validates) —, skill triggers, life domain, AppSheet yes/no. Confirm the pattern and layout with the user. A sheet that is not "one row = one record" (grids, one submission → many rows) is `layout = "custom"`: the profile/writer stays hand-written.
2. `python3 generator/spec_lint.py SPEC [--live]` → fix every error.
3. `python3 $E --new-sheet SPEC --plan` → show the user what will be created / left alone.
4. `python3 $E --new-sheet SPEC --scratch-test` → must PASS (creates and deletes a throwaway tab).
5. `python3 $E --new-sheet SPEC --apply` → tab, profile, dedicated skill, runbook, Apps Script source, life event (+ open loop, pushed to Drive).
6. **Human/browser steps** (not automatable): deploy the generated Apps Script following the runbook — Claude drives the editor, the user clicks Google's consent — and, if requested, the AppSheet steps (runbook only). The first real deployment is the real test of the generated JavaScript: expect small fixes, then re-run `--scratch-test`.
7. Regression suite after any change to the generator: `python3 generator/tests/run_tests.py` (41 checks; `--offline` skips the ones that touch the workbook).

## Trigger-fed sheets (registre, jm-livraison)
These two never write to the final table. The LLM reformats the text into the sheet's mini-DSL (prompt + Orange Money `<calculate/>` fee resolver stay in `_freetext-import-lib/append_import.py`, the single source of truth), ONE row `[timestamp, DSL, "En attente", ""]` is appended to the Import tab, and the existing Apps Script `onChange` trigger validates and writes the real table; the engine polls the Import row's result for up to 20 s. Extra flags: `--dsl "<DSL>"` (skip the LLM, submit approved text), `--no-wait`. `--dry-run` shows the DSL without writing — use it first for long, multi-day or ambiguous text.

## Layout of this skill
`scripts/intake.py` (CLI) · `scripts/intake_engine.py` (Profile base class + pipeline) · `profiles/*.py` (one per sheet) · shared helpers in `~/.qwen/skills/_freetext-import-lib/` (`intake_common.py`: Sheets client + LLM→JSON; Google OAuth token).
