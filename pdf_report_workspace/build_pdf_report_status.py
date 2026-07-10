# Build the operator-grouped PDF-report status spreadsheet AND rebuild the two deck
# table slides in the same structure (7 columns incl. Trial type + Diesel comparator).
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(r"D:\OneDrive - University of Cambridge\Research\JOLT_Report")
XLSX = ROOT / "pdf_report_workspace" / "pdf_report_status.xlsx"
PPTX = ROOT / "monthly_presentation" / "20260715" / "20260715Data Subcommittee Report v1.0.pptx"

# ── data: one row per trial, grouped by operator (alphabetical); within a group EVs
#    first then diesel comparators; same-vehicle stints kept adjacent for merging ──
# (operator, vehicle, reg, trial_type, diesel, period, pdf_ok)
GROUPS = [
    ("DP World", [
        ("Scania P-series BEV", "EX74JXW", "Round-robin", "No", "2025-07-07 – 2025-08-22", True),
        ("DAF XF 450", "WU70GLV", "Round-robin", "Yes", "2025-06-26 – 2025-08-08", False),
        ("DAF XF 450", "WU70GLV", "Round-robin", "Yes", "2025-11-07 – 2025-12-11", False),
    ]),
    ("HTL", [
        ("Volvo FH Electric", "CMZ6260", "Round-robin", "No", "2026-04-27 – 2026-07-01", True),
        ("Mercedes-Benz eActros 600", "YN75NMA", "Round-robin", "No", "2026-04-17 – 2026-06-26", True),
    ]),
    ("JLP", [
        ("Volvo FM Electric", "KY24LHT", "BYO", "No", "2024-06-21 – 2025-03-20", True),
        ("Scania P-series BEV", "EX74JXY", "BYO", "No", "2025-04-11 – 2026-05-03", True),
        ("DAF XD Electric", "LN25NKE", "Round-robin", "No", "2025-09-01 – 2025-12-29", True),
        ("Volvo FH Electric", "CMZ6260", "Round-robin", "No", "2025-10-30 – 2025-12-23", True),
    ]),
    ("Knowles", [
        ("Volvo FM Electric", "AV24LXJ", "BYO", "No", "2024-06-11 – 2026-07-03", True),
        ("Volvo FM Electric", "AV24LXK", "BYO", "No", "2024-06-11 – 2026-07-03", True),
        ("Volvo FM Electric", "AV24LXL", "BYO", "No", "2024-06-11 – 2026-07-03", True),
    ]),
    ("Nestlé", [
        ("Volvo FM Electric", "EV73SAL", "BYO", "No", "2024-06-12 – 2026-07-05", True),
        ("Volvo FM Electric", "YK73WFN", "BYO", "No", "2024-06-12 – 2026-07-03", True),
    ]),
    ("Port Express (Daimler)", [
        ("Mercedes-Benz eActros 600", "YN75NMA", "Round-robin", "No", "2026-01-29 – 2026-04-08", True),
    ]),
    ("SJG", [
        ("Volvo FH Electric", "CMZ6260", "Round-robin", "No", "2026-02-06 – 2026-04-07", True),
    ]),
    ("Welch Transport", [
        ("Renault E-Tech D Wide", "T88RNW", "BYO", "No", "2024-06-11 – 2026-07-03", True),
        ("Renault Trucks D Wide Z.E.", "N88GNW", "BYO", "No", "2024-10-11 – 2026-07-03", True),
        ("Renault E-Tech T", "TA70WTL", "BYO", "No", "2025-05-03 – 2026-07-03", True),
        ("DAF XD Electric", "LN25NKE", "Round-robin", "No", "2026-01-14 – 2026-04-07", True),
        ("Scania P-series BEV", "EX74JXW", "Round-robin", "No", "2026-02-26 – 2026-04-29", True),
    ]),
    ("WJF", [
        ("Scania P-series BEV", "EX74JXW", "Round-robin", "No", "2025-10-11 – 2025-11-18", True),
        ("Mercedes-Benz eActros 600", "YN25RSY", "Round-robin", "No", "2025-10-21 – 2025-11-18", True),
        ("Scania P410", "YT21EFD", "BYO", "Yes", "2025-08-30 – 2026-07-04", False),
        ("DAF XF 450", "WU70GLV", "Round-robin", "Yes", "2025-09-01 – 2025-11-06", False),
    ]),
    ("WS", [
        ("DAF XD Electric", "LN25NKE", "Round-robin", "No", "2026-04-16 – 2026-07-03", True),
    ]),
]
HEADERS = ["Operator", "Vehicle", "Reg", "Trial type", "Diesel comparator", "Period", "PDF report"]

