# -*- coding: utf-8 -*-
"""Génère le plan d'affaires partenarial (.xlsx) + computed.json depuis un config JSON.

Usage: python3 build_xlsx.py config.json sortie.xlsx
Tout est piloté par formules: seules les cellules jaunes (Paramètres, Achats, Investissement)
contiennent des valeurs saisies. computed.json reprend les chiffres clés pour le .docx
et sert de contrôle croisé après recalcul.
"""
import json, math, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

cfg = json.load(open(sys.argv[1], encoding="utf-8"))
OUT = sys.argv[2]

# ------------------------------------------------------------------ valeurs dérivées
DPW, WPM = cfg["days_per_week"], cfg["weeks_per_month"]
DPM = DPW * WPM
P, ING, EQ = cfg["products"], cfg["ingredients"], cfg["equipment"]
sp = cfg["split"]
CAP = cfg.get("partner_capital_share", 1.0)

equip_total = sum(e["qty"] * e["unit_price"] for e in EQ)
ca_day = sum(p["price"] * p["volume_per_day"] for p in P)
ca_week, ca_month = ca_day * DPW, ca_day * DPM
units_month = sum(p["volume_per_day"] for p in P) * DPM
# charge variable (optionnelle): "pct_of_revenue" (ex. frais de paiement 2 %) ou "per_unit" (coût par unité vendue);
# sinon "monthly_cost" fixe. Dans le classeur, la charge variable est une formule liée aux Ventes.
def ing_monthly(i):
    if "pct_of_revenue" in i: return i["pct_of_revenue"] * ca_month
    if "per_unit" in i: return i["per_unit"] * units_month
    return i["monthly_cost"]
monthly_ing = sum(ing_monthly(i) for i in ING)
weekly_ing = monthly_ing / WPM
invest_total = equip_total + monthly_ing
seed_total = equip_total + weekly_ing
LBL = {"charges_title": "ACHATS & CHARGES - INGRÉDIENTS / MATIÈRES",
       "charges_note": "Achats traités comme un réapprovisionnement mensuel récurrent (pas un stock unique).",
       "equipment": "Matériel", **cfg.get("labels", {})}
profit_week, profit_month = ca_week - weekly_ing, ca_month - monthly_ing
basis = sp.get("roi_basis", "revenue")
per_day = ca_day if basis == "revenue" else profit_month / DPM
# "roi_on_partner_share": le ROI se mesure sur la part de Phase 1 du partenaire (ce qu'il reçoit), pas sur le total
ON_SHARE = bool(sp.get("roi_on_partner_share"))
if ON_SHARE: per_day *= sp["phase1"]["partner"]
payback_days = invest_total / per_day
# semaine: arrondi au-dessus (on ne bascule qu'une fois l'investissement récupéré);
# mois: arrondi au plus proche (un mois est trop grossier pour un arrondi au-dessus),
# sauf ROI sur la part du partenaire: au-dessus (il doit être entièrement remboursé)
switch_week = sp.get("switch_week") or math.ceil(payback_days / DPW)
switch_month = sp.get("switch_month") or max(1, math.ceil(payback_days / DPM) if ON_SHARE else round(payback_days / DPM))

computed = dict(equip_total=equip_total, monthly_ing=monthly_ing, weekly_ing=weekly_ing,
                invest_total=invest_total, seed_total=seed_total, ca_day=ca_day,
                ca_week=ca_week, ca_month=ca_month, profit_week=profit_week,
                profit_month=profit_month, payback_days=payback_days,
                payback_weeks=payback_days / DPW, switch_week=switch_week,
                switch_month=switch_month, basis=basis)
json.dump(computed, open(OUT.rsplit(".", 1)[0] + ".computed.json", "w"), indent=2)

