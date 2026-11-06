#!/usr/bin/env python3
"""
bundleBuilder - Exact Attribute, Union & Access Profile PDF Generator
Presentation layer importing from the ComputeSimilarity folder.
"""

import os
import sys
from datetime import datetime
import mysql.connector
from mysql.connector import Error

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfgen import canvas

# ==============================================================================
# 1. DYNAMIC SYSTEM PATH RESOLUTION
# ==============================================================================
# Locate the absolute root path ('Scripts/') relative to this file's folder:
# __file__ is ".../RoleMiner/Scripts/GenerateRoles/role_generator_logic.py"
# dirname(__file__) is ".../RoleMiner/Scripts/GenerateRoles"
# dirname(dirname(__file__)) is ".../RoleMiner/Scripts"
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Append 'Scripts/' directory to Python's search path if not already there
if root_dir not in sys.path:
    sys.path.append(root_dir)

# ==============================================================================
# 2. CANONICAL IMPORTS FROM UTILS/CONFIG.PY
# ==============================================================================
# Importing db connection utilities from the specific Utils/config.py module
from Utils.config import get_db_connection, close_db_connection

# ==============================================================================
# 1. CROSS-FOLDER IMPORT ROUTING
# ==============================================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
compute_similarity_dir = os.path.join(parent_dir, "ComputeSimilarity")
sys.path.insert(0, compute_similarity_dir)

try:
    from find_exact_attribute_combinations import load_identity_sets, find_exact_correlations
except ImportError as e:
    print(f"❌ ERROR: Could not import the mining engine from {compute_similarity_dir}")
    print(f"Details: {e}")
    sys.exit(1)

OUTPUT_PDF = "Exact_Attribute_Unions_And_Access_Profiles_Report.pdf"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}

# ==============================================================================
# 2. RUNNING CANVAS
# ==============================================================================
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()
    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        if self._pageNumber > 1:
            self.drawString(54, 750, "bundleBuilder | 100% Exact Attribute Matches & Access Profiles")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)
        self.drawRightString(558, 36, f"Page {self._pageNumber} of {page_count}")
        self.drawString(54, 36, f"Evaluation Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Confidential")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 48, 558, 48)
        self.restoreState()


# ==============================================================================
# 3. SOURCE APP LOOKUP & PDF GENERATION ENGINE
# ==============================================================================
def get_entitlement_sources():
    """
    Bulletproof fetcher for mapping entitlement_name -> source_name.
    Strips whitespace and checks multiple tables.
    """
    mapping = {}
    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor(dictionary=True)
        
        try:
            cursor.execute("SELECT entitlement_name, MAX(entitlement_source) as source_name FROM Entitlement_to_Attribute_Correlations WHERE entitlement_source IS NOT NULL AND TRIM(entitlement_source) != '' GROUP BY entitlement_name")
            for row in cursor.fetchall():
                if row["entitlement_name"]: mapping[str(row["entitlement_name"]).strip()] = str(row["source_name"]).strip()
        except Error: pass
            
        try:
            cursor.execute("SELECT entitlement_name, MAX(entitlement_source) as source_name FROM Potential_Role_Entitlements WHERE entitlement_source IS NOT NULL AND TRIM(entitlement_source) != '' GROUP BY entitlement_name")
            for row in cursor.fetchall():
                key = str(row["entitlement_name"]).strip()
                if key not in mapping and row["source_name"]: mapping[key] = str(row["source_name"]).strip()
        except Error: pass
            
        try:
            cursor.execute("SELECT entitlement_name, MAX(source_name) as source_name FROM entitlements WHERE source_name IS NOT NULL AND TRIM(source_name) != '' GROUP BY entitlement_name")
            for row in cursor.fetchall():
                key = str(row["entitlement_name"]).strip()
                if key not in mapping and row["source_name"]: mapping[key] = str(row["source_name"]).strip()
        except Error: pass

        cursor.close()
        db_connection.close()
        return mapping
    except Error as e:
        print(f"❌ Database error fetching sources: {e}")
        return {}


def safe_trunc(val, limit=300):
    val_str = str(val)
    return val_str if len(val_str) <= limit else val_str[:limit] + "..."


