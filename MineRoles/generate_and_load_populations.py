# generate_and_load_populations.py

import json
import mysql.connector
from mysql.connector import Error
from collections import defaultdict
# Make sure to import 'product' from itertools
from itertools import combinations, product
import csv
import os

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
# Your configurations are unchanged
EXCLUDED_ATTRIBUTES = [
    'displayName', 'email', 'firstname', 'lastname', 'name', 'uid', 'endDate',"email","googleemail","identificationNumber","visibleSegments","phone","startDate","nePersonId","nePopulationsStartDate","nePopulationsStartEndDates",
    'inactive','status', 'employeeNumber', 'workPhone','accountCount',"cloudStatus","internalCloudStatus","neLocations","cloudAuthoritativeState","cloudAuthoritativeSource","identityState"
]
MAX_INTERSECTION_SIZE = 3
BATCH_SIZE = 50000 
OUTPUT_FILENAME = 'attribute_populations.tsv'
DELETE_FILE_AFTER_LOAD = True
EXCLUDED_HIERARCHICAL_PAIRS = {
    frozenset({'country', 'state'}), 
    frozenset({'state', 'city'}), 
    frozenset({'country', 'city'}),
    frozenset({'city', 'location'}), 
    frozenset({'state', 'location'}), 
    frozenset({'country', 'location'}),
    frozenset({'department', 'jobTitle'}), 
    frozenset({'cloudLifecycleState', 'state'}),
    frozenset({'cloudLifecycleState', 'city'}), 
    frozenset({'cloudLifecycleState', 'department'}),
    frozenset({'cloudLifecycleState', 'jobTitle'}), 
    frozenset({'cloudLifecycleState', 'neOrganizations'}),
    frozenset({'cloudLifecycleState', 'neOrganizationsSubOrganizations'}),
    frozenset({'cloudLifecycleState', 'nePopulationsLocations'}),
    frozenset({'cloudLifecycleState', 'nePopulations'}),
    frozenset({'cloudLifecycleState', 'neOrganizationsSubPopulations'}),
    frozenset({'cloudLifecycleState', 'nePopulationsOganizationsSubOrganizations'}),
    frozenset({'neOrganizations', 'neOrganizationsSubOrganizations'}),
    frozenset({'nePopulations', 'nePopulationsLocations'}),
    frozenset({'nePopulations', 'nePopulationsLocations'}),
    frozenset({'neOrganizations', 'nePopulationsLocations'}),
    frozenset({'nePopulations', 'neOrganizationsSubPopulations'}),
    frozenset({'nePopulationsOganizations', 'nePopulationsOganizationsSubOrganizations'})  
}

def get_db_connection(config, allow_local_infile=False):
    # ... (unchanged)
    db_config = config.copy()
    db_config['allow_local_infile'] = allow_local_infile
    try: conn = mysql.connector.connect(**db_config); return conn
    except Error as e: print(f"FATAL: Error connecting to MySQL: {e}"); return None

