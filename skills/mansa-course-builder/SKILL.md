---
name: mansa-course-builder
description: Builds a MANSA AI-training course for the public offer (the `mansa-ai-trainings-offer` bundle) across its three channels — (A) document course — a follow-along trainee document per language, branded PDF/DOCX (first built for Course 1), (B) web course from the approved MANSA module template (desktop + mobile, FR/EN, data saver, checkpoint quiz) as a Design canvas, (C) full video course for Udemy (to be built) — and registers every output in the bundle. Use whenever the user wants to create, design or extend a MANSA course, course module, lesson, quiz or web-course page ("make Course 2", "design the module for X", "build the web course for Course 1 module 03", "turn this training into a course"), or reuse the Course 1 template for a new audience. Not for the finished Ghislain client engagement (`mansa-ai-training`) — that bundle is source material here, not a target.
---

# MANSA Course Builder

Turns MANSA source material (training documents, onboarding guides, demo apps, videos) into sellable courses for the **MANSA AI Trainings Offer** — paid, online, autonomous AI courses for Cameroon/Africa (see the bundle's `01. Global Plan.md`). One course = up to three channels, built from the same content:

| Channel | Status | Output |
|---|---|---|
| **A. Document course** | **first course built** (Course 1, EN + FR, 2026-09-25) — see §A | branded `.md` → PDF/DOCX via `docgen` |
| **B. Web course** | **template ready** (approved 2026-09-25) | Design canvas: module overview, lesson, checkpoint, mobile lesson |
| **C. Full course (video)** | **to be built** — first real run defines it (see §C) | video lessons for Udemy |

Boundaries — delegate, don't duplicate:
- `pm/tasks` headers, bundle README, completion markers, commits → **`devtask-pm`**.
- Markdown → PDF/DOCX export, MANSA branding via `brand.json` → **`docgen`**.
- Logging the work in `life/` → **`life`** skill (Session Protocol).
- A MANSA reference code (`PROJ/MANSA/<kamit-date>-<NN>`) → **`african-calendar`**; never guess the Kamit date.

## 1. Where things live

All paths below are relative to `pm/tasks/analysis-α-implementation/` (the Drive-synced symlink; never `git add` through it).

```
mansa-ai-trainings-offer/                  ← the offer bundle (target)
├─ README.md                               ← keep current (devtask-pm rules)
├─ 00. Research.md                         ← market research: audiences, domains
├─ 01. Global Plan.md                      ← strategy: courses → sector briefs → kamda
├─ 02. Implementation and Plan.md          ← checklist + Design register  ← REGISTER HERE
└─ 00. Design/
   └─ Course <N> - <Channel> - <What> (<Module…>)/   ← exported canvases (html zips + pdf)

mansa-ai-training/                         ← source material (Course 1), read-only here
├─ 01. Training Document.md                ← content of modules 01–04
├─ 00. Onboarding/01. Onboarding - Guide(.md|(FR).md)  ← module 00 primer
├─ 00. Brand,Templates/                    ← logo, brand.json, 00. Brand rules.md
└─ 00. Marketing,Sales/…Flash Promo I Preview Video.mp4
```

This skill's own template: `.claude/skills/mansa-course-builder/templates/web-course/` (the six approved `.dc.html` + `canvas.json` + `ASSETS.md`).

## 2. Start of every run

1. Read `mansa-ai-trainings-offer/README.md` and the checklist at the top of `02. Implementation and Plan.md`: which course, which channel, what is already done.
2. Pin down, asking only what is not already written down: **course number and audience** (from `00. Research.md`'s target groups), **source material** (paths), **module list**, **language(s)** (FR, EN or both), **price tier** if the channel shows one (the plan: pan-African low/free vs. very high; unknown → `[PRICE]`).
3. Content rule for every channel: lesson text comes from the source material, condensed, never invented. No made-up stats, durations, prices or testimonials; use a visible placeholder (`[DURATION]`, `[PRICE]`) and list them in your reply.

## 3. MANSA visual identity (all channels)

Taken from `mansa-ai-training/00. Brand,Templates/` and the MANSA prospectus (`02. MANSA - Formation pratique - DEV - IA - Prospectus.html`):

- **Fonts**: `Archivo Black` (display/headings), `Work Sans` 400/500/600 (body), `JetBrains Mono` (labels, eyebrows, code, metadata).
- **Colors**: ink `#131313`, ink-soft `#4a4a46`, paper `#ffffff`, paper-sunk `#f4f4f1`, line `#dedcd4`; Cameroon-flag accents green `#007a5e`, yellow `#fcd116` (fills only, with ink text — as text use `#7a5a06`/`#6b4f05`), red `#c81e3a`; tints green `#e3f3ee`, yellow `#faf1dc`, red `#fbe7ea`.
- **Signature motif**: a thin green/yellow/red tricolor bar at the very top of every page.
- **Diagrams**: dark panel `#121416` in the style of the Flash Promo video; bright accents green `#16b78a`, yellow `#ffcf1f`, red `#ff5d73`. Color meaning is fixed by the Training Document — green = stable/done, yellow = transitional/caution, red = volatile.
- **Logo**: the transparent 612×408 PNG has wide margins; crop it with `object-fit: cover` in a ~3.1:1 box (170×54 desktop, 138×44 compact). It is black: light backgrounds only.

## §A. Document course — the trainee's follow-along document

First built for Course 1 on 2026-09-25: `mansa-ai-trainings-offer/03. Course 1 - Document course/`. Reuse that folder as the model.

**Layout — one folder per course, one file per language:**

```
mansa-ai-trainings-offer/
└─ 0N. Course <N> - Document course/
   ├─ 00. Brand,Templates/        ← copy of mansa-ai-training/00. Brand,Templates/brand.json
   │                                 + the two logos it names (docgen looks next to the .md)
   ├─ 01. Course <N> - <title> (EN).md     (+ .pdf/.docx)
   └─ 02. Course <N> - <titre> (FR).md     (+ .pdf/.docx)
```

One document per language, not one per module: the trainee follows a single file from top to bottom, and a single PDF is what gets distributed. Headers: `parent` = the bundle's `02. Implementation and Plan.md`, the EN and FR files are each other's `sibling`.

**Content shape** (see the Course 1 files):
1. Title block (for whom, format, `[DURATION]`), what the trainee will have at the end, "How to use this document", a `schema:course-map`.
2. **First contact** first: the 8 questions (from `02. Implementation and Plan.md` → *Course 1 structure*), each followed by a **MANSA:** answer — optionally a one-line *"What the AI will probably say"* hint. Then *II. Comfort check* in the user's exact wording ("If not, please ask more questions until you are / If you are: start the course here"); never Gemini's "ask 2 random questions / tell me a joke" variant (rejected by the user).
3. One `#` section per module, each with the same four parts: **What you'll do** → numbered **Steps** (exact commands in fenced blocks) → **Check** (what the trainee should see) → **Try it** (short exercise). A 3-question checkpoint with its answers written out after the questions.
4. Annexes for audience-specific translations (Course 1: "If you come from microservices").

**Content sources and tone.** Lesson material comes from the source bundle (Course 1: `01. Training Document.md`, `00. Onboarding/01. Onboarding - Guide(.md|(FR).md)`, `00. Documents/MANSA - DEV Onboarding - EN/FR.md`), adapted for a public, self-paced trainee: drop anything internal to a client or employer (developer agreement, HR interview, specific teams, local machine paths). Third-party propositions (`00. Content/`, e.g. Gemini's) are ideas only: rewrite them in MANSA's voice (warm, direct, "you", no hype, no emoji, no invented numbers like "4 hours → 10 minutes"). The FR file is written in the style of `01. Onboarding - Guide (FR).md` (vouvoiement, « compétences (skills) »), not translated line by line.

**Placeholders**, never invented: `[DURATION]`, `[AI CHAT LINK]`, `[AI ACCOUNT / PLAN]`, `[STARTER REPO URL]`, `[REFERENCE REPO URL]`, `[HOW TO GET AN API KEY]`, `[SUBMISSION CHANNEL]` (FR: `[DURÉE]`, `[URL DU DÉPÔT DE DÉPART]`, …). List them in the reply and in the checklist line.

**Filling a placeholder keeps its tag** (the user's convention, 2026-09-29): write `[NAME(value)]`, e.g. `[STARTER REPO URL(https://github.com/molhokwai/mansa-ai-starter)]`, so the value stays findable and changeable. Define a value once; other `[NAME]` occurrences in the same document take it (a `git clone [NAME] …` line needs no repeat). Readers never see the tags: the PDF/DOCX export (`docgen`, `resolveTaggedValues`) and the platform (`server/utils/placeholders.ts`, resolved per course and locale) show only the value, and a URL becomes a link. Inline code (`` `[DURATION]` ``) is left as written, to explain the convention; an unfilled `[NAME]` stays visible. Keep NAME identical across every occurrence, and fill the EN and FR documents alike.

**Export** (this document goes to trainees, so export is warranted): from the `nkensa` repo root, `bash .claude/skills/docgen/scripts/docgen.sh "<EN.md>" "<FR.md>"` (both in one call). Check `df -h /` first. Gotchas met on the first run:
- No `<details>`/`<summary>` for quiz answers: Chromium prints them collapsed, so the answers vanish from the PDF. Use a plain `### Answers` subsection.
- Consecutive `**For:** … / **Format:** …` lines need a blank line between them, or they merge into one paragraph.
- The cover date is hard-coded `fr-FR` in `docgen`'s `md2pdf.cjs`, so the English PDF shows "25 septembre 2026". Known, not yet fixed in `docgen`.
- Verify: each PDF starts `%PDF-` and ends `%%EOF`; each DOCX passes `unzip -l`; look at pages 1–3 of the EN PDF (cover with MANSA logo + tricolour bar, schema blocks rendered).

Register per §4 (checklist sub-item `2a-…`, bundle README tree + branch, `life/`).

## §B. Web course — from the approved template

The template (`templates/web-course/`) holds one module rendered as four artboards, plus the course-wide "First contact" step (two more):

| Artboard | File | Size | Role |
|---|---|---|---|
| Module overview | `Main.dc.html` | 1440×1720 | hero + module video, outcomes, lesson list with thumbnails/status, checkpoint card, course outline |
| Lesson | `Lesson.dc.html` | 1440×1960 | sidebar + progress, video/still with **Data saver** toggle, dark diagram, key-idea box, "Try it" exercise, prev/next |
| Checkpoint | `Checkpoint.dc.html` | 1440×1400 | one question per lesson, answer explained right or wrong, score, reset |
| Mobile lesson | `Mobile.dc.html` | 390×1620 | same lesson on a phone, FR, data-saver on, offline download, bottom next bar |
| First contact — desktop | `FirstContact.dc.html` | 1440×900 | **every course opens with it**: split screen, MANSA space (1/3, fades once the chat starts, back on hover/focus) + chat with the AI (2/3); 8 guided first-contact questions, MANSA's own answer after each, then "comfortable?" → course |
| First contact — mobile | `FirstContactMobile.dc.html` | 390×844 | same, stacked 1/3 top, 2/3 bottom, tap the faded top to bring it back; FR ("Premier contact") |

**Every course starts with the "First contact" step** (FR "Premier contact"; renamed from "Break the ice" on 2026-09-25) (the user's rule, 2026-09-25: for newcomers, and recommended for experts too). Its 8 questions are generic, so keep them; adapt only MANSA's answers to the course's audience. Source brief, verbatim: `mansa-ai-trainings-offer/02. Implementation and Plan.md` → *Course 1 structure*. The chat in the canvas is a mock with labelled placeholder answers: a Design canvas can't call an AI, the production page plugs in the live model.

Why data saver, mobile-first and FR/EN are in every module: `00. Research.md` — bilingual learners, uneven connectivity outside major cities.

Steps:
1. **Media.** If the module has a video: extract one still per lesson with ffmpeg (Course 1: `ffmpeg -ss <t> -i <video> -frames:v 1 -q:v 3 still-<n>.jpg`, t = 2/4/6 s). Copy files out of Drive-synced paths into the scratchpad first. No video → stills or diagrams only, and drop the `<video>` elements.
2. **Canvas.** Run the `/design` flow: `Artifact` quickstart `intent: "design"`, create from the Design type with a title like `MANSA Course <N> — <Module title>`, then follow the type's instructions exactly.
3. **Assets.** Upload logo, video and stills into the new canvas (`asset: true`, one `file_paths` call); swap every `/_blob/<id>` per `templates/web-course/ASSETS.md`.
4. **Content.** Copy the four templates into the canvas folder and replace the copy: module title/eyebrow, outcomes (one per lesson, color-coded), lessons, diagram (rebuild in HTML in the dark-panel style — don't paste a screenshot), key idea, exercise, checkpoint `bank` (one question per lesson, with `why`), mobile lesson (FR unless told otherwise), course outline. Keep sizes, structure, tokens.
5. Publish in one call; hand the link over; **don't verify unless asked** (the Design type forbids it).
6. After approval: the user exports from the canvas (html zip per artboard + PDF). Move the export into `mansa-ai-trainings-offer/00. Design/Course <N> - Web course - <What> (<Module…>)/` — **ASCII-only names**: replace `—`/`·` with `-` and drop `:` (invalid on the NTFS mount) and commas. `cmp` each copy before deleting the Downloads original.
7. **Register** (§4).

Gotchas learned building the template:
- In the Design format a whole-value style hole (`style="{{x.style}}"`) is unsafe; interpolate per property instead (`border: {{o.bw}} solid {{o.border}}`).
- Boolean HTML attributes on `<video>` need a hole: `controls="{{yes}}"`, `playsInline="{{yes}}"` with `yes: true` in `renderVals()`.
- The Checkpoint's selected/answer colors differ in lightness, not just hue (green `#007a5e` vs red `#c81e3a` plus 2px border), so they stay readable without color vision.
- An exported artboard only differs from its canvas source by `vendor/react*.js` lines and `assets/<id>.<ext>` paths: diff ignoring those to check whether the user edited the canvas before reusing sources.

## §C. Full course (video, Udemy) — TO BE BUILT

No run has produced one yet. From the plan: "Web full course: video course → Put on Udemy". Starting points already available: the Flash Promo trailer's visual language (dark schema animations), the web-course lesson structure (one video per lesson), and the checkpoint questions (Udemy quizzes). **When the first one is built, rewrite this section** with the real pipeline (recording/animation tool, Udemy format constraints) and flip its status.

## 4. Register every output (mandatory, same pass)

1. `02. Implementation and Plan.md`:
   - tick or add the sub-items under the course's checklist line (e.g. `2b-i`, `2b-ii`);
   - append a `## D<n>. <title>` entry under `# Design register`: status, live canvas URL, exported-files folder, reusable source, source content, and an artboard table (file, size, interactive, what it shows), plus open placeholders. Append-only: never rewrite earlier entries or the user's verbatim plan text.
2. `README.md` of the bundle: tree + branch summary for `00. Design/` + global status line (`devtask-pm` README rules; keep **Manually updated** markers).
3. `life/`: log the event in `life/50-work/events/<YYYY-MM>.md`, update the open loop for the offer in `life/00-meta/open-loops.md` and the two `SUMMARY.md` files (`life` skill).
4. If the run changed how a channel works (a new gotcha, §A/§C built for real), update **this skill** too; that's step 6 of the Training Document's improvement cycle.
