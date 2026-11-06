# compute_access_profile_similarity.py

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


def jaccard_similarity(set1, set2):
    """Calculates the Jaccard similarity between two sets."""
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union != 0 else 0

def calculate_and_load_similarity(db_connection.:
    """
    Calculates the Jaccard similarity between all access profiles based on their
    entitlement composition and loads the results into the database.
    """
    print("\n--- Starting Access Profile Similarity Analysis ---")
    
    # A configurable threshold to only store meaningful similarities
    SIMILARITY_THRESHOLD = 0.50 

    cursor = db_connection.cursor(dictionary=True)
    
    try:
        # 1. Fetch all AP-to-Entitlement mappings
        print("  - Step 1: Fetching all access profile to entitlement mappings...")
        query = "SELECT access_profile_id, access_profile_name, entitlement_id FROM CurrentRoleModel_AccessProfileEntitlements"
        cursor.execute(query)
        mappings = cursor.fetchall()
        print(f"  -> Found {len(mappings)} total entitlement assignments across all APs.")

        # 2. Build the data structure: a dictionary of {ap_id: {set_of_ent_ids}}
        print("  - Step 2: Building entitlement sets for each access profile...")
        ap_entitlements = defaultdict(set)
        ap_names = {} # To store names for the final output
        for row in mappings:
            ap_id = row['access_profile_id']
            ap_entitlements[ap_id].add(row['entitlement_id'])
            if ap_id not in ap_names:
                ap_names[ap_id] = row['access_profile_name']
        print(f"  -> Created sets for {len(ap_entitlements)} unique access profiles.")

        # 3. Iterate through all unique pairs of access profiles and calculate similarity
        print("  - Step 3: Calculating Jaccard similarity for all unique pairs...")
        similarity_results = []
        # Using itertools.combinations is more efficient than a nested loop
        ap_ids = list(ap_entitlements.keys())
        for ap1_id, ap2_id in combinations(ap_ids, 2):
            set1 = ap_entitlements[ap1_id]
            set2 = ap_entitlements[ap2_id]
            
            score = jaccard_similarity(set1, set2)
            
            # 4. If the score is above our threshold, store it
            if score >= SIMILARITY_THRESHOLD:
                similarity_results.append((
                    ap1_id,
                    ap_names[ap1_id],
                    ap2_id,
                    ap_names[ap2_id],
                    score
                ))
        print(f"  -> Found {len(similarity_results)} pairs with similarity >= {SIMILARITY_THRESHOLD}")

        # 5. Bulk load the results into the database
        if similarity_results:
            print("  - Step 4: Loading similarity results into the database...")
            cursor.execute("TRUNCATE TABLE CurrentRoleModel_AccessProfileSimilarity")
            
            sql = """
            INSERT INTO CurrentRoleModel_AccessProfileSimilarity
            (access_profile1_id, access_profile1_name, access_profile2_id, access_profile2_name, jaccard_score)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.executemany(sql, similarity_results)
            db_connection.commit()
            print(f"-> Successfully loaded {cursor.rowcount} similarity records.")
        else:
            print("  - Step 4: No significant similarities found to load.")

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
        print("FATAL: config.json not found. Please ensure it exists.")
        return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)

    try:
        calculate_and_load_similarity(db_connection.
        print("\nProcess completed successfully.")
    finally:
        if db_connection.and db_connection.is_connected():
            db_connection.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()
