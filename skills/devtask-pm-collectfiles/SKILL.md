---
name: devtask-pm-collectfiles
description: Explicit push to Google Drive via rclone, for pm/tasks/analysis-α-implementation (cloud-symlink, normally live-mirrored automatically), pm/scripts (this skill's own tooling, e.g. push-to-drive.sh itself), and life/ (excluded from git via .gitignore, no other backup/Drive presence at all). Trigger when the user says "push to drive", "push all files to drive", "collect files", "share these files", or names one of these trees plus Drive.
---

# Nkensa repo — Push to Google Drive (explicit)

Adapted from the generic scaffold's `devtask-pm-collectfiles` for this repo's actual shape, which is a bit unusual — **three** targets:

| Target | Local path | Why it needs this skill |
|---|---|---|
| `pm-tasks` | `pm/tasks/analysis-α-implementation` | Normally a live-mirror cloud-symlink (writes sync automatically, no push needed — see `devtask-pm` §1). This skill exists as an **explicit, on-demand** push on top of that, not a replacement for it. |
| `pm-scripts` | `pm/scripts` | This skill's own tooling (`push-to-drive.sh` itself) — pushed so it's human-browsable from Drive too, not just git. |
| `life` | `life/` | Repo folder on disk, but **excluded from git** (`/life/` in `.gitignore`) — no version control at all. This push is its *only* backup, human-browsable from Drive; local disk is the real source of truth. |

All three push via `rclone copy` (additive + idempotent — only new/changed files transfer by size+modtime, **nothing is ever deleted** on the remote, one-direction local→remote, runs only when invoked).

**`pm-tasks` and `pm-scripts` are deliberately two separate targets, not one `./pm/` push.** `./pm/tasks/analysis-α-implementation` is a symlink whose local basename (`tasks/analysis-α-implementation`, kebab-case) doesn't match the real remote folder names (`TASKS/ANALYSIS α IMPLEMENTATION`, uppercase+spaced) — pushing `./pm/` wholesale would create a parallel, wrongly-named duplicate tree instead of landing in the folder that already exists. Each target's `FOLDER_ID` is the *verified, walked-by-ID* exact remote folder, which sidesteps the naming mismatch entirely — if a new subtree under `pm/` ever needs its own Drive mirror, add it as its own named target the same way, don't try to generalize to a recursive whole-`pm/`-tree push.

## Addressing — by Drive folder ID, not by path

`rclone lsd gdrive:` does **not** show a top-level `PROJECTS` folder on this machine's configured account, even though every target's README describes its Drive location as a `PROJECTS/NKENSA/...` path. **Verified 2026-08-01, by walking the tree by ID rather than guessing**: `PROJECTS/NKENSA/PM` (root, folder id `1UusH9OBff2D4bfA1Bx9PzP0OE3QZjPw_`) contains `TASKS` (`1jme8zGZM0s19BGcTcd5klxkATJUvcsWE`) and `SCRIPTS` (`19W3nWR9JdrG6iOFmQpmel_mprAfToWjy`); `TASKS` contains `ANALYSIS α IMPLEMENTATION` (`1Gc8Ug8AJ1RgJ3kXnimGtsBWtjqSDwi34`) — all reachable and owned by this account, just not reachable by walking a `PROJECTS/...` path string from the visible root (likely a Drive shortcut/shared-location that doesn't reflect in a plain path listing). `push-to-drive.sh` therefore always addresses by **folder ID** (`--drive-root-folder-id`), never by constructing a `PROJECTS/NKENSA/...` path — that path string is documentation for a human clicking through the Drive UI, not something to feed to `rclone` directly. **When adding a new target: don't guess the ID from the path — walk down from a known-good parent ID with `rclone lsjson ... --dirs-only` one level at a time and confirm each hop, the way `PM → TASKS → ANALYSIS α IMPLEMENTATION` was confirmed.**

`pm-tasks`'s target folder came back **empty** via `rclone` before this skill's very first push (2026-08-01), despite the local live-mirror already having ~20 files — turned out to be the right folder (confirmed by the ID walk above), just never touched by `rclone` before; the OS-level Drive Desktop client doing the live-mirror sync apparently isn't depositing there (different account, or a different folder than this exact ID — still unconfirmed which). This skill's push doesn't resolve that separate mystery, it just makes sure the verified folder has current files regardless.

## The script

`pm/scripts/push-to-drive.sh` — run with `bash` (the exec bit doesn't stick on this repo's NTFS mount, same gotcha as `docgen.sh` — see `docgen` SKILL.md):

```bash
# one file
bash pm/scripts/push-to-drive.sh <pm-tasks|pm-scripts|life> "path/to/file.md"

# one folder (recursive)
bash pm/scripts/push-to-drive.sh <pm-tasks|pm-scripts|life> "path/to/folder"

# the WHOLE target tree (changed-only)
bash pm/scripts/push-to-drive.sh <pm-tasks|pm-scripts|life> --all

# preview without uploading
bash pm/scripts/push-to-drive.sh <pm-tasks|pm-scripts|life> --all --dry-run

# list what's currently on the remote
bash pm/scripts/push-to-drive.sh <pm-tasks|pm-scripts|life> --list
```

## Workflow

1. **Determine the target(s) and scope** — one file, one folder, or `--all`.
2. **Preview with `--dry-run` first** for a folder or `--all` push, so the user (or you) can sanity-check the file count/size before it actually uploads.
3. **Push.**
4. **Verify** with `--list`, or spot-check a specific file.

### When the push fails

Diagnose before falling back to a manual share: `rclone` not on `PATH` (`which rclone`), the `gdrive:` remote not authorised (`rclone about gdrive:` — should print quota, not an auth error), the folder ID wrong/inaccessible (`rclone lsd gdrive: --drive-root-folder-id <ID>` — "directory not found" means no access, not just "empty"), or a plain connectivity issue. There is no local-staging fallback wired up for this repo (unlike the generic scaffold's Method 2) — if the push can't be made to work, tell the user and stop rather than inventing a different sharing mechanism.

## Safety notes

- `rclone copy` never deletes on the remote — additive only, one-direction local→remote, runs only when invoked (no background watcher).
- `pm-tasks`'s local path is itself a symlink into a live-synced Drive mirror — this skill's push is a *second*, explicit, ID-addressed path to the same (or possibly different — see the finding above) Drive location, not a replacement for the live-mirror.
- `life/` has no other Drive presence — this skill is its only backup path. Not git-tracked (excluded via `.gitignore`) — the local disk is the actual source of truth; the Drive copy is a convenience mirror, not a second source of truth to reconcile against.
