#!/usr/bin/env python3
"""
Starter template for the piece YOU fill in: the actual call to whichever
LLM executes a task. The orchestrator only cares that this process:

  1. Reads the rendered task prompt from --prompt-file
  2. Does the work (in this template: one OpenAI-compatible chat completion
     call, since DeepSeek/Gemini/Groq/Cerebras all expose that shape — swap
     in a real coding-agent CLI here instead if you want actual file edits
     rather than a single completion)
  3. Writes a status JSON to --status-file, EXACTLY at that path, before exiting

Fill in the TODOs. Everything else (provider selection, retries, timeouts,
verification) is handled by orchestrate.py — this file's only job is "do
the task and report honestly."
"""
import argparse
import json
import os
import sys
import urllib.request


def call_llm(base_url, model, api_key, prompt_text):
    """Minimal OpenAI-compatible chat completion call using stdlib only.
    Swap for the official SDK of your chosen provider if you prefer."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
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
    return data["choices"][0]["message"]["content"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--status-file", required=True)
    p.add_argument("--provider", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--api-key-env", required=True)
    args = p.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        # Fail loudly and let the orchestrator's crash-detection catch it —
        # do NOT write a status file claiming success here.
        print(f"Missing API key in env var {args.api_key_env}", file=sys.stderr)
        sys.exit(1)

    with open(args.prompt_file) as f:
        prompt_text = f.read()

    # TODO: replace this single-completion call with whatever actually
    # executes the task for you — e.g. shelling out to a coding-agent CLI
    # (gemini-cli, an aider invocation, a custom tool-use loop) that can
    # read/write files, run commands, etc. The completion-only version
    # below only works for tasks whose entire output IS the model's text
    # response (e.g. "write this config value", "draft this doc section").
    try:
        response_text = call_llm(args.base_url, args.model, api_key, prompt_text)
    except Exception as e:
        print(f"LLM call failed: {e}", file=sys.stderr)
        sys.exit(1)  # non-zero exit + no status file = orchestrator sees "crashed"

    # TODO: parse response_text and actually apply it (write files, etc.)
    # For a "write this file's contents" style task this might be as
    # simple as: open(target_path, "w").write(response_text)

    # TODO: the executor is supposed to determine and report its OWN
    # success/failure honestly here, based on whether it believes it
    # completed every step in the task prompt — this template just always
    # reports success, which defeats the point. Replace with real logic
    # or an explicit self-check before writing this file.
    status = {
        "task_id": None,  # TODO: parse from the task prompt header, or pass in as an arg
        "status": "success",
        "output_files": [],  # TODO: fill in what was actually written
        "notes": "TEMPLATE — replace with real completion logic",
    }
    with open(args.status_file, "w") as f:
        json.dump(status, f)


if __name__ == "__main__":
    main()
