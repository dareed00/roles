#!/usr/bin/env python3
"""
bundleBuilder - Unified Heterogeneous Graph Role Report Generator
Queries: Unified_Discovered_Roles & Unified_Role_Members
Features:
  - 100% Alignment with Unified Graph Database Schema
  - Dedicated New Page for Every Role (PageBreak)
  - Pluralized Dynamic Names ("All Doctors", "All DevOps Engineers")
  - Live Dual-Direction Set Difference (Identities_Filtered)
  - Automated Root-Cause Diagnostics
"""

import os
import sys
from datetime import datetime
from collections import defaultdict
import mysql.connector
from mysql.connector import Error

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
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
# 1. DATABASE CONFIGURATION
# ==============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}
OUTPUT_PDF = "Unified_Mined_Roles_Report.pdf"

# ==============================================================================
# 2. RUNNING CANVAS (Page X of Y & Headers/Footers)
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
            self.drawString(54, 750, "bundleBuilder | Unified Graph Role Mining & Governance Report")
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
# 3. ROOT-CAUSE DIAGNOSTIC ENGINE
# ==============================================================================
def diagnose_root_cause(users_list, variance_type="missing"):
    """Analyzes identity attributes to explain why users are missing or extra."""
    if not users_list:
        return "No specific identity anomalies."

    reasons = []
    locations = {u.get("location") for u in users_list if u.get("location")}
    countries = {u.get("country") for u in users_list if u.get("country")}
    if len(locations) == 1 and list(locations)[0]:
        reasons.append(f"Geographic Cluster ({list(locations)[0]})")
    elif len(countries) == 1 and list(countries)[0]:
        reasons.append(f"Country Boundary ({list(countries)[0]})")

    types = {u.get("type") for u in users_list if u.get("type")}
    if len(types) == 1 and list(types)[0]:
        t_val = list(types)[0]
        if t_val.lower() in ["contractor", "vendor", "temp", "intern"]:
            reasons.append(f"Persona Filter ({t_val})")

    managers = [u for u in users_list if str(u.get("isManager")).lower() in ["true", "1", "yes"]]
    if len(managers) == len(users_list):
        reasons.append("Managerial Role Variance")

    recent_hires = 0
    now = datetime.now()
    for u in users_list:
        cdt = u.get("created")
        if cdt and isinstance(cdt, datetime):
            if (now - cdt).days <= 60:
                recent_hires += 1
    if recent_hires > 0 and recent_hires == len(users_list):
        reasons.append("New Hire Onboarding Lag (<60d tenure)")

    if not reasons:
        titles = {u.get("jobTitle") for u in users_list if u.get("jobTitle")}
        if len(titles) == 1 and list(titles)[0]:
            reasons.append(f"Job Title Nuance ({list(titles)[0]})")
        else:
            if variance_type == "missing":
                reasons.append("Unfulfilled Birthright Provisioning Gap")
            else:
                reasons.append("Ad-hoc / Unmanaged Direct Assignment")

    return " | ".join(reasons)


