# enrich_and_update_from_audits.py

import json
import mysql.connector
from mysql.connector import Error
from collections import defaultdict

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

def main():
    """
    Main orchestrator. Fetches all audit data, processes it in chronological
    order in Python to determine the final state, and then performs bulk updates.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        # 1. Fetch all necessary data into memory
        print("--- Step 1: Fetching all required data from the database ---")
        
        # Get all relevant events, oldest first
        cursor.execute("SELECT event_id, technical_name, created_datetime FROM AuditEventLog WHERE technical_name LIKE '%_PASSED' ORDER BY created_datetime ASC")
        all_events = cursor.fetchall()
        print(f"  -> Fetched {len(all_events)} events.")
        
        # Get all attributes and store them in a lookup dictionary
        cursor.execute("SELECT event_id, attribute_key, attribute_value FROM AuditEventLog_Attributes")
        all_attributes_raw = cursor.fetchall()
        attributes_lookup = defaultdict(dict)
        for attr in all_attributes_raw:
            attributes_lookup[attr['event_id']][attr['attribute_key']] = attr['attribute_value']
        print(f"  -> Built attribute lookup for {len(attributes_lookup)} events.")

        # 2. Process events chronologically to find the final state ("Last Write Wins")
        print("\n--- Step 2: Processing events chronologically... ---")
        
        # These dictionaries will hold the FINAL state for each object
        final_role_updates = {}
        final_ap_updates = {}
        final_entitlement_updates = {}

        for event in all_events:
            event_id = event['event_id']
            tech_name = event['technical_name']
            created = event['created_datetime']
            attrs = attributes_lookup.get(event_id, {})
            
            # --- Logic for Roles ---
            if 'ROLE' in tech_name:
                # The ID is nested under 'role.id' in the flattened attributes
                role_id = attrs.get('role.id')
                if role_id:
                    if role_id not in final_role_updates: final_role_updates[role_id] = {}
                    if tech_name == 'ROLE_ADD_PASSED':
                        final_role_updates[role_id]['last_add_date'] = created
                        final_role_updates[role_id]['last_add_date_eventId'] = event_id
                    elif tech_name == 'ROLE_REMOVE_PASSED':
                        final_role_updates[role_id]['last_remove_date'] = created
                        final_role_updates[role_id]['last_remove_date_eventId'] = event_id

            # --- Logic for Access Profiles ---
            elif 'ACCESS_PROFILE' in tech_name:
                ap_id = attrs.get('accessProfile.id')
                if ap_id:
                    if ap_id not in final_ap_updates: final_ap_updates[ap_id] = {}
                    if tech_name == 'ACCESS_PROFILE_ADD_PASSED':
                        final_ap_updates[ap_id]['last_add_date'] = created
                        final_ap_updates[ap_id]['last_add_date_eventId'] = event_id
                    elif tech_name == 'ACCESS_PROFILE_REMOVE_PASSED':
                        final_ap_updates[ap_id]['last_remove_date'] = created
                        final_ap_updates[ap_id]['last_remove_date_eventId'] = event_id

            # --- Logic for Entitlements ---
            elif 'ENTITLEMENT' in tech_name:
                ent_name = attrs.get('attribute') or attrs.get('value')
                source_name = attrs.get('sourceName')
                if ent_name and source_name:
                    composite_key = (ent_name, source_name)
                    if composite_key not in final_entitlement_updates: final_entitlement_updates[composite_key] = {}
                    if tech_name == 'ENTITLEMENT_ADD_PASSED':
                        final_entitlement_updates[composite_key]['last_add_date'] = created
                        final_entitlement_updates[composite_key]['last_add_date_eventId'] = event_id
                    elif tech_name == 'ENTITLEMENT_REMOVE_PASSED':
                        final_entitlement_updates[composite_key]['last_remove_date'] = created
                        final_entitlement_updates[composite_key]['last_remove_date_eventId'] = event_id
        
        print("  -> Finished processing all events.")

        # 3. Prepare and execute bulk updates
        print("\n--- Step 3: Preparing and executing bulk updates ---")

        # Update Roles
        if final_role_updates:
            role_params = [(v.get('last_add_date'), v.get('last_add_date_eventId'), v.get('last_remove_date'), v.get('last_remove_date_eventId'), k) for k, v in final_role_updates.items()]
            cursor.executemany("UPDATE CurrentRoleModel_Roles SET last_add_date=%s, last_add_date_eventId=%s, last_remove_date=%s, last_remove_date_eventId=%s WHERE id=%s", role_params)
            print(f"  -> Updated {cursor.rowcount} records in CurrentRoleModel_Roles.")

        # Update Access Profiles
        if final_ap_updates:
            ap_params = [(v.get('last_add_date'), v.get('last_add_date_eventId'), v.get('last_remove_date'), v.get('last_remove_date_eventId'), k) for k, v in final_ap_updates.items()]
            cursor.executemany("UPDATE CurrentRoleModel_AccessProfiles SET last_add_date=%s, last_add_date_eventId=%s, last_remove_date=%s, last_remove_date_eventId=%s WHERE id=%s", ap_params)
            print(f"  -> Updated {cursor.rowcount} records in CurrentRoleModel_AccessProfiles.")

        # Update Entitlements
        if final_entitlement_updates:
            ent_params = [(v.get('last_add_date'), v.get('last_add_date_eventId'), v.get('last_remove_date'), v.get('last_remove_date_eventId'), k[0], k[1]) for k, v in final_entitlement_updates.items()]
            cursor.executemany("UPDATE entitlements SET last_add_date=%s, last_add_date_eventId=%s, last_remove_date=%s, last_remove_date_eventId=%s WHERE entitlement_name=%s AND source_name=%s", ent_params)
            print(f"  -> Updated {cursor.rowcount} records in entitlements.")

        db_connection.commit()
        print("\nProcess completed successfully.")
        
    except Error as e:
        print(f"An error occurred during the process: {e}"); db_connection.rollback()
    finally:
        cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
