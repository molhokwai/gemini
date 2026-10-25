#!/usr/bin/env python3
"""
Validate a plan.json produced by the atomic-task-sequencer skill.

Usage:
    python3 validate_plan.py path/to/plan.json

Exits 0 and prints "OK" if valid. Exits 1 and prints all errors found
(not just the first one) otherwise.
"""
import json
import sys
import os

REQUIRED_TASK_FIELDS = {
    "id": str,
    "title": str,
    "type": str,
    "depends_on": list,
    "timeout_seconds": int,
    "max_retries": int,
    "prompt_file": str,
    "expected_outputs": list,
    "verify_command": str,
    "idempotent": bool,
}
VALID_TYPES = {"coding", "other"}


def validate(plan_path: str) -> list[str]:
    errors = []
    base_dir = os.path.dirname(os.path.abspath(plan_path))

    try:
        with open(plan_path) as f:
            plan = json.load(f)
    except json.JSONDecodeError as e:
        return [f"plan.json is not valid JSON: {e}"]
    except FileNotFoundError:
        return [f"File not found: {plan_path}"]

    for key in ("plan_id", "tasks"):
        if key not in plan:
            errors.append(f"Missing top-level field: '{key}'")

    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        errors.append("'tasks' must be a non-empty list")
        return errors

    seen_ids = set()
    for i, task in enumerate(tasks):
        prefix = f"task[{i}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        for field, expected_type in REQUIRED_TASK_FIELDS.items():
            if field not in task:
                errors.append(f"{prefix}: missing field '{field}'")
            elif not isinstance(task[field], expected_type):
                errors.append(
                    f"{prefix}.{field}: expected {expected_type.__name__}, "
                    f"got {type(task[field]).__name__}"
                )

        tid = task.get("id")
        if tid is not None:
            if tid in seen_ids:
                errors.append(f"{prefix}: duplicate task id '{tid}'")
            seen_ids.add(tid)

        ttype = task.get("type")
        if ttype is not None and ttype not in VALID_TYPES:
            errors.append(
                f"{prefix}.type: '{ttype}' not in {sorted(VALID_TYPES)}"
            )

        pf = task.get("prompt_file")
        if isinstance(pf, str):
            full_path = os.path.join(base_dir, pf)
            if not os.path.isfile(full_path):
                errors.append(
                    f"{prefix}.prompt_file: '{pf}' does not exist "
                    f"(resolved to {full_path})"
                )

        timeout = task.get("timeout_seconds")
        if isinstance(timeout, int) and timeout <= 0:
            errors.append(f"{prefix}.timeout_seconds: must be > 0")

        retries = task.get("max_retries")
        if isinstance(retries, int) and retries < 0:
            errors.append(f"{prefix}.max_retries: must be >= 0")

    # dependency graph checks: unknown deps + cycle detection
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            continue
        for dep in task.get("depends_on", []) or []:
            if dep not in seen_ids:
                errors.append(
                    f"task[{i}] (id={task.get('id')}): depends_on unknown "
                    f"task id '{dep}'"
                )

    cycle = _find_cycle(tasks)
    if cycle:
        errors.append(f"Dependency cycle detected: {' -> '.join(cycle)}")

    return errors


def _find_cycle(tasks) -> list[str] | None:
    graph = {
        t["id"]: t.get("depends_on", []) or []
        for t in tasks
        if isinstance(t, dict) and "id" in t
    }
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in graph}
    path = []

    def dfs(node):
        color[node] = GRAY
        path.append(node)
        for dep in graph.get(node, []):
            if dep not in color:
                continue  # unknown dep already reported separately
            if color[dep] == GRAY:
                return path[path.index(dep):] + [dep]
            if color[dep] == WHITE:
                result = dfs(dep)
                if result:
                    return result
        path.pop()
        color[node] = BLACK
        return None

    for tid in graph:
        if color[tid] == WHITE:
            result = dfs(tid)
            if result:
                return result
    return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 validate_plan.py path/to/plan.json", file=sys.stderr)
        sys.exit(2)

    errs = validate(sys.argv[1])
    if errs:
        print(f"INVALID — {len(errs)} error(s) found:\n", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    print("OK")
    sys.exit(0)
