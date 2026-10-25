#!/usr/bin/env python3
"""
Mini tool-loop executor — a lightweight agentic loop using OpenAI-compatible
function calling, so a single-completion API (DeepSeek/Gemini/Groq/Cerebras)
can still read files, write files, and (optionally) run shell commands across
multiple turns, rather than being limited to one shot of raw text.

This is the middle option between "raw completion" (executor_wrapper_template.py)
and "install a real agentic CLI" (see README.md alternative 3). See README.md
in this directory for the full comparison and how to switch between them —
switching is just changing the --executor-cmd string passed to orchestrate.py,
nothing else in the orchestrator changes.

Usage (same CLI contract orchestrate.py expects from any executor):
  python3 mini_loop_executor.py \
    --prompt-file rendered_task.md \
    --status-file status.json \
    --provider deepseek --model deepseek-chat \
    --base-url https://api.deepseek.com/v1 --api-key-env DEEPSEEK_API_KEY \
    [--max-turns 6] [--allow-shell] [--workdir .]

SAFETY: shell command execution is OFF by default. Pass --allow-shell only
if you trust the task prompts running through this pipeline and understand
that a cheap/context-limited model choosing what shell command to run,
unsupervised, is a real risk (prompt injection from file contents it reads,
runaway/destructive commands, etc). File read/write tools are always
sandboxed to --workdir (default: current directory) — path traversal
attempts (../, symlinks resolving outside workdir) are rejected.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file, relative to the working directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write (overwrite) a file's full contents, relative to the working directory. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files in a directory, relative to the working directory.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": (
                "Call this exactly once, when you are done — whether you succeeded "
                "or could not complete the task. This is the ONLY way to end the "
                "task; you must honestly report failure here if you could not "
                "finish, rather than claiming success."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["success", "failed"]},
                    "output_files": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["status", "notes"],
            },
        },
    },
]

SHELL_TOOL = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Run a shell command in the working directory and return its stdout/stderr/exit code. Use sparingly — only for things read_file/write_file/list_dir can't do (running a linter, a test, etc).",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}


def safe_path(workdir, rel_path):
    """Resolve rel_path against workdir and reject anything that escapes it."""
    full = os.path.realpath(os.path.join(workdir, rel_path))
    workdir_real = os.path.realpath(workdir)
    if not (full == workdir_real or full.startswith(workdir_real + os.sep)):
        raise ValueError(f"path '{rel_path}' resolves outside the working directory — rejected")
    return full


def execute_tool(name, args, workdir, allow_shell):
    try:
        if name == "read_file":
            path = safe_path(workdir, args["path"])
            if not os.path.isfile(path):
                return {"error": f"file not found: {args['path']}"}
            with open(path) as f:
                return {"content": f.read()}

        if name == "write_file":
            path = safe_path(workdir, args["path"])
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(args["content"])
            return {"ok": True, "bytes_written": len(args["content"])}

        if name == "list_dir":
            path = safe_path(workdir, args.get("path", "."))
            if not os.path.isdir(path):
                return {"error": f"not a directory: {args.get('path', '.')}"}
            return {"entries": sorted(os.listdir(path))}

        if name == "run_command":
            if not allow_shell:
                return {"error": "shell execution is disabled (run without --allow-shell); this tool call was refused"}
            result = subprocess.run(
                args["command"], shell=True, cwd=workdir,
                capture_output=True, text=True, timeout=60,
            )
            return {"returncode": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}

        return {"error": f"unknown tool: {name}"}
    except Exception as e:
        return {"error": str(e)}


def chat_completion(base_url, model, api_key, messages, tools):
    """One OpenAI-compatible chat completion call with tool definitions.
    Isolated into its own function so it can be mocked/monkeypatched for
    testing the loop logic without hitting a real network endpoint."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "tools": tools,
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            # Some providers (confirmed: Groq) front their API with Cloudflare,
            # which blocks urllib's default "Python-urllib/x.y" User-Agent as a
            # bot signature (HTTP 403, Cloudflare error 1010). A generic
            # browser/CLI-like UA avoids this — verified against a real 403.
            "User-Agent": "Mozilla/5.0 (compatible; klavis-executor-orchestrator/1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]


