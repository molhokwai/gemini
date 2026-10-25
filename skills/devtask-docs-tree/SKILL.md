---
name: devtask-docs-tree
description: Builds and maintains an application's documentation tree in a pm/tasks bundle, on the Klavis model — `00. Architecture/` (APP register = the app as built, DEV register = the tooling that built it) and `00. Documentation/` (a `00. Treeview.md` mapping the whole menu to its screens and backend calls in order, plus one folder per menu module holding its **Use cases** and its **Technical analysis**, all linked from the treeview). Grounded in the code, not in memory: a script extracts pages, API calls, routes, services, errors, tables and tests first. Use when the user asks to document an application or "all the modules", to create/refresh the treeview, use cases or technical analyses, to replicate Klavis's "00. Documentation / 00. Architecture" for another app, or when a shipped task changed a screen or a backend call (documentation checkpoint).
---

# Dev task — application documentation tree (Treeview + Use cases + Technical analysis)

First built for the MANSA course platform (2026-10-02, bundle `pm/tasks/analysis-α-implementation/mansa-ai-trainings-offer/`), on the model of Klavis (`~/@klavis-web/pm/tasks/analysis-and-implementation/00. Documentation/00. Treeview.md` and `00. Architecture/`, plus the per-module sections of the in-app docs `~/@klavis-web/src/assets/documentation/`).

**Relation to Klavis:** `klavis-devtask` has a *Treeview checkpoint* that fills the treeview **one branch per task**, and Klavis's in-app docs (`manifest.js`) keep six sections per module. This skill is the **full pass** (every branch at once) **plus** two files per module, and the same per-task sync afterwards. For Klavis itself, keep its French conventions and file names; for other bundles, follow the bundle's language (MANSA: English, with UI labels quoted in French).

Boundaries: file headers, bundle README, completion markers → **`devtask-pm`** §1 (cloud-symlink bundle, never `git add`). Push to Drive → **`devtask-pm-collectfiles`**. PDF/DOCX exports → **`docgen`** (on demand only).

## Output structure

```
<bundle>/
├─ 00. Architecture/
│  ├─ 00. Architecture - APP - <App> Architecture.md     the app AS BUILT (register + update protocol + journal)
│  └─ 00. Architecture - DEV - <tooling>.md              how it was built (pipeline, skills, lessons)
└─ 00. Documentation/
   ├─ 00. Treeview.md                                     menu → screens/steps → BE calls (method + route + FE fn), links
   └─ NN. <Module>/                                       one folder per menu branch (+ one "Platform (transverse)")
      ├─ NN. <Module> - Use cases.md
      └─ NN. <Module> - Technical analysis.md
```

Headers (mandatory, `devtask-pm` §1): Use cases → `parent` = Treeview, `sibling` = Technical analysis; Technical analysis → `parent` = APP register, `sibling` = Use cases; Treeview → `parent` = APP register; APP ↔ DEV are `sibling`s. Banner `-- <basename> --` with an `=` underline of the exact same length.

## Procedure (full pass)

1. **Extract the real map from the code** — never write from memory:
   ```bash
   python3 ~/.claude-nkensa/skills/devtask-docs-tree/scripts/extract_app_map.py <app-repo> > <scratchpad>/map.txt
   ```
   Pages (doc comment, components, calls), FE API functions (method, route, callers), server routes (guard → service), services (events, repos, header doc), error codes, tables, event subscribers, tests. Adapt the globs if the stack differs (the script documents its assumptions).
