#!/usr/bin/env python3
"""
bundleBuilder - Role Hierarchy Decomposition & Containment Detector
Compares Business Roles against IT Roles / Access Profiles to detect:
  1. 100% Full Containment (IT Role is a pure subset of Business Role)
  2. High Partial Overlap (75% - 99% Containment)
"""

import os
import sys
from collections import defaultdict
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


def detect_role_hierarchy(scope="APPROVED"):
    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor(dictionary=True)
        print(f"🔗 Connected to MySQL bundleBuilder (Scope: {scope})...")

        # 1. Select appropriate tables based on scope
        if scope.upper() == "APPROVED":
            r_table = "ApprovedRoleModel_Roles"
            re_table = "ApprovedRoleModel_RoleEntitlements"
            ap_table = "ApprovedRoleModel_AccessProfiles"
            ape_table = "ApprovedRoleModel_AccessProfileEntitlements"
            role_id_col = "role_id"
            ap_id_col = "access_profile_id"
        else:
            r_table = "Suggested_Roles"
            re_table = "Suggested_Role_Entitlements"
            ap_table = "Suggested_IT_Roles"
            ape_table = "Suggested_IT_Role_Entitlements"
            role_id_col = "role_id"
            ap_id_col = "it_role_id"

        # 2. Load Business Roles & their Entitlements
        cursor.execute(f"SELECT id, name FROM {r_table}" if scope == "APPROVED" else f"SELECT id, role_name as name FROM {r_table}")
        biz_roles = {str(r["id"]): r["name"] for r in cursor.fetchall()}

        cursor.execute(f"SELECT {role_id_col} as role_id, entitlement_id, entitlement_name FROM {re_table}" + (" WHERE is_included = 1" if scope != "APPROVED" else ""))
        biz_ents = defaultdict(dict)
        for row in cursor.fetchall():
            biz_ents[str(row["role_id"])][str(row["entitlement_id"])] = row["entitlement_name"]

        # 3. Load IT Roles & their Entitlements
        cursor.execute(f"SELECT id, name, primary_source FROM {ap_table}" if scope == "APPROVED" else f"SELECT id, it_role_name as name, primary_source FROM {ap_table}")
        it_roles = {str(r["id"]): {"name": r["name"], "source": r["primary_source"]} for r in cursor.fetchall()}

        cursor.execute(f"SELECT {ap_id_col} as ap_id, entitlement_id, entitlement_name FROM {ape_table}" + (" WHERE is_included = 1" if scope != "APPROVED" else ""))
        it_ents = defaultdict(dict)
        for row in cursor.fetchall():
            it_ents[str(row["ap_id"])][str(row["entitlement_id"])] = row["entitlement_name"]

        # 4. Compare all (Business Role, IT Role) Pairs
        print(f"⚙️ Analyzing {len(biz_roles)} Business Roles against {len(it_roles)} IT Access Profiles...")
        
        full_containments = []
        partial_overlaps = []

        for b_id, b_name in biz_roles.items():
            b_set = set(biz_ents.get(b_id, {}).keys())
            if not b_set:
                continue

            for it_id, it_meta in it_roles.items():
                it_name = it_meta["name"]
                it_source = it_meta["source"]
                it_dict = it_ents.get(it_id, {})
                it_set = set(it_dict.keys())
                
                if not it_set:
                    continue

                shared = b_set & it_set
                if not shared:
                    continue

                containment_pct = (len(shared) / len(it_set)) * 100.0
                missing_from_biz = [it_dict[eid] for eid in (it_set - shared)]

                result_record = {
                    "biz_id": b_id,
                    "biz_name": b_name,
                    "it_id": it_id,
                    "it_name": it_name,
                    "it_source": it_source,
                    "shared_count": len(shared),
                    "it_total_count": len(it_set),
                    "biz_total_count": len(b_set),
                    "containment_pct": containment_pct,
                    "missing_permissions": missing_from_biz
                }

                if containment_pct >= 99.9:
                    full_containments.append(result_record)
                elif containment_pct >= 75.0:
                    partial_overlaps.append(result_record)

        # 5. Display Executive Report
        print("\n" + "=" * 95)
        print("🟢 100% FULL CONTAINMENT RELATIONSHIPS (Modularize: Replace loose ents with IT Role)")
        print("=" * 95)
        if not full_containments:
            print("   None found. All business roles hold unique or distinct entitlement combinations.")
        else:
            for idx, r in enumerate(full_containments, 1):
                print(f"[{idx:02d}] 🏛️  Business Role : {r['biz_name']} ({r['biz_id']})")
                print(f"     🛠️  Contains IT Role : {r['it_name']} ({r['it_id']}) - App: {r['it_source']}")
                print(f"     📦 Permissions       : Holds ALL {r['shared_count']} of {r['it_total_count']} permissions in the IT Role.")
                print(f"     💡 Recommendation    : Attach IT Role [{r['it_name']}] to [{r['biz_name']}] & remove {r['shared_count']} direct entitlements.\n")

        print("=" * 95)
        print("🟡 HIGH PARTIAL OVERLAPS (75% - 99% Containment — Review for Alignment)")
        print("=" * 95)
        if not partial_overlaps:
            print("   None found.")
        else:
            for idx, r in enumerate(partial_overlaps[:10], 1):
                print(f"[{idx:02d}] 🏛️  Business Role : {r['biz_name']} ({r['biz_id']})")
                print(f"     🛠️  Overlaps IT Role : {r['it_name']} ({r['it_id']}) - App: {r['it_source']}")
                print(f"     📊 Containment Ratio : {r['shared_count']} of {r['it_total_count']} permissions ({r['containment_pct']:.1f}%)")
                print(f"     ⚠️  Missing from Role: {', '.join(r['missing_permissions'][:3])}" + (f" and {len(r['missing_permissions'])-3} more" if len(r['missing_permissions']) > 3 else ""))
                print(f"     💡 Action            : Consider adding missing permissions to complete the IT bundle.\n")

        cursor.close()
        db_connection.close()

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    scope_param = sys.argv[1] if len(sys.argv) > 1 else "APPROVED"
    detect_role_hierarchy(scope_param)
