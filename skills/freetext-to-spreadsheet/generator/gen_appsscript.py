"""
Apps Script generators (JavaScript sources) for the two Apps-Script patterns of a sheet spec:

  form_gs(spec, ss_id, gid)    pattern form-trigger  : Google Form for a flat table + onFormSubmit handler that writes/upserts the row
  import_gs(spec, ss_id, gid)  pattern import-trigger: Import tab + installable onChange processor (DSL text -> final table)

Both follow the conventions proven on the grading form (2026-09-21): standalone project, MODE switch, `main` is the ONLY top-level function
declaration (helpers are `var x = function`, the trigger handler is set on globalThis) so the editor's Run dropdown stays deterministic,
the target sheet is addressed by gid (renaming the tab is safe), rows are written to an explicit range found from an anchor column
(never appendRow: pre-seeded formulas would break getLastRow), and every parsing/coercion helper is a pure function (unit-testable under node).
The config is embedded as JSON; nothing else is spec-specific.
"""
import json

MSG = {
    'fr': {'added': 'Ajouté à "{tab}" : {n} ligne(s).', 'warnings': 'Avertissements :', 'colAbsent': 'colonne "{c}" absente de "{tab}", ignorée pour cette ligne.',
           'notInRef': '{h} : "{v}" absent de "{tab}" — ligne ajoutée quand même, à vérifier.', 'required': '{h} : valeur requise absente — ligne ajoutée quand même, à vérifier.',
           'badDate': 'date non reconnue : "{v}"', 'annotated': '--- Texte annoté ---', 'noHeader': 'ligne de données sans en-tête de colonnes ignorée : "{l}"',
           'badVal': '{h} : "{v}" non reconnu — laissé vide.', 'notChoice': '{h} : "{v}" n\'est pas dans {c} — conservé tel quel, à vérifier.', 'emptyName': '(vide)'},
    'en': {'added': 'Added to "{tab}": {n} row(s).', 'warnings': 'Warnings:', 'colAbsent': 'column "{c}" is not in "{tab}", ignored for this row.',
           'notInRef': '{h}: "{v}" not found in "{tab}" — row added anyway, please check.', 'required': '{h}: required value missing — row added anyway, please check.',
           'badDate': 'unrecognised date: "{v}"', 'annotated': '--- Annotated text ---', 'noHeader': 'data line without a column header ignored: "{l}"',
           'badVal': '{h}: "{v}" not recognised — left empty.', 'notChoice': '{h}: "{v}" is not in {c} — kept as written, please check.', 'emptyName': '(empty)'},
}


def _cols_cfg(spec):
    keep = ('key', 'header', 'type', 'required', 'default', 'choices', 'choices_from', 'min', 'max', 'aliases', 'formula', 'llm')
    return [{k: c[k] for k in keep if k in c} for c in spec['columns']]


def _anchor_key(spec):
    for c in spec['columns']:
        if c.get('required') and c['type'] != 'formula':
            return c['key']
    return next(c['key'] for c in spec['columns'] if c['type'] != 'formula')


def _sample(c, i=0):
    t = c['type']
    if t == 'choice':
        return (c.get('choices') or ['TEST'])[0]
    return {'date': '2026-01-02', 'time': '09:30', 'datetime': '2026-01-02 09:30', 'integer': str(max(c.get('min', 1), 1) if c.get('min', 1) <= 5 else c['min']),
            'number': str(c.get('min', 1)), 'percent': '50', 'boolean': 'Yes', 'link': 'https://example.com', 'text': f'TEST {c["header"]}',
            'longtext': f'TEST {c["header"]}'}.get(t, 'TEST')


