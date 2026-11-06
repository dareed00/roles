# inspect_object.py

import requests
import json
import urllib3

# Suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Configuration ---
try:
    with open('config.json') as f:
        config = json.load(f)
    client_id = config.get("ISC", {}).get("ClientId")
    client_secret = config.get("ISC", {}).get("ClientSecret")
    base_url = config.get("ISC", {}).get("BaseURL")
    if not all([client_id, client_secret, base_url]):
        raise ValueError("Config file is missing ISC credentials.")
except Exception as e:
    print(f"FATAL: Config error: {e}"); exit()

# --- Step 1: Get Access Token ---
print("Attempting to get access token...")
try:
    token_url = f"{base_url}/oauth/token"
    token_payload = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
    token_response = requests.post(token_url, data=token_payload, verify=False)
    token_response.raise_for_status()
    access_token = token_response.json().get("access_token")
    print("Successfully obtained access token.")
except Exception as e:
    print(f"FATAL: Failed to get token: {e}"); exit()

# --- Step 2: Make the API Call and Print the First Object ---
print("\nMaking API call to fetch one page of data...")
try:
    search_url = f"{base_url}/v3/search"
    
    # Using the correct payload that we know works
    search_payload = {
      "query": { "query": "*" },
      "indices": ["identities"],
      "sort": ["name"],
      "queryResultFilter": {
        "includes": ["access"]
      }
    }
    
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    
    # We only need one page for this test
    params = {'limit': 1} 
    
    search_response = requests.post(search_url, headers=headers, json=search_payload, params=params, verify=False)
    search_response.raise_for_status()
    
    results = search_response.json()
    
    if results:
        print("\n--- RAW JSON OF THE FIRST RECORD ---")
        print("Please copy the entire block below, starting from the opening '{' to the closing '}'.")
        print("-" * 35)
        
        # Pretty-print the first object from the response list
        print(json.dumps(results[0], indent=2))
        
        print("-" * 35)
    else:
        print("\nFAILURE: The API call returned 0 records.")

except Exception as e:
    print(f"\nAn error occurred during the search request: {e}")

