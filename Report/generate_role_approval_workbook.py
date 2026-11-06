#!/usr/bin/env python3
"""
bundleBuilder - Interactive Role Approval Excel Workbook Generator
Builds the multi-sheet staging workbook with:
  • 5-Action Resolution Dropdown (KEEP_AS_SUGGESTED, SEPARATE, MAKE_DYNAMIC, CERTIFY, IGNORE)
  • Parent & Dynamic Sub-Tier visual grouping and indentation
  • Assigned owners, heatmaps, entitlement inclusions, and lookup references.
"""

import os
import sys
import mysql.connector
from mysql.connector import Error
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Utils.config import open_connection, close_db_connection, DB_CONFIG

OUTPUT_EXCEL = os.path.join("Report", "Role_Mining_Admin_Approval_Workbook.xlsx")


def order_roles_with_dynamic_subtiers(roles_rows):
    """
    Orders Suggested_Roles so that any DYNAMIC_SUB_TIER rows appear immediately
    underneath their parent DYNAMIC_PARENT role.
    """
    parents = []
    subtiers_by_parent = {}

    for r in roles_rows:
        p_id = r.get("parent_role_id")
        if p_id:
            subtiers_by_parent.setdefault(p_id, []).append(r)
        else:
            parents.append(r)

    ordered = []
    for p in parents:
        ordered.append(p)
        children = subtiers_by_parent.get(p["id"], [])
        for c in children:
            ordered.append(c)

    return ordered


