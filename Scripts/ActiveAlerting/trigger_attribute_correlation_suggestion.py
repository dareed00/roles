# trigger_attribute_correlation_suggestion.py
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
        raise ValueError("FATAL: 'AttributeEntitlementSimilarity' configuration block not found in config.json.")
    required_keys = ['token_url', 'client_id', 'client_secret', 'workflow_url']
    for key in required_keys:
        if key not in isc_config or not isc_config[key]:
            raise ValueError(f"FATAL: The key '{key}' is missing or empty in the 'AttributeEntitlementSimilarity' block of your config.json.")
    
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

def get_user_sample_html_from_list(user_list):
    """Formats a list of user dictionaries into an HTML list."""
    if not user_list:
        return "<ul><li>No users in this category.</li></ul>"
    
    sample_size = 5
    user_sample = user_list[:sample_size]
    
    user_lines = [f"<li>{user.get('UID', 'N/A')} ({user.get('jobTitle', 'No Title')})</li>" for user in user_sample]
    
    if len(user_list) > sample_size:
        user_lines.append(f"<li>... and {len(user_list) - sample_size} more.</li>")
        
    return f"<ul>{''.join(user_lines)}</ul>"

# ===================================================================
# === THE FIX IS HERE: A new helper to get entitlement population correctly ===
# ===================================================================
def get_entitlement_population(cursor, native_entitlement_id):
    """Gets the total population for a given NATIVE entitlement ID."""
    if not native_entitlement_id:
        return 0
    sql = """
        SELECT COUNT(DISTINCT identity_id) as pop_count
        FROM (
            (SELECT identity_id FROM IdentityEntitlementAssignments_Filtered WHERE entitlement_id = %s)
            UNION
            (SELECT identity_id FROM IdentityEffectiveEntitlements_Filtered WHERE entitlement_id = %s)
        ) AS AllMembers
    """
    try:
        cursor.execute(sql, (native_entitlement_id, native_entitlement_id))
        result = cursor.fetchone()
        return result['pop_count'] if result else 0
    except Error as e:
        print(f"      --> !!! WARNING: Could not fetch entitlement population: {e}")
        return 0


def main():
    """Main orchestrator for the attribute-to-entitlement correlation script."""
    print("======================================================================")
    print("=== Starting Attribute to Entitlement Correlation Trigger Script ===")
    print("======================================================================")
    db_connection = None
    cursor = None
    try:
        print("[STEP 1] Loading configuration files...")
        with open('config.json') as f: config = json.load(f)
        with open('email_template_attribute_correlation.html', 'r') as f: email_template_string = f.read()
        print("    --> All configuration files loaded successfully.")

        print("\n[STEP 2] Authenticating to SailPoint ISC...")
        isc_config = config.get("AttributeEntitlementSimilarity")
        auth_token = get_sailpoint_token(isc_config)
        
        print("\n[STEP 3] Connecting to the database...")
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
        
        print("\n[STEP 4] Querying for high-confidence attribute correlations...")
        similarity_threshold = 0.80
        
        sql = "SELECT * FROM Entitlement_to_Attribute_Correlations WHERE jaccard_score >= %s"
        cursor.execute(sql, (similarity_threshold,))
        correlations = cursor.fetchall()
        print(f"    --> Found {len(correlations)} high-confidence correlations to process.")
        print("=" * 70)

        for i, corr in enumerate(correlations):
            print(f"\nProcessing Correlation #{i+1} (ID: {corr['id']}, Score: {corr['jaccard_score']:.2%})")
            
            attribute_name = corr['attribute_name']
            attribute_value = corr['attribute_value']
            entitlement_name = corr['entitlement_name']
            source_name = corr['entitlement_source']
            attribute_population = corr['attribute_population']

            print(f"    --> Comparing Attribute '{attribute_name}' with Entitlement '{entitlement_name}'")

            # ===================================================================
            # === THE FIX IS HERE: Look up the native entitlement_id ===
            # ===================================================================
            print("  [SUB-STEP 1] Fetching native ID for the entitlement...")
            cursor.execute("SELECT entitlement_id FROM entitlements WHERE entitlement_name = %s AND source_name = %s", (entitlement_name, source_name))
            entitlement_record = cursor.fetchone()

            if not entitlement_record or not entitlement_record.get('entitlement_id'):
                print(f"    --> !!! SKIPPING: Could not find a matching native entitlement_id for '{entitlement_name}' from source '{source_name}'.")
                continue
            
            native_entitlement_id = entitlement_record['entitlement_id']
            print(f"    --> Found native entitlement_id: {native_entitlement_id}")

            print("  [SUB-STEP 2] Fetching delta users (attribute but not entitlement)...")
            delta_users_table = "Entitlement_Attribute_Differing_UIDs"
            cursor.execute(f"SELECT * FROM {delta_users_table} WHERE correlation_id = %s AND is_in_attribute_only = 1", (corr['id'],))
            delta_users = cursor.fetchall()
            print(f"    --> Found {len(delta_users)} delta users.")
            
            population_overlap = attribute_population - len(delta_users)
            
            print("  [SUB-STEP 3] Calculating total entitlement population...")
            total_entitlement_population = get_entitlement_population(cursor, native_entitlement_id)
            print(f"    --> Total population for entitlement is: {total_entitlement_population}")

            print("  [SUB-STEP 4] Generating email content...")
            template_data = {
                "primary_grouping_column": attribute_name,
                "primary_value": attribute_value,
                "attribute_value": entitlement_name,
                "access_source_name": source_name,
                "jaccard_score_percent": f"{corr['jaccard_score']:.1%}",
                "population_primary": attribute_population,
                "population_attribute": total_entitlement_population,
                "population_overlap": population_overlap,
                "delta_user_count": len(delta_users),
                "delta_users_list": get_user_sample_html_from_list(delta_users)
            }
            email_body = email_template_string.format(**template_data)
            email_subject = f"High-Confidence Suggestion: Correlate '{attribute_name}' to Entitlement"

            workflow_payload = {
                "activity": {"ActivityName": "Attribute to Entitlement Correlation Found", "ActivityType": "AttributeToEntitlementCorrelationFound"},
                "correlation_details": corr,
                "email": {"subject": email_subject, "body": email_body},
                "entitlement_id":native_entitlement_id
            }
            
            print("  [SUB-STEP 5] Triggering workflow...")
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
Suggestions