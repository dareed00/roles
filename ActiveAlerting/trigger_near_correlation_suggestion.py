# trigger_near_correlation_suggestion.py

import json
import requests
import sys
import mysql.connector
from mysql.connector import Error
from datetime import datetime
from decimal import Decimal

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

def get_sailpoint_token(isc_config):
    """Authenticates to SailPoint and returns a bearer token. Raises an exception on failure."""
    if not isc_config:
        raise ValueError("FATAL: 'ISC' configuration block not found in config.json.")
    required_keys = ['token_url', 'client_id', 'client_secret', 'workflow_url']
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
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

def trigger_workflow(isc_config, token, workflow_inputs):
    """Triggers the ISC workflow with detailed payload tracing."""
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

def get_user_context_for_delta(cursor, identity_ids):
    """Fetches basic context for a list of identity IDs."""
    if not identity_ids:
        print("    *--> No delta users to fetch context for.")
        return "No users to display."
    
    id_sample = list(identity_ids)[:5]
    id_placeholders = ', '.join(['%s'] * len(id_sample))
    sql = f"SELECT name, email FROM Identities WHERE id IN ({id_placeholders})"
    
    try:
        print(f"    *--> Fetching context for {len(id_sample)} delta users...")
        print(f"        SQL: {sql}")
        print(f"        Params: {id_sample}")
        cursor.execute(sql, id_sample)
        users = cursor.fetchall()
        print(f"        Result: {users}")
        user_lines = [f"<li>{user['name']} ({user['email']})</li>" for user in users]
        if len(identity_ids) > 5:
            user_lines.append(f"<li>... and {len(identity_ids) - 5} more.</li>")
        return f"<ul>{''.join(user_lines)}</ul>"
    except Error as e:
        print(f"      --> !!! WARNING: Could not fetch user context for delta: {e}")
        return "User details could not be retrieved due to an error."

def get_population_ids(cursor, entitlement_db_id):
    """Gets the set of identity IDs for a given internal entitlement ID."""
    print(f"    *--> Getting population for internal entitlement ID: {entitlement_db_id}")
    cursor.execute("SELECT entitlement_id FROM entitlements WHERE id = %s", (entitlement_db_id,))
    native_id_record = cursor.fetchone()
    if not native_id_record:
        print("        --> Entitlement not found in 'entitlements' table. Returning empty set.")
        return set()
    
    native_id = native_id_record['entitlement_id']
    print(f"        --> Found native entitlement_id: {native_id}")
    
    sql = """
        (SELECT identity_id FROM IdentityEntitlementAssignments_Filtered WHERE entitlement_id = %s)
        UNION
        (SELECT identity_id FROM IdentityEffectiveEntitlements_Filtered WHERE entitlement_id = %s)
    """
    cursor.execute(sql, (native_id, native_id))
    id_set = {row['identity_id'] for row in cursor.fetchall()}
    print(f"        --> Returning a set with {len(id_set)} identity IDs.")
    return id_set

