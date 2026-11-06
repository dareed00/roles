# compute_audit_profiles.py

import json
import mysql.connector
from mysql.connector import Error
from collections import defaultdict
import statistics # Used for calculating the median

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

def calculate_audit_profiles(cursor, entity_type, id_col, name_col, table_name, profile_table):
    """
    A generic function to calculate and load audit profiles for a given entity type.
    """
    print(f"\n--- Starting Audit Profile Analysis for {entity_type} ---")
    
    # This query gets all stats EXCEPT the median, which is too complex for a single SQL query.
    base_stats_query = f"""
    WITH EventPairs AS (
        -- This CTE pairs ADD events with their subsequent REMOVE event for the same target
        SELECT
            add_event.object_id,
            add_event.object_name,
            add_event.target_name,
            add_event.created_datetime as add_date,
            MIN(remove_event.created_datetime) as remove_date
        FROM
            (SELECT * FROM AuditEventLog WHERE technical_name LIKE '{entity_type}_ADD_PASSED') add_event
        LEFT JOIN
            (SELECT * FROM AuditEventLog WHERE technical_name LIKE '{entity_type}_REMOVE_PASSED') remove_event
            ON add_event.object_id = remove_event.object_id AND add_event.target_name = remove_event.target_name AND remove_event.created_datetime > add_event.created_datetime
        GROUP BY
            add_event.event_id, add_event.object_id, add_event.object_name, add_event.target_name, add_event.created_datetime
    )
    SELECT
        m.{id_col} as object_id,
        m.{name_col} as object_name,
        MAX(CASE WHEN a.technical_name LIKE '%_ADD_PASSED' THEN a.created_datetime END) as last_add_date,
        MAX(CASE WHEN a.technical_name LIKE '%_REMOVE_PASSED' THEN a.created_datetime END) as last_remove_date,
        SUM(CASE WHEN a.technical_name LIKE '%_ADD_PASSED' AND a.created_datetime >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as adds_last_30_days,
        SUM(CASE WHEN a.technical_name LIKE '%_REMOVE_PASSED' AND a.created_datetime >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 ELSE 0 END) as removes_last_30_days,
        SUM(CASE WHEN a.technical_name LIKE '%_ADD_PASSED' AND a.created_datetime >= DATE_SUB(NOW(), INTERVAL 90 DAY) THEN 1 ELSE 0 END) as adds_last_90_days,
        SUM(CASE WHEN a.technical_name LIKE '%_REMOVE_PASSED' AND a.created_datetime >= DATE_SUB(NOW(), INTERVAL 90 DAY) THEN 1 ELSE 0 END) as removes_last_90_days,
        SUM(CASE WHEN a.technical_name LIKE '%_ADD_PASSED' THEN 1 ELSE 0 END) as total_adds,
        SUM(CASE WHEN a.technical_name LIKE '%_REMOVE_PASSED' THEN 1 ELSE 0 END) as total_removes,
        (SUM(CASE WHEN a.technical_name LIKE '%_ADD_PASSED' THEN 1 ELSE 0 END) - SUM(CASE WHEN a.technical_name LIKE '%_REMOVE_PASSED' THEN 1 ELSE 0 END)) as currently_active_assignments
    FROM {table_name} m
    LEFT JOIN AuditEventLog a ON m.{id_col} = a.object_id
    WHERE a.technical_name LIKE '{entity_type}_%'
    GROUP BY m.{id_col}, m.{name_col};
    """

    # This second, simpler query gets the raw data needed to calculate the median in Python.
    median_data_query = f"""
    WITH EventPairs AS (
        SELECT
            add_event.object_id,
            DATEDIFF(MIN(remove_event.created_datetime), add_event.created_datetime) as duration_days
        FROM
            (SELECT * FROM AuditEventLog WHERE technical_name LIKE '{entity_type}_ADD_PASSED') add_event
        JOIN
            (SELECT * FROM AuditEventLog WHERE technical_name LIKE '{entity_type}_REMOVE_PASSED') remove_event
            ON add_event.object_id = remove_event.object_id AND add_event.target_name = remove_event.target_name AND remove_event.created_datetime > add_event.created_datetime
        GROUP BY
            add_event.event_id, add_event.object_id
    )
    SELECT object_id, duration_days FROM EventPairs WHERE duration_days IS NOT NULL;
    """

    try:
        # Step 1: Calculate all stats except median
        print(f"  - Calculating base audit stats for all {entity_type}s...")
        cursor.execute(base_stats_query)
        base_stats_results = cursor.fetchall()
        
        # Store results in a dictionary for easy merging later
        final_profiles = {row['object_id']: row for row in base_stats_results}

        # Step 2: Calculate median in Python
        print(f"  - Calculating median assignment durations for all {entity_type}s...")
        cursor.execute(median_data_query)
        median_raw_data = cursor.fetchall()
        
        # Group durations by object_id
        durations_by_object = defaultdict(list)
        for row in median_raw_data:
            durations_by_object[row['object_id']].append(row['duration_days'])
            
        # Calculate median for each object and add it to our final profiles
        for object_id, durations in durations_by_object.items():
            if object_id in final_profiles:
                median_val = statistics.median(durations)
                final_profiles[object_id]['median_assignment_duration_days'] = median_val
        
        print(f"  -> Calculated profiles for {len(final_profiles)} {entity_type}s.")

        # Step 3: Bulk load the combined results
        if final_profiles:
            records_to_insert = []
            for profile in final_profiles.values():
                records_to_insert.append((
                    profile.get('object_id'), profile.get('object_name'),
                    profile.get('last_add_date'), profile.get('last_remove_date'),
                    profile.get('adds_last_30_days', 0), profile.get('removes_last_30_days', 0),
                    profile.get('adds_last_90_days', 0), profile.get('removes_last_90_days', 0),
                    profile.get('total_adds', 0), profile.get('total_removes', 0),
                    profile.get('median_assignment_duration_days'),
                    profile.get('currently_active_assignments', 0)
                ))
            
            print(f"  - Uploading {len(records_to_insert)} profiles to {profile_table}...")
            cursor.execute(f"TRUNCATE TABLE {profile_table}")
            upload_sql = f"""
            INSERT INTO {profile_table}
            (role_id, role_name, last_add_date, last_remove_date, adds_last_30_days, removes_last_30_days, adds_last_90_days, removes_last_90_days, total_adds, total_removes, median_assignment_duration_days, currently_active_assignments)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            # A bit of a hack to make the column names generic for all 3 tables
            if 'AccessProfile' in profile_table:
                upload_sql = upload_sql.replace('(role_id, role_name,', '(access_profile_id, access_profile_name,')
            elif 'Entitlement' in profile_table:
                upload_sql = upload_sql.replace('(role_id, role_name,', '(entitlement_id, entitlement_name,')

            cursor.executemany(upload_sql, records_to_insert)
            print(f"  -> Successfully loaded {cursor.rowcount} records.")

    except Error as e:
        print(f"    - DATABASE ERROR during {entity_type} audit analysis: {e}")
        raise # Re-raise the exception to trigger the rollback in main()


def main():
    """Main orchestrator for all audit profile analyses."""
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
    try:
        calculate_audit_profiles(cursor, "ROLE", "id", "name", "CurrentRoleModel_Roles", "Role_Audit_Profile")
        calculate_audit_profiles(cursor, "ACCESS_PROFILE", "id", "name", "CurrentRoleModel_AccessProfiles", "AccessProfile_Audit_Profile")
        calculate_audit_profiles(cursor, "ENTITLEMENT", "entitlement_id", "entitlement_name", "entitlements", "Entitlement_Audit_Profile")
        
        db_connection.commit()
    except Error:
        # The inner function will print the specific error
        db_connection.rollback()
    finally:
        if cursor: cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close()
            print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
