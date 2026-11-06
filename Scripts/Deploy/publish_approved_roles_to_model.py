#!/usr/bin/env python3
"""
bundleBuilder - Production Role Model Publisher & Comprehensive Audit Synchronizer
Promotes approved Business & IT roles from Staging into ApprovedRoleModel_* tables.
Audits Rule, Owner, Description, Name, Deploy Target, and Entitlement changes with before/after deltas.
"""

import os
import sys
import uuid
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


def publish_approved_role_model(changed_by="Admin / Excel Staging Workflow"):
    event_id = str(uuid.uuid4())[:8]
    print(f"\n🚀 Initiating Role Model Publication & Audit Stream [Event ID: {event_id}]...")

    try:
    db_connection = get_db_connection()
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.")

        audit_batch = []
        
        # Tracking Counters for Summary
        biz_created, biz_updated = 0, 0
        it_created, it_updated = 0, 0
        rules_created, rules_modified = 0, 0
        owners_assigned, owners_modified = 0, 0
        desc_created, desc_modified = 0, 0
        biz_ents_added, biz_ents_removed = 0, 0
        it_ents_added, it_ents_removed = 0, 0

        # ======================================================================
        # 1. PUBLISH APPROVED BUSINESS ROLES & AUDIT DELTAS
        # ======================================================================
        print("\n🏛️ [1/2] Publishing Approved Business Roles & Auditing Lifecycle...")
        
        # Load Existing Approved Roles
        cursor.execute("SELECT * FROM ApprovedRoleModel_Roles")
        existing_roles = {r["id"]: r for r in cursor.fetchall()}

        # Load Staged Approved Roles
        cursor.execute("""
            SELECT 
                id, role_name, approved_role_name, description, assignment_rule,
                owner_id, owner_name, deploy_target, target_population
            FROM Suggested_Roles
            WHERE approval_status = 'APPROVED'
        """)
        staged_roles = cursor.fetchall()

        # Load Staged Approved Entitlements
        cursor.execute("""
            SELECT 
                role_id, entitlement_id, entitlement_name, source_name, match_type
            FROM Suggested_Role_Entitlements
            WHERE is_included = 1
        """)
        staged_ents_by_role = defaultdict(list)
        for e in cursor.fetchall():
            staged_ents_by_role[e["role_id"]].append(e)

        # Load Existing Approved Entitlements
        cursor.execute("SELECT role_id, entitlement_id, entitlement_name FROM ApprovedRoleModel_RoleEntitlements")
        existing_ents_by_role = defaultdict(dict)
        for e in cursor.fetchall():
            existing_ents_by_role[e["role_id"]][e["entitlement_id"]] = e["entitlement_name"]

        for r in staged_roles:
            role_id = f"BR-{r['id']:04d}"
            role_name = (r["approved_role_name"] or r["role_name"]).strip()
            desc = (r["description"] or "").strip()
            rule = r["assignment_rule"].strip()
            owner_id = (r["owner_id"] or "IAM-Admins").strip()
            owner_name = (r["owner_name"] or "IAM Security Team").strip()
            deploy_target = (r["deploy_target"] or "BOTH").strip()
            pop = r["target_population"]

            current_staged_ents = staged_ents_by_role.get(r["id"], [])
            current_existing_ents = existing_ents_by_role.get(role_id, {})

            if role_id not in existing_roles:
                # --------------------------------------------------------------
                # NET-NEW BUSINESS ROLE (Version 1)
                # --------------------------------------------------------------
                cursor.execute("""
                    INSERT INTO ApprovedRoleModel_Roles 
                    (id, name, description, assignment_rule, rule_created_timestamp, rule_last_modified_timestamp,
                     owner_id, owner_name, deploy_target, status, version_number, target_population, activated_timestamp)
                    VALUES (%s, %s, %s, %s, NOW(), NOW(), %s, %s, %s, 'ACTIVE', 1, %s, NOW())
                """, (role_id, role_name, desc, rule, owner_id, owner_name, deploy_target, pop))

                # 1. Base Role Creation Audit
                audit_batch.append((
                    event_id, "BUSINESS_ROLE", role_id, role_name, 1, "CREATE_ROLE",
                    "ALL", None, f"Role Created: {role_name}",
                    changed_by, "Mined Role Staging Approval"
                ))

                # 2. Rule Creation Audit
                audit_batch.append((
                    event_id, "BUSINESS_ROLE", role_id, role_name, 1, "CREATE_RULE",
                    "assignment_rule", None, rule,
                    changed_by, f"Initial Rule Defined (Target: {pop:,} users)"
                ))
                rules_created += 1

                # 3. Owner Assignment Audit
                if owner_name:
                    audit_batch.append((
                        event_id, "BUSINESS_ROLE", role_id, role_name, 1, "ASSIGN_OWNER",
                        "owner", None, f"{owner_name} ({owner_id})",
                        changed_by, "Initial Role Owner Assigned"
                    ))
                    owners_assigned += 1

                # 4. Description Creation Audit
                if desc:
                    audit_batch.append((
                        event_id, "BUSINESS_ROLE", role_id, role_name, 1, "CREATE_DESCRIPTION",
                        "description", None, desc,
                        changed_by, "Initial Role Description Added"
                    ))
                    desc_created += 1

                biz_created += 1

            else:
                # --------------------------------------------------------------
                # EXISTING BUSINESS ROLE (Detect Deltas & Log Specific Audit Events)
                # --------------------------------------------------------------
                existing = existing_roles[role_id]
                old_ver = existing["version_number"]
                deltas = []
                rule_changed = False

                # A. Rule Delta Check
                if existing["assignment_rule"] != rule:
                    rule_changed = True
                    deltas.append(("MODIFY_RULE", "assignment_rule", existing["assignment_rule"], rule, f"Rule Updated (New Target: {pop:,} users)"))
                    rules_modified += 1

                # B. Owner Delta Check (ID or Name change)
                old_owner_id = (existing["owner_id"] or "").strip()
                old_owner_name = (existing["owner_name"] or "").strip()
                if old_owner_id != owner_id or old_owner_name != owner_name:
                    old_owner_str = f"{old_owner_name} ({old_owner_id})" if old_owner_name else "Unassigned"
                    new_owner_str = f"{owner_name} ({owner_id})"
                    deltas.append(("MODIFY_OWNER", "owner", old_owner_str, new_owner_str, "Role Ownership Reassigned"))
                    owners_modified += 1

                # C. Description Delta Check
                old_desc = (existing["description"] or "").strip()
                if old_desc != desc:
                    if not old_desc and desc:
                        deltas.append(("CREATE_DESCRIPTION", "description", None, desc, "Initial Role Description Defined"))
                        desc_created += 1
                    else:
                        deltas.append(("MODIFY_DESCRIPTION", "description", old_desc, desc, "Role Description Modified"))
                        desc_modified += 1

                # D. Role Name Delta Check
                if existing["name"] != role_name:
                    deltas.append(("UPDATE_NAME", "name", existing["name"], role_name, "Role Display Name Renamed"))

                # E. Deploy Target Delta Check
                if existing["deploy_target"] != deploy_target:
                    deltas.append(("UPDATE_DEPLOY_TARGET", "deploy_target", existing["deploy_target"], deploy_target, "Deployment Target Changed"))

                # F. Entitlement Additions/Removals
                staged_ent_ids = {e["entitlement_id"]: e for e in current_staged_ents}
                ents_added = [e for eid, e in staged_ent_ids.items() if eid not in current_existing_ents]
                ents_removed = [ename for eid, ename in current_existing_ents.items() if eid not in staged_ent_ids]

                if deltas or ents_added or ents_removed:
                    new_ver = old_ver + 1
                    
                    if rule_changed:
                        cursor.execute("""
                            UPDATE ApprovedRoleModel_Roles
                            SET name = %s, description = %s, assignment_rule = %s, rule_last_modified_timestamp = NOW(),
                                owner_id = %s, owner_name = %s, deploy_target = %s, target_population = %s,
                                version_number = %s, last_modified_timestamp = NOW()
                            WHERE id = %s
                        """, (role_name, desc, rule, owner_id, owner_name, deploy_target, pop, new_ver, role_id))
                    else:
                        cursor.execute("""
                            UPDATE ApprovedRoleModel_Roles
                            SET name = %s, description = %s, owner_id = %s, owner_name = %s,
                                deploy_target = %s, target_population = %s, version_number = %s, last_modified_timestamp = NOW()
                            WHERE id = %s
                        """, (role_name, desc, owner_id, owner_name, deploy_target, pop, new_ver, role_id))

                    # Log Granular Field Deltas
                    for action_type, field, old_v, new_v, reason in deltas:
                        audit_batch.append((
                            event_id, "BUSINESS_ROLE", role_id, role_name, new_ver, action_type,
                            field, str(old_v) if old_v else None, str(new_v) if new_v else None,
                            changed_by, reason
                        ))
                    biz_updated += 1

            # Synchronize Entitlements
            for e in current_staged_ents:
                eid = str(e["entitlement_id"])
                ename = e["entitlement_name"]
                if eid not in current_existing_ents:
                    cursor.execute("""
                        INSERT INTO ApprovedRoleModel_RoleEntitlements 
                        (role_id, role_name, entitlement_id, entitlement_name, source_name, match_type)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE role_name = VALUES(role_name)
                    """, (role_id, role_name, eid, ename, e["source_name"], e["match_type"]))

                    ver = (existing_roles[role_id]["version_number"] + 1) if role_id in existing_roles else 1
                    audit_batch.append((
                        event_id, "ROLE_ENTITLEMENT", role_id, role_name, ver, "ADD_ENTITLEMENT",
                        "entitlement", None, f"Added: {ename} ({e['source_name']})",
                        changed_by, "Entitlement Inclusion Approved"
                    ))
                    biz_ents_added += 1

            # Prune Removed Entitlements
            staged_ent_ids = {str(e["entitlement_id"]) for e in current_staged_ents}
            for eid, ename in current_existing_ents.items():
                if str(eid) not in staged_ent_ids:
                    cursor.execute("DELETE FROM ApprovedRoleModel_RoleEntitlements WHERE role_id = %s AND entitlement_id = %s", (role_id, eid))
                    ver = (existing_roles[role_id]["version_number"] + 1) if role_id in existing_roles else 1
                    audit_batch.append((
                        event_id, "ROLE_ENTITLEMENT", role_id, role_name, ver, "REMOVE_ENTITLEMENT",
                        "entitlement", ename, None,
                        changed_by, "Entitlement Excluded by Admin"
                    ))
                    biz_ents_removed += 1

        # ======================================================================
        # 2. PUBLISH APPROVED IT ROLES / ACCESS PROFILES & AUDIT DELTAS
        # ======================================================================
        print("\n🛠️ [2/2] Publishing Approved IT Roles & Auditing Lifecycle...")

        cursor.execute("SELECT * FROM ApprovedRoleModel_AccessProfiles")
        existing_aps = {ap["id"]: ap for ap in cursor.fetchall()}

        cursor.execute("""
            SELECT 
                id, it_role_name, approved_role_name, primary_source, description,
                owner_id, owner_name, deploy_target
            FROM Suggested_IT_Roles
            WHERE approval_status = 'APPROVED'
        """)
        staged_it_roles = cursor.fetchall()

        cursor.execute("""
            SELECT 
                it_role_id, entitlement_id, entitlement_name, source_name
            FROM Suggested_IT_Role_Entitlements
            WHERE is_included = 1
        """)
        staged_it_ents_by_ap = defaultdict(list)
        for e in cursor.fetchall():
            staged_it_ents_by_ap[e["it_role_id"]].append(e)

        cursor.execute("SELECT access_profile_id, entitlement_id, entitlement_name FROM ApprovedRoleModel_AccessProfileEntitlements")
        existing_it_ents_by_ap = defaultdict(dict)
        for e in cursor.fetchall():
            existing_it_ents_by_ap[e["access_profile_id"]][e["entitlement_id"]] = e["entitlement_name"]

        for ap in staged_it_roles:
            ap_id = f"ITR-{ap['id']:04d}"
            ap_name = (ap["approved_role_name"] or ap["it_role_name"]).strip()
            desc = (ap["description"] or "").strip()
            source = ap["primary_source"]
            owner_id = (ap["owner_id"] or "IAM-Admins").strip()
            owner_name = (ap["owner_name"] or "IAM Security Team").strip()
            deploy_target = (ap["deploy_target"] or "BOTH").strip()

            current_staged_ents = staged_it_ents_by_ap.get(ap["id"], [])
            current_existing_ents = existing_it_ents_by_ap.get(ap_id, {})

            if ap_id not in existing_aps:
                # --------------------------------------------------------------
                # NET-NEW IT ROLE (Version 1)
                # --------------------------------------------------------------
                cursor.execute("""
                    INSERT INTO ApprovedRoleModel_AccessProfiles 
                    (id, name, description, primary_source, owner_id, owner_name, deploy_target, status, version_number, activated_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 1, NOW())
                """, (ap_id, ap_name, desc, source, owner_id, owner_name, deploy_target))

                # Base IT Role Creation
                audit_batch.append((
                    event_id, "IT_ROLE", ap_id, ap_name, 1, "CREATE_ROLE",
                    "ALL", None, f"IT Role Created: {ap_name} ({len(current_staged_ents)} Permissions)",
                    changed_by, "Mined Access Profile Approval"
                ))

                # Owner Assignment Audit
                if owner_name:
                    audit_batch.append((
                        event_id, "IT_ROLE", ap_id, ap_name, 1, "ASSIGN_OWNER",
                        "owner", None, f"{owner_name} ({owner_id})",
                        changed_by, "Initial IT Role Owner Assigned"
                    ))
                    owners_assigned += 1

                # Description Creation Audit
                if desc:
                    audit_batch.append((
                        event_id, "IT_ROLE", ap_id, ap_name, 1, "CREATE_DESCRIPTION",
                        "description", None, desc,
                        changed_by, "Initial IT Role Description Added"
                    ))
                    desc_created += 1

                it_created += 1

            else:
                # --------------------------------------------------------------
                # EXISTING IT ROLE (Detect Deltas & Specific Audit Events)
                # --------------------------------------------------------------
                existing = existing_aps[ap_id]
                old_ver = existing["version_number"]
                deltas = []

                # A. Owner Delta Check
                old_owner_id = (existing["owner_id"] or "").strip()
                old_owner_name = (existing["owner_name"] or "").strip()
                if old_owner_id != owner_id or old_owner_name != owner_name:
                    old_owner_str = f"{old_owner_name} ({old_owner_id})" if old_owner_name else "Unassigned"
                    new_owner_str = f"{owner_name} ({owner_id})"
                    deltas.append(("MODIFY_OWNER", "owner", old_owner_str, new_owner_str, "IT Role Owner Reassigned"))
                    owners_modified += 1

                # B. Description Delta Check
                old_desc = (existing["description"] or "").strip()
                if old_desc != desc:
                    if not old_desc and desc:
                        deltas.append(("CREATE_DESCRIPTION", "description", None, desc, "Initial IT Role Description Added"))
                        desc_created += 1
                    else:
                        deltas.append(("MODIFY_DESCRIPTION", "description", old_desc, desc, "IT Role Description Modified"))
                        desc_modified += 1

                # C. Name Delta Check
                if existing["name"] != ap_name:
                    deltas.append(("UPDATE_NAME", "name", existing["name"], ap_name, "IT Role Renamed"))

                # D. Deploy Target Check
                if existing["deploy_target"] != deploy_target:
                    deltas.append(("UPDATE_DEPLOY_TARGET", "deploy_target", existing["deploy_target"], deploy_target, "Deployment Target Changed"))

                staged_ent_ids = {e["entitlement_id"]: e for e in current_staged_ents}
                ents_added = [e for eid, e in staged_ent_ids.items() if eid not in current_existing_ents]
                ents_removed = [ename for eid, ename in current_existing_ents.items() if eid not in staged_ent_ids]

                if deltas or ents_added or ents_removed:
                    new_ver = old_ver + 1
                    cursor.execute("""
                        UPDATE ApprovedRoleModel_AccessProfiles
                        SET name = %s, description = %s, owner_id = %s, owner_name = %s,
                            deploy_target = %s, version_number = %s, last_modified_timestamp = NOW()
                        WHERE id = %s
                    """, (ap_name, desc, owner_id, owner_name, deploy_target, new_ver, ap_id))

                    for action_type, field, old_v, new_v, reason in deltas:
                        audit_batch.append((
                            event_id, "IT_ROLE", ap_id, ap_name, new_ver, action_type,
                            field, str(old_v) if old_v else None, str(new_v) if new_v else None,
                            changed_by, reason
                        ))
                    it_updated += 1

            # Sync Entitlements
            for e in current_staged_ents:
                eid = str(e["entitlement_id"])
                ename = e["entitlement_name"]
                if eid not in current_existing_ents:
                    cursor.execute("""
                        INSERT INTO ApprovedRoleModel_AccessProfileEntitlements 
                        (access_profile_id, access_profile_name, entitlement_id, entitlement_name, source_name)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE access_profile_name = VALUES(access_profile_name)
                    """, (ap_id, ap_name, eid, ename, e["source_name"]))

                    ver = (existing_aps[ap_id]["version_number"] + 1) if ap_id in existing_aps else 1
                    audit_batch.append((
                        event_id, "AP_ENTITLEMENT", ap_id, ap_name, ver, "ADD_ENTITLEMENT",
                        "entitlement", None, f"Added: {ename} ({e['source_name']})",
                        changed_by, "Permission Inclusion Approved"
                    ))
                    it_ents_added += 1

            # Prune Entitlements
            staged_ent_ids = {str(e["entitlement_id"]) for e in current_staged_ents}
            for eid, ename in current_existing_ents.items():
                if str(eid) not in staged_ent_ids:
                    cursor.execute("DELETE FROM ApprovedRoleModel_AccessProfileEntitlements WHERE access_profile_id = %s AND entitlement_id = %s", (ap_id, eid))
                    ver = (existing_aps[ap_id]["version_number"] + 1) if ap_id in existing_aps else 1
                    audit_batch.append((
                        event_id, "AP_ENTITLEMENT", ap_id, ap_name, ver, "REMOVE_ENTITLEMENT",
                        "entitlement", ename, None,
                        changed_by, "Permission Excluded by Admin"
                    ))
                    it_ents_removed += 1

        # ======================================================================
        # 3. WRITE AUDIT LOG BATCH
        # ======================================================================
        print(f"\n📝 Writing {len(audit_batch):,} Granular Audit Log Records...")
        sql_audit = """
            INSERT INTO ApprovedRoleModel_AuditLog 
            (event_id, entity_type, entity_id, entity_name, version_number, action_type, field_name, old_value, new_value, changed_by, change_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        chunk_size = 5000
        for i in range(0, len(audit_batch), chunk_size):
            cursor.executemany(sql_audit, audit_batch[i:i + chunk_size])

        db_connection.commit()

        # Print Granular Audit Breakdown
        print("\n" + "=" * 80)
        print("📊 PUBLISHED ROLE MODEL & AUDIT SUMMARY")
        print("=" * 80)
        print(f"🏛️ Business Roles       : {biz_created:,} Created (v1) | {biz_updated:,} Updated (v+1)")
        print(f"🛠️ IT Roles (AP)        : {it_created:,} Created (v1) | {it_updated:,} Updated (v+1)")
        print(f"📋 Assignment Rules     : {rules_created:,} Initial Rules Created | {rules_modified:,} Rules Modified")
        print(f"👤 Role Owners          : {owners_assigned:,} Initial Owners Assigned | {owners_modified:,} Owners Reassigned")
        print(f"📝 Role Descriptions    : {desc_created:,} Initial Descriptions Added | {desc_modified:,} Descriptions Modified")
        print(f"🔑 Entitlements         : {biz_ents_added + it_ents_added:,} Attached | {biz_ents_removed + it_ents_removed:,} Pruned")
        print(f"📜 Total Audit Records  : {len(audit_batch):,} logged under Event ID: {event_id}")
        print("=" * 80)

        cursor.close()
        db_connection.close()
        print("🎉 Full Governance Audit & Role Publication Complete!")

    except Error as e:
        print(f"❌ Database error during publication: {e}")
        sys.exit(1)


if __name__ == "__main__":
    publish_approved_role_model()
