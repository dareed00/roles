# compute_entitlement_profiles.py

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


def main():
    """
    Main orchestrator for calculating detailed statistical profiles for each
    entitlement, using a complete view of all direct and inherited assignments.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
    try:
        print("\n--- Starting Entitlement Profile Analysis (Corrected Logic) ---")
        
        # This single, powerful query now correctly calculates all stats by first
        # creating a complete view of all direct and inherited assignments.
        query = """
        WITH All_Assignments AS (
            -- Set 1: All DIRECT assignments from the dedicated table
            SELECT 
                identity_id, 
                entitlement_id,
                'DIRECT' as assignment_type
            FROM 
                IdentityEntitlementAssignments

            UNION -- Using UNION, not UNION ALL, to start with a distinct set of user-entitlement pairs

            -- Set 2: All INHERITED assignments from the effective entitlements table
            SELECT 
                identity_id, 
                entitlement_id,
                -- Categorize the assignment type based on the role_id path
                CASE
                    WHEN role_id = 'N/A' THEN 'AP_BIRTHRIGHT'
                    ELSE 'ROLE_BIRTHRIGHT'
                END as assignment_type
            FROM 
                IdentityEffectiveEntitlements
        )
        -- Now, join the main entitlements table against this complete set of assignments
        SELECT
            e.id as entitlement_pk,
            e.entitlement_id,
            e.entitlement_name,
            e.source_name,
            -- The total population is the count of distinct users with this entitlement
            COUNT(DISTINCT A.identity_id) as total_population,
            -- The counts for each source are the sum of matches for that type
            SUM(CASE WHEN A.assignment_type = 'DIRECT' THEN 1 ELSE 0 END) as count_direct,
            SUM(CASE WHEN A.assignment_type = 'AP_BIRTHRIGHT' THEN 1 ELSE 0 END) as count_via_ap_only,
            SUM(CASE WHEN A.assignment_type = 'ROLE_BIRTHRIGHT' THEN 1 ELSE 0 END) as count_via_role
        FROM
            entitlements e
        LEFT JOIN
            All_Assignments A ON e.entitlement_id = A.entitlement_id
        GROUP BY
            e.id, e.entitlement_id, e.entitlement_name, e.source_name;
        """

        print("  - Calculating statistics for all entitlements using complete assignment data...")
        cursor.execute(query)
        results = cursor.fetchall()
        print(f"  -> Calculated profiles for {len(results)} entitlements.")

        if not results:
            print("No entitlements found to profile. Exiting."); return

        # Prepare records for bulk insertion
        records_to_insert = [
            (
                row['entitlement_pk'], row['entitlement_name'], row['source_name'],
                row['total_population'], row['count_direct'],
                row['count_via_ap_only'], row['count_via_role']
            )
            for row in results
        ]

        # --- Upload all collected results in a single batch ---
        print("\n--- Uploading Entitlement Profiles to Database ---")
        
        print("  - Clearing old data from Entitlement_Analysis_Profile...")
        cursor.execute("TRUNCATE TABLE Entitlement_Analysis_Profile")
        
        upload_sql = """
        INSERT INTO Entitlement_Analysis_Profile
        (entitlement_id, entitlement_name, source_name, total_population, count_direct, count_via_ap_only, count_via_role)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(upload_sql, records_to_insert)
        db_connection.commit()
        print(f"-> Successfully uploaded {cursor.rowcount} entitlement profiles.")

    except Error as e:
        print(f"Database Error during analysis: {e}")
        db_connection.rollback()
    finally:
        if cursor: cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close()
            print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
