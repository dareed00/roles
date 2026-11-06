# fetch_audit_events.py

import json
import mysql.connector
from mysql.connector import Error

# NOTE: This script is now self-contained and does not need to import from sailpoint_api.py
import requests
import urllib3

# Suppress warnings for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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


def get_all_results_with_search_after(url, headers, search_body):
    """
    Handles pagination robustly using the 'searchAfter' method, which is the
    correct and most efficient way for this API endpoint.
    """
    all_results = []
    limit = 250
    
    # Best practice for searchAfter: use a timestamp and a unique ID as a tie-breaker.
    sort_fields = ["created", "id"]
    search_body["sort"] = sort_fields
    search_body["limit"] = limit

    print(f"Fetching all pages for index: {search_body.get('indices')} using searchAfter")
    
    while True:
        print(f"  - Making API call...")
        if "searchAfter" in search_body:
            print(f"    - Using searchAfter: {search_body['searchAfter']}")

        response = requests.post(url, headers=headers, json=search_body, verify=False)
        response.raise_for_status()
        
        page_results = response.json()
        
        if not page_results:
            print("  - Received an empty page. All results have been fetched.")
            break
            
        all_results.extend(page_results)
        
        total_count_header = response.headers.get('X-Total-Count', len(all_results))
        print(f"  - Fetched {len(page_results)} records. Total so far: {len(all_results)} / {total_count_header} (est.)")

        last_record = page_results[-1]
        
        # Event search results are not nested in _source, so we access keys directly
        search_after_values = [last_record.get(field) for field in sort_fields]
        search_body["searchAfter"] = search_after_values

    return all_results

def format_datetime(iso_date_string):
    """Safely converts ISO 8601 date string to MySQL DATETIME format."""
    if not iso_date_string: return None
    return iso_date_string.replace('T', ' ').split('.')[0].split('Z')[0]

def flatten_json(y):
    """A helper function to flatten a nested JSON object into a single-level dictionary."""
    out = {}
    def recurse(t, parent_key=''):
        if isinstance(t, dict):
            for k, v in t.items():
                new_key = parent_key + '.' + k if parent_key else k
                recurse(v, new_key)
        elif isinstance(t, list):
            # For simplicity in this context, we will just serialize lists to JSON strings.
            out[parent_key] = json.dumps(t)
        else:
            out[parent_key] = t
    recurse(y)
    return out

def fetch_and_load_events(access_token, base_url, db_connection.:
    """
    Fetches access change events, loads the main event data, and normalizes
    the attributes into a separate, dedicated table.
    """
    print("\n--- Starting Audit Event Fetch Process ---")
    
    search_url = f"{base_url}/v3/search"
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    search_body = {
      "indices": ["events"],
      "query": { "query": "technicalName: (ENTITLEMENT_ADD_PASSED OR ROLE_ADD_PASSED OR ACCESS_PROFILE_ADD_PASSED OR ENTITLEMENT_REMOVE_PASSED OR ROLE_REMOVE_PASSED OR ACCESS_PROFILE_REMOVE_PASSED)" }
      # The sort field is now added by the pagination function
    }
    
    # Call the corrected, self-contained pagination function
    events = get_all_results_with_search_after(search_url, headers, search_body)

    if not events:
        print("No new audit events found to process."); return

    print(f"\nFetched a total of {len(events)} events. Preparing for database load...")
    main_event_records = []
    attribute_records = []
    
    for event in events:
        event_id = event.get('id')
        if not event_id: continue

        attributes = event.get('attributes', {}); actor = event.get('actor', {}); target = event.get('target', {})
        access_item = attributes.get('access', {})
        
        main_event_records.append((
            event_id, event.get('technicalName'), format_datetime(event.get('created')),
            actor.get('id'), actor.get('name'), target.get('id'), target.get('name'),
            access_item.get('id'), access_item.get('name'), access_item.get('type')
        ))

        flat_attributes = flatten_json(attributes)
        for key, value in flat_attributes.items():
            str_value = str(value) if value is not None else None
            attribute_records.append((event_id, key, str_value))

    cursor = db_connection.cursor()
    try:
        print("\nUploading main event data to AuditEventLog table...")
        cursor.execute("TRUNCATE TABLE AuditEventLog")
        main_insert_query = "INSERT INTO AuditEventLog (event_id, technical_name, created_datetime, actor_id, actor_name, target_id, target_name, object_id, object_name, object_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.executemany(main_insert_query, main_event_records)
        print(f"-> Successfully loaded {cursor.rowcount} main event records.")

        print("\nUploading normalized attributes to AuditEventLog_Attributes table...")
        cursor.execute("TRUNCATE TABLE AuditEventLog_Attributes")
        attr_insert_query = "INSERT INTO AuditEventLog_Attributes (event_id, attribute_key, attribute_value) VALUES (%s, %s, %s)"
        cursor.executemany(attr_insert_query, attribute_records)
        print(f"-> Successfully loaded {cursor.rowcount} attribute records.")
        
        db_connection.commit()
        print("\nEvent data load complete.")

    except Error as e:
        print(f"Database Error during event upload: {e}"); db_connection.rollback()
    finally:
        cursor.close()

def main():
    """Main orchestrator for this script."""
    try:
        with open('config.json') as f: config = json.load(f)
        client_id, client_secret, base_url = config.get("ClientId"), config.get("ClientSecret"), config.get("BaseURL")
    except Exception as e:
        print(f"Configuration Error: {e}"); exit()

    print("Attempting to fetch access token...")
    try:
        token_url = f"{base_url}/oauth/token"
        payload = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
        response = requests.post(token_url, data=payload, verify=False)
        access_token = response.json().get("access_token")
        print("Successfully obtained access token.")
    except Exception as e:
        print(f"ERROR fetching access token: {e}"); exit()

    db_connection = None
    try:
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
        fetch_and_load_events(access_token, base_url, db_connection.
    except Exception as e:
        print(f"An application error occurred: {e}")
    finally:
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
