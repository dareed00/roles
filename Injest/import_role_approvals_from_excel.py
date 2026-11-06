#!/usr/bin/env python3
"""
bundleBuilder - Excel Staging Ingestion & Approval Synchronizer
Reads the interactive approval workbook, parses admin decisions, name overrides,
assigned owners (GUID + Name), entitlement inclusion flags, and executes the 5 Role Resolution Actions:
  1. KEEP_AS_SUGGESTED : Retains role as a standard/hierarchical role.
  2. SEPARATE          : Splits multi-value OR/IN role into standalone roles, copies entitlements,
                         logs composite rule to Ignored_Suggested_Roles (as SEPARATED), and deletes composite role.
  3. MAKE_DYNAMIC      : Marks role as DYNAMIC_PARENT and auto-creates/links DYNAMIC_SUB_TIER child roles.
  4. CERTIFY           : Flags role as PENDING_CERTIFICATION for owner/manager sign-off.
  5. IGNORE            : Logs role + admin comment to Ignored_Suggested_Roles and marks IGNORED.
"""

import os
import sys
import re
import argparse
import mysql.connector
from mysql.connector import Error
import openpyxl

# ==============================================================================
# DYNAMIC SYSTEM PATH RESOLUTION & UTILS.CONFIG IMPORTS
# ==============================================================================
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Utils.config import open_connection, close_db_connection, DB_CONFIG

DEFAULT_EXCEL = os.path.join("Report", "Role_Mining_Admin_Approval_Workbook.xlsx")

VALID_RESOLUTION_ACTIONS = {
    "KEEP_AS_SUGGESTED",
    "SEPARATE",
    "MAKE_DYNAMIC",
    "CERTIFY",
    "IGNORE",
}


def clean_int_id(raw_id_str):
    """Extracts integer ID from strings like 'BR-0001' or 'ITR-0042'."""
    if not raw_id_str:
        return None
    match = re.search(r'\d+', str(raw_id_str))
    return int(match.group()) if match else None


def parse_multi_value_clauses(assignment_rule_str):
    """
    Extracts individual (attribute_name, attribute_value) pairs from an IN(...) or OR rule.
    Example:
      "Job_Code IN ('1111', '2222')" --> [('Job_Code', '1111'), ('Job_Code', '2222')]
      "(Job_Code = '1111') OR (Job_Code = '2222')" --> [('Job_Code', '1111'), ('Job_Code', '2222')]
    """
    if not assignment_rule_str:
        return []
    rule = str(assignment_rule_str).strip()
    pairs = []

    # Case 1: attr IN ('v1', 'v2', ...)
    in_matches = re.finditer(r"([A-Za-z0-9_\-]+)\s+IN\s*\(([^)]+)\)", rule, flags=re.IGNORECASE)
    for m in in_matches:
        attr_name = m.group(1).strip()
        raw_vals = m.group(2).split(",")
        for rv in raw_vals:
            clean_v = rv.strip().strip("'\"")
            if clean_v:
                pairs.append((attr_name, clean_v))

    if pairs:
        return pairs

    # Case 2: attr = 'v1' OR attr = 'v2'
    eq_matches = re.finditer(r"([A-Za-z0-9_\-]+)\s*=\s*'([^']+)'", rule, flags=re.IGNORECASE)
    for m in eq_matches:
        pairs.append((m.group(1).strip(), m.group(2).strip()))

    return pairs


