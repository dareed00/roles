import mysql.connector
import json

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    # --- IMPORTANT ---
    # Replace these placeholder values with your actual database credentials.
    config = {
        'host': 'localhost',
        'user': 'root',
        'password': 'password',
        'database': 'bundleBuilder'
        'raise_on_warnings': True
    }
    try:
        conn = mysql.connector.connect(**config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None

def get_entitlement_id(cursor, entitlement_name, source_name):
    """
    Retrieves the internal database ID of an entitlement from the 'entitlements' table
    based on its name and source name.
    """
    query = "SELECT id FROM entitlements WHERE entitlement_name = %s AND source_name = %s"
    cursor.execute(query, (entitlement_name, source_name))
    result = cursor.fetchone()
    return result[0] if result else None

def load_role(role_json):
    """
    Loads a single SailPoint Role JSON object, including its nested access
    profiles and entitlements, into the database.

    Args:
        role_json (dict): A dictionary representing the Role JSON object.
    """
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()

    try:
        # 1. Insert into CurrentRoleModel_Roles table
        # -------------------------------------------
        role_query = """
            INSERT INTO CurrentRoleModel_Roles (
                id, name, description, enabled, requestable, owner_id,
                owner_name, created, modified, accessProfiles,
                assignmentCriteria, segments
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                description = VALUES(description),
                enabled = VALUES(enabled),
                requestable = VALUES(requestable),
                owner_id = VALUES(owner_id),
                owner_name = VALUES(owner_name),
                modified = VALUES(modified),
                accessProfiles = VALUES(accessProfiles),
                assignmentCriteria = VALUES(assignmentCriteria),
                segments = VALUES(segments);
        """

        owner = role_json.get('owner', {})
        access_profiles_json = json.dumps(role_json.get('accessProfiles', []))
        assignment_criteria_json = json.dumps(role_json.get('assignmentCriteria'))
        segments_json = json.dumps(role_json.get('segments', []))

        role_data = (
            role_json.get('id'),
            role_json.get('name'),
            role_json.get('description'),
            role_json.get('enabled', True),
            role_json.get('requestable', True),
            owner.get('id'),
            owner.get('name'),
            role_json.get('created'),
            role_json.get('modified'),
            access_profiles_json,
            assignment_criteria_json,
            segments_json
        )

        cursor.execute(role_query, role_data)
        print(f"Successfully inserted/updated Role: {role_json.get('name')}")

        # Common values needed for mapping tables
        role_id = role_json.get('id')
        role_name = role_json.get('name')

        # 2. Insert into CurrentRoleModel_RoleAccessProfiles mapping table
        # ----------------------------------------------------------------
        if 'accessProfiles' in role_json and role_json['accessProfiles']:
            for ap in role_json['accessProfiles']:
                access_profile_id = ap.get('id')
                access_profile_name = ap.get('name')

                if access_profile_id:
                    map_ap_query = """
                        INSERT INTO CurrentRoleModel_RoleAccessProfiles (
                            role_id, role_name, access_profile_id, access_profile_name
                        ) VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE role_name = VALUES(role_name);
                    """
                    map_ap_data = (role_id, role_name, access_profile_id, access_profile_name)
                    cursor.execute(map_ap_query, map_ap_data)
                    print(f"  - Mapped Access Profile: {access_profile_name}")
                else:
                    print(f"  - WARNING: Access Profile '{access_profile_name}' is missing an 'id'. Skipping mapping.")

        # 3. Insert into CurrentRoleModel_RoleEntitlements mapping table
        # --------------------------------------------------------------
        if 'entitlements' in role_json and role_json['entitlements']:
            for ent in role_json['entitlements']:
                entitlement_name = ent.get('name')
                source_name = ent.get('source', {}).get('name') # Entitlements in Roles have a source object

                if not source_name:
                    print(f"  - WARNING: Entitlement '{entitlement_name}' is missing source information. Skipping mapping.")
                    continue

                # Get the internal database ID from the 'entitlements' table
                internal_ent_id = get_entitlement_id(cursor, entitlement_name, source_name)

                if internal_ent_id:
                    map_ent_query = """
                        INSERT INTO CurrentRoleModel_RoleEntitlements (
                            role_id, role_name, entitlement_id, entitlement_name
                        ) VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE role_name = VALUES(role_name);
                    """
                    map_ent_data = (role_id, role_name, internal_ent_id, entitlement_name)
                    cursor.execute(map_ent_query, map_ent_data)
                    print(f"  - Mapped Entitlement: {entitlement_name}")
                else:
                    print(f"  - WARNING: Entitlement '{entitlement_name}' from source '{source_name}' not found in 'entitlements' table. Skipping mapping.")

        conn.commit()
        print("Transaction successful.")

    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

# --- Example Usage ---
if __name__ == '__main__':
    # This is a sample JSON object representing a SailPoint Role.
    # It now includes both Access Profiles and direct Entitlements.
    sample_role_json = {
        "id": "2c91808a78134a49017814121f1b6001",
        "name": "Manager Role",
        "description": "Generic role for all
