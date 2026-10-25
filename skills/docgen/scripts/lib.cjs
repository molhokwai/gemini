// Shared helpers for the docgen pipeline.
// Resolves the project's deps and the installed Chromium regardless of CWD or
// Playwright version. No NODE_PATH and no hard-coded browser build needed.
const fs = require('fs');
const path = require('path');
const os = require('os');
const { createRequire } = require('module');

// Require `marked` / `playwright` from the project's node_modules, found by
// walking up from CWD until a node_modules with the package is located.
function projectRequire() {
  let dir = process.cwd();
  for (;;) {
    const nm = path.join(dir, 'node_modules');
    if (fs.existsSync(path.join(nm, 'marked'))) return createRequire(path.join(nm, '_'));
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  // Fallback: resolve relative to this script (skills live inside the project).
  return createRequire(path.join(__dirname, '_'));
}

// Find a usable full Chromium binary (NOT the headless_shell, which is often
// missing). Honour CHROME_BIN, else scan the Playwright cache for chromium-* .
function findChromium(playwright) {
  if (process.env.CHROME_BIN && fs.existsSync(process.env.CHROME_BIN)) return process.env.CHROME_BIN;
  const cache = path.join(os.homedir(), '.cache', 'ms-playwright');
  try {
    const builds = fs.readdirSync(cache)
      .filter(d => /^chromium-\d+$/.test(d))      // exclude chromium_headless_shell-*
      .sort();                                     // newest build sorts last
    for (const b of builds.reverse()) {
      const bin = path.join(cache, b, 'chrome-linux64', 'chrome');
      if (fs.existsSync(bin)) return bin;
    }
    // Fallback: only the headless-shell build is installed (no full Chromium).
    // It renders page.pdf() fine, so use it rather than failing.
    const shells = fs.readdirSync(cache)
      .filter(d => /^chromium_headless_shell-\d+$/.test(d))
      .sort();
    for (const b of shells.reverse()) {
      const bin = path.join(cache, b, 'chrome-headless-shell-linux64', 'chrome-headless-shell');
      if (fs.existsSync(bin)) return bin;
    }
  } catch (_) { /* cache dir absent */ }
  // Last resort: whatever Playwright thinks (may not exist → will throw clearly).
  try { return playwright.chromium.executablePath(); } catch (_) { return undefined; }
}

// <short-textarea for="..."> / <long-textarea for="..."> -> a bordered blank
// note box, labeled from the `for` value. These are void-style markers (no
// closing tag in source) — must be swapped for a real, self-closed <div>
// BEFORE marked.parse runs: left as-is, marked passes the bare opening tag
// through untouched and, since it's an unrecognized element with no special
// HTML5 content model, the browser/LibreOffice parser nests every subsequent
// line into it as a child (verified: an entire downstream section, including
// later headings, ended up trapped inside the first <long-textarea>).
// Sized with literal <br/> line breaks rather than CSS height/min-height —
// consistent with this pipeline's other DOCX findings (LibreOffice's HTML
// import does not reliably honour CSS sizing that isn't backed by real
// content), so blank space here is guaranteed to survive both the PDF
// (Chromium) and DOCX (LibreOffice) paths.
function renderNoteBoxes(md) {
  return md.replace(/<(short|long)-textarea\s+for="([^"]+)">/g, (m, size, forVal) => {
    const label = forVal.charAt(0).toUpperCase() + forVal.slice(1);
    const px = size === 'long' ? 140 : 46;
    // Tried a bordered <div> with a label + literal <br/>s for blank space
    // first — LibreOffice's HTML import doesn't keep <br/>-separated content
    // in one paragraph, so the border/shading only landed on the label's own
    // paragraph and the box collapsed to a tight chip around "NOTES", losing
    // all the blank space below it (verified 2026-08-05). A one-cell
    // <table> is the fix: this pipeline already leans on tables as the one
    // layout primitive LibreOffice's HTML import renders reliably (see
    // render-prospectus.cjs), and an explicit HTML `height=`/`width=`
    // attribute on the <td> (not CSS) is honoured where CSS sizing on a
    // <div> was not — same "attributes over CSS" lesson as brandImageInfo.
    return `<table width="100%" style="border-collapse:collapse;margin:8px 0 16px;"><tr><td style="border:1px solid #c5d2dd;padding:6px 10px;font-family:'Liberation Sans',Arial,sans-serif;font-size:8pt;color:#94a3ae;text-transform:uppercase;letter-spacing:.04em;" height="${px}">${label}</td></tr></table>`;
  });
}