# ------------------------------------------------------------------ styles
F = "Arial"
THEME = cfg.get("theme_color", "1F4E5F")
def font(**k): return Font(name=F, **k)
TITLE_FONT = font(size=16, bold=True, color="FFFFFF"); H1_FONT = font(size=13, bold=True, color="FFFFFF")
H2_FONT = font(size=11, bold=True, color="FFFFFF"); LABEL = font(size=10, bold=True)
NORMAL = font(size=10); INPUT = font(size=10, color="0000FF"); FORMULA = font(size=10)
LINK = font(size=10, color="008000"); TOTAL = font(size=10, bold=True)
NOTE = font(size=9, italic=True, color="808080")
def fill(c): return PatternFill("solid", fgColor=c)
TITLE_FILL, H1_FILL, H2_FILL = fill(THEME), fill(THEME), fill("BBBBBB")
TOTAL_FILL, INPUT_FILL = fill("E7E6E6"), fill("FFFFCC")
SALES_FILL, PH1_FILL, PH2_FILL = fill("F4CCCC"), fill("D9EAD3"), fill("CFE2F3")
side = Side(style="thin", color="B7B7B7"); BORDER = Border(left=side, right=side, top=side, bottom=side)
CUR = '#,##0"%s"' % cfg.get("currency_suffix", " f"); PCT = "0.0%"
CENTER = Alignment(horizontal="center", vertical="center")

def title(ws, rng, text, h=28):
    ws.merge_cells(rng); c = ws[rng.split(":")[0]]; c.value = text; c.font = TITLE_FONT
    c.fill = TITLE_FILL; c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[c.row].height = h
def h1(ws, rng, text):
    ws.merge_cells(rng); c = ws[rng.split(":")[0]]; c.value = text; c.font = H1_FONT
    c.fill = H1_FILL; c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
def h2(ws, row, headers, col0=1):
    for i, t in enumerate(headers):
        c = ws.cell(row=row, column=col0 + i, value=t); c.font = H2_FONT; c.fill = H2_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True); c.border = BORDER
    ws.row_dimensions[row].height = 30
def cell(ws, r, c, v, f=NORMAL, fmt=None, fl=None, al=None):
    # un texte ne doit jamais commencer par "=" (sinon interprété comme formule -> #VALUE!)
    x = ws.cell(row=r, column=c, value=v); x.font = f; x.border = BORDER
    if fmt: x.number_format = fmt
    if fl: x.fill = fl
    x.alignment = al or Alignment(horizontal="left", vertical="center"); return x
def num(ws, r, c, v, f=FORMULA, fmt=CUR, fl=None): return cell(ws, r, c, v, f, fmt, fl, CENTER)
def note(ws, ref, text, merge=None):
    ws[ref] = text; ws[ref].font = NOTE; ws[ref].alignment = Alignment(wrap_text=True, vertical="top")
    if merge: ws.merge_cells(merge)
def widths(ws, ws_widths):
    for k, w in ws_widths.items(): ws.column_dimensions[k].width = w

# ------------------------------------------------------------------ plan des lignes (fixe, calculé d'avance)
N, M, E = len(P), len(ING), len(EQ)
ACH_TOT = 5 + M
INV_MAT = 4 + E; INV_SEED = INV_MAT + 6; INV_TOT = INV_SEED + 6
VEN_TOT = 5 + N
# Paramètres (lignes fixes)
R_DPW, R_WPM, R_DPM = 5, 6, 7
R_P1P, R_P1O, R_P2P, R_P2O, R_CTRL = 11, 12, 13, 14, 15
R_PAYB, R_SW, R_SM = 19, 20, 21
R_CAPSH, R_CAPP, R_CAPO = 26, 27, 28
R_WREF, R_MREF = 31, 32
R_PROD0 = 36
def PR(r, col="B"): return "Paramètres!$%s$%d" % (col, r)
SEM, MOIS = PR(R_DPW), PR(R_WPM)

wb = Workbook(); wb.remove(wb.active)
partner, operator = cfg["partner"], cfg["operator"]

# ================================================================== Paramètres
ws = wb.create_sheet("Paramètres"); ws.sheet_view.showGridLines = False
widths(ws, {"A": 46, "B": 16, "C": 14, "D": 60}); title(ws, "A1:D1", "PARAMÈTRES")
h1(ws, "A3:D3", "Exploitation"); h2(ws, 4, ["Paramètre", "Valeur", "Unité", "Commentaire"])
cell(ws, R_DPW, 1, "Jours ouvrés / semaine"); num(ws, R_DPW, 2, DPW, INPUT, None, INPUT_FILL); cell(ws, R_DPW, 3, "jours")
cell(ws, R_WPM, 1, "Semaines / mois"); num(ws, R_WPM, 2, WPM, INPUT, None, INPUT_FILL); cell(ws, R_WPM, 3, "semaines")
cell(ws, R_WPM, 4, "Convention simplifiée: mois = semaines/mois × jours/semaine.", NOTE)
cell(ws, R_DPM, 1, "Jours ouvrés / mois (calculé)"); num(ws, R_DPM, 2, f"={SEM}*{MOIS}", FORMULA, None); cell(ws, R_DPM, 3, "jours")

