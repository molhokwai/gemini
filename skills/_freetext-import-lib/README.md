# freetext-import-lib

> Also hosts `intake_common.py` (2026-09-21): a small stdlib Sheets client (`Sheets`) and `llm_json()` (prompt -> provider-router -> parsed JSON), shared by `/students-grading` and the base of the generic intake engine (which also reuses `append_import.py`'s DSL prompts and fee resolver for the trigger-fed profiles) in `~/.qwen/skills/freetext-to-spreadsheet/` (profiles per sheet).

Shared library behind the `/freetext-to-jm-livraison-collecte` and `/freetext-to-registre`
skills. Not a skill itself — no `SKILL.md`, never invoked directly by name.

- `sheets_oauth.py` — dependency-free (stdlib only) Google OAuth2 "installed application" flow,
  tied to your own Google account. No service account, no `pip install`.
- `append_import.py` — reformats free text via a secondary LLM (through `/provider-router`) into
  the mini-DSL the existing "Import" (JM) / "Import Registre" (Finance) Apps Script triggers
  already understand, then appends it as a new row via the Sheets API. Never writes to
  "Dépôt / vente" or "Registre" directly — the existing triggers do all the matching/validation,
  exactly as they do for a human pasting text into the AppSheet form.

## One-time setup (do this once, not per-skill)

### 1. Google Cloud OAuth Client (Sheets API access)

1. Go to https://console.cloud.google.com/ and create a new project (or pick an existing one you
   don't mind using for this) — name it anything, e.g. "freetext-import".
2. In the left menu: **APIs & Services → Library**, search "Google Sheets API", click **Enable**.
3. **APIs & Services → OAuth consent screen**:
   - User type: **External** (unless you have a Workspace org — then Internal is fine and simpler).
   - Fill in an app name (e.g. "Freetext Import"), your email as support/developer contact.
   - Scopes: skip (not required for testing mode).
   - Test users: add `mayou.nkensa@gmail.com`.
   - Publishing status: leave in **Testing** — no need to publish/verify for personal use; test
     users can authorize a Testing-status app indefinitely (Google's 7-day refresh-token expiry
     only applies to *unverified* apps in production, not to apps kept in Testing).
4. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**.
   - Name: anything, e.g. "freetext-import-desktop".
   - Click **Create**, then **Download JSON**.
5. Save the downloaded file as exactly:
   ```
   ~/.claude-nkensa/secrets/freetext-import/client_secret.json
   ```
   (create the directory if it doesn't exist). **Never commit this file or the directory to
   git** — it's outside the skills tree specifically so a `git add -A` in the skills repo can't
   pick it up by accident.

### 2. Run the one-time authorization

```bash
python3 ~/.qwen/skills/_freetext-import-lib/sheets_oauth.py --authorize
```

This prints a URL — open it, sign in as `mayou.nkensa@gmail.com`, grant access. A token is then
cached at `~/.claude-nkensa/secrets/freetext-import/sheets_token.json` and auto-refreshes itself
for every future skill invocation — you won't need to repeat this unless that file is deleted or
the OAuth client is revoked.

### 3. LLM API keys — already handled

`append_import.py` loads `GEMINI_API_KEY`/`GROQ_API_KEY`/`DEEPSEEK_API_KEY`/`CEREBRAS_API_KEY`
straight from the nkensa project's `.env.local` (never overriding a var already exported in the
shell), so nothing to set up here — as long as at least one key stays present in that file, the
`/provider-router` "other" chain (Gemini → Groq → DeepSeek → Cerebras) has something to use.

## Manual test (bypasses the skill layer)

```bash
python3 ~/.qwen/skills/_freetext-import-lib/append_import.py \
  --target registre --text "5000f pour le marché ce matin, payé cash"
```
