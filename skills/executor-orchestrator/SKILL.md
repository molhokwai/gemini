---
name: executor-orchestrator
description: Runs a plan.json (produced by atomic-task-sequencer) as a supervised loop against a cheap/context-limited executor agent — dispatching one task at a time, waiting for a status marker file, verifying the result independently, retrying on failure, and escalating back to the planner when retries are exhausted. Use this whenever the user wants to actually execute a sequenced task plan, run an unattended plan → execute → verify pipeline, or asks about markers, timeouts, idempotency, or escalation in the context of running automated tasks against another agent/API.
---

# Executor Orchestrator

The runtime loop that drives a `plan.json` (from `atomic-task-sequencer`) against a real executor — a cheap LLM API call, a CLI agent, whatever process actually does the work per task. It handles the parts a naive "spawn and hope" loop gets wrong: knowing whether a task truly succeeded, retrying safely, detecting a hung executor, and knowing when to stop bothering the executor and come back to the planner instead.

## Core loop, one task at a time

1. Pick the next task whose `depends_on` are all marked `success` in the run log.
2. Get provider assignment for this task's `type` from `provider-router` (`route_provider.py`).
3. Render the task's `prompt_file` with the concrete `status_path` for this attempt injected (see "Status file path" below).
4. Launch the executor against that rendered prompt.
5. Wait for the status file to appear, up to `timeout_seconds`.
6. **Timeout →** kill the executor process, treat as a failure, go to step 8.
7. **Status file appears →**
   a. Check `expected_outputs` exist and are non-empty (cheap structural check).
   b. Run `verify_command`; must exit 0.
   c. Both pass + status file says `"success"` → mark task `success` in the run log, continue to next task.
   d. Anything fails → treat as a failure, go to step 8.
8. **On failure:** if attempts so far < `max_retries`, mark this provider failed for the run (`route_provider.py --mark-failed`) so the retry uses the next provider in the chain, then retry from step 2. If retries exhausted, **escalate** (see below) and either halt or skip-and-continue depending on `continue_on_failure`.

## Running it

```bash
python3 scripts/orchestrate.py \
  --plan plan.json \
  --executor-cmd 'python3 executor_wrapper.py --prompt-file {prompt_file} --status-file {status_file} --provider {provider} --model {model} --base-url {base_url} --api-key-env {api_key_env}' \
  --workdir .
```

`--executor-cmd` is a template — the orchestrator fills in `{prompt_file}`, `{status_file}`, and the provider fields from `route_provider.py`'s output, then runs it as a subprocess per task. You supply `executor_wrapper.py` (or point at an existing CLI); the orchestrator doesn't know or care what's inside it, only that it writes a status file in the agreed schema before exiting. See `references/executor_wrapper_template.py` for a minimal OpenAI-compatible-client starting point, or `scripts/mini_loop_executor.py` for a ready-to-use tool-calling loop (read/write/list files, optional `--allow-shell`) that works against any OpenAI-compatible provider out of the box.

**API keys from `.env.local`/`.env`:** `orchestrate.py` loads `<--workdir>/.env.local` then `<--workdir>/.env` into `os.environ` once at startup (Vite-style precedence — `.env.local` wins, real environment variables always win over both) before spawning `route_provider.py` or the executor — both rely on `os.environ.get(api_key_env)`, and subprocesses inherit this process's environment. This means a project keeping its cheap-provider keys in a gitignored `.env.local` (the Klavis convention — `DEEPSEEK_API_KEY`/`GEMINI_API_KEY`/`GROQ_API_KEY`/`CEREBRAS_API_KEY`) needs no manual `source`/`export` step before running the orchestrator; just make sure `--workdir` points at the directory that actually contains the `.env.local` file.

## Status file path — why the orchestrator, not the executor, decides it

Never let the executor choose or guess its own status file path — race conditions and stale files from previous attempts are the #1 source of false "success" reads. The orchestrator generates a fresh path per *attempt* (not just per task):

```
.orchestrator/status/{task_id}.attempt{N}.json
```

and deletes any stale file at that exact path before launching, so a leftover from a crashed prior run can never be misread as this attempt's result. The rendered task prompt tells the executor exactly this path — it must never be asked to invent one.