h1(ws, "A9:D9", "Répartition des bénéfices par phase (paramétrable)"); h2(ws, 10, ["Paramètre", "Valeur", "Unité", "Commentaire"])
for r, lab, v, cm in [(R_P1P, f"% {partner} (Phase 1 - avant ROI)", sp["phase1"]["partner"], "Avant le retour sur investissement"),
                      (R_P1O, f"% {operator} (Phase 1 - avant ROI)", sp["phase1"]["operator"], ""),
                      (R_P2P, f"% {partner} (Phase 2 - après ROI)", sp["phase2"]["partner"], ""),
                      (R_P2O, f"% {operator} (Phase 2 - après ROI)", sp["phase2"]["operator"], "")]:
    cell(ws, r, 1, lab); num(ws, r, 2, v, INPUT, PCT, INPUT_FILL); cell(ws, r, 3, "%"); cell(ws, r, 4, cm, NOTE)
cell(ws, R_CTRL, 1, "Contrôle: somme Phase 1 | Phase 2", LABEL)
num(ws, R_CTRL, 2, f"=B{R_P1P}+B{R_P1O}", FORMULA, PCT); num(ws, R_CTRL, 3, f"=B{R_P2P}+B{R_P2O}", FORMULA, PCT)
cell(ws, R_CTRL, 4, "Chaque phase doit sommer à 100%", NOTE)

h1(ws, "A17:D17", "Bascule de phase (retour sur investissement)")
cell(ws, 18, 1, "Base du ROI"); cell(ws, 18, 2, ("CA cumulé" if basis == "revenue" else "Bénéfice cumulé") + (" × part Phase 1 du partenaire" if ON_SHARE else ""), NORMAL, None, None, CENTER)
cell(ws, 18, 4, "CA: l'investissement est comparé aux encaissements; Bénéfice: après déduction des charges (plus prudent).", NOTE)
cell(ws, R_PAYB, 1, "Jours ouvrés pour récupérer l'investissement")
per_day_f = (f"'Ventes'!$D${VEN_TOT}" if basis == "revenue"
             else f"('Ventes'!$D${VEN_TOT}-'Achats-Charges'!$C${ACH_TOT}/{PR(R_DPM)})")
if ON_SHARE: per_day_f = f"({per_day_f}*$B${R_P1P})"
num(ws, R_PAYB, 2, f"=Investissement!$B${INV_TOT}/{per_day_f}", FORMULA, "0.0"); cell(ws, R_PAYB, 3, "jours")
cell(ws, R_SW, 1, "Semaine de bascule (dernière semaine en Phase 1)"); num(ws, R_SW, 2, switch_week, INPUT, None, INPUT_FILL)
cell(ws, R_SW, 3, "semaine"); cell(ws, R_SW, 4, "Par défaut: jours de ROI ÷ jours/semaine, arrondi au-dessus.", NOTE)
cell(ws, R_SM, 1, "Mois de bascule (dernier mois en Phase 1)"); num(ws, R_SM, 2, switch_month, INPUT, None, INPUT_FILL)
cell(ws, R_SM, 3, "mois"); cell(ws, R_SM, 4, "Par défaut: jours de ROI ÷ jours/mois, arrondi au plus proche (min. 1).", NOTE)

h1(ws, "A24:D24", "Financement et dates")
cell(ws, 25, 1, "Démarrage / achats"); cell(ws, 25, 2, cfg["start_date"], INPUT, None, INPUT_FILL, CENTER)
cell(ws, 25, 3, cfg["purchase_date"], INPUT, None, INPUT_FILL, CENTER)
cell(ws, R_CAPSH, 1, f"% du capital apporté par {partner}"); num(ws, R_CAPSH, 2, CAP, INPUT, PCT, INPUT_FILL)
cell(ws, R_CAPP, 1, f"→ Apport {partner}"); num(ws, R_CAPP, 2, f"=Investissement!$B${INV_TOT}*B{R_CAPSH}")
cell(ws, R_CAPO, 1, f"→ Apport {operator}"); num(ws, R_CAPO, 2, f"=Investissement!$B${INV_TOT}*(1-B{R_CAPSH})")

