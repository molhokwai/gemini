// Génère la proposition de partenariat depuis config.json + computed.json.
// Usage: node build_docx.js config.json computed.json sortie.docx [plan.json]
// layout "full" (défaut): page de garde + table des matières, PROPOSITION (1 page, lien vers le tableur
// après les signatures), puis PLAN: les feuilles choisies (plan.json, de export_sheets.py), les larges en paysage.
// layout "one_page": la proposition seule, sur une page (ancien format).
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType,
  AlignmentType, BorderStyle, ShadingType, LevelFormat, ExternalHyperlink, InternalHyperlink,
  Bookmark, PageNumber, Footer, PageOrientation, HeadingLevel, TabStopType, LeaderType,
} = require("docx");

const [cfgPath, compPath, outPath, planPath] = process.argv.slice(2);
const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf8"));
const c = JSON.parse(fs.readFileSync(compPath, "utf8"));

const THEME = cfg.theme_color || "1F4E5F";
const FONT = "Arial";
const fmt = (n) => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " f";
const pc = (x) => { const v = Math.round(x * 1000) / 10; return String(v).replace(".", ",") + "\u00a0%"; };
const sp = cfg.split, P = cfg.partner, O = cfg.operator;
// libellés et textes surchargeables (activité qui n'est pas de la restauration, ex. une formation en ligne)
const L = { equipment: "Matériel", first_month: "Approvisionnement du 1er mois", costs: "Coûts d'approvisionnement", ...(cfg.labels || {}) };
const run = (t, o = {}) => new TextRun({ text: t, font: FONT, size: 19, ...o });
const para = (children, o = {}) =>
  new Paragraph({ spacing: { after: 70 }, ...o, children: Array.isArray(children) ? children : [run(children)] });
const h = (t) =>
  new Paragraph({
    spacing: { before: 130, after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: THEME, space: 1 } },
    children: [run(t, { bold: true, color: THEME, size: 21 })],
  });
const bullet = (children) =>
  new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 40 },
    children: Array.isArray(children) ? children : [run(children)] });

const bd = { style: BorderStyle.SINGLE, size: 4, color: "B7B7B7" };
const borders = { top: bd, bottom: bd, left: bd, right: bd };
function table(widths, rows, headerFill = THEME) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: rows.map((r, i) => new TableRow({
      children: r.map((t, j) => new TableCell({
        width: { size: widths[j], type: WidthType.DXA }, borders,
        margins: { top: 40, bottom: 40, left: 90, right: 90 },
        shading: i === 0 ? { type: ShadingType.CLEAR, fill: headerFill, color: "auto" } : undefined,
        children: [new Paragraph({ alignment: j === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
          children: [run(String(t), { bold: i === 0, color: i === 0 ? "FFFFFF" : "000000", size: 18 })] })],
      })),
    })),
  });
}

const W = 10200; // largeur utile A4 avec marges ~1,0 cm... (11906 - 2*850)
const kids = [];
const FULL = (cfg.layout || "full") !== "one_page";
const URL_ = cfg.spreadsheet_url || "";
if (!URL_) console.error("ATTENTION: spreadsheet_url absent du config: le lien vers le tableur est remplacé par un emplacement à compléter.");
const linkRuns = (label) => URL_
  ? [run(label, { bold: true }), new ExternalHyperlink({ link: URL_, children: [run(URL_, { color: "1155CC", underline: {} })] })]
  : [run(label, { bold: true }), run("[lien du tableur à ajouter]", { color: "CC0000" })];
const bar = (t, o = {}) => new Paragraph({
  heading: o.heading, spacing: { before: o.before ?? 160, after: 100 },
  shading: { type: ShadingType.CLEAR, fill: o.fill || THEME, color: "auto" },
  children: [o.bm ? new Bookmark({ id: o.bm, children: [run(t, { bold: true, color: "FFFFFF", size: o.size || 24 })] })
                  : run(t, { bold: true, color: "FFFFFF", size: o.size || 24 })] });
const h1 = (t, bm) => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { after: 120 },
  children: [new Bookmark({ id: bm, children: [run(t, { bold: true, color: THEME, size: 28 })] })] });
if (FULL) {
  kids.push(h1("PROPOSITION DE PARTENARIAT", "bm_prop"));
  kids.push(bar("PROPOSITION", { heading: HeadingLevel.HEADING_2, bm: "bm_prop2", before: 0 }));
  kids.push(para([run("À l'attention de : ", { bold: true }), run(P)], { spacing: { after: 20 } }));
  kids.push(para([run("Préparé par : ", { bold: true }), run(cfg.prepared_by)]));
} else {
  kids.push(new Paragraph({ spacing: { after: 20 }, children: [run(`PROPOSITION DE PARTENARIAT - ${cfg.activity_name.toUpperCase()}`, { bold: true, size: 30, color: THEME })] }));
  kids.push(para([run(`${cfg.prepared_by} - à l'attention de ${P}`, { italics: true, color: "666666" })]));
}

