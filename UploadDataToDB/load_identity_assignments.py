# load_identity_assignments.py

import json
from sailpoint_api import SailPointAPI
import mysql.connector
from mysql.connector import Error

def process_and_load_data(db_connection. identities_with_access):
    """
    Processes a list of IDENTITY objects, each with a nested 'access' array,
    and loads the data into all four target tables.
    This is the definitive parsing logic.
    """
    if not identities_with_access:
        print("No identity data received from API to process."); return

    # --- Step 1: Sort data in memory ---
    print("\nSorting all identity and access data...")
    identity_list, role_assignments, ap_assignments, ent_assignments = [], [], [], []

    # Loop through each IDENTITY object in the main list
    for identity in identities_with_access:
        identity_id = identity.get('id')
        uid = identity.get('name')
        
        # Ensure the top-level identity object is valid
        if not (identity_id and uid):
            print(f"  - WARNING: Skipping a record because it is missing a top-level ID or Name.")
            continue
        
        identity_list.append((identity_id, uid))
        
        # Loop through the nested 'access' list inside this identity
        for item in identity.get('access', []):
            item_type = item.get('type')
            item_id = item.get('id')
            item_name = item.get('name')
            
            if not (item_id and item_name and item_type):
                print(f"  - WARNING: Skipping a malformed access item for user {uid}. Data: {item}")
                continue

            # Append the assignment to the correct list
            if item_type == 'ROLE':
                role_assignments.append((identity_id, uid, item_id, item_name))
            elif item_type == 'ACCESS_PROFILE':
                ap_assignments.append((identity_id, uid, item_id, item_name))
            elif item_type == 'ENTITLEMENT':
                ent_assignments.append((identity_id, uid, item_id, item_name))
            
    print(f"Found {len(identity_list)} total identity records to process.")
    print(f"Sorted into: {len(role_assignments)} role assignments, "
          f"{len(ap_assignments)} AP assignments, "
          f"{len(ent_assignments)} entitlement assignments.")

    # --- Step 2: Bulk load data into database ---
    if not identity_list:
        print("\nNo valid data was parsed. Nothing to load into the database.")
        return

    cursor = db_connection.cursor()
    try:
        print("\nDisabling foreign keys for bulk load..."); cursor.execute("SET FOREIGN_KEY_CHECKS=0")

        print("Loading IdentityListSummary table..."); cursor.execute("TRUNCATE TABLE IdentityListSummary")
        sql_identities = "INSERT IGNORE INTO IdentityListSummary (IdentityID, UID) VALUES (%s, %s)"
        cursor.executemany(sql_identities, identity_list)
        print(f"Loaded {cursor.rowcount} unique identities.")

        print("Loading assignment tables...")
        cursor.execute("TRUNCATE TABLE IdentityRoleAssignments")
        if role_assignments:
            sql_roles = "INSERT IGNORE INTO IdentityRoleAssignments (IdentityID, UID, RoleID, RoleName) VALUES (%s, %s, %s, %s)"
            cursor.executemany(sql_roles, role_assignments); print(f"Loaded {cursor.rowcount} role assignments.")
        
        cursor.execute("TRUNCATE TABLE IdentityAccessProfileAssignments")
        if ap_assignments:
            sql_aps = "INSERT IGNORE INTO IdentityAccessProfileAssignments (IdentityID, UID, AccessProfileID, AccessProfileName) VALUES (%s, %s, %s, %s)"
            cursor.executemany(sql_aps, ap_assignments); print(f"Loaded {cursor.rowcount} access profile assignments.")
        
        cursor.execute("TRUNCATE TABLE IdentityEntitlementAssignments")
        if ent_assignments:
            sql_ents = "INSERT IGNORE INTO IdentityEntitlementAssignments (IdentityID, UID, EntitlementID, EntitlementName) VALUES (%s, %s, %s, %s)"
            cursor.executemany(sql_ents, ent_assignments); print(f"Loaded {cursor.rowcount} entitlement assignments.")
        
        db_connection.commit(); print("\nAll data successfully loaded.")
    except Error as e:
        print(f"\nDatabase Error during bulk load: {e}"); db_connection.rollback()
    finally:
        print("\nRe-enabling foreign key checks."); cursor.execute("SET FOREIGN_KEY_CHECKS=1"); cursor.close()

def main():
    """Main orchestrator using the efficient Search API with includes."""
    print("--- Starting Identity Assignment Ingestion Process ---")
    
    db_connection = None
    try:
        with open('config.json') as f: config = json.load(f)
        api = SailPointAPI(config.get("ISC"))
        db_connection = mysql.connector.connect(**config.get("Database"))
        print("Successfully connected to the database.")

        identities_with_access = api.get_all_identities_with_access()
        
        if identities_with_access:
            process_and_load_data(db_connection. identities_with_access)
        else:
            print("API returned no data. Halting process.")
        
    except Error as e:
        print(f"A database error occurred: {e}")
    except Exception as e:
        print(f"An application error occurred: {e}")
    finally:
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("\nDatabase connection closed.")
            
    print("\n--- Identity Assignment Ingestion Process Finished ---")

if __name__ == "__main__":
    main()
