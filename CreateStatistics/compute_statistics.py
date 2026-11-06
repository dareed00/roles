# compute_statistics.py

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



# ===================================================================
# === Complex, Multi-Step Analysis Functions ===
# ===================================================================

def calculate_allocation_source_stats(cursor):
    """Calculates the source of entitlement allocations (Direct, Role, AP)."""
    print("  - Calculating: Entitlement Allocation Sources (Global)...")
    results = []
    try:
        query = """
        SELECT 
            SUM(CASE WHEN role_id = 'DIRECT' THEN 1 ELSE 0 END) as direct_count,
            SUM(CASE WHEN role_id != 'DIRECT' AND role_id != 'N/A' THEN 1 ELSE 0 END) as role_birthed_count,
            SUM(CASE WHEN role_id = 'N/A' THEN 1 ELSE 0 END) as ap_birthed_count
        FROM IdentityEffectiveEntitlements;
        """
        cursor.execute(query)
        row = cursor.fetchone()
        if row:
            results.append(("Entitlement Allocation Source", "Population", "Direct", None, row['direct_count'], None))
            results.append(("Entitlement Allocation Source", "Population", "Via Role", None, row['role_birthed_count'], None))
            results.append(("Entitlement Allocation Source", "Population", "Via Stand-alone AP", None, row['ap_birthed_count'], None))
    except Error as e:
        print(f"    - ERROR calculating Allocation Source Stats: {e}")
    return results

def calculate_segment_access_breakdown(cursor):
    """Calculates the average number of Roles, APs, and Entitlements per user segment."""
    print("  - Calculating: Access Breakdown by User Segment...")
    results = []
    segments = ['department', 'country', 'jobTitle', 'location', 'type']
    for segment in segments:
        print(f"    - Segmenting by: {segment}...")
        try:
            # CORRECTED: Changed T2.AttributeValue to T2.attribute_value and T2.AttributeName to T2.attribute_name
            query = f"""
            SELECT 
                T2.attribute_value as segment_value,
                COUNT(DISTINCT T1.id) as user_count,
                COUNT(DISTINCT T3.role_id) / COUNT(DISTINCT T1.id) as avg_roles,
                COUNT(DISTINCT T4.access_profile_id) / COUNT(DISTINCT T1.id) as avg_aps,
                COUNT(DISTINCT T5.entitlement_id) / COUNT(DISTINCT T1.id) as avg_ents
            FROM Identities_Filtered T1
            JOIN Identity_Attributes_Filtered T2 ON T1.id = T2.identity_id
            LEFT JOIN IdentityRoleAssignments_Filtered T3 ON T1.id = T3.identity_id
            LEFT JOIN IdentityAccessProfileAssignments_Filtered T4 ON T1.id = T4.identity_id
            LEFT JOIN IdentityEffectiveEntitlements_Filtered T5 ON T1.id = T5.identity_id
            WHERE T2.attribute_name = %s
            GROUP BY T2.attribute_value
            HAVING user_count > 5
            ORDER BY avg_ents DESC;
            """
            cursor.execute(query, (segment,))
            for row in cursor.fetchall():
                stat_name = f"Avg Entitlements per User by {segment}"
                results.append((stat_name, "Population", row['segment_value'], None, row['user_count'], row['avg_ents']))
        except Error as e:
            print(f"    - ERROR calculating Segment Breakdown for {segment}: {e}")
    return results