2. **Read the source architecture** (the proposal/analysis doc of the bundle, e.g. `02. … Implementation analysis.md`) for contexts, principles, decisions — and note where the code differs.
3. **Define the modules from the navigation:** header menu + admin menu + the hub pages (e.g. the course page and what hangs under it) + one **"Platform (transverse)"** module for what has no menu entry (webhooks, background jobs, start-up, health, config, deployment). Number them in menu order.
4. **Write the two Architecture registers.** APP: presentation + **update protocol** ("does this PR touch the architecture? yes → update the section + journal + the module's technical analysis + the treeview branch"), stack, principles as applied, contexts × tables × services × modules, layers/folders, ports & adapters, events and background work, shared reference data, configuration, deployment, journal. DEV: the tooling that built the app and the lessons kept.
5. **Write each module's two files** with the templates below — every route, function, table, event, error code and config name copied from the map.
6. **Write the Treeview:** a checklist of branches, a table *Branch | Use cases | Technical analysis* with links (spaces in paths → angle brackets: `[Use cases](<01. Home/01. Home - Use cases.md>)`), the navigation source, then the tree in a code block — screens/steps **in order**, each with its BE calls in call order (`METHOD /route   (api.function)`), "on load (parallel)" when they run together, and the target module at the end of each branch line. Finish with a dated *Journal of updates*.
7. **Verify:**
   - `python3 ~/.claude-nkensa/skills/devtask-docs-tree/scripts/check_docs.py <bundle-dir> <bundle-path-as-in-headers>` → 0 problems (paths, attribute targets, banners, treeview links).
   - Spot-check the claims that are easy to get wrong against the code: what is audited (`writeAudit` vs a field on the row), which events have subscribers, exact UI labels (from the i18n files), limits and defaults (from config / services), and **every caller** of an API function (a bare `.get(` search gives false positives — the script searches `<apiObject>.<fn>(`).
8. **Bundle README** (`devtask-pm` §1): add both folders to the tree and a branch summary each, same pass.
9. **Push to Drive** (`devtask-pm-collectfiles`, target `pm-tasks`), then report: files created, modules, what was verified.

## Template — `NN. <Module> - Use cases.md`

```
# <Module> — Use cases
> **Summary:** what the screen is for, in two sentences, with its route.
## Who uses it, and why            table Role | Main use
## Main journey                    numbered steps, UI labels quoted as shown («…»), routes in code
## Other cases                     errors, limits, alternative paths, other roles
## Diagram                         mermaid flowchart of the journey
## What it does not do             explicit limits (v1)
## See also                        Technical analysis (same folder) · 00. Treeview.md
```

## Template — `NN. <Module> - Technical analysis.md`

```
# <Module> — Technical analysis
> **Summary:** context(s), the use cases involved, the key rule — and the APP register sections it relies on (§n).
## Frontend                        table Piece | Role: pages, components, composables, api functions → METHOD /route
## Backend                         table Route | Guard | Use case | Events/audit; then Rules (domain files), Data (tables), Config
## Errors                          code (status), from the map
## Tests                           test file names (unit + components)
## Points of attention             gotchas, invariants, what must never change silently
## See also                        Use cases (same folder) · APP register · 00. Treeview.md
```

## Maintenance (per task — the documentation checkpoint)

At Ship (`devtask` Phase 4), if the task changed a screen, a step, a backend call, a rule, a table or a config reachable from a menu branch:
1. Update that branch of `00. Treeview.md` (steps and calls in order) and tick/date it.
2. Update the module's **Use cases** (journey, other cases) and **Technical analysis** (routes, rules, tables, errors, tests).
3. If the change is architectural, apply the APP register's update protocol (section + journal line).
4. Add a dated line to the Treeview's journal; re-run `check_docs.py`; push to Drive.

Skip when the task has no user-facing or architectural surface (pure refactor, tests only).

## Gotchas

- **Code first, prose second** — every name in these files must exist in the code; when unsure, grep before writing.
- **Caller detection:** search `api.fn(`, not `.fn(` (false positives were found in the first MANSA pass and corrected).
- **Audit vs record:** some decisions are stored on their own row (e.g. a refund's decided-by/note) rather than in `audit_log` — check `writeAudit` calls.
- **Links with spaces** need `<…>` in Markdown; links inside a fenced code block are not clickable — keep the link table outside it.
- On the NTFS-mounted Drive mirror, `sed -i` prints "preserving permissions… Operation not permitted" but still writes — check the result, don't retry blindly.
- Don't write these files through a `git add` — the bundle is a cloud symlink (`devtask-pm` §1).