h1(ws, "A30:D30", "Aperçu - Répartition Bénéfices")
cell(ws, R_WREF, 1, "Semaine de référence (aperçu hebdo)"); num(ws, R_WREF, 2, 1, INPUT, None, INPUT_FILL)
cell(ws, R_MREF, 1, "Mois de référence (aperçu mensuel)"); num(ws, R_MREF, 2, 1, INPUT, None, INPUT_FILL)
cell(ws, R_MREF, 4, "≤ bascule: Phase 1; > bascule: Phase 2.", NOTE)

h1(ws, "A34:D34", "Produits (prix et volumes paramétrables)"); h2(ws, 35, ["Produit", "Prix unitaire", "Volume / jour", "Commentaire"])
for i, p in enumerate(P):
    r = R_PROD0 + i
    cell(ws, r, 1, p["name"]); num(ws, r, 2, p["price"], INPUT, CUR, INPUT_FILL); num(ws, r, 3, p["volume_per_day"], INPUT, None, INPUT_FILL)
    cell(ws, r, 4, p.get("note", ""), NOTE)

# ================================================================== Achats-Charges
ws = wb.create_sheet("Achats-Charges"); ws.sheet_view.showGridLines = False
widths(ws, {"A": 30, "B": 18, "C": 16, "D": 16, "E": 46}); title(ws, "A1:E1", LBL["charges_title"])
note(ws, "A2", LBL["charges_note"], "A2:E2")
h2(ws, 4, ["Poste", "Base d'achat", "Coût / mois", "Coût / semaine", "Détail"])
for i, it in enumerate(ING):
    r = 5 + i
    cell(ws, r, 1, it["name"]); cell(ws, r, 2, it.get("base", ""))
    if "pct_of_revenue" in it:
        num(ws, r, 3, f"={it['pct_of_revenue']}*'Ventes'!$F${VEN_TOT}")
    elif "per_unit" in it:
        num(ws, r, 3, f"={it['per_unit']}*'Ventes'!$C${VEN_TOT}*{PR(R_DPM)}")
    else:
        num(ws, r, 3, it["monthly_cost"], INPUT, CUR, INPUT_FILL)
    num(ws, r, 4, f"=C{r}/{MOIS}"); cell(ws, r, 5, it.get("note", ""), NOTE)
cell(ws, ACH_TOT, 1, "TOTAL CHARGES", TOTAL, None, TOTAL_FILL); cell(ws, ACH_TOT, 2, "", fl=TOTAL_FILL)
num(ws, ACH_TOT, 3, f"=SUM(C5:C{ACH_TOT-1})", TOTAL, CUR, TOTAL_FILL); num(ws, ACH_TOT, 4, f"=SUM(D5:D{ACH_TOT-1})", TOTAL, CUR, TOTAL_FILL)
cell(ws, ACH_TOT, 5, "", fl=TOTAL_FILL)

# ================================================================== Investissement
ws = wb.create_sheet("Investissement"); ws.sheet_view.showGridLines = False
widths(ws, {"A": 38, "B": 14, "C": 16, "D": 16, "E": 40}); title(ws, "A1:E1", "INVESTISSEMENT")
h2(ws, 3, [LBL["equipment"], "Quantité", "Prix unitaire", "Total", "Détail"])
for i, e in enumerate(EQ):
    r = 4 + i
    cell(ws, r, 1, e["name"]); num(ws, r, 2, e["qty"], INPUT, None, INPUT_FILL); num(ws, r, 3, e["unit_price"], INPUT, CUR, INPUT_FILL)
    num(ws, r, 4, f"=B{r}*C{r}"); cell(ws, r, 5, e.get("note", ""), NOTE)
