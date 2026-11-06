# update_entity_audit_dates.py

import json
import mysql.connector
from mysql.connector import Error
from collections import defaultdict

def get_db_connection(config):
    """Establishes a database connection."""
    try:
        db_connection = mysql.connector.connect(**config)
        if db_connection.is_connected():
            print("Successfully connected to the database.")
            return conn
    except Error as e:
        print(f"FATAL: Error connecting to MySQL database: {e}"); return None

def main():
    """
    Main orchestrator. Fetches all audit data, processes it in chronological
    order, and performs bulk updates using the correct keys for each entity type.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        # Step 1: Fetch all necessary data into memory.
        print("--- Step 1: Fetching all required data from the database ---")
        
        cursor.execute("SELECT event_id, technical_name, created_datetime FROM AuditEventLog WHERE technical_name LIKE '%_PASSED' ORDER BY created_datetime ASC")
        all_events = cursor.fetchall()
        print(f"  -> Fetched {len(all_events)} events in chronological order.")
        
        cursor.execute("SELECT event_id, attribute_key, attribute_value FROM AuditEventLog_Attributes")
        all_attributes_raw = cursor.fetchall()
        attributes_lookup = defaultdict(dict)
        for attr in all_attributes_raw:
            attributes_lookup[attr['event_id']][attr['attribute_key']] = attr['attribute_value']
        print(f"  -> Built attribute lookup for {len(attributes_lookup)} events.")

        # Step 2: Process events chronologically to find the final state.
        print("\n--- Step 2: Processing events chronologically in memory... ---")
        
        final_role_updates = {}
        final_ap_updates = {}
        final_entitlement_updates = {}

        for event in all_events:
            event_id = event['event_id']
            tech_name = event['technical_name']
            created = event['created_datetime']
            attrs = attributes_lookup.get(event_id, {})
            
            # For all types, 'attributeValue' holds the name of the object.
            obj_name = attrs.get('attributeValue')
            if not obj_name: continue # Skip if the primary name is missing

            if 'ROLE' in tech_name:
                # The key for the dictionary is the Role Name.
                if obj_name not in final_role_updates: final_role_updates[obj_name] = {}
                if 'ADD' in tech_name:
                    final_role_updates[obj_name]['last_add_date'] = created
                    final_role_updates[obj_name]['last_add_date_eventId'] = event_id
                elif 'REMOVE' in tech_name:
                    final_role_updates[obj_name]['last_remove_date'] = created
                    final_role_updates[obj_name]['last_remove_date_eventId'] = event_id

            elif 'ACCESS_PROFILE' in tech_name:
                source_name = attrs.get('sourceName')
                if source_name:
                    composite_key = (obj_name, source_name)
                    if composite_key not in final_ap_updates: final_ap_updates[composite_key] = {}
                    if 'ADD' in tech_name:
                        final_ap_updates[composite_key]['last_add_date'] = created
                        final_ap_updates[composite_key]['last_add_date_eventId'] = event_id
                    elif 'REMOVE' in tech_name:
                        final_ap_updates[composite_key]['last_remove_date'] = created
                        final_ap_updates[composite_key]['last_remove_date_eventId'] = event_id

            elif 'ENTITLEMENT' in tech_name:
                source_name = attrs.get('sourceName')
                if source_name:
                    composite_key = (obj_name, source_name)
                    if composite_key not in final_entitlement_updates: final_entitlement_updates[composite_key] = {}
                    if 'ADD' in tech_name:
                        final_entitlement_updates[composite_key]['last_add_date'] = created
                        final_entitlement_updates[composite_key]['last_add_date_eventId'] = event_id
                    elif 'REMOVE' in tech_name:
                        final_entitlement_updates[composite_key]['last_remove_date'] = created
                        final_entitlement_updates[composite_key]['last_remove_date_eventId'] = event_id
        
        print(f"  -> Finished processing. Found final states for {len(final_role_updates)} roles, {len(final_ap_updates)} APs, and {len(final_entitlement_updates)} entitlements.")

        # Step 3: Prepare and execute bulk updates.
        print("\n--- Step 3: Preparing and executing bulk database updates ---")

        # ===================================================================
        # === THE FIX IS HERE ===
        # Update Roles by NAME, not ID.
        # ===================================================================
        if final_role_updates:
            role_params = [(v.get('last_add_date'), v.get('last_add_date_eventId'), v.get('last_remove_date'), v.get('last_remove_date_eventId'), k) for k, v in final_role_updates.items()]
            cursor.executemany("UPDATE CurrentRoleModel_Roles SET last_add_date=%s, last_add_date_eventId=%s, last_remove_date=%s, last_remove_date_eventId=%s WHERE name=%s", role_params)
            print(f"  -> Updated {cursor.rowcount} records in CurrentRoleModel_Roles.")

        # Update Access Profiles by NAME and SOURCE_NAME.
        if final_ap_updates:
            ap_params = [(v.get('last_add_date'), v.get('last_add_date_eventId'), v.get('last_remove_date'), v.get('last_remove_date_eventId'), k[0], k[1]) for k, v in final_ap_updates.items()]
            cursor.executemany("UPDATE CurrentRoleModel_AccessProfiles SET last_add_date=%s, last_add_date_eventId=%s, last_remove_date=%s, last_remove_date_eventId=%s WHERE name=%s AND source_name=%s", ap_params)
            print(f"  -> Updated {cursor.rowcount} records in CurrentRoleModel_AccessProfiles.")

        # Update Entitlements by NAME and SOURCE_NAME.
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
