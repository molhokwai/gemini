#!/usr/bin/env node
// Markdown -> standalone styled HTML (intermediate for LibreOffice -> docx).
// Run from the project root:  node .claude/skills/docgen/scripts/md2html.cjs <in.md> <out.html> ["Title"]
const fs = require('fs');
const path = require('path');
const { projectRequire, findChromium, renderBody, rasterizeSvgsForDocx, loadBrand, brandImageInfo } = require('./lib.cjs');

const [, , inPath, outPath, titleArg] = process.argv;
if (!inPath || !outPath) { console.error('Usage: md2html.cjs <in.md> <out.html> ["Title"]'); process.exit(1); }

const req = projectRequire();
const { marked } = req('marked');
const playwright = req('playwright');

(async () => {
  let body = renderBody(marked, fs.readFileSync(inPath, 'utf8'));
  const title = titleArg || path.basename(inPath).replace(/\.md$/, '');

  // LibreOffice's HTML import drops inline <svg> silently — rasterize to PNG
  // for this path only (md2pdf.cjs keeps native vector SVG). See lib.cjs.
  body = await rasterizeSvgsForDocx(body, playwright, findChromium);

  // No brand.json next to the doc → brand-neutral default, unchanged from before.
  const brand = loadBrand(inPath);
  const primary = (brand && brand.colors && brand.colors.primary) || '#0b3a5b';
  const headerLogo = brand && brand.header && brand.header.showLogo ? brandImageInfo(brand, 'logoHeader') : null;
  const coverLogo = brand && brand.coverPage ? brandImageInfo(brand, 'logoCover') : null;

  // NOTE — DOCX has no real per-page repeating header/footer here: this
  // pipeline hands LibreOffice a single flat HTML document, and its HTML
  // import creates a "Writer/Web" flow, not a paginated Word doc with actual
  // header/footer parts. So branding for DOCX is a ONE-TIME strip at the top
  // (not repeated per page like the PDF's real Playwright header/footer) —
  // a known, accepted gap; the PDF remains the print-faithful, fully
  // per-page-branded artifact. See docgen SKILL.md.
  //
  // Images use explicit width=/height= HTML attributes, not CSS sizing —
  // LibreOffice's HTML->DOCX import does not reliably honour CSS
  // max-width/max-height/object-fit (verified: a cover logo constrained only
  // by CSS rendered at full intrinsic size, overflowing the page). See
  // lib.cjs -> pngSize / brandImageInfo.
  const headerLogoHtml = headerLogo
    ? `<img src="${headerLogo.uri}" width="${Math.round(36 * headerLogo.aspect)}" height="36"/>`
    : '';
  const brandStrip = headerLogoHtml
    ? `<div style="margin-bottom:1.2em;">${headerLogoHtml}</div>`
    : '';

  const coverLogoHtml = coverLogo
    ? `<img src="${coverLogo.uri}" width="${Math.round(180 * coverLogo.aspect)}" height="180"/>`
    : '';
  const coverHtml = coverLogo ? `<div style="text-align:center;margin-bottom:2em;">
    ${coverLogoHtml}
    <div style="font-size:22pt;font-weight:700;color:${primary};margin-top:.6em;">${title}</div>
    <div style="font-size:11pt;color:#6b7f8c;margin-top:.4em;">${brand.name || ''}${brand.name ? ' — ' : ''}Hands-On AI Training</div>
    <hr style="border:none;border-top:2px solid ${primary};margin:1.4em 0;"/>
  </div>` : '';

  const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>${title}</title>
<style>
  body { font-family: "Liberation Sans","DejaVu Sans",Arial,sans-serif; font-size: 11pt; line-height: 1.45; color: #1f2933; }
  h1 { font-size: 20pt; color: ${primary}; border-bottom: 2px solid ${primary}; padding-bottom: 4px; }
  h2 { font-size: 15pt; color: ${primary}; border-bottom: 1px solid #cdd9e2; padding-bottom: 3px; }
  h3 { font-size: 12.5pt; color: ${primary}; }
  h4 { font-size: 11pt; color: #355; }
  a { color: #1565a8; }
  code { font-family: "Liberation Mono",monospace; font-size: 9.5pt; background: #eef2f6; color: #b4253f; padding: 0 3px; }
  h1 code, h2 code, h3 code, h4 code { font-size: 0.75em; }
  pre { background: #0f1f2e; color: #e6edf3; padding: 10px; font-size: 9pt; }
  pre code { background: none; color: inherit; }
  blockquote { border-left: 3px solid #5b9bd5; background: #f3f8fc; padding: 4px 12px; color: #38505f; }
  table { border-collapse: collapse; width: 100%; font-size: 10pt; }
  th, td { border: 1px solid #c5d2dd; padding: 4px 7px; text-align: left; vertical-align: top; }
  th { background: ${primary}; color: #fff; }
  hr { border: none; border-top: 1px solid #d4dde5; }
</style></head><body>${brandStrip}${coverHtml}${body}</body></html>`;

  fs.writeFileSync(outPath, html, 'utf8');
  console.log('HTML written:', outPath);
})().catch(e => { console.error(e); process.exit(1); });
