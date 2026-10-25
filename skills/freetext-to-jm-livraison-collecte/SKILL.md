---
name: freetext-to-jm-livraison-collecte
description: Turns free text (a sentence, a voice-note transcript, a quick note) describing a JM cake/ice-cream delivery, sale, or collection at a point into a row in the "Dépôt / vente" sheet. Use this whenever the user wants to log/save/record a JM livraison, vente, or collecte, or mentions delivering/selling/collecting product at a point — phrases like "log this delivery", "save this collection", "j'ai livré...", "collecte chez...", "enregistre cette livraison JM". Not for JM's own money transactions or personal finance (use freetext-to-registre for that — JM's own ledger was folded into Registre on 2026-09-15).
---

# Freetext → JM Livraison/Collecte

Reformats free text into the mini-DSL that `processImportEnAttente()`
(`life/50-work/52-jm/55-jm-livraisons-import.gs`) already parses, then submits it through that
exact trigger — never writes to "Dépôt / vente" directly. This means every existing safety net
(dynamic header matching, non-blocking Nom matching against "Points de dépôt / vente", numeric
extraction, already-processed-row detection) applies here exactly as it does when a human pastes
text into the AppSheet "Import Livraisons+Collecte JM" form. Full design rationale:
`life/50-work/66-freetext-import-skills-request.md`.

## When invoked

1. Take the user's free text (from the invocation args, or ask for it if not given).
2. Run (the engine's `jm-livraison` profile — same behaviour as before, plus `--dry-run`):
   ```bash
   python3 ~/.qwen/skills/freetext-to-spreadsheet/scripts/intake.py --profile jm-livraison --text "<the free text>"
   ```
   **When the text is long, spans several days, or is ambiguous, review first**: run the same command with
   `--dry-run` (it prints the reformatted DSL and writes nothing), check the `## <date>` blocks and values with the
   user (mixed "yesterday … this morning" texts have been seen collapsing under one date), then submit exactly the
   approved text with `--dsl "<the DSL>"` (skips the LLM; `<calculate/>` fee tags are still resolved). `--no-wait`
   skips the 20 s poll; `--check` shows the status of the latest Import row.
3. Report back to the user:
   - The reformatted DSL text the LLM produced (so they can sanity-check it).
   - The row number added to "Import".
   - The trigger's `Statut`/`Résultat` once processed (the script polls for up to 20s) — including
     any warnings (unrecognized point Nom, etc.). If still "En attente" after the poll window, say
     so plainly rather than guessing what happened.

## First-time setup required

If the script errors about a missing OAuth token or client secret, or about no available LLM
provider, stop and point the user at `~/.qwen/skills/_freetext-import-lib/README.md` —
this is one-time infra setup (a Google Cloud OAuth client + at least one LLM API key), not
something to work around per-invocation.

## Judgment calls

- Never invent a point Nom, quantity, or date that isn't clearly in the source text — an
  unrecognized Nom is fine (the trigger flags it non-blockingly), a fabricated one is not.
- If the text names a point ambiguously (e.g. a nickname or partial name), pass it through as
  written rather than guessing which real "Points de dépôt / vente" entry it maps to — the
  trigger's own soft matching, and the user's own review of the warning, are the right place to
  resolve that, not this skill.
- If the text describes multiple points/deliveries, that's fine — the DSL supports multiple data
  lines under one or more `## <date>` blocks.
