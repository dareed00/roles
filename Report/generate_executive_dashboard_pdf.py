#!/usr/bin/env python3
"""
bundleBuilder - Combined Executive Governance Dashboard (Business & IT Roles)
Synthesizes Birthright Business Roles and Functional IT Roles into a cohesive,
high-impact executive report with KPI scorecards, role catalogs, and risk triage.
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak, KeepTogether
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


OUTPUT_PDF = "Executive_Role_Mining_Governance_Dashboard.pdf"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


# ==============================================================================
# 1. NUMBERED CANVAS (PAGE X OF Y)
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
        self.drawString(54, 750, "bundleBuilder | Executive Identity Governance & Role Mining Dashboard")
        self.drawRightString(558, 750, "EXECUTIVE BRIEFING | CONFIDENTIAL")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        
        # Footer (Bottom)
        self.line(54, 44, 558, 44)
        self.drawString(54, 32, f"Evaluation Date: {datetime.now().strftime('%B %d, %Y')} | Scope: Unified Business & IT Role Program")
        self.drawRightString(558, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


# ==============================================================================
# 2. DATA AGGREGATION & GOVERNANCE METRICS ENGINE
# ==============================================================================
def load_executive_dashboard_data():
    try:
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.")

        # 1. Global Enterprise Metrics
        print("📊 Querying Enterprise Identity & Entitlement Baselines...")
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT identity_id) as total_identities,
                COUNT(DISTINCT entitlement_name) as total_unique_entitlements,
                COUNT(*) as total_raw_assignments
            FROM (
                SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
                UNION
                SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
            ) t
        """)
        baseline = cursor.fetchone()

        # 2. Business Roles Metrics & Top Roles
        print("🏛️ Loading Business Roles (Birthright)...")
        cursor.execute("""
            SELECT 
                id, role_name, assignment_rule, target_population,
                exact_entitlements_count, fuzzy_entitlements_count, total_entitlements_count, avg_jaccard_score
            FROM Suggested_Roles
            ORDER BY total_entitlements_count DESC, target_population DESC
        """)
        biz_roles = cursor.fetchall()

        # Fetch Business Role Entitlements for Governed Grant totals
        cursor.execute("""
            SELECT 
                role_id, match_type, jaccard_score, missing_users_count, extra_users_count
            FROM Suggested_Role_Entitlements
        """)
        biz_ents = cursor.fetchall()
        biz_ents_by_role = defaultdict(list)
        for e in biz_ents:
            biz_ents_by_role[e["role_id"]].append(e)

        # Calculate Governed Grants per Business Role
        for r in biz_roles:
            r_ents = biz_ents_by_role.get(r["id"], [])
            r["governed_grants"] = sum(max(0, r["target_population"] - e["missing_users_count"]) for e in r_ents)

        # 3. IT Functional Roles Metrics & Top Roles
        print("🛠️ Loading IT Roles (Functional Access Profiles)...")
        cursor.execute("""
            SELECT 
                id, it_role_name, primary_source, entitlements_count,
                full_holders_count, partial_holders_count, bundle_cohesion_score
            FROM Suggested_IT_Roles
            ORDER BY entitlements_count DESC, full_holders_count DESC
        """)
        it_roles = cursor.fetchall()

        # 4. Inactive & Risk Exception Triage
        print("🛑 Triaging Critical Identity Access Anomalies...")
        cursor.execute("""
            SELECT 
                fre.identity_id,
                fre.exception_type,
                fdr.entitlement_name,
                r.role_name
            FROM Fuzzy_Rule_Exceptions fre
            JOIN Fuzzy_Discovered_Rules fdr ON fre.rule_id = fdr.id AND fdr.rule_rank = 1
            JOIN Suggested_Roles r ON fdr.rule_logic = r.assignment_rule
        """)
        raw_exceptions = cursor.fetchall()

        # Enrich Identity State for Risk Scoring
        cursor.execute("""
            SELECT identity_id, attribute_name, attribute_value
            FROM Identity_Attributes_Filtered
            WHERE LOWER(attribute_name) IN ('identitystate', 'status', 'state', 'startdate', 'hiredate')
        """)
        user_state_rows = cursor.fetchall()
        user_states = {}
        user_start_dates = {}
        for row in user_state_rows:
            uid = str(row["identity_id"]).strip()
            attr = str(row["attribute_name"]).strip().lower()
            val = str(row["attribute_value"]).strip().upper()
            if attr in ('identitystate', 'status', 'state'):
                user_states[uid] = val
            elif attr in ('startdate', 'hiredate'):
                user_start_dates[uid] = val

        # Exception Classifications
        critical_inactive_exceptions = []
        new_hire_gaps = []
        mover_exceptions = []

        today = date.today()
        for exc in raw_exceptions:
            uid = str(exc["identity_id"]).strip()
            state = user_states.get(uid, "ACTIVE")
            
            if state in ("INACTIVE", "TERMINATED", "DISABLED", "FALSE"):
                critical_inactive_exceptions.append(exc)
            elif exc["exception_type"] == "MISSING_ACCESS":
                new_hire_gaps.append(exc)
            else:
                mover_exceptions.append(exc)

        cursor.close()
        db_connection.close()

        return baseline, biz_roles, it_roles, critical_inactive_exceptions, new_hire_gaps, mover_exceptions

    except Error as e:
        print(f"❌ Database error loading dashboard metrics: {e}")
        sys.exit(1)


