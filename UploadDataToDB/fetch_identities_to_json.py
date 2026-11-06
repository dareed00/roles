import requests
import json
import urllib3

# --- Shared Functions (Identical to other fetch scripts) ---
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
    # ... (This function is identical to the one in fetch_roles_to_json.py)
    all_results = []
    limit = 250
    sort_fields = ["name", "id"]
    search_body["sort"] = sort_fields
    search_body["limit"] = limit
    print(f"Fetching all pages for index: {search_body.get('indices')}")
    while True:
        response = requests.post(url, headers=headers, json=search_body, verify=False)
        response.raise_for_status()
        page_results = response.json()
        if not page_results: break
        all_results.extend(page_results)
        print(f"  - Fetched {len(all_results)} records...")
        last_record = page_results[-1]
        source_data = last_record.get('_source', last_record)
        search_body["searchAfter"] = [source_data.get(field) for field in sort_fields]
    return all_results

def main():
    """Main function to fetch identities and save them to a JSON file."""
    # ... (Config and Auth logic is identical)
    try:
        with open('config.json') as f: config = json.load(f)
        client_id, client_secret, base_url = config.get("ClientId"), config.get("ClientSecret"), config.get("BaseURL")
    except Exception as e:
        print(f"Config Error: {e}"); exit()
        
    print("Authenticating..."); access_token = requests.post(f"{base_url}/oauth/token", data={'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}, verify=False).json().get("access_token")

    print("\nAttempting to retrieve all Identities from SailPoint...")
    try:
        search_url = f"{base_url}/v3/search"
        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
        search_body = {"indices": ["identities"], "query": {"query": "*"},"queryResultFilter":{"includes":["firstName","lastName","displayName","inactive","modified","identityProfile","source","email","isManager","id","created","name","status","attributes","roleCount","ownsCount","accessProfileCount","employeeNumber","entitlementCount","accessCount","accountCount","accounts.id","accounts.name","accounts.acccountId","accounts.source.id","accounts.source.name","accounts.created","accounts.privileged"]}}

        all_identities = get_all_results_with_search_after(search_url, headers, search_body)
        
        if all_identities:
            output_filename = "identities.json"
            print(f"\nSuccessfully retrieved {len(all_identities)} identities.")
            identity_data = [identity.get('_source', identity) for identity in all_identities]
            with open(output_filename, 'w') as f:
                json.dump(identity_data, f, indent=2)
            print(f"All identities saved to {output_filename}")
        else:
            print("No identities found.")
    except requests.exceptions.RequestException as e:
        print(f"\nAn exception occurred: {e}")

if __name__ == "__main__":
    main()
