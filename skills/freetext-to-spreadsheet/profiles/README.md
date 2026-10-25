# Profiles — one per target sheet

The engine (`../scripts/intake_engine.py`, CLI `../scripts/intake.py`) owns the common pipeline; a profile only says what is
specific to one sheet. File `profiles/<name_with_underscores>.py`, CLI name = dashes (`taina_mood.py` → `--profile taina-mood`).
It must export `PROFILE = MyProfile()` where `MyProfile(Profile)` (import: `from intake_engine import Profile, Column`).

```
input (--text / --file / stdin / --json / profile-specific)
  -> parse_structured()   deterministic parser for the shapes this sheet knows; None = not recognised
  -> else LLM             llm_prompt() + from_llm()   (never invent values: say so in the prompt)
  -> finalize()           normalise, defaults, warnings, (custom writers) build a plan
  -> show()               preview — also what --dry-run prints
  -> write()              default: append rows, formats per column kind
```

Parsed = `{'rows': [dict], 'warnings': [str], 'meta': {...}, 'source': 'structured'|'llm'|'json'|'csv', 'ok': bool}`.

## Declarative part
| attribute | meaning |
|---|---|
| `name`, `description` | shown by `--list-profiles` |
| `tab` | target tab name |
| `columns` | `[Column(key, header, kind, width, wrap)]`, kind ∈ `text date datetime time percent`; drives `--init` (creates the tab with header + formats + widths), the default writer, the preview and `--check` |
| `date_key` | column used by the default `--check` (default `date`) |
| `show_empty_exclude` | column keys not reported as "empty" in the preview |

## Hooks (all optional except what your input modes need)
`add_args(ap)` extra CLI flags · `extra_actions(ctx)` extra action flags (return True if handled) · `read_text(ctx)` ·
`parse_structured(text, ctx)` · `llm_prompt(ctx)` · `from_llm(data, ctx, source)` · `acquire(ctx)` (override to add input modes,
e.g. `--csv`; call `super().acquire(ctx)` for the rest) · `finalize(parsed, ctx)` · `show(parsed, ctx)` · `init(ctx)` ·
`write(parsed, ctx)` (override for special layouts) · `check(ctx)` (return process exit code).
`ctx` = `.args` (argparse namespace: common flags `--text --file --json --date --init --check --dry-run --llm --no-llm` + yours),
`.sheets` (`Sheets` client: `sheet_id`, `batch`, `get_values`, `put_values`, `append_values`, raw `call`), `.today`, `.text`.

## Existing profiles
- `taina-mood` — append-rows sheet with a rich deterministic parser (numbered template) + LLM fallback. Verbatim port of the former `log_entry.py`; regression-tested identical (10 cases) and format-identical on a scratch tab.
- `registre`, `jm-livraison` — trigger-fed (`_import_trigger.py` base class): LLM -> DSL -> one row in the Import tab -> Apps Script trigger writes the real table. Prompts/fee formulas reused from `append_import.py`, not copied. Verified 2026-09-21: `--dsl` fee-tag resolution equals `append_import` (64/364); safe write test with a pre-processed row on both Import tabs (restored exactly); real end-to-end through both triggers with restore-by-diff (all touched cells restored, tabs back to original size).
- `students-grading` — custom writer for the two-row student-day grid; structured input is a CSV. Port of the former `students_grading.py`; regression-tested cell-identical on scratch rows.

## Adding a profile
**Preferred: generate it** from a sheet spec (`intake.py --new-sheet SPEC …`, see `../generator/SPEC.md`) — flat tables get a `TableProfile` (`scripts/table_profile.py`) for free. Hand-write a profile only for a layout that is not a flat table (like `students-grading`). Manual checklist:
1. Copy the closest existing profile. 2. Define `columns` (or override `write`). 3. Write `llm_prompt` (schema + "never invent") and
`from_llm`. 4. Add a deterministic `parse_structured` only if the input has a stable shape worth parsing without an LLM.
5. Test with `--dry-run` first, then a real write on a **scratch tab/rows**, then clear them.
Sheets that submit through an Apps Script `onChange` trigger (Registre, Dépôt / vente) must keep doing so — their profiles append
to the *Import* tab, not the final table (see `_freetext-import-lib/append_import.py`).
