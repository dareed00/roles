import os
import json
import requests # Added back for manual token acquisition
from datetime import datetime
import mysql.connector
from mysql.connector import Error

# Import the SailPoint V3 SDK components
from sailpoint.v3 import Configuration, ApiClient
from sailpoint.v3.api import RolesApi, AccessProfilesApi

# --- Configuration ---
# SailPoint ISC API Credentials (read from environment variables for security)
TENANT_URL = os.getenv("SAILPOINT_TENANT_URL")
CLIENT_ID = os.getenv("SAILPOINT_CLIENT_ID")
CLIENT_SECRET = os.getenv("SAILPOINT_CLIENT_SECRET")

# MySQL Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'password',
    'database': 'bundleBuilder'
}

# --- Manual Access Token Acquisition (for SDK v1.4.2 compatibility) ---
def get_access_token():
    """
    Manually obtains an OAuth 2.0 access token from SailPoint Identity Security Cloud
    using the requests library. This is a workaround for older SDK versions.
    """
    if not TENANT_URL or not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError(
            "SAILPOINT_TENANT_URL, SAILPOINT_CLIENT_ID, and SAILPOINT_CLIENT_SECRET "
            "environment variables must be set."
        )

    token_url = f"{TENANT_URL}/oauth/token"
    headers = {'Content-Type': 'application/json'}
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }

    try:
        response = requests.post(token_url, headers=headers, json=data)
        response.raise_for_status() # Raise an exception for HTTP errors
        token_data = response.json()
        return token_data.get('access_token')
    except requests.exceptions.RequestException as e:
        print(f"Error obtaining access token: {e}")
        if 'response' in locals() and response is not None:
             print(f"Response status code: {response.status_code}")
             print(f"Response content: {response.text}")
        return None

# --- SDK Initialization (Modified for v1.4.2) ---
def initialize_sailpoint_sdk():
    """
    Initializes the SailPoint V3 SDK Configuration and API Client
    for SDK version 1.4.2 by manually providing the access token.
    """
    # First, manually get the access token
    print("Manually obtaining access token for SDK v1.4.2...")
    access_token = get_access_token()
    if not access_token:
        raise Exception("Failed to obtain access token, cannot initialize SDK.")

    # 1. Create a Configuration object, primarily setting the host
    configuration = Configuration(host=TENANT_URL)
    
    # 2. Inject the manually obtained access token into the configuration
    # This is how older SDK versions handle bearer token authentication.
    configuration.access_token = access_token
    
    # 3. Initialize the ApiClient with the configuration
    api_client = ApiClient(configuration=configuration)
    
    return api_client

# --- Data Fetching Functions using SDK ---
def fetch_all_roles_sdk(roles_api):
    """
    Fetches all roles from SailPoint ISC using the SDK, handling pagination.
    """
    all_roles = []
    offset = 0
    limit = 250 # Max limit for SailPoint V3 API list endpoints

    print("Fetching roles with SDK (handling pagination)...")
    while True:
        try:
            # list_roles returns a list of Role objects (SDK model objects)
            current_page_roles = roles_api.list_roles(offset=offset, limit=limit)
            if not current_page_roles:
                break # No more roles
            
            all_roles.extend(current_page_roles)
            
            if len(current_page_roles) < limit:
                break # Last page
            
            offset += limit
            print(f"  Fetched {len(all_roles)} roles so far...")
        except Exception as e:
            print(f"Error fetching roles page (offset={offset}): {e}")
            return None # Indicate failure
    return all_roles

def fetch_all_access_profiles_sdk(access_profiles_api):
    """
    Fetches all access profiles from SailPoint ISC using the SDK, handling pagination.
    """
    all_access_profiles = []
    offset = 0
    limit = 250 # Max limit

    print("Fetching access profiles with SDK (handling pagination)...")
    while True:
        try:
            # list_access_profiles returns a list of AccessProfile objects (SDK model objects)
            current_page_aps = access_profiles_api.list_access_profiles(offset=offset, limit=limit)
            if not current_page_aps:
                break # No more access profiles
            
            all_access_profiles.extend(current_page_aps)
            
            if len(current_page_aps) < limit:
                break # Last page
            
            offset += limit
            print(f"  Fetched {len(all_access_profiles)} access profiles so far...")
        except Exception as e:
            print(f"Error fetching access profiles page (offset={offset}): {e}")
            return None # Indicate failure
    return all_access_profiles

