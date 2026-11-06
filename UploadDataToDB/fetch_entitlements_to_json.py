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
        source_data = last_record.get('_source', last_record)
        search_after_values = [source_data.get(field) for field in sort_fields]
        search_body["searchAfter"] = search_after_values

    return all_results

def main():
    """Main function to fetch entitlements and save them to a JSON file."""
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

    print("\nAttempting to retrieve all Entitlements from SailPoint...")
    try:
        search_url = f"{base_url}/v3/search"
        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
        
        search_body = {"indices": ["entitlements"], "query": {"query": "*"}}

        all_entitlements = get_all_results_with_search_after(search_url, headers, search_body)
        
        if all_entitlements:
            output_filename = "entitlements.json"
            print(f"\nSuccessfully retrieved a final total of {len(all_entitlements)} entitlements.")
            
            ent_data = [ent.get('_source', ent) for ent in all_entitlements]

            with open(output_filename, 'w') as f:
                json.dump(ent_data, f, indent=2)
            print(f"All entitlements have been saved to {output_filename}")
        else:
            print("No entitlements were found in your SailPoint tenant.")
    except requests.exceptions.RequestException as e:
        print(f"\nAn exception occurred when calling the Entitlements API: {e}")

if __name__ == "__main__":
    main()