// ```schema:<id> ... ``` is the ASCII-art authoring form for a schema — this
// is what the .md itself always shows (plain-text/git/editor view). If a
// sibling "<md-basename>.schemas/<id>.svg" file exists next to the .md,
// export (PDF/DOCX only — never the .md source) substitutes that raw SVG in
// place of the block for this one diagram, so it renders as a real vector
// (native in the PDF; rasterized to PNG for DOCX — see rasterizeSvgsForDocx).
// No matching .svg → the ASCII block is left exactly as-is, unchanged; SVG is
// opt-in per diagram, never required. See docgen SKILL.md §1.
function swapDiagramsForExport(md, mdPath) {
  if (!mdPath) return md;
  const diagramsDir = path.join(
    path.dirname(path.resolve(mdPath)),
    path.basename(mdPath).replace(/\.md$/i, '') + '.schemas',
  );
  return md.replace(/```schema:([\w-]+)\n[\s\S]*?```/g, (block, id) => {
    const svgPath = path.join(diagramsDir, `${id}.svg`);
    if (!fs.existsSync(svgPath)) return block;
    // Strip blank lines — marked's raw-HTML-block continuation rule breaks on
    // a blank line inside an embedded <svg> (see SKILL.md §1 gotcha); a
    // hand-authored sibling .svg file isn't written with that in mind, so
    // enforce it here rather than relying on every diagram author to know it.
    return fs.readFileSync(svgPath, 'utf8').split('\n').filter(l => l.trim() !== '').join('\n');
  });
}

