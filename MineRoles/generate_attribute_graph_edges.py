# generate_attribute_graph_edges.py

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
    # --- Step 1: Fetch Eligible Attributes ---
    print("\n--- Step 1: Fetching Attribute Populations ---")
    cursor.execute("""
            SELECT id, attribute_name, attribute_value, population_size 
            FROM Attribute_Populations 
            WHERE attribute_name NOT IN ('Combined Attribute', 'Union Attribute') AND population_size >= 1
        """)
    attr_rows = cursor.fetchall()
    if not attr_rows:
      print("No eligible attributes found.")
      return

    attr_map = {
        (str(row["attribute_name"]), str(row["attribute_value"])): row
        for row in attr_rows
    }
    print(f"  -> Loaded {len(attr_rows)} eligible single attributes.")

    # --- Step 2: Bulk Fetch User Attributes ---
    print("\n--- Step 2: Bulk Fetching User Attributes ---")
    attr_assign_sql = """
        SELECT T1.identity_id, T1.attribute_name, T1.attribute_value 
        FROM Identity_Attributes_Filtered AS T1
        JOIN Identities_Filtered AS T2 ON T1.identity_id = T2.id
        WHERE T1.attribute_name NOT IN ('Combined Attribute', 'Union Attribute')
        """
    cursor.execute(attr_assign_sql)
    assignment_rows = cursor.fetchall()
    print(f"  -> Fetched {len(assignment_rows)} total user attribute mappings.")

    attr_user_sets = defaultdict(set)
    user_to_attrs = defaultdict(list)

    for row in assignment_rows:
      key = (str(row["attribute_name"]), str(row["attribute_value"]))
      if key in attr_map:
        uid = str(row["identity_id"])
        attr_user_sets[key].add(uid)
        user_to_attrs[uid].append(key)

    # --- Step 3: Fast Inverted-Index Co-occurrence & Jaccard ---
    print(
        "\n--- Step 3: Computing Pairwise Attribute Similarities via Inverted"
        " Index & Tiers ---"
    )
    pair_intersections = defaultdict(int)

    for uid, attrs in user_to_attrs.items():
      n = len(attrs)
      if n < 2:
        continue
      sorted_attrs = sorted(attrs)
      for i in range(n):
        attr_a = sorted_attrs[i]
        for j in range(i + 1, n):
          attr_b = sorted_attrs[j]
          pair_intersections[(attr_a, attr_b)] += 1

    print(
        f"  -> Evaluated {len(pair_intersections)} co-occurring attribute pairs."
    )

    exact_matches = []
    near_matches = []

    for (attr_A_key, attr_B_key), intersection_size in (
        pair_intersections.items()
    ):
      name_A, val_A = attr_A_key
      name_B, val_B = attr_B_key

      pop_A = len(attr_user_sets[attr_A_key])
      pop_B = len(attr_user_sets[attr_B_key])

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
          exact_matches.append(
              (str(name_A), str(val_A), str(name_B), str(val_B), int(pop_A))
          )
        else:
          near_matches.append((
              str(name_A),
              str(val_A),
              str(name_B),
              str(val_B),
              float(round(score, 4)),
              int(pop_A),
              int(pop_B),
          ))

    print(
        f"\n--- Found {len(exact_matches)} Exact and {len(near_matches)} Near"
        " Attribute Correlations ---"
    )

    # --- Step 4: Batch Persistence ---
    print("\n--- Step 4: Loading Correlations into Database ---")
    cursor.execute("TRUNCATE TABLE Attribute_Exact_Correlations")
    cursor.execute("TRUNCATE TABLE Attribute_Near_Correlations")
    db_connection.commit()

    if exact_matches:
      exact_sql = """
            INSERT INTO Attribute_Exact_Correlations 
            (attribute_A_name, attribute_A_value, attribute_B_name, attribute_B_value, population_size) 
            VALUES (%s, %s, %s, %s, %s)
            """
      for s in range(0, len(exact_matches), BATCH_SIZE):
        cursor.executemany(exact_sql, exact_matches[s : s + BATCH_SIZE])
      print(f"  -> Inserted {len(exact_matches)} exact attribute correlations.")

    if near_matches:
      near_sql = """
            INSERT INTO Attribute_Near_Correlations 
            (attribute_A_name, attribute_A_value, attribute_B_name, attribute_B_value, jaccard_score, population_A_size, population_B_size) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
      for s in range(0, len(near_matches), BATCH_SIZE):
        cursor.executemany(near_sql, near_matches[s : s + BATCH_SIZE])
      print(f"  -> Inserted {len(near_matches)} near attribute correlations.")

    db_connection.commit()
    print("Attribute graph edge generation complete.")

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
