#!/usr/bin/env python3
"""
Executor orchestrator — runs a plan.json against a pluggable executor command.

Usage:
  python3 orchestrate.py \
    --plan plan.json \
    --executor-cmd 'python3 executor_wrapper.py --prompt-file {prompt_file} --status-file {status_file} --provider {provider} --model {model} --base-url {base_url} --api-key-env {api_key_env}' \
    --router scripts/route_provider.py \
    --provider-config providers.json \
    --workdir .

Stdlib only — no third-party dependencies required.
"""
import argparse
import json
import os
import shlex
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone


def log(logfile, msg):
    line = f"[{datetime.now(timezone.utc).isoformat()}] {msg}"
    print(line)
    with open(logfile, "a") as f:
        f.write(line + "\n")


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path) as f:
        return json.load(f)


def load_dotenv_files(root_dir):
    """Load KEY=VALUE pairs from <root_dir>/.env.local then <root_dir>/.env
    into os.environ, without overriding a variable already set in the real
    environment — matches Vite's .env.local-overrides-.env convention, which
    is where Klavis projects keep machine-local secrets (e.g. the cheap
    LLM-provider API keys route_provider.py looks for via api_key_env).
    Subprocesses spawned later (route_provider.py, the executor command)
    inherit this process's environment, so loading here once is enough —
    no per-script dotenv duplication needed. Missing files are silently
    skipped (most environments won't have .env.local at all)."""
    for filename in (".env.local", ".env"):
        path = os.path.join(root_dir, filename)
        if not os.path.isfile(path):
            continue
        with open(path) as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                os.environ.setdefault(key, value)


def save_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def render_task_prompt(prompt_path, status_path, out_path):
    """Inject the concrete status file path into the task doc before handing
    it to the executor, so it never has to guess or invent one."""
    with open(prompt_path) as f:
        content = f.read()
    injected = (
        content
        + f"\n\n---\n**Status file path for this attempt (write your JSON status here, exactly):**\n"
        f"`{status_path}`\n"
    )
    with open(out_path, "w") as f:
        f.write(injected)


def get_provider(router_script, task_type, config_path, state_path):
    result = subprocess.run(
        [sys.executable, router_script, "--task-type", task_type,
         "--config", config_path, "--state", state_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None, result.stderr.strip()
    return json.loads(result.stdout.strip()), None


def mark_provider_failed(router_script, provider, state_path, reason):
    subprocess.run(
        [sys.executable, router_script, "--mark-failed", provider,
         "--state", state_path, "--reason", reason],
        capture_output=True, text=True,
    )


def check_expected_outputs(expected_outputs):
    missing = []
    for path in expected_outputs:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            missing.append(path)
    return missing


def run_verify_command(cmd, cwd):
    # cwd MUST be passed explicitly: main() chdir's the whole process into
    # plan_dir (so plan.json-relative paths like tasks/001.md keep working),
    # so a verify_command written relative to --workdir (the norm — see
    # atomic-task-sequencer's own examples) would silently resolve against
    # plan_dir instead and almost always fail to find anything, without ever
    # raising an error (grep/test just report "not found" as exit 1).
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=120
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "verify_command timed out after 120s"


def wait_for_status_file(status_path, proc, timeout_seconds, poll_interval=0.5):
    """Polls for the status file. Returns ('ok', None), ('timeout', None),
    or ('crashed', returncode) depending on what happened first."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        if os.path.isfile(status_path):
            return "ok", None
        ret = proc.poll()
        if ret is not None:
            # process exited — give it one brief moment in case it wrote
            # the file right before exiting and the FS hasn't flushed
            time.sleep(0.2)
            if os.path.isfile(status_path):
                return "ok", None
            return "crashed", ret
        time.sleep(poll_interval)
    return "timeout", None


def kill_process(proc):
    if proc.poll() is not None:
        return
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    except ProcessLookupError:
        pass


def write_escalation(esc_dir, task, attempts, verify_output):
    os.makedirs(esc_dir, exist_ok=True)
    path = os.path.join(esc_dir, f"{task['id']}.json")
    save_json(path, {
        "task": task,
        "attempts": attempts,
        "last_verify_output": verify_output,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
    })
    return path


def snapshot_expected_outputs(expected_outputs):
    """Capture the pre-attempt bytes of every expected_outputs file that already
    exists, so a failed attempt's edits (up to and including a full-file
    overwrite) can be undone before the next provider is tried. Confirmed live:
    a Groq attempt once replaced a whole 289-line file with the literal string
    "modified content" and then honestly self-reported failure — without this
    restore, that corrupted content would have been the starting point handed
    to the NEXT attempt (or left on disk if the task ultimately escalated)."""
    return {p: open(p, "rb").read() for p in expected_outputs if os.path.isfile(p)}


def restore_expected_outputs(snapshot):
    for path, content in snapshot.items():
        with open(path, "wb") as f:
            f.write(content)


def any_file_actually_changed(expected_outputs, pre_task_snapshot):
    """A second, independent false-positive guard beyond mini_loop_executor's own
    "was write_file even called" check — confirmed live: an attempt can call
    write_file with content byte-identical to the original (a no-op rewrite),
    which passes the executor's own check (a real write_file call happened for
    the right path), passes expected_outputs/verify_command (file still exists,
    still compiles — nothing changed, so of course it still compiles), and self-
    reports "success" with a plausible-sounding notes string, all while the git
    diff is empty. If NONE of the pre-existing expected_outputs files differ
    from their pre-attempt snapshot, treat this as a fabricated success. Files
    that didn't exist before (freshly created by this attempt) always count as
    "changed" — there's nothing to compare them against."""
    if not pre_task_snapshot:
        return True  # nothing to compare against (e.g. all outputs are new files) — don't block success
    for path in expected_outputs:
        if path not in pre_task_snapshot:
            return True  # newly created file
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            if f.read() != pre_task_snapshot[path]:
                return True
    return False


