---
name: devtask
description: End-to-end orchestrator for a self-contained dev task in this repo (feature / fix / tooling change) from analysis to shipped commit. Drives lightweight phases — Init, Plan, Validate, Implement, Ship — scaled to the task's size, and delegates the git/PM mechanics to devtask-pm. Trigger when the user starts a non-trivial, self-contained piece of work spanning analysis → code → commit, especially anything touching ai/, projects/, or shared tooling.
---

# Nkensa repo — Dev Task Orchestrator

The **conductor** for a complete development task in this repo. Doesn't re-implement git or the reference-file protocol — sequences them and delegates:

| Concern | Owned by | Invoked at |
|---|---|---|
| Reference-file version-log, branch (if any), commit/push, registers | **`devtask-pm`** | Phase 0 (existing files) + Phase 5 (ship) |
| The lifecycle glue (init → plan → validate → implement) | **this skill** | Phases 0–4 |

This repo is a **single, solo monorepo** — not a classic frontend/backend split. There's no repo-aware test-skill routing here; "the test" for any given task is whatever check actually applies to what changed (a script's own smoke-run, a subproject's own test suite if `projects/*` has one, or just a careful re-read for docs/config changes).

## Scale to the task — this is a frame, not a tollgate

Most work in this repo is small-to-medium. Judge first:

- **Trivial** (a typo, a config tweak, a one-line log entry): skip straight to Implement, then a light Ship (commit directly, per `devtask-pm` §7's solo-repo note). Mention you're skipping the ceremony.
- **Small** (a new script, a `life/` domain addition, a skill tweak): Init (a few lines) → Plan (short) → Implement → Ship.
- **Complex or repo-wide** (a new tooling system, a reorg touching several top-level folders — the kind of thing that produced `ai/claude/skills-pm-scaffold/` or `life/`): run all phases, and split into a dedicated commit per concern at Ship (see `devtask-pm` §4).

When in doubt, propose a scale and proceed — this is a solo repo, there's no one else to ask.

## Where things live

- **Reference / task documents** → `pm/tasks/analysis-α-implementation/<topic-slug>/` — a **symlink to a live-synced Google Drive mirror** (`/media/nkensa/win11/Files/Projects/Nkensa/analysis-α-implementation`, syncing to Drive on its own — no push script needed, so `devtask-pm-collectfiles` isn't installed here). Edit these directly with `Write`/`Edit`; **never** `git add` anything through the symlink — git errors "beyond a symbolic link" (expected, not a bug). This is the *only* thing under `pm/tasks/` in this repo — no separate in-repo register system (see `devtask-pm` §8: registers are disabled here).
  - If the task's *deliverable* is itself a self-contained set of documents (not app code) — a training curriculum, a client doc pack — scaffold it as a **sub-project bundle**: a numbered file sequence (`00. <Title>.md`, `01. <Title>.md`, …) inside its own `<topic-slug>/`, instead of the single-file `<topic-slug> - Implementation Analysis.md`. See `devtask-pm` §1 for the full pattern and the `mansa-ai-training` precedent.
- **This orchestrator + `devtask-pm`** → `.claude/skills/` (auto-discovered by Claude Code as `/`-invocable).
- **The life/ event tree** (`life/CONSTITUTION.md`) is a *separate* system — it logs life/work events across all domains (including WORK), on its own Session Protocol (log `planned`/`in_progress` at start, update to `done` at end). A `devtask` run and a `life/50-work` event entry are not the same thing: run both — `devtask`'s reference file is the *plan and implementation record*; the `life/50-work` entry is the *"this happened" log line*. Don't let one substitute for the other.

## Phase 0 — Init

1. **Locate or create the reference file**, if the task is substantial enough to warrant one (skip for trivial tasks — see Scale above):
   ```
   pm/tasks/analysis-α-implementation/<topic-slug>/<topic-slug> - Implementation Analysis.md
   ```
   Header: a `<thisfile path="..."/>` tag, a title banner, then **Objective**, **Steps**, **Dependencies**, **Definition of Done** stubs.
2. **The developer fills the analysis** — the problem or the plain instructions for what to do. Prompt for it; do not invent requirements.
3. **Pick the task type** — `feature`, `fix`, `chore`, `refactor`, `docs`, `tooling`. Sets the commit `<type>`.

## Phase 1 — Plan

Draft a plan grounded in this repo's actual layout — cite real paths (`life/`, `ai/claude/skills-pm-scaffold/`, `projects/<name>/`, `shortcuts/`), not generic advice. Sequence the steps; name the Definition of Done. Write it into the reference file if one exists.

## Phase 2 — Validate

Present the plan; the developer validates or amends it. "Ok"/"Good" = greenlight. Don't start until accepted.

## Phase 3 — Implement

- Match the surrounding style and conventions of whatever you're touching.
- Keep changes minimal and reviewable; work in milestones.
- No fixed build command in this repo — the "gate" is whatever's appropriate to what changed (run a script, re-read a doc for correctness, check a subproject's own test command if `projects/*` has one).

## Phase 4 — Ship → delegate to `devtask-pm`

Hand off to **`devtask-pm`** for the git lifecycle: commit (named files only), conventional message, rollback SHA, and the enabled register checkpoints (§7 of `devtask-pm`). For anything logged in `life/`, also close out the `life/50-work` (or relevant domain) event entry per the Session Protocol — this is separate from, and in addition to, the git commit.

## Handoff summary

```
Phase 0 Init       · this skill  → reference file (if warranted) + task type
Phase 1 Plan       · this skill  → repo-grounded plan
Phase 2 Validate   · this skill  → developer accepts/amends
Phase 3 Implement  · this skill  → code/docs/config, milestone by milestone
Phase 4 Ship       · devtask-pm  → commit/push + registers + rollback SHA
```
