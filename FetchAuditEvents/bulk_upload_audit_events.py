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
    if not iso_date_string: return None
    return iso_date_string.replace('T', ' ').split('.')[0].split('Z')[0]

def main():
    """Main orchestrator for uploading audit event JSON files."""
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        # --- Stage 1: Load main event data ---
        print("\n--- Starting upload for audit_events.json ---")
        try:
            with open("audit_events.json", 'r') as f: main_event_data = json.load(f)
            
            if main_event_data:
                print("Clearing old data from AuditEventLog...")
                cursor.execute("TRUNCATE TABLE AuditEventLog")
                
                records = [ (item.get('event_id'), item.get('technical_name'), format_datetime(item.get('created_datetime')), item.get('actor_id'), item.get('actor_name'), item.get('target_id'), item.get('target_name'), item.get('object_id'), item.get('object_name'), item.get('object_type')) for item in main_event_data ]
                sql = "INSERT INTO AuditEventLog (event_id, technical_name, created_datetime, actor_id, actor_name, target_id, target_name, object_id, object_name, object_type) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                
                cursor.executemany(sql, records)
                print(f"-> Successfully loaded {cursor.rowcount} records into AuditEventLog.")
            else:
                print("audit_events.json is empty. Skipping.")

        except FileNotFoundError:
            print("WARNING: audit_events.json not found. Skipping main event load.")

        # --- Stage 2: Load attribute data ---
        print("\n--- Starting upload for audit_event_attributes.json ---")
        try:
            with open("audit_event_attributes.json", 'r') as f: attribute_data = json.load(f)
            
            if attribute_data:
                print("Clearing old data from AuditEventLog_Attributes...")
                cursor.execute("TRUNCATE TABLE AuditEventLog_Attributes")
                
                records = [ (item.get('event_id'), item.get('attribute_key'), item.get('attribute_value')) for item in attribute_data ]
                sql = "INSERT INTO AuditEventLog_Attributes (event_id, attribute_key, attribute_value) VALUES (%s, %s, %s)"
                
                cursor.executemany(sql, records)
                print(f"-> Successfully loaded {cursor.rowcount} records into AuditEventLog_Attributes.")
            else:
                print("audit_event_attributes.json is empty. Skipping.")

        except FileNotFoundError:
            print("WARNING: audit_event_attributes.json not found. Skipping attribute load.")
        
        db_connection.commit()
        print("\nAudit event data upload complete.")

    except Error as e:
        print(f"An error occurred during the loading process: {e}")
        db_connection.rollback()
    finally:
        cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
