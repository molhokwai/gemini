#!/usr/bin/env node
// Markdown -> styled A4 PDF via marked + Playwright Chromium.
// Run from the project root:  node .claude/skills/docgen/scripts/md2pdf.cjs <in.md> <out.pdf> ["Title"]
const path = require('path');
const fs = require('fs');
const { projectRequire, findChromium, renderBody, loadBrand, brandImageDataUri } = require('./lib.cjs');

const [, , inPath, outPath, titleArg] = process.argv;
if (!inPath || !outPath) { console.error('Usage: md2pdf.cjs <in.md> <out.pdf> ["Title"]'); process.exit(1); }

const req = projectRequire();
const { marked } = req('marked');
const playwright = req('playwright');

const body = renderBody(marked, fs.readFileSync(inPath, 'utf8'));
const title = titleArg || path.basename(inPath).replace(/\.md$/, '');

// No brand.json next to the doc → brand-neutral default, unchanged from before.
const brand = loadBrand(inPath);
const primary = (brand && brand.colors && brand.colors.primary) || '#0b3a5b';
const accentGreen = brand && brand.colors && brand.colors.accentGreen;
const accentYellow = brand && brand.colors && brand.colors.accentYellow;
const accentRed = brand && brand.colors && brand.colors.accentRed;
const headerLogo = brand && brand.header && brand.header.showLogo ? brandImageDataUri(brand, 'logoHeader') : null;
const coverLogo = brand && brand.coverPage ? brandImageDataUri(brand, 'logoCover') : null;
const accentBar = (accentGreen && accentYellow && accentRed)
  ? `<div style="height:4px;width:100%;display:flex;margin:.3em 0 1.4em;">
       <div style="flex:1;background:${accentGreen}"></div>
       <div style="flex:1;background:${accentYellow}"></div>
       <div style="flex:1;background:${accentRed}"></div>
     </div>`
  : '';

const coverHtml = coverLogo ? `<div style="height:259mm;display:flex;flex-direction:column;align-items:center;
     justify-content:center;text-align:center;page-break-after:always;">
  <img src="${coverLogo}" style="max-width:260px;max-height:260px;object-fit:contain;margin-bottom:2.2em;"/>
  <div style="font-size:26px;font-weight:700;color:${primary};max-width:80%;line-height:1.3;">${title}</div>
  <div style="font-size:13px;color:#6b7f8c;margin-top:1em;">${brand.name || ''}${brand.name ? ' — ' : ''}Hands-On AI Training</div>
  <div style="font-size:10.5px;color:#90a4b3;margin-top:2.4em;">${new Date().toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' })}</div>
  ${accentBar ? `<div style="width:220px;margin-top:1.6em;">${accentBar}</div>` : ''}
</div>` : '';

const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<style>
  @page { size: A4; margin: 18mm 16mm 20mm 16mm; }
  * { box-sizing: border-box; }
  body { font-family: "DejaVu Sans","Noto Sans","Liberation Sans",Arial,sans-serif;
         font-size: 10.5px; line-height: 1.5; color: #1f2933; margin: 0; }
  h1,h2,h3,h4 { color: ${primary}; line-height: 1.25; margin: 1.1em 0 .5em; font-weight: 700; }
  h1 { font-size: 21px; border-bottom: 3px solid ${primary}; padding-bottom: 6px; }
  h2 { font-size: 16px; border-bottom: 1px solid #cdd9e2; padding-bottom: 4px; margin-top: 1.6em; }
  h3 { font-size: 13px; color: ${primary}; }
  h4 { font-size: 11.5px; color: #355; }
  p { margin: .5em 0; }
  a { color: #1565a8; text-decoration: none; }
  code { font-family: "DejaVu Sans Mono","Liberation Mono",monospace; font-size: 9.5px;
         background: #eef2f6; padding: 1px 4px; border-radius: 3px; color: #b4253f; }
  h1 code, h2 code, h3 code, h4 code { font-size: 0.75em; }
  pre { background: #0f1f2e; color: #e6edf3; padding: 12px 14px; border-radius: 6px;
        overflow-x: auto; font-size: 9px; line-height: 1.45; page-break-inside: avoid; }
  pre code { background: none; color: inherit; padding: 0; font-size: 9px; }
  blockquote { border-left: 4px solid #5b9bd5; background: #f3f8fc; margin: .7em 0;
               padding: 6px 14px; color: #38505f; font-style: italic; }
  blockquote p { margin: .3em 0; }
  table { border-collapse: collapse; width: 100%; margin: .8em 0; font-size: 9.5px; page-break-inside: avoid; }
  th, td { border: 1px solid #c5d2dd; padding: 5px 8px; text-align: left; vertical-align: top; }
  th { background: ${primary}; color: #fff; font-weight: 600; }
  tr:nth-child(even) td { background: #f4f8fb; }
  ul, ol { margin: .4em 0 .6em; padding-left: 22px; }
  li { margin: .2em 0; }
  hr { border: none; border-top: 1px solid #d4dde5; margin: 1.4em 0; }
  h2, h3 { page-break-after: avoid; }
  strong { color: #0b2a40; }
</style></head><body>${coverHtml}${body}</body></html>`;

const headerTemplate = headerLogo
  ? `<div style="font-size:7px;color:#90a4b3;width:100%;padding:0 16mm;display:flex;align-items:center;justify-content:space-between;">
       <img src="${headerLogo}" style="height:19px;"/><span>${title}</span></div>`
  : `<div style="font-size:7px;color:#90a4b3;width:100%;padding:0 16mm;text-align:right;">${title}</div>`;

(async () => {
  const execPath = findChromium(playwright);
  const browser = await playwright.chromium.launch(execPath ? { executablePath: execPath } : {});
  const page = await browser.newPage();
  await page.setContent(html, { waitUntil: 'networkidle' });
  await page.pdf({
    path: outPath, format: 'A4', printBackground: true,
    margin: { top: '18mm', bottom: '20mm', left: '16mm', right: '16mm' },
    displayHeaderFooter: true,
    headerTemplate,
    footerTemplate: `<div style="font-size:7px;color:#90a4b3;width:100%;padding:0 16mm;text-align:right;">
        Page <span class="pageNumber"></span> / <span class="totalPages"></span></div>`,
  });
  await browser.close();
  console.log('PDF written:', outPath);
})().catch(e => { console.error(e); process.exit(1); });