cell(ws, INV_MAT, 1, "TOTAL " + LBL["equipment"].upper(), TOTAL, None, TOTAL_FILL)
for c in (2, 3, 5): cell(ws, INV_MAT, c, "", fl=TOTAL_FILL)
num(ws, INV_MAT, 4, f"=SUM(D4:D{INV_MAT-1})", TOTAL, CUR, TOTAL_FILL)
for base, ttl, lab2, ref in [(INV_MAT + 2, "Investissement d'amorçage (Seed investment)", "Charges - 1ère semaine", "D"),
                             (INV_SEED + 2, "Investissement total", "Charges - 1er mois", "C")]:
    h1(ws, f"A{base}:E{base}", ttl); h2(ws, base + 1, ["Poste", "Montant"])
    cell(ws, base + 2, 1, "Investissement " + LBL["equipment"].lower()); num(ws, base + 2, 2, f"=D{INV_MAT}", LINK)
    cell(ws, base + 3, 1, lab2); num(ws, base + 3, 2, f"='Achats-Charges'!{ref}{ACH_TOT}", LINK)
    cell(ws, base + 4, 1, "TOTAL - " + ttl.split(" (")[0], TOTAL, None, TOTAL_FILL)
    num(ws, base + 4, 2, f"=SUM(B{base+2}:B{base+3})", TOTAL, CUR, TOTAL_FILL)

# ================================================================== Ventes
ws = wb.create_sheet("Ventes"); ws.sheet_view.showGridLines = False
widths(ws, {"A": 22, "B": 14, "C": 16, "D": 16, "E": 16, "F": 16}); title(ws, "A1:F1", "VENTES")
note(ws, "A2", "Prix et volumes modifiables dans Paramètres.", "A2:F2")
h2(ws, 4, ["Produit", "Prix", "Volume / jour", "CA / jour", "CA / semaine", "CA / mois"])
for i in range(N):
    r, pr = 5 + i, R_PROD0 + i
    cell(ws, r, 1, f"=Paramètres!$A${pr}", LINK, None, SALES_FILL); num(ws, r, 2, f"=Paramètres!$B${pr}", LINK, CUR, SALES_FILL)
    num(ws, r, 3, f"=Paramètres!$C${pr}", LINK, None, SALES_FILL); num(ws, r, 4, f"=B{r}*C{r}", FORMULA, CUR, SALES_FILL)
    num(ws, r, 5, f"=D{r}*{SEM}", FORMULA, CUR, SALES_FILL); num(ws, r, 6, f"=E{r}*{MOIS}", FORMULA, CUR, SALES_FILL)
cell(ws, VEN_TOT, 1, "TOTAL", TOTAL, None, TOTAL_FILL); cell(ws, VEN_TOT, 2, "", fl=TOTAL_FILL)
num(ws, VEN_TOT, 3, f"=SUM(C5:C{VEN_TOT-1})", TOTAL, None, TOTAL_FILL)
for c, L in ((4, "D"), (5, "E"), (6, "F")): num(ws, VEN_TOT, c, f"=SUM({L}5:{L}{VEN_TOT-1})", TOTAL, CUR, TOTAL_FILL)

# ================================================================== Compte de Résultat
ws = wb.create_sheet("Compte de Résultat"); ws.sheet_view.showGridLines = False
widths(ws, {"A": 24, "B": 34, "C": 16, "D": 16, "E": 16, "F": 40}); title(ws, "A1:F1", "COMPTE DE RÉSULTAT")
for top, lab, ca_col, ch_col in [(3, "Hebdomadaire", "E", "D"), (7, "Mensuel", "F", "C")]:
    per = "semaine" if lab == "Hebdomadaire" else "mois"
    h1(ws, f"A{top}:F{top}", lab); h2(ws, top + 1, ["Activité", "Base de calcul", f"CA / {per}", f"Coûts / {per}", f"Profit / {per}", "Détail"])
    r = top + 2
    cell(ws, r, 1, cfg["activity_name"], LABEL, None, SALES_FILL); cell(ws, r, 2, "CA: Ventes - Coûts: Achats-Charges", NOTE, None, SALES_FILL)
    num(ws, r, 3, f"='Ventes'!{ca_col}{VEN_TOT}", LINK); num(ws, r, 4, f"='Achats-Charges'!{ch_col}{ACH_TOT}", LINK)
    num(ws, r, 5, f"=C{r}-D{r}"); cell(ws, r, 6, f"Bénéfice partagé {partner} / {operator} selon la phase.", NOTE, None, SALES_FILL)
CR_W, CR_M = 5, 9
note(ws, "A11", "Ce compte de résultat ne déduit pas l'investissement initial (coût unique de démarrage, feuille Investissement).", "A11:F12")

