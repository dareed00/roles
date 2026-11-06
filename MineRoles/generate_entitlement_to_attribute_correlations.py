# generate_entitlement_to_attribute_correlations.py

from collections import defaultdict
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


BATCH_SIZE = 5000

# Tier Configuration: (min_pop, max_pop, min_jaccard_threshold, min_size_ratio)
POPULATION_TIER_CONFIG = [
    (1, 3, 0.65, 0.65),
    (4, 8, 0.74, 0.74),
    (9, 14, 0.82, 0.82),
    (15, 20, 0.85, 0.85),
    (21, 30, 0.87, 0.87),
    (31, 50, 0.89, 0.89),
    (51, 75, 0.91, 0.91),
    (76, 100, 0.93, 0.93),
    (101, 150, 0.94, 0.94),
    (151, 225, 0.95, 0.95),
    (226, 300, 0.96, 0.96),
    (301, float("inf"), 0.97, 0.97),
]


def get_tier_parameters(pop_size):
  """Returns (min_jaccard_threshold, min_size_ratio) for a given population size."""
  for min_p, max_p, threshold, ratio in POPULATION_TIER_CONFIG:
    if min_p <= pop_size <= max_p:
      return threshold, ratio
  return 0.75, 0.75


def main():
  try:
    with open("config.json") as f:
      config = json.load(f)
  except FileNotFoundError:
    print("FATAL: config.json not found.")
    return

db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
  try:
    # --- Step 1: Fetch Catalogs in Bulk ---
    print("\n--- Step 1: Fetching Entitlement & Attribute Catalogs ---")
    cursor.execute(
        "SELECT id, entitlement_id, entitlement_name, source_name,"
        " population_size FROM entitlements WHERE population_size >= 1"
    )
    ent_rows = cursor.fetchall()
    ent_map = {row["id"]: row for row in ent_rows}

    cursor.execute("""
            SELECT id, attribute_name, attribute_value, population_size 
            FROM Attribute_Populations 
            WHERE attribute_name NOT IN ('Combined Attribute', 'Union Attribute') AND population_size >= 1
        """)
    attr_rows = cursor.fetchall()
    attr_map = {
        (str(row["attribute_name"]), str(row["attribute_value"])): row
        for row in attr_rows
    }

    print(
        f"  -> Loaded {len(ent_map)} entitlements and {len(attr_map)} single"
        " attributes."
    )

    # --- Step 2: Fetch Access Mappings & Build Inverted Indexes ---
    print("\n--- Step 2: Bulk Fetching Access & Attribute Mappings ---")
    ent_assign_sql = """
        SELECT DISTINCT T1.identity_id, T2.id AS ent_db_id
        FROM (
            SELECT identity_id, entitlement_id FROM IdentityEffectiveEntitlements_Filtered
            UNION
            SELECT identity_id, entitlement_id FROM IdentityEntitlementAssignments_Filtered
        ) AS T1
        JOIN entitlements AS T2 ON T1.entitlement_id = T2.entitlement_id
        JOIN Identities_Filtered AS T3 ON T1.identity_id = T3.id
        WHERE T2.population_size >= 1
        """
    cursor.execute(ent_assign_sql)
    ent_assignment_rows = cursor.fetchall()

    attr_assign_sql = """
        SELECT T1.identity_id, T1.attribute_name, T1.attribute_value 
        FROM Identity_Attributes_Filtered AS T1
        JOIN Identities_Filtered AS T2 ON T1.identity_id = T2.id
        WHERE T1.attribute_name NOT IN ('Combined Attribute', 'Union Attribute')
        """
    cursor.execute(attr_assign_sql)
    attr_assignment_rows = cursor.fetchall()

    user_to_ents = defaultdict(list)
    ent_user_sets = defaultdict(set)
    for r in ent_assignment_rows:
      uid = str(r["identity_id"])
      eid = int(r["ent_db_id"])
      user_to_ents[uid].append(eid)
      ent_user_sets[eid].add(uid)

    user_to_attrs = defaultdict(list)
    attr_user_sets = defaultdict(set)
    for r in attr_assignment_rows:
      uid = str(r["identity_id"])
      key = (str(r["attribute_name"]), str(r["attribute_value"]))
      if key in attr_map:
        user_to_attrs[uid].append(key)
        attr_user_sets[key].add(uid)

    # --- Step 3: Fast Cross-Domain Intersections with Tiering ---
    print(
        "\n--- Step 3: Computing Cross-Domain Similarities via Inverted Index"
        " & Tiers ---"
    )
    cross_intersections = defaultdict(int)

    all_users = set(user_to_ents.keys()) & set(user_to_attrs.keys())
    for uid in all_users:
      user_ents = user_to_ents[uid]
      user_attrs = user_to_attrs[uid]
      for eid in user_ents:
        for akey in user_attrs:
          cross_intersections[(eid, akey)] += 1

    print(
        f"  -> Evaluated {len(cross_intersections)} co-occurring"
        " entitlement-attribute pairs."
    )

    correlations_to_load = []
    for (ent_id, attr_key), intersection_size in cross_intersections.items():
      ent = ent_map[ent_id]
      attr = attr_map[attr_key]
      attr_name, attr_val = attr_key

      pop_E = len(ent_user_sets[ent_id])
      pop_A = len(attr_user_sets[attr_key])

      min_pop = min(pop_E, pop_A)
      max_pop = max(pop_E, pop_A)

      threshold, required_size_ratio = get_tier_parameters(min_pop)

      if max_pop == 0 or (min_pop / max_pop) < required_size_ratio:
        continue

      union_size = pop_E + pop_A - intersection_size
      if union_size == 0:
        continue

      score = intersection_size / union_size

      if score >= threshold:
        correlations_to_load.append((
            int(ent["id"]),
            str(ent["entitlement_name"]),
            str(ent["source_name"]) if ent["source_name"] else "",
            str(attr_name),
            str(attr_val),
            float(round(score, 4)),
            int(pop_E),
            int(pop_A),
        ))

    print(
        f"\n--- Found {len(correlations_to_load)} Significant Cross-Domain"
        " Correlations ---"
    )

    # --- Step 4: Safe Reset & Batch Persistence ---
    print("\n--- Step 4: Loading Correlations into Database ---")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    cursor.execute("TRUNCATE TABLE Entitlement_Attribute_Differing_UIDs")
    cursor.execute("TRUNCATE TABLE Entitlement_to_Attribute_Correlations")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    db_connection.commit()

    if correlations_to_load:
      insert_sql = """
            INSERT INTO Entitlement_to_Attribute_Correlations 
            (entitlement_id, entitlement_name, entitlement_source, attribute_name, attribute_value, jaccard_score, entitlement_population, attribute_population) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
      for s in range(0, len(correlations_to_load), BATCH_SIZE):
        cursor.executemany(
            insert_sql, correlations_to_load[s : s + BATCH_SIZE]
        )
      db_connection.commit()
      print(
          f"  -> Successfully inserted {len(correlations_to_load)} records"
          " into Entitlement_to_Attribute_Correlations."
      )

  except Error as e:
    print(f"DATABASE ERROR: {e}")
    db_connection.rollback()
  finally:
    if cursor:
      cursor.close()
    if db_connection.and db_connection.is_connected():
      db_connection.close()
      print("Database connection closed.")


if __name__ == "__main__":
  main()
