# compute_entitlement_similarity.py

import json
import mysql.connector
from mysql.connector import Error
from collections import defaultdict

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


# --- Main Configuration ---
POPULATION_SIMILARITY_RATIO = 0.75

def jaccard_similarity(set1, set2):
    """Calculates the Jaccard similarity between two sets."""
    union_size = len(set1.union(set2))
    if union_size == 0: return 0.0
    return len(set1.intersection(set2)) / union_size

def get_dynamic_threshold(population_size):
    """Returns the Jaccard threshold based on the population size."""
    if population_size > 20: return 0.90
    if population_size > 10: return 0.80
    return 0.75

def get_population_ids(cursor, entitlement_db_id):
    """Fetches the set of identity IDs for a single entitlement, on demand."""
    sql = """
    SELECT T2.id 
    FROM IdentityEffectiveEntitlements_Filtered AS T1
    JOIN Identities_Filtered AS T2 ON T1.identity_id = T2.id
    WHERE T1.entitlement_id = (SELECT entitlement_id FROM entitlements WHERE id = %s)
    
    UNION

    SELECT T2.id
    FROM IdentityEntitlementAssignments_Filtered AS T1
    JOIN Identities_Filtered AS T2 ON T1.identity_id = T2.id
    WHERE T1.entitlement_id = (SELECT entitlement_id FROM entitlements WHERE id = %s)
    """
    cursor.execute(sql, (entitlement_db_id, entitlement_db_id))
    return {row['id'] for row in cursor.fetchall()}

def main():
    """
    Compares entitlements by working from largest to smallest populations,
    with detailed tracing for each significant Jaccard comparison.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

   db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        # === Step 1: Fetch All Entitlements and Group by Size ===
        print("\n--- Step 1: Fetching and pre-grouping entitlements by size ---")
        ent_counts_query = "SELECT id, entitlement_id, entitlement_name, source_name, population_size FROM entitlements WHERE population_size > 1"
        cursor.execute(ent_counts_query)
        
        all_entitlements = [row for row in cursor.fetchall()]
        entitlements_by_size = defaultdict(list)
        for ent in all_entitlements:
            entitlements_by_size[ent['population_size']].append(ent)
            
        print(f"  -> Grouped {len(all_entitlements)} entitlements for analysis.")

        # === Step 2: Initialize Caches and Prepare Database ===
        print("\n--- Step 2: Preparing for analysis... ---")
        identity_cache = {}
        total_exact_matches = 0
        total_near_matches = 0

        print("  - Clearing previous correlation results...")
        cursor.execute("TRUNCATE TABLE Entitlement_Exact_Correlations")
        cursor.execute("TRUNCATE TABLE Entitlement_Near_Correlations")
        db_connection.commit()

        sorted_pop_sizes = sorted(entitlements_by_size.keys(), reverse=True)

        # === Step 3: Main Analysis Loop (Descending Population Size) ===
        print("\n--- Step 3: Starting main analysis loop... ---")
        
        for ent_A_pop_size in sorted_pop_sizes:
            batch_exact_matches = []
            batch_near_matches = []
            
            ent_A_list = entitlements_by_size[ent_A_pop_size]
            
            print(f"\n- Evaluating population size: {ent_A_pop_size} ({len(ent_A_list)} entitlement(s))...")

            max_pop_for_this_group = int(ent_A_pop_size / POPULATION_SIMILARITY_RATIO)

            for ent_A_info in ent_A_list:
                min_pop = int(ent_A_pop_size * POPULATION_SIMILARITY_RATIO)
                max_pop = max_pop_for_this_group

                if ent_A_info['id'] not in identity_cache:
                    identity_cache[ent_A_info['id']] = get_population_ids(cursor, ent_A_info['id'])
                ent_A_identities = identity_cache[ent_A_info['id']]
                
                for size_to_check in range(min_pop, max_pop + 1):
                    for ent_B_info in entitlements_by_size.get(size_to_check, []):
                        if ent_A_info['id'] >= ent_B_info['id']: continue

                        if ent_B_info['id'] not in identity_cache:
                            identity_cache[ent_B_info['id']] = get_population_ids(cursor, ent_B_info['id'])
                        ent_B_identities = identity_cache[ent_B_info['id']]
                        
                        score = jaccard_similarity(ent_A_identities, ent_B_identities)
                        threshold = get_dynamic_threshold(min(ent_A_pop_size, ent_B_info['population_size']))

                        if score >= threshold:
                            # ===================================================================
                            # === NEW TRACING: Print the Jaccard score for each significant match ===
                            # ===================================================================
                            print(f"    -> Match Found: '{ent_A_info['entitlement_name']}' vs '{ent_B_info['entitlement_name']}' | Jaccard: {score:.4f}")

                            if score == 1.0:
                                batch_exact_matches.append((
                                    ent_A_info['id'], ent_A_info['entitlement_name'], ent_A_info['source_name'],
                                    ent_B_info['id'], ent_B_info['entitlement_name'], ent_B_info['source_name'],
                                    ent_A_pop_size
                                ))
                            else:
                                batch_near_matches.append((
                                    ent_A_info['id'], ent_A_info['entitlement_name'], ent_A_info['source_name'],
                                    ent_B_info['id'], ent_B_info['entitlement_name'], ent_B_info['source_name'],
                                    score, ent_A_pop_size, ent_B_info['population_size']
                                ))
            
            num_exact_in_batch = len(batch_exact_matches)
            num_near_in_batch = len(batch_near_matches)

            if num_exact_in_batch > 0:
                exact_sql = "INSERT INTO Entitlement_Exact_Correlations (entitlement_A_id, entitlement_A_name, entitlement_A_source, entitlement_B_id, entitlement_B_name, entitlement_B_source, population_size) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                cursor.executemany(exact_sql, batch_exact_matches)
                total_exact_matches += cursor.rowcount
            
            if num_near_in_batch > 0:
                near_sql = "INSERT INTO Entitlement_Near_Correlations (entitlement_A_id, entitlement_A_name, entitlement_A_source, entitlement_B_id, entitlement_B_name, entitlement_B_source, jaccard_score, population_A_size, population_B_size) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                cursor.executemany(near_sql, batch_near_matches)
                total_near_matches += cursor.rowcount
            
            if num_exact_in_batch > 0 or num_near_in_batch > 0:
                db_connection.commit()

            print(f"  - Completed. Found {num_exact_in_batch} exact and {num_near_in_batch} near matches for this population size.")

            ids_to_purge = [ent_id for ent_id, ids in identity_cache.items() if len(ids) > max_pop_for_this_group]
            if ids_to_purge:
                print(f"  - Purging {len(ids_to_purge)} items from cache to save memory.")
                for ent_id in ids_to_purge:
                    del identity_cache[ent_id]
        
        print("\n-------------------------------------------------")
        print("Analysis Complete.")
        print(f"Total Exact Matches Found: {total_exact_matches}")
        print(f"Total Near Matches Found: {total_near_matches}")
        print("-------------------------------------------------")

    except Error as e:
        print(f"    - DATABASE ERROR during analysis: {e}"); db_connection.rollback()
    finally:
        if cursor: cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