# ==============================================================================
# 4. DATA EXTRACTION FROM UNIFIED TABLES
# ==============================================================================
def fetch_unified_report_data():
    """Queries Unified_Discovered_Roles and Unified_Role_Members and executes live set differences."""
    try:
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
        data = {}

        # 1. Executive Summary Totals
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM Unified_Discovered_Roles) AS total_roles,
                (SELECT COUNT(*) FROM Identities_Filtered) AS id_cnt,
                (SELECT COUNT(*) FROM entitlements) AS ent_cnt,
                (SELECT AVG(avg_internal_jaccard) FROM Unified_Discovered_Roles) AS avg_cohesion,
                (SELECT AVG(recommendation_score) FROM Unified_Discovered_Roles) AS avg_rec_score
        """)
        data["summary"] = cursor.fetchone()

        # 2. Fetch all Unified Roles
        cursor.execute("""
            SELECT id, community_id, role_name, role_type, primary_attribute_name, primary_attribute_value,
                   assignment_rule, avg_internal_jaccard, recommendation_score, entitlement_count,
                   attribute_count, user_footprint
            FROM Unified_Discovered_Roles
            ORDER BY recommendation_score DESC, id ASC
        """)
        roles = cursor.fetchall()
        data["roles"] = roles
        print(f"📊 Loaded {len(roles)} roles from Unified_Discovered_Roles.")

        if not roles:
            cursor.close()
            db_connection.close()
            return data

        # 3. Fetch all Unified Role Members (Attributes + Entitlements)
        cursor.execute("""
            SELECT 
                m.role_id, m.community_id, m.node_type, m.node_name, 
                m.node_attribute_name, m.node_attribute_value, m.source_system, 
                m.population_size, m.internal_centrality_score, m.is_primary_criteria,
                eap.count_direct, eap.total_population, eap.count_via_role
            FROM Unified_Role_Members m
            LEFT JOIN Entitlement_Analysis_Profile eap ON m.node_name = eap.entitlement_name
            ORDER BY m.role_id ASC, m.node_type ASC, m.internal_centrality_score DESC
        """)
        members_by_role = defaultdict(lambda: {"attributes": [], "entitlements": []})
        for m in cursor.fetchall():
            if m["node_type"] == "ATTRIBUTE":
                members_by_role[m["role_id"]]["attributes"].append(m)
            else:
                members_by_role[m["role_id"]]["entitlements"].append(m)
        data["members_by_role"] = members_by_role

        # 4. Cache Identity Attributes for Live Variance Lookups
        print("👤 Caching identity attributes from Identities_Filtered...")
        cursor.execute("""
            SELECT 
                i.id, i.name AS uid, i.displayName, i.email, i.status, i.isManager, i.created,
                (SELECT attribute_value FROM Identity_Attributes_Filtered WHERE identity_id = i.id AND attribute_name = 'jobTitle' LIMIT 1) AS jobTitle,
                (SELECT attribute_value FROM Identity_Attributes_Filtered WHERE identity_id = i.id AND attribute_name = 'department' LIMIT 1) AS department,
                (SELECT attribute_value FROM Identity_Attributes_Filtered WHERE identity_id = i.id AND attribute_name = 'location' LIMIT 1) AS location,
                (SELECT attribute_value FROM Identity_Attributes_Filtered WHERE identity_id = i.id AND attribute_name = 'country' LIMIT 1) AS country,
                (SELECT attribute_value FROM Identity_Attributes_Filtered WHERE identity_id = i.id AND attribute_name = 'type' LIMIT 1) AS type
            FROM Identities_Filtered i
        """)
        identity_cache = {row["id"]: row for row in cursor.fetchall()}

        # 5. Cache Entitlement Assignments (Direct + Effective)
        print("🔗 Caching entitlement assignments...")
        cursor.execute("""
            SELECT DISTINCT identity_id, entitlement_name 
            FROM (
                SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
                UNION
                SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
            ) t
        """)
        ent_assignments_map = defaultdict(set)
        for row in cursor.fetchall():
            ent_assignments_map[row["entitlement_name"]].add(row["identity_id"])

        # 6. Cache Attribute to Identity Mapping
        cursor.execute("SELECT identity_id, attribute_name, attribute_value FROM Identity_Attributes_Filtered")
        attr_identities_map = defaultdict(set)
        for row in cursor.fetchall():
            attr_key = (row["attribute_name"], row["attribute_value"])
            attr_identities_map[attr_key].add(row["identity_id"])

        # 7. Compute Exact Dual-Direction Set Differences
        print("⚙️ Computing dual-direction population variances for each unified role...")
        data["role_variance_users"] = {}

        for r in roles:
            role_id = r["id"]
            role_attrs = members_by_role[role_id]["attributes"]
            role_ents = members_by_role[role_id]["entitlements"]

            if not role_ents:
                continue

            # Establish the Role Cohort (I_role)
            if role_attrs:
                # Intersect or use primary attribute
                primary_a = next((a for a in role_attrs if a["is_primary_criteria"]), role_attrs[0])
                role_key = (primary_a["node_attribute_name"], primary_a["node_attribute_value"])
                role_identities = set(attr_identities_map.get(role_key, set()))
            else:
                core_ent = role_ents[0]["node_name"]
                role_identities = set(ent_assignments_map.get(core_ent, set()))

            data["role_variance_users"][role_id] = {}

            # Compare against each member entitlement (I_ent)
            for e in role_ents:
                ent_name = e["node_name"]
                ent_identities = set(ent_assignments_map.get(ent_name, set()))

                missing_id_set = role_identities - ent_identities
                extra_id_set = ent_identities - role_identities

                if missing_id_set or extra_id_set:
                    missing_user_records = [identity_cache[uid] for uid in missing_id_set if uid in identity_cache]
                    extra_user_records = [identity_cache[uid] for uid in extra_id_set if uid in identity_cache]

                    data["role_variance_users"][role_id][ent_name] = {
                        "missing": missing_user_records,
                        "extra": extra_user_records,
                        "missing_count": len(missing_id_set),
                        "extra_count": len(extra_id_set),
                    }

        cursor.close()
        db_connection.close()
        return data

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


# ==============================================================================
# 5. PDF GENERATION ENGINE
# ==============================================================================
def generate_pdf(data, filename=OUTPUT_PDF):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    styles = getSampleStyleSheet()

    # Typography & Colors
    s_title = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#0f172a"))
    s_sub = ParagraphStyle("S", fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor("#64748b"), spaceAfter=8)
    s_h1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor("#1e293b"), spaceBefore=12, spaceAfter=4, keepWithNext=True)
    s_h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#0284c7"), spaceBefore=4, spaceAfter=4, keepWithNext=True)
    s_cell = ParagraphStyle("C", fontName="Helvetica", fontSize=7.2, leading=9.2, textColor=colors.HexColor("#1e293b"))
    s_th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7.2, leading=9.2, textColor=colors.white)
    s_box = ParagraphStyle("B", fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#334155"), keepWithNext=True)
    s_section_sub = ParagraphStyle("SS", fontName="Helvetica-Bold", fontSize=7.8, leading=10, textColor=colors.HexColor("#475569"), spaceBefore=6, spaceAfter=2, keepWithNext=True)
    s_diag_title = ParagraphStyle("DT", fontName="Helvetica-Bold", fontSize=7.8, leading=10, textColor=colors.HexColor("#92400e"), spaceBefore=6, spaceAfter=2, keepWithNext=True)

    story = []

    # --------------------------------------------------------------------------
    # HEADER & EXECUTIVE KPI SUMMARY (Page 1)
    # --------------------------------------------------------------------------
    story.append(Paragraph("Unified Graph Role Mining & Governance Report", s_title))
    story.append(Paragraph(f"Database: <b>bundleBuilder</b> | Tables: <code>Unified_Discovered_Roles</code> & <code>Unified_Role_Members</code> | Date: {datetime.now().strftime('%B %d, %Y')}", s_sub))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=8))

    s = data["summary"]
    cohesion_pct = float(s["avg_cohesion"] or 0) * 100
    kpis = [
        [
            Paragraph("<b>Total Discovered Roles</b>", s_cell),
            Paragraph("<b>Identities Filtered</b>", s_cell),
            Paragraph("<b>Catalog Entitlements</b>", s_cell),
            Paragraph("<b>Avg Graph Cohesion</b>", s_cell),
            Paragraph("<b>Avg Rec. Score</b>", s_cell),
        ],
        [
            Paragraph(f"<b>{s['total_roles'] or 0:,}</b>", s_cell),
            Paragraph(f"<b>{s['id_cnt'] or 0:,}</b>", s_cell),
            Paragraph(f"<b>{s['ent_cnt'] or 0:,}</b>", s_cell),
            Paragraph(f"<font color='#16a34a'><b>{cohesion_pct:.1f}%</b></font>", s_cell),
            Paragraph(f"<b>{float(s['avg_rec_score'] or 0):.2f}</b>", s_cell),
        ],
    ]
    t_kpi = Table(kpis, colWidths=[100, 100, 100, 104, 100])
    t_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_kpi)
    story.append(Spacer(1, 10))

    # --------------------------------------------------------------------------
    # MASTER INDEX DIRECTORY TABLE
    # --------------------------------------------------------------------------
    story.append(Paragraph("Master Index: All Unified Mined Roles", s_h1))
    story.append(Paragraph("Complete catalog of mined roles generated by the unified heterogeneous graph engine.", s_box))
    story.append(Spacer(1, 4))

    master_rows = [
        [
            Paragraph("<b>#</b>", s_th),
            Paragraph("<b>Mined Role Name</b>", s_th),
            Paragraph("<b>Assignment Criteria</b>", s_th),
            Paragraph("<b>Role Type</b>", s_th),
            Paragraph("<b>Cohesion</b>", s_th),
            Paragraph("<b>Footprint</b>", s_th),
            Paragraph("<b>Ent. Count</b>", s_th),
        ]
    ]

    for idx, r in enumerate(data["roles"], 1):
        j_pct = float(r["avg_internal_jaccard"]) * 100
        score_color = "#16a34a" if j_pct >= 90 else ("#0284c7" if j_pct >= 75 else "#d97706")
        badge_type = f"<font size='6'>{r['role_type']}</font>"

        master_rows.append([
            Paragraph(str(idx), s_cell),
            Paragraph(f"<b>{r['role_name']}</b>", s_cell),
            Paragraph(r["assignment_rule"] or "<i>Pure Entitlement Modularity</i>", s_cell),
            Paragraph(badge_type, s_cell),
            Paragraph(f"<font color='{score_color}'><b>{j_pct:.1f}%</b></font>", s_cell),
            Paragraph(f"{r['user_footprint']:,} users", s_cell),
            Paragraph(f"{r['entitlement_count']} items", s_cell),
        ])

    t_master = Table(master_rows, colWidths=[20, 130, 140, 64, 45, 55, 50], repeatRows=1)
    t_master.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_master)

    # --------------------------------------------------------------------------
    # INDIVIDUAL ROLE PAGES (EACH ROLE ON A DEDICATED NEW PAGE)
    # --------------------------------------------------------------------------
    for idx, r in enumerate(data["roles"], 1):
        # 📄 FORCE EVERY ROLE ONTO A NEW PAGE
        story.append(PageBreak())

        role_id = r["id"]
        role_footprint = r["user_footprint"]
        jaccard_pct = float(r["avg_internal_jaccard"]) * 100
        rec_score = float(r["recommendation_score"])
        attrs = data["members_by_role"][role_id]["attributes"]
        ents = data["members_by_role"][role_id]["entitlements"]

        # Role Header Banner
        story.append(Paragraph(f"Role #{idx}: {r['role_name']}", s_h2))
        story.append(
            Paragraph(
                f"<b>Role Architecture:</b> {r['role_type']} &nbsp;|&nbsp; "
                f"<b>Graph Cohesion:</b> <font color='#16a34a'><b>{jaccard_pct:.1f}%</b></font> &nbsp;|&nbsp; "
                f"<b>Role Footprint:</b> {role_footprint:,} identities &nbsp;|&nbsp; "
                f"<b>Entitlements:</b> {r['entitlement_count']} &nbsp;|&nbsp; "
                f"<b>Community ID:</b> {r['community_id']}",
                s_box,
            )
        )
        story.append(Spacer(1, 4))

        # ----------------------------------------------------------------------
        # SUB-SECTION A: BUNDLED ATTRIBUTE CRITERIA NODES
        # ----------------------------------------------------------------------
        story.append(Paragraph("📋 Bundled Identity Criteria (Attribute Population Nodes)", s_section_sub))
        if attrs:
            attr_rows = [
                [
                    Paragraph("<b>Attribute Name</b>", s_th),
                    Paragraph("<b>Attribute Value</b>", s_th),
                    Paragraph("<b>Population Size</b>", s_th),
                    Paragraph("<b>Centrality Score</b>", s_th),
                    Paragraph("<b>Primary Criteria Flag</b>", s_th),
                ]
            ]
            for a in attrs:
                is_p_badge = (
                    "<font color='#16a34a'><b>PRIMARY CRITERIA ★</b></font>"
                    if a["is_primary_criteria"]
                    else "<font color='#64748b'>Secondary Filter</font>"
                )
                attr_rows.append([
                    Paragraph(f"<code>{a['node_attribute_name']}</code>", s_cell),
                    Paragraph(f"<b>{a['node_attribute_value']}</b>", s_cell),
                    Paragraph(f"{a['population_size']:,} users", s_cell),
                    Paragraph(f"{float(a['internal_centrality_score']):.4f}", s_cell),
                    Paragraph(is_p_badge, s_cell),
                ])

            t_attr = Table(attr_rows, colWidths=[110, 154, 75, 75, 90], repeatRows=1)
            t_attr.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_attr)
        else:
            story.append(Paragraph("<i>No identity attributes clustered in this community (Pure Entitlement Bundle).</i>", s_cell))

        story.append(Spacer(1, 4))

        # ----------------------------------------------------------------------
        # SUB-SECTION B: ENTITLEMENT COMPOSITION & MATCH STATUS
        # ----------------------------------------------------------------------
        story.append(Paragraph("🧩 Entitlement Composition & Centrality", s_section_sub))
        if ents:
            ent_rows = [
                [
                    Paragraph("<b>Entitlement Name</b>", s_th),
                    Paragraph("<b>Source App</b>", s_th),
                    Paragraph("<b>Ent. Pop</b>", s_th),
                    Paragraph("<b>Role Footprint</b>", s_th),
                    Paragraph("<b>Population Match</b>", s_th),
                    Paragraph("<b>Centrality (Verdict)</b>", s_th),
                ]
            ]
            for e in ents:
                ent_pop = e["population_size"] or 0
                cent = float(e["internal_centrality_score"] or 0)
                delta = ent_pop - role_footprint

                if delta == 0:
                    status_badge = "<font color='#16a34a'><b>Exact Match (100%)</b></font>"
                elif delta < 0:
                    status_badge = f"<font color='#d97706'><b>{abs(delta)} Missing ({ent_pop}/{role_footprint})</b></font>"
                else:
                    status_badge = f"<font color='#2563eb'><b>+{delta} Extra ({ent_pop}/{role_footprint})</b></font>"

                verdict = "CORE" if cent >= 0.85 else ("EVALUATE" if cent >= 0.60 else "PRUNE")
                verdict_color = "#16a34a" if verdict == "CORE" else ("#d97706" if verdict == "EVALUATE" else "#dc2626")

                ent_rows.append([
                    Paragraph(f"<b>{e['node_name']}</b>", s_cell),
                    Paragraph(str(e.get("source_system") or "Catalog"), s_cell),
                    Paragraph(str(ent_pop), s_cell),
                    Paragraph(str(role_footprint), s_cell),
                    Paragraph(status_badge, s_cell),
                    Paragraph(f"{cent:.4f} (<font color='{verdict_color}'><b>{verdict}</b></font>)", s_cell),
                ])

            t_ent = Table(ent_rows, colWidths=[145, 70, 45, 60, 105, 79], repeatRows=1)
            t_ent.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_ent)

            # ------------------------------------------------------------------
            # SUB-SECTION C: EXACT DUAL-DIRECTION IDENTITY DIFFERENCES
            # ------------------------------------------------------------------
            role_var_map = data["role_variance_users"].get(role_id, {})
            if role_var_map:
                story.append(Spacer(1, 4))
                story.append(Paragraph("🔍 Live Population Variance: Missing & Extra Users (Dual-Set Difference)", s_diag_title))

                var_rows = [
                    [
                        Paragraph("<b>Entitlement Name</b>", s_th),
                        Paragraph("<b>Variance Type</b>", s_th),
                        Paragraph("<b>Identity (UID / Name)</b>", s_th),
                        Paragraph("<b>Job Title / Dept</b>", s_th),
                        Paragraph("<b>Location / Type</b>", s_th),
                        Paragraph("<b>Diagnostic Reason ('Why')</b>", s_th),
                    ]
                ]

                has_items = False
                for ent_name, v_data in role_var_map.items():
                    missing_list = v_data.get("missing", [])
                    extra_list = v_data.get("extra", [])

                    # 1. Missing Users (In Role, but Missing Entitlement)
                    if missing_list:
                        has_items = True
                        diag_why = diagnose_root_cause(missing_list, "missing")
                        for u in missing_list[:3]:
                            u_display = f"<code>{u['uid']}</code>"
                            if u.get("displayName"):
                                u_display += f"<br/><font color='#64748b'>{u['displayName']}</font>"

                            title_dept = f"{u.get('jobTitle') or 'N/A'}<br/><font color='#64748b'>{u.get('department') or 'N/A'}</font>"
                            loc_type = f"{u.get('location') or 'N/A'}<br/><font color='#64748b'>{u.get('type') or 'Employee'}</font>"

                            var_rows.append([
                                Paragraph(f"<b>{ent_name}</b>", s_cell),
                                Paragraph("<font color='#b45309'><b>Missing Access</b><br/>(In Role)</font>", s_cell),
                                Paragraph(u_display, s_cell),
                                Paragraph(title_dept, s_cell),
                                Paragraph(loc_type, s_cell),
                                Paragraph(f"<b>{diag_why}</b>", s_cell),
                            ])
                        if len(missing_list) > 3:
                            var_rows.append([
                                Paragraph(f"<b>{ent_name}</b>", s_cell),
                                Paragraph("<font color='#b45309'><b>Missing Access</b></font>", s_cell),
                                Paragraph(f"<i>+{len(missing_list) - 3} more missing users</i>", s_cell),
                                Paragraph("—", s_cell),
                                Paragraph("—", s_cell),
                                Paragraph(f"<b>{diag_why}</b>", s_cell),
                            ])

                    # 2. Extra Users (Has Entitlement, but Outside Role Footprint)
                    if extra_list:
                        has_items = True
                        diag_why = diagnose_root_cause(extra_list, "extra")
                        for u in extra_list[:3]:
                            u_display = f"<code>{u['uid']}</code>"
                            if u.get("displayName"):
                                u_display += f"<br/><font color='#64748b'>{u['displayName']}</font>"

                            title_dept = f"{u.get('jobTitle') or 'N/A'}<br/><font color='#64748b'>{u.get('department') or 'N/A'}</font>"
                            loc_type = f"{u.get('location') or 'N/A'}<br/><font color='#64748b'>{u.get('type') or 'Employee'}</font>"

                            var_rows.append([
                                Paragraph(f"<b>{ent_name}</b>", s_cell),
                                Paragraph("<font color='#2563eb'><b>Extra Access</b><br/>(Outside Role)</font>", s_cell),
                                Paragraph(u_display, s_cell),
                                Paragraph(title_dept, s_cell),
                                Paragraph(loc_type, s_cell),
                                Paragraph(f"<b>{diag_why}</b>", s_cell),
                            ])
                        if len(extra_list) > 3:
                            var_rows.append([
                                Paragraph(f"<b>{ent_name}</b>", s_cell),
                                Paragraph("<font color='#2563eb'><b>Extra Access</b></font>", s_cell),
                                Paragraph(f"<i>+{len(extra_list) - 3} more extra users</i>", s_cell),
                                Paragraph("—", s_cell),
                                Paragraph("—", s_cell),
                                Paragraph(f"<b>{diag_why}</b>", s_cell),
                            ])

                if has_items:
                    t_var = Table(var_rows, colWidths=[105, 75, 80, 80, 75, 89], repeatRows=1)
                    t_var.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#78350f")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fffbeb"), colors.white]),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]))
                    story.append(t_var)

    # Build Document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Successfully compiled Unified Graph Role Mining Report: {filename}")


# ==============================================================================
# 6. EXECUTION ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    print("📡 Querying bundleBuilder database (Unified_Discovered_Roles & Unified_Role_Members)...")
    dataset = fetch_unified_report_data()
    print("📄 Rendering multi-page PDF document...")
    generate_pdf(dataset, OUTPUT_PDF)
