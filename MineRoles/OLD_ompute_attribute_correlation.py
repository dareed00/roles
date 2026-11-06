# compute_attribute_correlation.py

import json
import mysql.connector
from mysql.connector import Error
from collections import defaultdict
from itertools import combinations

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
EXCLUDED_ATTRIBUTES = [
    'displayName', 'email', 'firstname', 'lastname', 'name', 'uid', 'endDate',"email","googleemail","identificationNumber","visibleSegments","phone","startDate",
    'inactive', 'isManager', 'status', 'employeeNumber', 'accountCount',"cloudStatus","internalCloudStatus","cloudAuthoritativeState","cloudAuthoritativeSource","identityState"
]

def jaccard_similarity(set1, set2):
    """Calculates the Jaccard similarity between two sets."""
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union != 0 else 0

def get_dynamic_threshold(population_size):
    """Returns the Jaccard threshold based on the population size."""
    if population_size > 20: return 0.90
    if population_size > 10: return 0.80
    return 0.75

def main():
    """
    Main orchestrator for running single, multi-attribute intersection, and
    multi-attribute union correlation analysis.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    try:
        # === Step 1: Fetch all base populations (Done once for efficiency) ===
        print("\n--- Step 1: Fetching all base populations from filtered data ---")
        
        ent_query = "SELECT T1.identity_id, T1.entitlement_name, T2.source_name FROM IdentityEffectiveEntitlements_Filtered AS T1 JOIN entitlements AS T2 ON T1.entitlement_id = T2.entitlement_id;"
        cursor.execute(ent_query)
        ent_assignments = cursor.fetchall()
        entitlement_populations = defaultdict(set)
        for row in ent_assignments:
            entitlement_populations[(row['entitlement_name'], row['source_name'])].add(row['identity_id'])
        print(f"  -> Built population sets for {len(entitlement_populations)} unique entitlements.")

        placeholders = ', '.join(['%s'] * len(EXCLUDED_ATTRIBUTES))
        attr_query = f"SELECT identity_id, attribute_name, attribute_value FROM Identity_Attributes_Filtered WHERE attribute_name NOT IN ({placeholders})"
        cursor.execute(attr_query, tuple(EXCLUDED_ATTRIBUTES))
        all_attr_assignments = cursor.fetchall()
        attribute_populations = defaultdict(lambda: defaultdict(set))
        for row in all_attr_assignments:
            attribute_populations[row['attribute_name']][row['attribute_value']].add(row['identity_id'])
        print(f"  -> Built population sets for {len(attribute_populations)} unique attribute names.")

        exact_matches = []
        near_matches = []

        # === Step 2: Perform Single-Attribute Correlation Analysis ===
        print("\n--- Step 2: Comparing Entitlements vs. Single Attribute values... ---")
        # (This section remains the same, providing the baseline correlations)
        for (ent_name, ent_source), ent_identities in entitlement_populations.items():
            ent_pop_size = len(ent_identities)
            if ent_pop_size == 0: continue
            threshold = get_dynamic_threshold(ent_pop_size)
            for attr_name, value_populations in attribute_populations.items():
                for attr_value, attr_identities in value_populations.items():
                    attr_pop_size = len(attr_identities)
                    if attr_pop_size == 0: continue
                    is_small_pop_exception = (ent_pop_size == 2 and attr_pop_size in [1, 2]) or (attr_pop_size == 2 and ent_pop_size in [1, 2])
                    if not is_small_pop_exception and min(ent_pop_size, attr_pop_size) / max(ent_pop_size, attr_pop_size) < 0.35: continue
                    score = jaccard_similarity(ent_identities, attr_identities)
                    if score == 1.0:
                        exact_matches.append((ent_name, ent_source, attr_value, attr_name, ent_pop_size))
                    elif score >= threshold:
                        near_matches.append((ent_name, ent_source, attr_value, attr_name, score, ent_pop_size, attr_pop_size))
        
        print(f"  -> Single-Attribute: Found {len(exact_matches)} exact and {len(near_matches)} near matches (so far).")

        # === Step 3: Perform Multi-Attribute (Intersection) Analysis ===
        print("\n--- Step 3: Comparing Entitlements vs. Combined (Intersection) Attribute values... ---")
        # (This section remains the same)
        attribute_names = list(attribute_populations.keys())
        for name1, name2 in combinations(attribute_names, 2):
            for value1, ids1 in attribute_populations[name1].items():
                for value2, ids2 in attribute_populations[name2].items():
                    combo_identities = ids1.intersection(ids2)
                    if not combo_identities: continue
                    combo_desc_name = f"{name1}:{value1} | {name2}:{value2}"
                    for (ent_name, ent_source), ent_identities in entitlement_populations.items():
                        # ... (comparison logic as before)
                        ent_pop_size = len(ent_identities)
                        combo_pop_size = len(combo_identities)
                        if ent_pop_size == 0 or combo_pop_size == 0: continue
                        is_small = (ent_pop_size == 2 and combo_pop_size in [1, 2]) or (combo_pop_size == 2 and ent_pop_size in [1, 2])
                        if not is_small and min(ent_pop_size, combo_pop_size) / max(ent_pop_size, combo_pop_size) < 0.35: continue
                        score = jaccard_similarity(ent_identities, combo_identities)
                        threshold = get_dynamic_threshold(ent_pop_size)
                        if score == 1.0:
                            exact_matches.append((ent_name, ent_source, combo_desc_name, "Combined Attribute", ent_pop_size))
                        elif score >= threshold:
                            near_matches.append((ent_name, ent_source, combo_desc_name, "Combined Attribute", score, ent_pop_size, combo_pop_size))
        
        print(f"  -> Multi-Attribute (Intersection): Found {len(exact_matches)} exact and {len(near_matches)} near matches (cumulative).")

        # ===================================================================
        # === Step 4: NEW - Perform Union-Attribute Correlation Analysis ===
        # ===================================================================
        print("\n--- Step 4: Comparing Entitlements vs. Combined (Union) Attribute values... ---")
        for attr_name in attribute_populations.keys():
            # Get all unique values for the current attribute name
            values_for_name = list(attribute_populations[attr_name].keys())
            # Create all unique pairs of these values
            for value1, value2 in combinations(values_for_name, 2):
                ids1 = attribute_populations[attr_name][value1]
                ids2 = attribute_populations[attr_name][value2]
                
                # Apply the small population exception before forming the union
                is_small_pop_exception = (len(ids1) < 3 and len(ids2) < 3)

                # Form the union of the two populations
                union_identities = ids1.union(ids2)
                union_pop_size = len(union_identities)
                if not union_identities: continue

                # Create the descriptive name for this union
                union_desc_name = f"{attr_name}:{value1} U {attr_name}:{value2}"
                union_desc_source = "Union Attribute"
                
                # Now, compare this new union population against all entitlements
                for (ent_name, ent_source), ent_identities in entitlement_populations.items():
                    ent_pop_size = len(ent_identities)
                    if ent_pop_size == 0: continue
                    
                    # Apply your new efficiency filters
                    if not is_small_pop_exception:
                        # If not the exception, check if populations are within 90% size of each other
                        if min(ent_pop_size, union_pop_size) / max(ent_pop_size, union_pop_size) < 0.90:
                            continue # Skip if not within 90%

                    score = jaccard_similarity(ent_identities, union_identities)
                    threshold = get_dynamic_threshold(ent_pop_size)

                    if score == 1.0:
                        exact_matches.append((ent_name, ent_source, union_desc_name, union_desc_source, ent_pop_size))
                    elif score >= threshold:
                        near_matches.append((ent_name, ent_source, union_desc_name, union_desc_source, score, ent_pop_size, union_pop_size))

        print(f"  -> Union-Attribute: Found {len(exact_matches)} exact and {len(near_matches)} near matches (cumulative).")

        # === Step 5: Bulk load all combined results ===
        print("\n--- Step 5: Loading all results into correlation tables ---")
        # (This section is unchanged and will load results from all 3 analysis stages)
        print("  - Disabling foreign key checks for bulk load...")
        cursor.execute("SET FOREIGN_KEY_CHECKS=0;")
        if exact_matches:
            print("  - Loading exact matches..."); cursor.execute("TRUNCATE TABLE attr_value_exact_correlations")
            exact_sql = "INSERT INTO attr_value_exact_correlations (attribute_A_value, access_source_A_name, attribute_B_value, access_source_B_name, population_size) VALUES (%s, %s, %s, %s, %s)"
            cursor.executemany(exact_sql, exact_matches)
            print(f"  -> Loaded {cursor.rowcount} records.")
        if near_matches:
            print("  - Loading near matches..."); cursor.execute("TRUNCATE TABLE attr_value_near_match_differing_uids"); cursor.execute("TRUNCATE TABLE attr_value_near_correlations")
            near_sql = "INSERT INTO attr_value_near_correlations (attribute_A_value, access_source_A_name, attribute_B_value, access_source_B_name, jaccard_score, population_A_size, population_B_size) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            cursor.executemany(near_sql, near_matches)
            print(f"  -> Loaded {cursor.rowcount} records.")
        db_connection.commit()

    except Error as e:
        print(f"    - DATABASE ERROR during analysis: {e}"); db_connection.rollback()
    finally:
        if cursor:
            print("  - Re-enabling foreign key checks..."); cursor.execute("SET FOREIGN_KEY_CHECKS=1;"); cursor.close()
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("\nDatabase connection closed.")

if __name__ == "__main__":
    main()
