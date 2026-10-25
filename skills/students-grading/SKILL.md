---
name: students-grading
description: Records a student's results for an exercise sheet, quiz or exam — per question: correct or not, and the student's autonomy (0-100 %) — into the "Students grading" tab of the "Registre Financier — life/" Google Sheet. Takes structured input (student name, programme name, programme document link, and a CSV list of question / expected answer / correct / autonomy) or free text that it structures with an LLM. Use whenever the user wants to log, save, record or grade a child's or student's exercises, homework, daily program, test or exam results — phrases like "log Dang's exercises", "grade Taïna's program", "note les résultats de Maboma", "enregistre les notes", "students grading". Works for any level (children to doctoral) and any question count.
---

# Students grading

> **Engine (2026-09-21):** `scripts/students_grading.py` is now a thin wrapper around the shared engine (`freetext-to-spreadsheet/scripts/intake.py --profile students-grading`); same flags. The former standalone script is kept as `scripts/students_grading.legacy.py`.

Fills the wide "Students grading" grid: **2 rows per student-day** — a results row (1 right / 0 wrong / blank not given, one cell per question) and, under it, an **autonomy row** (0-100 %, one *unmerged* cell per question; 0 = needed full help, 100 = did it alone). Correct / Answered / % / average Autonomy are sheet formulas — the script never writes them. Row 2 of the tab holds the question labels (`1. i)`…), row 3 the expected-answer key of the programme the header describes; column G is the Programme (named link to the programme document).

Script: `~/.qwen/skills/students-grading/scripts/students_grading.py` (uses `_freetext-import-lib`: Google OAuth token, LLM routing via `provider-router`; first-time setup in that lib's README).

## Structured input (preferred when the data is already a list)

```bash
python3 ~/.qwen/skills/students-grading/scripts/students_grading.py \
  --student "Dang" --program "<programme name>" --program-link "<Google Doc / Drive URL>" \
  [--date YYYY-MM-DD] [--comment "..."] --csv results.csv        # or --csv - (stdin) / --csv-text "..."
```

CSV = `question, expected answer, correct, autonomy` (header row optional):
- `correct`: `1/0`, `yes/no`, `right/wrong`, `✓/✗`, `oui/non`; **empty = not given** (not counted against the student).
- `autonomy`: `0-100`, `60%` also fine; empty = not given.
- Optional extra column `n` / `nr` / `#` / `id` with the grid label (`1.i`, `2. iv)`) to place a question in a specific column; without it the k-th row goes to the k-th question column.

## Unstructured input

```bash
python3 .../students_grading.py --text "Maboma, 23 septembre. Exercice 1 tout juste, seul (autonomie 100%). Exercice 2 tout faux sauf le troisième, autonomie 40%. Exercices 3 à 6 non donnés." \
  --program "<name>" --program-link "<url>"
```
An LLM turns the text into the same structure (student, date, rows) — **never inventing**: anything not stated stays empty. It is given the grid labels so "exercise 1 all right" expands into `1.i … 1.vi`. Always read back its `LLM extraction:` line and the summary to the user.

## Other commands
- `--dry-run` on any write: shows the target rows and the totals without writing (use it first when the input was free text).
- `--header`: lists the grid's question labels and key.
- `--check --student S --date D`: exit 0 if that student-day already has a row.

## Behaviour to rely on
- **Upsert**: same date + student + programme → the existing rows are overwritten, never duplicated.
- **Different programme, same grid**: if a question's expected answer differs from the key row, the result is written anyway and a **cell note** `question -> expected` is attached to that result cell — nothing is lost, the layout doesn't change.
- **Programme cell**: a named link (the API cannot create smart chips); an existing chip showing the same name is left untouched.
- More questions than grid columns → the script stops and says so (extend the header first). Label not in the header → stops.

## Judgment calls
- Ask for the student's name and the programme name/link if the user gave neither — don't guess them.
- Never turn "not mentioned" into "wrong". A question only counts when the input says it was answered.
- Report back: rows written, `answered / correct (%)`, mean autonomy, and any key-mismatch warning.

## Related infrastructure (built 2026-09-21)
- **Google Form** (link in cell G1 of the tab): Date, Student, Programme link, then per question a Yes / No / Not given dropdown + an autonomy 0-100 field; an Apps Script `onFormSubmit` trigger writes the same rows. Script source + notes: `life/20-family/exercises/grades-form-setup.gs` (standalone Apps Script project "Untitled project", modes setup / rebuild / test / cleanup / status; addressed by sheet gid so renaming the tab is safe).
- History and decisions: `life/20-family/events/2026-09.md`.