kids.push(h("1. Le projet"));
kids.push(para(cfg.project_text ||
  `Lancer une activité de ${cfg.products.map((p) => p.name.toLowerCase()).join(" et ")} ${cfg.location_text}. ` +
  `Démarrage prévu : ${cfg.start_date} (achats : ${cfg.purchase_date}).`));

kids.push(h("2. Investissement demandé"));
const capShare = cfg.partner_capital_share;
kids.push(table([5600, 2300, 2300], [
  ["Poste", "Montant", ""],
  [L.equipment, fmt(c.equip_total), ""],
  [L.first_month, fmt(c.monthly_ing), ""],
  [`Investissement total (apport ${P} : ${pc(capShare)})`, fmt(c.invest_total), fmt(c.invest_total * capShare)],
].map((r, i) => (i === 0 ? ["Poste", "Total", `Apport ${P}`] : r))));

kids.push(h("3. Prévisions"));
const lines = [
  ["", "Par jour", "Par semaine", "Par mois"],
  ["Chiffre d'affaires", fmt(c.ca_day), fmt(c.ca_week), fmt(c.ca_month)],
  [L.costs, "", fmt(c.weekly_ing), fmt(c.monthly_ing)],
  ["Bénéfice", "", fmt(c.profit_week), fmt(c.profit_month)],
];
kids.push(table([3600, 2200, 2200, 2200], lines));
kids.push(para([run(cfg.assumptions_text ||
  `Hypothèses : ${cfg.days_per_week} jours/semaine, ${cfg.weeks_per_month} semaines/mois, ventes constantes, aucune croissance supposée. ` +
  cfg.products.map((p) => `${p.volume_per_day} ${p.name.toLowerCase()} à ${fmt(p.price)} / jour`).join(", ") + ".",
  { size: 16, italics: true, color: "666666" })], { spacing: { before: 50, after: 40 } }));

kids.push(h("4. Retour sur investissement et partage des bénéfices"));
const basisTxt = c.basis === "revenue" ? "chiffre d'affaires cumulé" : "bénéfice cumulé";
kids.push(para(cfg.payback_text ||
  `Sur la base du ${basisTxt}, l'investissement est récupéré en environ ${c.payback_days.toFixed(1).replace(".", ",")} jours ouvrés ` +
  `(≈ ${Math.ceil(c.payback_weeks)} semaines). La répartition évolue alors en deux phases :`));
kids.push(table([3000, 3600, 3600], [
  ["", "Phase 1 - avant ROI", "Phase 2 - après ROI"],
  [P, pc(sp.phase1.partner), pc(sp.phase2.partner)],
  [O, pc(sp.phase1.operator), pc(sp.phase2.operator)],
]));

kids.push(h("5. Modalités"));
kids.push(bullet(`Investissement unique, sans nouvel apport demandé.`));
kids.push(bullet(`Bénéfices ${cfg.payment_terms}.`));
for (const x of cfg.extra_clauses || []) kids.push(bullet(x));

kids.push(new Paragraph({ spacing: { before: 260 }, children: [run("Fait à " + (cfg.city || "") + ", le ____ / ____ / ________")] }));
kids.push(new Table({
  width: { size: W, type: WidthType.DXA }, columnWidths: [W / 2, W / 2],
  rows: [new TableRow({ children: [P, O].map((n) => new TableCell({
    width: { size: W / 2, type: WidthType.DXA },
    borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } },
    children: [para([run(n, { bold: true })]), para([run("Signature :")]), para([run(" ")]), para([run(" ")])],
  })) })],
}));

// lien vers le tableur, toujours, après les signatures
kids.push(para(linkRuns("Plan d'affaires complet (tableur) : "), { spacing: { before: 120, after: 40 } }));

const MARGIN = 850, A4 = { width: 11906, height: 16838 };
const footer = new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
  children: [new TextRun({ font: FONT, size: 16, color: "666666", children: ["page ", PageNumber.CURRENT, " / ", PageNumber.TOTAL_PAGES] })] })] });