# ================================================================== Répartition Bénéfices
ws = wb.create_sheet("Répartition Bénéfices"); ws.sheet_view.showGridLines = False
widths(ws, {"A": 24, "B": 16, "C": 20, "D": 18, "E": 52}); title(ws, "A1:E1", "RÉPARTITION DES BÉNÉFICES")
def pct(who, ref_cell, switch):
    a, b = (R_P1P, R_P2P) if who == "partner" else (R_P1O, R_P2O)
    return f"=IF({PR(ref_cell)}<={PR(switch)},{PR(a)},{PR(b)})"
for top, lab, ref_cell, switch, cr in [(3, "Aperçu hebdomadaire", R_WREF, R_SW, CR_W), (9, "Aperçu mensuel", R_MREF, R_SM, CR_M)]:
    per = "semaine" if cr == CR_W else "mois"
    h1(ws, f"A{top}:E{top}", lab); h2(ws, top + 1, ["Bénéficiaire", "% attribué", f"Base (profit/{per})", f"Montant / {per}", "Commentaire"])
    for k, (who, name, fl) in enumerate([("partner", partner, PH1_FILL), ("operator", operator, PH2_FILL)]):
        r = top + 2 + k
        cell(ws, r, 1, name, LABEL, None, fl); num(ws, r, 2, pct(who, ref_cell, switch), FORMULA, PCT, fl)
        num(ws, r, 3, f"='Compte de Résultat'!E{cr}", LINK); num(ws, r, 4, f"=B{r}*C{r}")
        cell(ws, r, 5, "Phase selon la référence dans Paramètres (≤ bascule: Phase 1)", NOTE, None, fl)
    r = top + 4
    cell(ws, r, 1, "TOTAL", TOTAL, None, TOTAL_FILL); num(ws, r, 2, f"=B{r-2}+B{r-1}", TOTAL, PCT, TOTAL_FILL)
    cell(ws, r, 3, "", fl=TOTAL_FILL); num(ws, r, 4, f"=D{r-2}+D{r-1}", TOTAL, CUR, TOTAL_FILL); cell(ws, r, 5, "Doit égaler 100% et le profit", NOTE, None, TOTAL_FILL)

# ================================================================== Exploitation (mensuelle / hebdomadaire)
def exploitation(name, n, unit, ca_col, ch_col, switch, first_invest):
    ws = wb.create_sheet(name); ws.sheet_view.showGridLines = False
    last = 1 + n; L = get_column_letter(last)
    ws.column_dimensions["A"].width = 40
    for c in range(2, last + 1): ws.column_dimensions[get_column_letter(c)].width = 13
    title(ws, f"A1:{L}1", f"TABLEAU D'EXPLOITATION {name.split()[-1].upper()} ({n} {unit.upper() if unit.endswith('s') else unit.upper() + 'S'})")
    note(ws, "A2", f"Sorties/Entrées constantes (aucune hypothèse de croissance). Investissement porté en totalité en {unit.capitalize()} 1. "
                   f"Phase 1 jusqu'{'au' if unit == 'mois' else 'à la'} {unit} de bascule (Paramètres), Phase 2 ensuite.", f"A2:{L}3")
    heads = [f"{unit.capitalize()} {i}" for i in range(1, n + 1)]; h2(ws, 5, ["Poste"] + heads)
    cell(ws, 6, 1, "Investissement", LABEL, None, SALES_FILL)
    num(ws, 6, 2, first_invest, LINK, CUR, INPUT_FILL)
    for c in range(3, last + 1): num(ws, 6, c, 0, INPUT, CUR, INPUT_FILL)
    cell(ws, 7, 1, "Sorties (charges d'exploitation)", LABEL, None, SALES_FILL)
    cell(ws, 8, 1, "Entrées (chiffre d'affaires)", LABEL, None, SALES_FILL)
    cell(ws, 9, 1, "Bénéfices (Entrées - Sorties)", TOTAL, None, TOTAL_FILL)
    cell(ws, 10, 1, f"Trésorerie nette ({unit}, après investissement)")
    for c in range(2, last + 1):
        l = get_column_letter(c)
        num(ws, 7, c, f"='Achats-Charges'!${ch_col}${ACH_TOT}", LINK); num(ws, 8, c, f"='Ventes'!${ca_col}${VEN_TOT}", LINK)
        num(ws, 9, c, f"={l}8-{l}7", TOTAL, CUR, TOTAL_FILL); num(ws, 10, c, f"={l}9-{l}6")
    h1(ws, f"A12:{L}12", "Répartition des bénéfices (hors investissement)"); h2(ws, 13, ["Bénéficiaire"] + heads)
    for k, (who, nm) in enumerate([("partner", partner), ("operator", operator)]):
        r = 14 + k; cell(ws, r, 1, nm)
        a, b = (R_P1P, R_P2P) if who == "partner" else (R_P1O, R_P2O)
        for c in range(2, last + 1):
            l = get_column_letter(c)
            num(ws, r, c, f"={l}9*IF({c-1}<={PR(switch)},{PR(a)},{PR(b)})")
    cell(ws, 16, 1, "TOTAL réparti", TOTAL, None, TOTAL_FILL)
    for c in range(2, last + 1):
        l = get_column_letter(c); num(ws, 16, c, f"=SUM({l}14:{l}15)", TOTAL, CUR, TOTAL_FILL)