def run_task(task, args, run_log, logfile):
    task_id = task["id"]
    task_type = task["type"]
    idempotent = task.get("idempotent", False)
    max_retries = task.get("max_retries", 0)
    effective_max_retries = max_retries if idempotent else 0  # hard safety rail

    status_dir = os.path.join(args.workdir, ".orchestrator", "status")
    os.makedirs(status_dir, exist_ok=True)
    tmp_dir = os.path.join(args.workdir, ".orchestrator", "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    attempts = []
    provider_state_path = os.path.join(args.workdir, ".orchestrator", "provider_state.json")
    # Resolve relative to --workdir, NOT the process cwd — main() chdir's into
    # plan_dir, so a bare relative path here would resolve against the wrong
    # directory and every expected_outputs check would report "missing" even
    # when the executor wrote the file correctly under --workdir.
    expected_outputs_abs = [
        p if os.path.isabs(p) else os.path.join(args.workdir, p)
        for p in task.get("expected_outputs", [])
    ]
    pre_task_snapshot = snapshot_expected_outputs(expected_outputs_abs)

    # Two scopes of provider failure (fix 2026-09-25, MANSA platform Phase 0 run):
    # - run-scoped (provider_state.json): the provider itself is broken — timeout, crash, HTTP error.
    #   It stays excluded for every later task of the run.
    # - task-scoped (a per-task copy): the provider answered but its work failed verification.
    #   That says something about THIS task, not about the provider, so it only rotates the
    #   provider for this task's retries. Before this fix one hard task marked every provider
    #   failed and blocked the whole rest of the plan.
    task_state_path = os.path.join(args.workdir, ".orchestrator", f"provider_state.task{task_id}.json")
    if os.path.isfile(provider_state_path):
        shutil.copyfile(provider_state_path, task_state_path)
    elif os.path.isfile(task_state_path):
        os.remove(task_state_path)

    attempt_num = 0
    while True:
        attempt_num += 1
        provider, err = get_provider(
            args.router, task_type, args.provider_config, task_state_path
        )
        if provider is None:
            log(logfile, f"task {task_id}: no provider available ({err}) — escalating")
            path = write_escalation(
                os.path.join(args.workdir, ".orchestrator", "escalations"),
                task, attempts, err,
            )
            run_log["tasks"][task_id] = "blocked"
            return "blocked", path

        status_path = os.path.abspath(
            os.path.join(status_dir, f"{task_id}.attempt{attempt_num}.json")
        )
        if os.path.isfile(status_path):
            os.remove(status_path)  # never trust a stale file for this attempt

        rendered_prompt = os.path.join(tmp_dir, f"{task_id}.attempt{attempt_num}.md")
        render_task_prompt(task["prompt_file"], status_path, rendered_prompt)

        cmd = args.executor_cmd.format(
            prompt_file=shlex.quote(rendered_prompt),
            status_file=shlex.quote(status_path),
            provider=provider["provider"],
            model=provider["model"],
            base_url=provider["base_url"],
            api_key_env=provider["api_key_env"],
        )
        log(logfile, f"task {task_id} attempt {attempt_num}: launching via {provider['provider']} ({provider['model']})")
        proc = subprocess.Popen(cmd, shell=True, cwd=args.workdir)

        outcome, returncode = wait_for_status_file(status_path, proc, task["timeout_seconds"])

        if outcome == "timeout":
            log(logfile, f"task {task_id} attempt {attempt_num}: TIMEOUT after {task['timeout_seconds']}s — killing executor")
            kill_process(proc)
            mark_provider_failed(args.router, provider["provider"], provider_state_path, "timeout")
            mark_provider_failed(args.router, provider["provider"], task_state_path, "timeout")
            attempts.append({"attempt": attempt_num, "provider": provider["provider"], "outcome": "timeout"})
        elif outcome == "crashed":
            log(logfile, f"task {task_id} attempt {attempt_num}: executor CRASHED (exit {returncode}) without writing status")
            mark_provider_failed(args.router, provider["provider"], provider_state_path, f"crashed exit={returncode}")
            mark_provider_failed(args.router, provider["provider"], task_state_path, f"crashed exit={returncode}")
            attempts.append({"attempt": attempt_num, "provider": provider["provider"], "outcome": "crashed", "returncode": returncode})
        else:
            kill_process(proc)  # in case it's lingering post-write
            status = load_json(status_path, {})
            self_reported = status.get("status")

            missing = check_expected_outputs(expected_outputs_abs)
            verify_ok, vout, verr = (True, "", "")
            if not missing:
                verify_ok, vout, verr = run_verify_command(task["verify_command"], args.workdir)

            changed = any_file_actually_changed(expected_outputs_abs, pre_task_snapshot)

            success = (self_reported == "success") and not missing and verify_ok and changed

            attempts.append({
                "attempt": attempt_num,
                "provider": provider["provider"],
                "outcome": "completed",
                "self_reported_status": self_reported,
                "missing_expected_outputs": missing,
                "verify_ok": verify_ok,
                "verify_stdout": vout,
                "verify_stderr": verr,
                "no_op_rewrite": not changed,
                "status_file_notes": status.get("notes"),
            })

            if success:
                log(logfile, f"task {task_id} attempt {attempt_num}: SUCCESS (provider={provider['provider']})")
                run_log["tasks"][task_id] = "success"
                return "success", None

            reason = (
                f"self_reported={self_reported}, missing_outputs={missing}, "
                f"verify_ok={verify_ok}, no_op_rewrite={not changed}"
            )
            log(logfile, f"task {task_id} attempt {attempt_num}: FAILED verification ({reason})")
            mark_provider_failed(args.router, provider["provider"], task_state_path, reason)

        # Reached only on a non-success outcome (success returns above) — undo
        # whatever this attempt did to expected_outputs before trying again
        # (or before leaving the task blocked), so a bad attempt never leaks
        # into the next provider's starting state or into a human's working tree.
        restore_expected_outputs(pre_task_snapshot)
        log(logfile, f"task {task_id} attempt {attempt_num}: restored expected_outputs to pre-attempt state")

        if attempt_num > effective_max_retries:
            reason_note = (
                "non-idempotent task — retries disabled by safety rail"
                if not idempotent else "max_retries exhausted"
            )
            log(logfile, f"task {task_id}: escalating to planner ({reason_note})")
            path = write_escalation(
                os.path.join(args.workdir, ".orchestrator", "escalations"),
                task, attempts, attempts[-1] if attempts else None,
            )
            run_log["tasks"][task_id] = "blocked"
            return "blocked", path


def dependencies_satisfied(task, run_log):
    return all(run_log["tasks"].get(dep) == "success" for dep in task.get("depends_on", []))


def dependencies_blocked(task, run_log):
    return any(run_log["tasks"].get(dep) in ("blocked", "failed") for dep in task.get("depends_on", []))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--executor-cmd", required=True,
                   help="Template with {prompt_file} {status_file} {provider} {model} {base_url} {api_key_env}")
    p.add_argument("--router", default=os.path.join(
        os.path.dirname(__file__), "..", "..", "provider-router", "scripts", "route_provider.py"))
    p.add_argument("--provider-config", default="providers.json")
    p.add_argument("--workdir", default=".")
    args = p.parse_args()

    plan_abspath = os.path.abspath(args.plan)
    plan_dir = os.path.dirname(plan_abspath) or "."
    workdir_abspath = os.path.abspath(args.workdir)
    os.chdir(plan_dir)
    args.plan = plan_abspath
    args.workdir = workdir_abspath

    load_dotenv_files(args.workdir)

    orch_dir = os.path.join(args.workdir, ".orchestrator")
    os.makedirs(orch_dir, exist_ok=True)
    logfile = os.path.join(orch_dir, "orchestrator.log")
    run_log_path = os.path.join(orch_dir, "run_log.json")

    plan = load_json(args.plan)
    if plan is None:
        print(f"Cannot read plan file: {args.plan}", file=sys.stderr)
        sys.exit(2)

    run_log = load_json(run_log_path, {"plan_id": plan.get("plan_id"), "tasks": {}})
    continue_on_failure = plan.get("continue_on_failure", False)

    tasks_by_id = {t["id"]: t for t in plan["tasks"]}
    log(logfile, f"=== Run started: plan_id={plan.get('plan_id')} tasks={len(plan['tasks'])} ===")

    halted = False
    while True:
        progressed = False
        for task in plan["tasks"]:
            tid = task["id"]
            status = run_log["tasks"].get(tid)
            if status in ("success", "blocked"):
                continue
            if dependencies_blocked(task, run_log):
                log(logfile, f"task {tid}: SKIPPED (a dependency is blocked)")
                run_log["tasks"][tid] = "blocked"
                save_json(run_log_path, run_log)
                progressed = True
                continue
            if not dependencies_satisfied(task, run_log):
                continue

            progressed = True
            run_log["tasks"][tid] = "running"
            save_json(run_log_path, run_log)

            outcome, esc_path = run_task(task, args, run_log, logfile)
            save_json(run_log_path, run_log)

            if outcome == "blocked" and not continue_on_failure:
                log(logfile, f"=== HALTING run: task {tid} escalated, continue_on_failure=false ===")
                log(logfile, f"Escalation package: {esc_path}")
                halted = True
                break
        if halted:
            break
        if not progressed:
            break

    remaining = [t["id"] for t in plan["tasks"] if run_log["tasks"].get(t["id"]) not in ("success", "blocked")]
    succeeded = [tid for tid, s in run_log["tasks"].items() if s == "success"]
    blocked = [tid for tid, s in run_log["tasks"].items() if s == "blocked"]

    log(logfile, f"=== Run finished: {len(succeeded)} succeeded, {len(blocked)} blocked, {len(remaining)} not reached ===")
    if blocked:
        log(logfile, f"Blocked task ids: {blocked} — see .orchestrator/escalations/")
    print(json.dumps({"succeeded": succeeded, "blocked": blocked, "not_reached": remaining}, indent=2))
    sys.exit(1 if blocked or remaining else 0)


if __name__ == "__main__":
    main()
