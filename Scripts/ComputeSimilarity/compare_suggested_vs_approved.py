#!/usr/bin/env python3
"""
bundleBuilder - Suggested vs. Approved Role Model Comparator (Robust Schema Introspection)
Dynamically inspects table columns to compare Suggested_Roles vs Approved & Current Roles,
and accurately populates already_defined and already_in_role flags.
"""

import os
import sys
import re
import json
import mysql.connector
from mysql.connector import Error

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


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


def ensure_columns_exist(db_connection.:
    cursor = db_connection.cursor()
    try:
        cursor.execute("""
            ALTER TABLE `Suggested_Roles`
            ADD COLUMN IF NOT EXISTS `already_defined` BOOLEAN NOT NULL DEFAULT FALSE AFTER `approval_status`
        """)
        cursor.execute("""
            ALTER TABLE `Suggested_Role_Entitlements`
            ADD COLUMN IF NOT EXISTS `already_in_role` BOOLEAN NOT NULL DEFAULT FALSE AFTER `match_type`
        """)
        cursor.execute("""
            ALTER TABLE `Suggested_IT_Role_Entitlements`
            ADD COLUMN IF NOT EXISTS `already_in_role` BOOLEAN NOT NULL DEFAULT FALSE AFTER `assignment_count`
        """)
        db_connection.commit()
    except Error as e:
        print(f"⚠️ DDL notice: {e}")
    finally:
        cursor.close()


def get_table_columns(cursor. table_name):
    """Returns a set of lowercase column names present in a table."""
    try:
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
        return {row["Field"].lower() for row in cursor.fetchall()}
    except Error:
        return set()


def extract_canonical_rule_set(rule_str):
    """
    Parses complex rule strings (SQL, JSON, Beanshell) into a canonical frozenset of (attr, val) pairs.
    """
    if not rule_str:
        return frozenset()

    clean_str = str(rule_str).strip()
    pairs = set()

    # 1. Try JSON parser
    if clean_str.startswith("{") or clean_str.startswith("["):
        try:
            data = json.loads(clean_str)
            if isinstance(data, dict):
                attr = data.get("attribute") or data.get("name") or data.get("property")
                val = data.get("value") or data.get("val")
                if attr and val:
                    pairs.add((str(attr).strip().lower(), str(val).strip().lower()))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        attr = item.get("attribute") or item.get("name")
                        val = item.get("value")
                        if attr and val:
                            pairs.add((str(attr).strip().lower(), str(val).strip().lower()))
        except Exception:
            pass

    # 2. Standard SQL Equality Matches: attr = 'val' or attr == "val"
    eq_matches = re.findall(r"([a-zA-Z0-9_\.]+)\s*(?:==|=|eq)\s*['\"]([^'\"]+)['\"]", clean_str, re.IGNORECASE)
    for attr, val in eq_matches:
        attr_clean = attr.split(".")[-1].strip().lower()
        pairs.add((attr_clean, val.strip().lower()))

    # 3. SQL IN clauses: attr IN ('val1', 'val2')
    in_matches = re.findall(r"([a-zA-Z0-9_\.]+)\s+IN\s*\(([^)]+)\)", clean_str, re.IGNORECASE)
    for attr, vals_raw in in_matches:
        attr_clean = attr.split(".")[-1].strip().lower()
        vals = re.findall(r"['\"]([^'\"]+)['\"]", vals_raw)
        for v in vals:
            pairs.add((attr_clean, v.strip().lower()))

    # 4. Beanshell / Java method calls: attr.equalsIgnoreCase("val")
    java_matches = re.findall(r"([a-zA-Z0-9_\.]+)\.equalsIgnoreCase\(['\"]([^'\"]+)['\"]\)", clean_str, re.IGNORECASE)
    for attr, val in java_matches:
        attr_clean = attr.split(".")[-1].strip().lower()
        pairs.add((attr_clean, val.strip().lower()))

    return frozenset(pairs)


def normalize_str(val):
    if val is None:
        return ""
    return str(val).strip().lower()


def load_all_production_rules(cursor.:
    """Loads and canonicalizes all production assignment rules with dynamic column detection."""
    canonical_rule_sets = set()
    raw_exact_strings = set()

    # 1. Check ApprovedRoleModel_Roles
    armr_cols = get_table_columns(cursor. "ApprovedRoleModel_Roles")
    if "assignment_rule" in armr_cols:
        cursor.execute("SELECT assignment_rule FROM ApprovedRoleModel_Roles WHERE assignment_rule IS NOT NULL AND TRIM(assignment_rule) != ''")
        for r in cursor.fetchall():
            raw_exact_strings.add(normalize_str(r["assignment_rule"]))
            parsed = extract_canonical_rule_set(r["assignment_rule"])
            if parsed:
                canonical_rule_sets.add(parsed)

    # 2. Check CurrentRoleModel_Roles (Dynamic column detection)
    crmr_cols = get_table_columns(cursor. "CurrentRoleModel_Roles")
    rule_col = None
    if "assignmentcriteria" in crmr_cols:
        rule_col = "assignmentCriteria"
    elif "assignment_rule" in crmr_cols:
        rule_col = "assignment_rule"
    elif "selector" in crmr_cols:
        rule_col = "selector"

    if rule_col:
        cursor.execute(f"SELECT `{rule_col}` AS rule_text FROM CurrentRoleModel_Roles WHERE `{rule_col}` IS NOT NULL AND TRIM(`{rule_col}`) != ''")
        for r in cursor.fetchall():
            raw_exact_strings.add(normalize_str(r["rule_text"]))
            parsed = extract_canonical_rule_set(r["rule_text"])
            if parsed:
                canonical_rule_sets.add(parsed)

    return canonical_rule_sets, raw_exact_strings


def run_comparison_pipeline():
    print("=" * 85)
    print("🔍 ENHANCED ROLE MODEL DELTA COMPARATOR (DYNAMIC SCHEMA INTROSPECTION)")
    print("=" * 85)

    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        ensure_columns_exist(db_connection.
        cursor = db_connection.cursor(dictionary=True)
        update_cur = db_connection.cursor()
        print("🔗 Connected to MySQL bundleBuilder.\n")

        # ======================================================================
        # 1. COMPARE BUSINESS ROLE ASSIGNMENT RULES (ROLE LEVEL)
        # ======================================================================
        print("🏛️ [1/3] Evaluating Suggested Business Role Assignment Rules...")
        canonical_prod_rules, raw_prod_rules = load_all_production_rules(cursor.
        print(f"   • Loaded {len(canonical_prod_rules):,} canonical rule definitions from production tables.")

        cursor.execute("SELECT id, role_name, assignment_rule FROM Suggested_Roles")
        suggested_roles = cursor.fetchall()

        role_updates = []
        matched_role_examples = []
        roles_already_defined = 0
        roles_net_new = 0

        for r in suggested_roles:
            r_id = r["id"]
            rule_str = r["assignment_rule"]
            rule_norm = normalize_str(rule_str)
            rule_canonical = extract_canonical_rule_set(rule_str)

            is_defined = False
            if rule_norm in raw_prod_rules:
                is_defined = True
            elif rule_canonical and rule_canonical in canonical_prod_rules:
                is_defined = True

            if is_defined:
                role_updates.append((1, r_id))
                roles_already_defined += 1
                if len(matched_role_examples) < 5:
                    matched_role_examples.append(f"Role [BR-{r_id:04d} / {r['role_name']}] -> Rule: {rule_str}")
            else:
                role_updates.append((0, r_id))
                roles_net_new += 1

        sql_update_role = "UPDATE Suggested_Roles SET already_defined = %s WHERE id = %s"
        chunk_size = 5000
        for i in range(0, len(role_updates), chunk_size):
            update_cur.executemany(sql_update_role, role_updates[i:i + chunk_size])

        # ======================================================================
        # 2. COMPARE BUSINESS ROLE ENTITLEMENTS (ENTITLEMENT LEVEL)
        # ======================================================================
        print("\n🔑 [2/3] Comparing Business Role Entitlements...")
        
        approved_biz_ents_rows = []
        if "ApprovedRoleModel_RoleEntitlements" in [t["TABLE_NAME"] for t in (cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"), cursor.fetchall())[-1]]:
            cursor.execute("SELECT role_id, role_name, entitlement_id, entitlement_name FROM ApprovedRoleModel_RoleEntitlements")
            approved_biz_ents_rows = cursor.fetchall()

        if not approved_biz_ents_rows:
            # Fallback to CurrentRoleModel
            crm_tables = [t["TABLE_NAME"] for t in (cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"), cursor.fetchall())[-1]]
            if "CurrentRoleModel_RoleEffectiveEntitlements" in crm_tables:
                cursor.execute("SELECT role_id, role_name, entitlement_id, entitlement_name FROM CurrentRoleModel_RoleEffectiveEntitlements")
                approved_biz_ents_rows = cursor.fetchall()
            elif "CurrentRoleModel_RoleEntitlements" in crm_tables:
                cursor.execute("SELECT role_id, role_name, entitlement_id, entitlement_name FROM CurrentRoleModel_RoleEntitlements")
                approved_biz_ents_rows = cursor.fetchall()

        approved_biz_set = set()
        for r in approved_biz_ents_rows:
            r_id = normalize_str(r.get("role_id"))
            r_name = normalize_str(r.get("role_name"))
            e_id = normalize_str(r.get("entitlement_id"))
            e_name = normalize_str(r.get("entitlement_name"))
            if r_id and e_name: approved_biz_set.add((r_id, e_name))
            if r_name and e_name: approved_biz_set.add((r_name, e_name))
            if r_id and e_id: approved_biz_set.add((r_id, e_id))
            if r_name and e_id: approved_biz_set.add((r_name, e_id))

        cursor.execute("SELECT id, role_name FROM Suggested_Roles")
        biz_role_meta = {r["id"]: {"name": normalize_str(r["role_name"])} for r in cursor.fetchall()}

        cursor.execute("SELECT id, role_id, entitlement_id, entitlement_name FROM Suggested_Role_Entitlements")
        suggested_biz_ents = cursor.fetchall()

        biz_ent_updates = []
        biz_flagged_existing = 0
        biz_flagged_new = 0

        for e in suggested_biz_ents:
            row_id = e["id"]
            r_id_int = e["role_id"]
            r_meta = biz_role_meta.get(r_id_int, {"name": ""})

            role_keys = [normalize_str(r_id_int), f"br-{r_id_int:04d}", r_meta["name"]]
            role_keys = [k for k in role_keys if k]
            ent_keys = [normalize_str(e.get("entitlement_name")), normalize_str(e.get("entitlement_id"))]
            ent_keys = [k for k in ent_keys if k]

            is_match = any((rk, ek) in approved_biz_set for rk in role_keys for ek in ent_keys)
            if is_match:
                biz_ent_updates.append((1, row_id))
                biz_flagged_existing += 1
            else:
                biz_ent_updates.append((0, row_id))
                biz_flagged_new += 1

        sql_update_biz_ent = "UPDATE Suggested_Role_Entitlements SET already_in_role = %s WHERE id = %s"
        for i in range(0, len(biz_ent_updates), chunk_size):
            update_cur.executemany(sql_update_biz_ent, biz_ent_updates[i:i + chunk_size])

        # ======================================================================
        # 3. COMPARE IT ROLE ENTITLEMENTS (IT LEVEL)
        # ======================================================================
        print("🛠️ [3/3] Comparing IT Role Entitlements...")
        approved_it_rows = []
        all_tables = [t["TABLE_NAME"] for t in (cursor.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()"), cursor.fetchall())[-1]]

        if "ApprovedRoleModel_AccessProfileEntitlements" in all_tables:
            cursor.execute("SELECT access_profile_id, access_profile_name, entitlement_id, entitlement_name FROM ApprovedRoleModel_AccessProfileEntitlements")
            approved_it_rows = cursor.fetchall()

        if not approved_it_rows and "CurrentRoleModel_AccessProfileEntitlements" in all_tables:
            cursor.execute("SELECT access_profile_id, access_profile_name, entitlement_id, entitlement_name FROM CurrentRoleModel_AccessProfileEntitlements")
            approved_it_rows = cursor.fetchall()

        approved_it_set = set()
        for r in approved_it_rows:
            ap_id = normalize_str(r.get("access_profile_id"))
            ap_name = normalize_str(r.get("access_profile_name"))
            e_id = normalize_str(r.get("entitlement_id"))
            e_name = normalize_str(r.get("entitlement_name"))
            if ap_id and e_name: approved_it_set.add((ap_id, e_name))
            if ap_name and e_name: approved_it_set.add((ap_name, e_name))
            if ap_id and e_id: approved_it_set.add((ap_id, e_id))
            if ap_name and e_id: approved_it_set.add((ap_name, e_id))

        cursor.execute("SELECT id, it_role_name FROM Suggested_IT_Roles")
        it_role_meta = {r["id"]: {"name": normalize_str(r["it_role_name"])} for r in cursor.fetchall()}

        cursor.execute("SELECT id, it_role_id, entitlement_id, entitlement_name FROM Suggested_IT_Role_Entitlements")
        suggested_it_ents = cursor.fetchall()

        it_ent_updates = []
        it_flagged_existing = 0
        it_flagged_new = 0

        for e in suggested_it_ents:
            row_id = e["id"]
            it_id_int = e["it_role_id"]
            it_meta = it_role_meta.get(it_id_int, {"name": ""})

            it_keys = [normalize_str(it_id_int), f"itr-{it_id_int:04d}", it_meta["name"]]
            it_keys = [k for k in it_keys if k]
            ent_keys = [normalize_str(e.get("entitlement_name")), normalize_str(e.get("entitlement_id"))]
            ent_keys = [k for k in ent_keys if k]

            is_match = any((ik, ek) in approved_it_set for ik in it_keys for ek in ent_keys)
            if is_match:
                it_ent_updates.append((1, row_id))
                it_flagged_existing += 1
            else:
                it_ent_updates.append((0, row_id))
                it_flagged_new += 1

        sql_update_it_ent = "UPDATE Suggested_IT_Role_Entitlements SET already_in_role = %s WHERE id = %s"
        for i in range(0, len(it_ent_updates), chunk_size):
            update_cur.executemany(sql_update_it_ent, it_ent_updates[i:i + chunk_size])

        db_connection.commit()

        # ======================================================================
        # 4. SUMMARY REPORT
        # ======================================================================
        print("\n" + "=" * 85)
        print("📊 CANONICAL COMPARISON RESULTS")
        print("=" * 85)
        print(f"🏛️ Business Roles (Rule Matching) : {len(suggested_roles):,} total evaluated")
        print(f"   • ⚪ Already Defined in Prod   : {roles_already_defined:,} roles (already_defined = 1)")
        print(f"   • ✨ Net-New Business Roles    : {roles_net_new:,} roles (already_defined = 0)")

        if matched_role_examples:
            print("\n   Sample Matched Roles:")
            for ex in matched_role_examples:
                print(f"     ✓ {ex}")

        print(f"\n🔑 Business Role Permissions   : {len(suggested_biz_ents):,} total")
        print(f"   • ⚪ Already in Approved Role  : {biz_flagged_existing:,} items (already_in_role = 1)")
        print(f"   • ✨ Net-New Permission Grants : {biz_flagged_new:,} items (already_in_role = 0)")

        print(f"\n🛠️ IT Role Permissions         : {len(suggested_it_ents):,} total")
        print(f"   • ⚪ Already in Approved AP    : {it_flagged_existing:,} items (already_in_role = 1)")
        print(f"   • ✨ Net-New AP Permissions    : {it_flagged_new:,} items (already_in_role = 0)")
        print("=" * 85)

        update_cur.close()
        cursor.close()
        db_connection.close()
        print("✅ Comparison complete! Both role-level and entitlement-level flags are now synchronized in MySQL.\n")

    except Error as e:
        print(f"❌ Database error during comparison: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_comparison_pipeline()