def calculate_segmented_outlier_analysis(cursor):
    """Finds users who have significantly more entitlements than their peers."""
    print("  - Calculating: Segmented Outlier Analysis...")
    results = []
    segments = ['department', 'country']
    for segment in segments:
        print(f"    - Analyzing outliers by: {segment}...")
        try:
            # CORRECTED: Changed T2.AttributeValue to T2.attribute_value and T2.AttributeName to T2.attribute_name
            query = f"""
            WITH SegmentStats AS (
                SELECT
                    T2.attribute_value,
                    AVG(T3.ent_count) as avg_for_segment,
                    STDDEV(T3.ent_count) as stddev_for_segment
                FROM Identity_Attributes_Filtered T2
                JOIN (
                    SELECT identity_id, COUNT(entitlement_id) as ent_count
                    FROM IdentityEffectiveEntitlements_Filtered
                    GROUP BY identity_id
                ) T3 ON T2.identity_id = T3.identity_id
                WHERE T2.attribute_name = %s
                GROUP BY T2.attribute_value
            ),
            UserEntCounts AS (
                SELECT identity_id, identity_name, COUNT(entitlement_id) as user_ent_count
                FROM IdentityEffectiveEntitlements_Filtered
                GROUP BY identity_id, identity_name
            )
            SELECT
                T1.identity_name,
                T2.attribute_value as segment_value,
                T1.user_ent_count,
                SS.avg_for_segment
            FROM UserEntCounts T1
            JOIN Identity_Attributes_Filtered T2 ON T1.identity_id = T2.identity_id
            JOIN SegmentStats SS ON T2.attribute_value = SS.attribute_value
            WHERE T2.attribute_name = %s AND T1.user_ent_count > SS.avg_for_segment + (2 * SS.stddev_for_segment)
            ORDER BY T1.user_ent_count DESC;
            """
            cursor.execute(query, (segment, segment))
            for row in cursor.fetchall():
                stat_name = f"Entitlement Outlier by {segment}"
                results.append((stat_name, "Outliers", row['identity_name'], row['segment_value'], row['user_ent_count'], row['avg_for_segment']))
        except Error as e:
            print(f"    - ERROR calculating Outlier Analysis for {segment}: {e}")
    return results

