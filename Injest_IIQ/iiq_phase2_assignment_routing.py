#!/usr/bin/env python3
"""
bundleBuilder - IIQ Phase 2: Assignment Routing Pipeline
Extracts spt_identity_entitlement and routes:
  • Source in ('Role', 'Rule')           --> IdentityRoleAssignments (with GUIDs & Names)
  • Source in ('Account', 'Aggregation') --> IdentityEntitlementAssignments (with GUIDs & Names)
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


def run_phase2_routing():
    try:
        print("🔗 Connecting to IIQ Source and bundleBuilder Destination...")
        iiq_conn = mysql.connector.connect(**IIQ_DB_CONFIG)
        iiq_cur = iiq_conn.cursor(dictionary=True)

        dest_conn = mysql.connector.connect(**BUNDLE_DB_CONFIG)
        dest_cur = dest_conn.cursor(dictionary=True)

        # 1. Cache GUID mappings from bundleBuilder catalogs
        print("🗺️ Pre-caching GUID lookups from bundleBuilder catalogs...")
        
        dest_cur.execute("SELECT id, name FROM CurrentRoleModel_Roles")
        role_map = {row["name"].strip(): str(row["id"]) for row in dest_cur.fetchall()}

        dest_cur.execute("SELECT id, name FROM CurrentRoleModel_AccessProfiles")
        ap_map = {row["name"].strip(): str(row["id"]) for row in dest_cur.fetchall()}

        dest_cur.execute("SELECT id, entitlement_name, source_name FROM entitlements")
        ent_map = {(row["entitlement_name"].strip(), row["source_name"].strip()): str(row["id"]) for row in dest_cur.fetchall()}
        ent_name_only_map = {row["entitlement_name"].strip(): str(row["id"]) for row in dest_cur.fetchall()}

        # 2. Extract Effective Access Records from IIQ
        print("\n📡 Querying effective access records with native GUIDs from IIQ...")
        iiq_cur.execute("""
            SELECT 
                ident.id AS identity_id,
                ident.name AS identity_name,
                app.id AS source_id,
                app.name AS source_name,
                ie.name AS attribute_name,
                ie.value AS entitlement_name,
                COALESCE(ie.source, 'Account') AS grant_source,
                ie.assigned_role,
                ie.granted_by_role
            FROM spt_identity_entitlement ie
            JOIN spt_identity ident ON ie.identity_id = ident.id
            JOIN spt_application app ON ie.application = app.id
            WHERE ie.value IS NOT NULL AND TRIM(ie.value) != ''
        """)
        rows = iiq_cur.fetchall()
        print(f"   • Fetched {len(rows):,} total entitlement assignment records.")

        role_assignments_batch = []
        direct_assignments_batch = []

        for r in rows:
            identity_id = str(r["identity_id"]).strip()
            identity_name = str(r["identity_name"]).strip()
            source_id = str(r["source_id"]).strip()
            source_name = str(r["source_name"]).strip()
            ent_name = str(r["entitlement_name"]).strip()
            attr_name = str(r["attribute_name"] or "memberOf").strip()
            source_type = str(r["grant_source"]).strip()

            # Resolve Entitlement GUID
            ent_id = ent_map.get((ent_name, source_name), ent_name_only_map.get(ent_name, None))

            if source_type.lower() in ("role", "rule"):
                assigned_role_name = str(r["assigned_role"] or "Direct Role Assignment").strip()
                granted_by_role_name = str(r["granted_by_role"] or "Directly Assigned").strip()
                if not granted_by_role_name:
                    granted_by_role_name = "Directly Assigned"

                # Resolve Role and Access Profile GUIDs
                role_id = role_map.get(assigned_role_name, f"ROLE-{assigned_role_name}")
                ap_id = ap_map.get(granted_by_role_name, "AP-DIRECT" if granted_by_role_name == "Directly Assigned" else f"AP-{granted_by_role_name}")

                role_assignments_batch.append((
                    identity_id[:250],
                    identity_name[:250],
                    role_id[:250],
                    assigned_role_name[:250],
                    ap_id[:250],
                    granted_by_role_name[:250],
                    ent_id[:250] if ent_id else None,
                    ent_name[:250],
                    source_id[:250],
                    source_name[:250],
                    source_type
                ))
            else:
                direct_assignments_batch.append((
                    identity_id[:250],
                    identity_name[:250],
                    ent_id[:250] if ent_id else None,
                    ent_name[:250],
                    source_id[:250],
                    source_name[:250],
                    attr_name[:250]
                ))

        # Re-populate destination assignment tables
        dest_cur.execute("DELETE FROM IdentityRoleAssignments")
        dest_cur.execute("DELETE FROM IdentityEntitlementAssignments")

        # 1. Insert Role-Governed Assignments
        print(f"\n🏛️ Inserting {len(role_assignments_batch):,} Role-Governed Assignments into IdentityRoleAssignments...")
        sql_role_assign = """
            INSERT INTO IdentityRoleAssignments 
            (identity_id, identity_name, role_id, role_name, access_profile_id, access_profile_name, entitlement_id, entitlement_name, source_id, source_name, grant_source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        chunk_size = 10000
        for i in range(0, len(role_assignments_batch), chunk_size):
            dest_cur.executemany(sql_role_assign, role_assignments_batch[i:i + chunk_size])

        # 2. Insert Direct Account Assignments
        print(f"📦 Inserting {len(direct_assignments_batch):,} Direct/Unmanaged Assignments into IdentityEntitlementAssignments...")
        sql_direct_assign = """
            INSERT INTO IdentityEntitlementAssignments 
            (identity_id, identity_name, entitlement_id, entitlement_name, source_id, source_name, attribute_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        for i in range(0, len(direct_assignments_batch), chunk_size):
            dest_cur.executemany(sql_direct_assign, direct_assignments_batch[i:i + chunk_size])

        dest_conn.commit()
        iiq_cur.close()
        iiq_conn.close()
        dest_cur.close()
        dest_conn.close()
        print("\n🎉 Phase 2 Assignment Routing Complete with Dual GUID + Name Fields!")

    except Error as e:
        print(f"❌ Phase 2 Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_phase2_routing()