def run_loop(base_url, model, api_key, task_id, prompt_text, workdir,
             max_turns, allow_shell, completion_fn=chat_completion):
    tools = TOOLS + ([SHELL_TOOL] if allow_shell else [])
    messages = [
        {
            "role": "system",
            "content": (
                "You are an execution agent working on exactly one atomic task. "
                "Use the provided tools to read/write files as needed. When finished "
                "(successfully or not), call task_complete exactly once — this is the "
                "only way the task ends. Report failure honestly if you could not "
                "complete every step; do not claim success you did not achieve."
            ),
        },
        {"role": "user", "content": prompt_text},
    ]

    written_files = set()  # paths actually passed to a successful write_file call

    for turn in range(1, max_turns + 1):
        message = completion_fn(base_url, model, api_key, messages, tools)
        messages.append(message)

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            # Model responded with plain text instead of a tool call — nudge it.
            messages.append({
                "role": "user",
                "content": "Please use the available tools. When done, call task_complete.",
            })
            continue

        # A single completion can bundle several tool_calls together, including
        # task_complete alongside a write_file in the SAME batch. Returning the
        # instant task_complete is seen (old behavior) silently drops any calls
        # listed after it — confirmed in practice: a model reported "success"
        # after a single turn with nothing ever written. Fix: execute every
        # non-task_complete call in the batch first, and only finalize once the
        # whole batch has run.
        completion_call = None
        for call in tool_calls:
            fn_name = call["function"]["name"]
            try:
                fn_args = json.loads(call["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name == "task_complete":
                completion_call = fn_args  # defer — finish executing the batch first
                continue

            result = execute_tool(fn_name, fn_args, workdir, allow_shell)
            if fn_name == "write_file" and "error" not in result:
                written_files.add(fn_args.get("path"))
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result),
            })

        if completion_call is not None:
            status = completion_call.get("status", "failed")
            output_files = completion_call.get("output_files", [])
            notes = completion_call.get("notes", "")
            # Don't trust a self-reported "success" that claims files this run
            # never actually wrote — this is exactly the false-positive pattern
            # observed in practice (model calls task_complete with a plausible
            # notes string, zero write_file calls, turns_used=1).
            if status == "success":
                unwritten = [f for f in output_files if f not in written_files]
                if unwritten:
                    status = "failed"
                    notes = (
                        f"REJECTED self-reported success: claimed output_files "
                        f"{unwritten} were never actually written via write_file "
                        f"during this run (written_files={sorted(written_files)}). "
                        f"Original notes: {notes}"
                    )
            return {
                "task_id": task_id,
                "status": status,
                "output_files": output_files,
                "notes": notes,
                "turns_used": turn,
            }

    return {
        "task_id": task_id,
        "status": "failed",
        "output_files": [],
        "notes": f"exceeded max_turns ({max_turns}) without calling task_complete",
        "turns_used": max_turns,
    }


def extract_task_id(prompt_text):
    import re
    m = re.search(r"Task (\S+):", prompt_text)
    return m.group(1) if m else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--status-file", required=True)
    p.add_argument("--provider", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--api-key-env", required=True)
    p.add_argument("--max-turns", type=int, default=6)
    p.add_argument("--allow-shell", action="store_true")
    p.add_argument("--workdir", default=".")
    args = p.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(f"Missing API key in env var {args.api_key_env}", file=sys.stderr)
        sys.exit(1)  # no status file written -> orchestrator sees "crashed"

    with open(args.prompt_file) as f:
        prompt_text = f.read()

    task_id = extract_task_id(prompt_text)

    try:
        result = run_loop(
            args.base_url, args.model, api_key, task_id, prompt_text,
            os.path.abspath(args.workdir), args.max_turns, args.allow_shell,
        )
    except Exception as e:
        print(f"executor loop failed: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.status_file, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
