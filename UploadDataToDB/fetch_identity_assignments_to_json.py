import requests
import json
import urllib3

# --- Shared Functions ---
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
    Handles pagination robustly using the 'searchAfter' method.
    """
    all_results = []
    limit = 250
    # A unique field like 'id' is crucial as a tie-breaker for sorting.
    sort_fields = ["name", "id"]
    search_body["sort"] = sort_fields
    search_body["limit"] = limit

    print(f"Fetching all pages for index: {search_body.get('indices')} using searchAfter")
    
    while True:
        print(f"  - Making API call...")
        if "searchAfter" in search_body: print(f"    - Using searchAfter: {search_body['searchAfter']}")

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
        # Note: Identity search results are NOT nested in _source, so we access directly.
        search_after_values = [last_record.get(field) for field in sort_fields]
        search_body["searchAfter"] = search_after_values

    return all_results

def main():
    """Main function to fetch all identity assignments and save them to multiple JSON files."""
    try:
        with open('config.json') as f: config = json.load(f)
        client_id, client_secret, base_url = config.get("ClientId"), config.get("ClientSecret"), config.get("BaseURL")
        if not all([client_id, client_secret, base_url]): raise ValueError("Config is missing credentials")
    except Exception as e:
        print(f"Configuration Error: {e}"); exit()

    print("Attempting to fetch access token...")
    try:
        token_url = f"{base_url}/oauth/token"
        payload = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
        response = requests.post(token_url, data=payload, verify=False)
        response.raise_for_status()
        access_token = response.json().get("access_token")
        print("Successfully obtained access token.")
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to obtain access token: {e}"); exit()

    print("\nAttempting to retrieve all identity access assignments from SailPoint...")
    try:
        search_url = f"{base_url}/v3/search"
        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
        
        # The exact search body you requested
        search_body = {
          "indices": ["identities"],
          "query": { "query": "*" },
          "queryResultFilter": {
            "includes": ["id", "name", "access.id", "access.name", "access.type", "access.standalone"]
          }
        }

        all_identities = get_all_results_with_search_after(search_url, headers, search_body)
        
        if all_identities:
            print(f"\nSuccessfully retrieved {len(all_identities)} total identity records.")
            
            # --- THE NEW PARSING LOGIC IS HERE ---
            print("Parsing results and separating by access type...")
            role_assignments = []
            ap_assignments = []
            ent_assignments = []

            for identity in all_identities:
                identity_info = {'identity_id': identity.get('id'), 'identity_name': identity.get('name')}
                
                for access_item in identity.get('access', []):
                    # Create a new record combining identity and access info
                    assignment_record = {**identity_info, 'access': access_item}
                    
                    if access_item.get('type') == 'ROLE':
                        role_assignments.append(assignment_record)
                    elif access_item.get('type') == 'ACCESS_PROFILE':
                        ap_assignments.append(assignment_record)
                    elif access_item.get('type') == 'ENTITLEMENT':
                        ent_assignments.append(assignment_record)
            
            # --- Save each list to its own JSON file ---
            output_files = {
                "identity_role_assignments.json": role_assignments,
                "identity_ap_assignments.json": ap_assignments,
                "identity_entitlement_assignments.json": ent_assignments
            }

            for filename, data in output_files.items():
                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"-> Saved {len(data)} records to {filename}")

        else:
            print("No identities were found in your SailPoint tenant.")
            
    except requests.exceptions.RequestException as e:
        print(f"\nAn exception occurred when calling the Search API: {e}")

if __name__ == "__main__":
    main()
