# plan.json — full field reference

## Top level

| Field | Type | Required | Notes |
|---|---|---|---|
| `plan_id` | string | yes | Slug identifying this run, e.g. `"klavis-purge-script-v2"`. Used to namespace status/log files. |
| `created` | string (ISO 8601) | no | Informational. |
| `continue_on_failure` | bool | no (default `false`) | If `true`, the orchestrator skips a task that exhausts retries/escalates and moves to the next task whose dependencies are still satisfied, instead of halting the whole run. |
| `tasks` | array of task objects | yes | See below. Order in the array is the default execution order for a linear runner; `depends_on` is authoritative for anything relying on ordering guarantees. |

## Task object

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Zero-padded, stable, unique. Never renumber. |
| `title` | string | yes | Human-readable, shown in logs. |
| `type` | `"coding"` \| `"other"` | yes | Consumed by `provider-router` to select the API chain. |
| `depends_on` | array of task `id` strings | yes (may be empty) | Must not form a cycle; validated by `validate_plan.py`. |
| `timeout_seconds` | int | yes | Wall-clock time the orchestrator waits for the status file before declaring the executor dead. |
| `max_retries` | int | yes | Attempts after the first failure before escalating to the planner. |
| `prompt_file` | string (relative path) | yes | Path to the self-contained task document, relative to `plan.json`'s directory. |
| `expected_outputs` | array of string paths | yes | Files the task should create/modify. Used by the orchestrator's baseline sanity check (existence + non-empty) *before* running `verify_command`. |
| `verify_command` | string (shell command) | yes | Must exit 0 on success. Run from the working directory the orchestrator was launched in. |
| `idempotent` | bool | yes | If `false`, `max_retries` should typically be `0` unless the task has been designed with an explicit "clean slate" step. |
| `notes` | string | no | Free text — design rationale, non-idempotency caveats, anything the planner (you, later) would want to know when re-reading this plan. |

## Why `expected_outputs` AND `verify_command`

They check different things:
- `expected_outputs` is a **structural** sanity check — did the executor even touch the files it was supposed to? Cheap, always run first.
- `verify_command` is a **correctness** check — is what it produced actually valid/working? Can be as strict as you want.

Failing the cheap check first means you don't waste time running an expensive verify command (or worse, a flaky test suite) against a file the executor never touched.

## Status file (written by the executor, read by the orchestrator)

```json
{"task_id": "003", "status": "success", "output_files": ["src/foo.py"], "notes": "..."}
```

`status` must be exactly `"success"` or `"failed"`. The orchestrator treats anything else (malformed JSON, missing field, unexpected value) as a failure and logs it distinctly from an explicit `"failed"`, since it usually indicates the executor didn't follow the task document's instructions correctly — worth flagging to the planner even if a retry later succeeds.
