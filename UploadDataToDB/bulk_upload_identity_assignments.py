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



def bulk_upload_assignments(db_connection.:
    """
    Reads assignment JSON files, de-duplicates records, and loads them.
    Uses the access item's name as a fallback if its ID is null.
    """
    upload_configs = {
        "identity_role_assignments.json": {
            "table": "IdentityRoleAssignments",
            "sql": "INSERT INTO IdentityRoleAssignments (identity_id, identity_name, role_id, role_name, standalone) VALUES (%s, %s, %s, %s, %s)",
            # ===================================================================
            # === THE FIX IS HERE: Use 'name' as a fallback for 'id' ===
            "parser": lambda item: (
                item.get('identity_id'), item.get('identity_name'),
                item['access'].get('id') or item['access'].get('name'), # Fallback logic
                item['access'].get('name'),
                item['access'].get('standalone')
            ),
            "unique_key_indices": [0, 2] 
        },
        "identity_ap_assignments.json": {
            "table": "IdentityAccessProfileAssignments",
            "sql": "INSERT INTO IdentityAccessProfileAssignments (identity_id, identity_name, access_profile_id, access_profile_name, standalone) VALUES (%s, %s, %s, %s, %s)",
            "parser": lambda item: (
                item.get('identity_id'), item.get('identity_name'),
                item['access'].get('id') or item['access'].get('name'), # Fallback logic
                item['access'].get('name'),
                item['access'].get('standalone')
            ),
            "unique_key_indices": [0, 2]
        },
        "identity_entitlement_assignments.json": {
            "table": "IdentityEntitlementAssignments",
            "sql": "INSERT INTO IdentityEntitlementAssignments (identity_id, identity_name, entitlement_id, entitlement_name, standalone) VALUES (%s, %s, %s, %s, %s)",
            "parser": lambda item: (
                item.get('identity_id'), item.get('identity_name'),
                item['access'].get('id') or item['access'].get('name'), # Fallback logic
                item['access'].get('name'),
                item['access'].get('standalone')
            ),
            "unique_key_indices": [0, 2]
        }
        # ===================================================================
    }

    cursor = db_connection.cursor()
    try:
        print("\nDisabling foreign key checks for bulk load...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")

        for file_name, config in upload_configs.items():
            table_name = config['table']
            print(f"\n--- Starting upload for {file_name} into {table_name} ---")

            try:
                with open(file_name, 'r') as f: data = json.load(f)
            except FileNotFoundError:
                print(f"WARNING: {file_name} not found. Skipping."); continue

            if not data:
                print("JSON file is empty. Nothing to upload."); continue
            
            print(f"Clearing old data from {table_name}...")
            cursor.execute(f"TRUNCATE TABLE {table_name}")

            unique_records = {}
            id1_index, id2_index = config['unique_key_indices']
            
            print(f"Parsing and de-duplicating {len(data)} raw records...")
            
            records_to_insert_tuples = []
            for item in data:
                # The parser now handles the fallback logic. We just need to check if the final key is valid.
                record = config['parser'](item)
                if not record[id1_index] or not record[id2_index]:
                    print(f"  - WARNING: Skipping record with missing critical IDs: {item}")
                    continue
                
                unique_key = f"{record[id1_index]}-{record[id2_index]}"
                if unique_key not in unique_records:
                    unique_records[unique_key] = record
            
            records_to_insert = list(unique_records.values())

            print(f"Preparing to insert {len(records_to_insert)} valid, unique records...")
            cursor.executemany(config['sql'], records_to_insert)
            print(f"-> Successfully loaded {cursor.rowcount} records into {table_name}.")
        
        db_connection.commit()
        print("\nAll assignment data successfully loaded and committed.")

    except Error as e:
        print(f"An error occurred during the loading process: {e}")
        db_connection.rollback()
    finally:
        print("Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        cursor.close()

def main():
    # ... (main function is unchanged) ...
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return
    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        bulk_upload_assignments(db_connection.
    finally:
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
