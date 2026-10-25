# Sheet spec v1 (2026-09-21) — IMPLEMENTED

**Status: the generator exists** (`intake.py --new-sheet SPEC …`, §6, §10). The five open questions of the draft were answered **yes** by the user (TOML; repeating groups stay `custom`; Apps Script in `life/<domain>/apps-script/`; language per sheet; AppSheet = runbook only). This is the contract the generator implements. `spec_lint.py` (this folder) already validates specs against it (`spec_lint.py SPEC [--live]`; `--live` compares an adopt spec with the real header row, read-only),
and the three files in `examples/` are real cases written in it (two existing sheets + one that exercises the escape hatch).
`workbooks.toml` maps the `workbook` key to a spreadsheet id, so ids never live in a spec.

## 1. What a spec is
One TOML file per sheet (`<id>.spec.toml`), hand-written or drafted with Claude from a description. TOML because it is stdlib
(`tomllib`), has comments, and stays readable for long column lists (JSON has no comments; YAML is not stdlib).
A spec describes **what the sheet is** — columns, how data gets in, what the skill is called. It never contains code or
credentials. The generator turns a spec into the pieces listed in §5.

Guiding rules (from what went wrong or right in this project):
- **A spec describes; it never restructures.** For a sheet that already exists (`mode = "adopt"`) the generator only *verifies* the
  layout and produces the profile/skill around it. It fails on drift instead of "fixing" it. (Lesson 2026-09-21: keep layouts the user built.)
- **Nothing is invented at runtime.** `safety.never_invent = true` puts the rule in every generated LLM prompt.
- **Test on scratch before real.** `safety.scratch_test = true`: the generator refuses `apply` until a scratch-tab run passed (§6).
- **Apps Script and AppSheet are deployed by a person in a browser.** The generator emits sources and a runbook; consent clicks and the
  AppSheet file picker are human steps (see google-workspace skill).

## 2. Top-level layout
```toml
spec_version = 1
[sheet]       # identity + shape of the tab
[[columns]]   # one block per column — order = column order. Equivalent spelling: a top-level inline array
              # `columns = [ {key=..., ...}, ... ]` placed BEFORE the first [table] (TOML would attach it to that table otherwise;
              # one key=value per line inside blocks — TOML has no `;`)
[[reference]] # optional: other tabs the values are validated/matched against
[intake]      # how data gets in (the pattern) + pattern options
[channels]    # which entry points exist
[skill]       # the dedicated skill to generate
[life]        # where events get logged in the life/ tree
[appsheet]    # optional runbook request
[safety]      # guard rails
```

## 3. Sections

### `[sheet]`
| key | type | required | meaning |
|---|---|---|---|
| `id` | kebab-case | yes | profile name (`--profile <id>`), default skill name, file prefix |
| `title` | string | yes | exact tab title |
| `description` | string | yes | one line, shown in `--list-profiles` and the skill |
| `language` | `fr`\|`en` | yes | language of headers/prompts/skill text the generator writes |
| `workbook` | string | yes | key into `workbooks.toml` (spreadsheet id lives there, never in a spec). Default workbook: `registre-financier` |
| `mode` | `create`\|`adopt` | yes | `create` = generator creates the tab; `adopt` = tab exists, verify only |
| `layout` | `table`\|`custom` | yes | `table` = one row = one record (fully generatable). `custom` = special layout with a hand-written writer (escape hatch, §7) |
| `frozen_rows` | int | no (1) | |
| `upsert_on` | list of column keys | no | natural key; if set, a re-run updates the existing row instead of appending |

### `[[columns]]` (required unless `layout = "custom"`)
| key | meaning |
|---|---|
| `key` | snake_case, unique — the record field name |
| `header` | exact header text, unique |
| `type` | `text` `longtext` `integer` `number` `percent` `date` `time` `datetime` `choice` `boolean` `link` `formula` |
| `required` | bool (default false): missing value → the skill asks instead of writing |
| `default` | `"today"` / `"now"` (date/time types only), a literal, or omitted |
| `choices` \| `choices_from` | for `type = "choice"`, exactly one: literal list, or `"Tab!A2:A"` (validation list from a reference range) |
| `min`, `max` | for `integer`/`number`/`percent` (`percent` is stored as a fraction 0–1, shown as %) |
| `formula` | for `type = "formula"`: A1 formula with `{row}`; the skill never writes it (like Correct/Answered/% today) |
| `width`, `wrap` | display |
| `note` | help text put on the header cell |
| `llm` | one sentence for the extraction prompt: what the field means / how to fill it |
| `aliases` | other header names accepted in CSV/JSON input |

### `[[reference]]` (optional)
`tab`, `key_column`, `used_by` (column keys). Values of those columns are matched against the reference tab; a miss is a
**non-blocking warning** (same behaviour as Nom vs "Points de dépôt / vente" today), never a rejection.

