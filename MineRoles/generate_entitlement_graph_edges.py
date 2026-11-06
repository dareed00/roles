# generate_entitlement_graph_edges.py

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
    # --- Step 1: Fetch Entitlements Catalog ---
    print("\n--- Step 1: Fetching Entitlements Catalog ---")
    cursor.execute(
        "SELECT id, entitlement_id, entitlement_name, source_name,"
        " population_size FROM entitlements WHERE population_size >= 1"
    )
    ent_rows = cursor.fetchall()
    if not ent_rows:
      print("No entitlements found.")
      return

    ent_map = {row["id"]: row for row in ent_rows}
    print(f"  -> Loaded {len(ent_rows)} eligible entitlements.")

    # --- Step 2: Bulk Fetch Access Mappings ---
    print("\n--- Step 2: Bulk Fetching Access Mappings ---")
    assignment_sql = """
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
    cursor.execute(assignment_sql)
    assignment_rows = cursor.fetchall()
    print(f"  -> Fetched {len(assignment_rows)} total access mappings.")

    ent_user_sets = defaultdict(set)
    user_to_ents = defaultdict(list)

    for row in assignment_rows:
      uid = str(row["identity_id"])
      eid = int(row["ent_db_id"])
      ent_user_sets[eid].add(uid)
      user_to_ents[uid].append(eid)

    # --- Step 3: Fast Inverted-Index Pairwise Jaccard ---
    print(
        "\n--- Step 3: Computing Pairwise Similarities via Inverted Index &"
        " Tiers ---"
    )
    pair_intersections = defaultdict(int)

    for uid, ents in user_to_ents.items():
      n = len(ents)
      if n < 2:
        continue
      sorted_ents = sorted(ents)
      for i in range(n):
        ent_a = sorted_ents[i]
        for j in range(i + 1, n):
          ent_b = sorted_ents[j]
          pair_intersections[(ent_a, ent_b)] += 1

    print(
        f"  -> Evaluated {len(pair_intersections)} co-occurring entitlement"
        " pairs."
    )

    exact_matches = []
    near_matches = []

    for (ent_A_id, ent_B_id), intersection_size in pair_intersections.items():
      ent_A = ent_map[ent_A_id]
      ent_B = ent_map[ent_B_id]

      pop_A = len(ent_user_sets[ent_A_id])
      pop_B = len(ent_user_sets[ent_B_id])

      min_pop = min(pop_A, pop_B)
      max_pop = max(pop_A, pop_B)

      threshold, required_size_ratio = get_tier_parameters(min_pop)

      if max_pop == 0 or (min_pop / max_pop) < required_size_ratio:
        continue

      union_size = pop_A + pop_B - intersection_size
      if union_size == 0:
        continue

      score = intersection_size / union_size

      if score >= threshold:
        if score == 1.0:
          exact_matches.append((
              int(ent_A["id"]),
              str(ent_A["entitlement_name"]),
              str(ent_A["source_name"]) if ent_A["source_name"] else "",
              int(ent_B["id"]),
              str(ent_B["entitlement_name"]),
              str(ent_B["source_name"]) if ent_B["source_name"] else "",
              int(pop_A),
          ))
        else:
          near_matches.append((
              int(ent_A["id"]),
              str(ent_A["entitlement_name"]),
              str(ent_A["source_name"]) if ent_A["source_name"] else "",
              int(ent_B["id"]),
              str(ent_B["entitlement_name"]),
              str(ent_B["source_name"]) if ent_B["source_name"] else "",
              float(round(score, 4)),
              int(pop_A),
              int(pop_B),
          ))

    print(
        f"\n--- Found {len(exact_matches)} Exact and {len(near_matches)} Near"
        " Correlations ---"
    )

    # --- Step 4: Batch Persistence ---
    print("\n--- Step 4: Loading Correlations into Database ---")
    cursor.execute("TRUNCATE TABLE Entitlement_Exact_Correlations")
    cursor.execute("TRUNCATE TABLE Entitlement_Near_Correlations")
    db_connection.commit()

    if exact_matches:
      exact_sql = """
            INSERT INTO Entitlement_Exact_Correlations 
            (entitlement_A_id, entitlement_A_name, entitlement_A_source, entitlement_B_id, entitlement_B_name, entitlement_B_source, population_size) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
      for s in range(0, len(exact_matches), BATCH_SIZE):
        cursor.executemany(exact_sql, exact_matches[s : s + BATCH_SIZE])
      print(f"  -> Inserted {len(exact_matches)} exact records.")

    if near_matches:
      near_sql = """
            INSERT INTO Entitlement_Near_Correlations 
            (entitlement_A_id, entitlement_A_name, entitlement_A_source, entitlement_B_id, entitlement_B_name, entitlement_B_source, jaccard_score, population_A_size, population_B_size) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
      for s in range(0, len(near_matches), BATCH_SIZE):
        cursor.executemany(near_sql, near_matches[s : s + BATCH_SIZE])
      print(f"  -> Inserted {len(near_matches)} near records.")

    db_connection.commit()
    print("Entitlement graph edge generation complete.")

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