const section = (children, landscape = false) => ({
  properties: { page: { size: { ...A4, orientation: landscape ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT },
    margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
  footers: { default: footer }, children });

let sections;
if (!FULL) {
  sections = [section(kids)];
} else {
  // ---------- PLAN: feuilles du tableur
  const plan = planPath && fs.existsSync(planPath) ? JSON.parse(fs.readFileSync(planPath, "utf8")) : { sheets: [] };
  const MAXC = 13; // colonnes par tableau (libellé + 12 périodes); au-delà, le tableau est coupé en plusieurs
  const sheetTable = (t, avail, fsize) => {
    const n = t.rows[0].cells.length;
    const chunks = [];
    if (n <= MAXC) chunks.push([...Array(n).keys()]);
    else for (let i = 1; i < n; i += MAXC - 1) chunks.push([0, ...Array.from({ length: Math.min(MAXC - 1, n - i) }, (_, k) => i + k)]);
    // même échelle pour tous les morceaux (celle du premier, le plus large): les colonnes gardent leur largeur
    const scale = avail / chunks[0].reduce((a, i) => a + t.widths[i], 0);
    return chunks.flatMap((idx, ci) => {
      const widths = idx.map((i) => Math.floor(t.widths[i] * scale));
      const tbl = new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
        rows: t.rows.map((r) => new TableRow({ tableHeader: r.header, children: idx.map((i, j) => {
          const c = r.cells[i];
          const fill = r.header ? THEME : (c.fill && c.fill !== "FFFFFF" ? c.fill : undefined);
          const color = r.header ? "FFFFFF" : (c.color && c.color !== "000000" ? c.color : "000000");
          return new TableCell({ width: { size: widths[j], type: WidthType.DXA }, borders,
            margins: { top: 25, bottom: 25, left: 60, right: 60 },
            shading: fill ? { type: ShadingType.CLEAR, fill, color: "auto" } : undefined,
            children: [new Paragraph({ alignment: r.header ? AlignmentType.CENTER : (c.num ? AlignmentType.RIGHT : AlignmentType.LEFT),
              children: [run(c.t, { size: fsize, bold: r.header || c.bold, italics: c.italic && !r.header, color })] })] });
        }) })) });
      return ci < chunks.length - 1 ? [tbl, new Paragraph({ spacing: { after: 80 }, children: [] })] : [tbl];
    });
  };
  const sheetBlocks = (s, k, landscape) => {
    const avail = (landscape ? A4.height : A4.width) - 2 * MARGIN;
    const fsize = landscape && s.max_cols > 10 ? 13 : 16;
    const out = [];
    let titled = false;
    for (const b of s.blocks) {
      if (b.type === "title" && !titled) { out.push(bar(b.text, { heading: HeadingLevel.HEADING_2, bm: `bm_s${k}`, before: 200 })); titled = true; }
      else if (b.type === "title" || b.type === "heading") out.push(bar(b.text, { fill: "9E9E9E", size: 20, before: 140 }));
      else if (b.type === "note") out.push(para([run(b.text, { size: 15, italics: true, color: "808080" })], { spacing: { after: 60 } }));
      else if (b.type === "table") out.push(...sheetTable(b, avail, fsize), new Paragraph({ spacing: { after: 80 }, children: [] }));
    }
    if (!titled) out.unshift(bar(s.name.toUpperCase(), { heading: HeadingLevel.HEADING_2, bm: `bm_s${k}`, before: 200 }));
    return out;
  };
  const sheetTitle = (s) => {
    const t = (s.blocks.find((b) => b.type === "title") || { text: s.name.toUpperCase() }).text;
    return t.startsWith("PLAN D'AFFAIRES") ? s.name.toUpperCase() : t; // le Résumé porte le titre du classeur
  };
  const planSections = [];
  let cur = null;
  plan.sheets.forEach((s, k) => {
    const landscape = s.max_cols > 7;
    if (!cur || cur.landscape !== landscape) { cur = { landscape, children: [] }; planSections.push(cur); }
    if (k === 0) {
      cur.children.push(h1("PLAN", "bm_plan"));
      cur.children.push(para([run("Extraits du plan d'affaires. ", { italics: true, color: "666666" }), ...linkRuns("Tableur complet : ")]));
    }
    cur.children.push(...sheetBlocks(s, k, landscape));
  });

  // ---------- page de garde + table des matières
  const tocLine = (t, bm, level) => new Paragraph({ spacing: { after: 60 }, indent: { left: level * 360 },
    tabStops: [{ type: TabStopType.RIGHT, position: A4.width - 2 * MARGIN, leader: LeaderType.DOT }],
    children: [new InternalHyperlink({ anchor: bm, children: [run(t, { bold: level === 0, size: 20 }), run("\t", { size: 20 })] })] });
  const cover = [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 400, after: 80 }, children: [run("PROPOSITION DE PARTENARIAT", { bold: true, size: 32, color: THEME })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 1200 }, children: [run(`${cfg.activity_name} — ${P}`, { italics: true, size: 20, color: "666666" })] }),
    bar("TABLE DES MATIÈRES", { before: 0 }),
    tocLine("PROPOSITION DE PARTENARIAT", "bm_prop", 0), tocLine("PROPOSITION", "bm_prop2", 1),
    ...(plan.sheets.length ? [tocLine("PLAN", "bm_plan", 0), ...plan.sheets.map((s, k) => tocLine(sheetTitle(s), `bm_s${k}`, 1))] : []),
  ];
  sections = [section(cover), section(kids), ...planSections.map((x) => section(x.children, x.landscape))];
}

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 16 } } } },
  numbering: { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 500, hanging: 250 } } } }] }] },
  sections,
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(outPath, b); console.log("OK", outPath); });
