---
name: life
description: Read and write the personal life/ tree — the Session Protocol from life/CONSTITUTION.md. Check current state before starting substantive work (read life/SUMMARY.md and surface life/00-meta/open-loops.md's open planned/in_progress tasks — mandatory, every run), log events across any domain (mission, family, admin, finance, work, health, writings) starting as planned/in_progress and closing out as done, keep the two-tier SUMMARY.md rolling summaries current, route ambiguous events through 90-inbox triage, and maintain the family tree (life/20-family/family-tree.csv + .md) — ask for full details (prénom, nom, date de naissance/âge) whenever a family member is mentioned and isn't already fully captured. Trigger at the start of substantive work in this repo, whenever something worth remembering happens (a decision, an incident, a completed piece of work, any life event), whenever a family member is mentioned by name, or when the user says "log this in life", "check life summary", "what's going on in life/", "log the backlog", "add to the family tree", or similar.
---

# Life Tree — Session Protocol

`life/` is the single tree everything gets recorded in — see `life/CONSTITUTION.md` for the full rationale (the Purpose and Cumulative Goal sections especially). This skill is the **fast-path operational summary** of that Constitution, for actually doing the read/log/update cycle without re-reading the whole document every time. **The Constitution is the source of truth** — if the two ever disagree, it wins; fix this skill to match (and if the disagreement is a real rule change rather than a typo here, log it in `life/00-meta/tree-changelog.md` per the Constitution's own Amendment rule, don't just silently diverge).

`life/` is a plain part of this repo on disk, but **not git-tracked** — `.gitignore`'s `/life/` excludes the whole tree, matching the Constitution's own Session Protocol wording (fixed 2026-09-07: this line used to say "plain, git-tracked," which drifted from reality and from the Constitution itself). Its only backup path is an explicit push to Google Drive via `devtask-pm-collectfiles` (`bash pm/scripts/push-to-drive.sh life ...`), not `git add`/commit.

## 1. The Tree (quick reference)

| Code | Domain | Scope |
|---|---|---|
| `00` | META | This Constitution, tree changelog, inbox triage log |
| `10` | MISSION | The revolutionary goal — doctrine, strategy, organizing |
| `20` | FAMILY | Chérie, the children, household |
| `30` | ADMIN | Legal existence — national ID, passport, admin steps |
| `40` | FINANCE | Income, expenses, budget |
| `50` | WORK | Programming, project management, entrepreneurship |
| `60` | HEALTH | Physical/mental health, routine, medical, advocacy |
| `70` | WRITINGS | Thinking/writing not yet (or never) folded into Mission |
| `90` | INBOX | Not yet triaged — must trend to zero |

`80-89` reserved. Known sub-branches: `20-family` (21 Chérie · 22 Taïna · 23 Maboma · 24 Dang · 25 Aïko Oscar · 26 Haïla), `30-admin` (31 CNI · 32 Passport), `60-health` (61 Daily routine · 62 Sunday family sport · 63 Medical · 64 Sport-for-Health advocacy). `10/40/50/70` stay flat until they earn a split. Every domain has `README.md` + `SUMMARY.md` + `events/YYYY-MM.md`.

## 2. Family Tree — detect mentions, ask for details, add

`life/20-family/` keeps two paired files as the actual family tree, kept in sync with each other:
- `family-tree.csv` — one row per person: `id,prenom,nom,relation_a_moi,relation_a_cherie,date_naissance,age_approx,statut,notes`. `id` is a bare CONSTITUTION code (`21` Chérie, `22` Taïna, …) **only** for someone with their own dedicated `life/20-family/NN-name/` sub-branch folder — not every CSV row needs to become a full sub-branch, only propose that promotion if the user wants dedicated event tracking for that person. Everyone else (co-parents, wider family) gets a **hyphenated** `20-N` id (`20-7`, `20-8`, …) instead of a bare number — **never** continue the bare-number sequence past `26` (fixed 2026-08-01: `27`/`28`/`29` were reassigned to `20-7`/`20-8`/`20-9` after realizing bare numbers in the high-20s would eventually collide with another domain's own reserved code, e.g. `30`/`31`/`32` under `30-ADMIN` — every two-digit number is potentially a reserved top-level or sub-branch code per the Constitution's own tree, so a family-tree-only id must be visibly namespaced). `relation_a_cherie` is blank for anyone with no direct relation to her (e.g. a co-parent from a different relationship) — leave it blank rather than writing "—" or "n/a".
- `family-tree.md` — the same people as an ASCII diagram + legend table, `<thisfile>`-headed, `sibling`-linked to the CSV.

**Whenever a family member is mentioned** in conversation — named for the first time, or a known person resurfaces with new context — and isn't already fully captured in the CSV:
1. **Ask for the complete details** before adding them: prénom, nom, date de naissance (or âge approximatif if the exact date isn't known/available), and their relation to the user. Don't guess or infer a surname/DOB from context — ask. It's fine to add someone with fields still marked `?` if the user gives some details now and others later; don't block the whole addition on getting every field at once, but don't silently invent a value either.
2. **Add them to both files in the same pass**: a new row in `family-tree.csv`, and a new node in `family-tree.md`'s ASCII diagram + legend table. If the person is already in the tree but a field was unknown (`?`) and is now known, fill it in rather than adding a duplicate row.
3. If this reveals a real event (a birth, a milestone, a status change), that's a **separate** `20-family` (or sub-branch) event per §4 below — the tree row is the standing record of *who*, the event log is the record of *what happened*. Don't conflate them.

Current known gaps in the tree (as of last update, 2026-08-01): Taïna's exact relation to Chérie; exact DOB for Karen Tips (20-7, ~50) and Émilie (20-10, ~38); DOB/age for Nafa (20-9, "à rechercher") and confirmation of Adil's (20-8, under 10) exact DOB; Kamdem's (20-12) surname (possibly SIMO like his brother, not stated explicitly); the prénom/nom split for Kuisseu Divine Vera (20-13, given as one block); whether `25`/`26` are correctly matched to Aïko Oscar/Haïla respectively (assigned by order of mention, not explicitly confirmed), and whether Haïla specifically still carries the "injoignable" status originally noted for `26` in general. Ask when next relevant.

## 3. Start of substantive work

1. Read `life/SUMMARY.md` — always, first, not a full `events/` scan. Read the relevant domain's own `SUMMARY.md` too if more context is actually needed.
2. **Read `life/00-meta/open-loops.md` and surface it — mandatory, every time this skill runs, not just on request.** It's short by design (only currently-open items). Mention anything overdue or due soon to the user; don't just read it silently. This is the fix for the 2026-05-01 publicités task that sat `planned` and unmentioned for nearly four months — see that file's own note.
3. **Kemetic date, once per calendar day** (added 2026-09-07, per the user's request while renaming a session `"7 Paophi, 2nd Month of the Flood (Akhet), Year 6263"` after https://calendrier-africain.netlify.app/): check `life/00-meta/last-kemetic-announcement.txt` — if it's missing or doesn't hold today's Gregorian date, invoke the global **`african-calendar`** skill (it computes today's Kemetic date offline, no network call — see that skill for the calendar system itself), announce the result in this reply, and overwrite that file with today's date (`YYYY-MM-DD`) so it doesn't repeat again the same day. There is **no tool to rename a session** — don't claim to have renamed it; instead suggest the date string as a title and note the user can apply it with `/rename` if this session isn't already named. Skip this step entirely for a trivial/non-substantive message.
4. If this is a real new piece of work (not a trivial aside), log it immediately as an event, `status: planned` (or `in_progress` if already underway). This same entry gets **updated** at the end, never duplicated — and gets a line in `open-loops.md` in the same pass (§4).

## 4. End of work — logging what happened

1. Update that same event entry in place (or append fresh if nothing was pre-logged): `status` → `done` / `cancelled` / `recurring`, outcome added to the body.
2. Update the domain's `SUMMARY.md` in the **same pass**, and the `life/SUMMARY.md` line for that domain if it materially changed. A summary that's fallen out of sync is worse than no summary.
3. **Sync `life/00-meta/open-loops.md` in the same pass**: a new `planned`/`in_progress` entry gets a line added; a closed one gets its line removed (the history stays in the domain's own `events/*.md` regardless — this file only tracks what's still open).
4. **If `open-loops.md` changed, push just that file to Drive**: `bash pm/scripts/push-to-drive.sh life "00-meta/open-loops.md"`. This is the one exception to the otherwise on-demand-only Drive push convention — a daily scheduled cloud routine reads this file from Drive (see Constitution §Session Protocol) to send a once-a-day reminder, since cloud agents can't see the local disk and `life/` isn't git-tracked.
5. An entry left at `planned`/`in_progress` is an open loop, same as an uncleared inbox item — it gets closed out, not left to linger across sessions. `open-loops.md` is what makes that enforceable instead of aspirational.

## 5. Event format — exact

```markdown
## YYYY-MM-DD [HH:MM] · <code> <DOMAIN> · <short title>

- status: done | planned | recurring | cancelled
- tags: comma, separated, tags
- amount: <number>            # optional — finance or any quantifiable event
- currency: XAF | EUR | ...   # optional — only alongside amount

Free-text body — as much detail as warranted.
```

Lives in `<domain-path>/events/YYYY-MM.md`. Same schema everywhere — Finance gets no special format, it just uses `amount`/`currency` more often.

Insert **newest-first** — right after the file's `# <DOMAIN> — YYYY-MM` header, ahead of everything already there. (Fixed in Constitution v4, 2026-08-01: v3's prose said "appended at the end, in chronological order," but that never actually matched practice in any domain's `events/*.md` — the rule was corrected to match reality instead of the other way around. If you ever find another file that still isn't newest-first, that file drifted — fix the file, the rule stands.)

## 6. Triage — domain unclear

Log immediately in `90-inbox/events/` as-is, don't block on classifying it. On review — at least weekly for the user, or opportunistically whenever this skill runs and inbox isn't empty — either redirect it to the right branch/sub-branch, propose a new sub-branch (if a recurring gap shows up), or propose a new top-level branch (code from `80-89`, confirm with the user, log in `tree-changelog.md`). `90-inbox` must trend toward zero; it's never a permanent second home.

## 7. Backlogging past events

Not everything is logged live — some things (e.g. a recurring routine that lapsed for a few weeks) get logged after the fact. When backlogging:
- Use the event's **own actual date** in the heading, never today's date.
- Ask the user for the real date if it isn't already known — never guess or fabricate one.
- Fine to log straight to `status: done` (or `recurring`) — no need to fake a `planned` phase for something already fully in the past.

## 8. Language

Structural elements (folder/field names, this skill) stay English. Event **content** is whatever fits — French and English for now, moving deliberately toward Bamoun and Bassâ per the Constitution's Language Convention. Don't force a language that doesn't fit the moment being recorded.

## 9. Read-only check-ins

Not every invocation logs something new — "what's going on in life/" or "check my life summary" is a valid, read-only use: just read `life/SUMMARY.md` (+ the relevant domain `SUMMARY.md` if asked for more) and report back. Don't write anything unless there's an actual event to record.
