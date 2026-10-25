---
name: docgen
description: Generate project/planning/training/client documents as Markdown and export them to PDF + DOCX via a local marked + Playwright + LibreOffice pipeline. Owns the export mechanics (no pandoc/wkhtmltopdf/weasyprint on this machine) and their gotchas. Trigger whenever the user asks to generate/write a planning, training document, client deliverable, or asks to export an existing .md to PDF or DOCX. For pm/tasks reference-file conventions, version log, commits and rollback, delegate to the sibling skill devtask-pm.
---

# Doc Generation (Markdown → PDF + DOCX)

Ported from `klavis-web`'s `klavis-docs-docgen` skill (v1.0.4 GoToMarket session) and generalized for this repo. Owns **exporting** any Markdown document to PDF + DOCX for distribution — not a specific brand's voice or content conventions, which belong to whichever project the document is for.

Boundaries:
- **`pm/tasks/` reference files, version log, `git acp`, rollback** → sibling skill **`devtask-pm`** (delegate; don't duplicate).
- This skill = export mechanics only. Document content/voice/conventions are the calling project's own (e.g. a client's brand guide) — apply those in the Markdown, not here.

**On demand only — never automatic.** Editing or re-editing a reference `.md` is not, by itself, a reason to (re)run this pipeline. Export only when the user asks for a PDF/DOCX, or a file is actually about to leave the editing tool (handed to someone, printed, uploaded) — not as routine hygiene after every write. A source `.md` with no export sitting next to it, or with a stale one from three edits ago, is the normal steady state, not a gap to close proactively. (Corrected 2026-07-31 after this skill's own author re-exported on every single edit across a session — don't repeat that.)

## 1. Document conventions this pipeline understands

