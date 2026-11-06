# master_bulk_loader.py

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


def format_datetime(iso_date_string):
    """Safely converts ISO 8601 date string to MySQL DATETIME format."""
    if not iso_date_string: return None
    return iso_date_string.replace('T', ' ').split('.')[0].split('Z')[0]

def load_primary_entities(cursor, data_map):
    """Loads Roles, Access Profiles, and Entitlements."""
    # This function is correct and remains unchanged.
    print("\n--- Stage 1: Loading Primary Entities ---")
    if data_map.get('roles'):
        print("Loading CurrentRoleModel_Roles...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_Roles")
        records = [ (item.get('id'), item.get('name'), item.get('description'), item.get('enabled'), item.get('requestable'), item.get('owner',{}).get('id'), item.get('owner',{}).get('name'), format_datetime(item.get('created')), format_datetime(item.get('modified'))) for item in data_map['roles'] ]
        cursor.executemany("INSERT INTO CurrentRoleModel_Roles (id, name, description, enabled, requestable, owner_id, owner_name, created, modified) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", records)
        print(f"-> Loaded {cursor.rowcount} roles.")
    if data_map.get('access_profiles'):
        print("Loading CurrentRoleModel_AccessProfiles...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_AccessProfiles")
        records = [ (item.get('id'), item.get('name'), item.get('description'), item.get('enabled'), item.get('requestable'), item.get('owner',{}).get('id'), item.get('owner',{}).get('name'), item.get('source',{}).get('id'), item.get('source',{}).get('name'), format_datetime(item.get('created')), format_datetime(item.get('modified'))) for item in data_map['access_profiles'] ]
        cursor.executemany("INSERT INTO CurrentRoleModel_AccessProfiles (id, name, description, enabled, requestable, owner_id, owner_name, source_id, source_name, created, modified) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", records)
        print(f"-> Loaded {cursor.rowcount} access profiles.")
    if data_map.get('entitlements'):
        print("Loading entitlements...")
        cursor.execute("TRUNCATE TABLE entitlements")
        records = [ (item.get('id'), item.get('name'), item.get('source',{}).get('name'), item.get('description'), item.get('owner',{}).get('name')) for item in data_map['entitlements'] ]
        cursor.executemany("INSERT INTO entitlements (entitlement_id, entitlement_name, source_name, description, owner_name) VALUES (%s, %s, %s, %s, %s)", records)
        print(f"-> Loaded {cursor.rowcount} entitlements.")

def load_complex_identities(cursor, data_map):
    """Loads the main Identities table and its two nested child tables."""
    # This function is correct and remains unchanged.
    if not data_map.get('identities'):
        print("\nIdentities file not found. Skipping Stage 2.")
        return
    print("\n--- Stage 2: Loading Complex Identity Data ---")
    identity_data = data_map['identities']
    identity_records, account_records, attribute_records = [], [], []
    for item in identity_data:
        identity_id = item.get('id');
        if not identity_id: continue
        identity_records.append((identity_id, item.get('name'), item.get('email'), item.get('firstName'), item.get('lastName'), item.get('displayName'), item.get('inactive'), item.get('isManager'), item.get('status'), item.get('employeeNumber'), format_datetime(item.get('created')), format_datetime(item.get('modified')), item.get('accountCount')))
        for account in item.get('accounts', []):
            account_records.append((identity_id, account.get('id'), account.get('name'), account.get('accountId'), account.get('source',{}).get('id'), account.get('source',{}).get('name'), format_datetime(account.get('created')), account.get('privileged')))
        for attr_name, attr_value in item.get('attributes', {}).items():
            attribute_records.append((identity_id, attr_name, str(attr_value)))
    print("Loading Identities table..."); cursor.execute("TRUNCATE TABLE Identities");
    cursor.executemany("INSERT INTO Identities (id, name, email, firstName, lastName, displayName, inactive, isManager, status, employeeNumber, created, modified, accountCount) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", identity_records)
    print(f"-> Loaded {cursor.rowcount} records.")
    print("Loading Identity_Accounts table..."); cursor.execute("TRUNCATE TABLE Identity_Accounts");
    cursor.executemany("INSERT INTO Identity_Accounts (identity_id, account_id, account_name, native_identity, source_id, source_name, created, privileged) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", account_records)
    print(f"-> Loaded {cursor.rowcount} records.")
    print("Loading Identity_Attributes table..."); cursor.execute("TRUNCATE TABLE Identity_Attributes");
    cursor.executemany("INSERT INTO Identity_Attributes (identity_id, attribute_name, attribute_value) VALUES (%s, %s, %s)", attribute_records)
    print(f"-> Loaded {cursor.rowcount} records.")
    
