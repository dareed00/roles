# analyze_entitlement_communities.py

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
    # --- Step 1: Pre-cache Entitlement Metadata & Identity Footprints ---
    print("\n--- Step 1: Pre-caching Entitlement Identity Footprints ---")
    cursor.execute(
        "SELECT id, entitlement_id, entitlement_name, source_name,"
        " population_size FROM entitlements"
    )
    entitlements = {row["id"]: row for row in cursor.fetchall()}

    cache_sql = """
        SELECT DISTINCT T2.id AS ent_db_id, T1.identity_id
        FROM (
            SELECT identity_id, entitlement_id FROM IdentityEffectiveEntitlements_Filtered
            UNION
            SELECT identity_id, entitlement_id FROM IdentityEntitlementAssignments_Filtered
        ) AS T1
        JOIN entitlements AS T2 ON T1.entitlement_id = T2.entitlement_id
        JOIN Identities_Filtered AS T3 ON T1.identity_id = T3.id
        """
    cursor.execute(cache_sql)
    ent_user_cache = defaultdict(set)
    for r in cursor.fetchall():
      ent_user_cache[r["ent_db_id"]].add(str(r["identity_id"]))
    print(
        f"  -> Pre-cached access sets for {len(ent_user_cache)} entitlements."
    )

    # --- Step 2: Build Graph from Exact + Near Correlations ---
    print(
        "\n--- Step 2: Fetching All Weighted Edges (Exact + Near"
        " Correlations) ---"
    )
    edge_query = """
        SELECT entitlement_A_id, entitlement_B_id, 1.0 AS jaccard_score FROM Entitlement_Exact_Correlations
        UNION ALL
        SELECT entitlement_A_id, entitlement_B_id, jaccard_score FROM Entitlement_Near_Correlations
        """
    cursor.execute(edge_query)
    correlations = cursor.fetchall()

    G = nx.Graph()
    for ent_id, ent_data in entitlements.items():
      G.add_node(
          ent_id,
          name=ent_data["entitlement_name"],
          source=ent_data["source_name"],
          pop_size=ent_data["population_size"],
      )

    for corr in correlations:
      G.add_edge(
          int(corr["entitlement_A_id"]),
          int(corr["entitlement_B_id"]),
          weight=float(corr["jaccard_score"]),
      )

    print(
        f"  -> Graph built: {G.number_of_nodes()} nodes,"
        f" {G.number_of_edges()} edges."
    )
    if G.number_of_edges() == 0:
      print("No correlation edges found. Run edge generation script first.")
      return

    # --- Step 3: Run Native NetworkX Louvain ---
    print("\n--- Step 3: Running NetworkX Louvain Community Detection ---")
    communities_list = louvain_communities(G, weight="weight", seed=42)
    modularity_score = nx_modularity(G, communities_list, weight="weight")
    print(
        f"  -> Discovered {len(communities_list)} communities (Modularity:"
        f" {modularity_score:.4f})."
    )

    # --- Step 4: Reset & Populate Potential_Roles Tables ---
    print(
        "\n--- Step 4: Scoring Communities and Loading into Database Tables ---"
    )
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    cursor.execute("TRUNCATE TABLE Potential_Roles")
    cursor.execute("TRUNCATE TABLE Potential_Role_Entitlements")
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

      # In-memory user footprint union
      all_users = set().union(
          *(ent_user_cache.get(node_id, set()) for node_id in nodes)
      )
      community_score = (
          (avg_cohesion * 0.6) + (len(nodes) * 0.3) + (len(all_users) * 0.1)
      )

      # 1. Insert parent Potential_Roles
      cursor.execute(
          """
            INSERT INTO Potential_Roles 
            (community_id, recommendation_score, avg_internal_jaccard, entitlement_count, user_footprint) 
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
      potential_role_db_id = cursor.lastrowid

      # 2. Insert members into Potential_Role_Entitlements
      members_to_load = []
      for node_id in nodes:
        node_data = G.nodes[node_id]
        centrality = sum(
            G[node_id][nbr].get("weight", 1.0)
            for nbr in G.neighbors(node_id)
            if nbr in nodes
        )
        members_to_load.append((
            int(potential_role_db_id),
            int(node_id),
            str(node_data["name"]),
            str(node_data["source"]) if node_data["source"] else "",
            int(node_data["pop_size"]),
            float(centrality),
        ))

      cursor.executemany(
          """
            INSERT INTO Potential_Role_Entitlements 
            (potential_role_id, entitlement_id, entitlement_name, entitlement_source, population_size, internal_centrality_score) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
          members_to_load,
      )
      loaded_roles += 1

    db_connection.commit()
    print(
        f"  -> Successfully analyzed and persisted {loaded_roles} candidate"
        " roles to Potential_Roles."
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
