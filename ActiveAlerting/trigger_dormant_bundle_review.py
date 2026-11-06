# trigger_dormant_bundle_review.py

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

# --- Helper Functions ---
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

def get_bundle_members_html(cursor, bundle_id, bundle_type):
    """Fetches the members of a Role or AP and formats them as HTML."""
    print(f"    *--> [get_bundle_members_html] called for {bundle_type} ID: {bundle_id}")
    
    if bundle_type == "Role":
        sql = """
            SELECT DISTINCT I.name, I.email FROM IdentityRoleAssignments AS IRA
            JOIN Identities AS I ON I.id = IRA.identity_id
            WHERE IRA.role_id = %s
            LIMIT 20
        """
    else: # Access Profile
        sql = """
            SELECT DISTINCT I.name, I.email FROM IdentityAccessProfileAssignments AS IPAA
            JOIN Identities AS I ON I.id = IPAA.identity_id
            WHERE IPAA.access_profile_id = %s
            LIMIT 20
        """
    try:
        cursor.execute(sql, (bundle_id,))
        users = cursor.fetchall()
        if not users:
            return "<tr><td colspan='2'>No current members found.</td></tr>", 0
        rows = [f"<tr><td style='padding: 8px; border: 1px solid #dddddd;'>{user['name']}</td><td style='padding: 8px; border: 1px solid #dddddd;'>{user['email']}</td></tr>" for user in users]
        if len(users) >= 20:
            rows.append("<tr><td colspan='2' style='padding: 8px; font-style: italic;'>... and possibly more (display limited to 20).</td></tr>")
        return "".join(rows), len(users)
    except Error as e:
        print(f"      --> !!! WARNING: Could not fetch members: {e}")
        return "<tr><td colspan='2'>Error retrieving members.</td></tr>", 0

def get_bundle_composition_html(cursor, bundle_id, bundle_type):
    """
    Creates an HTML list of a bundle's composition by querying the correct
    database tables.
    """
    print(f"    *--> [get_bundle_composition_html] called for {bundle_type} ID: {bundle_id}")
    html = "<ul>"
    
    try:
        if bundle_type == "Role":
            sql = """
                SELECT DISTINCT entitlement_name, access_profile_name 
                FROM CurrentRoleModel_RoleEffectiveEntitlements 
                WHERE role_id = %s 
                ORDER BY access_profile_name, entitlement_name
            """
            cursor.execute(sql, (bundle_id,))
            results = cursor.fetchall()
            if not results:
                html += "<li>No entitlements or access profiles found.</li>"
            else:
                last_ap = None
                for item in results:
                    if item['access_profile_name'] != last_ap:
                        if last_ap is not None:
                            html += "</ul></li>" # Close previous sub-list
                        html += f"<li><b>Access Profile:</b> {item['access_profile_name']}<ul>"
                        last_ap = item['access_profile_name']
                    html += f"<li>{item['entitlement_name']}</li>"
                html += "</ul></li>" # Close the final sub-list
        
        else: # Access Profile
            sql = """
                SELECT entitlement_name 
                FROM CurrentRoleModel_AccessProfileEntitlements 
                WHERE access_profile_id = %s 
                ORDER BY entitlement_name
            """
            cursor.execute(sql, (bundle_id,))
            results = cursor.fetchall()
            if not results:
                html += "<li>No entitlements found.</li>"
            else:
                for item in results:
                    html += f"<li><b>Entitlement:</b> {item['entitlement_name']}</li>"
        
        html += "</ul>"
        return html

    except Error as e:
        print(f"      --> !!! WARNING: Could not fetch bundle composition: {e}")
        return "<ul><li>Error retrieving composition details.</li></ul>"

def main():
    """Main orchestrator for the dormant bundle review script."""
    print("======================================================================")
    print("=== Starting Dormant Bundle (Role/AP) Review Trigger Script ===")
    print("======================================================================")
    db_connection = None
    cursor = None
    try:
        print("[STEP 1] Loading configuration files...")
        with open('config.json') as f:
            config = json.load(f)
        with open('email_template_dormant_bundle.html', 'r') as f:
            email_template_string = f.read()
        print("    --> All configuration files loaded successfully.")

        print("\n[STEP 2] Authenticating to SailPoint ISC...")
        isc_config = config.get("ISC")
        auth_token = get_sailpoint_token(isc_config)
        
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
        print("\n[STEP 4] Creating database cursor...")

        print("    --> Cursor created successfully.")
        
        print("\n[STEP 5] Querying for dormant Roles and Access Profiles...")
        sixty_days_ago = datetime.now() - timedelta(days=60)
        print(f"    --> Calculated inactivity threshold date: {sixty_days_ago.strftime('%Y-%m-%d')}")
        
        # --- Process Roles ---
        cursor.execute("SELECT * FROM CurrentRoleModel_Roles WHERE modified < %s", (sixty_days_ago,))
        dormant_roles = cursor.fetchall()
        print(f"    --> Found {len(dormant_roles)} dormant Roles.")
        
        # --- Process Access Profiles ---
        cursor.execute("SELECT * FROM CurrentRoleModel_AccessProfiles WHERE modified < %s", (sixty_days_ago,))
        dormant_aps = cursor.fetchall()
        print(f"    --> Found {len(dormant_aps)} dormant Access Profiles.")
        
        all_dormant_bundles = dormant_roles + dormant_aps
        print("=" * 70)

        for i, bundle in enumerate(all_dormant_bundles):
            bundle_type = "Role" if 'assignmentCriteria' in bundle else "Access Profile"
            
            print(f"\nProcessing Dormant {bundle_type} #{i+1}: '{bundle['name']}'")
            print("  [RAW BUNDLE DATA]:")
            print(f"    {json.dumps(bundle, default=str)}")

            print("  [SUB-STEP 1] Fetching current members...")
            user_table_rows_html, member_count = get_bundle_members_html(cursor, bundle['id'], bundle_type)
            print(f"    --> Found {member_count} current members.")

            print("  [SUB-STEP 2] Fetching bundle composition...")
            composition_html = get_bundle_composition_html(cursor, bundle['id'], bundle_type)
            print(f"    --> Composition HTML generated.")

            print("  [SUB-STEP 3] Generating email content from template...")
            
            email_subject = f"Review Requested: Dormant {bundle_type} - \"{bundle['name']}\""
            
            template_data = {
                "owner_name": bundle.get('owner_name') or 'Bundle Owner',
                "bundle_type": bundle_type,
                "bundle_name": bundle['name'],
                "description": bundle.get('description', 'N/A'),
                "last_modified_date": bundle['modified'].strftime('%Y-%m-%d %H:%M'),
                "composition_html": composition_html,
                "population": member_count,
                "user_table_rows": user_table_rows_html
            }
            email_body = email_template_string.format(**template_data)
            print("    --> Email subject and body generated.")

            workflow_payload = { 
                "activity": { "ActivityName": f"Dormant {bundle_type} Notification", "ActivityType": f"Dormant{bundle_type}Notification" },
                "target_bundle": bundle,
                "email": { "subject": email_subject, "body": email_body }
            }
            
            print("  [SUB-STEP 4] Triggering workflow...")
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