def load_relationship_tables(cursor, data_map):
    """Loads the mappings between Roles, APs, and Entitlements."""
    # This function is correct and remains unchanged.
    print("\n--- Stage 3: Loading Relationship Tables ---")
    if data_map.get('roles'):
        print("Loading CurrentRoleModel_RoleAccessProfiles..."); cursor.execute("TRUNCATE TABLE CurrentRoleModel_RoleAccessProfiles")
        records = [ (role.get('id'), role.get('name'), ap.get('id'), ap.get('name')) for role in data_map['roles'] for ap in role.get('accessProfiles', []) ]
        cursor.executemany("INSERT INTO CurrentRoleModel_RoleAccessProfiles (role_id, role_name, access_profile_id, access_profile_name) VALUES (%s,%s,%s,%s)", records)
        print(f"-> Loaded {cursor.rowcount} Role -> AP mappings.")
    if data_map.get('roles'):
        print("Loading CurrentRoleModel_RoleEntitlements..."); cursor.execute("TRUNCATE TABLE CurrentRoleModel_RoleEntitlements")
        records = [ (role.get('id'), role.get('name'), ent.get('id'), ent.get('name')) for role in data_map['roles'] for ent in role.get('entitlements', []) ]
        cursor.executemany("INSERT INTO CurrentRoleModel_RoleEntitlements (role_id, role_name, entitlement_id, entitlement_name) VALUES (%s,%s,%s,%s)", records)
        print(f"-> Loaded {cursor.rowcount} Role -> Entitlement mappings.")
    if data_map.get('access_profiles'):
        print("Loading CurrentRoleModel_AccessProfileEntitlements..."); cursor.execute("TRUNCATE TABLE CurrentRoleModel_AccessProfileEntitlements")
        records = [ (ap.get('id'), ap.get('name'), ent.get('id'), ent.get('name')) for ap in data_map['access_profiles'] for ent in ap.get('entitlements', []) ]
        cursor.executemany("INSERT INTO CurrentRoleModel_AccessProfileEntitlements (access_profile_id, access_profile_name, entitlement_id, entitlement_name) VALUES (%s,%s,%s,%s)", records)
        print(f"-> Loaded {cursor.rowcount} AP -> Entitlement mappings.")

def load_assignment_tables(cursor, data_map):
    """Loads the identity-to-access assignment tables with de-duplication."""
    print("\n--- Stage 4: Loading Identity Assignment Tables ---")
    
    # ===================================================================
    # === THE FIX IS HERE: Re-introducing the de-duplication logic ===
    # ===================================================================
    configs = {
        "identity_role_assignments": {"table": "IdentityRoleAssignments", "sql": "INSERT INTO IdentityRoleAssignments (identity_id, identity_name, role_id, role_name, standalone) VALUES (%s,%s,%s,%s,%s)", "id_indices": [0, 2]},
        "identity_ap_assignments": {"table": "IdentityAccessProfileAssignments", "sql": "INSERT INTO IdentityAccessProfileAssignments (identity_id, identity_name, access_profile_id, access_profile_name, standalone) VALUES (%s,%s,%s,%s,%s)", "id_indices": [0, 2]},
        "identity_entitlement_assignments": {"table": "IdentityEntitlementAssignments", "sql": "INSERT INTO IdentityEntitlementAssignments (identity_id, identity_name, entitlement_id, entitlement_name, standalone) VALUES (%s,%s,%s,%s,%s)", "id_indices": [0, 2]}
    }
    
    for key, config in configs.items():
        if data_map.get(key):
            table_name, sql, id_indices = config['table'], config['sql'], config['id_indices']
            print(f"Loading {table_name}...")
            cursor.execute(f"TRUNCATE TABLE {table_name}")
            
            # De-duplicate records in memory before attempting to insert
            unique_records = {}
            id1_index, id2_index = id_indices
            
            print(f"  - Parsing and de-duplicating {len(data_map[key])} raw records...")
            for item in data_map[key]:
                access_item = item.get('access', {})
                # Use name as fallback for ID, as established previously
                access_id = access_item.get('id') or access_item.get('name')
                identity_id = item.get('identity_id')
                
                if not identity_id or not access_id:
                    print(f"  - WARNING: Skipping record with missing critical IDs: {item}")
                    continue

                # Create a unique key (e.g., 'identityID-entitlementID')
                unique_key = f"{identity_id}-{access_id}"
                
                # If we haven't seen this key before, create and store the full record tuple.
                if unique_key not in unique_records:
                    unique_records[unique_key] = (identity_id, item.get('identity_name'), access_id, access_item.get('name'), access_item.get('standalone'))

            records_to_insert = list(unique_records.values())

            print(f"  - Preparing to insert {len(records_to_insert)} unique records...")
            cursor.executemany(sql, records_to_insert)
            print(f"-> Loaded {cursor.rowcount} records.")

def main():
    """Main orchestrator for reading all JSON files and loading them into the database."""
    # ... (This function is correct and remains unchanged) ...
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return
    print("--- Reading all source JSON files into memory ---")
    data_map = {}
    json_files = ["roles.json", "access_profiles.json", "entitlements.json", "identities.json", "identity_role_assignments.json", "identity_ap_assignments.json", "identity_entitlement_assignments.json"]
    for file_name in json_files:
        try:
            with open(file_name, 'r') as f: data_map[file_name.split('.')[0]] = json.load(f)
            print(f"Successfully read {file_name}")
        except FileNotFoundError:
            print(f"WARNING: {file_name} not found. Some loading stages will be skipped.")
            data_map[file_name.split('.')[0]] = None
   db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        print("\nDisabling foreign key checks for full bulk load...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        load_primary_entities(cursor, data_map)
        load_complex_identities(cursor, data_map)
        load_relationship_tables(cursor, data_map)
        load_assignment_tables(cursor, data_map) # This will now work
        db_connection.commit()
        print("\nMaster bulk load process completed successfully.")
    except Error as e:
        print(f"An error occurred during the loading process: {e}"); db_connection.rollback()
    finally:
        print("Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