### `[intake]` — the pattern (who writes the final table)
| `pattern` | skill writes | other channel | Apps Script | when to choose it |
|---|---|---|---|---|
| `direct` | the final table | none | none | simple logs (Taïna mood). Default. |
| `form-trigger` | the final table | Google Form → `onFormSubmit` → final table | form + trigger `.gs` | someone fills a phone form; no AppSheet plan needed |
| `import-trigger` | the **Import** tab (a text DSL) | AppSheet/any paste → Import → `onChange` trigger → final table | setup + import-trigger `.gs` | rich validation/matching that must live next to the data (Registre, Dépôt / vente) |

Pattern options (subtables):
- `[intake.direct]`: `parser = "none"|"hand"` — `hand` makes the generator emit a `parse_structured()` stub for a deterministic input shape.
- `[intake.form]`: `title`, `date_question = true`, `not_given_choice = true` (yes/no/"Not given" dropdowns for boolean columns).
- `[intake.import]`: `tab` (Import tab name), `dsl_columns` (column keys usable in the DSL), `date_blocks = true` (`## <date>` blocks), `default_rules` (list of `{column, rule}` such as "Compte defaults to Cash"), `import_columns` (default `Horodatage, Texte, Statut, Résultat`), `dsl_extra_columns` (list of `{name, note}`: columns the DSL accepts and uses for matching but that are **not stored** in the final tab — e.g. `Lieu` for Dépôt / vente). A column absent from `dsl_columns` (e.g. `Nr`, resolved by the trigger) is never declared in the DSL.

### `[channels]`
`skill = true` (always), `form = false` (needs `pattern = "form-trigger"`), `appsheet = false` (runbook only, see `[appsheet]`).

### `[skill]`
`name` (kebab, default = `sheet.id`), `triggers` (≥3 phrases the description should react to), `not_for` (disambiguation vs other skills),
`judgment` (bullets copied into the SKILL.md "Judgment calls").

### `[life]`
`domain` (path under `life/`, e.g. `"20-family/22-taina"`), `open_loop` = `none`|`daily`|`weekly`|`<text>` — used to log the creation event and,
optionally, a recurring open loop.

### `[appsheet]` (optional)
`mode = "none"|"runbook"`, `app` (name of the **existing** app to extend — never a second app), `views` (`form`, `table`). With `runbook`, the
generator writes a step list (§5), it does not touch AppSheet.

### `[safety]`
`never_invent` (true), `scratch_test` (true), `keep_existing_layout` (true for `adopt`).

### `[custom]` (required when `layout = "custom"`)
`writer` (path of the hand-written profile), `form_script` (optional hand-written Apps Script), `why` (one sentence: why this is not a flat table). The generator produces everything *around* a custom sheet (skill, life log, runbook, lint) and never touches the writer.

## 4. Type mapping (one column type → every generated artifact)
| type | Sheets format / validation | Form item | AppSheet type | LLM schema |
|---|---|---|---|---|
| `text` | none | short answer | Text | string |
| `longtext` | wrap | paragraph | LongText | string |
| `integer` / `number` | number, min/max validation | short answer + number validation | Number | number |
| `percent` | `0%`, 0–1 validation | short answer 0–100 (÷100) | Percent | number 0–100 |
| `date` / `time` / `datetime` | `yyyy-mm-dd` / `hh:mm` / `yyyy-mm-dd hh:mm` | date / time / (date+time) | Date / Time / DateTime | ISO string |
| `choice` | dropdown from list or range | dropdown | Enum / Ref | one of the choices |
| `boolean` | 1/0 checkbox-style | Yes / No / Not given dropdown | Yes/No | true/false/null |
| `link` | named link | short answer + URL validation | Url | url + label |
| `formula` | `formula` with `{row}` | — | — | — (never written) |

## 5. What the generator would produce (all idempotent, `plan` first)
| artifact | pattern | where |
|---|---|---|
| tab: header, formats, validation, conditional formats, frozen rows | all (`create` only) | the workbook |
| profile `profiles/<id>.py` (columns, prompt from `llm`/`choices`/`never_invent`, normalisers stubs) | all | this skill |
| Apps Script `<id>-form.gs` (setup/rebuild/test/cleanup/status modes, sheet addressed by **gid**, handler on `globalThis`) | `form-trigger` | repo `life/<domain>/apps-script/` |
| Apps Script `<id>-setup.gs` + `<id>-import.gs` (Import tab, DSL parser, non-blocking validation, statuses) | `import-trigger` | repo `life/<domain>/apps-script/` |
| dedicated skill `<skill.name>/SKILL.md` + thin wrapper script | all | `~/.qwen/skills/` |
| AppSheet runbook `<id>-appsheet-runbook.md` (which table to add to which app, column type mapping, views, plan/deploy gotchas) | if `[appsheet].mode = "runbook"` | repo `life/<domain>/` |
| `life/` event + optional open loop | all | life tree |

Generated files carry a header `GENERATED from <id>.spec.toml — hash <sha>`; regenerating never overwrites a file whose body was hand-edited
(it writes `<file>.new` and reports the diff). Hand-written hooks live in clearly marked regions or in a sibling `<id>_hooks.py`.