COMMON_JS = r'''
var normKey_ = function (s) {
  return String(s).trim().toLowerCase().replace(/[éèêë]/g, 'e').replace(/[àâä]/g, 'a').replace(/[ôö]/g, 'o').replace(/[ûü]/g, 'u').replace(/[îï]/g, 'i').replace(/ç/g, 'c');
};
var MONTHS_ = { 'janv': 0, 'jan': 0, 'january': 0, 'janvier': 0, 'févr': 1, 'fev': 1, 'fév': 1, 'feb': 1, 'february': 1, 'février': 1, 'mars': 2, 'mar': 2, 'march': 2,
  'avr': 3, 'apr': 3, 'april': 3, 'avril': 3, 'mai': 4, 'may': 4, 'juin': 5, 'jun': 5, 'june': 5, 'juil': 6, 'jul': 6, 'july': 6, 'juillet': 6,
  'août': 7, 'aout': 7, 'aug': 7, 'august': 7, 'sept': 8, 'sep': 8, 'september': 8, 'septembre': 8, 'oct': 9, 'october': 9, 'octobre': 9,
  'nov': 10, 'november': 10, 'novembre': 10, 'déc': 11, 'dec': 11, 'december': 11, 'décembre': 11 };
// -> {date: Date|null, warning: string|null}
var parseDateLabel_ = function (label) {
  var s = String(label).trim(), m;
  if ((m = s.match(/(\d{4})-(\d{1,2})-(\d{1,2})/))) { var d0 = new Date(+m[1], +m[2] - 1, +m[3]); return d0.getMonth() === +m[2] - 1 ? { date: d0 } : { date: null, warning: 'invalid date: ' + s }; }
  if ((m = s.match(/(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})/))) { var d1 = new Date(+m[3], +m[2] - 1, +m[1]); return d1.getMonth() === +m[2] - 1 ? { date: d1 } : { date: null, warning: 'invalid date: ' + s }; }
  if ((m = s.match(/(\d{1,2})\s+([a-zéûô]+)\.?\s+(\d{4})/i))) {
    var mo = MONTHS_[m[2].toLowerCase().replace(/\.$/, '')];
    if (mo === undefined) return { date: null, warning: 'unknown month: ' + m[2] };
    var d2 = new Date(+m[3], mo, +m[1]);
    return d2.getMonth() === mo ? { date: d2 } : { date: null, warning: 'invalid date: ' + s };
  }
  return { date: null, warning: null };
};
var extractNumber_ = function (s) { var m = String(s).replace(/ /g, '').replace(/ /g, '').match(/-?\d+(?:[.,]\d+)?/); return m ? parseFloat(m[0].replace(',', '.')) : null; };
var parseTime_ = function (s) {
  var m = String(s).toLowerCase().match(/\b(\d{1,2})\s*[:h]\s*(\d{2})?\s*(am|pm)?/) || String(s).toLowerCase().match(/\b(\d{1,2})()\s*(am|pm)\b/);
  if (!m) return null;
  var h = +m[1], mi = +(m[2] || 0);
  if (m[3] === 'pm' && h < 12) h += 12;
  if (m[3] === 'am' && h === 12) h = 0;
  return h < 24 && mi < 60 ? (h * 60 + mi) / 1440 : null;      // fraction of a day: the cell's time format shows hh:mm
};
// Coerces one raw text to the value to write ('' = leave empty). Pure. Pushes human warnings.
var coerceValue_ = function (col, raw, warnings, msg) {
  var v = String(raw === undefined || raw === null ? '' : raw).trim();
  if (v === '' || /^(-|—|\?|n\/a|na|none|null|aucun|aucune|rien)$/i.test(v)) return '';
  var t = col.type, bad = function () { warnings.push(msg.badVal.replace('{h}', col.header).replace('{v}', v)); return ''; };
  if (t === 'text' || t === 'longtext' || t === 'link') return v;
  if (t === 'date') { var pd = parseDateLabel_(v); if (pd.warning) warnings.push(pd.warning); return pd.date || bad(); }
  if (t === 'time') { var tm = parseTime_(v); return tm === null ? bad() : tm; }
  if (t === 'datetime') { var dd = parseDateLabel_(v); if (!dd.date) return bad(); var tt = parseTime_(v.replace(/\d{4}-\d{2}-\d{2}/, '')); return new Date(dd.date.getTime() + Math.round((tt || 0) * 86400000)); }
  if (t === 'integer' || t === 'number' || t === 'percent') {
    var n = extractNumber_(v);
    if (n === null) return bad();
    if (t === 'percent') n = n / 100;
    var lo = col.min === undefined ? null : (t === 'percent' ? col.min / 100 : col.min), hi = col.max === undefined ? null : (t === 'percent' ? col.max / 100 : col.max);
    if ((lo !== null && n < lo) || (hi !== null && n > hi)) return bad();
    if (t === 'integer' && n !== Math.floor(n)) return bad();
    return n;
  }
  if (t === 'boolean') { var b = v.toLowerCase(); if (/^(1|yes|y|true|oui|vrai|ok|x)$/.test(b)) return 1; if (/^(0|no|n|non|false|faux)$/.test(b)) return 0; return bad(); }
  if (t === 'choice') {
    var list = col.choices || col.resolvedChoices || [];
    for (var i = 0; i < list.length; i++) if (normKey_(list[i]) === normKey_(v)) return list[i];
    if (list.length) warnings.push(msg.notChoice.replace('{h}', col.header).replace('{v}', v).replace('{c}', JSON.stringify(list)));
    return v;
  }
  return v;
};
'''