def generate_pdf(total_ids, total_ents, results_dict, ent_source_map, filename=OUTPUT_PDF):
    # Unpack the dictionary from the new engine format
    singles = results_dict.get("SINGLE", [])
    two_and = results_dict.get("2_WAY_AND", [])
    three_and = results_dict.get("3_WAY_AND", [])
    two_or = results_dict.get("2_WAY_OR", [])
    three_or = results_dict.get("3_WAY_OR", [])
    four_or = results_dict.get("4_WAY_OR", [])
    suggested_aps = results_dict.get("SUGGESTED_AP", [])

    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()

    s_title = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#0f172a"))
    s_sub = ParagraphStyle("S", fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor("#64748b"), spaceAfter=8)
    s_h1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#1e293b"), spaceBefore=16, spaceAfter=6)
    s_cell = ParagraphStyle("C", fontName="Helvetica", fontSize=7.2, leading=9.2, textColor=colors.HexColor("#1e293b"))
    s_th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7.2, leading=9.2, textColor=colors.white)

    story = []

    story.append(Paragraph("100% Exact Matches: Attributes & Access Profiles", s_title))
    story.append(Paragraph(f"Database: <b>bundleBuilder</b> | Extracted: {datetime.now().strftime('%B %d, %Y')} | Scope: <b>Jaccard = 1.0</b>", s_sub))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=10))

    kpis = [
        [
            Paragraph("<b>Identities</b>", s_cell),
            Paragraph("<b>Ents</b>", s_cell),
            Paragraph("<b>Singles</b>", s_cell),
            Paragraph("<b>AND Intersections</b>", s_cell),
            Paragraph("<b>OR Unions</b>", s_cell),
            Paragraph("<b>Suggested APs</b>", s_cell),
        ],
        [
            Paragraph(f"<b>{total_ids:,}</b>", s_cell),
            Paragraph(f"<b>{total_ents:,}</b>", s_cell),
            Paragraph(f"<font color='#16a34a'><b>{len(singles):,}</b></font>", s_cell),
            Paragraph(f"<font color='#9333ea'><b>{len(two_and) + len(three_and):,}</b></font>", s_cell),
            Paragraph(f"<font color='#0284c7'><b>{len(two_or) + len(three_or) + len(four_or):,}</b></font>", s_cell),
            Paragraph(f"<font color='#dc2626'><b>{len(suggested_aps):,}</b></font>", s_cell),
        ],
    ]
    t_kpi = Table(kpis, colWidths=[80, 80, 80, 90, 80, 80])
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_kpi)

    def build_rules_table(data_list, title, bg_color):
        story.append(Spacer(1, 10))
        story.append(Paragraph(title, s_h1))
        if not data_list:
            story.append(Paragraph("<i>None found.</i>", s_cell))
            return

        if "components" not in data_list[0]:
            rows = [[Paragraph("<b>Entitlement (Source)</b>", s_th), Paragraph("<b>Pop</b>", s_th), Paragraph("<b>Exact 100% Rule</b>", s_th)]]
            for m in data_list:
                ent_name = safe_trunc(m['entitlement_name'])
                source_name = ent_source_map.get(m['entitlement_name'], 'Unknown')
                disp_str = f"{ent_name} <font color='#64748b'>({source_name})</font>"
                
                rows.append([Paragraph(f"<b>{disp_str}</b>", s_cell), Paragraph(f"{m['population']}", s_cell), Paragraph(f"<code>{safe_trunc(m['rule'])}</code>", s_cell)])
            t = Table(rows, colWidths=[200, 60, 244], repeatRows=1)
        else:
            rows = [[Paragraph("<b>Entitlement (Source)</b>", s_th), Paragraph("<b>Type</b>", s_th), Paragraph("<b>Pop</b>", s_th), Paragraph("<b>Exact 100% Rule</b>", s_th), Paragraph("<b>Population Components</b>", s_th)]]
            for m in data_list:
                ent_name = safe_trunc(m['entitlement_name'])
                source_name = ent_source_map.get(m['entitlement_name'], 'Unknown')
                disp_str = f"{ent_name} <font color='#64748b'>({source_name})</font>"
                
                components_str = "<br/>".join([safe_trunc(c, 100) for c in m.get("components", [])])
                rows.append([
                    Paragraph(f"<b>{disp_str}</b>", s_cell), 
                    Paragraph(m.get("match_type", "").replace(" (OR)", "").replace(" (AND)", ""), s_cell), 
                    Paragraph(f"{m['population']}", s_cell), 
                    Paragraph(f"<code>{safe_trunc(m['rule'])}</code>", s_cell), 
                    Paragraph(components_str, s_cell)
                ])
            t = Table(rows, colWidths=[140, 80, 40, 120, 124], repeatRows=1)

        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor(bg_color)), ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")])]))
        story.append(t)

    build_rules_table(singles, "1. Single-Attribute Exact Matches ($S_{E} == S_{A}$)", "#1e293b")
    build_rules_table(two_and, "2. Two-Attribute Exact Intersections ($S_{E} == S_{A} \cap S_{B}$)", "#4c1d95")
    build_rules_table(three_and, "3. Three-Attribute Exact Intersections ($S_{E} == S_{A} \cap S_{B} \cap S_{C}$)", "#4c1d95")
    build_rules_table(two_or, "4. Two-Attribute Exact Unions ($S_{E} == S_{A} \cup S_{B}$)", "#0369a1")
    build_rules_table(three_or, "5. Three-Attribute Exact Unions ($S_{E} == S_{A} \cup S_{B} \cup S_{C}$)", "#0369a1")
    build_rules_table(four_or, "6. Four-Attribute Exact Unions ($S_{E} == S_{A} \cup S_{B} \cup S_{C} \cup S_{D}$)", "#0369a1")

    # 4. SUGGESTED ACCESS PROFILES
    story.append(Spacer(1, 15))
    story.append(Paragraph("7. Suggested Access Profiles (Unexplained Entitlement Bundles)", s_h1))
    story.append(Paragraph("These entitlements share the exact same user cohort, but do NOT map cleanly to any HR attribute combination. They likely represent pure functional Access Profiles.", s_sub))
    
    if suggested_aps:
        ap_rows = [[Paragraph("<b>Cohort Size</b>", s_th), Paragraph("<b>Entitlement Count</b>", s_th), Paragraph("<b>Bundled Entitlements (Source)</b>", s_th)]]
        for ap in suggested_aps:
            ents_formatted = "<br/>".join([
                f"• {safe_trunc(e)} <font color='#64748b'>({ent_source_map.get(e, 'Unknown')})</font>" 
                for e in ap["entitlements"]
            ])
            
            # FIXED: Used len(ap['entitlements']) instead of relying on missing 'entitlement_count' key
            ap_rows.append([
                Paragraph(f"<b>{ap['population']} users</b>", s_cell),
                Paragraph(f"{len(ap['entitlements'])} items", s_cell),
                Paragraph(ents_formatted, s_cell)
            ])
        t_ap = Table(ap_rows, colWidths=[80, 80, 344], repeatRows=1)
        t_ap.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#b45309")), 
            ("GRID", (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")), 
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fffbeb")]),
            ("VALIGN", (0,0), (-1,-1), "TOP")
        ]))
        story.append(t_ap)
    else:
        story.append(Paragraph("<i>No orphaned access profiles found.</i>", s_cell))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Generated Exact Attribute Unions & Intersections Report: {filename}")


if __name__ == "__main__":
    print("📡 Extracting Identities, Entitlements, and Attributes from Database...")
    ent_sets, attr_sets, _ = load_identity_sets()
    
    print("📡 Fetching Entitlement Source mappings...")
    ent_source_map = get_entitlement_sources()
    
    unique_ids = set()
    for ids in attr_sets.values(): unique_ids.update(ids)
    
    print("⚙️ Executing Exact Math Engine (Unions, Intersections, and APs)...")
    results_dict = find_exact_correlations(ent_sets, attr_sets)
    
    print("📄 Rendering PDF Document...")
    generate_pdf(len(unique_ids), len(ent_sets), results_dict, ent_source_map, OUTPUT_PDF)
