#!/usr/bin/env python3
"""
bundleBuilder - SailPoint ISC IT Role (Access Profile) Payload Generator
Compares approved IT Roles against CurrentRoleModel_AccessProfiles:
  • Net-New IT Roles  --> Generates POST /v3/access-profiles payload
  • Existing IT Roles --> Generates PATCH /v3/access-profiles/{id} JSON Patch payload
Outputs a master manifest: Deploy/isc_it_roles_deployment_manifest.json
"""

import os
import sys
import json
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


MANIFEST_OUTPUT = os.path.join("Deploy", "isc_it_roles_deployment_manifest.json")
PAYLOAD_DIR = os.path.join("Deploy", "ISC_Payloads")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


def normalize_str(val):
    if val is None:
        return ""
    return str(val).strip().lower()


def generate_isc_payloads():
    print("=" * 85)
    print("📦 SAILPOINT ISC IT ROLE (ACCESS PROFILE) PAYLOAD GENERATOR")
    print("=" * 85)

    os.makedirs(PAYLOAD_DIR, exist_ok=True)

    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.\n")

        # ======================================================================
        # 1. LOAD EXISTING ISC ACCESS PROFILES (Current Production State)
        # ======================================================================
        print("🔍 [1/4] Indexing existing ISC Access Profiles from CurrentRoleModel...")
        cursor.execute("""
            SELECT id, name, description, owner_id, source_id, source_name, enabled 
            FROM CurrentRoleModel_AccessProfiles
        """)
        existing_ap_rows = cursor.fetchall()

        existing_aps_by_name = {}
        existing_aps_by_id = {}
        for ap in existing_ap_rows:
            ap_id = str(ap["id"]).strip()
            ap_name_norm = normalize_str(ap["name"])
            existing_aps_by_name[ap_name_norm] = ap
            existing_aps_by_id[ap_id.lower()] = ap

        print(f"   • Loaded {len(existing_ap_rows):,} existing Access Profiles from ISC baseline.")

        # ======================================================================
        # 2. LOAD ENTITLEMENT & SOURCE METADATA LOOKUPS
        # ======================================================================
        print("🗺️ [2/4] Indexing Entitlement GUIDs and Source IDs...")
        cursor.execute("SELECT id, entitlement_name, source_id, source_name FROM entitlements")
        ent_meta_rows = cursor.fetchall()

        ent_id_map = {}
        source_id_map = {}
        for e in ent_meta_rows:
            e_name_norm = normalize_str(e["entitlement_name"])
            src_name_norm = normalize_str(e["source_name"])
            e_id = str(e["id"]).strip()
            src_id = str(e["source_id"] or "").strip()

            ent_id_map[e_name_norm] = e_id
            if src_name_norm and src_id:
                source_id_map[src_name_norm] = src_id

        # ======================================================================
        # 3. LOAD APPROVED IT ROLES & ENTITLEMENTS FOR DEPLOYMENT
        # ======================================================================
        print("🛠️ [3/4] Loading Approved IT Roles targeted for ISC...")
        
        # Pull approved IT roles targeted for ISC_CLOUD or BOTH
        cursor.execute("""
            SELECT 
                id, it_role_name, approved_role_name, primary_source, description,
                owner_id, owner_name, deploy_target
            FROM Suggested_IT_Roles
            WHERE approval_status = 'APPROVED'
              AND deploy_target IN ('BOTH', 'ISC_CLOUD')
        """)
        staged_it_roles = cursor.fetchall()

        # If Suggested_IT_Roles is not yet reviewed, fallback to ApprovedRoleModel_AccessProfiles
        if not staged_it_roles:
            print("ℹ️ No approved roles found in Suggested_IT_Roles. Checking ApprovedRoleModel_AccessProfiles...")
            cursor.execute("""
                SELECT 
                    id, name AS it_role_name, name AS approved_role_name, primary_source, description,
                    owner_id, owner_name, deploy_target
                FROM ApprovedRoleModel_AccessProfiles
                WHERE deploy_target IN ('BOTH', 'ISC_CLOUD')
            """)
            staged_it_roles = cursor.fetchall()

        print(f"   • Found {len(staged_it_roles):,} IT Roles targeted for ISC deployment.")

        # Load Entitlements per IT Role
        cursor.execute("""
            SELECT it_role_id, entitlement_id, entitlement_name, source_name
            FROM Suggested_IT_Role_Entitlements
            WHERE is_included = 1
        """)
        staged_ents_by_role = defaultdict(list)
        for e in cursor.fetchall():
            staged_ents_by_role[e["it_role_id"]].append(e)

        if not staged_ents_by_role:
            cursor.execute("""
                SELECT access_profile_id AS it_role_id, entitlement_id, entitlement_name, source_name
                FROM ApprovedRoleModel_AccessProfileEntitlements
            """)
            for e in cursor.fetchall():
                staged_ents_by_role[e["it_role_id"]].append(e)

        # ======================================================================
        # 4. GENERATE POST & PATCH PAYLOADS
        # ======================================================================
        print("\n⚙️ [4/4] Generating RFC 6902 JSON Patch & POST Payloads...")

        post_operations = []
        patch_operations = []

        for r in staged_it_roles:
            local_id_int = r["id"]
            local_id_str = f"ITR-{local_id_int:04d}" if isinstance(local_id_int, int) else str(local_id_int)
            final_name = (r["approved_role_name"] or r["it_role_name"]).strip()
            name_norm = normalize_str(final_name)
            desc = (r["description"] or f"Functional Access Profile for {final_name}.").strip()
            source_name = (r["primary_source"] or "Identity Security Cloud").strip()
            owner_id = (r["owner_id"] or "2c91808568c529c60168cca6f90c1313").strip()  # Fallback admin GUID

            # Resolve Source GUID
            source_id = source_id_map.get(normalize_str(source_name), "2c9180835d19eb94015d2334e34e028b")

            # Resolve Entitlements List for Payload
            raw_ents = staged_ents_by_role.get(local_id_int, [])
            entitlements_payload = []
            for e in raw_ents:
                e_name = e["entitlement_name"].strip()
                # Resolve Entitlement GUID
                e_guid = str(e.get("entitlement_id") or ent_id_map.get(normalize_str(e_name), e_name)).strip()
                entitlements_payload.append({
                    "type": "ENTITLEMENT",
                    "id": e_guid,
                    "name": e_name
                })

            # Check if this IT Role already exists in ISC
            existing_match = existing_aps_by_name.get(name_norm) or existing_aps_by_id.get(normalize_str(local_id_str))

            if existing_match:
                # --------------------------------------------------------------
                # EXISTING ACCESS PROFILE --> PATCH /v3/access-profiles/{id}
                # --------------------------------------------------------------
                isc_ap_id = existing_match["id"]
                
                # Standard RFC 6902 JSON Patch document
                patch_document = [
                    {
                        "op": "replace",
                        "path": "/name",
                        "value": final_name
                    },
                    {
                        "op": "replace",
                        "path": "/description",
                        "value": desc
                    },
                    {
                        "op": "replace",
                        "path": "/owner",
                        "value": {
                            "type": "IDENTITY",
                            "id": owner_id
                        }
                    },
                    {
                        "op": "replace",
                        "path": "/entitlements",
                        "value": [{"type": "ENTITLEMENT", "id": item["id"]} for item in entitlements_payload]
                    },
                    {
                        "op": "replace",
                        "path": "/enabled",
                        "value": True
                    }
                ]

                operation_entry = {
                    "operation_type": "PATCH",
                    "endpoint": f"/v3/access-profiles/{isc_ap_id}",
                    "isc_access_profile_id": isc_ap_id,
                    "local_role_id": local_id_str,
                    "role_name": final_name,
                    "primary_source": source_name,
                    "entitlements_count": len(entitlements_payload),
                    "payload": patch_document
                }
                patch_operations.append(operation_entry)

                # Save individual inspectable JSON
                with open(os.path.join(PAYLOAD_DIR, f"PATCH_{local_id_str}.json"), "w", encoding="utf-8") as f:
                    json.dump(operation_entry, f, indent=2)

            else:
                # --------------------------------------------------------------
                # NET-NEW ACCESS PROFILE --> POST /v3/access-profiles
                # --------------------------------------------------------------
                post_document = {
                    "name": final_name,
                    "description": desc,
                    "owner": {
                        "type": "IDENTITY",
                        "id": owner_id
                    },
                    "source": {
                        "type": "SOURCE",
                        "id": source_id
                    },
                    "entitlements": [{"type": "ENTITLEMENT", "id": item["id"]} for item in entitlements_payload],
                    "enabled": True,
                    "requestable": True
                }

                operation_entry = {
                    "operation_type": "POST",
                    "endpoint": "/v3/access-profiles",
                    "local_role_id": local_id_str,
                    "role_name": final_name,
                    "primary_source": source_name,
                    "source_id": source_id,
                    "entitlements_count": len(entitlements_payload),
                    "payload": post_document
                }
                post_operations.append(operation_entry)

                with open(os.path.join(PAYLOAD_DIR, f"POST_{local_id_str}.json"), "w", encoding="utf-8") as f:
                    json.dump(operation_entry, f, indent=2)

        # ======================================================================
        # 5. WRITE MASTER DEPLOYMENT MANIFEST
        # ======================================================================
        manifest = {
            "metadata": {
                "generated_timestamp": datetime.now().isoformat(),
                "target_platform": "SailPoint Identity Security Cloud (ISC)",
                "total_operations": len(post_operations) + len(patch_operations),
                "create_operations_count": len(post_operations),
                "update_operations_count": len(patch_operations)
            },
            "create_operations": post_operations,
            "update_operations": patch_operations
        }

        with open(MANIFEST_OUTPUT, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Print Summary Report
        print("\n" + "=" * 85)
        print("📊 ISC PAYLOAD GENERATION & DEPLOYMENT MANIFEST SUMMARY")
        print("=" * 85)
        print(f"📄 Master Manifest File  : {MANIFEST_OUTPUT}")
        print(f"📁 Individual JSON Files : {PAYLOAD_DIR}/")
        print(f"✨ Net-New IT Roles (POST) : {len(post_operations):,} payloads generated")
        print(f"🔄 Existing IT Roles (PATCH): {len(patch_operations):,} payloads generated")
        print("=" * 85)

        if post_operations:
            print("\n   Sample Net-New POST Operations:")
            for op in post_operations[:3]:
                print(f"     ➕ POST /v3/access-profiles -> [{op['local_role_id']}] {op['role_name']} ({op['entitlements_count']} perms)")

        if patch_operations:
            print("\n   Sample Existing PATCH Operations:")
            for op in patch_operations[:3]:
                print(f"     🔄 PATCH /v3/access-profiles/{op['isc_access_profile_id']} -> [{op['local_role_id']}] {op['role_name']}")

        cursor.close()
        db_connection.close()
        print("\n🎉 Success! Manifest is ready for API execution.\n")

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    generate_isc_payloads()
