# test_search.py

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
        raise ValueError("ClientId, ClientSecret, and BaseURL must be set in the 'ISC' section of config.json")

except (FileNotFoundError, ValueError) as e:
    print(f"FATAL: Configuration error: {e}")
    exit()

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
    print(f"FATAL: Failed to get token: {e}")
    exit()

# --- Step 2: Make the Search API Call (The Simple Way) ---
print("\nMaking a single, clean search request (no pagination)...")
try:
    search_url = f"{base_url}/v3/search"
    
    # The exact payload that works in Postman, with no extra keys.
    search_payload = {
      "query": { "query": "*" },
      "indices": ["identities"],
      "sort": ["name"],
      "queryResultFilter": {
        "includes": ["access"]
      }
    }
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Make the call with ONLY the payload. No 'params' argument.
    search_response = requests.post(search_url, headers=headers, json=search_payload, verify=False)
    search_response.raise_for_status()
    
    # --- Analyze the Results ---
    total_count = search_response.headers.get('X-Total-Count')
    results = search_response.json()
    
    print("\n--- RESULTS ---")
    print(f"Status Code: {search_response.status_code}")
    print(f"X-Total-Count Header: {total_count}")
    print(f"Number of Records Received: {len(results)}")
    
    if results:
        print("\nSUCCESS: The API call returned data.")
        print("This confirms the issue was the unnecessary pagination parameters.")
        # Print first record as proof
        print("\nFirst record received:")
        print(json.dumps(results[0], indent=2))
    else:
        print("\nFAILURE: The API call returned 0 records even with a clean payload.")
        print("This indicates a deeper issue beyond the script's logic, possibly with permissions for the API client.")

except Exception as e:
    print(f"\nAn error occurred during the search request: {e}")

