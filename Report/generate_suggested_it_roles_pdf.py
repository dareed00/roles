#!/usr/bin/env python3
"""
bundleBuilder - Suggested IT Roles & Functional Access Profiles PDF Generator
Renders each IT/Functional Role on its own scorecard page with bundled permissions,
cohesion metrics, and enriched adoption rosters (Full vs. Partial Holders).
"""

import os
import sys
import html
from datetime import datetime, date
from collections import defaultdict
import mysql.connector
from mysql.connector import Error

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
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
# 1. DYNAMIC NUMBERED CANVAS (PAGE X OF Y)
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
        
        # Header (Top)
        self.drawString(54, 750, "bundleBuilder | Suggested IT & Functional Role Scorecard")
        self.drawRightString(558, 750, "CONFIDENTIAL & PROPRIETARY")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        
        # Footer (Bottom)
        self.line(54, 44, 558, 44)
        self.drawString(54, 32, f"Evaluation Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Scope: Peer Entitlement Clustering")
        self.drawRightString(558, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


# ==============================================================================
# 2. DATE PARSER & TENURE CALCULATOR
# ==============================================================================
def parse_hire_date(date_str):
    if not date_str:
        return None, "Unknown"
    
    clean_str = str(date_str).strip()
    formats = [
        "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%m/%d/%Y",
        "%d-%m-%Y", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"
    ]
    
    parsed_date = None
    for fmt in formats:
        try:
            parsed_date = datetime.strptime(clean_str.split(".")[0], fmt).date()
            break
        except (ValueError, TypeError):
            continue

    if not parsed_date:
        return None, clean_str

    days_ago = (date.today() - parsed_date).days
    return days_ago, parsed_date.strftime("%Y-%m-%d")


def format_tenure_badge(days_ago, date_formatted):
    if days_ago is None:
        return f"<b>{date_formatted}</b><br/><font color='#64748b'>Tenure: Unknown</font>"
    
    if 0 <= days_ago <= 30:
        return f"<b>{date_formatted}</b><br/><font color='#16a34a'><b>[🐣 New Hire: {days_ago}d ago]</b></font>"
    elif 30 < days_ago <= 90:
        return f"<b>{date_formatted}</b><br/><font color='#0284c7'><b>[Onboarding: {days_ago}d ago]</b></font>"
    elif days_ago > 90:
        years = days_ago / 365.25
        if years >= 1.0:
            return f"<b>{date_formatted}</b><br/><font color='#64748b'>[{days_ago:,}d ago / {years:.1f}y]</font>"
        return f"<b>{date_formatted}</b><br/><font color='#64748b'>[{days_ago}d ago]</font>"
    else:
        return f"<b>{date_formatted}</b><br/><font color='#7c3aed'><b>[Future Hire: in {abs(days_ago)}d]</b></font>"


# ==============================================================================
# 3. DATA LOADER & PROFILE ENRICHER
# ==============================================================================
def load_it_role_catalog_data():
    try:
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.")

        # 1. Fetch Suggested IT Roles
        cursor.execute("""
            SELECT 
                id, it_role_name, primary_source, description, entitlements_count,
                full_holders_count, partial_holders_count, bundle_cohesion_score, role_type
            FROM Suggested_IT_Roles
            ORDER BY entitlements_count DESC, full_holders_count DESC
        """)
        it_roles = cursor.fetchall()

        # 2. Fetch IT Role Entitlements
        cursor.execute("""
            SELECT 
                it_role_id, entitlement_id, entitlement_name, source_name, assignment_count
            FROM Suggested_IT_Role_Entitlements
            ORDER BY assignment_count DESC, entitlement_name ASC
        """)
        ent_rows = cursor.fetchall()
        role_ents_map = defaultdict(list)
        for e in ent_rows:
            role_ents_map[e["it_role_id"]].append(e)

        # 3. Fetch Enriched Identity Profiles
        print("👤 Fetching and indexing Identity Profiles...")
        cursor.execute("""
            SELECT identity_id, attribute_name, attribute_value 
            FROM Identity_Attributes_Filtered
            WHERE attribute_value IS NOT NULL AND TRIM(attribute_value) != ''
        """)
        raw_attrs = cursor.fetchall()
        
        user_attr_map = defaultdict(dict)
        for row in raw_attrs:
            uid = str(row["identity_id"]).strip()
            name_key = str(row["attribute_name"]).strip().lower()
            user_attr_map[uid][name_key] = str(row["attribute_value"]).strip()

        identity_profiles = {}
        for uid, a in user_attr_map.items():
            first = a.get("firstname", a.get("first_name", ""))
            last = a.get("lastname", a.get("last_name", ""))
            full_name = f"{first} {last}".strip()
            if not full_name:
                full_name = a.get("displayname", a.get("name", a.get("fullname", uid)))

            state_raw = a.get("identitystate", a.get("status", a.get("state", a.get("cloudlifecyclestate", "ACTIVE")))).upper()
            if state_raw in ("ACTIVE", "TRUE", "ENABLED", "A"):
                state_badge = "<font color='#16a34a'><b>[🟢 ACTIVE]</b></font>"
                state_clean = "ACTIVE"
            elif state_raw in ("INACTIVE", "TERMINATED", "DISABLED", "FALSE", "T"):
                state_badge = "<font color='#dc2626'><b>[🔴 INACTIVE]</b></font>"
                state_clean = "INACTIVE"
            elif "LEAVE" in state_raw:
                state_badge = "<font color='#ca8a04'><b>[🟡 ON LEAVE]</b></font>"
                state_clean = "ON_LEAVE"
            else:
                state_badge = f"<font color='#64748b'><b>[{state_raw[:10]}]</b></font>"
                state_clean = state_raw

            hire_date_raw = a.get("startdate", a.get("hiredate", a.get("start_date", a.get("hire_date", a.get("createddate", None)))))
            days_ago, date_formatted = parse_hire_date(hire_date_raw)

            identity_profiles[uid] = {
                "uid": uid,
                "name": full_name,
                "title": a.get("jobtitle", a.get("title", "Unknown Title")),
                "department": a.get("department", a.get("dept", "Unknown Dept")),
                "location": a.get("location", a.get("city", a.get("site", "Unknown Location"))),
                "manager": a.get("manager", a.get("managername", a.get("supervisor", "Not Listed"))),
                "state_badge": state_badge,
                "state_clean": state_clean,
                "days_ago": days_ago,
                "hire_date_formatted": date_formatted,
                "is_new_hire": (days_ago is not None and 0 <= days_ago <= 30)
            }

        # 4. Fetch Identity Adoption Mappings per IT Role
        print("👥 Loading IT Role Identity Adoption Mappings...")
        cursor.execute("""
            SELECT 
                it_role_id, identity_id, held_entitlements_count, coverage_percentage, adoption_status
            FROM Suggested_IT_Role_Identities
            ORDER BY coverage_percentage DESC, held_entitlements_count DESC
        """)
        id_rows = cursor.fetchall()

        role_full_holders = defaultdict(list)
        role_partial_holders = defaultdict(list)

        for row in id_rows:
            rid = row["it_role_id"]
            uid = str(row["identity_id"]).strip()
            prof = identity_profiles.get(uid, {
                "uid": uid, "name": uid, "title": "Unknown", "department": "Unknown",
                "location": "Unknown", "manager": "Not Listed",
                "state_badge": "<font color='#64748b'><b>[UNKNOWN]</b></font>",
                "state_clean": "UNKNOWN", "days_ago": None,
                "hire_date_formatted": "Unknown", "is_new_hire": False
            })

            item = {
                "profile": prof,
                "held_count": row["held_entitlements_count"],
                "coverage_pct": float(row["coverage_percentage"]),
                "status": row["adoption_status"]
            }

            if row["adoption_status"] == "FULL_HOLDER":
                role_full_holders[rid].append(item)
            else:
                role_partial_holders[rid].append(item)

        cursor.close()
        db_connection.close()
        return it_roles, role_ents_map, identity_profiles, role_full_holders, role_partial_holders

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


def escape(val):
    return html.escape(str(val) if val is not None else "")


# ==============================================================================
# 4. PDF COMPILATION ENGINE
# ==============================================================================
def generate_pdf(it_roles, role_ents_map, identity_profiles, role_full_holders, role_partial_holders, filename=OUTPUT_PDF):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    styles = getSampleStyleSheet()

    # Typography Styles
    s_role_title = ParagraphStyle("RT", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor("#0f172a"))
    s_role_meta = ParagraphStyle("RM", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#64748b"), spaceAfter=5)
    s_h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#1e293b"), spaceBefore=7, spaceAfter=3)
    s_h3_green = ParagraphStyle("H3G", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor("#15803d"), spaceBefore=6, spaceAfter=2)
    s_h3_amber = ParagraphStyle("H3A", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor("#b45309"), spaceBefore=6, spaceAfter=2)

    s_cell = ParagraphStyle("C", fontName="Helvetica", fontSize=6.8, leading=8.5, textColor=colors.HexColor("#1e293b"))
    s_cell_bold = ParagraphStyle("CB", fontName="Helvetica-Bold", fontSize=6.8, leading=8.5, textColor=colors.HexColor("#0f172a"))
    s_cell_center = ParagraphStyle("CC", fontName="Helvetica", fontSize=6.8, leading=8.5, textColor=colors.HexColor("#1e293b"), alignment=1)
    s_th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7, leading=8.5, textColor=colors.white, alignment=1)
    
    s_desc_box = ParagraphStyle("DB", fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#334155"))
    s_notice = ParagraphStyle("NT", fontName="Helvetica-Oblique", fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))

    story = []
    total_roles = len(it_roles)
    print(f"📄 Rendering {total_roles} IT Roles into PDF scorecard...")

    for idx, role in enumerate(it_roles, start=1):
        role_id = role["id"]
        role_name = role["it_role_name"]
        primary_source = role["primary_source"]
        ents = role_ents_map.get(role_id, [])
        total_ents_in_role = role["entitlements_count"]

        full_holders = role_full_holders.get(role_id, [])
        partial_holders = role_partial_holders.get(role_id, [])
        total_users = len(full_holders) + len(partial_holders)

        # ----------------------------------------------------------------------
        # A. ROLE HEADER & METRICS
        # ----------------------------------------------------------------------
        story.append(Paragraph(f"<b>IT Role {idx} of {total_roles}:</b> {escape(role_name)}", s_role_title))
        story.append(Paragraph(
            f"IT Role ID: <b>ITR-{role_id:04d}</b> | Primary Source: <b>{escape(primary_source)}</b> | Cluster Cohesion: <b>{float(role['bundle_cohesion_score'])*100:.1f}% Jaccard</b> | Type: <b>FUNCTIONAL BUNDLE</b>",
            s_role_meta
        ))
        story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#4f46e5"), spaceAfter=4))

        # KPI Bar
        kpi_table_data = [
            [
                Paragraph("<b>Bundled Permissions</b>", s_cell_center),
                Paragraph("<b>Full Holders (100%)</b>", s_cell_center),
                Paragraph("<b>Partial Candidates</b>", s_cell_center),
                Paragraph("<b>Total User Footprint</b>", s_cell_center),
                Paragraph("<b>Bundle Cohesion</b>", s_cell_center),
            ],
            [
                Paragraph(f"<b>{total_ents_in_role} permissions</b>", s_cell_center),
                Paragraph(f"<font color='#16a34a'><b>{len(full_holders):,} users</b></font>", s_cell_center),
                Paragraph(f"<font color='#ca8a04'><b>{len(partial_holders):,} users</b></font>", s_cell_center),
                Paragraph(f"<b>{total_users:,} users</b>", s_cell_center),
                Paragraph(f"<b>{float(role['bundle_cohesion_score'])*100:.1f}%</b>", s_cell_center),
            ]
        ]
        t_kpi = Table(kpi_table_data, colWidths=[100, 100, 104, 100, 100])
        t_kpi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_kpi)
        story.append(Spacer(1, 4))

        # Functional Description Box
        desc_box_data = [[
            Paragraph("<b>Functional Scope:</b>", s_cell_bold),
            Paragraph(f"{escape(role['description'])}", s_desc_box)
        ]]
        t_desc = Table(desc_box_data, colWidths=[105, 399])
        t_desc.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef2ff")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c7d2fe")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_desc)
        story.append(Spacer(1, 4))

        # ----------------------------------------------------------------------
        # B. BUNDLED PERMISSIONS TABLE
        # ----------------------------------------------------------------------
        story.append(Paragraph("<b>Clustered Permissions in this Access Profile:</b>", s_h2))

        ent_table_data = [[
            Paragraph("<b>Permission / Entitlement Name</b>", s_th),
            Paragraph("<b>Target Application</b>", s_th),
            Paragraph("<b>Enterprise Assignments</b>", s_th),
            Paragraph("<b>Bundle Penetration</b>", s_th),
        ]]

        for e in ents:
            ent_name = e["entitlement_name"]
            source = e["source_name"] or primary_source
            assignments = e["assignment_count"]
            penetration = (len(full_holders) / assignments * 100.0) if assignments > 0 else 100.0

            ent_table_data.append([
                Paragraph(f"<b>{escape(ent_name)}</b>", s_cell),
                Paragraph(f"<font color='#64748b'>{escape(source)}</font>", s_cell),
                Paragraph(f"<b>{assignments:,} users</b>", s_cell_center),
                Paragraph(f"<b>{penetration:.1f}%</b>", s_cell_center),
            ])

        t_ents = Table(ent_table_data, colWidths=[230, 114, 80, 80], repeatRows=1)
        t_ents.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#312e81")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(t_ents)
        story.append(Spacer(1, 6))

        # ----------------------------------------------------------------------
        # C. SECTION 1: FULL ACCESS HOLDERS (100% COVERAGE)
        # ----------------------------------------------------------------------
        story.append(Paragraph(f"<b>🟢 Section A: Full Holders (100% Coverage — {len(full_holders)} Users)</b>", s_h3_green))

        if not full_holders:
            story.append(Paragraph("<i>⚠️ No users currently hold 100% of the bundle simultaneously.</i>", s_notice))
        else:
            full_table_data = [[
                Paragraph("<b>Identity & State</b>", s_th),
                Paragraph("<b>HR Context & Org</b>", s_th),
                Paragraph("<b>Start Date & Tenure</b>", s_th),
                Paragraph("<b>Recommended Action</b>", s_th),
            ]]

            for item in full_holders:
                p = item["profile"]
                tenure_badge = format_tenure_badge(p["days_ago"], p["hire_date_formatted"])

                action_p = Paragraph("<font color='#15803d'><b>🟢 ASSIGN IT ROLE</b></font><br/><font color='#64748b'>(Standardize Core Access)</font>", s_cell)
                col1 = Paragraph(f"{p['state_badge']}<br/><b>{escape(p['name'])}</b><br/><font color='#64748b'>UID: {escape(p['uid'])}</font>", s_cell)
                col2 = Paragraph(f"<b>Title:</b> {escape(p['title'])}<br/><b>Dept:</b> {escape(p['department'])}<br/><b>Mgr:</b> {escape(p['manager'])}", s_cell)
                col3 = Paragraph(tenure_badge, s_cell)

                full_table_data.append([col1, col2, col3, action_p])

            t_full = Table(full_table_data, colWidths=[115, 130, 105, 154], repeatRows=1)
            t_full.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#15803d")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_full)

        story.append(Spacer(1, 6))

        # ----------------------------------------------------------------------
        # D. SECTION 2: PARTIAL HOLDERS (<100% COVERAGE — ADOPTION CANDIDATES)
        # ----------------------------------------------------------------------
        story.append(Paragraph(f"<b>⚠️ Section B: Partial Holders (<100% Coverage — {len(partial_holders)} Users)</b>", s_h3_amber))

        if not partial_holders:
            story.append(Paragraph("<i>✅ No partial holders. All users in this footprint hold either 100% or 0% of permissions.</i>", s_notice))
        else:
            partial_table_data = [[
                Paragraph("<b>Identity & State</b>", s_th),
                Paragraph("<b>Current HR Context</b>", s_th),
                Paragraph("<b>Start Date & Tenure</b>", s_th),
                Paragraph("<b>Bundle Coverage</b>", s_th),
                Paragraph("<b>Recommended Action</b>", s_th),
            ]]

            for item in partial_holders:
                p = item["profile"]
                tenure_badge = format_tenure_badge(p["days_ago"], p["hire_date_formatted"])
                held_cnt = item["held_count"]
                cov_pct = item["coverage_pct"]

                # Action determination with CERTIFY or REVOKE
                if p["state_clean"] == "INACTIVE":
                    action_p = Paragraph("<font color='#dc2626'><b>🔴 CERTIFY or REVOKE IMMEDIATELY</b></font><br/><font color='#64748b'>(Terminated Identity)</font>", s_cell)
                elif cov_pct >= 66.0:
                    action_p = Paragraph("<font color='#16a34a'><b>🟢 COMPLETE BUNDLE</b></font><br/><font color='#64748b'>(High-Coverage Candidate)</font>", s_cell)
                else:
                    action_p = Paragraph("<font color='#ea580c'><b>🟠 CERTIFY or REVOKE</b></font><br/><font color='#64748b'>(Partial Rogue / Mover Access)</font>", s_cell)

                col1 = Paragraph(f"{p['state_badge']}<br/><b>{escape(p['name'])}</b><br/><font color='#64748b'>UID: {escape(p['uid'])}</font>", s_cell)
                col2 = Paragraph(f"<b>Title:</b> {escape(p['title'])}<br/><b>Dept:</b> {escape(p['department'])}<br/><b>Mgr:</b> {escape(p['manager'])}", s_cell)
                col3 = Paragraph(tenure_badge, s_cell)
                col4 = Paragraph(f"<b>{held_cnt} of {total_ents_in_role}</b><br/><font color='#b45309'><b>({cov_pct:.1f}%)</b></font>", s_cell_center)

                partial_table_data.append([col1, col2, col3, col4, action_p])

            t_partial = Table(partial_table_data, colWidths=[105, 115, 95, 95, 94], repeatRows=1)
            t_partial.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b45309")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fffbeb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_partial)

        # Force next role onto a clean new page
        if idx < total_roles:
            story.append(PageBreak())

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Generated Complete IT Roles Catalog: {filename} ({total_roles} pages)")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    it_roles, role_ents_map, identity_profiles, role_full_holders, role_partial_holders = load_it_role_catalog_data()
    if not it_roles:
        print("⚠️ No suggested IT roles found in `Suggested_IT_Roles`. Please run `synthesize_it_roles.py` first.")
        sys.exit(0)

    generate_pdf(it_roles, role_ents_map, identity_profiles, role_full_holders, role_partial_holders, OUTPUT_PDF)
