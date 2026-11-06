# analyze_and_load_potential_attribute_roles.py

from collections import defaultdict
import json
import mysql.connector
from mysql.connector import Error
import networkx as nx
from networkx.algorithms.community import (
    louvain_communities,
    modularity as nx_modularity,
)

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
    # --- Step 1: Pre-cache Attribute Metadata & Identity Footprints ---
    print("\n--- Step 1: Pre-caching Attribute Identity Footprints ---")
    cursor.execute("""
            SELECT attribute_name, attribute_value, population_size 
            FROM Attribute_Populations 
            WHERE attribute_name NOT IN ('Combined Attribute', 'Union Attribute')
        """)
    attributes = {
        (str(row["attribute_name"]), str(row["attribute_value"])): row
        for row in cursor.fetchall()
    }

    cursor.execute("""
            SELECT T1.identity_id, T1.attribute_name, T1.attribute_value 
            FROM Identity_Attributes_Filtered AS T1
            JOIN Identities_Filtered AS T2 ON T1.identity_id = T2.id
            WHERE T1.attribute_name NOT IN ('Combined Attribute', 'Union Attribute')
        """)
    attr_user_cache = defaultdict(set)
    for r in cursor.fetchall():
      key = (str(r["attribute_name"]), str(r["attribute_value"]))
      attr_user_cache[key].add(str(r["identity_id"]))
    print(f"  -> Pre-cached identities for {len(attr_user_cache)} attributes.")

    # --- Step 2: Build Graph from Exact + Near Correlations ---
    print(
        "\n--- Step 2: Building Attribute Graph (Exact + Near Correlations)"
        " ---"
    )
    edge_sql = """
        SELECT attribute_A_name, attribute_A_value, attribute_B_name, attribute_B_value, 1.0 AS jaccard_score 
        FROM Attribute_Exact_Correlations
        UNION ALL
        SELECT attribute_A_name, attribute_A_value, attribute_B_name, attribute_B_value, jaccard_score 
        FROM Attribute_Near_Correlations
        """
    cursor.execute(edge_sql)
    correlations = cursor.fetchall()

    G = nx.Graph()
    for (name, val), data in attributes.items():
      G.add_node((name, val), pop_size=data["population_size"])

    for corr in correlations:
      node_A = (str(corr["attribute_A_name"]), str(corr["attribute_A_value"]))
      node_B = (str(corr["attribute_B_name"]), str(corr["attribute_B_value"]))
      G.add_edge(node_A, node_B, weight=float(corr["jaccard_score"]))

    print(
        f"  -> Graph built: {G.number_of_nodes()} nodes,"
        f" {G.number_of_edges()} edges."
    )
    if G.number_of_edges() == 0:
      print("No attribute correlation edges found.")
      return

    # --- Step 3: Run Native NetworkX Louvain ---
    print("\n--- Step 3: Running NetworkX Louvain Community Detection ---")
    communities_list = louvain_communities(G, weight="weight", seed=42)
    modularity_score = nx_modularity(G, communities_list, weight="weight")
    print(
        f"  -> Discovered {len(communities_list)} communities (Modularity:"
        f" {modularity_score:.4f})."
    )

    # --- Step 4: Analyze & Persist Candidate Attribute Roles ---
    print("\n--- Step 4: Loading Communities into Database ---")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    cursor.execute("TRUNCATE TABLE Potential_Attribute_Roles")
    cursor.execute("TRUNCATE TABLE Potential_Attribute_Role_Members")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

    loaded_roles = 0
    for cid, node_set in enumerate(communities_list):
      nodes = list(node_set)
      if len(nodes) < 2:
        continue  # Skip singletons

      subgraph = G.subgraph(nodes)
      internal_edges = subgraph.edges(data=True)
      avg_cohesion = (
          sum(d.get("weight", 1.0) for u, v, d in internal_edges)
          / len(internal_edges)
          if internal_edges
          else 0.0
      )

      all_users = set().union(*(attr_user_cache.get(node, set()) for node in nodes))
      community_score = (
          (avg_cohesion * 0.6) + (len(nodes) * 0.3) + (len(all_users) * 0.1)
      )

      # 1. Insert parent Potential_Attribute_Roles
      cursor.execute(
          """
            INSERT INTO Potential_Attribute_Roles 
            (community_id, recommendation_score, avg_internal_jaccard, attribute_count, user_footprint) 
            VALUES (%s, %s, %s, %s, %s)
            """,
          (
              int(cid),
              float(community_score),
              float(avg_cohesion),
              int(len(nodes)),
              int(len(all_users)),
          ),
      )
      role_id = cursor.lastrowid

      # 2. Insert members into Potential_Attribute_Role_Members
      members = []
      for node in nodes:
        attr_name, attr_val = node
        node_data = G.nodes[node]
        centrality = sum(
            G[node][nbr].get("weight", 1.0)
            for nbr in G.neighbors(node)
            if nbr in nodes
        )
        members.append((
            int(role_id),
            str(attr_name),
            str(attr_val),
            int(node_data["pop_size"]),
            float(centrality),
        ))

      cursor.executemany(
          """
            INSERT INTO Potential_Attribute_Role_Members 
            (potential_attribute_role_id, attribute_name, attribute_value, population_size, internal_centrality_score) 
            VALUES (%s, %s, %s, %s, %s)
            """,
          members,
      )
      loaded_roles += 1

    db_connection.commit()
    print(
        f"  -> Successfully loaded {loaded_roles} potential attribute roles"
        " into the database."
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
