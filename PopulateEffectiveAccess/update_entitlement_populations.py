# update_entitlement_populations.py

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

def get_db_connection(config):
    """Establishes a database connection."""
    try:
        db_connection = mysql.connector.connect(**config)
        if db_connection.is_connected():
            return conn
    except Error as e:
        print(f"FATAL: Error connecting to MySQL database: {e}")
        return None

def main():
    """
    Calculates the true population of each entitlement by combining assignments
    from both IdentityEntitlementAssignments_Filtered and 
    IdentityEffectiveEntitlements_Filtered, then updates the main 'entitlements' table.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    
    db_connection = get_db_connection()
        if db_connection:
            cursor = db_connection.cursor(dictionary=True)
            print("Connected to MySQL database. Querying 'exact_correlations'...")
    
    try:
        # === Step 1: Calculate the true, combined population from both filtered sources ===
        print("\n--- Step 1: Calculating combined entitlement populations from filtered sources ---")
        
        # ===================================================================
        # === THE FIX IS HERE: Using joins to ensure a consistent identity ID ===
        # ===================================================================
        combined_counts_query = """
        SELECT
            ent_id,
            COUNT(ident_id) as pop_count
        FROM (
            -- Get assignments from the direct assignment table, joining to get the integer ID
            SELECT
                T1.entitlement_id AS ent_id,
                T2.id AS ident_id
            FROM
                IdentityEntitlementAssignments_Filtered AS T1
            JOIN
                Identities_Filtered AS T2 ON T1.identity_id = T2.id

            UNION -- This combines the results and automatically makes them distinct
            
            -- Get assignments from the effective entitlements table (already has the integer ID)
            SELECT
                entitlement_id AS ent_id,
                identity_id AS ident_id
            FROM
                IdentityEffectiveEntitlements_Filtered

        ) AS combined_assignments
        GROUP BY
            ent_id;
        """
        
        cursor.execute(combined_counts_query)
        ent_pop_counts = cursor.fetchall()
        
        if not ent_pop_counts:
            print("  -> No entitlement populations found in the filtered tables. The 'entitlements' table will be zeroed.");
            cursor.execute("UPDATE entitlements SET population_size = 0")
            db_connection.commit()
            return

        print(f"  -> Calculated combined populations for {len(ent_pop_counts)} unique entitlements.")

        # === Step 2: Update the main 'entitlements' table with these new counts ===
        print("\n--- Step 2: Updating the main 'entitlements' table with new population counts ---")
        
        print("  - Resetting all population counts in 'entitlements' table to zero...")
        cursor.execute("UPDATE entitlements SET population_size = 0")

        update_params = [(row['pop_count'], row['ent_id']) for row in ent_pop_counts]
        
        print(f"  - Performing bulk update for {len(update_params)} entitlements...")
        update_sql = "UPDATE entitlements SET population_size = %s WHERE entitlement_id = %s"
        
        cursor.executemany(update_sql, update_params)
        print(f"  -> Successfully updated {cursor.rowcount} entitlement records.")

        db_connection.commit()
        print("\nEntitlement populations have been successfully updated.")

    except Error as e:
        print(f"    - DATABASE ERROR during processing: {e}")
        import traceback
        traceback.print_exc()
        db_connection.rollback()
    finally:
        if cursor: cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