The renderer strips two decorations before rendering, so they never leak into PDF/DOCX:
- The `<thisfile path="..." related="..." />` header tag (this repo's convention — see `devtask-pm` SKILL.md §1).
- `-- N. Title --` / `====` decoration lines.

**Tagged values** — `[NAME(value)]` renders as just the value, and a bare `[NAME]` / `[NAME — hint]` anywhere else in the same document renders as that value too (or stays as it is when no value is defined, i.e. still to fill). NAME is in capitals, so Markdown links `[text](url)` and diagram labels without a definition are never touched; inline code is left as written, fenced code blocks are filled. `resolveTaggedValues` (`lib.cjs`), first step of `renderBody`. Convention from the MANSA course documents (2026-09-29); the platform applies the same rule to course content.

`<short-textarea for="notes">` / `<long-textarea for="notes">` — a blank, bordered fill-in box for a worksheet-style document (e.g. a training "Suivi" doc a participant prints or copies and annotates). Write the tag alone on its own line, no closing tag — `renderNoteBoxes` (`lib.cjs`) swaps it for a real box before `marked` ever sees it. `short` ≈ 2 lines tall, `long` ≈ 6; the label is the `for=` value, title-cased. Implemented as a one-cell `<table>` with explicit `height=`/`width=` attributes, not a `<div>` — see the DOCX gotcha in §3 for why.

Beyond that, write plain GFM Markdown — headings, tables, code blocks, blockquotes all render with a clean default style (see §3). If a specific project needs its own visual identity (brand colors, footer, tagline), edit a project-local copy of the `.cjs` templates rather than this shared one.

**Schemas/diagrams: ASCII in the `.md` by default; SVG only in PDF/DOCX export, opt-in per diagram (updated 2026-08-09 — was "inline SVG by default" before).** Write a diagram as an ID-tagged ASCII-art fenced block:

````
```schema:tree-structure
+----------------+
|  project root  |
+----------------+
```
````

That block is the `.md`'s own permanent content — always what a plain-text/git/editor view shows, never touched by export. To get a polished vector version **in the PDF/DOCX only**, drop a matching SVG file at `<md-basename>.schemas/<id>.svg` next to the `.md` (e.g. `01. Training Document.schemas/tree-structure.svg` beside `01. Training Document.md`) — `swapDiagramsForExport` (`lib.cjs`, wired into `renderBody`) substitutes it in for that one block during PDF/DOCX generation only, reusing the existing native-SVG-in-PDF rendering and rasterize-to-PNG-for-DOCX path (§3) unchanged. No matching `.svg` → the ASCII block renders as-is in PDF/DOCX too, exactly like today; SVG is never required, just an optional per-diagram upgrade when a document is actually going out the door polished. Keep SVGs reasonably sized (a `viewBox` around 500–700px wide fits an A4 column) and reuse the palette in `scripts/md2pdf.cjs`'s `<style>` block (`#0b3a5b` dark navy, `#14507a` mid blue, `#c5d2dd`/`#cdd9e2` light borders) so schemas match the surrounding document instead of clashing with it. This is a default, not a mandate — a caller can still hand-write raw `<svg>...</svg>` directly in the `.md` (the old convention) when a project genuinely wants the same vector diagram in every context including the raw `.md`.

**No blank lines inside an embedded `<svg>...</svg>` block — verified 2026-07-31, silent and ugly when violated.** `marked`'s raw-HTML-block handling only lets a *bare* open/close tag alone on its own line restart block-continuation after a blank line; a line shaped like `<text ...>content</text>` (open+content+close all on one line) does **not** qualify, so marked falls back to wrapping it in a stray `<p>`. Because `<p>` is one of the HTML5 "foreign content" breakout tags, the browser's parser reads that stray `<p>` as an instruction to **pop out of the SVG namespace entirely** — everything after it in that same source `<svg>` block (even though it's still textually between the opening `<svg>` and its `</svg>`) renders as inert plain text, not as SVG shapes, and the diagram silently loses its bottom half with no error anywhere in the pipeline. Fix: write the whole `<svg>...</svg>` block as one unbroken run of lines, zero blank lines from the opening tag to the closing tag — group elements visually with indentation or comments instead of blank lines if you want it. Sanity-check before exporting: `node -e "...renderBody...".match(/<p>\s*<(text|rect|line|path)/)` should be `null`. A sibling `<id>.svg` file used via the `schema:<id>` convention above doesn't need manual care here — `swapDiagramsForExport` strips blank lines automatically before substitution.

## 2. Branding — a project's own logo/colors/cover, sourced from a sidecar `brand.json`

Brand-neutral by default (unchanged from before): if a doc's own directory has no `00. Brand,Templates/brand.json` next to it, styling is exactly the plain default in §3 — no logo, no cover page, the existing navy palette. Branding is **opt-in per bundle**, never assumed.

**Discovery.** `lib.cjs` → `loadBrand(mdPath)` looks for `<the .md's own directory>/00. Brand,Templates/brand.json`. That folder is also where the actual logo/template asset files live (whatever a human dropped in — a template docx for style reference, logo variants, etc.).

**The three-step conversation, first time a bundle needs branding:**
1. **Branding folder exists but is empty of rules** (a human created `00. Brand,Templates/` and dropped in assets, no `brand.json`/rules doc yet) → this is a real, common starting state, not an error. Say so, then move to step 2.
2. **Ask for the branding details** — which logo for the small repeating header vs. a larger cover placement (if there's more than one candidate file), a color palette (or: derive one from the logo itself and show what you derived before locking it in), what the header/footer should actually carry (page numbers only? a tagline? contact info?), whether a full cover page is wanted at all. Use whatever's already in the folder as options in the question, don't ask blindly — e.g. "here are the 3 logo files you dropped in, which is the header one?"
3. **First generation only: ask to fill in any remaining unknowns**, then **write both** — the project's own `00. Brand,Templates/00. Brand rules.md` (human-readable: what was decided, and *why* — cite the actual conversation, don't just restate the config) **and** `brand.json` (machine-readable, same folder, is what the pipeline actually reads — see shape below). Every answer and asset given gets saved there; a later regeneration reuses it without re-asking.

**`brand.json` shape** (all keys optional; a missing key just falls back to the neutral default for that one thing):
```json
{
  "name": "ProjectName",
  "logoHeader": "relative/path/to/small-logo.png",
  "logoCover": "relative/path/to/larger-logo.png",
  "colors": { "primary": "#111111", "accentGreen": "#...", "accentYellow": "#...", "accentRed": "#..." },
  "header": { "showLogo": true, "showTitle": true, "showContact": false },
  "footer": { "showPageNumbers": true, "showContact": false },
  "coverPage": true
}
```
`colors` beyond `primary` are free-form — `md2pdf.cjs`/`md2html.cjs` currently only consume `primary` (heading/table color) plus the three named accents (a cover-page accent bar, easy to extend). Logo paths are relative to `brand.json`'s own folder.

**What actually gets branded, and a real gap to be upfront about:**
- PDF (Chromium/Playwright): a **true per-page repeating** header (logo + doc title) and footer (page numbers), plus a real first-page cover if `coverPage: true` — all via `page.pdf()`'s native `headerTemplate`/`footerTemplate` and an in-flow cover `<div>` with `page-break-after`.
- DOCX (LibreOffice HTML import): **no real per-page header/footer exists in this pipeline** — LibreOffice imports one flat HTML doc as a "Writer/Web" flow, not a paginated Word document with actual header/footer parts. Branding there is a **one-time strip at the top** (logo + cover), not repeated per page. Don't oversell this to the user — say plainly that PDF is the fully-branded, print-faithful artifact and DOCX is the editable convenience copy with brand-once-at-the-top. A real per-page Word header would need direct docx-XML manipulation (e.g. `python-docx`), a different toolchain than this HTML-based one.
- **Images need explicit `width=`/`height=` HTML attributes for the DOCX path, not CSS sizing** — verified: a cover logo constrained only by `max-width`/`max-height`/`object-fit` rendered at full intrinsic pixel size in Word, overflowing the page. `lib.cjs` → `pngSize`/`brandImageInfo` reads a PNG's real dimensions (its `IHDR` chunk) so an explicit, aspect-correct `width=`/`height=` can be computed for a target display size. The PDF path doesn't need this — Chromium honours CSS sizing normally.

## 3. Export pipeline — PDF + DOCX

No `pandoc` / `wkhtmltopdf` / `weasyprint` on this machine. `scripts/` bundles self-contained scripts that resolve the project's `node_modules` and the installed Chromium automatically — **no `NODE_PATH`, no `CHROME_BIN`, no hard-coded browser build** needed.

**Prerequisite (one-time per project tree):** `marked` and `playwright` must exist in some `node_modules` reachable by walking up from the CWD (see `scripts/lib.cjs` → `projectRequire`). This repo has no root `package.json` by default — if neither package is found, `npm init -y && npm install marked playwright` in the directory you're generating from (or the repo root) before running the pipeline. Chromium itself does **not** need re-downloading if `~/.cache/ms-playwright` already has a `chromium-*` build (check first — `ls ~/.cache/ms-playwright`).

**Turn-key (preferred).** Run from wherever `node_modules` resolves (repo root, or the project subfolder if installed there):
```bash
.claude/skills/docgen/scripts/docgen.sh "<path/to/doc.md>" ["<another.md>" ...]
# variants: --pdf-only | --docx-only as first arg
```
PDFs and DOCX are written next to each source `.md`, titled from the filename. Quote paths (they contain spaces/accents).

**Under the hood (if you need a single step):**
- PDF: `node scripts/md2pdf.cjs <in.md> <out.pdf> "Title"` — `marked` → styled A4 HTML → Playwright Chromium `page.pdf()` (header/footer with page numbers, styled tables, dark code blocks, **native inline-SVG rendering**).
- DOCX: `node scripts/md2html.cjs <in.md> <out.html> "Title"` — `marked` → HTML → **each inline `<svg>` rasterized to a PNG** (`lib.cjs` → `rasterizeSvgsForDocx`: a throwaway Chromium page screenshots the SVG at `deviceScaleFactor: 2` for crispness, keyed off the SVG's own `viewBox` for natural size) → LibreOffice `soffice --convert-to "docx:MS Word 2007 XML"`.

**Gotchas already handled by the scripts (know them anyway):**
- *Chromium build drift.* `chromium.executablePath()` can point at a build that isn't installed. `md2pdf.cjs` scans `~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome` and uses the full Chromium, falling back to `chromium_headless_shell-*` if that's all that's installed. **Never delete `~/.cache/ms-playwright`.**
- *LibreOffice second-run crash.* A 2nd `soffice` call in the same session crashes (`DeploymentException` / "Unspecified Application Error", empty log) because the default profile is locked. `docgen.sh` always passes a **fresh `-env:UserInstallation=file://…` profile** and converts all HTML in **one** soffice call. The `javaldx` Java warning is harmless.
- *DOCX layout.* LibreOffice imports the HTML as a "Writer/Web" document — fine for editing/sharing; it's a web-layout docx, not print-paginated. The PDF is the print-faithful artifact.
- *Inline SVG vanishes in DOCX — verified 2026-07-31.* Fed a raw `<svg>` block straight to LibreOffice's HTML import, the vector content is silently dropped — no image, no shapes — while any `<text>` nodes *inside* the SVG survive as stray loose paragraph text with no visual context (e.g. two floating words where a labeled flow diagram used to be). `md2html.cjs` now rasterizes every SVG to PNG before handing off to LibreOffice specifically to avoid this; don't bypass that step by calling `renderBody` directly for a DOCX-bound file.
- *Rasterized SVG diagrams overflow the page in DOCX — verified 2026-08-05.* The `<img>` produced by `rasterizeSvgsForDocx` used to be sized with CSS only (`max-width:100%;height:auto`), which LibreOffice's HTML->DOCX import doesn't honour (same underlying issue as the brand-image gotcha above) — it fell back to the raw screenshot's pixel count (2x, for `deviceScaleFactor` crispness) as CSS px, so a 620px-viewBox diagram rendered at ~1240px wide and got clipped off the page edge. Fixed by giving the `<img>` explicit `width=`/`height=` matching the SVG's own `viewBox` size, which is also what the PDF path already renders it at.
- *Fenced code blocks unreadable in DOCX — verified 2026-08-05.* LibreOffice's HTML import maps every `<code>` tag to its built-in "Source Text" character style (dark-red text on a light-gray highlight), ignoring the `pre code { background:none; color:inherit }` CSS override that makes the PDF/HTML path look right — so a code block came out as low-contrast dark-red-on-light-gray boxes sitting inside the dark navy `PreformattedText` paragraph background. `md2html.cjs` now unwraps `<code>` tags that are direct children of `<pre>` before handing off to LibreOffice (`lib.cjs` → `unwrapPreCodeForDocx`), leaving the paragraph style's own (correct) colors in charge; don't bypass this by calling `renderBody` directly for a DOCX-bound file.
- *A bordered blank-space `<div>` collapses to a chip around its label in DOCX — verified 2026-08-05.* Tried building the `<short-textarea>`/`<long-textarea>` note box (see §1) as `<div style="border:...">label<br/><br/>...</div>`. LibreOffice's HTML import doesn't keep `<br/>`-separated content in one paragraph, so the border/shading only carried onto the label's own paragraph — the box visually collapsed to a tight chip around "NOTES", losing all the blank space meant to be written in. Fixed by using a one-cell `<table>` with explicit HTML `height=`/`width=` attributes on the `<td>` (not CSS) instead of a `<div>` — tables are the one layout primitive LibreOffice's HTML import renders reliably (same lesson `render-prospectus.cjs` already learned), and explicit attributes survive where CSS sizing doesn't (same reason as the brand-image `width=`/`height=` gotcha above).
- *Inline code inside a heading renders too small/mismatched — fixed 2026-08-03.* The base `code { font-size: 9.5px/9.5pt }` rule is calibrated against **body** text (~10.5px/11pt), so a `` `code` `` span inside an `# H1`/`## H2`/etc. heading inherited that fixed size instead of scaling with the heading — badly undersized next to a 21px/20pt H1. Both `md2pdf.cjs` and `md2html.cjs` now add `h1 code, h2 code, h3 code, h4 code { font-size: 0.75em; }` right after the base `code` rule — `em` resolves against the *heading's own* computed font-size, so a code span in a title always renders at **3/4 of that title's font-size**, at any heading level, without hardcoding a px/pt value per level. Higher selector specificity means this always wins over the base `code` rule regardless of CSS order, but keep it placed directly after the base rule for readability.

After generating, sanity-check: PDF starts `%PDF-` and ends with `%%EOF`; DOCX is a valid zip (`unzip -l`).

- *Exec bit doesn't stick under `/media/nkensa/win11`.* That mount (NTFS/fuseblk) doesn't persist the executable bit — `chmod +x docgen.sh` succeeds but a later `./docgen.sh` still fails with `Permission denied`. Invoke it as `bash .claude/skills/docgen/scripts/docgen.sh ...` instead of relying on the shebang; this is unrelated to the script's own permissions and will recur every session on that disk.

## 4. Machine constraint — disk

Root FS (`/`, holds `$HOME` + `~/.claude` + any `npm install` you run without an explicit `--prefix`) has repeatedly run near-full on this machine (an ENOSPC once truncated a memory write mid-session on a sibling machine running this same pipeline). Check `df -h /` before any `npm install`; if root is tight, `npm install --prefix <path-on-a-roomier-disk>` and point `docgen.sh`'s CWD there, or reuse an existing `node_modules` elsewhere in the tree that already has `marked`+`playwright` (walked up automatically — no config needed). Do **not** touch `~/.cache/ms-playwright`.

## 5. Workflow (only once export is actually asked for / actually needed)

1. Write the `.md` using the target project's own content conventions (this skill doesn't impose any) — and stop there by default; do not chain into export.
2. When export is actually warranted (see the on-demand rule above): check whether `00. Brand,Templates/brand.json` exists next to the doc (§2) — if a branding folder exists without a `brand.json`/rules doc yet, that's the "waiting for rules" state, walk through §2's ask; otherwise proceed brand-neutral.
3. Confirm `marked`+`playwright` are resolvable (§3 prerequisite); install once if not.
4. Export with `docgen.sh` (§3); verify outputs (§3 last line).
5. If the doc lives under a cloud-symlinked `pm/tasks/` path, remember the `.md`/`.pdf`/`.docx` are **not git-tracked** — see `devtask-pm` SKILL.md §1. Docs under a normal in-repo `projects/*` path are tracked normally.
