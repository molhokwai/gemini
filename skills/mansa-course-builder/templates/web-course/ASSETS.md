# Web-course template — assets and placeholders

The six `.dc.html` files here are the **approved** MANSA web-course module template (2026-09-25), copied verbatim from the Design canvas https://claude.ai/artifact/W9W1BSVhwNMAY84mc7z6Hq. Content is Course 1 / Module 02 ("The three AI schemas") plus the course-wide "First contact" step (`FirstContact*.dc.html`, added 2026-09-25, uses only the logo asset): replace the module content, keep the structure and styling.

## `/_blob/<id>` references are canvas-specific

Every image/video in these files points at an asset uploaded to **that** canvas. A new canvas does not have them: re-upload the files into the new canvas (`Artifact` publish, `asset: true`, `file_paths`) and replace each id below with the url the upload returns.

| Id in the template | What it is | Source file |
|---|---|---|
| `c546a0db0050bc12539158f796628a9c` | MANSA header logo | `mansa-ai-training/00. Brand,Templates/MANSA - (Assoc) - Logo 612x408 - Transparent.png` |
| `f41bd6490c19699c4466082e9524cca9` | Module video (Course 1 used the Flash Promo trailer) | `mansa-ai-training/00. Marketing,Sales/MANSA Ai Training - Flash Promo I Preview Video.mp4` |
| `55f63bd20be203b72807453f24974d47` | Still 1 (lesson 1 thumbnail, video poster) | frame at 2 s of the video |
| `eb4fb1c6b227d39aeda0a798fec439a2` | Still 2 (lesson 2 thumbnail/poster) | frame at 4 s |
| `df125376206eae99dc4b433f311fbf74` | Still 3 (lesson 3 thumbnail) | frame at 6 s |

Paths are relative to `pm/tasks/analysis-α-implementation/`.

## Placeholders to fill

- `[DURATION]` (EN) / `[DURÉE]` (FR): per module and per lesson. Never invent them; ask.
- The Course outline in `Main.dc.html` (aside) lists Course 1's modules 00–04: replace with the new course's outline.
- `Checkpoint.dc.html`: the question bank lives in the logic class (`bank`), one question per lesson, each with `why`.
- `canvas.json`: `title`, board `title`s and the heading note text.