// Markdown -> inner HTML, stripping reference-doc decorations (<thisfile .../>
// header tag, `-- N. Title --` / `====` decoration lines — see devtask-pm SKILL.md §1)
// and substituting export-only SVG diagrams (see swapDiagramsForExport) when mdPath is given.
// Tagged values (the MANSA course convention, 2026-09-29): the author keeps each value tagged so it
// can be found and changed later. `[NAME(value)]` shows only the value; a bare `[NAME]` or
// `[NAME — hint]` shows the value defined anywhere else in the same document, or stays as it is
// (still to fill). NAME is in capitals, so Markdown links `[text](url)` are never touched; inline
// code is left as written (it shows the convention itself), fenced code blocks are filled.
// Same rule as the platform's server/utils/placeholders.ts — keep them in step.
const TAG_NAME = "[A-ZÀ-Ý][A-ZÀ-Ý0-9 /'’-]*?";
const TAG_HINT = '(?: — [^\\]()]*)?';
const TAG_DEFINITION = () => new RegExp(`\\[(${TAG_NAME})${TAG_HINT}\\(((?:(?!\\)\\]).)+)\\)\\]`, 'g');
const TAG_REFERENCE = () => new RegExp(`\\[(${TAG_NAME})${TAG_HINT}\\]`, 'g');
const INLINE_CODE = /(`[^`\n]+`)/;

function resolveTaggedValues(md) {
  const values = {};
  for (const m of md.matchAll(TAG_DEFINITION())) {
    const name = m[1].trim();
    if (!(name in values)) values[name] = m[2].trim();
  }
  return md
    .split(INLINE_CODE)
    .map((part, i) => (i % 2 === 1 ? part : part
      .replace(TAG_DEFINITION(), (_all, _name, value) => value.trim())
      .replace(TAG_REFERENCE(), (all, name) => values[name.trim()] ?? all)))
    .join('');
}

function renderBody(marked, md, mdPath) {
  md = swapDiagramsForExport(md, mdPath);
  md = resolveTaggedValues(md);
  md = md.replace(/<thisfile[\s\S]*?\/>/g, '');                       // custom tag
  md = md.replace(/^\s*--\s*\d+\..*?--\s*$/gm, '').replace(/^={3,}\s*$/gm, ''); // -- N. Title -- / ====
  md = renderNoteBoxes(md);
  marked.setOptions({ gfm: true, breaks: false });
  return marked.parse(md);
}

// LibreOffice's HTML->DOCX import silently drops inline <svg> (verified: the
// vector content vanishes, only stray <text> node strings survive as loose
// paragraph text — no image, no shapes). Chromium (md2pdf.cjs) renders inline
// SVG natively and needs none of this. For the DOCX path only, rasterize each
// <svg>...</svg> block to a PNG (via a throwaway Chromium page + element
// screenshot at deviceScaleFactor 2 for crispness) and swap it for an <img
// src="data:image/png;base64,...">, so schemas survive into Word instead of
// silently disappearing.
async function rasterizeSvgsForDocx(html, playwright, findChromium) {
  const svgs = html.match(/<svg[\s\S]*?<\/svg>/g);
  if (!svgs || svgs.length === 0) return html;

  const execPath = findChromium(playwright);
  const browser = await playwright.chromium.launch(execPath ? { executablePath: execPath } : {});
  try {
    let out = html;
    for (const svg of svgs) {
      const vb = svg.match(/viewBox="[\d.\-]+\s+[\d.\-]+\s+([\d.]+)\s+([\d.]+)"/);
      const w = vb ? Math.ceil(parseFloat(vb[1])) : 600;
      const h = vb ? Math.ceil(parseFloat(vb[2])) : 400;

      // Force the root <svg ...> tag to an explicit natural pixel size for a
      // crisp, correctly-proportioned screenshot — strip any responsive
      // width/height/style it carries for the doc's own (HTML) rendering;
      // only the root tag is touched, not inner elements that also use
      // width/height (e.g. <rect>).
      const openTag = svg.match(/^<svg\b[^>]*>/)[0];
      const cleanedOpenTag = openTag
        .replace(/\swidth="[^"]*"/i, '')
        .replace(/\sheight="[^"]*"/i, '')
        .replace(/\sstyle="[^"]*"/i, '')
        .replace(/^<svg/, `<svg width="${w}" height="${h}"`);
      const sizedSvg = svg.replace(openTag, cleanedOpenTag);

      const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
      await page.setContent(`<!DOCTYPE html><html><body style="margin:0;padding:0;">${sizedSvg}</body></html>`);
      const el = await page.$('svg');
      const buf = await el.screenshot({ omitBackground: true });
      await page.close();

      // Explicit width=/height= (not just CSS) — same reason as brand images
      // (see brandImageInfo): without them, LibreOffice's HTML->DOCX import
      // falls back to the raw screenshot's pixel count (2x here, for
      // deviceScaleFactor crispness) as CSS px, rendering the diagram at
      // roughly double its intended size and overflowing off the page edge
      // — verified 2026-08-05 (a 620px-viewBox diagram clipped mid-box).
      // Sizing to the SVG's own viewBox (w x h) keeps the on-page size
      // matching what md2pdf.cjs's native-SVG path already renders.
      const img = `<img src="data:image/png;base64,${buf.toString('base64')}" width="${w}" height="${h}" style="display:block;margin:1em auto;" alt="schema"/>`;
      out = out.replace(svg, img);
    }
    return out;
  } finally {
    await browser.close();
  }
}

// LibreOffice's HTML->DOCX import maps every <code> tag to its built-in
// "Source Text" character style (dark-red text on a light-gray highlight),
// regardless of the `pre code { background:none; color:inherit }` CSS
// override used for the PDF/HTML path — verified by inspecting the produced
// document.xml: the <w:rStyle w:val="SourceText"/> run inside a
// PreformattedText paragraph stacks its own light shd/dark-red color on top
// of the paragraph's dark navy background, making code blocks unreadable.
// Fix: for the DOCX path only, unwrap <code> tags that are direct children of
// <pre> (keep the text, drop the tag) so LibreOffice has nothing left to map
// to Source Text and the block inherits the correct PreformattedText colors.
function unwrapPreCodeForDocx(html) {
  return html.replace(/<pre><code(?:\s+class="[^"]*")?>([\s\S]*?)<\/code><\/pre>/g, '<pre>$1</pre>');
}

// Brand-neutral by default: only look for a sidecar "<doc's own dir>/00.
// Brand,Templates/brand.json". No brand.json → no branding, current default
// styling applies exactly as before (see devtask-pm / docgen SKILL.md).
function loadBrand(mdPath) {
  const dir = path.dirname(path.resolve(mdPath));
  const brandDir = path.join(dir, '00. Brand,Templates');
  const brandFile = path.join(brandDir, 'brand.json');
  if (!fs.existsSync(brandFile)) return null;
  const brand = JSON.parse(fs.readFileSync(brandFile, 'utf8'));
  brand._dir = brandDir;
  return brand;
}

// Read a brand-relative image (e.g. brand.logoHeader) as a data: URI, or
// return null if the brand has no such key or the file is missing.
function brandImageDataUri(brand, key) {
  if (!brand || !brand[key]) return null;
  const p = path.join(brand._dir, brand[key]);
  if (!fs.existsSync(p)) return null;
  const ext = path.extname(p).slice(1).toLowerCase();
  const mime = ext === 'jpg' || ext === 'jpeg' ? 'image/jpeg' : ext === 'svg' ? 'image/svg+xml' : 'image/png';
  return `data:${mime};base64,${fs.readFileSync(p).toString('base64')}`;
}

// PNG's IHDR chunk (bytes 16-23, big-endian uint32 pairs) gives the natural
// pixel size directly, no image library needed. Used to compute an explicit
// width= alongside height= for DOCX <img> tags — LibreOffice's HTML->DOCX
// import does NOT reliably honour CSS max-width/max-height/object-fit
// (verified: without an explicit width attribute, a raw 1500x1000 cover logo
// rendered at full intrinsic size, overflowing the page, instead of the
// CSS-constrained ~180px box; only explicit width/height HTML attributes,
// not CSS alone, size an image predictably through this pipeline).
function pngSize(absPath) {
  const buf = fs.readFileSync(absPath);
  if (buf.readUInt32BE(0) !== 0x89504e47) return null; // not a PNG (signature mismatch)
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

// brandImageDataUri + natural size in one call, so callers can compute an
// explicit width= for a target height= (or vice versa) that DOCX will
// actually respect. Falls back to a 1:1 assumption if the file isn't a PNG.
function brandImageInfo(brand, key) {
  const uri = brandImageDataUri(brand, key);
  if (!uri) return null;
  const p = path.join(brand._dir, brand[key]);
  const size = pngSize(p) || { width: 1, height: 1 };
  return { uri, width: size.width, height: size.height, aspect: size.width / size.height };
}

module.exports = {
  projectRequire, findChromium, renderBody, resolveTaggedValues, swapDiagramsForExport, rasterizeSvgsForDocx,
  unwrapPreCodeForDocx, loadBrand, brandImageDataUri, brandImageInfo,
};
