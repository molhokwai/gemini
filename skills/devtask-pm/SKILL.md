---
name: devtask-pm
description: Nkensa repo task & project-management workflow — pm/tasks reference files, append-only version log, commit/push convention, rollback, and the conditional register checkpoints (Cost, Architecture, Dev Tooling, Backlog, Future). Trigger whenever the user says "commit this", "git acp this", "give me the rollback commit", references a file under pm/tasks/, or asks to open a PR.
---

# Nkensa repo — Dev Task & Project Management

The **non-visual** parts of the dev workflow for this repo: reference files, commit/push, rollback, and the register checkpoints. Adapted from the generic scaffold at `ai/claude/skills-pm-scaffold/skills/devtask-pm/SKILL.md` for this repo's actual shape: **solo, single-repo, GitHub-hosted, no required approver**.

## 0. Reuse-first

Before building something new in this repo, check whether it already exists — `life/CONSTITUTION.md`'s tree, `ai/claude/` for existing AI tooling, `projects/*` for existing client work, `shortcuts/` for existing utility scripts. Grep before adding a parallel mechanism.

## 0.5. Nuance: locate the actual git repo before running git

This skill's "single-repo" framing assumes the working directory *is* the repo root — true for a repo like `nkensa` (git at the project root, e.g. `~/.claude`). It is not universally true: some projects keep the git repo(s) nested in a subfolder rather than at the project root — e.g. a project root with no `.git` of its own, but `./src/api/` and `./src/web/` each their own git repo (a multi-repo layout, not a monorepo).

Before any `git` command (`add`, `commit`, `push`, `status`, branch ops), confirm which repo you're actually in:
1. `git -C <target-dir> rev-parse --show-toplevel` — if it errors, the target isn't inside a git repo at all; don't assume the project root is one.
2. If a project has multiple independently-committable git roots (like `src/api/` + `src/web/` above), treat each as its own repo for commit/push purposes — a change spanning both is **two commits in two repos**, not one, even if the user's request reads as a single task. Say so before committing rather than silently picking one.
3. Don't default to running `git` from the project root out of habit — `cd`/`git -C` into the actual repo root first, or every subsequent git command in this skill (§4 commit convention, §5 workflow, §9 safety rails) operates on the wrong tree or just fails.

## 1. Reference files — cloud-symlink only, no in-repo registers

- **`pm/tasks/analysis-α-implementation/`** — a symlink to `/media/nkensa/win11/Files/Projects/Nkensa/analysis-α-implementation`, a live-synced local mirror of a Google Drive folder (no push script needed — writes sync on their own). This is where per-task reference files live, and it's the *only* thing under `pm/tasks/` in this repo. **Never `git add` anything through this symlink** — git errors "beyond a symbolic link"; edit directly with `Write`/`Edit` and it persists via the Drive sync, not via git.

Each `<topic-slug>/` folder under it takes one of two shapes, picked by size — same tree, no separate mechanism:
- **Single-file task** (the common case): `<topic-slug>/<topic-slug> - Implementation Analysis.md` — one plan/decision record for one dev task.
- **Sub-project bundle** — when the task's own *output* is a self-contained set of documents rather than code (e.g. a training curriculum, a client deliverable pack, a multi-doc brief), the topic-slug folder holds a numbered sequence instead: `00. <Title>.md`, `01. <Title>.md`, … Each file gets its own `<thisfile path="..." parent="..."/>` header (§1 of the generic scaffold's template — `parent` points at the `00.` file the others elaborate). Generated exports (`.pdf`/`.docx` via the `docgen` skill) sit next to their source `.md`, same folder — **on demand only**: export when a file is actually needed for distribution outside the editing tool, never automatically after every edit. A source `.md` with no export next to it, or with a stale one, is the expected steady state, not a bug to fix proactively. This mirrors how Klavis's own `pm/tasks/.../v1.0.4 GoToMarket/` version-project folders bundle a `00. Master Plan.md` alongside its derived docs (see `docgen` SKILL.md §1) — same idea, applied per-topic-slug here rather than at a repo-wide version layer, since this repo doesn't ship named versions (see §8). `projects/mansa/src/dev/projects/ai-training/` → `pm/tasks/analysis-α-implementation/mansa-ai-training/` (2026-07-30) is the first instance: the training brief and generated training document for MANSA's AI training, moved here from `projects/mansa/` because it's a reference/decision-record deliverable (edited outside git, shared via Drive), not app code — `projects/mansa/` stays for the actual client app source. This bundle also carries a `00. Brand,Templates/` sub-folder (logo/template assets + `brand.json` + `00. Brand rules.md`) — see `docgen` SKILL.md §2 for the branding mechanism, and that bundle's own `00. Brand rules.md` for a MANSA-specific convention worth knowing about generally: MANSA project reference codes (`PROJ/MANSA/<date>-<NN>`) use an **African (Kamit) calendar date, not the Gregorian one** — never compute or guess that conversion; ask the user or check https://calendrier-africain.netlify.app/ if it isn't already known this session.