IMPORT_JS = r'''/**
 * GENERATED from __SPEC__ — spec hash __HASH__ — edit the spec and regenerate, do not hand-edit.
 *
 * Import-trigger processor for "__FINAL__" (spec id __ID__). Standalone Apps Script project.
 *   MODE 'setup'  : creates the Import tab "__IMPORT__" (Horodatage, Texte, Statut, Résultat) if missing and installs the onChange trigger
 *   MODE 'test'   : parses a sample DSL WITHOUT writing anything and logs the result (safe)
 *   MODE 'status' : logs the installed triggers (harmless default)
 * Flow: a row [timestamp, DSL text, "En attente", ""] appears in the Import tab (skill / AppSheet paste) -> the onChange trigger parses the DSL
 * (## <date> blocks; header line; data lines; last column absorbs commas; lines ending with ✅ are skipped), validates NON-BLOCKINGLY
 * (unknown column, value not in a reference tab, value not in the allowed list: warning, row still added), writes the rows to the final table
 * at an explicit next row (never appendRow), then sets Statut = "Traité" and Résultat = summary + annotated text.
 */
var MODE = 'status';
var CFG = __CFG__;
''' + COMMON_JS + r'''
var splitLine_ = function (line, n) {
  var parts = line.split(',');
  if (parts.length <= n) return parts.map(function (p) { return p.trim(); });
  var head = parts.slice(0, n - 1), tail = parts.slice(n - 1).join(',');
  head.push(tail);
  return head.map(function (p) { return p.trim(); });
};

// header name (normalised) -> column key, from header / key / aliases of the final table
var headerMap_ = function (cfg) {
  var map = {};
  cfg.columns.forEach(function (c) {
    [c.header, c.key].concat(c.aliases || []).forEach(function (n) { map[normKey_(n)] = c.key; });
  });
  return map;
};

// PURE: DSL text -> {records, warnings, lines(annotated)}. refs = {tab: {normalisedValue: true}} (or null). No sheet access.
var parseImportText_ = function (text, cfg, refs) {
  var msg = cfg.msg, map = headerMap_(cfg), extra = {};
  (cfg.dslExtra || []).forEach(function (n) { extra[normKey_(n)] = true; });
  var byKey = {}; cfg.columns.forEach(function (c) { byKey[c.key] = c; });
  var lines = text.split('\n'), records = [], warnings = [], warnedCols = {};
  var dateObj = null, dateLabel = null, active = null, awaiting = false;
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i], dm = line.match(/^\s*##\s*(.+?)\s*$/);
    if (dm) {
      var pd = parseDateLabel_(dm[1]);
      dateLabel = dm[1]; dateObj = pd.date; if (pd.warning) warnings.push(pd.warning);
      if (!pd.date && !pd.warning) warnings.push(msg.badDate.replace('{v}', dm[1]));
      active = null; awaiting = true; continue;
    }
    if (!line.trim()) continue;
    if (awaiting) { active = line.split(',').map(function (c) { return c.trim(); }); awaiting = false; continue; }
    if (!active) { warnings.push(msg.noHeader.replace('{l}', line.slice(0, 40))); continue; }
    if (/✅\s*$/.test(line)) continue;
    var fields = splitLine_(line, active.length), cells = {}, rowWarn = [];
    for (var j = 0; j < active.length; j++) {
      var name = normKey_(active[j]), raw = fields[j];
      if (raw === undefined || raw === '') continue;
      if (extra[name]) continue;                                   // accepted, used for matching, not stored
      var key = map[name];
      if (!key) { if (!warnedCols[dateLabel + '|' + name]) { warnedCols[dateLabel + '|' + name] = 1; warnings.push(msg.colAbsent.replace('{c}', name).replace('{tab}', cfg.finalTitle)); } continue; }
      cells[key] = raw;
    }
    var values = {};
    cfg.columns.forEach(function (c) {
      if (c.type === 'formula') return;
      var raw = cells[c.key];
      if ((raw === undefined || raw === '') && c.type === 'date' && cfg.dateBlocks && dateObj) { values[c.key] = dateObj; return; }   // block date fills the date column
      if (raw === undefined || raw === '') { if (c.required) rowWarn.push(msg.required.replace('{h}', c.header)); return; }
      values[c.key] = coerceValue_(c, raw, rowWarn, msg);
    });
    (cfg.references || []).forEach(function (ref) {
      var set = refs && refs[ref.tab];
      if (!set) return;
      ref.usedBy.forEach(function (k) {
        var v = values[k];
        if (v !== undefined && v !== '' && !set[normKey_(v)]) rowWarn.push(msg.notInRef.replace('{h}', byKey[k].header).replace('{v}', v).replace('{tab}', ref.tab));
      });
    });
    warnings = warnings.concat(rowWarn);
    records.push({ values: values, dateLabel: dateLabel });
    lines[i] = line.replace(/\s*$/, '') + ' ✅';
  }
  return { records: records, warnings: warnings, annotated: lines.join('\n') };
};

var summarize_ = function (res, cfg) {
  var out = [cfg.msg.added.replace('{tab}', cfg.finalTitle).replace('{n}', res.records.length)];
  res.records.forEach(function (r) {
    var parts = [];
    cfg.columns.forEach(function (c) { var v = r.values[c.key]; if (v !== undefined && v !== '') parts.push(c.key + '=' + (v instanceof Date ? v.toISOString().slice(0, 10) : v)); });
    out.push('  ' + (r.dateLabel ? '[' + r.dateLabel + '] ' : '') + parts.join(', '));
  });
  if (res.warnings.length) { out.push(cfg.msg.warnings); res.warnings.forEach(function (w) { out.push('  ' + w); }); }
  return out.join('\n');
};

var loadRefs_ = function (ss, cfg) {
  var refs = {};
  (cfg.references || []).forEach(function (ref) {
    var sh = ss.getSheetByName(ref.tab);
    if (!sh) return;
    var data = sh.getDataRange().getValues(), idx = -1;
    data[0].forEach(function (h, i) { if (normKey_(h) === normKey_(ref.keyColumn)) idx = i; });
    if (idx < 0) return;
    var set = {}; for (var r = 1; r < data.length; r++) if (data[r][idx] !== '') set[normKey_(data[r][idx])] = true;
    refs[ref.tab] = set;
  });
  return refs;
};

var finalSheet_ = function (ss) { return ss.getSheets().filter(function (s) { return s.getSheetId() === CFG.gid; })[0]; };

// writes records at explicit rows found from the anchor column (never appendRow)
var writeRecords_ = function (ss, cfg, records) {
  var sh = finalSheet_(ss);
  if (!sh) throw new Error('Final table (gid ' + cfg.gid + ') not found');
  var width = cfg.columns.length, anchorIdx = cfg.columns.map(function (c) { return c.key; }).indexOf(cfg.anchorKey) + 1;
  var anchorVals = sh.getRange(1, anchorIdx, Math.max(sh.getMaxRows(), 2), 1).getValues();
  var next = 2;
  for (var r = anchorVals.length - 1; r >= 1; r--) { if (anchorVals[r][0] !== '') { next = r + 2; break; } }
  records.forEach(function (rec) {
    var row = cfg.columns.map(function (c) { return c.type === 'formula' || rec.values[c.key] === undefined ? '' : rec.values[c.key]; });
    sh.getRange(next, 1, 1, width).setValues([row]);
    cfg.columns.forEach(function (c, i) { if (c.type === 'formula') sh.getRange(next, i + 1).setFormula(c.formula.replace(/\{row\}/g, String(next))); });
    next++;
  });
};

globalThis.processImportPending = function (e) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return;
  try {
    var ss = SpreadsheetApp.openById(CFG.ssId), sh = ss.getSheetByName(CFG.importTab);
    if (!sh) return;
    var data = sh.getDataRange().getValues(), refs = null;
    for (var r = 1; r < data.length; r++) {
      var texte = data[r][1], statut = data[r][2];
      if (!texte || statut === 'Traité') continue;
      refs = refs || loadRefs_(ss, CFG);
      var res = parseImportText_(String(texte), CFG, refs);
      writeRecords_(ss, CFG, res.records);
      sh.getRange(r + 1, 4).setValue(summarize_(res, CFG) + '\n\n' + CFG.msg.annotated + '\n' + res.annotated);
      sh.getRange(r + 1, 3).setValue('Traité');
    }
  } finally { lock.releaseLock(); }
};

var setup_ = function () {
  var ss = SpreadsheetApp.openById(CFG.ssId), sh = ss.getSheetByName(CFG.importTab);
  if (!sh) {
    sh = ss.insertSheet(CFG.importTab);
    sh.getRange(1, 1, 1, 4).setValues([['Horodatage', 'Texte', 'Statut', 'Résultat']]).setFontWeight('bold');
    sh.setFrozenRows(1);
    sh.getRange(2, 2, 999, 1).setWrap(true);
  }
  var has = ScriptApp.getProjectTriggers().some(function (t) { return t.getHandlerFunction() === 'processImportPending'; });
  if (!has) ScriptApp.newTrigger('processImportPending').forSpreadsheet(ss).onChange().create();
  Logger.log('Import tab ready: ' + CFG.importTab + ' — onChange trigger ' + (has ? 'already installed' : 'installed'));
};

var test_ = function () {
  var res = parseImportText_(CFG.sampleDsl, CFG, null);
  Logger.log(summarize_(res, CFG));
  Logger.log('(test: nothing was written)');
};

var status_ = function () {
  ScriptApp.getProjectTriggers().forEach(function (t) { Logger.log('trigger: ' + t.getHandlerFunction() + ' / ' + t.getEventType()); });
};

function main() {
  if (MODE === 'setup') setup_();
  else if (MODE === 'test') test_();
  else if (MODE === 'status') status_();
  else throw new Error('Unknown MODE ' + MODE);
}
'''

