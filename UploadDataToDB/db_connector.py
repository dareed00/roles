# db_connector.py

import mysql.connector
from mysql.connector import Error

def connect_to_db(db_config):
    """Establishes a connection to the database."""
    try:
        conn = mysql.connector.connect(**db_config)
        if conn.is_connected():
            print("Successfully connected to the database.")
            return conn
    except Error as e:
        print(f"FATAL: Error connecting to MySQL database: {e}")
        return None

def format_datetime(iso_date_string):
    """Converts ISO 8601 date string to MySQL DATETIME format."""
    if not iso_date_string:
        return None
    return iso_date_string.replace('T', ' ').split('.')[0].split('Z')[0]

def create_entitlement_id_map(conn):
    """
    Queries the entitlements table to create a mapping from the
    API's string ID (entitlement_id) to the database's integer ID (id).
    """
    print("Creating entitlement API-to-DB ID map...")
    id_map = {}
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, entitlement_id FROM entitlements")
        for (db_id, api_id) in cursor:
            id_map[api_id] = db_id
        print(f"Successfully created map for {len(id_map)} entitlements.")
        return id_map
    except Error as e:
        print(f"ERROR: Could not create entitlement ID map: {e}")
        return None
    finally:
        cursor.close()

def load_mapping_data(conn, source_data, table_name, entitlement_id_map=None):
    """Loads data into the various mapping tables."""
    if not source_data:
        print(f"No source data to process for mapping table: {table_name}")
        return

    cursor = conn.cursor()
    records_to_insert = []
    try:
        print(f"Processing relationships for {table_name}...")
        cursor.execute(f"TRUNCATE TABLE {table_name}")

        if table_name == 'CurrentRoleModel_RoleAccessProfiles':
            sql = "INSERT INTO CurrentRoleModel_RoleAccessProfiles (role_id, role_name, access_profile_id, access_profile_name) VALUES (%s, %s, %s, %s)"
            for role in source_data:
                for ap in role.get('accessProfiles', []):
                    records_to_insert.append((role.get('id'), role.get('name'), ap.get('id'), ap.get('name')))

        elif table_name == 'CurrentRoleModel_RoleEntitlements':
            if not entitlement_id_map: return
            sql = "INSERT INTO CurrentRoleModel_RoleEntitlements (role_id, role_name, entitlement_id, entitlement_name) VALUES (%s, %s, %s, %s)"
            for role in source_data:
                for ent in role.get('entitlements', []):
                    db_ent_id = entitlement_id_map.get(ent.get('id'))
                    if db_ent_id:
                        records_to_insert.append((role.get('id'), role.get('name'), db_ent_id, ent.get('name')))

        elif table_name == 'CurrentRoleModel_AccessProfileEntitlements':
            if not entitlement_id_map: return
            sql = "INSERT INTO CurrentRoleModel_AccessProfileEntitlements (access_profile_id, access_profile_name, entitlement_id, entitlement_name) VALUES (%s, %s, %s, %s)"
            for ap in source_data:
                for ent in ap.get('entitlements', []):
                    db_ent_id = entitlement_id_map.get(ent.get('id'))
                    if db_ent_id:
                        records_to_insert.append((ap.get('id'), ap.get('name'), db_ent_id, ent.get('name')))

        if records_to_insert:
            cursor.executemany(sql, records_to_insert)
            conn.commit()
            print(f"Successfully loaded {cursor.rowcount} records into {table_name}.")
    except Error as e:
        print(f"Database Error on commit for {table_name}: {e}"); conn.rollback()
    finally:
        cursor.close()

def load_primary_data(conn, data, table_name):
    """
    Loads data into primary tables. Includes new fields for Roles and APs,
    but keeps the entitlements insert simple.
    """
    if not data:
        print(f"No primary data to load for table: {table_name}"); return
        
    cursor = conn.cursor()
    try:
        print(f"Disabling foreign key checks for {table_name}..."); cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        print(f"Clearing old data from {table_name}..."); cursor.execute(f"TRUNCATE TABLE {table_name}")

        if table_name == 'CurrentRoleModel_Roles':
            sql = """INSERT INTO CurrentRoleModel_Roles (id, name, description, enabled, requestable, owner_id, owner_name, created, modified) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            values_to_insert = []
            for item in data:
                owner = item.get('owner', {})
                values_to_insert.append((item.get('id'), item.get('name'), item.get('description'), item.get('enabled'), item.get('requestable'), owner.get('id'), owner.get('name'), format_datetime(item.get('created')), format_datetime(item.get('modified'))))
            cursor.executemany(sql, values_to_insert)
                
        elif table_name == 'CurrentRoleModel_AccessProfiles':
            sql = """INSERT INTO CurrentRoleModel_AccessProfiles (id, name, description, enabled, requestable, owner_id, owner_name, source_id, source_name, created, modified) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            values_to_insert = []
            for item in data:
                owner = item.get('owner', {})
                source = item.get('source', {})
                values_to_insert.append((item.get('id'), item.get('name'), item.get('description'), item.get('enabled'), item.get('requestable'), owner.get('id'), owner.get('name'), source.get('id'), source.get('name'), format_datetime(item.get('created')), format_datetime(item.get('modified'))))
            cursor.executemany(sql, values_to_insert)

        elif table_name == 'entitlements':
            # ===================================================================
            # === THE FIX IS HERE: Reverted to the original, simpler INSERT statement ===
            sql = """INSERT IGNORE INTO entitlements (entitlement_id, entitlement_name, source_name, description, owner_name) 
                     VALUES (%s, %s, %s, %s, %s)"""
            values_to_insert = []
            for item in data:
                source = item.get('source', {})
                owner = item.get('owner', {})
                values_to_insert.append((item.get('id'), item.get('name'), source.get('name'), item.get('description'), owner.get('name', '')))
            cursor.executemany(sql, values_to_insert)
            # ===================================================================

        conn.commit()
        print(f"Successfully loaded {cursor.rowcount} records into {table_name}.")

    except Error as e:
        print(f"Database Error on commit for {table_name}: {e}"); conn.rollback()
    finally:
        print(f"Re-enabling foreign key checks for {table_name}."); cursor.execute("SET FOREIGN_KEY_CHECKS=1"); cursor.close()