exploitation("Exploitation Mensuelle", cfg.get("horizon_months", 12), "mois", "F", "C", R_SM, f"=Investissement!$B${INV_TOT}")
exploitation("Exploitation Hebdomadaire", cfg.get("horizon_weeks", 13), "semaine", "E", "D", R_SW, "='Exploitation Mensuelle'!$B$6")

# ================================================================== Résumé (en premier)
ws = wb.create_sheet("Résumé", 0); ws.sheet_view.showGridLines = False
widths(ws, {"A": 44, "B": 20, "C": 4, "D": 34, "E": 20}); title(ws, "A1:E1", f"PLAN D'AFFAIRES - {cfg['activity_name'].upper()}", 32)
note(ws, "A2", f"Partenariat avec {partner} - {cfg.get('location_text', '')}", "A2:E2")
h1(ws, "A4:E4", "1. Chiffres clés")
rows = [(f"Investissement total ({LBL['equipment'].lower()} + 1er mois)", f"=Investissement!$B${INV_TOT}", CUR, "CA mensuel prévisionnel", f"='Compte de Résultat'!C{CR_M}", CUR),
        ("CA / jour", f"='Ventes'!D{VEN_TOT}", CUR, "Coûts mensuels", f"='Compte de Résultat'!D{CR_M}", CUR),
        ("Jours ouvrés pour récupérer l'investissement", f"={PR(R_PAYB)}", '0.0', "Bénéfice mensuel prévisionnel", f"='Compte de Résultat'!E{CR_M}", CUR)]
for i, (a, fa, fma, b, fb, fmb) in enumerate(rows):
    r = 5 + i
    cell(ws, r, 1, a, LABEL); num(ws, r, 2, fa, LINK, fma); cell(ws, r, 4, b, LABEL); num(ws, r, 5, fb, LINK, fmb)
cell(ws, 8, 1, "Démarrage", LABEL); cell(ws, 8, 2, cfg["start_date"], INPUT, None, INPUT_FILL, CENTER)
cell(ws, 8, 4, "Achats", LABEL); cell(ws, 8, 5, cfg["purchase_date"], INPUT, None, INPUT_FILL, CENTER)
h1(ws, "A10:E10", "2. Répartition des bénéfices"); h2(ws, 11, ["Bénéficiaire", "Phase 1 (avant ROI)", "", "", "Phase 2 (après ROI)"])
for k, (nm, a, b) in enumerate([(partner, R_P1P, R_P2P), (operator, R_P1O, R_P2O)]):
    r = 12 + k; cell(ws, r, 1, nm, LABEL, None, PH1_FILL); num(ws, r, 2, f"={PR(a)}", LINK, PCT, PH1_FILL)
    cell(ws, r, 4, "", fl=PH2_FILL); num(ws, r, 5, f"={PR(b)}", LINK, PCT, PH2_FILL)

# ------------------------------------------------------------------ lignes/colonnes masquées (config.hidden)
for sheet, spec in cfg.get("hidden", {}).items():
    if sheet in wb.sheetnames:
        for r in spec.get("rows", []): wb[sheet].row_dimensions[r].hidden = True
        for c in spec.get("columns", []): wb[sheet].column_dimensions[c].hidden = True

wb.save(OUT)
print("OK", OUT, json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in computed.items()}, ensure_ascii=False))
