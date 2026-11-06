# trigger_owner_email.py

import json
import requests
import mysql.connector
from mysql.connector import Error

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

def get_db_connection(config):
    """Establishes a database connection."""
    try:
        db_connection = mysql.connector.connect(**config)
        if db_connection.is_connected(): return conn
    except Error as e:
        print(f"FATAL: Error connecting to MySQL: {e}"); return None

def get_sailpoint_token(sp_config):
    """Authenticates to SailPoint and returns a bearer token."""
    token_url = f"{sp_config['tenant_url']}/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": sp_config['client_id'],
        "client_secret": sp_config['client_secret']
    }
    print("--- Authenticating to SailPoint ISC ---")
    response = requests.post(token_url, data=payload)
    
    if response.status_code == 200:
        print("--- Authentication Successful ---")
        return response.json().get("access_token")
    else:
        print(f"!!! SailPoint Authentication Failed. Status: {response.status_code}")
        print(response.text)
        return None

def trigger_workflow(sp_config, token, workflow_inputs):
    """Triggers a specific workflow in SailPoint ISC."""
    trigger_url = f"{sp_config['tenant_url']}/v3/workflows/{sp_config['workflow_id']}/trigger"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print(f"--- Triggering Workflow: {sp_config['workflow_id']} ---")
    response = requests.post(trigger_url, headers=headers, json=workflow_inputs)
    
    if response.status_code == 202:
        print("--- Workflow Triggered Successfully (Status 202 Accepted) ---")
        return True
    else:
        print(f"!!! Workflow Trigger Failed. Status: {response.status_code}")
        print(response.text)
        return False

def main():
    """
    Main function to find an entitlement owner and trigger an email workflow.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    # --- 1. Authenticate to SailPoint ---
    sp_config = config.get("SailPoint")
    auth_token = get_sailpoint_token(sp_config)
    if not auth_token:
        return

    # --- 2. Get Data from our Database ---
    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    cursor = db_connection.cursor(dictionary=True, buffered=True)

    try:
        # Example: Find the owner of the first entitlement in the list
        cursor.execute("SELECT name, owner_name, owner_email FROM entitlements WHERE owner_email IS NOT NULL LIMIT 1")
        entitlement_to_notify = cursor.fetchone()

        if not entitlement_to_notify:
            print("--- No entitlements with an owner email found in the database. ---")
            return

        print(f"--- Found entitlement '{entitlement_to_notify['name']}' owned by '{entitlement_to_notify['owner_email']}' ---")

        # --- 3. Prepare the Workflow Inputs ---
        # This payload must match the input schema you defined in the ISC Workflow
        workflow_payload = {
            "recipientEmail": entitlement_to_notify['owner_email'],
            "emailSubject": f"Action Required: Review for Entitlement '{entitlement_to_notify['name']}'",
            "emailBody": f"Hello {entitlement_to_notify['owner_name']},\n\nThis is an automated notification to ask you to review the entitlement '{entitlement_to_notify['name']}'.\n\nPlease verify its current members and description.\n\nThank you,\nYour Automated Role Mining Bot",
            "entitlementName": entitlement_to_notify['name']
        }
        
        # --- 4. Trigger the Workflow ---
        trigger_workflow(sp_config, auth_token, workflow_payload)

    except Error as e:
        print(f"    - DATABASE ERROR: {e}")
    finally:
        if cursor: cursor.close()
        if db_connection.and db_connection.is_connected(): db_connection.close(); print("Database connection closed.")


if __name__ == "__main__":
    main()