def escape(val):
    return html.escape(str(val) if val is not None else "")


# ==============================================================================
# 3. PDF DASHBOARD COMPILATION ENGINE
# ==============================================================================
def generate_dashboard_pdf(baseline, biz_roles, it_roles, inactives, new_hires, movers, filename=OUTPUT_PDF):
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
    s_title = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=colors.HexColor("#0f172a"))
    s_sub = ParagraphStyle("S", fontName="Helvetica", fontSize=8.5, leading=11, textColor=colors.HexColor("#64748b"), spaceAfter=6)
    s_h1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=colors.HexColor("#0f172a"), spaceBefore=10, spaceAfter=4)
    s_h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#1e293b"), spaceBefore=6, spaceAfter=3)

    s_cell = ParagraphStyle("C", fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#1e293b"))
    s_cell_bold = ParagraphStyle("CB", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.HexColor("#0f172a"))
    s_cell_center = ParagraphStyle("CC", fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#1e293b"), alignment=1)
    s_th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7.2, leading=9, textColor=colors.white, alignment=1)
    
    s_kpi_num = ParagraphStyle("KN", fontName="Helvetica-Bold", fontSize=14, leading=16, alignment=1)
    s_kpi_label = ParagraphStyle("KL", fontName="Helvetica-Bold", fontSize=6.8, leading=8.5, textColor=colors.HexColor("#64748b"), alignment=1)

    story = []

    # Aggregated Rollups
    total_biz_governed_grants = sum(r.get("governed_grants", 0) for r in biz_roles)
    avg_biz_confidence = (sum(float(r["avg_jaccard_score"]) for r in biz_roles) / len(biz_roles)) if biz_roles else 1.0
    avg_it_cohesion = (sum(float(r["bundle_cohesion_score"]) for r in it_roles) / len(it_roles)) if it_roles else 1.0
    total_it_permissions_bundled = sum(r["entitlements_count"] for r in it_roles)
    total_it_full_holders = sum(r["full_holders_count"] for r in it_roles)

    # --------------------------------------------------------------------------
    # PAGE 1: EXECUTIVE KPI SCORECARD & STRATEGIC HIGHLIGHTS
    # --------------------------------------------------------------------------
    story.append(Paragraph("Executive Identity Governance & Role Mining Dashboard", s_title))
    story.append(Paragraph(f"Database: <b>bundleBuilder</b> | Scope: <b>Dual-Pillar Architecture (Business & IT Roles)</b> | Status: <b>AUDITED</b>", s_sub))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=8))

    # Master KPI Grid (2x3)
    kpi_grid = [
        [
            Paragraph("<font color='#0369a1'>" + f"{total_biz_governed_grants:,}" + "</font>", s_kpi_num),
            Paragraph("<font color='#16a34a'>" + f"{len(biz_roles)}" + "</font>", s_kpi_num),
            Paragraph("<font color='#4f46e5'>" + f"{len(it_roles)}" + "</font>", s_kpi_num),
            Paragraph("<font color='#ca8a04'>" + f"{len(new_hires):,}" + "</font>", s_kpi_num),
            Paragraph("<font color='#dc2626'>" + f"{len(inactives):,}" + "</font>", s_kpi_num),
        ],
        [
            Paragraph("<b>GOVERNED BIRTHRIGHT GRANTS</b><br/>Automated by Business Roles", s_kpi_label),
            Paragraph("<b>BUSINESS ROLES MINED</b><br/>HR-Driven Birthright Models", s_kpi_label),
            Paragraph("<b>IT ACCESS PROFILES MINED</b><br/>Functional Application Bundles", s_kpi_label),
            Paragraph("<b>PENDING ONBOARDING GAPS</b><br/>Under-Provisioned Users (Grant)", s_kpi_label),
            Paragraph("<b>CRITICAL RISK (INACTIVE USERS)</b><br/>Orphaned Access (Revoke Now)", s_kpi_label),
        ]
    ]
    t_kpi_master = Table(kpi_grid, colWidths=[100, 100, 104, 100, 100])
    t_kpi_master.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 5),
    ]))
    story.append(t_kpi_master)
    story.append(Spacer(1, 8))

    # --------------------------------------------------------------------------
    # DUAL-PILLAR COMPARISON TABLE
    # --------------------------------------------------------------------------
    story.append(Paragraph("1. Dual-Pillar Role Architecture Overview", s_h1))
    
    dual_pillar_data = [
        [
            Paragraph("<b>Role Architecture Pillar</b>", s_th),
            Paragraph("<b>Core Driving Mechanism</b>", s_th),
            Paragraph("<b>Mined Roles</b>", s_th),
            Paragraph("<b>Total Permissions</b>", s_th),
            Paragraph("<b>Governed Volume</b>", s_th),
            Paragraph("<b>Quality Benchmark</b>", s_th),
        ],
        [
            Paragraph("<b>🏛️ Business Roles (Birthright)</b>", s_cell),
            Paragraph("HR Attributes (Title, Dept, Location)", s_cell),
            Paragraph(f"<b>{len(biz_roles)} roles</b>", s_cell_center),
            Paragraph(f"{sum(r['total_entitlements_count'] for r in biz_roles):,} permissions", s_cell_center),
            Paragraph(f"<b>{total_biz_governed_grants:,} grants</b>", s_cell_center),
            Paragraph(f"<font color='#16a34a'><b>{avg_biz_confidence*100:.1f}% Match</b></font>", s_cell_center),
        ],
        [
            Paragraph("<b>🛠️ IT Roles (Functional Profiles)</b>", s_cell),
            Paragraph("Peer Co-occurrence & Application Usage", s_cell),
            Paragraph(f"<b>{len(it_roles)} bundles</b>", s_cell_center),
            Paragraph(f"{total_it_permissions_bundled:,} permissions", s_cell_center),
            Paragraph(f"<b>{total_it_full_holders:,} baseline users</b>", s_cell_center),
            Paragraph(f"<font color='#4f46e5'><b>{avg_it_cohesion*100:.1f}% Cohesion</b></font>", s_cell_center),
        ]
    ]
    t_pillar = Table(dual_pillar_data, colWidths=[125, 145, 60, 64, 60, 50])
    t_pillar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_pillar)
    story.append(Spacer(1, 8))

    # --------------------------------------------------------------------------
    # TOP BUSINESS ROLES TABLE
    # --------------------------------------------------------------------------
    story.append(Paragraph("2. Top Strategic Business Roles (Ranked by Governed Grants)", s_h1))
    
    top_biz_data = [[
        Paragraph("<b>Business Role Name</b>", s_th),
        Paragraph("<b>HR Membership Rule</b>", s_th),
        Paragraph("<b>Target Users</b>", s_th),
        Paragraph("<b>Bundled Ents</b>", s_th),
        Paragraph("<b>Governed Grants</b>", s_th),
        Paragraph("<b>Confidence</b>", s_th),
    ]]

    for r in biz_roles[:7]:
        top_biz_data.append([
            Paragraph(f"<b>{escape(r['role_name'])}</b>", s_cell),
            Paragraph(f"<code>{escape(r['assignment_rule'])}</code>", s_cell),
            Paragraph(f"<b>{r['target_population']:,}</b>", s_cell_center),
            Paragraph(f"{r['total_entitlements_count']} items", s_cell_center),
            Paragraph(f"<font color='#0369a1'><b>{r['governed_grants']:,}</b></font>", s_cell_center),
            Paragraph(f"<b>{float(r['avg_jaccard_score'])*100:.1f}%</b>", s_cell_center),
        ])

    t_top_biz = Table(top_biz_data, colWidths=[130, 160, 54, 55, 60, 45], repeatRows=1)
    t_top_biz.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_top_biz)
    
    # PAGE 2: IT ROLES & REMEDIATION ACTION PLAN
    story.append(PageBreak())

    # --------------------------------------------------------------------------
    # TOP IT FUNCTIONAL ROLES TABLE
    # --------------------------------------------------------------------------
    story.append(Paragraph("3. Top Strategic IT Functional Roles (Access Profiles)", s_h1))
    
    top_it_data = [[
        Paragraph("<b>IT Functional Role Name</b>", s_th),
        Paragraph("<b>Primary Application</b>", s_th),
        Paragraph("<b>Permissions</b>", s_th),
        Paragraph("<b>Full Holders (100%)</b>", s_th),
        Paragraph("<b>Partial Candidates</b>", s_th),
        Paragraph("<b>Cluster Cohesion</b>", s_th),
    ]]

    for r in it_roles[:7]:
        top_it_data.append([
            Paragraph(f"<b>{escape(r['it_role_name'])}</b>", s_cell),
            Paragraph(f"<font color='#64748b'>{escape(r['primary_source'])}</font>", s_cell),
            Paragraph(f"<b>{r['entitlements_count']} items</b>", s_cell_center),
            Paragraph(f"<font color='#16a34a'><b>{r['full_holders_count']:,} users</b></font>", s_cell_center),
            Paragraph(f"<font color='#ca8a04'><b>{r['partial_holders_count']:,} users</b></font>", s_cell_center),
            Paragraph(f"<b>{float(r['bundle_cohesion_score'])*100:.1f}%</b>", s_cell_center),
        ])

    t_top_it = Table(top_it_data, colWidths=[140, 110, 60, 70, 74, 50], repeatRows=1)
    t_top_it.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#312e81")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_top_it)
    story.append(Spacer(1, 8))

    # --------------------------------------------------------------------------
    # 4. ACTIONABLE REMEDIATION & RISK TRIAGE QUEUE
    # --------------------------------------------------------------------------
    story.append(Paragraph("4. Strategic Governance Remediation & Risk Matrix", s_h1))

    remediation_matrix = [
        [
            Paragraph("<b>Risk / Action Stream</b>", s_th),
            Paragraph("<b>Impacted Population</b>", s_th),
            Paragraph("<b>Primary Root Cause</b>", s_th),
            Paragraph("<b>Standard Workflow Recommendation</b>", s_th),
        ],
        [
            Paragraph("<font color='#dc2626'><b>🔴 Critical Orphaned Access</b></font>", s_cell),
            Paragraph(f"<b>{len(inactives):,} assignments</b>", s_cell_center),
            Paragraph("Terminated/Disabled employees retaining entitlements", s_cell),
            Paragraph("<font color='#dc2626'><b>CERTIFY or REVOKE IMMEDIATELY</b></font>", s_cell),
        ],
        [
            Paragraph("<font color='#ca8a04'><b>🟡 Onboarding Birthright Gaps</b></font>", s_cell),
            Paragraph(f"<b>{len(new_hires):,} assignments</b>", s_cell_center),
            Paragraph("New hires matching HR rule but missing birthright access", s_cell),
            Paragraph("<font color='#16a34a'><b>BULK GRANT (Automated Role Assignment)</b></font>", s_cell),
        ],
        [
            Paragraph("<font color='#ea580c'><b>🟠 Department Movers / Drift</b></font>", s_cell),
            Paragraph(f"<b>{len(movers):,} assignments</b>", s_cell_center),
            Paragraph("Transferred workers holding legacy departmental access", s_cell),
            Paragraph("<font color='#ea580c'><b>CERTIFY or REVOKE (Manager Review)</b></font>", s_cell),
        ]
    ]
    t_rem = Table(remediation_matrix, colWidths=[120, 80, 154, 150])
    t_rem.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t_rem)

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Generated Complete Executive Dashboard: {filename}")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    baseline, biz_roles, it_roles, inactives, new_hires, movers = load_executive_dashboard_data()
    generate_dashboard_pdf(baseline, biz_roles, it_roles, inactives, new_hires, movers, OUTPUT_PDF)
