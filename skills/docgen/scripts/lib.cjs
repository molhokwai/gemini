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

// Markdown -> inner HTML, stripping reference-doc decorations (<thisfile .../>
// header tag, `-- N. Title --` / `====` decoration lines — see devtask-pm SKILL.md §1).
function renderBody(marked, md) {
  md = md.replace(/<thisfile[\s\S]*?\/>/g, '');                       // custom tag
  md = md.replace(/^\s*--\s*\d+\..*?--\s*$/gm, '').replace(/^={3,}\s*$/gm, ''); // -- N. Title -- / ====
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

      const img = `<img src="data:image/png;base64,${buf.toString('base64')}" style="max-width:100%;height:auto;display:block;margin:1em auto;" alt="schema"/>`;
      out = out.replace(svg, img);
    }
    return out;
  } finally {
    await browser.close();
  }
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
  projectRequire, findChromium, renderBody, rasterizeSvgsForDocx,
  loadBrand, brandImageDataUri, brandImageInfo,
};