## Provider failures have two scopes (fix 2026-09-25)

A timeout or crash (the provider is down, out of credit, rate-limited, or its model was retired) excludes that provider for the **rest of the run** (`provider_state.json`). A **failed verification** only rotates the provider for **that task's** retries (a per-task copy, `provider_state.task<ID>.json`), because it says something about the task, not about the provider. Before this fix, one hard task marked every provider failed and blocked the rest of the plan.

Also seen on that run: Groq retired `llama-3.3-70b-versatile` (HTTP 404 — now `openai/gpt-oss-120b`), Cerebras answered 402 Payment Required, and free tiers can crash mid-run on rate limits. Smoke-test each enabled provider with a one-file task before a long run.

**Report location for the nkensa / MANSA projects:** the Klavis report register path above does not exist there — write the run report into the task's own reference file (e.g. `mansa-ai-trainings-offer/02. Application - Implementation/04. Application - Phase 0 - Foundations ✅.md` → *Pipeline report*).

## Idempotency and re-entrancy

- Before launching an attempt, the orchestrator does **not** assume a clean slate — it re-checks `expected_outputs` from any prior attempt of this task. If the task is marked `"idempotent": true` in plan.json, this is safe: re-running is expected to converge to the same end state regardless of partial prior attempts.
- If `"idempotent": false`, the orchestrator refuses to retry automatically past 1 attempt regardless of `max_retries` in plan.json, and escalates immediately on the first failure — re-running a non-idempotent task blind is how you get duplicated appends, double-charged side effects, etc. This is a hard safety rail in `orchestrate.py`, not just plan-authoring discipline.
- The whole run itself is re-entrant: if you kill the orchestrator process and restart it against the same `plan.json` and the same `.orchestrator/run_log.json`, it picks up from the first task not yet marked `success` rather than re-running everything. Delete `.orchestrator/` to force a full clean run.

## No-op-rewrite detection — a second false-positive class

Beyond the executor's self-reported status and `verify_command`, `orchestrate.py` catches a distinct
failure mode: the executor calls `write_file` with content **byte-identical** to what was already there
(e.g. it read the file, decided it already satisfies the task, and wrote it back unchanged), then
self-reports `"success"`. Every other signal looks green — the file exists, `verify_command` can even pass
(the file was already valid before the "fix") — so this slips past both the structural check and the
verify command.

The orchestrator closes this gap by snapshotting the bytes of every pre-existing `expected_outputs` file
before each attempt (`pre_task_snapshot`), then comparing post-attempt bytes against that snapshot
(`any_file_actually_changed`) once the attempt finishes. If **none** of the pre-existing files actually
changed, the attempt is downgraded to failure regardless of self-reported status or `verify_command`
result, and the attempt log records `no_op_rewrite: true` so this is distinguishable from other failure
causes later. This is a real, observed failure mode (not hypothetical) — treat it as a required check, not
an optional enhancement.

**Known gap, not yet patched:** `restore_expected_outputs` only restores files that existed in
`pre_task_snapshot` — it has nothing to restore *to* for a file that didn't exist before the attempt. If a
failed or crashed attempt **creates** a brand-new file, that file is left on disk even though the attempt
is marked failed. After any crashed/failed attempt, check for and manually delete orphaned new files before
re-running — don't assume a "failed" status means the working tree is untouched.

## Before launching a real run: verify paths and `--workdir`

Two real incidents motivate double-checking this, not just trusting the plan.json/task doc as authored:

1. A task doc referenced a file at a path that *looked* right but was actually a different, uncompiled
   duplicate elsewhere in the repo (a monorepo with two files sharing a namespace/basename). The executor
   happily wrote there, `expected_outputs` matched (it was checking that same wrong path), the attempt was
   marked success — and the actual fix silently never took effect until a human noticed later. See
   `atomic-task-sequencer/SKILL.md` for the authoring-side fix; this is the same class of bug, just visible
   from the launch side too.
2. `--workdir` was pointed one directory above the actual project root (a shared parent of two sibling
   repos). An executor's relative-path `write_file` calls then resolved one level too high, landing outside
   every `expected_outputs` path the orchestrator was tracking — the file was written, just never where
   anyone was looking for it.