FORM_JS = r'''/**
 * GENERATED from __SPEC__ — spec hash __HASH__ — edit the spec and regenerate, do not hand-edit.
 *
 * Google Form + onFormSubmit for "__FINAL__" (spec id __ID__). Standalone Apps Script project.
 *   MODE 'setup'   : creates the form (once), links raw answers to the spreadsheet, installs the onFormSubmit trigger, logs the form URLs
 *   MODE 'rebuild' : empties the form and rebuilds its questions from CFG (same URL)
 *   MODE 'test'    : submits one fake response (values marked TEST) so the trigger writes a row — clear that row + the response afterwards
 *   MODE 'cleanup' : deletes all form responses
 *   MODE 'status'  : logs URLs and triggers (harmless default)
 * The handler writes to an explicit row found from an anchor column (never appendRow), upserts on CFG.upsertOn when set, writes formula
 * columns per row, and never touches an existing formula cell on update. Sheet addressed by gid.
 */
var MODE = 'status';
var CFG = __CFG__;
''' + COMMON_JS + r'''
var sheet_ = function () { return SpreadsheetApp.openById(CFG.ssId).getSheetById(CFG.gid); };
var YES = 'Yes', NO = 'No', NOT_GIVEN = 'Not given';

var rangeChoices_ = function (ref) {          // "Tab!A2:A" -> [values]
  var p = ref.split('!'), sh = SpreadsheetApp.openById(CFG.ssId).getSheetByName(p[0].replace(/^'|'$/g, ''));
  if (!sh) return [];
  return sh.getRange(p[1]).getValues().map(function (r) { return r[0]; }).filter(function (v) { return v !== ''; });
};

var populate_ = function (form) {
  form.setDescription(CFG.description);
  form.setCollectEmail(false); form.setAllowResponseEdits(false); form.setShowLinkToRespondAgain(true);
  CFG.asked.forEach(function (c) {
    var it, req = !!c.required;
    if (c.type === 'date') it = form.addDateItem();
    else if (c.type === 'time') it = form.addTimeItem();
    else if (c.type === 'datetime') it = form.addDateTimeItem();
    else if (c.type === 'longtext') it = form.addParagraphTextItem();
    else if (c.type === 'choice') {
      var ch = c.choices || rangeChoices_(c.choices_from);
      it = form.addListItem().setChoiceValues(ch);
    } else if (c.type === 'boolean') it = form.addListItem().setChoiceValues(CFG.notGiven ? [YES, NO, NOT_GIVEN] : [YES, NO]);
    else {
      it = form.addTextItem();
      if (c.type === 'integer' || c.type === 'number') {
        var v = (c.min !== undefined && c.max !== undefined) ? FormApp.createTextValidation().requireNumberBetween(c.min, c.max).build() : FormApp.createTextValidation().requireNumber().build();
        it.setValidation(v);
      } else if (c.type === 'percent') it.setValidation(FormApp.createTextValidation().setHelpText('0 to 100').requireNumberBetween(0, 100).build());
      else if (c.type === 'link') it.setValidation(FormApp.createTextValidation().requireTextIsUrl().build());
    }
    it.setTitle(c.header).setRequired(req);
    if (c.note || c.llm) it.setHelpText(c.note || c.llm);
  });
};

// PURE: raw form answers ({header: string}) -> {key: value to write}. tz-aware date helpers are passed in.
var answersToValues_ = function (answers, cfg, todayDate, nowDate) {
  var values = {}, warnings = [];
  cfg.columns.forEach(function (c) {
    if (c.type === 'formula') return;
    var raw = answers[c.header];
    if (c.type === 'boolean') raw = raw === 'Yes' ? '1' : (raw === 'No' ? '0' : '');
    if (c.type === 'choice' && raw === NOT_GIVEN) raw = '';
    var v = coerceValue_(c, raw, warnings, cfg.msg);
    if (v === '' && c.default === 'today') v = todayDate;
    if (v === '' && c.default === 'now') v = c.type === 'datetime' ? nowDate : (nowDate.getHours() * 60 + nowDate.getMinutes()) / 1440;
    if (v === '' && c.default !== undefined && c.default !== 'today' && c.default !== 'now') v = coerceValue_(c, c.default, warnings, cfg.msg);
    values[c.key] = v;
  });
  return { values: values, warnings: warnings };
};

var cellText_ = function (v, tz) { return v instanceof Date ? Utilities.formatDate(v, tz, 'yyyy-MM-dd') : normKey_(v); };

globalThis.onGeneratedFormSubmit = function (e) {
  var ss = SpreadsheetApp.openById(CFG.ssId), tz = ss.getSpreadsheetTimeZone(), sh = sheet_();
  var answers = {};
  e.response.getItemResponses().forEach(function (ir) { var r = ir.getResponse(); answers[ir.getItem().getTitle()] = Array.isArray(r) ? r.join(', ') : r; });
  var now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var res = answersToValues_(answers, CFG, today, now);
  CFG.required.forEach(function (k) { if (res.values[k] === '' || res.values[k] === undefined) throw new Error('Missing required value: ' + k); });
  var width = CFG.columns.length, keys = CFG.columns.map(function (c) { return c.key; });
  var data = sh.getRange(1, 1, Math.max(sh.getMaxRows(), 2), width).getValues();
  var row = -1;
  if (CFG.upsertOn.length) {
    var want = CFG.upsertOn.map(function (k) { return cellText_(res.values[k], tz); });
    for (var r = 1; r < data.length && row < 0; r++) {
      var same = CFG.upsertOn.every(function (k, i) { return cellText_(data[r][keys.indexOf(k)], tz) === want[i]; });
      if (same && data[r][keys.indexOf(CFG.upsertOn[0])] !== '') row = r + 1;
    }
  }
  var updating = row > 0;
  if (!updating) {
    var ai = keys.indexOf(CFG.anchorKey);
    row = 2;
    for (var q = data.length - 1; q >= 1; q--) { if (data[q][ai] !== '') { row = q + 2; break; } }
  }
  CFG.columns.forEach(function (c, i) {
    if (c.type === 'formula') { if (!updating) sh.getRange(row, i + 1).setFormula(c.formula.replace(/\{row\}/g, String(row))); return; }
    sh.getRange(row, i + 1).setValue(res.values[c.key] === undefined ? '' : res.values[c.key]);
  });
  Logger.log((updating ? 'Updated' : 'Appended') + ' row ' + row + (res.warnings.length ? ' — warnings: ' + res.warnings.join(' | ') : ''));
};

var installTrigger_ = function (form) {
  var has = ScriptApp.getProjectTriggers().some(function (t) { return t.getHandlerFunction() === 'onGeneratedFormSubmit'; });
  if (!has) ScriptApp.newTrigger('onGeneratedFormSubmit').forForm(form).onFormSubmit().create();
};

var setup_ = function () {
  var props = PropertiesService.getScriptProperties(), id = props.getProperty('FORM_ID'), form;
  if (id) form = FormApp.openById(id);
  else {
    form = FormApp.create(CFG.formTitle);
    populate_(form);
    form.setDestination(FormApp.DestinationType.SPREADSHEET, CFG.ssId);
    props.setProperty('FORM_ID', form.getId());
  }
  installTrigger_(form);
  Logger.log('FORM PUBLISHED URL: ' + form.getPublishedUrl());
  Logger.log('FORM EDIT URL: ' + form.getEditUrl());
};

var rebuild_ = function () {
  var id = PropertiesService.getScriptProperties().getProperty('FORM_ID');
  if (!id) throw new Error('No form yet — run MODE setup first');
  var form = FormApp.openById(id);
  form.getItems().forEach(function (it) { form.deleteItem(it); });
  form.removeDestination();
  form.setTitle(CFG.formTitle);
  populate_(form);
  form.setDestination(FormApp.DestinationType.SPREADSHEET, CFG.ssId);
  installTrigger_(form);
  Logger.log('Rebuilt ' + form.getItems().length + ' items. URL: ' + form.getPublishedUrl());
};

var test_ = function () {
  var form = FormApp.openById(PropertiesService.getScriptProperties().getProperty('FORM_ID')), r = form.createResponse(), byHeader = {};
  CFG.asked.forEach(function (c) { byHeader[c.header] = c; });
  form.getItems().forEach(function (it) {
    var c = byHeader[it.getTitle()];
    if (!c) return;
    var s = CFG.samples[c.key], t = c.type;
    if (t === 'date') { var p = s.split('-'); r.withItemResponse(it.asDateItem().createResponse(new Date(Date.UTC(+p[0], +p[1] - 1, +p[2], 12)))); }
    else if (t === 'time') { var q = s.split(':'); r.withItemResponse(it.asTimeItem().createResponse(+q[0], +q[1])); }
    else if (t === 'datetime') { var d = s.split(/[- :]/); r.withItemResponse(it.asDateTimeItem().createResponse(+d[0], +d[1], +d[2], +d[3], +d[4])); }
    else if (t === 'longtext') r.withItemResponse(it.asParagraphTextItem().createResponse(s));
    else if (t === 'choice' || t === 'boolean') r.withItemResponse(it.asListItem().createResponse(t === 'boolean' ? YES : s));
    else r.withItemResponse(it.asTextItem().createResponse(s));
  });
  r.submit();
  Logger.log('Test response submitted (values start with TEST) — clear the resulting row and the response afterwards.');
};

var cleanup_ = function () { FormApp.openById(PropertiesService.getScriptProperties().getProperty('FORM_ID')).deleteAllResponses(); Logger.log('All form responses deleted.'); };

var status_ = function () {
  var id = PropertiesService.getScriptProperties().getProperty('FORM_ID');
  Logger.log('FORM_ID=' + id);
  if (id) { var f = FormApp.openById(id); Logger.log('URL: ' + f.getPublishedUrl() + '  EDIT: ' + f.getEditUrl() + '  items: ' + f.getItems().length); }
  ScriptApp.getProjectTriggers().forEach(function (t) { Logger.log('trigger: ' + t.getHandlerFunction() + ' / ' + t.getEventType()); });
};

function main() {
  if (MODE === 'setup') setup_();
  else if (MODE === 'rebuild') rebuild_();
  else if (MODE === 'test') test_();
  else if (MODE === 'cleanup') cleanup_();
  else if (MODE === 'status') status_();
  else throw new Error('Unknown MODE ' + MODE);
}
'''


