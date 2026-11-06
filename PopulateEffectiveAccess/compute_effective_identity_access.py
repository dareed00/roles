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


def calculate_and_load_inherited_assignments(db_connection.:
    """
    Calculates the effective entitlements for every identity that are INHERITED
    from roles and access profiles, and loads them into the
    IdentityEffectiveEntitlements table.
    """
    print("\n--- Starting inherited identity access calculation ---")
    
    # This query now ONLY calculates access from Roles and Access Profiles.
    # It explicitly excludes direct assignments.
    query = """
    INSERT INTO IdentityEffectiveEntitlements 
    (identity_id, identity_name, role_id, role_name, access_profile_id, access_profile_name, entitlement_id, entitlement_name)
    (
        -- 1. Get entitlements INHERITED from roles
        SELECT
            ira.identity_id,
            ira.identity_name,
            crre.role_id,
            crre.role_name,
            crre.access_profile_id, -- This shows the path within the role
            crre.access_profile_name,
            crre.entitlement_id,
            crre.entitlement_name
        FROM IdentityRoleAssignments ira
        JOIN CurrentRoleModel_RoleEffectiveEntitlements crre ON ira.role_id = crre.role_id

        UNION ALL

        -- 2. Get entitlements INHERITED from stand-alone access profiles
        SELECT
            iapa.identity_id,
            iapa.identity_name,
            'N/A' as role_id, -- This access did not come from a role
            'N/A' as role_name,
            ape.access_profile_id,
            ape.access_profile_name,
            ape.entitlement_id,
            ape.entitlement_name
        FROM IdentityAccessProfileAssignments iapa
        JOIN CurrentRoleModel_AccessProfileEntitlements ape ON iapa.access_profile_id = ape.access_profile_id
    )
    ON DUPLICATE KEY UPDATE
        -- If a duplicate is found (e.g., same path from two different roles),
        -- we just need to confirm an existing record. This prevents errors.
        identity_id = VALUES(identity_id);
    """
    
    cursor = db_connection.cursor()
    
    try:
        # Disabling checks for the placeholder 'N/A' values
        print("  - Disabling foreign key checks for placeholders...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")

        print("  - Clearing old inherited assignment data...")
        cursor.execute("TRUNCATE TABLE IdentityEffectiveEntitlements")
        
        print("  - Calculating and inserting new inherited assignment data...")
        cursor.execute(query)
        
        row_count = cursor.rowcount
        db_connection.commit()
        
        print(f"\nSuccessfully calculated and loaded {row_count} inherited assignment records.")

    except Error as e:
        print(f"    - DATABASE ERROR during calculation: {e}")
        db_connection.rollback()
    finally:
        print("  - Re-enabling foreign key checks...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        cursor.close()


def main():
    """Main orchestrator for the script."""
    try:
        with open('config.json') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found. Please ensure it exists.")
        return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)

    try:
        calculate_and_load_inherited_assignments(db_connection.
    finally:
        if db_connection.and db_connection.is_connected():
            db_connection.close()
            print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
