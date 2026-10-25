# Executor options — what actually runs each task, and how to switch

`orchestrate.py` never knows or cares *how* a task gets done — it only
knows the contract: launch `--executor-cmd`, wait for a status file at
the path it injects, verify independently. That means switching executors
is a **one-line change** (the `--executor-cmd` argument), never a change
to the orchestrator, router, or plan.json. This doc lays out the options
so you can pick per-project, or even per-task-type.

## Quick comparison

| Option | Setup effort | Handles multi-file edits / running tests? | Works with all 4 providers? | Risk surface |
|---|---|---|---|---|
| **1. Raw completion** | None (stdlib only) | No — one text response, you apply it yourself | Yes, any OpenAI-compatible endpoint | Low — no code execution |
| **2. Mini tool-loop** (built here) | None (stdlib only) | Yes, within a capped number of turns | Yes, if the model supports OpenAI-style function calling | Medium — file writes sandboxed to workdir; shell exec off by default |
| **3. Multi-provider CLI** (e.g. `aider`) | Install a package | Yes, mature multi-turn editing + test running | Depends on tool's provider support (`aider` supports arbitrary OpenAI-compatible base URLs) | Medium-high — full coding-agent capability, its own safety model |
| **4. Vendor-specific agentic CLI** (Claude Code, Gemini CLI, etc.) | Install + auth per vendor | Yes, most capable option | No — one tool per vendor, breaks the "one wrapper, four providers" simplicity | Depends on tool |

## Option 1 — Raw completion (`references/executor_wrapper_template.py`)

One HTTP call, one text response back. You write the logic that decides
what to do with that text (write it to a file, etc.) directly in the
wrapper — there's a `# TODO` for exactly that in the template.

**Use when:** the task's entire deliverable *is* text — drafting a doc
section, generating a config value, writing a single well-specified file
in one shot with no need to see intermediate results.

**Don't use when:** the task needs to read a file first, or iterate based
on a test/lint result — a single completion has no feedback loop.

```
--executor-cmd 'python3 executor_wrapper_template.py --prompt-file {prompt_file} --status-file {status_file} --provider {provider} --model {model} --base-url {base_url} --api-key-env {api_key_env}'
```

## Option 2 — Mini tool-loop (`scripts/mini_loop_executor.py`) — the default here

A small agentic loop, stdlib-only, using OpenAI-compatible function
calling: the model gets `read_file`, `write_file`, `list_dir`, and must
call `task_complete` exactly once to end the task (with an honest
`success`/`failed` status — it's a structured tool call, not free text,
which is more reliable to parse than hoping the model writes clean JSON
unprompted). Capped at `--max-turns` (default 6) so a confused model
can't loop forever — hitting the cap is reported as `"failed"`, which the
orchestrator's verification will catch anyway even if it weren't.

```
--executor-cmd 'python3 mini_loop_executor.py --prompt-file {prompt_file} --status-file {status_file} --provider {provider} --model {model} --base-url {base_url} --api-key-env {api_key_env} --max-turns 6'
```

**Shell execution is off by default.** A `run_command` tool exists but is
refused unless you pass `--allow-shell`. Think carefully before enabling
it: a cheap/context-limited model deciding what shell command to run,
unsupervised, based on task-prompt content (which itself might include
untrusted text, e.g. from a file it read) is a real risk — runaway
commands, unintended deletions, or a task prompt that was itself
compromised. If you enable it, do so only for task types where you've
reviewed what commands might plausibly be needed (e.g. `python -m
py_compile`, `pytest path/to/test.py`), not as a blanket default.

**File writes are sandboxed** to the executor's working directory —
`../` traversal or symlink escapes are rejected before any write happens
(tested: see conversation history for the path-traversal test case).

**Provider caveat:** this depends on the provider/model supporting
OpenAI-style `tools`/function-calling in its API response format. All
four (DeepSeek, Gemini via its OpenAI-compatible endpoint, Groq, Cerebras)
generally support this for their mainstream models, but **verify against
current docs for the specific model you configure in `providers.json`** —
function-calling support varies by model within a provider's lineup, and
this changes over time. If a model doesn't support it, you'll see it
never produce `tool_calls`, hit the "please use the available tools" nudge
repeatedly, and eventually exceed `max_turns` — a clear, debuggable
failure mode rather than a silent one.

**Use when:** tasks need to read-then-write, or write multiple files, but
don't need to run tests/linters as part of the task itself, and you want
to keep the whole pipeline dependency-free and provider-agnostic.

## Option 3 — Multi-provider CLI (e.g. `aider`)

Real agentic coding tools like [`aider`](https://aider.chat) support
pointing at arbitrary OpenAI-compatible endpoints via environment
variables or config, which means one CLI install can serve all four of
your providers by swapping which env vars/base URL you set before
invoking it — similar spirit to this suite's routing, but with a much
more capable editing/test-running loop underneath.

Rough shape (verify current `aider` flags/env vars against its docs
before relying on this — CLI interfaces change):

```bash
pip install aider-chat --break-system-packages

# wrapper script sets provider-specific env vars based on the orchestrator's
# {base_url}/{model}/{api_key_env} template args, then:
aider --model openai/{model} --openai-api-base {base_url} --yes --message-file {prompt_file}
```

You'd still write a thin wrapper (same shape as the templates here) whose
job is: translate the orchestrator's `--provider/--model/--base-url/--api-key-env`
args into whatever `aider` expects, run it, then **write the status file
yourself** afterward based on `aider`'s exit code and a check of what it
actually changed (`git diff` is a natural fit here since `aider` commits
its own changes) — `aider` won't natively speak this suite's status-file
protocol, so that translation layer is on you.

**Use when:** tasks are real multi-file coding work where running tests
mid-task and iterating on failures matters, and you're OK with the
install/maintenance overhead of a real coding agent.

## Option 4 — Vendor-specific agentic CLI (Claude Code, Gemini CLI, etc.)

The most capable option, but ties you to one vendor per tool — breaks the
"one wrapper handles all four providers" simplicity that makes the
routing chain useful. Consider this less as a *replacement* for the
routing chain and more as an **escalation lane**: if a task keeps landing
in `.orchestrator/escalations/` after exhausting the cheap-provider
chain, that's a signal to hand *that specific task* to a more capable
tool (possibly me, in a follow-up session) rather than routing everything
through it from the start — which would defeat the cost-saving point of
this whole pipeline.

## How to actually switch

1. Write (or reuse) a wrapper that accepts the same five arguments every
   executor here accepts: `--prompt-file --status-file --provider --model
   --base-url --api-key-env`, plus whatever's specific to your chosen tool.
2. Change the `--executor-cmd` template string passed to `orchestrate.py`.
   Nothing else — not `plan.json`, not `provider-router`, not
   `orchestrate.py` itself — needs to change.
3. You can even route different task **types** to different executors by
   writing a thin dispatcher wrapper that picks a strategy based on
   `{provider}` or by inspecting the task prompt, if you want coding tasks
   to go through `aider` while everything else goes through the mini
   tool-loop. The orchestrator doesn't need to know about this split —
   your `--executor-cmd` wrapper is exactly where that decision belongs.
