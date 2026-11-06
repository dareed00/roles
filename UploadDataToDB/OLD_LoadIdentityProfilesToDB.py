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
        'database': 'bundleBuilder',
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
    Retrieves the ID of an entitlement from the 'entitlements' table
    based on its name and source name.
    """
    query = "SELECT id FROM entitlements WHERE entitlement_name = %s AND source_name = %s"
    cursor.execute(query, (entitlement_name, source_name))
    result = cursor.fetchone()
    return result[0] if result else None

def load_access_profile(access_profile_json):
    """
    Loads a single SailPoint Access Profile JSON object into the database.

    Args:
        access_profile_json (dict): A dictionary representing the
                                     Access Profile JSON object.
    """
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()

    try:
        # 1. Insert into CurrentRoleModel_AccessProfiles table
        # ---------------------------------------------------
        ap_query = """
            INSERT INTO CurrentRoleModel_AccessProfiles (
                id, name, description, enabled, requestable, created, modified,
                owner_id, owner_name, source_id, source_name, entitlements,
                segments, provisioningCriteria, additionalOwners
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                description = VALUES(description),
                enabled = VALUES(enabled),
                requestable = VALUES(requestable),
                modified = VALUES(modified),
                owner_id = VALUES(owner_id),
                owner_name = VALUES(owner_name),
                source_id = VALUES(source_id),
                source_name = VALUES(source_name),
                entitlements = VALUES(entitlements),
                segments = VALUES(segments),
                provisioningCriteria = VALUES(provisioningCriteria),
                additionalOwners = VALUES(additionalOwners);
        """

        # Extract owner and source data safely
        owner = access_profile_json.get('owner', {})
        source = access_profile_json.get('source', {})

        # Convert complex fields to JSON strings for storage
        entitlements_json = json.dumps(access_profile_json.get('entitlements', []))
        segments_json = json.dumps(access_profile_json.get('segments', []))
        provisioning_criteria_json = json.dumps(access_profile_json.get('provisioningCriteria'))
        additional_owners_json = json.dumps(access_profile_json.get('additionalOwners', []))

        ap_data = (
            access_profile_json.get('id'),
            access_profile_json.get('name'),
            access_profile_json.get('description'),
            access_profile_json.get('enabled', True),
            access_profile_json.get('requestable', True),
            access_profile_json.get('created'),
            access_profile_json.get('modified'),
            owner.get('id'),
            owner.get('name'),
            source.get('id'),
            source.get('name'),
            entitlements_json,
            segments_json,
            provisioning_criteria_json,
            additional_owners_json
        )

        cursor.execute(ap_query, ap_data)
        print(f"Successfully inserted/updated Access Profile: {access_profile_json.get('name')}")


        # 2. Insert into CurrentRoleModel_AccessProfileEntitlements mapping table
        # ---------------------------------------------------------------------
        if 'entitlements' in access_profile_json and access_profile_json['entitlements']:
            access_profile_id = access_profile_json.get('id')
            access_profile_name = access_profile_json.get('name')

            for ent in access_profile_json['entitlements']:
                entitlement_name = ent.get('name')
                # Assuming the source name for the entitlement is the same as the AP's source
                source_name = source.get('name')

                # First, get the ID of the existing entitlement
                entitlement_id = get_entitlement_id(cursor, entitlement_name, source_name)

                if entitlement_id:
                    map_query = """
                        INSERT INTO CurrentRoleModel_AccessProfileEntitlements (
                            access_profile_id, access_profile_name, entitlement_id, entitlement_name
                        ) VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            access_profile_name = VALUES(access_profile_name),
                            entitlement_name = VALUES(entitlement_name);
                    """
                    map_data = (access_profile_id, access_profile_name, entitlement_id, entitlement_name)
                    cursor.execute(map_query, map_data)
                    print(f"  - Mapped entitlement: {entitlement_name}")
                else:
                    print(f"  - WARNING: Entitlement '{entitlement_name}' with source '{source_name}' not found in 'entitlements' table. Skipping mapping.")

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
    # This is a sample JSON object representing a SailPoint Access Profile.
    # Replace this with your actual data.
    sample_ap_json = {
      "id": "2c91808a78134a49017814121f1b5272",
      "name": "Employee-AD",
      "description": "Access Profile for Employee Active Directory accounts",
      "created": "2021-03-08T19:58:39.932Z",
      "modified": "2021-03-08T20:01:10.724Z",
      "enabled": True,
      "requestable": True,
      "owner": {
        "type": "IDENTITY",
        "id": "2c918085771e162501772153229c2381",
        "name": "Dana Reed"
      },
      "source": {
        "type": "SOURCE",
        "id": "2c91808a78134a480178137351440343",
        "name": "Active Directory"
      },
      "entitlements": [
        {
          "type": "ENTITLEMENT",
          "id": "2c91808a78134a4901781411faec5231",
          "name": "CN=Employees,OU=Groups,OU=Demo,DC=seri,DC=sailpoint,DC=com"
        }
      ],
      "segments": [],
      "provisioningCriteria": None,
      "additionalOwners": []
    }

    # To use the script, you would call the load_access_profile function
    # with your JSON object.
    #
    # IMPORTANT: Before running, make sure you have:
    # 1. Installed the mysql-connector-python library (`pip install mysql-connector-python`)
    # 2. Updated the get_db_connection() function with your database credentials.
    # 3. Ensured that the entitlements listed in your JSON already exist in the
    #    'entitlements' table, as this script only maps them.

     load_access_profile(sample_ap_json)
    print("Example script ready. Update connection details and uncomment the function call to run.")
