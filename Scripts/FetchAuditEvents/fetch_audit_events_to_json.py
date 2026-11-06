# fetch_audit_events_to_json.py

import json
import requests
import urllib3

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



# --- (Helper functions: get_all_results_with_search_after, flatten_json) ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
def get_all_results_with_search_after(url, headers, search_body):
    all_results, limit, sort_fields = [], 250, ["created", "id"]
    search_body["sort"], search_body["limit"] = sort_fields, limit
    print(f"Fetching all pages for index: {search_body.get('indices')} using searchAfter")
    while True:
        response = requests.post(url, headers=headers, json=search_body, verify=False)
        response.raise_for_status()
        page_results = response.json()
        if not page_results: print("  - Received an empty page."); break
        all_results.extend(page_results)
        total_count_header = response.headers.get('X-Total-Count', len(all_results))
        print(f"  - Fetched {len(page_results)} records. Total so far: {len(all_results)} / {total_count_header} (est.)")
        search_body["searchAfter"] = [page_results[-1].get(field) for field in sort_fields]
    return all_results

def flatten_json(y):
    out = {}
    def recurse(t, pk=''):
        if isinstance(t, dict):
            for k, v in t.items(): recurse(v, f"{pk}.{k}" if pk else k)
        elif isinstance(t, list): out[pk] = json.dumps(t)
        else: out[pk] = t
    recurse(y)
    return out

def fetch_and_save_events(access_token, base_url):
    print("\n--- Starting Audit Event Fetch Process ---")
    search_url = f"{base_url}/v3/search"
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    search_body = {
      "indices": ["events"],
      "query": { "query": "technicalName: (ENTITLEMENT_ADD_PASSED OR ROLE_ADD_PASSED OR ACCESS_PROFILE_ADD_PASSED OR ENTITLEMENT_REMOVE_PASSED OR ROLE_REMOVE_PASSED OR ACCESS_PROFILE_REMOVE_PASSED)" },
      "queryResultFilter": {"includes": ["id", "technicalName", "created", "attributes"]}
    }
    
    events = get_all_results_with_search_after(search_url, headers, search_body)
    if not events: print("No new audit events found."); return

    print(f"\nFetched {len(events)} events. Parsing for file export...")
    main_event_records, attribute_records = [], []
    
    for event in events:
        event_id = event.get('id')
        if not event_id: continue
        # We only load the raw data. No smart parsing here.
        main_event_records.append({"event_id": event_id, "technical_name": event.get('technicalName'), "created_datetime": event.get('created')})
        for key, value in flatten_json(event.get('attributes', {})).items():
            attribute_records.append({"event_id": event_id, "attribute_key": key, "attribute_value": str(value) if value is not None else None})

    with open("audit_events.json", 'w') as f: json.dump(main_event_records, f, indent=2)
    print(f"-> Saved {len(main_event_records)} records to audit_events.json")
    with open("audit_event_attributes.json", 'w') as f: json.dump(attribute_records, f, indent=2)
    print(f"-> Saved {len(attribute_records)} records to audit_event_attributes.json")

def main():
    try:
        with open('config.json') as f: config = json.load(f)
        client_id, client_secret, base_url = config.get("ClientId"), config.get("ClientSecret"), config.get("BaseURL")
    except Exception as e:
        print(f"Configuration Error: {e}"); exit()
    print("Authenticating...")
    try:
        token_url = f"{base_url}/oauth/token"
        payload = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
        access_token = requests.post(token_url, data=payload, verify=False).json().get("access_token")
    except Exception as e:
        print(f"ERROR fetching token: {e}"); exit()
    fetch_and_save_events(access_token, base_url)

if __name__ == "__main__":
    main()
