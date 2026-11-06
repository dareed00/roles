#!/usr/bin/env python3
"""
bundleBuilder - Script 1: Populate Tripartite Knowledge Graph (with Attribute Filtering)
Extracts Identities, Selected Business Attributes, and Entitlements into a structured heterogeneous graph.
"""

import os
import sys
import pickle
from datetime import datetime
from collections import defaultdict
import mysql.connector
from mysql.connector import Error
import networkx as nx

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

# ==============================================================================
# 1. CONFIGURATION & ATTRIBUTE FILTERING
# ==============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}
GRAPH_PICKLE_FILE = "tripartite_graph.gpickle"

# ------------------------------------------------------------------------------
# ATTRIBUTE FILTER CONFIGURATION
# ------------------------------------------------------------------------------
# 1. ALLOWLIST: Only attributes listed here will be added to the graph.
#    (Set to None if you want to allow all attributes by default)
ALLOWED_ATTRIBUTES = (
    "jobTitle",
    "department",
    "location",
    "country",
    "type",
    "isManager",
    "division",
    "costCenter",
)

# 2. BLOCKLIST: Attributes listed here are explicitly EXCLUDED (e.g. system/runtime flags).
EXCLUDED_ATTRIBUTES = (
    "cloudStatus",
    "lifecycleState",
    "cloudLifecycleState",
    "identityStatus",
     "identityState",
    "employeeNumber",
     "visibleSegments",
    "email",
    "uid",
    "id",
    "passwordStatus",
    "lastRefresh",
    "endDate",
    "startDate",
)


# ==============================================================================
# 2. GRAPH POPULATION ENGINE
# ==============================================================================
def populate_graph():
    try:
        print("🔗 Connecting to MySQL bundleBuilder...")
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor(dictionary=True)

        G = nx.Graph()

        # ----------------------------------------------------------------------
        # 1. LOAD IDENTITIES
        # ----------------------------------------------------------------------
        print("👤 Loading Identities from Identities_Filtered...")
        cursor.execute("SELECT id, name AS uid, displayName, email, isManager FROM Identities_Filtered")
        identities = cursor.fetchall()
        
        nodes_batch = []
        for u in identities:
            nid = f"ID::{u['id']}"
            display = u["displayName"] or u["uid"] or u["id"]
            G.add_node(nid, node_type="IDENTITY", uid=u["uid"], display_name=display, is_manager=bool(u["isManager"]))
            nodes_batch.append((nid, "IDENTITY", display, 1))

        # ----------------------------------------------------------------------
        # 2. LOAD ATTRIBUTES & HAS_ATTRIBUTE EDGES (WITH FILTERING)
        # ----------------------------------------------------------------------
        print("🏷️ Loading Attributes with configured allowlist/blocklist filters...")
        
        # Build dynamic SQL WHERE clause
        where_clauses = ["attribute_value IS NOT NULL", "TRIM(attribute_value) != ''"]
        params = []

        if ALLOWED_ATTRIBUTES:
            placeholders = ", ".join(["%s"] * len(ALLOWED_ATTRIBUTES))
            where_clauses.append(f"attribute_name IN ({placeholders})")
            params.extend(ALLOWED_ATTRIBUTES)

        if EXCLUDED_ATTRIBUTES:
            placeholders = ", ".join(["%s"] * len(EXCLUDED_ATTRIBUTES))
            where_clauses.append(f"attribute_name NOT IN ({placeholders})")
            params.extend(EXCLUDED_ATTRIBUTES)

        query = f"""
            SELECT identity_id, attribute_name, attribute_value
            FROM Identity_Attributes_Filtered
            WHERE {' AND '.join(where_clauses)}
        """
        cursor.execute(query, params)
        attr_rows = cursor.fetchall()
        
        attr_pops = defaultdict(int)
        edges_batch = []

        for r in attr_rows:
            a_name = r["attribute_name"].strip()
            a_val = r["attribute_value"].strip()
            attr_key = f"ATTR::{a_name}={a_val}"
            id_key = f"ID::{r['identity_id']}"
            
            attr_pops[attr_key] += 1
            G.add_edge(id_key, attr_key, relation="HAS_ATTRIBUTE", weight=1.0)
            edges_batch.append((id_key, attr_key, "HAS_ATTRIBUTE", 1.0000))

        for attr_key, pop in attr_pops.items():
            name_val = attr_key.replace("ATTR::", "")
            k, v = name_val.split("=", 1)
            G.add_node(attr_key, node_type="ATTRIBUTE", attribute_name=k, attribute_value=v, population_size=pop)
            nodes_batch.append((attr_key, "ATTRIBUTE", name_val, pop))

        # ----------------------------------------------------------------------
        # 3. LOAD ENTITLEMENTS & HOLDS_ACCESS EDGES
        # ----------------------------------------------------------------------
        print("🔑 Loading Entitlements (Direct + Effective)...")
        cursor.execute("""
            SELECT DISTINCT identity_id, entitlement_name 
            FROM (
                SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
                UNION
                SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
            ) t
        """)
        ent_rows = cursor.fetchall()
        
        ent_pops = defaultdict(int)
        for r in ent_rows:
            ent_key = f"ENT::{r['entitlement_name'].strip()}"
            id_key = f"ID::{r['identity_id']}"
            
            ent_pops[ent_key] += 1
            G.add_edge(id_key, ent_key, relation="HOLDS_ACCESS", weight=1.0)
            edges_batch.append((id_key, ent_key, "HOLDS_ACCESS", 1.0000))

        for ent_key, pop in ent_pops.items():
            raw_name = ent_key.replace("ENT::", "")
            G.add_node(ent_key, node_type="ENTITLEMENT", entitlement_name=raw_name, population_size=pop)
            nodes_batch.append((ent_key, "ENTITLEMENT", raw_name, pop))

        # ----------------------------------------------------------------------
        # 4. PERSIST TO DATABASE (Graph_Nodes & Graph_Edges)
        # ----------------------------------------------------------------------
        print(f"💾 Persisting {len(nodes_batch):,} Nodes and {len(edges_batch):,} Edges to MySQL...")
        cur_exec = db_connection.cursor()
        cur_exec.execute("DELETE FROM Graph_Edges")
        cur_exec.execute("DELETE FROM Graph_Nodes")

        cur_exec.executemany("""
            INSERT INTO Graph_Nodes (node_id, node_type, display_label, population_size)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE population_size = VALUES(population_size)
        """, nodes_batch)

        chunk_size = 10000
        for i in range(0, len(edges_batch), chunk_size):
            chunk = edges_batch[i:i + chunk_size]
            cur_exec.executemany("""
                INSERT IGNORE INTO Graph_Edges (source_node_id, target_node_id, relation_type, weight)
                VALUES (%s, %s, %s, %s)
            """, chunk)

        db_connection.commit()
        cursor.close()
        cur_exec.close()
        db_connection.close()

        # Serialize graph to file
        with open(GRAPH_PICKLE_FILE, "wb") as f:
            pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

        print(f"\n✅ Tripartite Graph successfully built and serialized to '{GRAPH_PICKLE_FILE}'!")
        print(f"   • Identities: {len(identities):,}")
        print(f"   • Filtered Attributes: {len(attr_pops):,} (Filtered out exclusions like cloudStatus)")
        print(f"   • Entitlements: {len(ent_pops):,}")
        print(f"   • Total Graph Edges: {G.number_of_edges():,}")

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    populate_graph()
