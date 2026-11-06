# main.py

import json
from sailpoint_api import SailPointAPI
import db_connector

def aggregate_unique_entitlements(roles_data, ap_data, ent_data):
    """
    Collects all unique entitlements from Roles, Access Profiles,
    and the main entitlement list to ensure a complete set.
    """
    print("Aggregating unique entitlements from all sources...")
    all_entitlements = {} # Use a dictionary to handle deduplication automatically

    # Helper to process a list of items (roles or APs)
    def process_items(items):
        for item in items:
            for ent in item.get('entitlements', []):
                ent_id = ent.get('id')
                if ent_id and ent_id not in all_entitlements:
                    all_entitlements[ent_id] = ent
    
    # Process entitlements from the main search call first
    if ent_data:
        for ent in ent_data:
            ent_id = ent.get('id')
            if ent_id and ent_id not in all_entitlements:
                all_entitlements[ent_id] = ent
                
    # Process nested entitlements from roles
    if roles_data:
        process_items(roles_data)
        
    # Process nested entitlements from access profiles
    if ap_data:
        process_items(ap_data)

    unique_ent_list = list(all_entitlements.values())
    print(f"Found a total of {len(unique_ent_list)} unique entitlements.")
    return unique_ent_list


def main():
    """
    Main function to orchestrate fetching and loading data and their relationships.
    """
    print("--- Starting Full Data Ingestion Process ---")
    
    # 1. Load Configuration
    try:
        with open('config.json') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found. Please ensure it exists.")
        return

    # 2. Initialize API and fetch all data first
    try:
        api = SailPointAPI(config.get("ISC"))
        roles_data = api.get_roles()
        access_profiles_data = api.get_access_profiles()
        raw_entitlements_data = api.get_entitlements()
    except Exception as e:
        print(f"FATAL: Could not initialize SailPoint API or fetch data. Aborting. Error: {e}")
        return
        
    # ===================================================================
    # === THE FIX IS HERE: Aggregate all entitlements before loading ===
    # This ensures our entitlements table is complete.
    all_unique_entitlements = aggregate_unique_entitlements(roles_data, access_profiles_data, raw_entitlements_data)
    # ===================================================================

    # 3. Connect to Database
    db_conn = db_connector.connect_to_db(config.get("Database"))
    if not db_conn:
        print("FATAL: Could not connect to the database. Aborting.")
        return
        
    # 4. Load data into tables
    try:
        print("\n--- Loading Primary Entities ---")
        db_connector.load_primary_data(db_conn, roles_data, 'CurrentRoleModel_Roles')
        db_connector.load_primary_data(db_conn, access_profiles_data, 'CurrentRoleModel_AccessProfiles')
        # Load the complete, de-duplicated list of entitlements
        db_connector.load_primary_data(db_conn, all_unique_entitlements, 'entitlements')

        # --- IMPORTANT: Create the ID map AFTER loading the complete entitlement set ---
        entitlement_id_map = db_connector.create_entitlement_id_map(db_conn)

        print("\n--- Loading Relationship Mappings ---")
        if entitlement_id_map:
            db_connector.load_mapping_data(db_conn, roles_data, 'CurrentRoleModel_RoleAccessProfiles')
            db_connector.load_mapping_data(db_conn, roles_data, 'CurrentRoleModel_RoleEntitlements', entitlement_id_map)
            # This call will now succeed because the map is complete
            db_connector.load_mapping_data(db_conn, access_profiles_data, 'CurrentRoleModel_AccessProfileEntitlements', entitlement_id_map)
        else:
            print("Skipping mapping table loads due to error in creating entitlement ID map.")

    finally:
        # 5. Close the database connection
        if db_conn and db_conn.is_connected():
            db_conn.close()
            print("\nDatabase connection closed.")
            
    print("\n--- Full Data Ingestion Process Finished ---")

if __name__ == "__main__":
    main()