def main():
    """Main orchestrator for all statistical analyses."""
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

   db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
    all_results = []

    # CORRECTED: The query for 'APs With Zero Assignments' now uses the correct join condition 'ap.id = a.access_profile_id'
    simple_statistical_queries = {
        "Total Roles": {"category": "Inventory", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_Roles"},
        "Total Access Profiles": {"category": "Inventory", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_AccessProfiles"},
        "Total Entitlements": {"category": "Inventory", "query": "SELECT COUNT(*) as stat FROM entitlements"},
        "Roles Missing Owners": {"category": "Quality", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_Roles WHERE owner_id IS NULL OR owner_id = ''"},
        "APs Missing Owners": {"category": "Quality", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_AccessProfiles WHERE owner_id IS NULL OR owner_id = ''"},
        "Dormant Roles (>1 Year)": {"category": "Quality", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_Roles WHERE last_add_date IS NULL OR last_add_date < DATE_SUB(NOW(), INTERVAL 1 YEAR)"},
        "Dormant APs (>1 Year)": {"category": "Quality", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_AccessProfiles WHERE last_add_date IS NULL OR last_add_date < DATE_SUB(NOW(), INTERVAL 1 YEAR)"},
        "Role Status Breakdown": {"category": "Inventory", "query": "SELECT enabled as value_1, COUNT(*) as numeric_value_1 FROM CurrentRoleModel_Roles GROUP BY enabled", "multi_row": True},
        "AP Status Breakdown": {"category": "Inventory", "query": "SELECT enabled as value_1, COUNT(*) as numeric_value_1 FROM CurrentRoleModel_AccessProfiles GROUP BY enabled", "multi_row": True},
        "APs By Source": {"category": "Inventory", "query": "SELECT source_name as value_1, COUNT(*) as numeric_value_1 FROM CurrentRoleModel_AccessProfiles GROUP BY source_name ORDER BY COUNT(*) DESC", "multi_row": True},
        "Top 10 Most Assigned Roles": {"category": "Population", "query": "SELECT role_name as value_1, COUNT(*) as numeric_value_1 FROM IdentityRoleAssignments GROUP BY role_name ORDER BY COUNT(*) DESC LIMIT 10", "multi_row": True},
        "Top 10 Most Assigned APs": {"category": "Population", "query": "SELECT access_profile_name as value_1, COUNT(*) as numeric_value_1 FROM IdentityAccessProfileAssignments GROUP BY access_profile_name ORDER BY COUNT(*) DESC LIMIT 10", "multi_row": True},
        "Top 10 Most Assigned Entitlements": {"category": "Population", "query": "SELECT entitlement_name as value_1, COUNT(*) as numeric_value_1 FROM IdentityEntitlementAssignments GROUP BY entitlement_name ORDER BY COUNT(*) DESC LIMIT 10", "multi_row": True},
        "Roles With Zero Assignments": {"category": "Quality", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_Roles r LEFT JOIN IdentityRoleAssignments a ON r.id = a.role_id WHERE a.role_id IS NULL"},
        "APs With Zero Assignments": {"category": "Quality", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_AccessProfiles ap LEFT JOIN IdentityAccessProfileAssignments a ON ap.id = a.access_profile_id WHERE a.access_profile_id IS NULL"},
        "\"God\" Roles (by Entitlement Count)": {"category": "Role Mining", "query": "SELECT role_name as value_1, COUNT(*) as numeric_value_1 FROM CurrentRoleModel_RoleEffectiveEntitlements GROUP BY role_name ORDER BY COUNT(*) DESC LIMIT 10", "multi_row": True},
        "\"God\" APs (by Entitlement Count)": {"category": "Role Mining", "query": "SELECT access_profile_name as value_1, COUNT(*) as numeric_value_1 FROM CurrentRoleModel_AccessProfileEntitlements GROUP BY access_profile_name ORDER BY COUNT(*) DESC LIMIT 10", "multi_row": True},
        "Redundant \"Wrapper\" APs (1 Entitlement)": {"category": "Role Mining", "query": "SELECT access_profile_name as value_1, COUNT(*) as numeric_value_1 FROM CurrentRoleModel_AccessProfileEntitlements GROUP BY access_profile_name HAVING COUNT(*) = 1", "multi_row": True},
        "Redundant Direct Assignments (Global)": {"category": "Role Mining", "query": "SELECT COUNT(*) as stat FROM IdentityEntitlementAssignments WHERE (identity_id, entitlement_id) IN (SELECT identity_id, entitlement_id FROM IdentityEffectiveEntitlements)"},
        "Top 20 Most Similar Role Pairs": {"category": "Role Mining", "query": "SELECT role1_name as value_1, role2_name as value_2, jaccard_score as numeric_value_2 FROM CurrentRoleModel_RoleSimilarity ORDER BY jaccard_score DESC LIMIT 20", "multi_row": True},
        "Highly Similar Role Pairs (>80%)": {"category": "Role Mining", "query": "SELECT COUNT(*) as stat FROM CurrentRoleModel_RoleSimilarity WHERE jaccard_score > 0.8"},
        "Cannibalization Candidates": {"category": "Role Mining", "query": "SELECT rs.role1_name as value_1, rs.role2_name as value_2, rs.jaccard_score as numeric_value_2 FROM CurrentRoleModel_RoleSimilarity rs JOIN CurrentRoleModel_Roles r1 ON rs.role1_id = r1.id JOIN CurrentRoleModel_Roles r2 ON rs.role2_id = r2.id WHERE rs.jaccard_score BETWEEN 0.7 AND 0.99 AND r1.owner_id != r2.owner_id LIMIT 20", "multi_row": True},
    }

    print("--- Starting Statistical Analysis ---")
    try:
        # --- Run Complex Analyses First ---
        all_results.extend(calculate_allocation_source_stats(cursor))
        all_results.extend(calculate_segment_access_breakdown(cursor))
        all_results.extend(calculate_segmented_outlier_analysis(cursor))

        # --- Run Simple, Config-driven Analyses ---
        for stat_name, config in simple_statistical_queries.items():
            print(f"  - Calculating: {stat_name}...")
            try:
                cursor.execute(config["query"])
                rows = cursor.fetchall()
                if not config.get("multi_row"):
                    all_results.append((stat_name, config["category"], None, None, rows[0]['stat'], None))
                else:
                    for row in rows:
                        all_results.append((
                            stat_name, config["category"],
                            row.get('value_1'), row.get('value_2'),
                            row.get('numeric_value_1'), row.get('numeric_value_2')
                        ))
            except Error as e:
                print(f"    - ERROR calculating {stat_name}: {e}")

        # --- Upload all results in a single batch ---
        print("\n--- Uploading Analysis Results to Database ---")
        cursor.execute("TRUNCATE TABLE Analysis_Results")
        upload_sql = "INSERT INTO Analysis_Results (stat_name, category, value_1, value_2, numeric_value_1, numeric_value_2) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor.executemany(upload_sql, all_results)
        db_connection.commit()
        print(f"-> Successfully uploaded {cursor.rowcount} analysis results.")

    except Error as e:
        print(f"Database Error during analysis: {e}")
        db_connection.rollback()
    finally:
        if cursor: cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()