def main():
    """
    Calculates populations for single attributes and INTERSECTIONS of up to 3
    attributes, then saves to a file and performs a bulk upload.
    """
    try:
        with open('config.json') as f: config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    read_conn = get_db_connection(config.get("Database"))
    if not read_conn: return
    
    cursor = read_conn.cursor(dictionary=True)
    try:
        # Step 1: Fetch all Individual Attribute Populations into Memory
        print("\n--- Step 1: Fetching all individual attribute populations into memory ---")
        placeholders = ', '.join(['%s'] * len(EXCLUDED_ATTRIBUTES))
        attr_query = f"SELECT identity_id, attribute_name, attribute_value FROM Identity_Attributes_Filtered WHERE attribute_name NOT IN ({placeholders})"
        cursor.execute(attr_query, tuple(EXCLUDED_ATTRIBUTES))
        
        attribute_sets = defaultdict(lambda: defaultdict(set))
        for row in cursor.fetchall():
            attribute_sets[row['attribute_name']][row['attribute_value']].add(row['identity_id'])
        print(f"  -> Fetched identity sets for {len(attribute_sets)} unique attribute names.")

        # Step 2: Generate All Candidate Populations
        print("\n--- Step 2: Generating all candidate population definitions and counts... ---")
        all_populations_to_write = []

        # Stage A: Single-Attribute Populations
        print("  - Generating single-attribute populations...")
        for attr_name, value_dict in attribute_sets.items():
            for attr_value, id_set in value_dict.items():
                all_populations_to_write.append([attr_name, attr_value, len(id_set)])
        
        attribute_names = list(attribute_sets.keys())
        
        # Loop for generating intersections of increasing size
        for combo_size in range(2, MAX_INTERSECTION_SIZE + 1):
            print(f"  - Generating intersection populations of size {combo_size}...")
            
            for name_combo in combinations(attribute_names, combo_size):
                if any(frozenset(pair) in EXCLUDED_HIERARCHICAL_PAIRS for pair in combinations(name_combo, 2)):
                    continue

                # ===================================================================
                # === THE FIX IS HERE: Using itertools.product for clean combinations ===
                # ===================================================================
                # Create a list of the value lists for the current name combination
                value_lists = [attribute_sets[name].keys() for name in name_combo]
                
                # 'product' correctly creates all combinations as tuples
                for v_combo in product(*value_lists):
                    # v_combo is now a tuple, e.g., ('US', 'Sales') - which is valid
                    
                    id_sets_to_intersect = [attribute_sets[name_combo[i]][v_combo[i]] for i in range(combo_size)]
                    intersection_ids = set.intersection(*id_sets_to_intersect)

                    if intersection_ids:
                        combo_name = " | ".join([f"{name_combo[i]}:{v_combo[i]}" for i in range(combo_size)])
                        all_populations_to_write.append(["Combined Attribute", combo_name, len(intersection_ids)])

        print(f"\n  -> Generated a total of {len(all_populations_to_write)} populations to write.")

        # Step 3: Write all data to a TSV file
        print(f"\n--- Step 3: Writing all population data to '{OUTPUT_FILENAME}' ---")
        file_path = os.path.abspath(OUTPUT_FILENAME)
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter='\t', lineterminator='\n')
            writer.writerows(all_populations_to_write)
        print(f"  -> Successfully wrote {len(all_populations_to_write)} records.")
    
    except Error as e:
        print(f"    - DATABASE ERROR during data fetch: {e}"); return
    finally:
        if cursor: cursor.close()
        if read_conn and read_conn.is_connected(): read_conn.close()

    # --- Part 2: Use LOAD DATA INFILE to upload the generated file ---
    print("\n--- Step 4: Starting high-performance bulk upload ---")
    load_conn = get_db_connection(config.get("Database"), allow_local_infile=True)
    if not load_conn: return
    
    load_cursor = load_conn.cursor()
    try:
        print("  - Clearing old data from Attribute_Populations...")
        load_cursor.execute("TRUNCATE TABLE Attribute_Populations")
        load_sql = f"LOAD DATA LOCAL INFILE '{file_path.replace(os.sep, '/')}' INTO TABLE Attribute_Populations FIELDS TERMINATED BY '\t' LINES TERMINATED BY '\n' (attribute_name, attribute_value, population_size)"
        print(f"  - Executing LOAD DATA INFILE command for '{file_path}'...")
        load_cursor.execute(load_sql)
        load_conn.commit()
        print(f"  -> Successfully loaded {load_cursor.rowcount} records.")

    except Error as e:
        print(f"    - DATABASE ERROR during bulk load: {e}"); load_conn.rollback()
    finally:
        if DELETE_FILE_AFTER_LOAD:
            try: os.remove(file_path); print(f"  - Successfully deleted temporary file.")
            except OSError as e: print(f"  - ERROR deleting temporary file: {e}")
        if load_cursor: load_cursor.close()
        if load_conn and load_conn.is_connected():
            load_conn.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
