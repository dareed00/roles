#!/usr/bin/env python3
"""
bundleBuilder - Role Lifecycle Management & Deletion/Deactivation Auditor
Safely transitions Business and IT roles between ACTIVE, DEACTIVATED, and DELETED states.
Ensures zero hard-deletes, updates lifecycle timestamps, and writes immutable audit logs.
"""

import os
import sys
import uuid
import argparse
import mysql.connector
from mysql.connector import Error

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


def transition_role_state(role_id, target_action, reason, changed_by="Admin CLI"):
    event_id = str(uuid.uuid4())[:8]
    role_id_clean = role_id.strip().upper()
    action_clean = target_action.strip().upper()

    # Determine if Business Role (BR-) or IT Role (ITR-)
    if role_id_clean.startswith("BR-"):
        entity_type = "BUSINESS_ROLE"
        table_name = "ApprovedRoleModel_Roles"
    elif role_id_clean.startswith("ITR-"):
        entity_type = "IT_ROLE"
        table_name = "ApprovedRoleModel_AccessProfiles"
    else:
        print(f"❌ Error: Invalid Role ID format '{role_id}'. Expected prefix 'BR-' or 'ITR-'.")
        sys.exit(1)

    # Validate action
    action_map = {
        "DEACTIVATE": ("DEACTIVATED", "DEACTIVATE_ROLE", "`deactivated_timestamp` = NOW()"),
        "DELETE": ("DELETED", "DELETE_ROLE", "`deleted_timestamp` = NOW()"),
        "REACTIVATE": ("ACTIVE", "REACTIVATE_ROLE", "`activated_timestamp` = NOW(), `deactivated_timestamp` = NULL, `deleted_timestamp` = NULL")
    }

    if action_clean not in action_map:
        print(f"❌ Error: Invalid action '{target_action}'. Allowed actions: DEACTIVATE, DELETE, REACTIVATE.")
        sys.exit(1)

    new_status, audit_action, timestamp_sql = action_map[action_clean]

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor(dictionary=True)
        print(f"🔗 Connected to MySQL bundleBuilder [Event ID: {event_id}]...")

        # 1. Fetch Current Role State
        cur.execute(f"SELECT * FROM `{table_name}` WHERE `id` = %s", (role_id_clean,))
        role = cur.fetchone()

        if not role:
            print(f"❌ Error: {entity_type} with ID '{role_id_clean}' not found in `{table_name}`.")
            sys.exit(1)

        old_status = role["status"]
        old_ver = role["version_number"]
        role_name = role["name"]

        if old_status == new_status:
            print(f"⚠️ Warning: {role_id_clean} ({role_name}) is already in '{new_status}' state. No action taken.")
            sys.exit(0)

        # 2. Increment Version & Update Lifecycle State
        new_ver = old_ver + 1
        sql_update = f"""
            UPDATE `{table_name}`
            SET 
                `status` = %s,
                `version_number` = %s,
                `last_modified_timestamp` = NOW(),
                {timestamp_sql}
            WHERE `id` = %s
        """
        cur.execute(sql_update, (new_status, new_ver, role_id_clean))

        # 3. Write Immutable Audit Trail
        sql_audit = """
            INSERT INTO `ApprovedRoleModel_AuditLog` 
            (event_id, entity_type, entity_id, entity_name, version_number, action_type, field_name, old_value, new_value, changed_by, change_reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        old_val_summary = f"Status: {old_status} (Version {old_ver})"
        new_val_summary = f"Status: {new_status} (Version {new_ver})"

        cur.execute(sql_audit, (
            event_id,
            entity_type,
            role_id_clean,
            role_name,
            new_ver,
            audit_action,
            "status",
            old_val_summary,
            new_val_summary,
            changed_by,
            reason
        ))

        conn.commit()
        cur.close()
        conn.close()

        # Print Confirmation
        print("\n" + "=" * 80)
        print("✅ ROLE LIFECYCLE TRANSITION COMPLETE")
        print("=" * 80)
        print(f"📋 Entity Type   : {entity_type}")
        print(f"🆔 Role ID       : {role_id_clean} ({role_name})")
        print(f"🔄 State Change  : {old_status} (v{old_ver}) ──► {new_status} (v{new_ver})")
        print(f"📝 Action Logged : {audit_action}")
        print(f"👤 Changed By    : {changed_by}")
        print(f"💡 Justification : {reason}")
        print(f"📜 Audit Log ID  : Event {event_id}")
        print("=" * 80)

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Role Lifecycle (Deactivate, Delete, Reactivate) with Audit Trail.")
    parser.add_argument("role_id", help="Role ID to modify (e.g., BR-0001 or ITR-0004)")
    parser.add_argument("action", choices=["DEACTIVATE", "DELETE", "REACTIVATE"], help="Lifecycle action to execute")
    parser.add_argument("-r", "--reason", required=True, help="Mandatory business justification / change reason")
    parser.add_argument("-u", "--user", default="Admin CLI", help="Admin username executing the change")

    args = parser.parse_args()
    transition_role_state(args.role_id, args.action, args.reason, args.user)
