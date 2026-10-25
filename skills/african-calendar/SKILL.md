---
name: african-calendar
description: Computes today's (or any) date in the "Calendrier Africain Kamit" / Kemetic calendar system from https://calendrier-africain.netlify.app/ — a fixed 365-day year with no leap years, 12 months of 30 days across 3 seasons (Akhet/Flood, Peret/Recession, Chémou/Harvest) plus 5 épagomenal days, epoch An 6262 = 2025-08-02 CE. Pure offline arithmetic, no network call. Use whenever the user asks for today's date "in the African/Kemetic/Egyptian calendar", wants a session or document dated that way, asks to convert a Gregorian date to/from it, or another skill (e.g. `life`'s Session Protocol) needs to announce or stamp the current Kemetic date.
---

# African Calendar (Kemetic)

Global, project-agnostic skill — usable in any Kimi Code session. Computes dates in the Kemetic calendar shown at https://calendrier-africain.netlify.app/, reverse-engineered from that page's own inline Vue script (fetched + inspected 2026-09-07) rather than scraped live — so it works offline, instantly, and without depending on the site being up.

## The calendar system

- **Fixed 365-day year, no leap years.** The Gregorian calendar is the one that drifts (leap years); this one never does — per the site's own framing, Gregorian is "a modified copy, born 4,256 years later."
- **12 months of 30 days**, grouped into 3 seasons of 4 months each:
  - **Akhet** (Flood): Thout, Phaophi, Athyr, Khoiak
  - **Peret** (Recession): Tybi, Méchir, Phamenoth, Pharmouti
  - **Chémou** (Harvest): Pachon, Payni, Epiphi, Mésori
- **5 épagomenal days** at year's end (360 × 12 = 360, + 5 = 365): Wasire (Osiris), Hor (Horus), Setou (Seth), Aïssate (Isis), Nabintou (Nephthys).
- **Epoch**: An 6262, Mois 1 (Thout), Jour 1 = 2025-08-02 (Gregorian).

## Usage

```
bash ~/.qwen/skills/african-calendar/scripts/kemetic-date.sh                    # today
bash ~/.qwen/skills/african-calendar/scripts/kemetic-date.sh 2026-09-07          # a specific Gregorian date
bash ~/.qwen/skills/african-calendar/scripts/kemetic-date.sh --to-gregorian 6263 2 7   # Kemetic Y M D → Gregorian
```

Forward output: `<day> <month>, <ordinal> Month of the <season-en> (<season-fr>), Year <year> — mois de <god>` (or `Épagomène <name> (<deity>), Year <year>` on one of the 5 extra days). Reverse (`--to-gregorian`) prints a plain `YYYY-MM-DD`.

## What to do with the result

- **Announcing the date**: just say it, in the format above (or trimmed, e.g. "7 Phaophi, 2nd Month of the Flood (Akhet), Year 6263").
- **Naming a session with it**: there is **no tool that renames a Kimi Code session** — only the user's own `/rename` slash command can. Never claim to have renamed a session yourself. Instead, state the date/title and tell the user they can run `/rename "<title>"` if the session isn't already named.
- **Calling this skill from another skill** (e.g. `life`'s Session Protocol): that caller owns its own "how often" logic (e.g. once per calendar day, via its own marker file) — this skill just computes the date on request, it doesn't track when it was last announced.

## Maintenance note

The formula is lifted from the live page's source, not fetched live each time — if the site ever changes its epoch or month/season data, this drifts from it. Worth an occasional spot-check against https://calendrier-africain.netlify.app/ (view source, look for the `todayEgypt()` function and `MONTHS_DATA`/`PERIODS`/`EPAGOMENES` arrays) rather than trusting it blindly forever. Last verified: 2026-09-07.