# --- Data Parsing and Insertion Functions ---
def parse_and_insert_roles(roles_sdk_objects, cnx):
    """
    Parses SailPoint ISC Role SDK objects and inserts them into CurrentRoleModel_Roles table.
    """
    if not roles_sdk_objects:
        print("No role data to insert.")
        return

    cursor = cnx.cursor()
    insert_query = """
    INSERT IGNORE INTO CurrentRoleModel_Roles (
        id, name, description, enabled, requestable,
        owner_id, owner_name, created, modified,
        accessProfiles, assignmentCriteria, segments, load_timestamp
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    records_to_insert = []
    load_timestamp = datetime.now()

    for role_obj in roles_sdk_objects:
        # Access attributes directly from SDK objects
        role_id = role_obj.id
        name = role_obj.name
        description = role_obj.description
        enabled = role_obj.enabled
        requestable = role_obj.requestable

        # Handle owner - it's an IdentityReference object or None
        owner_id = role_obj.owner.id if role_obj.owner else None
        owner_name = role_obj.owner.name if role_obj.owner else None

        # Convert SDK datetime objects to native Python datetime or None
        # The SDK returns datetime objects directly if the value is present
        created = role_obj.created if role_obj.created else None
        modified = role_obj.modified if role_obj.modified else None
        
        # Convert SDK model lists/objects to serializable dictionaries and then to JSON strings
        # The SDK objects have a to_dict() method for this.
        access_profiles_json = json.dumps([ap.to_dict() for ap in role_obj.access_profiles]) if role_obj.access_profiles else None
        assignment_criteria_json = json.dumps(role_obj.assignment_criteria.to_dict()) if role_obj.assignment_criteria else None
        segments_json = json.dumps([s for s in role_obj.segments]) if role_obj.segments else None # segments is typically list of strings

        records_to_insert.append((
            role_id, name, description, enabled, requestable,
            owner_id, owner_name, created, modified,
            access_profiles_json, assignment_criteria_json, segments_json, load_timestamp
        ))
    
    try:
        if records_to_insert:
            cursor.executemany(insert_query, records_to_insert)
            cnx.commit()
            print(f"Successfully inserted/ignored {cursor.rowcount} Role records.")
        else:
            print("No role records prepared for insertion.")
    except Error as e:
        print(f"Error inserting role data: {e}")
        cnx.rollback()
    finally:
        cursor.close()

def parse_and_insert_access_profiles(access_profiles_sdk_objects, cnx):
    """
    Parses SailPoint ISC Access Profile SDK objects and inserts them into CurrentRoleModel_AccessProfiles table.
    """
    if not access_profiles_sdk_objects:
        print("No access profile data to insert.")
        return

    cursor = cnx.cursor()
    insert_query = """
    INSERT IGNORE INTO CurrentRoleModel_AccessProfiles (
        id, name, description, enabled, requestable,
        owner_id, owner_name, created, modified,
        source_id, source_name, entitlements, segments,
        provisioningCriteria, additionalOwners, load_timestamp
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    records_to_insert = []
    load_timestamp = datetime.now()

    for ap_obj in access_profiles_sdk_objects:
        # Access attributes directly from SDK objects
        ap_id = ap_obj.id
        name = ap_obj.name
        description = ap_obj.description
        enabled = ap_obj.enabled
        requestable = ap_obj.requestable

        # Handle owner - it's an IdentityReference object or None
        owner_id = ap_obj.owner.id if ap_obj.owner else None
        owner_name = ap_obj.owner.name if ap_obj.owner else None
        
        # Handle source - it's a SourceDto or None
        source_id = ap_obj.source.id if ap_obj.source else None
        source_name = ap_obj.source.name if ap_obj.source else None

        # Convert SDK datetime objects to native Python datetime or None
        created = ap_obj.created if ap_obj.created else None
        modified = ap_obj.modified if ap_obj.modified else None

        # Convert SDK model lists/objects to serializable dictionaries and then to JSON strings
        entitlements_json = json.dumps([ent.to_dict() for ent in ap_obj.entitlements]) if ap_obj.entitlements else None
        segments_json = json.dumps([s for s in ap_obj.segments]) if ap_obj.segments else None # segments is typically list of strings
        provisioning_criteria_json = json.dumps(ap_obj.provisioning_criteria.to_dict()) if ap_obj.provisioning_criteria else None
        additional_owners_json = json.dumps([owner.to_dict() for owner in ap_obj.additional_owners]) if ap_obj.additional_owners else None

        records_to_insert.append((
            ap_id, name, description, enabled, requestable,
            owner_id, owner_name, created, modified,
            source_id, source_name, entitlements_json, segments_json,
            provisioning_criteria_json, additional_owners_json, load_timestamp
        ))
    
    try:
        if records_to_insert:
            cursor.executemany(insert_query, records_to_insert)
            cnx.commit()
            print(f"Successfully inserted/ignored {cursor.rowcount} Access Profile records.")
        else:
            print("No access profile records prepared for insertion.")
    except Error as e:
        print(f"Error inserting access profile data: {e}")
        cnx.rollback()
    finally:
        cursor.close()

# --- Main Execution Flow ---
def main():
    print("Starting SailPoint ISC Role and Access Profile data ingestion using SDK (v1.4.2 compatible)...")

    api_client = None
    mysql_cnx = None

    try:
        # 1. Initialize SailPoint SDK
        print("Initializing SailPoint SDK...")
        api_client = initialize_sailpoint_sdk()
        roles_api = RolesApi(api_client)
        access_profiles_api = AccessProfilesApi(api_client)
        print("SailPoint SDK initialized successfully.")

        # Connect to MySQL
        print("Connecting to MySQL database...")
        mysql_cnx = mysql.connector.connect(**DB_CONFIG)
        print("Successfully connected to MySQL.")

        # 2. Fetch Roles
        all_roles = fetch_all_roles_sdk(roles_api)
        if all_roles is None:
            print("Failed to retrieve roles. Exiting.")
            return
        print(f"Total retrieved {len(all_roles)} roles.")

        # 3. Parse and Insert Roles
        if all_roles:
            parse_and_insert_roles(all_roles, mysql_cnx)

        # 4. Fetch Access Profiles
        all_access_profiles = fetch_all_access_profiles_sdk(access_profiles_api)
        if all_access_profiles is None:
            print("Failed to retrieve access profiles. Exiting.")
            return
        print(f"Total retrieved {len(all_access_profiles)} access profiles.")

        # 5. Parse and Insert Access Profiles
        if all_access_profiles:
            parse_and_insert_access_profiles(all_access_profiles, mysql_cnx)

    except ValueError as ve:
        print(f"Configuration Error: {ve}")
    except Error as e:
        print(f"Database operation failed: {e}")
        if mysql_cnx:
            mysql_cnx.rollback()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        # The ApiClient should be closed to release resources.
        if api_client:
            api_client.close()
            
        if mysql_cnx and mysql_cnx.is_connected():
            mysql_cnx.close()
            print("MySQL connection closed.")
        print("Data ingestion process finished.")

if __name__ == "__main__":
    main()
