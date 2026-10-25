---
name: atomic-task-sequencer
description: Turns a high-level implementation plan into a plan.json file of atomic, self-contained tasks that a "dumb", context-limited executor agent (e.g. a cheap/free LLM CLI) can run one at a time without needing the rest of the plan. Use this whenever the user wants to break down a project plan, spec, or design doc into discrete numbered steps for automated or scripted execution — especially when they mention "atomic tasks", "plan.json", "task sequencing", handing work to a "simpler agent", or building an execution pipeline. This is the planning half of a plan → execute → verify pipeline; pair it with the executor-orchestrator skill to actually run the tasks, and the provider-router skill to pick which LLM API executes each one.
---

# Atomic Task Sequencer

Turns an implementation plan (prose, bullet list, design doc — whatever the user hands you) into a `plan.json` file: an ordered, dependency-aware list of atomic tasks, each one fully self-contained so a context-limited executor agent can run it without seeing the rest of the plan.

## When to use this

- The user has (or asks you to first produce) an implementation plan and wants it split into discrete steps for automated execution.
- The user mentions handing work to a "dumb"/"unsophisticated"/"simpler" agent, a cheap API model, or a scripted execution loop.
- Pairs naturally with `executor-orchestrator` (runs the plan.json) and `provider-router` (decides which LLM executes each task).

## Process

1. **Get or produce the implementation plan.** If the user hasn't given you one, do the high-level planning yourself first, in prose — this is work you (the sophisticated planner) should do, not the sequencer.
2. **Decompose into atomic tasks.** A task is atomic if it:
   - Touches the smallest reasonable unit of work (one file, one function, one config change, one migration step — not "build the auth system")
   - Has an unambiguous, checkable definition of done
   - Can be described completely without referencing other tasks' internal reasoning (only their *outputs*, via explicit file paths or values)
3. **Sequence by dependency, not just plan order.** Two tasks with no dependency between them can run in either order — mark this explicitly (see `depends_on`) rather than assuming linear order. This lets the orchestrator later parallelize if it wants to, and makes retries safer.
4. **Classify each task's type** as `"coding"` or `"other"` — the provider-router skill uses this to pick the API routing chain (DeepSeek-first for coding, Gemini-first otherwise).
5. **Write the self-contained task prompt** for each task (see Task Document Format below) — this is what actually gets sent to the executor agent, so it must not assume any memory of the plan.
6. **Verify every file path before writing it down** — for each path you're about to put in a task's
   `## Context`/`## Steps` section or in `expected_outputs`, actually check it yourself (`Read`/`ls`, or
   confirm the parent directory exists for a brand-new file) rather than trusting memory, a prior
   Explore-agent summary, or a similarly-named file elsewhere in the repo. A wrong path here doesn't fail
   loudly: the executor will happily create/edit a file at the wrong (possibly uncompiled or unreferenced)
   location, `expected_outputs`'s own check will pass because it's checking that same wrong path, and the
   mistake surfaces only much later when a human notices the fix didn't actually apply. This is doubly
   true in monorepos with lookalike paths — two files sharing a namespace or basename in different
   projects/layers — so grep for the class/type/symbol name and confirm you're pointing at the file that's
   actually compiled/imported/routed, not just a file with a matching name. (`executor-orchestrator` does a
   second, independent spot-check of this before launching — but that's a safety net, not a substitute for
   getting it right here.)
7. **Define a verification command** for each task — a shell command the orchestrator can run after execution to check the task actually succeeded, independent of the executor's own self-report. See "Designing verification commands" below. This is the single most important field — an executor's `"status": "success"` is a claim, not a fact.
8. **Validate the output** against the schema before handing it off:
   ```bash
   python3 scripts/validate_plan.py path/to/plan.json
   ```
9. Tell the user the plan.json is ready and point them at `executor-orchestrator` to run it.

## plan.json schema

```json
{
  "plan_id": "short-slug-for-this-run",
  "created": "2026-08-13T00:00:00Z",
  "continue_on_failure": false,
  "tasks": [
    {
      "id": "001",
      "title": "Short human-readable title",
      "type": "coding",
      "depends_on": [],
      "timeout_seconds": 300,
      "max_retries": 2,
      "prompt_file": "tasks/001.md",
      "expected_outputs": ["src/utils/parse_config.py"],
      "verify_command": "python3 -m py_compile src/utils/parse_config.py",
      "idempotent": true,
      "notes": "Safe to re-run: overwrites the whole file rather than appending."
    }
  ]
}
```

