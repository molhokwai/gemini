---
name: freetext-to-registre
description: Turns free text (a sentence, a voice-note transcript, a quick note) describing a personal or JM financial transaction or life event into a row in the "Registre" sheet of "Registre Financier — life/". Use this whenever the user wants to save/log/record a transaction, an expense, an income, a payment, a financial event, or asks to add something to "the register"/"Registre" — phrases like "log this transaction", "save this to the register", "add this expense", "j'ai dépensé...", "enregistre cette transaction", "note ça dans le registre". Not for JM delivery/collection point data (use freetext-to-jm-livraison-collecte for that).
---

# Freetext → Registre

Reformats free text into the mini-DSL that `processImportRegistreEnAttente()`
(`life/40-finance/45-registre-import.gs`) already parses, then submits it through that exact
trigger — never writes to "Registre" directly. This means every existing safety net (dynamic
header matching, non-blocking validation, numeric extraction, already-processed-row detection)
applies here exactly as it does when a human pastes text into the AppSheet "Import Registre" form.
Full design rationale: `life/50-work/66-freetext-import-skills-request.md`.

## When invoked

1. Take the user's free text (from the invocation args, or ask for it if not given).
2. Run (the engine's `registre` profile — same behaviour as before, plus `--dry-run`):
   ```bash
   python3 ~/.qwen/skills/freetext-to-spreadsheet/scripts/intake.py --profile registre --text "<the free text>"
   ```
   **When the text is long, spans several days, or is ambiguous, review first**: run the same command with
   `--dry-run` (it prints the reformatted DSL and writes nothing), check the `## <date>` blocks and values with the
   user (mixed "yesterday … this morning" texts have been seen collapsing under one date), then submit exactly the
   approved text with `--dsl "<the DSL>"` (skips the LLM; `<calculate/>` fee tags are still resolved). `--no-wait`
   skips the 20 s poll; `--check` shows the status of the latest Import row.
3. Report back to the user:
   - The reformatted DSL text the LLM produced (so they can sanity-check it).
   - The row number added to "Import Registre".
   - The trigger's `Statut`/`Résultat` once processed (the script polls for up to 20s) — including
     any warnings (unrecognized Poste/Bénéficiaire, etc.). If still "En attente" after the poll
     window, say so plainly rather than guessing what happened.

## First-time setup required

If the script errors about a missing OAuth token or client secret, or about no available LLM
provider, stop and point the user at `~/.qwen/skills/_freetext-import-lib/README.md` —
this is one-time infra setup (a Google Cloud OAuth client + at least one LLM API key), not
something to work around per-invocation.

## Judgment calls

- If the free text is ambiguous about `Statut` (prévu vs réel), default to `réel` only if the
  text clearly describes something that already happened; otherwise leave the LLM to infer from
  tense/wording, and flag the ambiguity to the user in your report rather than silently picking.
- Never fabricate a `Poste` or amount that isn't in the source text — an incomplete row (missing
  optional fields) is fine; a guessed one is not, since it's real accounting.
- `Compte` is a deliberate exception (2026-09-16): if the text names no payment method, the
  reformatting prompt defaults it to `Cash` (the most common unspecified-account case) rather
  than leaving it blank. Still flag it in your report so the user can correct it if the default
  is wrong for that transaction — see `_freetext-import-lib/append_import.py`'s `dsl_doc` for the
  exact rule text.
- `Heure` is a similar deliberate exception (2026-09-17): if the text names no specific time, the
  reformatting prompt defaults it to the current time (the moment the script runs) rather than
  leaving it blank. Still flag it in your report so the user can correct it if the transaction
  actually happened at a different time — see `_freetext-import-lib/append_import.py`'s `dsl_doc`
  for the exact rule text.
- If the text describes multiple distinct transactions, that's fine — the DSL supports multiple
  data lines under one or more `## <date>` blocks; the underlying script/prompt already handles
  this.
- Orange Money fees (2026-09-17, tables + source/history in `life/40-finance/46-frais-orange-money.md`
  — note that file's own history: the first formula was verified against a real receipt, then
  *replaced* by tables the user supplied on 2026-09-17 that contradicted that receipt; on 2026-09-19 a
  second real receipt (withdrawal 32 000f → 388f) confirmed the original 0.2%+4 transfer formula and
  gave withdrawal = 1.2%+4, so the code was recalibrated to the receipts (v4). If a future receipt
  contradicts them again, flag it and ask, don't just silently re-derive another formula).
  Deposits (cash↔Orange Money, both legs your own accounts) are always free — never add a fee line
  for those, just the two opposite-sign internal-transfer lines.
  A transfer to someone else explicitly described as going "through/via Orange Money" gets **three
  lines by default**: (1) the main transaction, (2) a transfer-fee line always charged to the
  sender's Orange Money account, (3) a withdrawal-fee top-up sent to the beneficiary so they still
  net the full amount after paying their own withdrawal fee — omitted only if the source text
  explicitly vetoes it ("pas de frais de retrait" / "sans complément retrait" / "retrait gratuit").
  **The LLM never computes the fee numbers itself** — it got this wrong twice (once on the transfer
  fee's arithmetic, once by using the wrong formula for the withdrawal top-up). Instead the
  reformatting prompt has it emit `<calculate what="transaction_fees|withdrawal_fees"
  source_amount="…" compte="Orange Money" transaction_type="transfer|deposit"/>` placeholders in
  place of each amount, which `append_import.py`'s `resolve_calculate_tags()` resolves
  deterministically in Python before the row is ever sent to the sheet — see that function and
  `_compute_transaction_fee`/`_compute_withdrawal_fee` for the actual formulas, and the dsl_doc's
  worked 3-line example for the exact shape expected. If a future run ever shows a literal
  `<calculate...>` tag in the reformatted DSL output, that's a bug (the tag failed to resolve) —
  don't let it reach the sheet, fix the resolver instead.
