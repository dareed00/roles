#!/usr/bin/env python3
"""
RoleMiner - OpenPyXL Color Palettes, Typography, and Cell Styling Helpers
File: Scripts/Report/workbook_styles.py
"""

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# --- GREY-OUT STYLING FOR EXISTING PRODUCTION ACCESS ---
GREY_OUT_FILL = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
MUTED_FONT = Font(name="Calibri", size=10, color="7F7F7F", italic=True)

# --- SEMANTIC FONTS ---
FONT_GREEN_DARK = Font(name="Segoe UI", size=9.5, bold=True, color="166534")
FONT_OLIVE_DARK = Font(name="Segoe UI", size=9.5, bold=True, color="3F6212")
FONT_AMBER_DARK = Font(name="Segoe UI", size=9.5, bold=True, color="92400E")
FONT_ORANGE_DARK = Font(name="Segoe UI", size=9.5, bold=True, color="C2410C")
FONT_RED_DARK = Font(name="Segoe UI", size=9.5, bold=True, color="991B1B")
FONT_PURPLE_DARK = Font(name="Segoe UI", size=9.5, bold=True, color="4338CA")
FONT_GRAY_MUTED = Font(name="Segoe UI", size=9.5, color="94A3B8")

# --- WORKBOOK TYPOGRAPHY ---
FONT_TITLE = Font(name="Segoe UI", size=14, bold=True, color="0F172A")
FONT_HEADER = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
FONT_DATA = Font(name="Segoe UI", size=9.5, color="1E293B")
FONT_FORMULA = Font(name="Segoe UI", size=9.5, italic=True, color="0369A1")
FONT_CODE = Font(name="Consolas", size=9, color="0369A1")
FONT_CODE_FADED = Font(name="Consolas", size=9, color="94A3B8")
FONT_KPI_NUM = Font(name="Segoe UI", size=16, bold=True, color="0369A1")
FONT_KPI_LBL = Font(name="Segoe UI", size=9, bold=True, color="64748B")
FONT_ACTION_BLUE = Font(name="Segoe UI", size=9.5, bold=True, color="1F4E78")

# --- ROW & HEADER FILLS ---
FILL_WHITE = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
FILL_LIGHT_BLUE = PatternFill(start_color="E6F4FA", end_color="E6F4FA", fill_type="solid")
FILL_DYNAMIC_PARENT = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
FILL_DYNAMIC_SUBTIER = PatternFill(start_color="F2F4F8", end_color="F2F4F8", fill_type="solid")

FILL_HEADER_NAVY = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
FILL_HEADER_BLUE = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")
FILL_HEADER_INDIGO = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
FILL_HEADER_PURPLE = PatternFill(start_color="4338CA", end_color="4338CA", fill_type="solid")
FILL_HEADER_EMERALD = PatternFill(start_color="047857", end_color="047857", fill_type="solid")
FILL_KPI_BG = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

# --- BORDERS & ALIGNMENTS ---
THIN_BORDER_SIDE = Side(border_style="thin", color="CBD5E1")
THIN_BORDER = Border(
    left=THIN_BORDER_SIDE, right=THIN_BORDER_SIDE,
    top=THIN_BORDER_SIDE, bottom=THIN_BORDER_SIDE
)

ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
ALIGN_LEFT_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)


def style_confidence_cell(cell, score_val, is_faded=False):
    pct = score_val * 100.0 if score_val <= 1.0 else score_val
    cell.value = f"{pct:.1f}%"
    if is_faded:
        cell.font = FONT_GRAY_MUTED
    elif pct >= 100.0:
        cell.font = FONT_GREEN_DARK
    elif pct >= 95.0:
        cell.font = FONT_OLIVE_DARK
    elif pct >= 85.0:
        cell.font = FONT_AMBER_DARK
    else:
        cell.font = FONT_RED_DARK


def style_coverage_cell(cell, cov_pct, holders, total, is_faded=False):
    cell.value = f"{cov_pct:.1f}% ({holders}/{total})"
    if is_faded:
        cell.font = FONT_GRAY_MUTED
    elif cov_pct >= 100.0:
        cell.font = FONT_GREEN_DARK
    elif cov_pct >= 95.0:
        cell.font = FONT_OLIVE_DARK
    elif cov_pct >= 80.0:
        cell.font = FONT_AMBER_DARK
    else:
        cell.font = FONT_RED_DARK


def style_missing_cell(cell, count, is_faded=False):
    cell.value = count
    if is_faded or count == 0:
        cell.font = FONT_GRAY_MUTED
    elif count <= 5:
        cell.font = FONT_AMBER_DARK
    else:
        cell.font = FONT_ORANGE_DARK


def style_extra_cell(cell, count, is_faded=False):
    cell.value = count
    if is_faded:
        cell.font = FONT_GRAY_MUTED
    elif count == 0:
        cell.font = FONT_GREEN_DARK
    elif count <= 5:
        cell.font = FONT_AMBER_DARK
    else:
        cell.font = FONT_RED_DARK


def style_decision_cell(cell, value, is_faded=False):
    cell.value = value
    val_upper = str(value).upper()
    if is_faded:
        cell.font = FONT_GRAY_MUTED
    elif val_upper in ("ACCEPT", "APPROVED", "YES"):
        cell.font = FONT_GREEN_DARK
    elif val_upper in ("SPLIT", "SEPARATE", "MAKE_DYNAMIC"):
        cell.font = FONT_PURPLE_DARK
    elif val_upper in ("PENDING_REVIEW", "REVIEW", "PENDING_CERTIFICATION", "CERTIFY"):
        cell.font = FONT_AMBER_DARK
    elif val_upper in ("DENY", "REJECTED", "NO", "SKIP", "ALREADY_IN_PROD", "IGNORE", "IGNORED"):
        cell.font = FONT_RED_DARK


def auto_fit_workbook_columns(wb):
    """Auto-fits column widths across all sheets in the workbook."""
    for ws in wb.worksheets:
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                if cell.row < 4 and ws.title != "_Lookups_Reference":
                    continue
                val_str = str(cell.value or "")
                if "\n" in val_str:
                    lines = val_str.split("\n")
                    max_len = max(max_len, max(len(l) for l in lines))
                elif not val_str.startswith("="):
                    max_len = max(max_len, len(val_str))
                else:
                    max_len = max(max_len, 20)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3.5, 12), 65)