Before launching for real:
- Confirm **`--workdir`** is the directory every `expected_outputs` absolute path actually lives under —
  after resolving both to absolute paths, each `expected_outputs` entry should start with `--workdir`.
- Pass **`--router`** and **`--provider-config`** as absolute paths. `orchestrate.py` `chdir`s into the
  plan's own directory early (so `plan.json`-relative paths like `tasks/001.md` keep working) — a relative
  `--router`/`--provider-config` then resolves against that new cwd instead of the one you typed it from,
  and fails with a confusing "no such file" deep inside `route_provider.py` rather than pointing at the
  actual mistake.
- Spot-check at least one `expected_outputs` path per task with `ls`/`Read` before the run — the same
  verification `atomic-task-sequencer` should already have done when authoring the task. A second,
  independent check costs nothing and catches the case where the sequencer's own check was wrong or the
  plan was hand-edited afterward.

## Reporting — always write the end-of-run report

When a run finishes — whether every task succeeded, or it halted/finished with some tasks blocked — append
an entry to the shared, cross-repo report register:

```
./pm/tasks/analysis-and-implementation/00. Architecture/00. Architecture - DEV - AI Architecture - Atomic Execution Pipeline/00. Reports.md
```

(cloud symlink, not git-tracked — edit directly with `Edit`/`Write`, never `git add`, same rule as any
other reference file per `klavis-devtask-pm` §1.) **Append, never overwrite** a prior run's entry. One
entry per run, containing at minimum:

- A table: `Task nr | AI providers tried | Successful run time | Task status | Notes`.
- A short tally (how many succeeded automated / after retry / needed manual completion).
- A one-paragraph note on anything that required manual intervention and **why** — a provider
  hallucination, a stale dev server, a wrong path, a tooling gap fixed mid-run, etc.

This is not optional politeness: it is the only place the cost/reliability trade-off of routing tasks to
cheap providers stays visible over time, across many runs. Skipping it silently erodes the point of
measuring the pipeline at all.

## Timeouts and dead-executor detection

- `timeout_seconds` (per task, from plan.json) is a hard wall-clock cap from subprocess launch to status-file-appears.
- On timeout, the orchestrator sends SIGTERM, waits 5s, then SIGKILL if the process is still alive — never leaves orphaned executor processes running.
- A distinct case from "timeout": the process exits (crashes) *before* the timeout without writing a status file. The orchestrator detects this via the subprocess return code and treats it as an immediate failure (not a retry-eligible timeout) — the executor is gone, retrying with a fresh process is fine, but it's worth logging separately since a crash often points to a bad task prompt (malformed input) rather than a slow API.

## Escalation path back to the planner

Escalation means: the orchestrator stops trying to solve this itself and produces a package for you (the sophisticated planner) to look at. It writes:

```
.orchestrator/escalations/{task_id}.json
```

containing: the task definition, every attempt's status file (or lack thereof) and stderr/stdout tail, the verification command's output, and the providers that were tried. It does **not** try to be clever about re-planning — that's your job. If `continue_on_failure: false` (default), the orchestrator halts the whole run after writing the escalation and prints the path. If `true`, it logs the escalation, marks the task and everything depending on it as `blocked`, and continues with any remaining tasks whose dependencies are still satisfiable.

When you're brought an escalation file, read it, decide whether to: fix the task's prompt and re-run just that task, split it into smaller atomic tasks, or do it yourself — then update `plan.json` and re-invoke the orchestrator; it resumes from the run log automatically.

## Files this skill produces (all under `.orchestrator/` next to plan.json)

```
.orchestrator/
├── run_log.json           # per-task status: pending | running | success | failed | blocked
├── status/                # per-attempt status files written by the executor
├── escalations/           # packages for the planner when retries are exhausted
└── orchestrator.log       # full timestamped log of every attempt
```

These are local, per-run working files — they don't accumulate history across runs and aren't meant to.
The durable, cross-run record is the report you append per the Reporting section above.

## Reference implementation

`scripts/orchestrate.py` is a working, dependency-free (stdlib only) implementation of the loop above. `references/executor_wrapper_template.py` is a starting point for the piece you fill in — the actual call to whichever LLM/CLI is doing the work, using the provider fields the orchestrator passes it.
