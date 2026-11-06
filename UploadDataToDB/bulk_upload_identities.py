# bulk_upload_identities.py

import json
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


def format_datetime(iso_date_string):
    """Safely converts ISO 8601 date string to MySQL DATETIME format."""
    if not iso_date_string:
        return None
    return iso_date_string.replace('T', ' ').split('.')[0].split('Z')[0]

def main():
    """
    Main orchestrator for reading identities.json and loading it into the
    Identities, Identity_Accounts, and Identity_Attributes tables.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    try:
        print("Reading identities.json file...")
        with open('identities.json', 'r') as f: identity_data = json.load(f)
        print(f"-> Found {len(identity_data)} identity records to process.")
    except FileNotFoundError:
        print("FATAL: identities.json not found. Please run the fetch script first."); return
    if not identity_data:
        print("identities.json is empty. Nothing to upload."); return

    # Prepare records for all three tables
    identity_records = []
    account_records = []
    attribute_records = []

    print("Parsing records for database insertion...")
    for item in identity_data:
        identity_id = item.get('id')
        if not identity_id:
            continue # Skip records with no main ID

        # Prepare the record for the main 'Identities' table
        identity_records.append((
            identity_id, item.get('name'), item.get('email'), item.get('firstName'),
            item.get('lastName'), item.get('displayName'), item.get('inactive'),
            item.get('isManager'), item.get('status'), item.get('employeeNumber'),
            format_datetime(item.get('created')), format_datetime(item.get('modified')),
            item.get('accountCount')
        ))

        # Prepare records for the nested 'accounts'
        for account in item.get('accounts', []):
            source = account.get('source', {})
            account_records.append((
                identity_id, account.get('id'), account.get('name'),
                account.get('accountId'), source.get('id'), source.get('name'),
                format_datetime(account.get('created')), account.get('privileged')
            ))
        
        # ===================================================================
        # === THE NEW LOGIC IS HERE ===
        # Prepare records for the nested 'attributes' object
        # The 'attributes' field is a dictionary of key-value pairs
        for attr_name, attr_value in item.get('attributes', {}).items():
            # Convert value to string to handle various data types (booleans, numbers, etc.)
            attribute_records.append((identity_id, attr_name, str(attr_value)))
        # ===================================================================

    # --- Perform the three-stage bulk upload ---
    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        print("\nDisabling foreign key checks for bulk load...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")

        # Stage 1: Load main Identities table
        print("Clearing old data and loading into Identities table...")
        cursor.execute("TRUNCATE TABLE Identities")
        identity_sql = "INSERT INTO Identities (id, name, email, firstName, lastName, displayName, inactive, isManager, status, employeeNumber, created, modified, accountCount) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
        cursor.executemany(identity_sql, identity_records)
        print(f"-> Loaded {cursor.rowcount} records into Identities.")

        # Stage 2: Load nested Identity_Accounts table
        print("Clearing old data and loading into Identity_Accounts table...")
        cursor.execute("TRUNCATE TABLE Identity_Accounts")
        account_sql = "INSERT INTO Identity_Accounts (identity_id, account_id, account_name, native_identity, source_id, source_name, created, privileged) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
        cursor.executemany(account_sql, account_records)
        print(f"-> Loaded {cursor.rowcount} records into Identity_Accounts.")
        
        # Stage 3: Load nested Identity_Attributes table
        print("Clearing old data and loading into Identity_Attributes table...")
        cursor.execute("TRUNCATE TABLE Identity_Attributes")
        attribute_sql = "INSERT INTO Identity_Attributes (identity_id, attribute_name, attribute_value) VALUES (%s, %s, %s)"
        cursor.executemany(attribute_sql, attribute_records)
        print(f"-> Loaded {cursor.rowcount} records into Identity_Attributes.")

        db_connection.commit()
        print("\nIdentity data upload completed successfully.")
        
    except Error as e:
        print(f"An error occurred during the loading process: {e}"); db_connection.rollback()
    finally:
        print("Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
