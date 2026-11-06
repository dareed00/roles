#!/usr/bin/env python3
"""
bundleBuilder - Complete Multi-Source Role Mining & Governance Report
Features:
  - Extracts Attribute-Driven Roles directly from Entitlement_to_Attribute_Correlations (e.g. "All Doctors")
  - Merges with Graph-Discovered Communities (Potential_Roles & Potential_Attribute_Roles)
  - English Pluralization Engine (e.g., "Doctor" -> "All Doctors")
  - Each Mined Role on a Dedicated Page (PageBreak per role)
  - Live Dual-Direction Set Difference (Identities_Filtered vs Entitlement Assignments)
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
OUTPUT_PDF = "All_Mined_Roles_Unified_Report.pdf"

# Minimum Jaccard score to include an entitlement in an attribute-correlated role
MIN_ATTR_CORRELATION_THRESHOLD = 0.50

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
            self.drawString(54, 750, "bundleBuilder | Unified Role Mining & Identity Governance Report")
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
# 3. ENGLISH PLURALIZATION ENGINE
# ==============================================================================
def pluralize_phrase(text):
    """Converts a singular title/persona into a natural plural form."""
    if not text:
        return ""
    text = text.strip()
    words = text.split()
    if not words:
        return ""

    last_word = words[-1]
    lower_last = last_word.lower()

    collective_or_uncountable = {
        "staff", "personnel", "faculty", "police", "people",
        "sales", "operations", "resources", "services", "logistics",
        "analytics", "finance", "legal", "procurement", "marketing",
        "engineering", "it", "security", "data", "software", "hardware",
        "management", "accounting", "admin", "support", "infrastructure",
    }
    if lower_last in collective_or_uncountable:
        return text

    if lower_last.endswith("s") and not lower_last.endswith(("ss", "us", "is")):
        return text

    irregulars = {
        "person": "people", "man": "men", "woman": "women", "child": "children",
        "doctor": "doctors", "nurse": "nurses", "physician": "physicians",
        "analyst": "analysts", "specialist": "specialists", "scientist": "scientists",
        "lead": "leads", "manager": "managers", "director": "directors",
        "officer": "officers", "engineer": "engineers", "developer": "developers",
        "architect": "architects", "administrator": "administrators",
        "consultant": "consultants", "intern": "interns", "representative": "representatives",
        "accountant": "accountants", "technician": "technicians", "coordinator": "coordinators",
        "supervisor": "supervisors", "associate": "associates", "executive": "executives",
        "advisor": "advisors", "adviser": "advisers", "worker": "workers",
        "contractor": "contractors", "employee": "employees", "user": "users", "member": "members",
    }

    if lower_last in irregulars:
        plural_last = irregulars[lower_last]
        if last_word.isupper():
            plural_last = plural_last.upper()
        elif last_word[0].isupper():
            plural_last = plural_last.capitalize()
        words[-1] = plural_last
        return " ".join(words)

    if lower_last.endswith("y") and len(lower_last) > 1 and lower_last[-2] not in "aeiou":
        plural_last = last_word[:-1] + ("IES" if last_word.isupper() else "ies")
    elif lower_last.endswith(("s", "x", "z", "ch", "sh", "ss")):
        plural_last = last_word + ("ES" if last_word.isupper() else "es")
    else:
        plural_last = last_word + ("S" if last_word.isupper() else "s")

    words[-1] = plural_last
    return " ".join(words)


# ==============================================================================
# 4. ROOT-CAUSE DIAGNOSTIC ENGINE
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
# 5. UNIFIED DATA EXTRACTION (ATTRIBUTES + COMMUNITIES)
# ==============================================================================
def fetch_all_data():
    """Extracts attribute-correlated roles and graph community roles into a unified catalog."""
    try:
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
        data = {}

        # 1. Summary Totals
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM Potential_Roles) AS potential_roles_cnt,
                (SELECT COUNT(*) FROM Identities_Filtered) AS id_cnt,
                (SELECT COUNT(*) FROM entitlements) AS ent_cnt,
                (SELECT COUNT(*) FROM Attribute_Populations) AS attr_pop_cnt,
                (SELECT COUNT(DISTINCT attribute_name, attribute_value) FROM Entitlement_to_Attribute_Correlations) AS attr_roles_cnt
        """)
        data["summary"] = cursor.fetchone()

        # 2. Caching Identity Metadata from Identities_Filtered
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

        # 3. Caching Entitlement Assignments
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

        # 4. Caching Attribute-to-Identity Mapping
        cursor.execute("SELECT identity_id, attribute_name, attribute_value FROM Identity_Attributes_Filtered")
        attr_identities_map = defaultdict(set)
        for row in cursor.fetchall():
            attr_key = (row["attribute_name"], row["attribute_value"])
            attr_identities_map[attr_key].add(row["identity_id"])

        # 5. Extracting Entitlement Analysis Profiles (for Delivery Mode Breakdown)
        cursor.execute("SELECT * FROM Entitlement_Analysis_Profile")
        eap_cache = {row["entitlement_name"]: row for row in cursor.fetchall()}

        # ======================================================================
        # PIPELINE A: EXTRACT ATTRIBUTE-CORRELATED ROLES (e.g., jobTitle=Doctor)
        # ======================================================================
        print("🧪 Synthesizing attribute-correlated roles (Entitlement_to_Attribute_Correlations)...")
        cursor.execute("""
            SELECT 
                c.attribute_name,
                c.attribute_value,
                c.entitlement_name,
                c.entitlement_source,
                c.jaccard_score,
                c.entitlement_population,
                c.attribute_population,
                COALESCE(ap.population_size, c.attribute_population) AS resolved_pop_size
            FROM Entitlement_to_Attribute_Correlations c
            LEFT JOIN Attribute_Populations ap 
                   ON c.attribute_name = ap.attribute_name 
                  AND c.attribute_value = ap.attribute_value
            WHERE c.jaccard_score >= %s
            ORDER BY c.attribute_name, c.attribute_value, c.jaccard_score DESC
        """, (MIN_ATTR_CORRELATION_THRESHOLD,))
        
        attr_corr_rows = cursor.fetchall()
        attr_role_groups = defaultdict(list)
        for row in attr_corr_rows:
            key = (row["attribute_name"], row["attribute_value"])
            attr_role_groups[key].append(row)

        unified_roles = []
        role_idx = 1

        for (attr_name, attr_val), rows in attr_role_groups.items():
            plural_name = f"All {pluralize_phrase(attr_val)}"
            avg_jaccard = sum(float(r["jaccard_score"]) for r in rows) / len(rows)
            footprint = rows[0]["resolved_pop_size"]

            # Member entitlements
            role_ents = []
            for r in rows:
                eap = eap_cache.get(r["entitlement_name"], {})
                role_ents.append({
                    "entitlement_name": r["entitlement_name"],
                    "entitlement_source": r.get("entitlement_source") or "N/A",
                    "population_size": r["entitlement_population"],
                    "internal_centrality_score": float(r["jaccard_score"]),  # Attribute correlation acts as centrality
                    "count_direct": eap.get("count_direct", 0),
                    "total_population": eap.get("total_population", r["entitlement_population"]),
                    "count_via_role": eap.get("count_via_role", 0),
                })

            unified_roles.append({
                "role_type": "Attribute-Correlated",
                "role_name": plural_name,
                "primary_criteria": f"<code>{attr_name}</code> = <b>{attr_val}</b>",
                "attribute_name": attr_name,
                "attribute_value": attr_val,
                "community_id": f"Attr:{attr_name[:3]}-{attr_val}",
                "avg_internal_jaccard": avg_jaccard,
                "recommendation_score": avg_jaccard * len(role_ents) * 2.0,
                "user_footprint": footprint,
                "entitlement_count": len(role_ents),
                "entitlements": role_ents,
                "attributes": [{
                    "attribute_name": attr_name,
                    "attribute_value": attr_val,
                    "population_size": footprint,
                    "avg_jaccard": avg_jaccard,
                    "matched_entitlements_count": len(role_ents),
                }],
            })

        # ======================================================================
        # PIPELINE B: MERGE GRAPH-DISCOVERED ROLES (Potential_Roles)
        # ======================================================================
        print("🕸️ Extracting graph-discovered community roles (Potential_Roles)...")
        cursor.execute("""
            SELECT id, community_id, recommendation_score, avg_internal_jaccard, 
                   entitlement_count, user_footprint
            FROM Potential_Roles
            ORDER BY recommendation_score DESC
        """)
        pot_roles = cursor.fetchall()

        for pr in pot_roles:
            pr_id = pr["id"]
            # Fetch member entitlements
            cursor.execute("""
                SELECT 
                    pre.entitlement_name, pre.entitlement_source, pre.population_size, 
                    pre.internal_centrality_score,
                    eap.count_direct, eap.total_population, eap.count_via_role
                FROM Potential_Role_Entitlements pre
                LEFT JOIN Entitlement_Analysis_Profile eap ON pre.entitlement_name = eap.entitlement_name
                WHERE pre.potential_role_id = %s
                ORDER BY pre.internal_centrality_score DESC
            """, (pr_id,))
            p_ents = cursor.fetchall()

            # Correlated attribute lookup
            cursor.execute("""
                SELECT 
                    c.attribute_name, c.attribute_value,
                    COALESCE(ap.population_size, c.attribute_population, 0) AS population_size,
                    AVG(c.jaccard_score) AS avg_jaccard,
                    COUNT(DISTINCT pre.entitlement_name) AS matched_entitlements_count
                FROM Potential_Role_Entitlements pre
                JOIN Entitlement_to_Attribute_Correlations c ON pre.entitlement_name = c.entitlement_name
                LEFT JOIN Attribute_Populations ap 
                       ON c.attribute_name = ap.attribute_name 
                      AND c.attribute_value = ap.attribute_value
                WHERE pre.potential_role_id = %s
                GROUP BY c.attribute_name, c.attribute_value, ap.population_size, c.attribute_population
                ORDER BY avg_jaccard DESC
            """, (pr_id,))
            p_attrs = cursor.fetchall()

            if p_attrs:
                top_a = p_attrs[0]
                role_name = f"All {pluralize_phrase(top_a['attribute_value'])}"
                crit = f"<code>{top_a['attribute_name']}</code> = <b>{top_a['attribute_value']}</b>"
                a_name = top_a["attribute_name"]
                a_val = top_a["attribute_value"]
            else:
                role_name = f"Candidate Community #{pr['community_id']}"
                crit = "<i>Graph Network Modularity</i>"
                a_name = None
                a_val = None

            unified_roles.append({
                "role_type": "Graph-Community",
                "role_name": role_name,
                "primary_criteria": crit,
                "attribute_name": a_name,
                "attribute_value": a_val,
                "community_id": pr["community_id"],
                "avg_internal_jaccard": float(pr["avg_internal_jaccard"]),
                "recommendation_score": float(pr["recommendation_score"]),
                "user_footprint": pr["user_footprint"],
                "entitlement_count": pr["entitlement_count"],
                "entitlements": p_ents,
                "attributes": p_attrs,
            })

        # Sort unified roles by user footprint and recommendation score
        unified_roles.sort(key=lambda r: (r["user_footprint"], r["recommendation_score"]), reverse=True)
        data["roles"] = unified_roles
        print(f"📊 Successfully compiled {len(unified_roles)} unified candidate roles (including all attribute roles).")

        # ======================================================================
        # PIPELINE C: COMPUTE LIVE DUAL-SET DIFFERENCE ON IDENTITIES_FILTERED
        # ======================================================================
        print("⚙️ Executing dual-direction set differences against Identities_Filtered...")
        data["role_variance_users"] = {}

        for r_idx, r in enumerate(unified_roles):
            role_key_id = f"role_{r_idx}"
            a_name = r.get("attribute_name")
            a_val = r.get("attribute_value")
            role_ents = r.get("entitlements", [])

            if a_name and a_val:
                role_identities = set(attr_identities_map.get((a_name, a_val), set()))
            elif role_ents:
                core_ent = role_ents[0]["entitlement_name"]
                role_identities = set(ent_assignments_map.get(core_ent, set()))
            else:
                role_identities = set()

            data["role_variance_users"][role_key_id] = {}

            for e in role_ents:
                ent_name = e["entitlement_name"]
                ent_identities = set(ent_assignments_map.get(ent_name, set()))

                missing_id_set = role_identities - ent_identities
                extra_id_set = ent_identities - role_identities

                if missing_id_set or extra_id_set:
                    missing_user_records = [identity_cache[uid] for uid in missing_id_set if uid in identity_cache]
                    extra_user_records = [identity_cache[uid] for uid in extra_id_set if uid in identity_cache]

                    data["role_variance_users"][role_key_id][ent_name] = {
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
# 6. PDF GENERATION ENGINE
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

    # Typography Styles
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
    story.append(Paragraph("Unified Role Mining & Governance Catalog Report", s_title))
    story.append(Paragraph(f"Database: <b>bundleBuilder</b> | Extracted: {datetime.now().strftime('%B %d, %Y')} | Scope: <b>Attribute Correlations + Community Roles</b>", s_sub))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceAfter=8))

    s = data["summary"]
    total_mined_roles = len(data["roles"])
    kpis = [
        [
            Paragraph("<b>Total Discovered Roles</b>", s_cell),
            Paragraph("<b>Identities Filtered</b>", s_cell),
            Paragraph("<b>Catalog Entitlements</b>", s_cell),
            Paragraph("<b>Attribute Populations</b>", s_cell),
            Paragraph("<b>Correlated Attribute Roles</b>", s_cell),
        ],
        [
            Paragraph(f"<b>{total_mined_roles:,}</b>", s_cell),
            Paragraph(f"<b>{s['id_cnt'] or 0:,}</b>", s_cell),
            Paragraph(f"<b>{s['ent_cnt'] or 0:,}</b>", s_cell),
            Paragraph(f"<b>{s['attr_pop_cnt'] or 0:,}</b>", s_cell),
            Paragraph(f"<font color='#16a34a'><b>{s['attr_roles_cnt'] or 0:,}</b></font>", s_cell),
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
    # MASTER INDEX TABLE (Executive Directory)
    # --------------------------------------------------------------------------
    story.append(Paragraph("Master Index: All Attribute & Community Discovered Roles", s_h1))
    story.append(Paragraph("Complete catalog including attribute-correlated personas (e.g. All Doctors) and graph communities.", s_box))
    story.append(Spacer(1, 4))

    master_rows = [
        [
            Paragraph("<b>#</b>", s_th),
            Paragraph("<b>Mined Role Name</b>", s_th),
            Paragraph("<b>Primary Assignment Criteria</b>", s_th),
            Paragraph("<b>Mining Source</b>", s_th),
            Paragraph("<b>Cohesion</b>", s_th),
            Paragraph("<b>Footprint</b>", s_th),
            Paragraph("<b>Ent. Count</b>", s_th),
        ]
    ]

    for idx, r in enumerate(data["roles"], 1):
        j_pct = float(r["avg_internal_jaccard"]) * 100
        score_color = "#16a34a" if j_pct >= 90 else ("#0284c7" if j_pct >= 75 else "#d97706")
        badge_type = (
            "<font color='#0284c7'><b>Attribute</b></font>"
            if r["role_type"] == "Attribute-Correlated"
            else "<font color='#64748b'>Graph</font>"
        )

        master_rows.append([
            Paragraph(str(idx), s_cell),
            Paragraph(f"<b>{r['role_name']}</b>", s_cell),
            Paragraph(r["primary_criteria"], s_cell),
            Paragraph(badge_type, s_cell),
            Paragraph(f"<font color='{score_color}'><b>{j_pct:.1f}%</b></font>", s_cell),
            Paragraph(f"{r['user_footprint']:,} users", s_cell),
            Paragraph(f"{r['entitlement_count']} items", s_cell),
        ])

    t_master = Table(master_rows, colWidths=[20, 130, 134, 60, 50, 55, 55], repeatRows=1)
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

        role_key_id = f"role_{idx-1}"
        role_footprint = r["user_footprint"]
        jaccard_pct = float(r["avg_internal_jaccard"]) * 100
        rec_score = float(r["recommendation_score"])
        ents = r.get("entitlements", [])
        attrs = r.get("attributes", [])

        # Role Header Banner
        story.append(Paragraph(f"Role #{idx}: {r['role_name']}", s_h2))
        story.append(
            Paragraph(
                f"<b>Mining Source:</b> {r['role_type']} &nbsp;|&nbsp; "
                f"<b>Louvain / Correlation Cohesion:</b> <font color='#16a34a'><b>{jaccard_pct:.1f}%</b></font> &nbsp;|&nbsp; "
                f"<b>Role Footprint:</b> {role_footprint:,} identities &nbsp;|&nbsp; "
                f"<b>Total Entitlements:</b> {r['entitlement_count']} &nbsp;|&nbsp; "
                f"<b>Identifier:</b> {r['community_id']}",
                s_box,
            )
        )
        story.append(Spacer(1, 4))

        # ----------------------------------------------------------------------
        # SUB-SECTION A: CORRELATED ATTRIBUTE POPULATIONS
        # ----------------------------------------------------------------------
        story.append(Paragraph("📋 Correlated Attribute Populations", s_section_sub))
        if attrs:
            attr_rows = [
                [
                    Paragraph("<b>Attribute Name</b>", s_th),
                    Paragraph("<b>Attribute Value</b>", s_th),
                    Paragraph("<b>Attr Pop</b>", s_th),
                    Paragraph("<b>Avg Correlation</b>", s_th),
                    Paragraph("<b>Role Coverage</b>", s_th),
                ]
            ]
            for a in attrs[:4]:
                avg_j_pct = float(a["avg_jaccard"]) * 100
                cov_str = f"{a['matched_entitlements_count']} of {len(ents)} items"
                j_color = "#16a34a" if avg_j_pct >= 90 else "#0284c7"
                attr_rows.append([
                    Paragraph(f"<code>{a['attribute_name']}</code>", s_cell),
                    Paragraph(f"<b>{a['attribute_value']}</b>", s_cell),
                    Paragraph(f"{a['population_size']:,}", s_cell),
                    Paragraph(f"<font color='{j_color}'><b>{avg_j_pct:.1f}%</b></font>", s_cell),
                    Paragraph(cov_str, s_cell),
                ])
            t_attr = Table(attr_rows, colWidths=[100, 154, 75, 85, 90], repeatRows=1)
            t_attr.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_attr)
        else:
            story.append(Paragraph("<i>No statistically correlated attribute populations.</i>", s_cell))

        story.append(Spacer(1, 4))

        # ----------------------------------------------------------------------
        # SUB-SECTION B: ENTITLEMENT COMPOSITION & MATCH STATUS
        # ----------------------------------------------------------------------
        story.append(Paragraph("🧩 Entitlement Composition & Population Match", s_section_sub))
        if ents:
            ent_rows = [
                [
                    Paragraph("<b>Entitlement Name</b>", s_th),
                    Paragraph("<b>Source App</b>", s_th),
                    Paragraph("<b>Ent. Pop</b>", s_th),
                    Paragraph("<b>Role Footprint</b>", s_th),
                    Paragraph("<b>Pop. Match Status</b>", s_th),
                    Paragraph("<b>Verdict</b>", s_th),
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
                    Paragraph(f"<b>{e['entitlement_name']}</b>", s_cell),
                    Paragraph(str(e.get("entitlement_source") or "N/A"), s_cell),
                    Paragraph(str(ent_pop), s_cell),
                    Paragraph(str(role_footprint), s_cell),
                    Paragraph(status_badge, s_cell),
                    Paragraph(f"<font color='{verdict_color}'><b>{verdict}</b></font>", s_cell),
                ])

            t_ent = Table(ent_rows, colWidths=[150, 75, 45, 60, 105, 69], repeatRows=1)
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
            role_var_map = data["role_variance_users"].get(role_key_id, {})
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

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Successfully compiled Unified Role Mining Report with All Attribute Roles: {filename}")


# ==============================================================================
# 7. EXECUTION ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    print("📡 Extracting bundleBuilder database (Entitlement_to_Attribute_Correlations + Potential_Roles)...")
    dataset = fetch_all_data()
    print("📄 Rendering multi-page PDF document...")
    generate_pdf(dataset, OUTPUT_PDF)