Field notes:
- **`id`**: zero-padded string, sortable, stable — never reuse or renumber once tasks exist, since status files and logs key off this.
- **`depends_on`**: list of task `id`s. Empty list = can run as soon as its turn comes up in a naive linear runner, or immediately in a parallel runner.
- **`timeout_seconds`**: be generous but finite. Coding tasks touching multiple files need more than a config tweak.
- **`max_retries`**: how many times the orchestrator retries this exact task before escalating to the planner. 2 is a reasonable default; 0 for tasks with side effects that aren't idempotent (rare — prefer making tasks idempotent instead).
- **`verify_command`**: must exit 0 on success, non-zero on failure. Keep it cheap (lint, compile check, file-exists-and-nonempty, a targeted test) — not a full test suite run per task.
- **`idempotent`**: true if re-running the task from scratch produces the same end state. If you can't make a task idempotent, say so in `notes` and set `max_retries: 0`.

## Task Document Format (what the executor actually reads)

Each `prompt_file` referenced in plan.json must be a **fully self-contained** markdown file — the executor has no memory of the overall plan and limited context, so nothing can be implied. Template:

```markdown
# Task 001: <title>

## Objective
One or two sentences. No reference to "the plan" or other tasks by number — describe outcomes, not history.

## Context
Only what's needed to do THIS task: relevant file paths, current file contents if the executor needs to see them, exact function signatures, relevant constants. If the executor needs to read a file first, say so explicitly with the exact path.

## Steps
1. Explicit, ordered, unambiguous.
2. Exact file paths, not "the config file".
3. Exact expected content/behavior, not "make it work".

## Boundaries — DO NOT
- Do not modify files outside: <list the exact files this task may touch>
- Do not install new dependencies unless explicitly listed here.
- Do not attempt to fix unrelated issues you notice — note them in `notes` in the status file instead.

## On completion, write a status file
Write valid JSON to `<status_path>` (exact path given by the orchestrator at launch time — do not guess it):
```json
{"task_id": "001", "status": "success", "output_files": ["src/utils/parse_config.py"], "notes": "one-line summary of what changed"}
```
Use `"status": "failed"` if you could not complete the task, and explain why in `notes`. Do not write `"success"` unless you actually completed every step above.
```

Context-limited agents over-scope when uncertain — the "Boundaries" section is not optional politeness, it's a control on blast radius. Always include it.

## Lessons from real runs (MANSA platform Phase 0, 2026-09-25 — 43 tasks, 4 runs)

Almost every failure in those runs came from the plan, not from the cheap models. Check these before launching:
1. **One test file per module.** A test file that imports several modules (e.g. all UI components, all repositories) fails every task whose siblings are not built yet — the module cannot even be imported. If task N's check runs a test, that test must import only task N's outputs plus things that already exist.
2. **Checks must not depend on formatting.** `grep -q "sqliteTable('jobs'"` failed three correct files that put `'jobs'` on the next line. Prefer a real test; if you must grep, grep a token, accept both quote styles (`['\"]`), and don't insist on `export function` vs `export const`.
3. **Prepare the toolchain before the first task.** Framework test runners often need generated files (Nuxt: `nuxt prepare` → `.nuxt/tsconfig.*.json`); run it yourself, and if it needs files a later task writes (e.g. i18n locale files), put minimal placeholders in place first. Run one contract test end-to-end yourself before launching the pipeline.
4. **Give enough turns.** With `mini_loop_executor.py`, 10 turns ran out on tasks that read several files first; 20 was enough for every task.
5. **Write the contracts yourself.** Planner-written tests made the executors' success verifiable; 40 of 43 modules were right on the first real attempt.

## Designing verification commands

Rank of preference (cheapest + most reliable first):
1. **Existence + non-empty check** for simple file-creation tasks: `test -s path/to/file`
2. **Syntax/compile check** for code: `python3 -m py_compile file.py`, `node --check file.js`, `tsc --noEmit file.ts`
3. **Targeted lint/test** for logic-bearing tasks: run just the relevant test file, not the whole suite.
4. **Grep/structural check** for config or data tasks: confirm a key exists, a line was added, a JSON field has the expected value.

Never rely solely on the executor's self-reported `status` field — that's exactly what verification exists to catch.

## Handing off

Once `plan.json` and all `tasks/*.md` files pass `validate_plan.py`, tell the user it's ready for `executor-orchestrator` and mention `provider-router` will assign each task's `type` to a provider chain automatically.