NAVY = RGBColor(0x1F, 0x49, 0x7D)
ACCENTS7 = [RGBColor(0x4F, 0x81, 0xBD), RGBColor(0xC0, 0x50, 0x4D), RGBColor(0x9B, 0xBB, 0x59),
            RGBColor(0x80, 0x64, 0xA2), RGBColor(0x4B, 0xAC, 0xC6), RGBColor(0xF7, 0x96, 0x46), NAVY]
GREEN_TXT = RGBColor(0x4F, 0x62, 0x28)
RED_TXT = RGBColor(0x94, 0x37, 0x34)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BLACK = RGBColor(0x26, 0x26, 0x26)


def tint(c, f):
    return RGBColor(*(int(v + (255 - v) * f) for v in (c[0], c[1], c[2])))


def hexs(c):
    return f"{c[0]:02X}{c[1]:02X}{c[2]:02X}"


def vehicle_blocks(rows):
    """[(start, end)] of consecutive same-reg rows (0-based, inclusive)."""
    blocks, s = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i][1] != rows[s][1]:
            blocks.append((s, i - 1))
            s = i
    return blocks


# ───────────────────────── xlsx ─────────────────────────
wb = Workbook()
ws = wb.active
ws.title = "PDF report status"
widths = [24, 27, 10, 13, 17, 24, 11]
for j, w in enumerate(widths, start=1):
    ws.column_dimensions[chr(64 + j)].width = w
thin = Side(style="thin", color="BFBFBF")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
for j, h in enumerate(HEADERS, start=1):
    c = ws.cell(row=1, column=j, value=h)
    c.font = Font(name="Arial", bold=True, color="FFFFFF", size=11)
    c.fill = PatternFill("solid", fgColor=hexs(ACCENTS7[j - 1]))
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    c.border = border
ws.freeze_panes = "A2"
r = 2
for gi, (op, rows) in enumerate(GROUPS):
    g0 = r
    for i, (veh, reg, ttype, diesel, period, ok) in enumerate(rows):
        light = 0.80 if (r % 2 == 0) else 0.90
        vals = [op, veh, reg, ttype, diesel, period, "✓" if ok else "✗"]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=j, value=v)
            c.font = Font(name="Arial", size=11, bold=(j == 3),
                          color=("4F6228" if ok else "943734") if j == 7 else "262626")
            c.fill = PatternFill("solid", fgColor=hexs(tint(ACCENTS7[j - 1], light)))
            c.alignment = Alignment(horizontal="center" if j in (3, 4, 5, 7) else "left",
                                    vertical="center")
            c.border = border
        r += 1
    if len(rows) > 1:
        ws.merge_cells(start_row=g0, start_column=1, end_row=r - 1, end_column=1)
        ws.cell(row=g0, column=1).alignment = Alignment(horizontal="left", vertical="center")
    for s, e in vehicle_blocks(rows):
        if e > s:
            for col in (2, 3, 4, 5, 7):
                ws.merge_cells(start_row=g0 + s, start_column=col, end_row=g0 + e, end_column=col)
ws.cell(row=r + 1, column=1, value="Generated from excel_report_database 2.2.8 "
        "(briefing batch of 2026-07-10). One row per trial (vehicle-operator stint); "
        "periods = briefing operating period (diesel comparators: observed data span). "
        "Canonical flat table: pdf_report_status.md.").font = Font(name="Arial", size=9, italic=True)
wb.save(XLSX)
print("xlsx saved:", XLSX)

# ───────────────────────── pptx ─────────────────────────
SLIDE_GROUPS = [GROUPS[:5], GROUPS[5:]]
TITLES = ["Partner PDF Reports — Coverage by Operator (1/2)",
          "Partner PDF Reports — Coverage by Operator (2/2)"]
COL_W = [1.55, 2.70, 1.40, 1.60, 1.55, 2.80, 1.10]  # sums to 12.70
FONT, SZ = "Arial", 18

