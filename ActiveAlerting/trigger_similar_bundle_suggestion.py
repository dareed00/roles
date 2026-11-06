# trigger_similar_bundle_suggestion.py

import json
import requests
import sys
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
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

# --- Helper Functions (Re-using our perfected functions) ---

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
            try:
                error_details += f"--> Error Details: {json.dumps(response.json(), indent=2)}"
            except json.JSONDecodeError:
                error_details += f"--> Raw Response (not JSON): {response.text}"
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
    data_to_send = json.dumps(workflow_inputs, default=json_serial, indent=2)
    
    print("-------------------- START OF FINAL API PAYLOAD --------------------")
    print(data_to_send)
    print("--------------------- END OF FINAL API PAYLOAD ---------------------")
    
    response = requests.post(trigger_url, headers=headers, data=data_to_send)
    
    if response.status_code == 202:
        print("    --> SUCCESS: Workflow Triggered Successfully (Status 202 Accepted).")
        return True
    else:
        print(f"    --> !!! FAILURE: Workflow Trigger Failed. Status: {response.status_code}")
        print(f"        --> Raw Response: {response.text}")
        return False

# --- New & Adapted Helper Functions for This Script ---

def get_user_sample_html(cursor, identity_ids):
    """Fetches context for a small sample of identity IDs and returns an HTML list."""
    if not identity_ids:
        return "<ul><li>No users in this category.</li></ul>"
    
    sample_size = 5
    id_sample = list(identity_ids)[:sample_size]
    id_placeholders = ', '.join(['%s'] * len(id_sample))
    sql = f"SELECT name, email FROM Identities WHERE id IN ({id_placeholders})"
    
    try:
        cursor.execute(sql, id_sample)
        users = cursor.fetchall()
        user_lines = [f"<li>{user['name']} ({user['email']})</li>" for user in users]
        if len(identity_ids) > sample_size:
            user_lines.append(f"<li>... and {len(identity_ids) - sample_size} more.</li>")
        return f"<ul>{''.join(user_lines)}</ul>"
    except Error as e:
        print(f"      --> !!! WARNING: Could not fetch user context: {e}")
        return "<ul><li>Error retrieving user details.</li></ul>"

def get_bundle_population_ids(cursor, bundle_id, bundle_type):
    """Gets the set of identity IDs for a given Role or Access Profile."""
    print(f"    *--> [get_bundle_population_ids] for {bundle_type} ID: {bundle_id}")
    table_map = {"Role": "IdentityRoleAssignments", "Access Profile": "IdentityAccessProfileAssignments"}
    column_map = {"Role": "role_id", "Access Profile": "access_profile_id"}

    sql = f"SELECT identity_id FROM {table_map[bundle_type]} WHERE {column_map[bundle_type]} = %s"
    
    cursor.execute(sql, (bundle_id,))
    return {row['identity_id'] for row in cursor.fetchall()}

def process_similar_bundles(cursor, isc_config, auth_token, email_template, bundle_type):
    """Queries for similar bundles, calculates deltas, and triggers workflows."""
    
    table_map = {"Role": "CurrentRoleModel_RoleSimilarity", "Access Profile": "CurrentRoleModel_AccessProfileSimilarity"}
    id_field_map = {"Role": "role", "Access Profile": "access_profile"}
    
    # We set a threshold to only report on high-confidence matches (e.g., > 80% similar)
    similarity_threshold = 0.80

    sql = f"SELECT * FROM {table_map[bundle_type]} WHERE jaccard_score >= %s AND ignored = 0 AND state != 'APPROVED'"
    cursor.execute(sql, (similarity_threshold,))
    similar_pairs = cursor.fetchall()
    print(f"\n[STEP] Found {len(similar_pairs)} high-confidence similar {bundle_type} pairs to process.")
    print("=" * 70)

    for i, pair in enumerate(similar_pairs):
        print(f"\nProcessing similar {bundle_type} pair #{i+1} (Similarity: {pair['jaccard_score']:.2%})")
        
        bundle_A_id = pair[f'{id_field_map[bundle_type]}1_id']
        bundle_B_id = pair[f'{id_field_map[bundle_type]}2_id']

        # Fetch full details for both bundles
        cursor.execute(f"SELECT * FROM CurrentRoleModel_{bundle_type}s WHERE id = %s", (bundle_A_id,))
        bundle_A = cursor.fetchone()
        cursor.execute(f"SELECT * FROM CurrentRoleModel_{bundle_type}s WHERE id = %s", (bundle_B_id,))
        bundle_B = cursor.fetchone()

        if not bundle_A or not bundle_B:
            print("    --> !!! SKIPPING: Could not retrieve full details for both bundles.")
            continue
            
        print(f"    --> Bundle A: '{bundle_A['name']}'")
        print(f"    --> Bundle B: '{bundle_B['name']}'")

        # Calculate population deltas
        pop_A_ids = get_bundle_population_ids(cursor, bundle_A['id'], bundle_type)
        pop_B_ids = get_bundle_population_ids(cursor, bundle_B['id'], bundle_type)
        
        delta_A_not_B = pop_A_ids - pop_B_ids
        delta_B_not_A = pop_B_ids - pop_A_ids

        # Generate email content
        template_data = {
            "owner_name": bundle_A.get('owner_name') or 'Bundle Owner',
            "bundle_type": bundle_type,
            "bundle_A_name": bundle_A['name'],
            "bundle_B_name": bundle_B['name'],
            "bundle_A_desc": bundle_A.get('description', 'N/A'),
            "bundle_B_desc": bundle_B.get('description', 'N/A'),
            "jaccard_score_percent": f"{pair['jaccard_score']:.1%}",
            "population_A": len(pop_A_ids),
            "population_B": len(pop_B_ids),
            "delta_A_not_B_count": len(delta_A_not_B),
            "delta_B_not_A_count": len(delta_B_not_A),
            "delta_A_users_list": get_user_sample_html(cursor, delta_A_not_B),
            "delta_B_users_list": get_user_sample_html(cursor, delta_B_not_A)
        }
        email_body = email_template.format(**template_data)
        email_subject = f"Review Recommended: Similar {bundle_type}s Found - \"{bundle_A['name']}\" and \"{bundle_B['name']}\""

        workflow_payload = {
            "activity": {"ActivityName": f"Similar {bundle_type} Found", "ActivityType": f"Similar{bundle_type}Found"},
            "similarity_details": pair,
            "bundle_A_details": bundle_A,
            "bundle_B_details": bundle_B,
            "email": {"subject": email_subject, "body": email_body}
        }
        
        print("  [SUB-STEP] Triggering workflow...")
        trigger_workflow(isc_config, auth_token, workflow_payload)
        print("-" * 70)


def main():
    """Main orchestrator for the similar bundle suggestion script."""
    print("======================================================================")
    print("=== Starting Similar Bundle Suggestion Trigger Script ===")
    print("======================================================================")
    db_connection = None
    cursor = None
    try:
        print("[STEP 1] Loading configuration files...")
        with open('config.json') as f: config = json.load(f)
        with open('email_template_similar_bundle.html', 'r') as f: email_template_string = f.read()
        print("    --> All configuration files loaded successfully.")

        print("\n[STEP 2] Authenticating to SailPoint ISC...")
        isc_config = config.get("ISC")
        auth_token = get_sailpoint_token(isc_config)
        
        print("\n[STEP 3] Connecting to the database...")
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
        
        # Process both Roles and Access Profiles
        process_similar_bundles(cursor, isc_config, auth_token, email_template_string, "Role")
        process_similar_bundles(cursor, isc_config, auth_token, email_template_string, "Access Profile")

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