def _msg(spec):
    return MSG[spec['sheet']['language']]


def sample_dsl(spec):
    """A tiny DSL text exercising the declared DSL columns (used by MODE test and by the node unit tests)."""
    keymap = {c['key']: c for c in spec['columns']}
    imp = spec['intake']['import']
    heads = [keymap[k]['header'] for k in imp['dsl_columns']]
    vals = [_sample(keymap[k]) for k in imp['dsl_columns']]
    return f'## 2 janv 2026\n{", ".join(heads)}\n{", ".join(vals)}'


def import_gs(spec, ss_id, gid, spec_name, spec_hash):
    imp = spec['intake']['import']
    cfg = {'ssId': ss_id, 'gid': gid, 'finalTitle': spec['sheet']['title'], 'importTab': imp['tab'], 'columns': _cols_cfg(spec),
           'anchorKey': _anchor_key(spec), 'dateBlocks': bool(imp.get('date_blocks', True)),
           'dslExtra': [x['name'] for x in imp.get('dsl_extra_columns', [])],
           'references': [{'tab': r['tab'], 'keyColumn': r['key_column'], 'usedBy': r['used_by']} for r in spec.get('reference', [])],
           'msg': _msg(spec), 'sampleDsl': sample_dsl(spec)}
    return (IMPORT_JS.replace('__SPEC__', spec_name).replace('__HASH__', spec_hash).replace('__FINAL__', spec['sheet']['title'])
            .replace('__ID__', spec['sheet']['id']).replace('__IMPORT__', imp['tab']).replace('__CFG__', json.dumps(cfg, ensure_ascii=False, indent=1)))