def generate_approval_workbook(output_path=OUTPUT_EXCEL):
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            sys.exit(1)
        cur = conn.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder. Extracting staging data...")

        # 1. Fetch Business Roles (excluding IGNORED roles)
        cur.execute("""
            SELECT 
                id, role_name, approval_status, resolution_action, hierarchy_type,
                parent_role_id, dimension_attribute, dimension_value,
                deploy_target, approved_role_name, owner_id, owner_name,
                description, assignment_rule, target_population,
                exact_entitlements_count, fuzzy_entitlements_count,
                total_entitlements_count, avg_jaccard_score, admin_notes
            FROM Suggested_Roles
            WHERE approval_status != 'IGNORED'
            ORDER BY total_entitlements_count DESC, target_population DESC
        """)
        raw_biz_roles = cur.fetchall()
        biz_roles = order_roles_with_dynamic_subtiers(raw_biz_roles)

        # 2. Fetch Business Role Entitlements
        cur.execute("""
            SELECT 
                sre.id, sre.role_id, sr.role_name, sre.entitlement_id,
                sre.entitlement_name, sre.source_name, sre.match_type,
                sre.already_in_role, sre.is_included, sre.jaccard_score,
                sre.missing_users_count, sre.extra_users_count, sre.admin_notes
            FROM Suggested_Role_Entitlements sre
            JOIN Suggested_Roles sr ON sre.role_id = sr.id
            WHERE sr.approval_status != 'IGNORED'
            ORDER BY sre.role_id, sre.jaccard_score DESC
        """)
        biz_ents = cur.fetchall()

        # 3. Fetch IT Roles
        cur.execute("""
            SELECT 
                id, it_role_name, approval_status, deploy_target, approved_role_name,
                owner_id, owner_name, primary_source, description, entitlements_count,
                full_holders_count, partial_holders_count, bundle_cohesion_score, admin_notes
            FROM Suggested_IT_Roles
            ORDER BY entitlements_count DESC, full_holders_count DESC
        """)
        it_roles = cur.fetchall()

        # 4. Fetch IT Role Entitlements
        cur.execute("""
            SELECT 
                sire.id, sire.it_role_id, sir.it_role_name, sire.entitlement_id,
                sire.entitlement_name, sire.source_name, sire.assignment_count,
                sire.already_in_role, sire.is_included, sire.admin_notes
            FROM Suggested_IT_Role_Entitlements sire
            JOIN Suggested_IT_Roles sir ON sire.it_role_id = sir.id
            ORDER BY sire.it_role_id, sire.assignment_count DESC
        """)
        it_ents = cur.fetchall()

        # 5. Fetch Identity Lookups
        cur.execute("SELECT id, COALESCE(displayName, name) AS full_name FROM Identities_Filtered ORDER BY full_name LIMIT 5000")
        identities_lookup = cur.fetchall()

        wb = openpyxl.Workbook()
        wb.remove(wb.active)  # Remove default sheet

        # Styles
        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=10)
        parent_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        subtier_fill = PatternFill(start_color="F2F4F8", end_color="F2F4F8", fill_type="solid")
        thin_border = Border(
            left=Side(style="thin", color="D9D9D9"),
            right=Side(style="thin", color="D9D9D9"),
            top=Side(style="thin", color="D9D9D9"),
            bottom=Side(style="thin", color="D9D9D9"),
        )

        # ======================================================================
        # SHEET 1: Business_Roles_Review (With 5 Actions & Dynamic Sub-Tiers)
        # ======================================================================
        ws_br = wb.create_sheet(title="Business_Roles_Review")
        ws_br["A1"] = "🏛️ BUSINESS ROLES & DYNAMIC HIERARCHY REVIEW"
        ws_br["A1"].font = Font(size=14, bold=True, color="1F4E78")
        ws_br["A2"] = "Select Approval Decision (Col A) and Resolution Action (Col O: KEEP_AS_SUGGESTED, SEPARATE, MAKE_DYNAMIC, CERTIFY, IGNORE). Add reasons in Col N."

        br_headers = [
            "Approval_Decision",       # Col 1 (A)
            "Deploy_Target",           # Col 2 (B)
            "Role_ID",                 # Col 3 (C)
            "Suggested_Role_Name",     # Col 4 (D)
            "Approved_Name_Override",  # Col 5 (E)
            "Owner_Name",              # Col 6 (F)
            "Owner_GUID",              # Col 7 (G)
            "Assignment_Rule",         # Col 8 (H)
            "Target_Population",       # Col 9 (I)
            "Total_Entitlements",      # Col 10 (J)
            "Exact_Entitlements",      # Col 11 (K)
            "Fuzzy_Entitlements",      # Col 12 (L)
            "Avg_Jaccard",             # Col 13 (M)
            "Admin_Notes_Reason",      # Col 14 (N)
            "Resolution_Action",       # Col 15 (O) <-- 5-Action Dropdown
            "Hierarchy_Type",          # Col 16 (P) <-- STANDARD, DYNAMIC_PARENT, DYNAMIC_SUB_TIER
            "Parent_Role_ID",          # Col 17 (Q) <-- Links Sub-Tiers to Parent
            "Dimension_Criteria",      # Col 18 (R) <-- Sub-Tier Dimension
        ]

        for col_idx, text in enumerate(br_headers, start=1):
            cell = ws_br.cell(row=4, column=col_idx, value=text)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        for idx, r in enumerate(biz_roles, start=5):
            h_type = r.get("hierarchy_type") or "STANDARD"
            parent_id = r.get("parent_role_id")
            dim_attr = r.get("dimension_attribute")
            dim_val = r.get("dimension_value")

            display_role_name = r["role_name"]
            if h_type == "DYNAMIC_SUB_TIER":
                display_role_name = f"   ↳ [SUB-TIER: {dim_attr}={dim_val}] {r['role_name']}"

            parent_label = f"BR-{int(parent_id):04d}" if parent_id else "—"
            dim_label = f"{dim_attr} = '{dim_val}'" if dim_attr and dim_val else "—"

            row_vals = [
                r.get("approval_status") or "PENDING_REVIEW",
                r.get("deploy_target") or "BOTH",
                f"BR-{int(r['id']):04d}",
                display_role_name,
                r.get("approved_role_name") or "",
                r.get("owner_name") or "",
                r.get("owner_id") or "",
                r.get("assignment_rule") or "",
                r.get("target_population") or 0,
                r.get("total_entitlements_count") or 0,
                r.get("exact_entitlements_count") or 0,
                r.get("fuzzy_entitlements_count") or 0,
                float(r.get("avg_jaccard_score") or 1.0),
                r.get("admin_notes") or "",
                r.get("resolution_action") or "KEEP_AS_SUGGESTED",
                h_type,
                parent_label,
                dim_label,
            ]

            for col_idx, val in enumerate(row_vals, start=1):
                c = ws_br.cell(row=idx, column=col_idx, value=val)
                c.border = thin_border
                if h_type == "DYNAMIC_PARENT":
                    c.fill = parent_fill
                    if col_idx in (3, 4, 15, 16):
                        c.font = Font(bold=True)
                elif h_type == "DYNAMIC_SUB_TIER":
                    c.fill = subtier_fill
                    if col_idx == 4:
                        c.font = Font(italic=True, color="333333")

        # Add Dropdown Validations on Business_Roles_Review
        if len(biz_roles) > 0:
            max_r = len(biz_roles) + 4
            dv_status = DataValidation(type="list", formula1='"APPROVED,REJECTED,PENDING_REVIEW,PENDING_CERTIFICATION,IGNORED"', allow_blank=True)
            dv_target = DataValidation(type="list", formula1='"BOTH,ISC_CLOUD,IIQ_ONPREM,SKIP"', allow_blank=True)
            dv_action = DataValidation(type="list", formula1='"KEEP_AS_SUGGESTED,SEPARATE,MAKE_DYNAMIC,CERTIFY,IGNORE"', allow_blank=True)

            ws_br.add_data_validation(dv_status)
            ws_br.add_data_validation(dv_target)
            ws_br.add_data_validation(dv_action)

            dv_status.add(f"A5:A{max_r}")
            dv_target.add(f"B5:B{max_r}")
            dv_action.add(f"O5:O{max_r}")

        # ======================================================================
        # SHEET 2: Business_Role_Entitlements
        # ======================================================================
        ws_be = wb.create_sheet(title="Business_Role_Entitlements")
        be_headers = [
            "Include", "Role_ID", "Role_Name", "Source_Name", "Entitlement_ID",
            "Entitlement_Name", "Match_Type", "Already_In_Role", "Jaccard_Score",
            "Missing_Users", "Extra_Users", "Admin_Notes"
        ]
        for col_idx, text in enumerate(be_headers, start=1):
            c = ws_be.cell(row=4, column=col_idx, value=text)
            c.fill = header_fill
            c.font = header_font

        for idx, e in enumerate(biz_ents, start=5):
            vals = [
                "YES" if e.get("is_included", 1) == 1 else "NO",
                f"BR-{int(e['role_id']):04d}",
                e.get("role_name") or "",
                e.get("source_name") or "",
                e.get("entitlement_id") or "",
                e.get("entitlement_name") or "",
                e.get("match_type") or "",
                "YES" if e.get("already_in_role") == 1 else "NO",
                float(e.get("jaccard_score") or 1.0),
                e.get("missing_users_count") or 0,
                e.get("extra_users_count") or 0,
                e.get("admin_notes") or "",
            ]
            for col_idx, val in enumerate(vals, start=1):
                ws_be.cell(row=idx, column=col_idx, value=val).border = thin_border

        # ======================================================================
        # SHEET 3: IT_Roles_Review
        # ======================================================================
        ws_itr = wb.create_sheet(title="IT_Roles_Review")
        itr_headers = [
            "Approval_Decision", "Deploy_Target", "IT_Role_ID", "Suggested_IT_Role_Name",
            "Approved_Name_Override", "Owner_Name", "Owner_GUID", "Primary_Source",
            "Entitlements_Count", "Full_Holders", "Partial_Holders", "Cohesion_Score", "Admin_Notes"
        ]
        for col_idx, text in enumerate(itr_headers, start=1):
            c = ws_itr.cell(row=4, column=col_idx, value=text)
            c.fill = header_fill
            c.font = header_font

        for idx, r in enumerate(it_roles, start=5):
            vals = [
                r.get("approval_status") or "PENDING_REVIEW",
                r.get("deploy_target") or "BOTH",
                f"ITR-{int(r['id']):04d}",
                r.get("it_role_name") or "",
                r.get("approved_role_name") or "",
                r.get("owner_name") or "",
                r.get("owner_id") or "",
                r.get("primary_source") or "",
                r.get("entitlements_count") or 0,
                r.get("full_holders_count") or 0,
                r.get("partial_holders_count") or 0,
                float(r.get("bundle_cohesion_score") or 1.0),
                r.get("admin_notes") or "",
            ]
            for col_idx, val in enumerate(vals, start=1):
                ws_itr.cell(row=idx, column=col_idx, value=val).border = thin_border

        # ======================================================================
        # SHEET 4: IT_Role_Entitlements
        # ======================================================================
        ws_ite = wb.create_sheet(title="IT_Role_Entitlements")
        ite_headers = [
            "Include", "IT_Role_ID", "IT_Role_Name", "Entitlement_Name",
            "Source_Name", "Entitlement_ID", "Assignment_Count", "Already_In_Role", "Admin_Notes"
        ]
        for col_idx, text in enumerate(ite_headers, start=1):
            c = ws_ite.cell(row=4, column=col_idx, value=text)
            c.fill = header_fill
            c.font = header_font

        for idx, e in enumerate(it_ents, start=5):
            vals = [
                "YES" if e.get("is_included", 1) == 1 else "NO",
                f"ITR-{int(e['it_role_id']):04d}",
                e.get("it_role_name") or "",
                e.get("entitlement_name") or "",
                e.get("source_name") or "",
                e.get("entitlement_id") or "",
                e.get("assignment_count") or 0,
                "YES" if e.get("already_in_role") == 1 else "NO",
                e.get("admin_notes") or "",
            ]
            for col_idx, val in enumerate(vals, start=1):
                ws_ite.cell(row=idx, column=col_idx, value=val).border = thin_border

        # ======================================================================
        # SHEET 5: _Lookups_Reference
        # ======================================================================
        ws_lk = wb.create_sheet(title="_Lookups_Reference")
        ws_lk.append(["Identity_UID", "Full_Name"])
        for ident in identities_lookup:
            ws_lk.append([ident["id"], ident["full_name"]])

        # Auto-fit column widths across sheets
        for sheet in wb.worksheets:
            for col in sheet.columns:
                col_letter = get_column_letter(col[0].column)
                max_len = max((len(str(cell.value or "")) for cell in col[:200]), default=12)
                sheet.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 55)

        wb.save(output_path)
        print(f"✅ Success! Generated Approval Workbook with 5-Action Resolution & Dynamic Sub-Tiers at: '{output_path}'")

    except Error as e:
        print(f"❌ Database error generating workbook: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)


if __name__ == "__main__":
    generate_approval_workbook()
