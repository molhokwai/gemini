#!/usr/bin/env python3
"""
Provider routing with fallback chains.

  coding chain: deepseek -> gemini -> groq -> cerebras
  other  chain: gemini -> groq -> deepseek -> cerebras

Usage:
  # Get the next available provider for a task type
  python3 route_provider.py --task-type coding --state provider_state.json --config providers.json

  # Mark a provider as failed for the rest of this run (e.g. after a 429)
  python3 route_provider.py --mark-failed deepseek --state provider_state.json --reason "429 rate limit"

  # Reset state (e.g. at the start of a new run, or after a daily quota reset)
  python3 route_provider.py --reset --state provider_state.json
"""
import argparse
import json
import os
import sys
import time

CHAINS = {
    "coding": ["deepseek", "gemini", "groq", "cerebras"],
    "other": ["gemini", "groq", "deepseek", "cerebras"],
}


def load_json(path, default):
    if not os.path.isfile(path):
        return default
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)  # atomic on POSIX — safe against concurrent readers


def get_provider(task_type: str, config_path: str, state_path: str):
    if task_type not in CHAINS:
        print(
            f"error: unknown task type '{task_type}', expected one of {list(CHAINS)}",
            file=sys.stderr,
        )
        sys.exit(2)

    config = load_json(config_path, {})
    state = load_json(state_path, {"failed": {}})

    for name in CHAINS[task_type]:
        provider_cfg = config.get(name)
        if not provider_cfg:
            continue
        if not provider_cfg.get("enabled", False):
            continue
        api_key_env = provider_cfg.get("api_key_env")
        if not api_key_env or not os.environ.get(api_key_env):
            continue
        if name in state.get("failed", {}):
            continue
        print(
            json.dumps(
                {
                    "provider": name,
                    "model": provider_cfg["model"],
                    "base_url": provider_cfg["base_url"],
                    "api_key_env": api_key_env,
                }
            )
        )
        return 0

    tried = CHAINS[task_type]
    print(
        f"error: no available provider for task type '{task_type}'. "
        f"Tried in order: {tried}. Check providers.json (enabled + api_key_env "
        f"set in environment) and provider_state.json (not marked failed).",
        file=sys.stderr,
    )
    return 1


def mark_failed(provider: str, state_path: str, reason: str):
    state = load_json(state_path, {"failed": {}})
    state.setdefault("failed", {})[provider] = {
        "reason": reason,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_json(state_path, state)
    print(f"marked '{provider}' failed: {reason}")
    return 0


def reset_state(state_path: str):
    save_json(state_path, {"failed": {}})
    print(f"reset {state_path}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task-type", choices=list(CHAINS))
    p.add_argument("--config", default="providers.json")
    p.add_argument("--state", default="provider_state.json")
    p.add_argument("--mark-failed", metavar="PROVIDER")
    p.add_argument("--reason", default="unspecified")
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()

    if args.reset:
        sys.exit(reset_state(args.state))
    if args.mark_failed:
        sys.exit(mark_failed(args.mark_failed, args.state, args.reason))
    if args.task_type:
        sys.exit(get_provider(args.task_type, args.config, args.state))

    p.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