def load_lookup_fallback_map(wb):
    """Builds a Full Name -> UID lookup map from the _Lookups_Reference sheet."""
    lookup_map = {}
    if "_Lookups_Reference" in wb.sheetnames:
        ws = wb["_Lookups_Reference"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and row[0] and len(row) > 1 and row:
                uid = str(row[0]).strip()
                name = str(row).strip()
                lookup_map[name.lower()] = uid
                lookup_map[uid.lower()] = uid
    return lookup_map


def find_default_report_path():
    candidate_paths = [
        DEFAULT_EXCEL,
        os.path.join("..", "Report", "Role_Mining_Admin_Approval_Workbook.xlsx"),
        "Role_Mining_Admin_Approval_Workbook.xlsx",
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            return p
    return DEFAULT_EXCEL


def resolve_excel_path():
    parser = argparse.ArgumentParser(description="Import role approval decisions and resolution actions from Excel.")
    parser.add_argument("file_path", nargs="?", default=None, help="Path to the Excel approval workbook (.xlsx)")
    parser.add_argument("-f", "--file", dest="flag_path", default=None, help="Explicit file path flag")
    args, _ = parser.parse_known_args()

    chosen_path = args.flag_path or args.file_path or os.getenv("APPROVAL_EXCEL_PATH")
    if not chosen_path:
        default_found = find_default_report_path()
        if os.path.exists(default_found):
            return default_found
        try:
            user_input = input(f"Enter Excel file path [Default: {DEFAULT_EXCEL}]: ").strip()
            chosen_path = user_input if user_input else DEFAULT_EXCEL
        except (EOFError, KeyboardInterrupt):
            print("\nOperation cancelled.")
            sys.exit(0)
    return chosen_path


def handle_separate_action(cur, role_id, final_name, owner_name, owner_uid, deploy_target, notes):
    """
    Executes Option 2 (SEPARATE):
    1. Splits composite rule into standalone single-attribute roles in Suggested_Roles.
    2. Copies included entitlements into each standalone role (allowing overlap).
    3. Records the composite rule in Ignored_Suggested_Roles (as SEPARATED) with reviewer comment.
    4. Deletes the composite role from Suggested_Roles.
    """
    cur.execute("SELECT role_name, assignment_rule FROM Suggested_Roles WHERE id = %s", (role_id,))
    row = cur.fetchone()
    if not row:
        return 0

    orig_role_name, assignment_rule = row[0], row
    clauses = parse_multi_value_clauses(assignment_rule)
    if len(clauses) < 2:
        print(f"   ⚠️ Role ID {role_id} ('{final_name}') has fewer than 2 clauses; keeping as standalone.")
        return 0

    # Fetch included entitlements for the composite role
    cur.execute("""
        SELECT entitlement_id, entitlement_name, source_name, match_type, jaccard_score, missing_users_count, extra_users_count
        FROM Suggested_Role_Entitlements
        WHERE role_id = %s AND is_included = 1
    """, (role_id,))
    included_ents = cur.fetchall()

    split_created = 0
    for attr_name, attr_val in clauses:
        single_rule = f"{attr_name} = '{attr_val}'"
        sub_role_name = f"All {attr_val} ({attr_name}) Users"

        # Check if standalone role for this single clause already exists
        cur.execute("SELECT id FROM Suggested_Roles WHERE TRIM(assignment_rule) = %s LIMIT 1", (single_rule,))
        existing = cur.fetchone()

        if existing:
            target_sub_id = existing[0]
        else:
            # Count matching population from Identity_Attributes_Filtered
            cur.execute("""
                SELECT COUNT(DISTINCT identity_id)
                FROM Identity_Attributes_Filtered
                WHERE attribute_name = %s AND attribute_value = %s
            """, (attr_name, attr_val))
            pop_cnt = (cur.fetchone() or [0])[0]

            cur.execute("""
                INSERT INTO Suggested_Roles
                (role_name, approval_status, resolution_action, hierarchy_type, deploy_target,
                 approved_role_name, owner_id, owner_name, description, assignment_rule,
                 target_population, total_entitlements_count, avg_jaccard_score, admin_notes)
                VALUES (%s, 'APPROVED', 'KEEP_AS_SUGGESTED', 'STANDARD', %s, %s, %s, %s, %s, %s, %s, %s, 1.0000, %s)
            """, (
                sub_role_name[:250],
                deploy_target,
                sub_role_name[:250],
                owner_uid,
                owner_name,
                f"Standalone role separated from composite role '{final_name}' ({single_rule}).",
                single_rule,
                pop_cnt,
                len(included_ents),
                notes or f"Created via SEPARATE action from {final_name}",
            ))
            target_sub_id = cur.lastrowid

            # Populate eligible identities for the new split role
            cur.execute("""
                INSERT INTO Suggested_Role_Identities (role_id, identity_id, status)
                SELECT DISTINCT %s, identity_id, 'ELIGIBLE'
                FROM Identity_Attributes_Filtered
                WHERE attribute_name = %s AND attribute_value = %s
            """, (target_sub_id, attr_name, attr_val))

        # Copy/merge entitlements into the standalone role
        for ent in included_ents:
            e_id, e_name, s_name, m_type, j_score, miss_cnt, extra_cnt = ent
            cur.execute("""
                SELECT id FROM Suggested_Role_Entitlements
                WHERE role_id = %s AND TRIM(entitlement_name) = %s
            """, (target_sub_id, str(e_name).strip()))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO Suggested_Role_Entitlements
                    (role_id, entitlement_id, entitlement_name, source_name, match_type, is_included, jaccard_score, missing_users_count, extra_users_count)
                    VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s)
                """, (target_sub_id, e_id, e_name, s_name, m_type, j_score, miss_cnt, extra_cnt))

        split_created += 1

    # Record composite rule in Ignored_Suggested_Roles so it is never proposed again
    cur.execute("""
        INSERT INTO Ignored_Suggested_Roles
        (assignment_rule_signature, role_name, resolution_type, ignored_by, ignore_reason)
        VALUES (%s, %s, 'SEPARATED', %s, %s)
        ON DUPLICATE KEY UPDATE
            resolution_type = 'SEPARATED',
            ignored_by = VALUES(ignored_by),
            ignore_reason = VALUES(ignore_reason),
            ignored_timestamp = NOW()
    """, (
        assignment_rule.strip()[:500],
        final_name[:250],
        owner_name or "Admin Reviewer",
        notes or f"Separated into {split_created} standalone roles.",
    ))

    # Delete the composite role from Suggested_Roles (cascades to its staging entitlements/identities)
    cur.execute("DELETE FROM Suggested_Roles WHERE id = %s", (role_id,))
    print(f"   ✂️ [SEPARATE] Split '{final_name}' into {split_created} standalone roles and suppressed composite rule.")
    return split_created


def handle_make_dynamic_action(cur, role_id, final_name, owner_name, owner_uid, deploy_target, notes):
    """
    Executes Option 3 (MAKE_DYNAMIC):
    1. Marks the composite role as hierarchy_type = 'DYNAMIC_PARENT'.
    2. Creates or links N child roles with hierarchy_type = 'DYNAMIC_SUB_TIER' and parent_role_id = role_id.
    """
    cur.execute("SELECT assignment_rule FROM Suggested_Roles WHERE id = %s", (role_id,))
    row = cur.fetchone()
    if not row:
        return 0

    assignment_rule = row[0]
    clauses = parse_multi_value_clauses(assignment_rule)

    # Mark parent role as DYNAMIC_PARENT
    cur.execute("""
        UPDATE Suggested_Roles
        SET resolution_action = 'MAKE_DYNAMIC',
            hierarchy_type = 'DYNAMIC_PARENT'
        WHERE id = %s
    """, (role_id,))

    tiers_linked = 0
    for idx, (attr_name, attr_val) in enumerate(clauses, start=1):
        single_rule = f"{attr_name} = '{attr_val}'"
        tier_name = f"{final_name} - Tier {idx} ({attr_name}={attr_val})"

        # Check if a sub-tier or standalone role for this single clause already exists
        cur.execute("""
            SELECT id FROM Suggested_Roles
            WHERE (parent_role_id = %s AND dimension_attribute = %s AND dimension_value = %s)
               OR (TRIM(assignment_rule) = %s AND id != %s)
            LIMIT 1
        """, (role_id, attr_name, attr_val, single_rule, role_id))
        existing_tier = cur.fetchone()

        cur.execute("""
            SELECT COUNT(DISTINCT identity_id)
            FROM Identity_Attributes_Filtered
            WHERE attribute_name = %s AND attribute_value = %s
        """, (attr_name, attr_val))
        tier_pop = (cur.fetchone() or [0])[0]

        if existing_tier:
            cur.execute("""
                UPDATE Suggested_Roles
                SET parent_role_id = %s,
                    hierarchy_type = 'DYNAMIC_SUB_TIER',
                    resolution_action = 'KEEP_AS_SUGGESTED',
                    dimension_attribute = %s,
                    dimension_value = %s,
                    target_population = %s
                WHERE id = %s
            """, (role_id, attr_name, attr_val, tier_pop, existing_tier[0]))
        else:
            cur.execute("""
                INSERT INTO Suggested_Roles
                (role_name, approval_status, resolution_action, hierarchy_type, parent_role_id,
                 dimension_attribute, dimension_value, deploy_target, approved_role_name,
                 owner_id, owner_name, description, assignment_rule, target_population,
                 total_entitlements_count, avg_jaccard_score, admin_notes)
                VALUES (%s, 'APPROVED', 'KEEP_AS_SUGGESTED', 'DYNAMIC_SUB_TIER', %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 1.0000, %s)
            """, (
                tier_name[:250],
                role_id,
                attr_name,
                attr_val,
                deploy_target,
                tier_name[:250],
                owner_uid,
                owner_name,
                f"Dynamic Sub-Tier for parent role '{final_name}' where {single_rule}.",
                single_rule,
                tier_pop,
                notes or f"Auto-generated dynamic sub-tier for {final_name}",
            ))
        tiers_linked += 1

    print(f"   🌐 [MAKE_DYNAMIC] Configured '{final_name}' as Dynamic Parent with {tiers_linked} linked Sub-Tiers.")
    return tiers_linked


def handle_ignore_action(cur, role_id, final_name, owner_name, notes):
    """
    Executes Option 5 (IGNORE):
    1. Records the role's canonical rule and reviewer comment into Ignored_Suggested_Roles.
    2. Marks the role as IGNORED in Suggested_Roles.
    """
    cur.execute("SELECT assignment_rule FROM Suggested_Roles WHERE id = %s", (role_id,))
    row = cur.fetchone()
    if not row:
        return

    assignment_rule = row[0]
    cur.execute("""
        INSERT INTO Ignored_Suggested_Roles
        (assignment_rule_signature, role_name, resolution_type, ignored_by, ignore_reason)
        VALUES (%s, %s, 'IGNORED', %s, %s)
        ON DUPLICATE KEY UPDATE
            resolution_type = 'IGNORED',
            ignored_by = VALUES(ignored_by),
            ignore_reason = VALUES(ignore_reason),
            ignored_timestamp = NOW()
    """, (
        assignment_rule.strip()[:500],
        final_name[:250],
        owner_name or "Admin Reviewer",
        notes or "Ignored by reviewer during Excel workbook inspection.",
    ))

    cur.execute("""
        UPDATE Suggested_Roles
        SET approval_status = 'IGNORED',
            resolution_action = 'IGNORE',
            admin_notes = %s,
            reviewed_timestamp = NOW()
        WHERE id = %s
    """, (notes, role_id))
    print(f"   🚫 [IGNORE] Recorded '{final_name}' in Ignored_Suggested_Roles with comment: '{notes or 'No comment provided'}'.")


def sync_approvals_to_mysql(excel_file):
    excel_file = os.path.expanduser(excel_file.strip("'\""))
    if not os.path.exists(excel_file):
        print(f"\n❌ Error: Excel approval workbook '{excel_file}' could not be found.")
        sys.exit(1)

    print(f"\n📖 Opening '{excel_file}' for staging ingestion...")
    try:
        wb_data = openpyxl.load_workbook(excel_file, data_only=True)
        wb_raw = openpyxl.load_workbook(excel_file, data_only=False)
    except Exception as e:
        print(f"❌ Failed to parse Excel file '{excel_file}': {e}")
        sys.exit(1)

    lookup_fallback = load_lookup_fallback_map(wb_raw)

    biz_roles_updated = 0
    biz_ents_updated = 0
    it_roles_updated = 0
    it_ents_updated = 0

    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            sys.exit(1)
        cur = conn.cursor()
        print("🔗 Connected to MySQL bundleBuilder.")

        # ======================================================================
        # 1. PARSE & UPDATE BUSINESS ENTITLEMENTS FIRST (So SEPARATE copies updated inclusions)
        # ======================================================================
        if "Business_Role_Entitlements" in wb_data.sheetnames:
            print("\n🔑 [1/4] Synchronizing Business Role Entitlement inclusions...")
            ws = wb_data["Business_Role_Entitlements"]

            sql_update_biz_ent = """
                UPDATE `Suggested_Role_Entitlements`
                SET 
                    `is_included` = %s,
                    `admin_notes` = %s,
                    `reviewed_timestamp` = NOW()
                WHERE `role_id` = %s 
                  AND TRIM(`entitlement_name`) = %s
            """

            for row_idx in range(5, ws.max_row + 1):
                raw_include = ws.cell(row=row_idx, column=1).value
                raw_role_id = ws.cell(row=row_idx, column=2).value
                raw_ent_name = ws.cell(row=row_idx, column=6).value
                raw_notes = ws.cell(row=row_idx, column=12).value

                role_id = clean_int_id(raw_role_id)
                if not role_id or not raw_ent_name:
                    continue

                is_included = 1 if str(raw_include or "YES").strip().upper() == "YES" else 0
                ent_name = str(raw_ent_name).strip()
                notes = str(raw_notes or "").strip() if raw_notes else None

                cur.execute(sql_update_biz_ent, (is_included, notes, role_id, ent_name))
                if is_included == 0:
                    sql_exclude_biz = """
                        INSERT INTO `Role_Entitlement_Exclusions` (`role_name`, `entitlement_name`, `source_name`, `declined_by`, `decline_reason`, `is_permanent`)
                        SELECT COALESCE(sr.approved_role_name, sr.role_name), sre.entitlement_name, sre.source_name, %s, %s, TRUE
                        FROM `Suggested_Role_Entitlements` sre
                        JOIN `Suggested_Roles` sr ON sre.role_id = sr.id
                        WHERE sre.role_id = %s AND TRIM(sre.entitlement_name) = %s
                        ON DUPLICATE KEY UPDATE decline_reason = VALUES(decline_reason), decline_timestamp = NOW()
                    """
                    cur.execute(sql_exclude_biz, ('Reviewer', notes or 'Declined in workbook review', role_id, ent_name))
                biz_ents_updated += 1

            print(f"   ✅ Synchronized {biz_ents_updated:,} Business Role Entitlement decisions.")

        # ======================================================================
        # 2. PARSE & UPDATE BUSINESS ROLES + 5 RESOLUTION ACTIONS (Sheet: Business_Roles_Review)
        # ======================================================================
        if "Business_Roles_Review" in wb_data.sheetnames:
            print("\n🏛️ [2/4] Synchronizing Business Roles & Executing Resolution Actions...")
            ws = wb_data["Business_Roles_Review"]

            sql_update_biz = """
                UPDATE `Suggested_Roles`
                SET 
                    `approval_status` = %s,
                    `resolution_action` = %s,
                    `deploy_target` = %s,
                    `approved_role_name` = %s,
                    `owner_name` = %s,
                    `owner_id` = %s,
                    `admin_notes` = %s,
                    `reviewed_timestamp` = NOW()
                WHERE `id` = %s
            """

            for row_idx in range(5, ws.max_row + 1):
                raw_decision = ws.cell(row=row_idx, column=1).value
                raw_target = ws.cell(row=row_idx, column=2).value
                raw_id = ws.cell(row=row_idx, column=3).value
                raw_suggested_name = ws.cell(row=row_idx, column=4).value
                raw_override_name = ws.cell(row=row_idx, column=5).value
                raw_owner_name = ws.cell(row=row_idx, column=6).value
                raw_owner_uid = ws.cell(row=row_idx, column=7).value
                raw_notes = ws.cell(row=row_idx, column=14).value
                raw_res_action = ws.cell(row=row_idx, column=15).value

                role_id = clean_int_id(raw_id)
                if not role_id:
                    continue

                decision = str(raw_decision or "PENDING_REVIEW").strip().upper()
                res_action = str(raw_res_action or "").strip().upper()

                # Support selecting the 5 resolution actions in either Column 15 OR Column 1
                if decision in VALID_RESOLUTION_ACTIONS and not res_action:
                    res_action = decision
                if res_action not in VALID_RESOLUTION_ACTIONS:
                    res_action = "KEEP_AS_SUGGESTED"

                deploy_target = str(raw_target or "BOTH").strip().upper()
                # Strip visual sub-tier prefix if present
                clean_sug_name = re.sub(r"^\s*↳\s*\[SUB-TIER[^\]]*\]\s*", "", str(raw_suggested_name or "")).strip()
                final_name = str(raw_override_name or clean_sug_name or "").strip()
                owner_name = str(raw_owner_name or "").strip()

                owner_uid = str(raw_owner_uid or "").strip()
                if not owner_uid or owner_uid.startswith("=") or "⚠️" in owner_uid:
                    owner_uid = lookup_fallback.get(owner_name.lower(), "IAM-Admins")

                notes = str(raw_notes or "").strip() if raw_notes else None

                # Map status for CERTIFY and IGNORE
                if res_action == "CERTIFY":
                    decision = "PENDING_CERTIFICATION"
                elif res_action == "IGNORE" or decision == "IGNORED":
                    res_action = "IGNORE"
                    decision = "IGNORED"

                # Base update first
                cur.execute(sql_update_biz, (
                    decision,
                    res_action,
                    deploy_target,
                    final_name,
                    owner_name,
                    owner_uid,
                    notes,
                    role_id,
                ))

                # Execute specialized structural actions
                if res_action == "SEPARATE":
                    handle_separate_action(cur, role_id, final_name, owner_name, owner_uid, deploy_target, notes)
                elif res_action == "MAKE_DYNAMIC":
                    handle_make_dynamic_action(cur, role_id, final_name, owner_name, owner_uid, deploy_target, notes)
                elif res_action == "IGNORE":
                    handle_ignore_action(cur, role_id, final_name, owner_name, notes)

                biz_roles_updated += 1

            print(f"   ✅ Synchronized {biz_roles_updated:,} Business Roles.")

        # ======================================================================
        # 3. PARSE & UPDATE IT ROLES (Sheet: IT_Roles_Review)
        # ======================================================================
        if "IT_Roles_Review" in wb_data.sheetnames:
            print("\n🛠️ [3/4] Synchronizing IT Roles / Access Profiles Master decisions...")
            ws = wb_data["IT_Roles_Review"]

            sql_update_it = """
                UPDATE `Suggested_IT_Roles`
                SET 
                    `approval_status` = %s,
                    `deploy_target` = %s,
                    `approved_role_name` = %s,
                    `owner_name` = %s,
                    `owner_id` = %s,
                    `admin_notes` = %s,
                    `reviewed_timestamp` = NOW()
                WHERE `id` = %s
            """

            for row_idx in range(5, ws.max_row + 1):
                raw_decision = ws.cell(row=row_idx, column=1).value
                raw_target = ws.cell(row=row_idx, column=2).value
                raw_id = ws.cell(row=row_idx, column=3).value
                raw_suggested_name = ws.cell(row=row_idx, column=4).value
                raw_override_name = ws.cell(row=row_idx, column=5).value
                raw_owner_name = ws.cell(row=row_idx, column=6).value
                raw_owner_uid = ws.cell(row=row_idx, column=7).value
                raw_notes = ws.cell(row=row_idx, column=13).value

                role_id = clean_int_id(raw_id)
                if not role_id:
                    continue

                decision = str(raw_decision or "PENDING_REVIEW").strip().upper()
                deploy_target = str(raw_target or "BOTH").strip().upper()
                final_name = str(raw_override_name or raw_suggested_name or "").strip()
                owner_name = str(raw_owner_name or "").strip()

                owner_uid = str(raw_owner_uid or "").strip()
                if not owner_uid or owner_uid.startswith("=") or "⚠️" in owner_uid:
                    owner_uid = lookup_fallback.get(owner_name.lower(), "IAM-Admins")

                notes = str(raw_notes or "").strip() if raw_notes else None

                cur.execute(sql_update_it, (
                    decision,
                    deploy_target,
                    final_name,
                    owner_name,
                    owner_uid,
                    notes,
                    role_id
                ))
                it_roles_updated += 1

            print(f"   ✅ Synchronized {it_roles_updated:,} IT Roles.")

        # ======================================================================
        # 4. PARSE & UPDATE IT ENTITLEMENTS (Sheet: IT_Role_Entitlements)
        # ======================================================================
        if "IT_Role_Entitlements" in wb_data.sheetnames:
            print("\n🗄️ [4/4] Synchronizing IT Role Entitlement inclusions...")
            ws = wb_data["IT_Role_Entitlements"]

            sql_update_it_ent = """
                UPDATE `Suggested_IT_Role_Entitlements`
                SET 
                    `is_included` = %s,
                    `admin_notes` = %s,
                    `reviewed_timestamp` = NOW()
                WHERE `it_role_id` = %s 
                  AND TRIM(`entitlement_name`) = %s
            """

            for row_idx in range(5, ws.max_row + 1):
                raw_include = ws.cell(row=row_idx, column=1).value
                raw_role_id = ws.cell(row=row_idx, column=2).value
                raw_ent_name = ws.cell(row=row_idx, column=4).value
                raw_notes = ws.cell(row=row_idx, column=9).value

                role_id = clean_int_id(raw_role_id)
                if not role_id or not raw_ent_name:
                    continue

                is_included = 1 if str(raw_include or "YES").strip().upper() == "YES" else 0
                ent_name = str(raw_ent_name).strip()
                notes = str(raw_notes or "").strip() if raw_notes else None

                cur.execute(sql_update_it_ent, (is_included, notes, role_id, ent_name))
                if is_included == 0:
                    sql_exclude_it = """
                        INSERT INTO `Role_Entitlement_Exclusions` (`role_name`, `entitlement_name`, `source_name`, `declined_by`, `decline_reason`, `is_permanent`)
                        SELECT COALESCE(sr.approved_role_name, sr.it_role_name), sre.entitlement_name, sre.source_name, %s, %s, TRUE
                        FROM `Suggested_IT_Role_Entitlements` sre
                        JOIN `Suggested_IT_Roles` sr ON sre.it_role_id = sr.id
                        WHERE sre.it_role_id = %s AND TRIM(sre.entitlement_name) = %s
                        ON DUPLICATE KEY UPDATE decline_reason = VALUES(decline_reason), decline_timestamp = NOW()
                    """
                    cur.execute(sql_exclude_it, ('Reviewer', notes or 'Declined in workbook review', role_id, ent_name))
                it_ents_updated += 1

            print(f"   ✅ Synchronized {it_ents_updated:,} IT Role Entitlement decisions.")

        conn.commit()

        print("\n" + "=" * 80)
        print("📊 STAGING SYNCHRONIZATION SUMMARY")
        print("=" * 80)
        cur.execute("SELECT resolution_action, COUNT(*) FROM Suggested_Roles GROUP BY resolution_action")
        print("🏛️ Business Roles by Resolution Action:")
        for action, count in cur.fetchall():
            print(f"   • {str(action):<22}: {count:,} roles")

        cur.execute("SELECT resolution_type, COUNT(*) FROM Ignored_Suggested_Roles GROUP BY resolution_type")
        print("\n🚫 Persistently Suppressed Roles (Ignored_Suggested_Roles):")
        for rtype, count in cur.fetchall():
            print(f"   • {str(rtype):<22}: {count:,} roles")

        print(f"\n🎉 Success! Changes from '{excel_file}' are now stored in MySQL bundleBuilder.")

    except Error as e:
        print(f"❌ Database error during Excel sync: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)


if __name__ == "__main__":
    target_path = resolve_excel_path()
    sync_approvals_to_mysql(target_path)