## 6. Commands (built)
```
intake.py --new-sheet SPEC --plan            # list what would be created/changed/left alone; writes nothing
intake.py --new-sheet SPEC --verify          # compare the spec with the live tab (drift report) — the only thing adopt does
intake.py --new-sheet SPEC --scratch-test    # create a throwaway tab from the spec, write/read/delete, prove the profile works
intake.py --new-sheet SPEC --apply [--only tab|profile|scripts|skill|runbook|life]
```
Apps Script deployment is **not** a command: it is a guided browser session (Claude drives the editor, the user clicks Google's consent),
described in the generated skill and runbook, exactly as done for the grading form.

## 7. What does not fit (deliberately out of scope for `layout = "table"`)
- **One submission → many rows** (the grading grid: 34 question rows + 34 autonomy cells per student-day) and any two-row / wide grid.
  Use `layout = "custom"`: the spec still names the sheet, skill, channels, life log and safety; the writer (and form-question generation)
  is a hand-written profile, like `students-grading`. The generator scaffolds everything around it.
- **Charts, pivots, dashboards, cross-sheet formulas.** Add by hand; `--verify` ignores what it does not know.
- **Deterministic input parsers** (Taïna's numbered template): only a stub is generated (`parser = "hand"`).

## 8. What the three examples showed (why the format looks like this)
- **`taina-mood`** (adopt, direct): 18 columns, all types covered by the table in §4, live header identical → the flat-table model fits real data. The numbered-template parser is domain code, hence `parser = "hand"` (stub only).
- **`jm-livraison`** (adopt, import-trigger): needed three things a naive spec lacks — a column the trigger fills itself and the DSL must never declare (`Nr`), a DSL-only column (`Lieu`: accepted for matching, not stored — today this produces a "colonne lieu absente" warning on every import, a known wart the spec now makes visible), and tolerance for helper cells beside the table (`--verify` ignores extra columns to the right).
- **`students-grading`** (adopt, custom): a two-row student-day grid with one submission → many cells cannot be a flat table; `layout = "custom"` keeps it inside the same system (skill, channels, life log, safety) without pretending to generate its writer.
- TOML gotchas found while writing them: no `;` between keys on one line; a top-level inline `columns` array must precede the first `[table]`.

## 9. Decisions (answered by the user, 2026-09-21)
TOML: yes · repeating groups stay `layout = "custom"` · Apps Script sources in `life/<domain>/apps-script/` · language follows `sheet.language` per sheet · AppSheet is a guided runbook only.

## 10. What was built, how it is verified, and what is NOT proven
**Built** (`generator/`): `generate.py` (plan / verify / scratch-test / apply), `gen_tab.py` (tab: header, formats, validation, notes, widths; drift check), `gen_appsscript.py` (form and import JavaScript), `gen_artifacts.py` (profile, DSL prompt, dedicated SKILL.md, runbook, life log), and the runtime core `scripts/table_profile.py` (typed coercion, prompt from the spec, CSV/JSON/text input, upsert, formula columns, optional `<id>_hooks.py`).

**Behaviour to rely on**
- `apply` refuses without a scratch-test proof for the *current spec hash* when `[safety].scratch_test = true` (proofs live in `generator/.scratch/`).
- `create` re-runs are safe: if the tab exists the header is verified, never recreated; `adopt` never restructures and aborts on drift.
- **adopt defaults**: only tab verification + profile + skill + life log; `scripts` and `runbook` are opt-in via `--only` (they already exist by hand for real sheets).
- Generated files end with `GENERATED-BODY-HASH`; a hand-edited or hand-written file is never overwritten (`<file>.new`).
- Apps Script / runbook generation needs the tab to exist (its gid is embedded); otherwise `apply` refuses.
- The dedicated skill calls the engine directly (`intake.py --profile <id>`); no per-skill wrapper script is generated.
- Import statuses are fixed across sheets: `En attente` / `Traité`.

**Verified** (`generator/tests/run_tests.py`, 41 checks): coercions (21), lint incl. 9 injected errors, `--verify` of the two adopted real sheets, and three scratch tests on test specs — `direct` (7 checks: typed round-trip, formula column, upsert, required, range warning, CSV), `form-trigger` (15: same + generated JS `node --check`, only `main` declared, answer→value logic) and `import-trigger` (14: DSL prompt, Import-tab round-trip, generated JS parsing: sample DSL, `✅` skip, unknown column, last column absorbs commas, block date, required/choice warnings). Also exercised by hand: full `apply` on a throwaway spec (tab, profile, skill, life event + open loop), the generated profile writing/upserting, idempotent re-apply, hand-edit protection, the hooks.

**NOT proven yet — the first real deployment is the test**
- The generated Apps Script has been syntax-checked and its pure logic unit-tested under node, but **never run inside Apps Script**: `FormApp`/`DateTimeItem`/`TimeItem` calls, form validation objects, `LockService`, the onChange trigger and the explicit-row writer only get exercised when a human deploys it (see the runbook). Expect to fix small things on the first real sheet.
- The generated import processor reproduces the proven trigger's behaviours (blocks, comma absorption, `✅`, non-blocking warnings) but is a new implementation: it warns once per unknown column per block (the hand-written one warns per row) and writes with an explicit row range instead of `appendRow`. The existing Registre / Dépôt / vente scripts are untouched.
- AppSheet: runbook text only, never followed on a generated sheet.