def form_gs(spec, ss_id, gid, spec_name, spec_hash):
    fm = spec['intake'].get('form', {})
    asked = []
    for c in spec['columns']:
        if c['type'] == 'formula':
            continue
        if c['type'] == 'datetime' and c.get('default') == 'now' and not c.get('required'):
            continue                                   # timestamp filled by the handler
        asked.append({k: c[k] for k in ('key', 'header', 'type', 'required', 'choices', 'choices_from', 'min', 'max', 'note', 'llm') if k in c})
    cfg = {'ssId': ss_id, 'gid': gid, 'formTitle': fm.get('title') or spec['sheet']['title'], 'description': spec['sheet']['description'],
           'columns': _cols_cfg(spec), 'asked': asked, 'anchorKey': _anchor_key(spec), 'upsertOn': spec['sheet'].get('upsert_on') or [],
           'required': [c['key'] for c in spec['columns'] if c.get('required') and c['type'] != 'formula'],
           'notGiven': bool(fm.get('not_given_choice', True)), 'msg': _msg(spec),
           'samples': {c['key']: _sample(c) for c in spec['columns']}}
    return (FORM_JS.replace('__SPEC__', spec_name).replace('__HASH__', spec_hash).replace('__FINAL__', spec['sheet']['title'])
            .replace('__ID__', spec['sheet']['id']).replace('__CFG__', json.dumps(cfg, ensure_ascii=False, indent=1)))
