import requests
import json
import urllib3

# Suppress warnings for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Load Configuration ---
try:
    with open('config.json') as f:
        config = json.load(f)
    
    client_id = config.get("ClientId")
    client_secret = config.get("ClientSecret")
    base_url = config.get("BaseURL")
    
    if not all([client_id, client_secret, base_url]):
        raise ValueError("ClientId, ClientSecret, and BaseURL must be set in config.json")

except FileNotFoundError:
    print("ERROR: config.json file not found.")
    exit()
except Exception as e:
    print(f"Configuration Error: {e}")
    exit()

# --- Step 1: Manually Authenticate using 'requests' ---
print("Attempting to manually fetch access token...")
try:
    token_url = f"{base_url}/oauth/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }
    # Make the request with SSL verification OFF
    response = requests.post(token_url, data=payload, verify=False)
    response.raise_for_status() # Check for HTTP errors (like 400, 401)
    
    access_token = response.json().get("access_token")
    print("Successfully obtained access token.")

except requests.exceptions.RequestException as e:
    print(f"ERROR: Failed to obtain access token: {e}")
    exit()


# --- Step 2: Call the Roles API using the token and 'requests' ---
print("\nAttempting to retrieve all roles from SailPoint...")
try:
    roles_url = f"{base_url}/v3/roles"
    
    # Prepare the authorization header
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    # Make the GET request to the roles endpoint, with SSL verification OFF
    roles_response = requests.get(roles_url, headers=headers, verify=False)
    roles_response.raise_for_status() # Check for HTTP errors
    
    all_roles = roles_response.json()

    # --- Process and Display Results ---
    if all_roles:
        print(f"\nSuccessfully retrieved {len(all_roles)} roles.\n")
        print("--- Role Details ---")
        
        for role in all_roles:
            # Access dictionary keys directly, using .get() for safety
            print(f"Role Name: {role.get('name', 'N/A')}")
            print(f"Description: {role.get('description', 'N/A')}")
            print(f"Enabled: {role.get('enabled', 'N/A')}")
            owner = role.get('owner', {})
            print(f"Owner: {owner.get('name', 'N/A')}")
            print("-" * 20)
    else:
        print("No roles were found in your SailPoint tenant.")

except requests.exceptions.RequestException as e:
    print(f"\nAn exception occurred when calling the Roles API: {e}")