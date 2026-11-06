#!/usr/bin/env python3
"""
bundleBuilder - Enriched Suggested Business Roles PDF Generator
Fades out entitlements already in the approved role model into light gray,
spotlighting net-new suggestions in vivid color.
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

OUTPUT_PDF = "Suggested_Business_Roles_Catalog_Report.pdf"

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


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
        self.drawString(54, 750, "bundleBuilder | Suggested Business Role Scorecard (Delta View)")
        self.drawRightString(558, 750, "CONFIDENTIAL & PROPRIETARY")
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        self.line(54, 44, 558, 44)
        self.drawString(54, 32, f"Evaluation Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Scope: Net-New vs. Approved Delta")
        self.drawRightString(558, 32, f"Page {self._pageNumber} of {page_count}")
        self.restoreState()


def parse_hire_date(date_str):
    if not date_str:
        return None, "Unknown"
    clean_str = str(date_str).strip()
    formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d"]
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
    else:
        return f"<b>{date_formatted}</b><br/><font color='#64748b'>[{days_ago:,}d ago]</font>"


def load_full_role_and_identity_data():
    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.")

        # 1. Fetch IT Role Linkages
        cursor.execute("""
            SELECT itre.entitlement_name, itr.id AS it_role_id, itr.it_role_name 
            FROM Suggested_IT_Role_Entitlements itre
            JOIN Suggested_IT_Roles itr ON itre.it_role_id = itr.id
        """)
        it_role_linkage = defaultdict(list)
        for row in cursor.fetchall():
            it_role_linkage[row["entitlement_name"].strip().lower()].append(row)

        # 2. Fetch Suggested Business Roles
        cursor.execute("""
            SELECT id, role_name, description, assignment_rule, target_population,
                   exact_entitlements_count, fuzzy_entitlements_count, total_entitlements_count, avg_jaccard_score
            FROM Suggested_Roles
            ORDER BY total_entitlements_count DESC, target_population DESC
        """)
        roles = cursor.fetchall()

        # 3. Fetch Business Role Entitlements (Including already_in_role column)
        cursor.execute("""
            SELECT role_id, entitlement_id, entitlement_name, source_name,
                   match_type, jaccard_score, missing_users_count, extra_users_count,
                   already_in_role
            FROM Suggested_Role_Entitlements
        """)
        ent_rows = cursor.fetchall()
        role_ents_map = defaultdict(list)
        for e in ent_rows:
            ent_norm = e["entitlement_name"].strip().lower()
            it_links = it_role_linkage.get(ent_norm, [])
            if it_links:
                e["it_role_id_str"] = f"ITR-{it_links[0]['it_role_id']:04d}"
                e["it_role_name"] = it_links[0]["it_role_name"]
            else:
                e["it_role_id_str"] = None
                e["it_role_name"] = "Standalone"

            role_ents_map[e["role_id"]].append(e)

        # 4. Fetch Enriched Identity Profiles
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
            full_name = f"{first} {last}".strip() or a.get("displayname", uid)
            state_raw = a.get("identitystate", a.get("status", a.get("state", "ACTIVE"))).upper()
            hire_date_raw = a.get("startdate", a.get("hiredate", a.get("start_date", a.get("hire_date", None))))
            days_ago, date_formatted = parse_hire_date(hire_date_raw)

            identity_profiles[uid] = {
                "uid": uid,
                "name": full_name,
                "title": a.get("jobtitle", a.get("title", "Unknown Title")),
                "department": a.get("department", a.get("dept", "Unknown Dept")),
                "manager": a.get("manager", a.get("managername", "Not Listed")),
                "state_clean": "ACTIVE" if state_raw in ("ACTIVE", "TRUE", "ENABLED") else state_raw,
                "state_badge": "<font color='#16a34a'><b>[🟢 ACTIVE]</b></font>" if state_raw in ("ACTIVE", "TRUE") else "<font color='#dc2626'><b>[🔴 INACTIVE]</b></font>",
                "days_ago": days_ago,
                "hire_date_formatted": date_formatted,
                "is_new_hire": (days_ago is not None and 0 <= days_ago <= 30)
            }

        # 5. Fetch Exceptions
        cursor.execute("""
            SELECT r.id as role_id, fdr.entitlement_name, fre.identity_id, fre.exception_type
            FROM Suggested_Roles r
            JOIN Fuzzy_Discovered_Rules fdr ON r.assignment_rule = fdr.rule_logic AND fdr.rule_rank = 1
            JOIN Fuzzy_Rule_Exceptions fre ON fdr.id = fre.rule_id
        """)
        exception_rows = cursor.fetchall()
        role_missing_users = defaultdict(list)
        role_extra_users = defaultdict(list)

        for row in exception_rows:
            rid = row["role_id"]
            uid = str(row["identity_id"]).strip()
            ent_name = row["entitlement_name"]
            profile = identity_profiles.get(uid, {"uid": uid, "name": uid, "title": "Unknown", "department": "Unknown", "manager": "Not Listed", "state_clean": "UNKNOWN", "state_badge": "[UNKNOWN]", "days_ago": None, "hire_date_formatted": "Unknown", "is_new_hire": False})
            exc_item = {"profile": profile, "entitlement_name": ent_name}
            if row["exception_type"] == "MISSING_ACCESS":
                role_missing_users[rid].append(exc_item)
            else:
                role_extra_users[rid].append(exc_item)

        cursor.close()
        db_connection.close()
        return roles, role_ents_map, identity_profiles, role_missing_users, role_extra_users

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


def escape(val):
    return html.escape(str(val) if val is not None else "")


def generate_pdf(roles, role_ents_map, identity_profiles, role_missing_users, role_extra_users, filename=OUTPUT_PDF):
    doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()

    s_role_title = ParagraphStyle("RT", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor("#0f172a"))
    s_role_meta = ParagraphStyle("RM", fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#64748b"), spaceAfter=5)
    s_h2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=colors.HexColor("#1e293b"), spaceBefore=7, spaceAfter=3)
    s_h3_red = ParagraphStyle("H3R", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor("#b91c1c"), spaceBefore=6, spaceAfter=2)
    s_h3_amber = ParagraphStyle("H3A", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=colors.HexColor("#b45309"), spaceBefore=6, spaceAfter=2)

    s_cell = ParagraphStyle("C", fontName="Helvetica", fontSize=6.5, leading=8.2, textColor=colors.HexColor("#1e293b"))
    s_cell_bold = ParagraphStyle("CB", fontName="Helvetica-Bold", fontSize=6.5, leading=8.2, textColor=colors.HexColor("#0f172a"))
    s_cell_center = ParagraphStyle("CC", fontName="Helvetica", fontSize=6.5, leading=8.2, textColor=colors.HexColor("#1e293b"), alignment=1)
    s_th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=6.8, leading=8.5, textColor=colors.white, alignment=1)
    
    s_cell_faded = ParagraphStyle("CF", fontName="Helvetica", fontSize=6.5, leading=8.2, textColor=colors.HexColor("#94a3b8"))
    s_cell_faded_center = ParagraphStyle("CFC", fontName="Helvetica", fontSize=6.5, leading=8.2, textColor=colors.HexColor("#94a3b8"), alignment=1)
    s_rule_box = ParagraphStyle("RB", fontName="Courier-Bold", fontSize=7.5, leading=9.5, textColor=colors.HexColor("#0369a1"))
    s_notice = ParagraphStyle("NT", fontName="Helvetica-Oblique", fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))

    story = []
    total_roles = len(roles)
    print(f"📄 Rendering {total_roles} Business Roles with Delta Fading into PDF...")

    for idx, role in enumerate(roles, start=1):
        role_id = role["id"]
        role_name = role["role_name"]
        target_pop = role["target_population"]
        raw_ents = role_ents_map.get(role_id, [])

        # Sort: Net-New proposals first, then Existing in Prod
        sorted_ents = sorted(raw_ents, key=lambda e: (e.get("already_in_role", 0), -float(e["jaccard_score"]), e["entitlement_name"]))

        missing_list = role_missing_users.get(role_id, [])
        extra_list = role_extra_users.get(role_id, [])
        total_governed_assignments = sum(max(0, target_pop - e["missing_users_count"]) for e in sorted_ents)

        # A. ROLE HEADER & METRICS
        story.append(Paragraph(f"<b>Role {idx} of {total_roles}:</b> {escape(role_name)}", s_role_title))
        story.append(Paragraph(f"Role ID: <b>BR-{role_id:04d}</b> | Overall Confidence: <b>{float(role['avg_jaccard_score'])*100:.1f}% Jaccard</b> | Status: <b>DELTA REVIEW</b>", s_role_meta))
        story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#0284c7"), spaceAfter=4))

        kpi_table_data = [
            [Paragraph("<b>Target Cohort</b>", s_cell_center), Paragraph("<b>Bundled Entitlements</b>", s_cell_center), Paragraph("<b>Governed Grants</b>", s_cell_center), Paragraph("<b>Exact / Fuzzy</b>", s_cell_center), Paragraph("<b>Avg Match Quality</b>", s_cell_center)],
            [Paragraph(f"<b>{target_pop:,} users</b>", s_cell_center), Paragraph(f"<b>{role['total_entitlements_count']} items</b>", s_cell_center), Paragraph(f"<font color='#0369a1'><b>{total_governed_assignments:,} grants</b></font>", s_cell_center), Paragraph(f"<font color='#16a34a'><b>{role['exact_entitlements_count']}</b></font> / <font color='#ca8a04'><b>{role['fuzzy_entitlements_count']}</b></font>", s_cell_center), Paragraph(f"<b>{float(role['avg_jaccard_score'])*100:.1f}%</b>", s_cell_center)]
        ]
        t_kpi = Table(kpi_table_data, colWidths=[95, 105, 114, 95, 95])
        t_kpi.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_kpi)
        story.append(Spacer(1, 4))

        rule_box_data = [[Paragraph("<b>Automated Rule:</b>", s_cell_bold), Paragraph(f"<code>{escape(role['assignment_rule'])}</code>", s_rule_box)]]
        t_rule = Table(rule_box_data, colWidths=[110, 394])
        t_rule.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f9ff")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bae6fd")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_rule)
        story.append(Spacer(1, 4))

        # B. BUNDLED ENTITLEMENTS TABLE WITH DELTA FADING
        story.append(Paragraph("<b>Bundled Entitlements & Delta Status (Faded = Already in Prod):</b>", s_h2))

        ent_rows_table = [[
            Paragraph("<b>Proposal Status</b>", s_th),
            Paragraph("<b>Entitlement Name</b>", s_th),
            Paragraph("<b>Source App</b>", s_th),
            Paragraph("<b>Associated IT Role</b>", s_th),
            Paragraph("<b>Cohort Coverage</b>", s_th),
            Paragraph("<b>Jaccard</b>", s_th),
            Paragraph("<b>Missing<br/>(Grant)</b>", s_th),
            Paragraph("<b>Extra<br/>(Revoke)</b>", s_th),
        ]]

        for ent in sorted_ents:
            is_already = bool(ent.get("already_in_role", False))
            jaccard_val = float(ent["jaccard_score"]) * 100
            missing_cnt = ent["missing_users_count"]
            extra_cnt = ent["extra_users_count"]

            cohort_holders = max(0, target_pop - missing_cnt)
            cov_pct = (cohort_holders / target_pop * 100.0) if target_pop > 0 else 100.0

            if is_already:
                # FADED STYLING FOR EXISTING PERMISSIONS
                badge_p = Paragraph("<font color='#94a3b8'><b>⚪ IN PROD ROLE</b></font>", s_cell_faded)
                ent_name_p = Paragraph(f"<font color='#94a3b8'>{escape(ent['entitlement_name'])}</font>", s_cell_faded)
                source_p = Paragraph(f"<font color='#94a3b8'>{escape(ent['source_name'])}</font>", s_cell_faded)
                it_role_p = Paragraph(f"<font color='#94a3b8'>[{ent['it_role_id_str'] or 'Direct'}]</font>", s_cell_faded)
                cov_p = Paragraph(f"{cov_pct:.0f}% ({cohort_holders}/{target_pop})", s_cell_faded_center)
                jaccard_p = Paragraph(f"{jaccard_val:.1f}%", s_cell_faded_center)
                missing_p = Paragraph(f"{missing_cnt}", s_cell_faded_center)
                extra_p = Paragraph(f"{extra_cnt}", s_cell_faded_center)
            else:
                # VIVID STYLING FOR NET-NEW PROPOSALS
                if missing_cnt == 0 and extra_cnt == 0:
                    badge_label = "✨ NEW (100% BIRTHRIGHT)"
                    badge_color = "#16a34a"
                elif missing_cnt == 0:
                    badge_label = "✨ NEW (100% ADOPTED)"
                    badge_color = "#3f6212"
                else:
                    badge_label = f"✨ NEW PROPOSAL ({jaccard_val:.0f}%)"
                    badge_color = "#ea580c"

                badge_p = Paragraph(f"<b><font color='{badge_color}'>{badge_label}</font></b>", s_cell)
                ent_name_p = Paragraph(f"<b>{escape(ent['entitlement_name'])}</b>", s_cell)
                source_p = Paragraph(f"<font color='#64748b'>{escape(ent['source_name'])}</font>", s_cell)
                it_role_p = Paragraph(f"<font color='#4338ca'><b>🛠️ [{ent['it_role_id_str']}]</b></font><br/>{escape(ent['it_role_name'])}" if ent["it_role_id_str"] else "<font color='#64748b'><i>Standalone</i></font>", s_cell)
                
                cov_str = f"<font color='#16a34a'><b>🟢 100% ({cohort_holders}/{target_pop})</b></font>" if cov_pct >= 100.0 else f"<font color='#ca8a04'><b>🟡 {cov_pct:.1f}% ({cohort_holders}/{target_pop})</b></font>"
                cov_p = Paragraph(cov_str, s_cell_center)
                jaccard_p = Paragraph(f"<b>{jaccard_val:.1f}%</b>", s_cell_center)
                missing_p = Paragraph(f"<font color='{'#dc2626' if missing_cnt > 0 else '#16a34a'}'><b>{missing_cnt}</b></font>", s_cell_center)
                extra_p = Paragraph(f"<font color='{'#dc2626' if extra_cnt > 0 else '#16a34a'}'><b>{extra_cnt}</b></font>", s_cell_center)

            ent_rows_table.append([badge_p, ent_name_p, source_p, it_role_p, cov_p, jaccard_p, missing_p, extra_p])

        t_ents = Table(ent_rows_table, colWidths=[90, 95, 54, 105, 65, 33, 31, 31], repeatRows=1)
        t_ents.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(t_ents)
        story.append(Spacer(1, 6))

        # C. EXCEPTION ROSTERS
        story.append(Paragraph("<b>⚠️ Section A: Missing Users (Under-Provisioned — Recommended for Grant)</b>", s_h3_amber))
        if not missing_list:
            story.append(Paragraph("<i>✅ No under-provisioned users found. All eligible users hold the required entitlements.</i>", s_notice))
        else:
            missing_table_data = [[Paragraph("<b>Identity & State</b>", s_th), Paragraph("<b>HR Context & Org</b>", s_th), Paragraph("<b>Start Date & Tenure</b>", s_th), Paragraph("<b>Missing Entitlement</b>", s_th), Paragraph("<b>Recommended Action</b>", s_th)]]
            for item in missing_list:
                p = item["profile"]
                tenure_badge = format_tenure_badge(p["days_ago"], p["hire_date_formatted"])
                action_p = Paragraph("<font color='#16a34a'><b>🟢 GRANT ACCESS</b></font><br/><font color='#64748b'>(Pending Onboarding)</font>" if p["is_new_hire"] else "<font color='#16a34a'><b>🟢 GRANT ACCESS</b></font><br/><font color='#64748b'>(Birthright Access Gap)</font>", s_cell)
                missing_table_data.append([
                    Paragraph(f"{p['state_badge']}<br/><b>{escape(p['name'])}</b><br/><font color='#64748b'>UID: {escape(p['uid'])}</font>", s_cell),
                    Paragraph(f"<b>Title:</b> {escape(p['title'])}<br/><b>Dept:</b> {escape(p['department'])}<br/><b>Mgr:</b> {escape(p['manager'])}", s_cell),
                    Paragraph(tenure_badge, s_cell),
                    Paragraph(f"<b>{escape(item['entitlement_name'])}</b>", s_cell),
                    action_p
                ])
            t_missing = Table(missing_table_data, colWidths=[105, 115, 95, 95, 94], repeatRows=1)
            t_missing.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b45309")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fffbeb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_missing)

        story.append(Spacer(1, 6))

        story.append(Paragraph("<b>🛑 Section B: Extra Users (Over-Provisioned — Recommended for Remediation)</b>", s_h3_red))
        if not extra_list:
            story.append(Paragraph("<i>✅ No over-provisioned users found. No rogue access detected outside the membership rule.</i>", s_notice))
        else:
            extra_table_data = [[Paragraph("<b>Identity & State</b>", s_th), Paragraph("<b>Current HR Context</b>", s_th), Paragraph("<b>Start Date & Tenure</b>", s_th), Paragraph("<b>Rogue Entitlement</b>", s_th), Paragraph("<b>Recommended Action</b>", s_th)]]
            for item in extra_list:
                p = item["profile"]
                tenure_badge = format_tenure_badge(p["days_ago"], p["hire_date_formatted"])
                action_p = Paragraph("<font color='#dc2626'><b>🔴 CERTIFY or REVOKE IMMEDIATELY</b></font><br/><font color='#64748b'>(Terminated Identity)</font>" if p["state_clean"] in ("INACTIVE", "TERMINATED") else "<font color='#ea580c'><b>🟠 CERTIFY or REVOKE</b></font><br/><font color='#64748b'>(Transferred / Mover)</font>", s_cell)
                extra_table_data.append([
                    Paragraph(f"{p['state_badge']}<br/><b>{escape(p['name'])}</b><br/><font color='#64748b'>UID: {escape(p['uid'])}</font>", s_cell),
                    Paragraph(f"<b>Title:</b> {escape(p['title'])}<br/><b>Dept:</b> {escape(p['department'])}<br/><b>Mgr:</b> {escape(p['manager'])}", s_cell),
                    Paragraph(tenure_badge, s_cell),
                    Paragraph(f"<b>{escape(item['entitlement_name'])}</b>", s_cell),
                    action_p
                ])
            t_extra = Table(extra_table_data, colWidths=[105, 115, 95, 95, 94], repeatRows=1)
            t_extra.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b91c1c")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fef2f2")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_extra)

        if idx < total_roles:
            story.append(PageBreak())

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Generated Complete Delta Business Role Catalog: {filename}")


if __name__ == "__main__":
    roles, role_ents_map, identity_profiles, role_missing_users, role_extra_users = load_full_role_and_identity_data()
    if not roles:
        print("⚠️ No suggested roles found in `Suggested_Roles`. Please run `synthesize_suggested_roles.py` first.")
        sys.exit(0)

    generate_pdf(roles, role_ents_map, identity_profiles, role_missing_users, role_extra_users, OUTPUT_PDF)
