# compute_correlation_from_populations.py

import json
import mysql.connector
from mysql.connector import Error
from collections import defaultdict
import re

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
    return len(set1.intersection(set2)) / len(set1.union(set2)) if set1 and set2 else 0

def get_dynamic_threshold(population_size):
    """Returns the Jaccard threshold based on the population size."""
    if population_size > 20: return 0.90
    if population_size > 10: return 0.80
    return 0.75

def get_population_ids(cursor, item_type, key):
    """A single, unified function to get any ID set on demand."""
    if item_type == 'entitlement':
        sql = "SELECT identity_id FROM IdentityEffectiveEntitlements_Filtered WHERE entitlement_id = %s"
        cursor.execute(sql, (key,))
    elif item_type == 'candidate':
        attr_name, attr_value_desc = key['attribute_name'], key['attribute_value']
        if attr_name == "Combined Attribute": # Intersection
            parts = [part.split(':', 1) for part in attr_value_desc.split(' | ')]
            (name1, val1), (name2, val2) = parts[0], parts[1]
            sql = "SELECT identity_id FROM Identity_Attributes_Filtered WHERE (attribute_name = %s AND attribute_value = %s) OR (attribute_name = %s AND attribute_value = %s) GROUP BY identity_id HAVING COUNT(DISTINCT attribute_name) = 2"
            cursor.execute(sql, (name1, val1, name2, val2))
        elif attr_name == "Union Attribute": # Union
            name_part, value_part = attr_value_desc.split(':', 1)
            values = [v.strip() for v in value_part.split(' U ')]
            placeholders = ', '.join(['%s'] * len(values))
            sql = f"SELECT DISTINCT identity_id FROM Identity_Attributes_Filtered WHERE attribute_name = %s AND attribute_value IN ({placeholders})"
            cursor.execute(sql, (name_part, *values))
        else: # Simple attribute
            sql = "SELECT identity_id FROM Identity_Attributes_Filtered WHERE attribute_name = %s AND attribute_value = %s"
            cursor.execute(sql, (attr_name, attr_value_desc))
    return {row['identity_id'] for row in cursor.fetchall()}

def main():
    """
    Main orchestrator that uses a highly efficient, entitlement-centric loop
    with 'group by size' maps for both entitlements and candidates.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        # === Step 1: Fetch All Pre-Calculated Population Counts and Group by Size ===
        print("\n--- Step 1: Fetching and pre-grouping all population COUNTS by size ---")
        
        ent_counts_query = "SELECT entitlement_id, entitlement_name, source_name, population_size FROM entitlements WHERE population_size > 1 AND is_correlated = FALSE"
        cursor.execute(ent_counts_query)
        entitlements_by_size = defaultdict(list)
        for row in cursor.fetchall():
            entitlements_by_size[row['population_size']].append(row)
        print(f"  -> Grouped {sum(len(v) for v in entitlements_by_size.values())} unsolved entitlements.")

        attr_counts_query = "SELECT attribute_name, attribute_value, population_size FROM Attribute_Populations"
        cursor.execute(attr_counts_query)
        candidates_by_size = defaultdict(list)
        for row in cursor.fetchall():
            candidates_by_size[row['population_size']].append(row)
        print(f"  -> Grouped {sum(len(v) for v in candidates_by_size.values())} candidates.")

        # === Step 2: Perform Highly Targeted Jaccard Analysis (Entitlements First) ===
        print("\n--- Step 2: Performing targeted Jaccard analysis (entitlement-centric)... ---")
        exact_matches = []
        near_matches = []
        
        for ent_pop_size, ent_list in entitlements_by_size.items():
            for ent_info in ent_list:
                min_pop = int(ent_pop_size * POPULATION_SIMILARITY_RATIO)
                max_pop = int(ent_pop_size / POPULATION_SIMILARITY_RATIO)
                ent_identities = get_population_ids(cursor, 'entitlement', ent_info['entitlement_id'])
                
                for size_to_check in range(min_pop, max_pop + 1):
                    for candidate_info in candidates_by_size.get(size_to_check, []):
                        candidate_identities = get_population_ids(cursor, 'candidate', candidate_info)
                        score = jaccard_similarity(ent_identities, candidate_identities)
                        threshold = get_dynamic_threshold(ent_pop_size)
                        if score >= threshold:
                            if score == 1.0:
                                exact_matches.append((ent_info['entitlement_name'], ent_info['source_name'], candidate_info['attribute_value'], candidate_info['attribute_name'], ent_pop_size))
                            else:
                                near_matches.append((ent_info['entitlement_name'], ent_info['source_name'], candidate_info['attribute_value'], candidate_info['attribute_name'], score, ent_pop_size, candidate_info['population_size']))

        print(f"\n--- TOTALS: Found {len(exact_matches)} exact and {len(near_matches)} near correlations. ---")

        # === Step 3: Bulk load results and update status ===
        print("\n--- Step 3: Loading results and updating entitlement status ---")
        print("  - Disabling foreign key checks..."); cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
        
        if exact_matches:
            print("  - Loading exact matches..."); 
            cursor.execute("TRUNCATE TABLE attr_value_exact_correlations")
            cursor.executemany("INSERT INTO attr_value_exact_correlations (attribute_A_value, access_source_A_name, attribute_B_value, access_source_B_name, population_size) VALUES (%s, %s, %s, %s, %s)", exact_matches)
            
            # ===================================================================
            # === THE FIX IS HERE: Using both name and source for the UPDATE ===
            # ===================================================================
            # Get a unique list of (entitlement_name, source_name) tuples for solved entitlements
            solved_ent_pairs = list(set([(em[0], em[1]) for em in exact_matches]))
            
            if solved_ent_pairs:
                # Prepare a query that can update multiple rows based on tuple pairs
                # This creates a series of (name = %s AND source_name = %s) clauses
                update_clauses = " OR ".join(["(entitlement_name = %s AND source_name = %s)"] * len(solved_ent_pairs))
                # Flatten the list of tuples into a single list of parameters
                params = [item for pair in solved_ent_pairs for item in pair]
                
                update_sql = f"UPDATE entitlements SET is_correlated = TRUE WHERE {update_clauses}"
                
                cursor.execute(update_sql, params)
                print(f"  -> Marked {cursor.rowcount} entitlements as 'correlated' using name and source.")

        if near_matches:
            print("  - Loading near matches..."); 
            cursor.execute("TRUNCATE TABLE attr_value_near_match_differing_uids"); cursor.execute("TRUNCATE TABLE attr_value_near_correlations")
            cursor.executemany("INSERT INTO attr_value_near_correlations (attribute_A_value, access_source_A_name, attribute_B_value, access_source_B_name, jaccard_score, population_A_size, population_B_size) VALUES (%s, %s, %s, %s, %s, %s, %s)", near_matches)
            print(f"  -> Loaded {cursor.rowcount} records.")
            
        db_connection.commit()

    except Error as e:
        print(f"    - DATABASE ERROR during analysis: {e}"); db_connection.rollback()
    finally:
        if cursor: print("  - Re-enabling foreign key checks..."); cursor.execute("SET FOREIGN_KEY_CHECKS=1;"); cursor.close()
        if db_connection.and db_connection.is_connected(): db_connection.close(); print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
