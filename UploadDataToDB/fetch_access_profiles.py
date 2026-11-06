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

def get_all_search_results(url, headers, search_body):
    """
    Handles pagination for POST search requests to retrieve all results.
    """
    all_results = []
    offset = 0
    limit = 250
    
    print(f"Fetching all pages for endpoint: {url} with index: {search_body['indices']}")
    while True:
        # For POST search, pagination is handled in the request body
        search_body['offset'] = offset
        search_body['limit'] = limit
        
        response = requests.post(url, headers=headers, json=search_body, verify=False)
        response.raise_for_status()
        
        page_results = response.json()
        if not page_results:
            print("Received an empty page. Assuming all results have been fetched.")
            break
            
        all_results.extend(page_results)
        
        total_count_header = response.headers.get('X-Total-Count', len(all_results))
        print(f"  ... Fetched {len(all_results)} / {total_count_header} records")

        offset += limit
        
        if len(page_results) < limit:
            break

    return all_results

# --- Load Configuration ---
try:
    with open('config.json') as f:
        config = json.load(f)
    client_id = config.get("ClientId")
    client_secret = config.get("ClientSecret")
    base_url = config.get("BaseURL")
    if not all([client_id, client_secret, base_url]):
        raise ValueError("ClientId, ClientSecret, and BaseURL must be set in config.json")
except Exception as e:
    print(f"Configuration Error: {e}"); exit()

# --- Step 1: Authenticate ---
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

# --- Step 2: Call the Access Profiles Search API ---
print("\nAttempting to retrieve all Access Profiles from SailPoint...")
try:
    # ===================================================================
    # === THE FIX IS HERE: Use the /v3/search endpoint ===
    search_url = f"{base_url}/v3/search"
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    
    # Define the specific search body to query for access profiles
    search_body = {
        "indices": ["accessprofiles"], # Correct index name for Access Profiles
        "query": {
            "query": "*"
        },
        "sort": ["name"]
    }
    # ===================================================================

    # Use the search pagination helper to get all results
    all_access_profiles = get_all_search_results(search_url, headers, search_body)
    
    if all_access_profiles:
        print(f"\nSuccessfully retrieved {len(all_access_profiles)} access profiles.\n")
        print("--- Access Profile Details ---")
        
        for ap in all_access_profiles:
            # Search results are often nested in a '_source' field
            source_data = ap.get('_source', ap)
            
            print(f"AP Name: {source_data.get('name', 'N/A')}")
            source = source_data.get('source', {})
            print(f"Source: {source.get('name', 'N/A')}")
            print(f"Description: {source_data.get('description', 'N/A')}")
            print(f"Enabled: {source_data.get('enabled', 'N/A')}")
            owner = source_data.get('owner', {})
            print(f"Owner: {owner.get('name', 'N/A')}")
            print("-" * 20)
    else:
        print("No access profiles were found in your SailPoint tenant.")
except requests.exceptions.RequestException as e:
    print(f"\nAn exception occurred when calling the Access Profiles API: {e}")
