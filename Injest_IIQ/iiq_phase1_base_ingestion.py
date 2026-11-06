#!/usr/bin/env python3
"""
bundleBuilder - IIQ Phase 1: Base Catalog Ingestion
Extracts spt_identity (GUIDs & unpivoted attributes), spt_managed_attribute (GUIDs & entitlements),
and spt_bundle (GUIDs & role definitions).
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

IDENTITY_ATTRIBUTE_COLUMNS = [
    "firstname", "lastname", "email", "department", "jobtitle", 
    "location", "country", "manager", "type", "identitystate", 
    "inactive", "region", "division", "costcenter", "startdate"
]


def run_phase1_ingestion():
    try:
        print("🔗 Connecting to IIQ Source and bundleBuilder Destination...")
        iiq_conn = mysql.connector.connect(**IIQ_DB_CONFIG)
        iiq_cur = iiq_conn.cursor(dictionary=True)

        dest_conn = mysql.connector.connect(**BUNDLE_DB_CONFIG)
        dest_cur = dest_conn.cursor()

        # ======================================================================
        # 1. ENTITLEMENTS (GUID id, entitlement_name, source_id, source_name)
        # ======================================================================
        print("\n📦 [1/3] Extracting Entitlements with Immutable GUIDs...")
        iiq_cur.execute("""
            SELECT 
                ma.id AS entitlement_id,
                ma.value AS entitlement_name,
                app.id AS source_id,
                app.name AS source_name,
                ma.description AS description,
                owner.id AS owner_id,
                owner.name AS owner_name
            FROM spt_managed_attribute ma
            JOIN spt_application app ON ma.application = app.id
            LEFT JOIN spt_identity owner ON ma.owner = owner.id
            WHERE ma.value IS NOT NULL AND TRIM(ma.value) != ''
        """)
        ent_rows = iiq_cur.fetchall()

        dest_cur.execute("DELETE FROM entitlements")
        sql_ent = """
            INSERT INTO entitlements (id, entitlement_name, source_id, source_name, description, owner_id, owner_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                entitlement_name=VALUES(entitlement_name),
                source_name=VALUES(source_name),
                description=VALUES(description)
        """
        ent_batch = [
            (
                str(r["entitlement_id"])[:250],
                str(r["entitlement_name"])[:250],
                str(r["source_id"])[:250] if r["source_id"] else None,
                str(r["source_name"])[:250],
                r["description"],
                str(r["owner_id"])[:250] if r["owner_id"] else None,
                str(r["owner_name"])[:250] if r["owner_name"] else None
            )
            for r in ent_rows
        ]
        dest_cur.executemany(sql_ent, ent_batch)
        print(f"   ✅ Ingested {len(ent_batch):,} Entitlements with immutable GUIDs.")

        # ======================================================================
        # 2. IDENTITIES (GUID identity_id, identity_name, attributes)
        # ======================================================================
        print("\n👤 [2/3] Extracting Identities (GUID + Name) & Unpivoting Attributes...")
        iiq_cur.execute("SELECT * FROM spt_identity")
        identity_rows = iiq_cur.fetchall()

        attr_batch = []
        for row in identity_rows:
            identity_guid = str(row.get("id")).strip()
            identity_name = str(row.get("name") or identity_guid).strip()
            
            for col, val in row.items():
                col_clean = col.lower().replace("_", "")
                if val is not None and str(val).strip() != "" and col_clean in [c.replace("_", "") for c in IDENTITY_ATTRIBUTE_COLUMNS]:
                    attr_batch.append((identity_guid, identity_name, col, str(val)[:250]))

        dest_cur.execute("DELETE FROM IdentityAttributes")
        sql_attr = "INSERT INTO IdentityAttributes (identity_id, identity_name, attribute_name, attribute_value) VALUES (%s, %s, %s, %s)"
        
        chunk_size = 10000
        for i in range(0, len(attr_batch), chunk_size):
            dest_cur.executemany(sql_attr, attr_batch[i:i + chunk_size])
        print(f"   ✅ Ingested {len(identity_rows):,} Identities ({len(attr_batch):,} unpivoted attribute rows).")

        # ======================================================================
        # 3. CURRENT ROLE MODEL (GUID id, name)
        # ======================================================================
        print("\n🏛️ [3/3] Extracting Current Role Models with Immutable GUIDs...")
        
        # Business Roles
        iiq_cur.execute("""
            SELECT 
                b.id, b.name, b.description,
                CASE WHEN b.disabled = 1 THEN 0 ELSE 1 END AS enabled,
                owner.name AS owner_name, b.created, b.modified, b.selector
            FROM spt_bundle b
            LEFT JOIN spt_identity owner ON b.owner = owner.id
            WHERE b.type IN ('business', 'organizational') OR b.type IS NULL
        """)
        biz_roles = iiq_cur.fetchall()

        dest_cur.execute("DELETE FROM CurrentRoleModel_Roles")
        sql_biz = """
            INSERT INTO CurrentRoleModel_Roles 
            (id, name, description, enabled, requestable, owner_name, created, modified, assignmentCriteria)
            VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
        """
        biz_batch = [
            (str(r["id"]), str(r["name"])[:250], r["description"], r["enabled"], r["owner_name"], r["created"], r["modified"], str(r["selector"]) if r["selector"] else None)
            for r in biz_roles
        ]
        dest_cur.executemany(sql_biz, biz_batch)
        print(f"   ✅ Ingested {len(biz_batch):,} Business Roles.")

        # Access Profiles (IT Roles)
        iiq_cur.execute("""
            SELECT 
                b.id, b.name, b.description,
                CASE WHEN b.disabled = 1 THEN 0 ELSE 1 END AS enabled,
                owner.name AS owner_name,
                MAX(app.name) AS source_name
            FROM spt_bundle b
            LEFT JOIN spt_identity owner ON b.owner = owner.id
            LEFT JOIN spt_profile p ON p.bundle = b.id
            LEFT JOIN spt_application app ON p.application = app.id
            WHERE b.type = 'it'
            GROUP BY b.id, b.name, b.description, b.disabled, owner.name
        """)
        it_roles = iiq_cur.fetchall()

        dest_cur.execute("DELETE FROM CurrentRoleModel_AccessProfiles")
        sql_it = """
            INSERT INTO CurrentRoleModel_AccessProfiles 
            (id, name, description, enabled, requestable, owner_name, source_name)
            VALUES (%s, %s, %s, %s, 1, %s, %s)
        """
        it_batch = [
            (str(r["id"]), str(r["name"])[:250], r["description"], r["enabled"], r["owner_name"], str(r["source_name"] or "IdentityIQ")[:250])
            for r in it_roles
        ]
        dest_cur.executemany(sql_it, it_batch)
        print(f"   ✅ Ingested {len(it_batch):,} IT Roles (Access Profiles).")

        dest_conn.commit()
        iiq_cur.close()
        iiq_conn.close()
        dest_cur.close()
        dest_conn.close()
        print("\n🎉 Phase 1 Ingestion Complete with Dual GUID + Name Fields!")

    except Error as e:
        print(f"❌ Phase 1 Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_phase1_ingestion()