There is no separate in-repo register system for this repo — see §8: all registers are disabled here. `life/CONSTITUTION.md`'s own event-logging + Session Protocol already covers the "don't lose track of what happened" need at the scale this repo operates at.

See `pm/tasks/analysis-α-implementation/README.md` for more.

Only substantial tasks need a reference file (per `devtask`'s Scale-to-the-task judgment) — a one-line `life/50-work` event entry is enough for small things.

## Gotcha: verify a cloud-symlink resolves cleanly — don't trust a single check at creation time (2026-07-30)

**What happened**: right after `ln -s /media/nkensa/win11/Files/Projects/Nkensa/analysis-α-implementation pm/tasks/analysis-α-implementation`, `readlink -f` on it looked correct (single-level, resolving straight to the real folder). Sometime after that — after files had been written through it — the symlink was found resolving into a **duplicated nested path**, `.../analysis-α-implementation/analysis-α-implementation`, instead of the intended single level. Exact mechanism unconfirmed; the prime suspect is that the real target sits on an NTFS/fuseblk mount (`/media/nkensa/win11`) that a Windows-side Google Drive Desktop client syncs independently of this Linux session — a passing check right after `ln -s` doesn't guarantee the symlink (or the synced folder under it) stays that shape once an external, out-of-session process touches the same tree.

**Fix applied**: the user recreated the symlink pointing at the correct single-level path and moved the misplaced file back into it.

**How to avoid it next time** — for *any* symlink into a live cloud-synced mirror, not just this one:
1. `readlink -f <symlink>` immediately after `ln -s`.
2. **Don't stop there** — check again after giving any external sync client a moment to process the folder, and diff the two results.
3. Self-reference sanity check: confirm the resolved path does **not** repeat its own basename consecutively (`.../<name>/<name>`) — that's the exact shape this incident took.
4. After the *first* write through the symlink, verify by listing the **resolved real path directly** (`find <resolved-path> -maxdepth 2`), not just by reading back through the symlink — a duplicated-nesting bug can still read back "correctly" through the symlink itself while the real tree underneath has drifted.
5. Treat a cloud-symlinked path whose target is synced by something outside this session's control as needing **periodic re-verification**, not a one-time check.

**File header — mandatory on every file under `pm/tasks/analysis-α-implementation/`** (single-file task or sub-project bundle alike; the only exemption is a plain navigation `README.md`, per the Klavis precedent this convention is ported from). Not optional, not "when it seems warranted" — every `.md` in the tree gets one. Modeled exactly on the canonical example at `Klavis/ANALYSIS α IMPLEMENTATION/00. Architecture/00. Architecture - APP - AI Architecture.md`:

```
<thisfile
	path="<repo-relative path to this file, e.g. ./pm/tasks/analysis-α-implementation/<topic-slug>/<file>.md>"
	sibling="<path to a parallel/paired file, if any>"
	parent="<path to the file this one elaborates/derives from, if any>"
	related="<path to a loosely-connected file, if any — catch-all for a forward link that isn't parent/sibling>"
/>

-- <Title> --
===========
```

Rules, exact — verified against the canonical example, not approximate:
- **Attributes are tab-indented** (one tab, not spaces), only the attributes that actually apply are present (omit unused ones entirely — never write `parent="(if any)"` as a literal placeholder).
- **`<Title>` is the file's own basename without the `.md` extension** — e.g. `01. Training Document.md` → `-- 01. Training Document --`. Don't editorialize it into a different, longer, more descriptive title; the descriptive title (if wanted) belongs in the body's first `#` heading, not the banner.
- **The `=` underline's length equals the exact character count of the `-- <Title> --` line above it** — count it, don't eyeball it or default to a fixed-length rule.
- **This banner appears exactly once per file, at the top.** Every section within the file's body uses plain Markdown headings (`#`, `##`, `###`) — never a second `-- ... --` banner. (The `docgen` skill's export pipeline strips the top banner and any `-- N. Title --`-shaped line before rendering; a body that reused the banner style for internal sections would get stripped, which is precisely why it's reserved for the top only.)

**Per-bundle `README.md` — created once, kept current thereafter** (added 2026-08-03). Each substantial `<topic-slug>/` bundle (sub-project bundles especially, per the shape above) gets its own `README.md` at the bundle's root — the one file exempt from the `<thisfile>` header, per the rule above. Purpose: an always-current *short* snapshot of the whole bundle, readable for orientation instead of scanning every file underneath it — same idea as `life/CONSTITUTION.md`'s Session Protocol `SUMMARY.md` files, scoped to one engagement/task bundle instead of the whole tree.

Structure, exact:
1. **Global summary** — one paragraph: what this engagement/task is, for whom, current status (what's decided, what's still open, the next real milestone).
2. **Tree** — a fenced treeview of the bundle's *actual* current contents — reflect reality, not an aspirational future shape.
3. **Branch summaries** — one short bullet per top-level file/folder ("branch"): what it is and why it exists, not a restatement of its title.

**Maintenance discipline**: update the relevant branch summary (and the global summary if it materially changed) in the same pass as whatever change prompted it — a stale snapshot defeats its own purpose, same principle as the Session Protocol's "a summary that's fallen out of sync is worse than no summary."

**Manual-edit marker convention**: if the user edits the README directly — a correction typed straight into the file, bypassing the usual AI-driven update — mark the touched bullet/sentence with **Manually updated** inline, so a later AI-driven pass can tell a human specifically chose that wording and folds new information in rather than silently overwriting it. Don't strip the marker on a later legitimate update; fold new information into the same bullet without erasing the record that a human touched it, unless the user says otherwise.

**Completion markers — ✅ / ❌ suffix on reference files.** When all the work described in a reference file (or a `<topic-slug>/` bundle) is done, mark it by appending a checkmark to the file/folder name itself — e.g. `mansa-ai-training - Implementation Analysis.md` → `mansa-ai-training - Implementation Analysis ✅.md`. When work had to be stopped or couldn't be completed, mark it with a cross instead.

Judge from the file's own content: an explicit "done"/merge confirmation, a checklist with every item `[x]`, or a `# N. Next version ... Ok` version-log entry → ✅. The file itself saying work was interrupted or abandoned mid-way (not merely deferred) → ❌. Leave unmarked anything genuinely still open/in-progress, deliberately deferred-but-never-attempted, or ambiguous/mixed — don't force a marker where the evidence doesn't support one; flag the ambiguity instead of guessing.

Renaming mechanics: update the file/folder name and its own `<thisfile path="...">` self-reference (and any `parent=`/`sibling=`/`related=` tags in other files pointing at it) in the same pass — these live behind the Drive-sync symlink (§1), so rename with a plain `mv`, never `git mv`.

Unlike the Klavis skills, this repo has no Backlog register (§8 disables all registers) — so the Klavis version's "already tracked in the Backlog register" carve-out doesn't apply here: a deferred sub-item should instead be noted inline in the reference file itself (or in `life/50-work`, per this repo's own scale judgment) before it's treated as non-blocking for a ✅.

**Per-task checklist**, immediately after the task description:

```
## Checklist
- [ ] 1. <step>
- [ ] 2. <…>
```

Check items off as they land; reference the current item in commit bodies and version-log entries.

## 2. Version log — lives in the reference file

When one exists, the running log of base-version commits is appended to *that task's* reference file, not to this skill. Session-dependent — don't assume continuity across sessions; if a previous session's reference file is implied but stale (idle > ~1 day), confirm it's still current before appending.

Each time the user says **"commit this / make it the new base version"**, and a reference file is active:

1. Commit, push, get the new SHA.
2. Append below the last `# N. Next version` block:
   ```
   # <N+1>. Next version: <summary> Ok
   Rollback commit: `git reset --hard <sha>`
   ```

**Never delete** existing content — append-only.

## 3. Branch naming (optional — see the solo-repo note below)

```
dev/<YYYYMMDD>/<Subject>
```

- `<your-name>` — this repo has one developer; use `git config user.name` if a name is ever needed in a note or commit body (currently `molhokwai`).
- No `<your-role>` variable — solo repo, no role attribution needed.
- `<Subject>` is PascalCase, concise.

**Solo-repo note**: branching is *available*, not mandatory. For anything trivial-to-small (per `devtask`'s Scale judgment), committing directly to `main` — as this repo has always done — is fine. Reach for a branch when a change is large enough that you'd want to review the whole diff before it lands, or risky enough that a clean rollback point matters more than usual (e.g. a repo-wide reorg).

### `git checkout` helpers (when branching)

```bash
git checkout main && git pull
git checkout -b dev/<YYYYMMDD>/<Subject>
```

Never force-push to `main`.

## 4. Commit / push convention

```
<type>(<scope>): <summary>

<bullet-list-body>

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

(Match the `Co-Authored-By` line to whichever Claude model is actually running the session, not a fixed string.)

- **Type**: `feat`, `fix`, `chore`, `refactor`, `docs`, `tooling` — match the change.
- **Scope**: the top-level folder or system touched — `life`, `ai/claude`, `projects/<name>`, `shortcuts`.
- **One concern per commit.** When a session produces several unrelated deliverables (as the `life/` tree, the quick-task subagent, and the skills scaffold each did in one session), commit them **separately** — don't bundle. This is the repo's established practice, not a hypothetical rule.
- Always pass the message via a HEREDOC:

  ```bash
  git commit -m "$(cat <<'EOF'
  <type>(<scope>): <summary>

  - bullet 1
  - bullet 2

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

## 5. Commit/push workflow (the core interaction)

After each agreed milestone, on **"commit this" / "git acp this"**:

1. `git add <specific files>` — **never** `-A` or `.`.
2. `git commit` with the HEREDOC format above.
3. `git push` (to `main` directly for small changes, per §3; to the feature branch if one is in use).
4. If a reference file is active, append a "Next version" block (§2).
5. Reply with the rollback command:
   ```
   git reset --hard <new-commit-sha>
   ```

## 6. Rollback workflow

- **"rollback the last commit"** → `git reset --hard <previous-sha>` (or `HEAD~1`).
- **"rollback to version N"** → use the reference file's `# N. Next version` entry.
- **"discard my uncommitted changes in file X"** → `git checkout -- <file>`.

Use git — never reconstruct a prior state from memory.

## 7. PR/MR (only when branching)

If a branch was used (§3), open a PR into `main` on GitHub (`molhokwai/nkensa`) — self-review, no required external approver for this repo. **Propose the title + body first** and wait for confirmation before opening (same discipline as a team repo, even solo — it's a cheap check against a rushed diff):

- Title: `<type>(<scope>): <summary>`.
- Body: **Summary** (1-3 lines), **Commits** (one line each), per-area sections (how + gotchas), **Test plan**.

Open via `gh pr create` only if asked; otherwise hand over title + body for manual opening.

## 8. Registers — disabled for this repo

The generic scaffold (`ai/claude/skills-pm-scaffold/skills/devtask-pm/SKILL.md` §7.1) defines seven conditional ship-time registers (Cost, App Architecture, Dev Tooling, Design, Backlog, Future, Version Closure). **None are instantiated here** — `life/CONSTITUTION.md`'s own event-logging + Session Protocol (log `planned`/`in_progress` at start, `done` at end, roll up into `SUMMARY.md` files) already covers what the registers exist for, at the scale this repo actually operates at, without a second parallel system to keep in sync.

If a specific register ever earns its keep here (e.g. Claude Code spend tracking growing beyond what `claude-budget-cap/` already covers), re-enable it by following the scaffold's own instantiation pattern — a register is just one question + one append-only file.

## 9. Safety rails

- **Never** `git add -A` or `git add .` — always name the files.
- **Never** `--amend` a pushed commit — create a new commit.
- **Never** `--no-verify` without explicit permission.
- **Never** force-push to `main`.
- **Never** commit `.env` files, secrets, credentials, or large binaries. (Note: `shortcuts/github-recovery-codes+pat+psws.txt` is a known pre-existing exception the user is handling separately — don't treat its presence as license to add more.)
- **Never** try to `git add` anything under `pm/tasks/analysis-α-implementation/` — it's a symlink to a cloud-synced mirror, not part of the repo; git will refuse ("beyond a symbolic link"). Edit those files directly and let the Drive sync carry them.

## 10. Naming

Name every artifact explicitly and self-describingly — longer is fine if it adds clarity. Disambiguate the generic (a qualified noun over a bare one) and stay consistent across related artifacts (a script, its README, its config should share a root name).

## 11. Document language

This repo is deliberately mixed-language — see `life/CONSTITUTION.md`'s own Language Convention (structural elements in English, content in whatever fits, moving toward Bamoun/Bassâ over time). Reference files and commit messages follow the same rule: no fixed doc language requirement here.