def main():
    """Main orchestrator for the script."""
    print("======================================================================")
    print("=== Starting Workflow Trigger for NEAR Correlation Suggestions ===")
    print("======================================================================")
    db_connection = None
    cursor = None
    try:
        print("[STEP 1] Loading configuration files...")
        with open('config.json') as f: config = json.load(f)
        print("    --> 'config.json' loaded successfully.")

        try:
            with open('email_template_near.html', 'r') as f: email_template_string = f.read()
            print("    --> 'email_template_near.html' loaded successfully.")
        except FileNotFoundError:
            raise FileNotFoundError("FATAL: email_template_near.html not found.")

        print("\n[STEP 2] Authenticating to SailPoint ISC...")
        isc_config = config.get("ISC")
        auth_token = get_sailpoint_token(isc_config)
        
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
        print("    --> Cursor created successfully.")
        
        print("\n[STEP 5] Querying for all near correlations...")
        cursor.execute("SELECT * FROM Entitlement_Near_Correlations ORDER BY jaccard_score DESC")
        correlations = cursor.fetchall()
        print(f"    --> Found {len(correlations)} total near correlations to process.")
        print("=" * 70)

        for i, corr in enumerate(correlations):
            print(f"\nProcessing Near Correlation #{i+1}:")
            print("  [RAW CORRELATION DATA]:")
            # Print the raw dictionary for the current correlation
            print(f"    {json.dumps(corr, default=str)}")

            entitlement_a_id = corr['entitlement_A_id']
            entitlement_b_id = corr['entitlement_B_id']
            
            print(f"  [SUB-STEP 1] Fetching details for entitlements (A_id: {entitlement_a_id}, B_id: {entitlement_b_id})...")
            cursor.execute("SELECT entitlement_name, source_name, entitlement_id FROM entitlements WHERE id = %s", (entitlement_a_id,))
            ent_a_details = cursor.fetchone()
            print(f"    --> Entitlement A Details: {ent_a_details}")
            cursor.execute("SELECT entitlement_name, source_name, entitlement_id FROM entitlements WHERE id = %s", (entitlement_b_id,))
            ent_b_details = cursor.fetchone()
            print(f"    --> Entitlement B Details: {ent_b_details}")

            if not ent_a_details or not ent_b_details:
                print("    --> !!! SKIPPING: Could not find full details for one or both entitlements.")
                continue
            
            print(f"  [SUB-STEP 2] Searching for parent bundle of Entitlement B...")
            native_entitlement_id_b = ent_b_details['entitlement_id']
            print(f"    --> Using native entitlement_id for lookup: '{native_entitlement_id_b}'")

            cursor.execute("SELECT role_id, role_name FROM CurrentRoleModel_RoleEntitlements WHERE entitlement_id = %s", (native_entitlement_id_b,))
            role_membership = cursor.fetchone()

            cursor.execute("SELECT access_profile_id, access_profile_name FROM CurrentRoleModel_AccessProfileEntitlements WHERE entitlement_id = %s", (native_entitlement_id_b,))
            ap_membership = cursor.fetchone()

            activity_info, bundle_info = {}, {}
            if role_membership:
                bundle_type, bundle_name = "Role", role_membership['role_name']
                print(f"    --> SUCCESS: Found in Role: {role_membership}")
                activity_info = {"ActivityName": "Suggest Near Entitlement To Role Owner", "ActivityType": "SuggestNearEntitlementToRoleOwner"}
                bundle_info = {"role_id": role_membership['role_id'], "role_name": bundle_name}
            elif ap_membership:
                bundle_type, bundle_name = "Access Profile", ap_membership['access_profile_name']
                print(f"    --> SUCCESS: Found in Access Profile: {ap_membership}")
                activity_info = {"ActivityName": "Suggest Near Entitlement To Access Profile Owner", "ActivityType": "SuggestNearEntitlementToAccessProfileOwner"}
                bundle_info = {"access_profile_id": ap_membership['access_profile_id'], "access_profile_name": bundle_name}
            else:
                print(f"    --> !!! SKIPPING: Entitlement not found in any Role or AP.")
                continue

            print("  [SUB-STEP 3] Calculating population deltas...")
            pop_a_ids = get_population_ids(cursor, entitlement_a_id)
            pop_b_ids = get_population_ids(cursor, entitlement_b_id)
            overlap_ids = pop_a_ids.intersection(pop_b_ids)
            delta_b_not_a = pop_b_ids - pop_a_ids
            print(f"    --> Pop A: {len(pop_a_ids)}, Pop B: {len(pop_b_ids)}, Overlap: {len(overlap_ids)}, Exceptions (B not A): {len(delta_b_not_a)}")

            print("  [SUB-STEP 4] Fetching context for delta users...")
            delta_users_html = get_user_context_for_delta(cursor, delta_b_not_a)

            print("  [SUB-STEP 5] Generating email content...")
            template_data = {
                "bundle_type": bundle_type, "bundle_name": bundle_name,
                "entitlement_to_add_name": ent_a_details['entitlement_name'], "entitlement_to_add_source": ent_a_details['source_name'],
                "jaccard_score_percent": f"{corr['jaccard_score']:.1%}",
                "population_A": len(pop_a_ids), "population_B": len(pop_b_ids),
                "population_overlap": len(overlap_ids),
                "delta_user_count": len(delta_b_not_a),
                "delta_users_list": delta_users_html,
                "existing_entitlement_name": ent_b_details['entitlement_name']
            }
            email_body = email_template_string.format(**template_data)
            email_subject = f"High-Confidence Suggestion: Add Entitlement to Your {bundle_type}: \"{bundle_name}\""
            print("    --> Email subject and body generated.")

            workflow_payload = { 
                "correlation_details": corr, "target_bundle": bundle_info, "activity": activity_info,
                "email": { "subject": email_subject, "body": email_body }
            }
            
            print("  [SUB-STEP 6] Triggering workflow...")
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
        if cursor: cursor.close(); print("    --> Cursor closed.")
        if db_connection.and db_connection.is_connected(): db_connection.close(); print("    --> Database connection closed.")
        print("======================================================================")
        print("=== Script Finished ===")
        print("======================================================================")

if __name__ == "__main__":
    main()
