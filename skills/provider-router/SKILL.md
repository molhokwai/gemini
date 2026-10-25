---
name: provider-router
description: Picks which cheap/free LLM API (DeepSeek, Gemini, Groq, Cerebras) should execute a given atomic task, with automatic fallback when a provider is disabled, out of quota, or erroring. Use this whenever the user is routing tasks across multiple LLM API providers, asking "which provider should handle X", building a fallback chain for API calls, or running the executor-orchestrator skill (which calls this for every task before dispatch). Coding tasks route DeepSeek → Gemini → Groq → Cerebras; everything else routes Gemini → Groq → DeepSeek → Cerebras.
---

# Provider Router

Deterministic, config-driven routing: given a task's `type` (`"coding"` or `"other"`), returns the next available provider + model + API config, trying each in order and falling back automatically.

## Routing chains

| Task type | Order | Rationale |
|---|---|---|
| `coding` | DeepSeek → Gemini → Groq → Cerebras | DeepSeek has meaningfully better code quality per dollar; worth spending its (cheap, not-quite-free) tokens first when the task actually is code generation. Requires the manager to keep the DeepSeek subscription/credits topped up — this chain silently falls through to Gemini if DeepSeek is disabled or out of quota, so nothing breaks if they don't. |
| `other` | Gemini → Groq → DeepSeek → Cerebras | Gemini's free tier has the best combination of quality and daily volume for non-coding tasks (config edits, doc generation, data transforms, verification write-ups). Groq as the fast fallback; DeepSeek held back since its strength (code quality) isn't the bottleneck for non-coding work. |

Cerebras sits last in both chains — it's the highest-volume free tier (1M tokens/day, no card) but weakest model roster, so it's the "the other three all failed or are exhausted" safety net, not a first choice.

## How routing decisions are made

`scripts/route_provider.py` reads `providers.json` (config: which providers are enabled, their env var names for API keys, model names, base URLs) and a per-run `provider_state.json` (which the orchestrator updates as it hits failures/quota errors), then returns the first provider in the relevant chain that is:

1. **Enabled** in `providers.json` (the manager can flip `"enabled": false` any time — e.g. if the DeepSeek subscription lapses)
2. **Has an API key present** in the environment (checked by env var name, not stored in the config file itself — never put API keys in `providers.json`)
3. **Not marked quota-exhausted or erroring** in `provider_state.json` for the current run

If none qualify, it exits non-zero with a clear message — the orchestrator treats this as an immediate escalation to the planner (see `executor-orchestrator`'s escalation path), since it means the whole pipeline is stuck, not just one task.

## Usage

```bash
python3 scripts/route_provider.py --task-type coding --state provider_state.json --config providers.json
```

Prints JSON to stdout:
```json
{"provider": "deepseek", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1", "api_key_env": "DEEPSEEK_API_KEY"}
```

## Marking a provider as failed mid-run

When the executor wrapper gets a 429 (rate limit) or a hard API error from a provider, it should call:

```bash
python3 scripts/route_provider.py --mark-failed deepseek --state provider_state.json --reason "429 rate limit"
```

before requesting the next provider in the chain. This is per-run state (lives next to the plan.json, not global) — a fresh run starts with a clean slate and will retry providers that were marked failed in a previous run, since quota often resets daily.

## Setting up `providers.json`

Copy the template below, fill in real model names/base URLs for whichever SDKs you're using (all four providers expose OpenAI-compatible endpoints, so the executor wrapper can use one HTTP client for all of them), and never commit real API keys — only the env var *names* go in this file.

```json
{
  "deepseek": {
    "enabled": true,
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "api_key_env": "DEEPSEEK_API_KEY"
  },
  "gemini": {
    "enabled": true,
    "model": "gemini-2.5-flash",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "api_key_env": "GEMINI_API_KEY"
  },
  "groq": {
    "enabled": true,
    "model": "llama-3.3-70b-versatile",
    "base_url": "https://api.groq.com/openai/v1",
    "api_key_env": "GROQ_API_KEY"
  },
  "cerebras": {
    "enabled": true,
    "model": "llama-3.3-70b",
    "base_url": "https://api.cerebras.ai/v1",
    "api_key_env": "CEREBRAS_API_KEY"
  }
}
```

Model names and free-tier limits change often — double-check current values against each provider's docs before relying on this in production; don't assume the values above are still accurate by the time you read this.
