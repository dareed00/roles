# trigger_bundle_suggestion.py

import json
import requests
import sys
import mysql.connector
from mysql.connector import Error
from datetime import datetime

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

# --- Helper Functions ---
def get_db_connection(db_config):
    """Establishes a database connection. Raises an exception on failure."""
    if not db_config:
        raise ValueError("FATAL: 'Database' configuration block not found in config.json.")
    try:
        db_connection = mysql.connector.connect(**db_config)
        print("    --> Database connection successful.")
        return conn
    except Error as e:
        raise ConnectionError(f"Error connecting to MySQL: {e}")

def get_sailpoint_token(isc_config):
    """Authenticates to SailPoint and returns a bearer token. Raises an exception on failure."""
    if not isc_config:
        raise ValueError("FATAL: 'ISC' configuration block not found in config.json.")
    required_keys = ['token_url', 'client_id', 'client_secret']
    for key in required_keys:
        if key not in isc_config or not isc_config[key]:
            raise ValueError(f"FATAL: The key '{key}' is missing or empty in the 'ISC' block of your config.json.")
    
    print(f"  [TRACE] Attempting to get SailPoint ISC access token from: {isc_config['token_url']}")
    payload = {"grant_type": "client_credentials", "client_id": isc_config['client_id'], "client_secret": isc_config['client_secret']}
    
    try:
        response = requests.post(isc_config['token_url'], data=payload)
        if response.status_code != 200:
            error_details = f"SailPoint Authentication Failed. Status Code: {response.status_code}\n"
            try: error_details += f"--> Error Details: {json.dumps(response.json(), indent=2)}"
            except json.JSONDecodeError: error_details += f"--> Raw Response (not JSON): {response.text}"
            raise Exception(error_details)
        access_token = response.json().get("access_token")
        print("    --> Success! Token received.")
        return access_token
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"NETWORK ERROR: Could not connect to SailPoint endpoint. Error: {e}")

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# ===================================================================
# === THE FIX IS HERE: Adding verbose tracing for the API payload ===
# ===================================================================
def trigger_workflow(isc_config, token, workflow_inputs):
    """Triggers the ISC workflow."""
    if 'workflow_url' not in isc_config or not isc_config['workflow_url']:
        raise ValueError("FATAL: The key 'workflow_url' is missing or empty in the 'ISC' block of your config.json.")

    trigger_url = isc_config['workflow_url']
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # This creates a nicely formatted string of the JSON for logging
    data_to_send = json.dumps(workflow_inputs, default=json_serial, indent=2)
    
    print(f"  [TRACE] Preparing to call API endpoint: {trigger_url}")
    print("-------------------- START OF API PAYLOAD --------------------")
    print(data_to_send)
    print("--------------------- END OF API PAYLOAD ---------------------")
    
    response = requests.post(trigger_url, headers=headers, data=data_to_send)
    
    if response.status_code == 202:
        print("    --> SUCCESS: Workflow Triggered Successfully (Status 202 Accepted).")
        return True
    else:
        print(f"    --> !!! FAILURE: Workflow Trigger Failed. Status: {response.status_code}")
        print(f"        --> Raw Response: {response.text}")
        return False


