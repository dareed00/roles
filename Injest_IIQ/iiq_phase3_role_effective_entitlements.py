#!/usr/bin/env python3
"""
bundleBuilder - IIQ Phase 3: Current Role Model Effective Entitlements
Extracts unique (role_id, role_name, access_profile_id, access_profile_name, entitlement_id, entitlement_name)
effective lineage and populates CurrentRoleModel_RoleEffectiveEntitlements.
"""

import os
import sys
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


IIQ_DB_CONFIG = {
    "host": os.getenv("IIQ_DB_HOST", "localhost"),
    "port": int(os.getenv("IIQ_DB_PORT", 3306)),
    "user": os.getenv("IIQ_DB_USER", "root"),
    "password": os.getenv("IIQ_DB_PASSWORD", "password"),
    "database": os.getenv("IIQ_DB_NAME", "identityiq"),
}

BUNDLE_DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


def run_phase3_role_effective_matrix():
    try:
        print("🔗 Connecting to IIQ Source and bundleBuilder Destination...")
        iiq_conn = mysql.connector.connect(**IIQ_DB_CONFIG)
        iiq_cur = iiq_conn.cursor(dictionary=True)

        dest_conn = mysql.connector.connect(**BUNDLE_DB_CONFIG)
        dest_cur = dest_conn.cursor(dictionary=True)

        # 1. Pre-cache GUID lookups from bundleBuilder
        print("🗺️ Pre-caching GUID lookups for Roles, Access Profiles, and Entitlements...")
        
        dest_cur.execute("SELECT id, name FROM CurrentRoleModel_Roles")
        role_map = {row["name"].strip(): str(row["id"]) for row in dest_cur.fetchall()}

        dest_cur.execute("SELECT id, name FROM CurrentRoleModel_AccessProfiles")
        ap_map = {row["name"].strip(): str(row["id"]) for row in dest_cur.fetchall()}

        dest_cur.execute("SELECT id, entitlement_name, source_name, source_id FROM entitlements")
        ent_rows = dest_cur.fetchall()
        ent_map = {(r["entitlement_name"].strip(), r["source_name"].strip()): (str(r["id"]), str(r["source_id"])) for r in ent_rows}
        ent_name_only_map = {r["entitlement_name"].strip(): (str(r["id"]), str(r["source_id"])) for r in ent_rows}

        # 2. Extract Distinct Role Lineage from IIQ
        print("📡 Extracting distinct effective role mappings from spt_identity_entitlement...")
        iiq_cur.execute("""
            SELECT DISTINCT
                COALESCE(NULLIF(TRIM(ie.assigned_role), ''), 'Unassigned Role') AS assigned_role_name,
                COALESCE(NULLIF(TRIM(ie.granted_by_role), ''), 'Directly Assigned') AS granted_by_role_name,
                ie.value AS entitlement_name,
                app.id AS source_id,
                app.name AS source_name
            FROM spt_identity_entitlement ie
            JOIN spt_application app ON ie.application = app.id
            WHERE ie.source IN ('Role', 'Rule')
              AND ie.value IS NOT NULL AND TRIM(ie.value) != ''
        """)
        lineage_rows = iiq_cur.fetchall()
        print(f"   • Extracted {len(lineage_rows):,} distinct effective Role-to-Entitlement paths.")

        effective_batch = []
        seen_keys = set()

        for r in lineage_rows:
            role_name = r["assigned_role_name"].strip()
            ap_name = r["granted_by_role_name"].strip()
            ent_name = r["entitlement_name"].strip()
            src_name = r["source_name"].strip()
            src_id = str(r["source_id"]).strip()

            # Resolve IDs
            role_id = role_map.get(role_name, f"ROLE-{role_name}")
            ap_id = ap_map.get(ap_name, "AP-DIRECT" if ap_name == "Directly Assigned" else f"AP-{ap_name}")
            
            ent_meta = ent_map.get((ent_name, src_name), ent_name_only_map.get(ent_name, (f"ENT-{ent_name}", src_id)))
            ent_id = ent_meta[0]

            unique_key = (role_id, ap_id, ent_id)
            if unique_key not in seen_keys:
                seen_keys.add(unique_key)
                effective_batch.append((
                    role_id[:250],
                    role_name[:250],
                    ap_id[:250],
                    ap_name[:250],
                    ent_id[:250],
                    ent_name[:250],
                    src_id[:250],
                    src_name[:250]
                ))

        dest_cur.execute("DELETE FROM CurrentRoleModel_RoleEffectiveEntitlements")
        
        sql_effective = """
            INSERT INTO CurrentRoleModel_RoleEffectiveEntitlements 
            (role_id, role_name, access_profile_id, access_profile_name, entitlement_id, entitlement_name, source_id, source_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE mapping_timestamp=CURRENT_TIMESTAMP
        """

        print(f"\n💾 Inserting {len(effective_batch):,} Effective Entitlements with Paired GUIDs into CurrentRoleModel_RoleEffectiveEntitlements...")
        chunk_size = 10000
        for i in range(0, len(effective_batch), chunk_size):
            dest_cur.executemany(sql_effective, effective_batch[i:i + chunk_size])

        dest_conn.commit()
        iiq_cur.close()
        iiq_conn.close()
        dest_cur.close()
        dest_conn.close()
        print("🎉 Phase 3 Role Effective Matrix Ingestion Complete with Dual GUID + Name Fields!")

    except Error as e:
        print(f"❌ Phase 3 Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_phase3_role_effective_matrix()