prs = Presentation(PPTX)


def set_cell(cell, text, bold, colour, fill, center=False, wrap=False):
    cell.fill.solid()
    cell.fill.fore_color.rgb = fill
    cell.margin_left, cell.margin_right = Inches(0.06), Inches(0.04)
    cell.margin_top = cell.margin_bottom = Inches(0.01)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf = cell.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = text
    f = run.font
    f.name, f.size, f.bold = FONT, Pt(SZ), bold
    f.color.rgb = colour
    if center:
        p.alignment = PP_ALIGN.CENTER


for si, (slide, groups, title) in enumerate(zip([prs.slides[1], prs.slides[2]], SLIDE_GROUPS, TITLES)):
    for sh in list(slide.shapes):
        if sh.has_table:
            sh._element.getparent().remove(sh._element)
    slide.shapes.title.text = title
    trun = slide.shapes.title.text_frame.paragraphs[0].runs[0]
    trun.font.color.rgb = NAVY
    trun.font.name = FONT

    rows = [(op, row) for op, oprows in groups for row in oprows]
    n_rows = len(rows) + 1
    left = Inches((13.333 - sum(COL_W)) / 2)
    need_tall = {i for i, (op, _) in enumerate(rows, start=1) if len(op) > 16}
    height = 0.62 + 0.34 * len(rows) + 0.28 * len(need_tall)
    tbl = slide.shapes.add_table(n_rows, 7, left, Inches(1.10), Inches(sum(COL_W)), Inches(height)).table
    tbl.first_row = False
    tbl.horz_banding = False
    for j, w in enumerate(COL_W):
        tbl.columns[j].width = Inches(w)
    tbl.rows[0].height = Inches(0.62)
    for i in range(1, n_rows):
        tbl.rows[i].height = Inches(0.62 if i in need_tall else 0.34)
    for j, h in enumerate(HEADERS):
        set_cell(tbl.cell(0, j), h, True, WHITE, ACCENTS7[j], center=True, wrap=True)

    # group/vehicle merge maps
    op_spans, veh_spans, r0 = [], [], 1
    for op, oprows in groups:
        if len(oprows) > 1:
            op_spans.append((r0, r0 + len(oprows) - 1))
        for s, e in vehicle_blocks(oprows):
            if e > s:
                veh_spans.append((r0 + s, r0 + e))
        r0 += len(oprows)
    merged = set()
    for lo, hi in op_spans:
        merged |= {(i, 0) for i in range(lo + 1, hi + 1)}
    for lo, hi in veh_spans:
        for col in (1, 2, 3, 4, 6):
            merged |= {(i, col) for i in range(lo + 1, hi + 1)}
    span_fill = {}
    for lo, hi in op_spans:
        for i in range(lo, hi + 1):
            span_fill[(i, 0)] = tint(ACCENTS7[0], 0.85)
    for lo, hi in veh_spans:
        for col in (1, 2, 3, 4, 6):
            for i in range(lo, hi + 1):
                span_fill[(i, col)] = tint(ACCENTS7[col], 0.85)

    for i, (op, (veh, reg, ttype, diesel, period, ok)) in enumerate(rows, start=1):
        light = 0.80 if i % 2 == 0 else 0.90
        # slide-only compaction so every cell stays single-line at 18 pt
        veh_s = veh.replace("Mercedes-Benz", "Mercedes").replace("Renault Trucks", "Renault")
        period_s = period.replace(" – ", "–")
        vals = [op, veh_s, reg, ttype, diesel, period_s, "✓" if ok else "✗"]
        for j, val in enumerate(vals):
            fill = span_fill.get((i, j), tint(ACCENTS7[j], light))
            colour, bold = BLACK, j == 2
            if j == 6:
                colour, bold = (GREEN_TXT if ok else RED_TXT), True
            set_cell(tbl.cell(i, j), "" if (i, j) in merged else val, bold, colour, fill,
                     center=(j in (2, 3, 4, 6)), wrap=(j == 0))
    for lo, hi in op_spans:
        tbl.cell(lo, 0).merge(tbl.cell(hi, 0))
    for lo, hi in veh_spans:
        for col in (1, 2, 3, 4, 6):
            tbl.cell(lo, col).merge(tbl.cell(hi, col))

prs.save(PPTX)
print("pptx saved:", PPTX)
