import requests
import json
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
    limit = 50000  # You can adjust this, 250 is a common and efficient size
    
    # The sort order MUST match what you extract for searchAfter. A unique field like 'id' is crucial as a tie-breaker.
    sort_fields = ["name", "id"]
    search_body["sort"] = sort_fields
    search_body["limit"] = limit

    print(f"Fetching all pages for endpoint: {url} with index: {search_body.get('indices')} using searchAfter")
    
    while True:
        print(f"  - Making API call...")
        if "searchAfter" in search_body:
            print(f"    - Using searchAfter: {search_body['searchAfter']}")

        response = requests.post(url, headers=headers, json=search_body, verify=False)
        response.raise_for_status()
        
        page_results = response.json()
        
        # The definitive exit condition: the API returns an empty list.
        if not page_results:
            print("  - Received an empty page. All results have been fetched.")
            break
            
        all_results.extend(page_results)
        
        total_count_header = response.headers.get('X-Total-Count', len(all_results))
        print(f"  - Fetched {len(page_results)} records. Total so far: {len(all_results)} / {total_count_header} (header may be an estimate)")

        # ===================================================================
        # === THE NEW LOGIC IS HERE ===
        # Get the last record from the page we just received.
        last_record = page_results[-1]
        
        # Extract the values from the last record that correspond to our sort fields.
        # We need to handle nested '_source' field for search results.
        source_data = last_record.get('_source', last_record)
        search_after_values = [source_data.get(field) for field in sort_fields]
        
        # Update the search body for the NEXT request.
        search_body["searchAfter"] = search_after_values
        # ===================================================================

    return all_results

# --- Configuration and Authentication (remains the same) ---
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

# --- Step 2: Call the Entitlements Search API with searchAfter logic ---
print("\nAttempting to retrieve all Entitlements from SailPoint...")
try:
    search_url = f"{base_url}/v3/search"
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    
    # This is the initial search body. The pagination function will add 'sort', 'limit', and 'searchAfter'.
    search_body = {
        "indices": ["entitlements"],
        "query": { "query": "*",
        "limit":10000 }
    }

    all_entitlements = get_all_results_with_search_after(search_url, headers, search_body)
    
    if all_entitlements:
        print(f"\nSuccessfully retrieved a final total of {len(all_entitlements)} entitlements.\n")
        print("--- Entitlement Details (First 5) ---")
        for ent in all_entitlements[:5]:
            source_data = ent.get('_source', ent)
            print(f"Entitlement Name: {source_data.get('name', 'N/A')}")
            print(f"Value: {source_data.get('value', 'N/A')}")
            source = source_data.get('source', {})
            print(f"Source: {source.get('name', 'N/A')}")
            print("-" * 20)
    else:
        print("No entitlements were found in your SailPoint tenant.")
except requests.exceptions.RequestException as e:
    print(f"\nAn exception occurred when calling the Entitlements API: {e}")
