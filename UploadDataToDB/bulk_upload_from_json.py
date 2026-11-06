import json
import mysql.connector
from mysql.connector import Error

def get_db_connection(config):
    """Establishes a database connection."""
    try:
        conn = mysql.connector.connect(**config)
        if conn.is_connected():
            print("Successfully connected to the database.")
            return conn
    except Error as e:
        print(f"FATAL: Error connecting to MySQL database: {e}"); return None

def format_datetime(iso_date_string):
    """Safely converts ISO 8601 date string to MySQL DATETIME format."""
    if not iso_date_string: return None
    return iso_date_string.replace('T', ' ').split('.')[0].split('Z')[0]

def load_primary_tables(cursor, data_map):
    """Loads data into the main entity tables."""
    print("\n--- Stage 1: Loading Primary Entity Tables ---")
    
    # Load Roles
    if data_map.get('roles'):
        print("Loading CurrentRoleModel_Roles...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_Roles")
        records = [ (item.get('id'), item.get('name'), item.get('description'), item.get('enabled'), item.get('requestable'), item.get('owner',{}).get('id'), item.get('owner',{}).get('name'), format_datetime(item.get('created')), format_datetime(item.get('modified'))) for item in data_map['roles'] ]
        sql = "INSERT INTO CurrentRoleModel_Roles (id, name, description, enabled, requestable, owner_id, owner_name, created, modified) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} roles.")

    # Load Access Profiles
    if data_map.get('access_profiles'):
        print("Loading CurrentRoleModel_AccessProfiles...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_AccessProfiles")
        records = [ (item.get('id'), item.get('name'), item.get('description'), item.get('enabled'), item.get('requestable'), item.get('owner',{}).get('id'), item.get('owner',{}).get('name'), item.get('source',{}).get('id'), item.get('source',{}).get('name'), format_datetime(item.get('created')), format_datetime(item.get('modified'))) for item in data_map['access_profiles'] ]
        sql = "INSERT INTO CurrentRoleModel_AccessProfiles (id, name, description, enabled, requestable, owner_id, owner_name, source_id, source_name, created, modified) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} access profiles.")

    # Load Entitlements
    if data_map.get('entitlements'):
        print("Loading entitlements...")
        cursor.execute("TRUNCATE TABLE entitlements")
        records = [ (item.get('id'), item.get('name'), item.get('source',{}).get('name'), item.get('description'), item.get('owner',{}).get('name')) for item in data_map['entitlements'] ]
        sql = "INSERT INTO entitlements (entitlement_id, entitlement_name, source_name, description, owner_name) VALUES (%s, %s, %s, %s, %s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} entitlements.")

    # Load Identities
    if data_map.get('identities'):
        print("Loading Identities...")
        cursor.execute("TRUNCATE TABLE Identities")
        records = [ (item.get('id'), item.get('name'), item.get('email'), item.get('firstName'), item.get('lastName'), item.get('displayName'), item.get('inactive'), item.get('isManager'), item.get('status'), item.get('employeeNumber'), format_datetime(item.get('created')), format_datetime(item.get('modified')), item.get('accountCount')) for item in data_map['identities'] ]
        sql = "INSERT INTO Identities (id, name, email, firstName, lastName, displayName, inactive, isManager, status, employeeNumber, created, modified, accountCount) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} identities.")

def load_relationship_tables(cursor, data_map):
    """Loads data into the relationship and nested tables."""
    print("\n--- Stage 2: Loading Relationship & Nested Tables ---")
    
    # Load Identity Accounts
    if data_map.get('identities'):
        print("Loading Identity_Accounts...")
        cursor.execute("TRUNCATE TABLE Identity_Accounts")
        records = [ (identity.get('id'), account.get('id'), account.get('name'), account.get('accountId'), account.get('source',{}).get('id'), account.get('source',{}).get('name'), format_datetime(account.get('created')), account.get('privileged')) for identity in data_map['identities'] for account in identity.get('accounts', []) ]
        sql = "INSERT INTO Identity_Accounts (identity_id, account_id, account_name, native_identity, source_id, source_name, created, privileged) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} account records.")

    # Load Role -> AP mappings
    if data_map.get('roles'):
        print("Loading CurrentRoleModel_RoleAccessProfiles...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_RoleAccessProfiles")
        records = [ (role.get('id'), role.get('name'), ap.get('id'), ap.get('name')) for role in data_map['roles'] for ap in role.get('accessProfiles', []) ]
        sql = "INSERT INTO CurrentRoleModel_RoleAccessProfiles (role_id, role_name, access_profile_id, access_profile_name) VALUES (%s,%s,%s,%s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} Role -> AP mappings.")
            
    # Load Role -> Entitlement mappings
    if data_map.get('roles'):
        print("Loading CurrentRoleModel_RoleEntitlements...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_RoleEntitlements")
        records = [ (role.get('id'), role.get('name'), ent.get('id'), ent.get('name')) for role in data_map['roles'] for ent in role.get('entitlements', []) ]
        sql = "INSERT INTO CurrentRoleModel_RoleEntitlements (role_id, role_name, entitlement_id, entitlement_name) VALUES (%s,%s,%s,%s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} Role -> Entitlement mappings.")

    # Load AP -> Entitlement mappings
    if data_map.get('access_profiles'):
        print("Loading CurrentRoleModel_AccessProfileEntitlements...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_AccessProfileEntitlements")
        records = [ (ap.get('id'), ap.get('name'), ent.get('id'), ent.get('name')) for ap in data_map['access_profiles'] for ent in ap.get('entitlements', []) ]
        sql = "INSERT INTO CurrentRoleModel_AccessProfileEntitlements (access_profile_id, access_profile_name, entitlement_id, entitlement_name) VALUES (%s,%s,%s,%s)"
        cursor.executemany(sql, records)
        print(f"-> Loaded {cursor.rowcount} AP -> Entitlement mappings.")

def main():
    """Main orchestrator for reading all JSON files and loading them into the database."""
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    print("--- Reading all source JSON files ---")
    data_map = {}
    for key in ["roles", "access_profiles", "entitlements", "identities"]:
        file_name = f"{key}.json"
        try:
            with open(file_name, 'r') as f: data_map[key] = json.load(f)
            print(f"Successfully read {file_name}")
        except FileNotFoundError:
            print(f"WARNING: {file_name} not found. Some tables will be skipped.")
            data_map[key] = None

    conn = get_db_connection(config.get("Database"))
    if not conn: return
    
    cursor = conn.cursor()
    try:
        # ===================================================================
        # === THE FIX IS HERE ===
        print("\nDisabling foreign key checks for bulk load...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        # ===================================================================

        # Run the loading process
        load_primary_tables(cursor, data_map)
        load_relationship_tables(cursor, data_map)
        
        conn.commit()
        print("\nAll data successfully loaded and committed.")

    except Error as e:
        print(f"An error occurred during the loading process: {e}")
        conn.rollback()

    finally:
        # ===================================================================
        # === AND HERE: Ensure checks are ALWAYS re-enabled ===
        print("Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        # ===================================================================
        cursor.close()
        if conn and conn.is_connected():
            conn.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
