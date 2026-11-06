# trigger_dormant_entitlement_review.py

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

# --- Helper Functions (These are all correct and unchanged) ---
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
    print(f"    --> Auth Payload (secret redacted): {{'grant_type': 'client_credentials', 'client_id': '{isc_config['client_id']}', 'client_secret': '*****'}}")
    
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
    
    print(f"  [TRACE] Preparing to call API endpoint: {trigger_url}")
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

def get_current_members_html(cursor, native_entitlement_id):
    """Fetches the current members of an entitlement and returns them as an HTML table string."""
    print(f"    *--> [get_current_members_html] called for native entitlement ID: {native_entitlement_id}")
    
    sql = """
        SELECT DISTINCT I.name, I.email
        FROM (
            (SELECT identity_id FROM IdentityEntitlementAssignments_Filtered WHERE entitlement_id = %s)
            UNION
            (SELECT identity_id FROM IdentityEffectiveEntitlements_Filtered WHERE entitlement_id = %s)
        ) AS AllMembers
        JOIN Identities AS I ON I.id = AllMembers.identity_id
        LIMIT 20
    """
    
    try:
        print("        --> Executing member lookup query...")
        cursor.execute(sql, (native_entitlement_id, native_entitlement_id))
        users = cursor.fetchall()
        print(f"        --> Found {len(users)} members from query.")
        
        if not users:
            return "<tr><td colspan='2'>No current members found.</td></tr>", 0

        rows = [f"<tr><td style='padding: 8px; border: 1px solid #dddddd;'>{user['name']}</td><td style='padding: 8px; border: 1px solid #dddddd;'>{user['email']}</td></tr>" for user in users]
        
        if len(users) >= 20:
            rows.append("<tr><td colspan='2' style='padding: 8px; font-style: italic;'>... and possibly more (display limited to 20).</td></tr>")

        return "".join(rows), len(users)
    except Error as e:
        print(f"      --> !!! WARNING: Could not fetch members for entitlement: {e}")
        return "<tr><td colspan='2'>Error retrieving members.</td></tr>", 0

def main():
    """Main orchestrator for the dormant entitlement review script."""
    print("======================================================================")
    print("=== Starting Dormant Entitlement Review Trigger Script ===")
    print("======================================================================")
    db_connection = None
    cursor = None
    try:
        print("[STEP 1] Loading configuration files...")
        with open('config.json') as f: config = json.load(f)
        print("    --> 'config.json' loaded successfully.")

        try:
            with open('email_template_dormant.html', 'r') as f:
                email_template_string = f.read()
            print("    --> 'email_template_dormant.html' loaded successfully.")
        except FileNotFoundError:
            raise FileNotFoundError("FATAL: email_template_dormant.html not found.")

        print("\n[STEP 2] Authenticating to SailPoint ISC...")
        isc_config = config.get("DormantEmail")
        auth_token = get_sailpoint_token(isc_config)
        
        print("\n[STEP 3] Connecting to the database...")
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
        print("    --> Cursor created successfully.")
        
        print("\n[STEP 5] Querying for dormant entitlements...")
        ten_days_ago = datetime.now() - timedelta(days=10)
        print(f"    --> Calculated inactivity threshold date: {ten_days_ago.strftime('%Y-%m-%d')}")
        
        # ===================================================================
        # === THE FIX IS HERE: Added 'entitlement_id' to the SELECT statement ===
        # ===================================================================
        sql = """
            SELECT 
                id, entitlement_id, entitlement_name, source_name, description, owner_name, creation_timestamp,
                last_add_date, last_remove_date,
                GREATEST(COALESCE(last_add_date, '1970-01-01'), COALESCE(last_remove_date, '1970-01-01')) as most_recent_change
            FROM entitlements
            WHERE (last_remove_date IS NOT NULL OR last_add_date IS NOT NULL)
            HAVING most_recent_change < %s
        """
        cursor.execute(sql, (ten_days_ago,))
        dormant_entitlements = cursor.fetchall()
        print(f"    --> Found {len(dormant_entitlements)} dormant entitlements to process.")
        print("=" * 70)

        for i, ent in enumerate(dormant_entitlements):
            print(f"\nProcessing Dormant Entitlement #{i+1}: '{ent['entitlement_name']}'")
            print("  [RAW ENTITLEMENT DATA]:")
            print(f"    {json.dumps(ent, default=str)}")
            
            date_format = "%Y-%m-%d %H:%M:%S"
            last_change_date = datetime.strptime(str(ent['most_recent_change']), date_format)
            creation_timestamp_obj = datetime.strptime(str(ent['creation_timestamp']), date_format)

            last_change_type = "Unknown"
            last_add_dt = datetime.strptime(str(ent['last_add_date']), date_format) if ent.get('last_add_date') else datetime.min
            last_remove_dt = datetime.strptime(str(ent['last_remove_date']), date_format) if ent.get('last_remove_date') else datetime.min

            if last_add_dt >= last_remove_dt:
                last_change_type = "Access Added"
            else:
                last_change_type = "Access Removed"

            print(f"  [CALCULATED] Last change was '{last_change_type}' on {last_change_date.strftime('%Y-%m-%d')}")

            print("  [SUB-STEP 1] Fetching current members...")
            # Pass the native entitlement_id directly to save a lookup
            user_table_rows_html, member_count = get_current_members_html(cursor, ent['entitlement_id'])
            print(f"    --> Found {member_count} current members.")

            print("  [SUB-STEP 2] Generating email content from template...")
            
            email_subject = f"Review Requested: Dormant Entitlement - \"{ent['entitlement_name']}\""
            
            template_data = {
                "owner_name": ent.get('owner_name') or 'Bundle Owner',
                "entitlement_name": ent['entitlement_name'],
                "source_name": ent['source_name'],
                "creation_date": creation_timestamp_obj.strftime('%Y-%m-%d'),
                "description": ent.get('description', 'N/A'),
                "last_change_date": last_change_date.strftime('%Y-%m-%d'),
                "last_change_type": last_change_type,
                "population": member_count,
                "user_table_rows": user_table_rows_html
            }
            email_body = email_template_string.format(**template_data)
            print("    --> Email subject and body generated.")

            workflow_payload = { 
                "activity": {"ActivityName": "Dormant Entitlement Notification", "ActivityType": "DormantEntitlementNotification"},
                "entitlement_details": ent,
                "email": { "subject": email_subject, "body": email_body }
            }
            
            print("  [SUB-STEP 3] Triggering workflow...")
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
