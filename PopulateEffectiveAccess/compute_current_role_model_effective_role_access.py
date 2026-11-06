# compute_current_role_model_effective_role_access.py

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


def calculate_and_load_effective_access(db_connection.:
    """
    Calculates and loads effective entitlements for roles, using the string-based
    entitlement_id for consistency.
    """
    print("\n--- Starting effective role access calculation ---")
    cursor = db_connection.cursor()
    
    try:
        print("  - Clearing old effective access data...")
        cursor.execute("TRUNCATE TABLE CurrentRoleModel_RoleEffectiveEntitlements")
        db_connection.commit()

        # --- Stage 1: Insert INHERITED entitlements from Access Profiles ---
        print("  - Calculating and inserting inherited entitlements...")
        
        inherited_query = """
        INSERT INTO CurrentRoleModel_RoleEffectiveEntitlements 
        (role_id, role_name, access_profile_id, access_profile_name, entitlement_id, entitlement_name)
        (
            SELECT
                rap.role_id,
                rap.role_name,
                rap.access_profile_id,
                rap.access_profile_name,
                ape.entitlement_id, -- Using the string ID directly
                ape.entitlement_name
            FROM
                CurrentRoleModel_RoleAccessProfiles rap
            JOIN
                CurrentRoleModel_AccessProfileEntitlements ape ON rap.access_profile_id = ape.access_profile_id
        );
        """
        cursor.execute(inherited_query)
        inherited_count = cursor.rowcount
        print(f"  -> Loaded {inherited_count} inherited entitlement records.")
        db_connection.commit()

        # --- Stage 2: Insert DIRECTLY assigned entitlements ---
        print("  - Calculating and inserting direct entitlements...")
        
        direct_query = """
        INSERT INTO CurrentRoleModel_RoleEffectiveEntitlements
        (role_id, role_name, access_profile_id, access_profile_name, entitlement_id, entitlement_name)
        (
            SELECT
                role_id,
                role_name,
                NULL, -- Use NULL for the access_profile_id
                'Directly Assigned',
                entitlement_id, -- Using the string ID directly
                entitlement_name
            FROM
                CurrentRoleModel_RoleEntitlements
        );
        """
        cursor.execute(direct_query)
        direct_count = cursor.rowcount
        print(f"  -> Loaded {direct_count} direct entitlement records.")
        db_connection.commit()

        total_count = inherited_count + direct_count
        print(f"\nSuccessfully calculated and loaded a total of {total_count} effective entitlement records.")

    except Error as e:
        print(f"    - DATABASE ERROR during calculation: {e}")
        db_connection.rollback()
    finally:
        cursor.close()

def main():
    """Main orchestrator for the script."""
    try:
        with open('config.json') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found. Please ensure it exists."); return

   db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)

    try:
        calculate_and_load_effective_access(db_connection.
    finally:
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