def main():
    """Main orchestrator for the script."""
    print("======================================================================")
    print("=== Starting Workflow Trigger Script for Bundle Suggestions ===")
    print("======================================================================")
    db_connection = None
    cursor = None
    try:
        print("[STEP 1] Loading configuration files...")
        with open('config.json') as f: config = json.load(f)
        print("    --> 'config.json' loaded successfully.")

        try:
            with open('email_template.html', 'r') as f:
                email_template_string = f.read()
            print("    --> 'email_template.html' loaded successfully.")
        except FileNotFoundError:
            raise FileNotFoundError("FATAL: email_template.html not found in the script directory.")
        
        print("\n[STEP 2] Authenticating to SailPoint ISC...")
        isc_config = config.get("ISC")
        auth_token = get_sailpoint_token(isc_config)
        
        print("\n[STEP 3] Connecting to the database...")
        db_config = config.get("Database")
        db_connection = get_db_connection(db_config)
        
        print("\n[STEP 4] Creating a database cursor...")
        cursor = db_connection.cursor(dictionary=True, buffered=True )
        print("    --> Cursor created successfully.")
        
        print("\n[STEP 5] Querying for all exact correlations...")
        cursor.execute("SELECT * FROM Entitlement_Exact_Correlations")
        correlations = cursor.fetchall()
        print(f"    --> Found {len(correlations)} total correlations to process.")
        print("=" * 70)

        for i, corr in enumerate(correlations):
            print(f"\nProcessing Correlation #{i+1} (ID: {corr['id']}):")
            
            entitlement_a_id = corr['entitlement_A_id']
            entitlement_b_id = corr['entitlement_B_id']
            
            print(f"  [SUB-STEP 1] Fetching details for entitlements...")
            cursor.execute("SELECT entitlement_name, source_name, entitlement_id FROM entitlements WHERE id = %s", (entitlement_a_id,))
            ent_a_details = cursor.fetchone()

            cursor.execute("SELECT entitlement_name, source_name, entitlement_id FROM entitlements WHERE id = %s", (entitlement_b_id,))
            ent_b_details = cursor.fetchone()

            if not ent_a_details or not ent_b_details:
                print(f"    --> !!! SKIPPING: Could not find full details for one or both entitlements.")
                continue

            print(f"    --> Entitlement to Suggest (A): '{ent_a_details['entitlement_name']}'")
            print(f"    --> Existing Entitlement (B): '{ent_b_details['entitlement_name']}'")
            
            print(f"  [SUB-STEP 2] Searching for parent bundle of Entitlement B...")
            native_entitlement_id_b = ent_b_details['entitlement_id']
            print(f"    --> Using native entitlement_id for lookup: '{native_entitlement_id_b}'")

            cursor.execute("SELECT role_id, role_name FROM CurrentRoleModel_RoleEntitlements WHERE entitlement_id = %s", (native_entitlement_id_b,))
            role_membership = cursor.fetchone()

            cursor.execute("SELECT access_profile_id, access_profile_name FROM CurrentRoleModel_AccessProfileEntitlements WHERE entitlement_id = %s", (native_entitlement_id_b,))
            ap_membership = cursor.fetchone()

            activity_info, bundle_info = {}, {}

            if role_membership:
                bundle_type = "Role"
                bundle_name = role_membership['role_name']
                print(f"    --> SUCCESS: Found in Role: '{bundle_name}'")
                activity_info = {"ActivityName": "Suggest Exact Entitlement To Role Owner", "ActivityType": "SuggestExactEntitlementToRoleOwner"}
                bundle_info = {"id": role_membership['role_id'], "name": bundle_name}
            elif ap_membership:
                bundle_type = "Access Profile"
                bundle_name = ap_membership['access_profile_name']
                print(f"    --> SUCCESS: Found in Access Profile: '{bundle_name}'")
                activity_info = {"ActivityName": "Suggest Exact Entitlement To Access Profile Owner", "ActivityType": "SuggestExactEntitlementToAccessProfileOwner"}
                bundle_info = {"id": ap_membership['access_profile_id'], "name": bundle_name}
            else:
                print(f"    --> !!! SKIPPING: Entitlement not found in any Role or AP.")
                continue
            
            print(f"  [SUB-STEP 3] Generating email content from template...")
            
            email_subject = f"Action Recommended: Add Entitlement to Your {bundle_type}: \"{bundle_name}\""
            
            template_data = {
                "bundle_type": bundle_type,
                "bundle_name": bundle_name,
                "entitlement_to_add_name": ent_a_details['entitlement_name'],
                "entitlement_to_add_source": ent_a_details['source_name'],
                "population": corr['population_size'],
                "existing_entitlement_name": ent_b_details['entitlement_name']
            }
            email_body = email_template_string.format(**template_data)

            workflow_payload = { 
                "correlation_details": { "correlation_id": corr['id'], "entitlement_to_add": ent_a_details, "existing_entitlement_in_bundle": ent_b_details, "population": corr['population_size'] }, 
                "target_bundle": bundle_info, 
                "activity": activity_info,
                "email": { "subject": email_subject, "body": email_body }
            }
            
            print(f"  [SUB-STEP 4] Triggering workflow...")
            trigger_workflow(isc_config, auth_token, workflow_payload)
            print("=" * 70)

    except (ValueError, ConnectionError, mysql.connector.Error, FileNotFoundError, Exception) as e:
        print(f"\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"!!! SCRIPT HALTED DUE TO A FATAL ERROR:")
        print(f"!!! {type(e).__name__}: {e}")
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        sys.exit(1)
        
    finally:
        print("\n[FINALLY] Executing cleanup block...")
        if cursor: 
            cursor.close()
            print("    --> Cursor closed.")
        if db_connection.and db_connection.is_connected(): 
            db_connection.close()
            print("    --> Database connection closed.")
        print("======================================================================")
        print("=== Script Finished ===")
        print("======================================================================")

if __name__ == "__main__":
    main()
