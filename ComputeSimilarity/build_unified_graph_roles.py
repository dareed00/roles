#!/usr/bin/env python3
"""
Unified Heterogeneous Graph Role Mining Engine
Treats Entitlements and Attribute Populations (Size >= 1) as first-class graph nodes.
Performs Inverted-Index Sparse Jaccard Calculation + Louvain Community Clustering.
"""

import os
import sys
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
# CONFIGURATION
# ==============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}

# Jaccard edge threshold (edges below this similarity are ignored)
JACCARD_THRESHOLD = 0.40

# Population Filters: Load populations of 1 or greater
MIN_ATTR_POPULATION = 1        # Load all populations of size 1 or greater
MAX_ATTR_POPULATION_PCT = 1.00 # No upper bound limit (100% allowed)

# Attribute keys to include (set to None if you want literally every attribute name)
INCLUDED_ATTRIBUTE_NAMES = ("jobTitle", "department", "location", "country", "type", "isManager")


# ==============================================================================
# PLURALIZATION HELPER
# ==============================================================================
def pluralize_phrase(text):
    if not text:
        return ""
    text = text.strip()
    words = text.split()
    if not words:
        return ""

    last_word = words[-1]
    lower_last = last_word.lower()

    collective_or_uncountable = {
        "staff", "personnel", "faculty", "police", "people",
        "sales", "operations", "resources", "services", "logistics",
        "analytics", "finance", "legal", "procurement", "marketing",
        "engineering", "it", "security", "data", "software", "hardware",
        "management", "accounting", "admin", "support", "infrastructure",
    }
    if lower_last in collective_or_uncountable:
        return text

    if lower_last.endswith("s") and not lower_last.endswith(("ss", "us", "is")):
        return text

    irregulars = {
        "person": "people", "man": "men", "woman": "women", "child": "children",
        "doctor": "doctors", "nurse": "nurses", "physician": "physicians",
        "analyst": "analysts", "specialist": "specialists", "scientist": "scientists",
        "lead": "leads", "manager": "managers", "director": "directors",
        "officer": "officers", "engineer": "engineers", "developer": "developers",
        "architect": "architects", "administrator": "administrators",
        "consultant": "consultants", "intern": "interns", "representative": "representatives",
        "accountant": "accountants", "technician": "technicians", "coordinator": "coordinators",
        "supervisor": "supervisors", "associate": "associates", "executive": "executives",
        "advisor": "advisors", "adviser": "advisers", "worker": "workers",
        "contractor": "contractors", "employee": "employees", "user": "users", "member": "members",
    }

    if lower_last in irregulars:
        plural_last = irregulars[lower_last]
        if last_word.isupper():
            plural_last = plural_last.upper()
        elif last_word[0].isupper():
            plural_last = plural_last.capitalize()
        words[-1] = plural_last
        return " ".join(words)

    if lower_last.endswith("y") and len(lower_last) > 1 and lower_last[-2] not in "aeiou":
        plural_last = last_word[:-1] + ("IES" if last_word.isupper() else "ies")
    elif lower_last.endswith(("s", "x", "z", "ch", "sh", "ss")):
        plural_last = last_word + ("ES" if last_word.isupper() else "es")
    else:
        plural_last = last_word + ("S" if last_word.isupper() else "s")

    words[-1] = plural_last
    return " ".join(words)


# ==============================================================================
# 1. EXTRACT POPULATIONS (POPULATION >= 1)
# ==============================================================================
def load_feature_populations(db_connection.:
    cursor = db_connection.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(DISTINCT id) AS total FROM Identities_Filtered")
    total_identities = cursor.fetchone()["total"] or 1
    print(f"👥 Total Filtered Identities: {total_identities:,}")

    feature_sets = {}
    feature_meta = {}

    # A. Entitlements (Direct + Effective)
    print("📦 Extracting Entitlement assignment populations...")
    cursor.execute("""
        SELECT DISTINCT identity_id, entitlement_name 
        FROM (
            SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
            UNION
            SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
        ) t
    """)
    for row in cursor.fetchall():
        fid = f"ENT::{row['entitlement_name']}"
        if fid not in feature_sets:
            feature_sets[fid] = set()
            feature_meta[fid] = {
                "type": "ENTITLEMENT",
                "name": row["entitlement_name"],
                "source": "Catalog",
                "attr_name": None,
                "attr_val": None,
            }
        feature_sets[fid].add(row["identity_id"])

    # B. Attributes (Populations of 1 or Greater)
    print(f"🏷️ Extracting Attribute populations (Min Population >= {MIN_ATTR_POPULATION})...")
    if INCLUDED_ATTRIBUTE_NAMES:
        placeholders = ", ".join(["%s"] * len(INCLUDED_ATTRIBUTE_NAMES))
        query = f"""
            SELECT identity_id, attribute_name, attribute_value
            FROM Identity_Attributes_Filtered
            WHERE attribute_name IN ({placeholders})
              AND attribute_value IS NOT NULL 
              AND TRIM(attribute_value) != ''
        """
        cursor.execute(query, INCLUDED_ATTRIBUTE_NAMES)
    else:
        query = """
            SELECT identity_id, attribute_name, attribute_value
            FROM Identity_Attributes_Filtered
            WHERE attribute_value IS NOT NULL 
              AND TRIM(attribute_value) != ''
        """
        cursor.execute(query)

    raw_attr_sets = defaultdict(set)
    for row in cursor.fetchall():
        key = (row["attribute_name"], row["attribute_value"].strip())
        raw_attr_sets[key].add(row["identity_id"])

    # Load all attribute populations matching criteria
    max_pop_limit = int(total_identities * MAX_ATTR_POPULATION_PCT)
    for (attr_k, attr_v), uids in raw_attr_sets.items():
        pop = len(uids)
        if pop < MIN_ATTR_POPULATION or pop > max_pop_limit:
            continue
        fid = f"ATTR::{attr_k}={attr_v}"
        feature_sets[fid] = uids
        feature_meta[fid] = {
            "type": "ATTRIBUTE",
            "name": f"{attr_k}={attr_v}",
            "source": "HRIS",
            "attr_name": attr_k,
            "attr_val": attr_v,
        }

    cursor.close()
    print(f"✨ Loaded {len(feature_sets):,} total population nodes ({sum(1 for f in feature_meta.values() if f['type']=='ENTITLEMENT')} Entitlements, {sum(1 for f in feature_meta.values() if f['type']=='ATTRIBUTE')} Attributes).")
    return feature_sets, feature_meta, total_identities


# ==============================================================================
# 2. INVERTED INDEX & FAST SPARSE JACCARD CALCULATION
# ==============================================================================
def compute_sparse_jaccard_graph(feature_sets, feature_meta):
    print("⚡ Building Inverted Index (Identity -> Features)...")
    identity_to_features = defaultdict(list)
    for fid, uids in feature_sets.items():
        for uid in uids:
            identity_to_features[uid].append(fid)

    print("⚡ Computing co-occurrence intersections...")
    pair_intersections = defaultdict(int)
    for uid, f_list in identity_to_features.items():
        n = len(f_list)
        for i in range(n):
            f1 = f_list[i]
            for j in range(i + 1, n):
                f2 = f_list[j]
                pair_key = (f1, f2) if f1 < f2 else (f2, f1)
                pair_intersections[pair_key] += 1

    print("🕸️ Building Heterogeneous NetworkX Graph...")
    G = nx.Graph()

    for fid, meta in feature_meta.items():
        G.add_node(
            fid,
            node_type=meta["type"],
            node_name=meta["name"],
            source=meta["source"],
            attr_name=meta["attr_name"],
            attr_val=meta["attr_val"],
            population=len(feature_sets[fid]),
        )

    edge_count = 0
    for (f1, f2), intersection in pair_intersections.items():
        pop1 = len(feature_sets[f1])
        pop2 = len(feature_sets[f2])
        union = pop1 + pop2 - intersection
        if union == 0:
            continue
        jaccard = intersection / union

        if jaccard >= JACCARD_THRESHOLD:
            G.add_edge(f1, f2, weight=jaccard)
            edge_count += 1

    print(f"✅ Graph built: {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges (Threshold >= {JACCARD_THRESHOLD}).")
    return G


# ==============================================================================
# 3. LOUVAIN COMMUNITY DETECTION & ROLE SYNTHESIS
# ==============================================================================
def mine_unified_roles(G, feature_sets):
    print("🔬 Executing Louvain Community Clustering on Unified Graph...")
    communities = nx.community.louvain_communities(G, weight="weight", resolution=1.0, seed=42)
    print(f"🎯 Discovered {len(communities):,} total Louvain communities.")

    mined_roles = []

    for comm_idx, comm_nodes in enumerate(communities, start=1):
        if len(comm_nodes) < 2:
            continue

        subgraph = G.subgraph(comm_nodes)
        weighted_degrees = dict(subgraph.degree(weight="weight"))
        total_weight = sum(d.get("weight", 1.0) for u, v, d in subgraph.edges(data=True))
        num_edges = subgraph.number_of_edges()
        avg_jaccard = (total_weight / num_edges) if num_edges > 0 else 1.0

        entitlements = []
        attributes = []
        all_uids_in_community = set()

        for node_id in comm_nodes:
            ndata = G.nodes[node_id]
            centrality = weighted_degrees.get(node_id, 0.0)
            uids = feature_sets.get(node_id, set())
            all_uids_in_community.update(uids)

            member_info = {
                "node_id": node_id,
                "node_type": ndata["node_type"],
                "node_name": ndata["node_name"],
                "source_system": ndata["source"],
                "attr_name": ndata["attr_name"],
                "attr_val": ndata["attr_val"],
                "population_size": ndata["population"],
                "internal_centrality": centrality,
                "is_primary": False,
            }

            if ndata["node_type"] == "ENTITLEMENT":
                entitlements.append(member_info)
            else:
                attributes.append(member_info)

        if not entitlements:
            continue

        entitlements.sort(key=lambda x: x["internal_centrality"], reverse=True)
        attributes.sort(key=lambda x: x["internal_centrality"], reverse=True)

        if attributes:
            primary_attr = attributes[0]
            primary_attr["is_primary"] = True
            plural_name = pluralize_phrase(primary_attr["attr_val"])
            role_name = f"All {plural_name}"
            p_name = primary_attr["attr_name"]
            p_val = primary_attr["attr_val"]
            role_type = "Compound Attribute" if len(attributes) > 1 else "Single Attribute"
            
            crit_parts = [f"{a['attr_name']}='{a['attr_val']}'" for a in attributes[:3]]
            assignment_rule = " AND ".join(crit_parts)
            user_footprint = primary_attr["population_size"]
        else:
            role_name = f"Candidate Community #{comm_idx}"
            p_name = None
            p_val = None
            role_type = "Pure Entitlement Cluster"
            assignment_rule = "Graph Modularity (Anchor Entitlement)"
            user_footprint = entitlements[0]["population_size"]

        rec_score = avg_jaccard * len(entitlements) * (1.5 if attributes else 1.0)

        mined_roles.append({
            "community_id": comm_idx,
            "role_name": role_name,
            "role_type": role_type,
            "primary_attribute_name": p_name,
            "primary_attribute_value": p_val,
            "assignment_rule": assignment_rule,
            "avg_internal_jaccard": avg_jaccard,
            "recommendation_score": rec_score,
            "entitlement_count": len(entitlements),
            "attribute_count": len(attributes),
            "user_footprint": user_footprint,
            "members": attributes + entitlements,
        })

    mined_roles.sort(key=lambda x: x["recommendation_score"], reverse=True)
    return mined_roles


# ==============================================================================
# 4. PERSIST TO MYSQL DATABASE
# ==============================================================================
def save_roles_to_db(db_connection. mined_roles):
    print(f"💾 Persisting {len(mined_roles)} unified roles to bundleBuilder database...")
    cursor = db_connection.cursor()

    cursor.execute("DELETE FROM Unified_Role_Members")
    cursor.execute("DELETE FROM Unified_Discovered_Roles")

    sql_role = """
        INSERT INTO Unified_Discovered_Roles 
        (community_id, role_name, role_type, primary_attribute_name, primary_attribute_value,
         assignment_rule, avg_internal_jaccard, recommendation_score, entitlement_count,
         attribute_count, user_footprint)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    sql_member = """
        INSERT INTO Unified_Role_Members
        (role_id, community_id, node_type, node_name, node_attribute_name, node_attribute_value,
         source_system, population_size, internal_centrality_score, is_primary_criteria)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for r in mined_roles:
        cursor.execute(sql_role, (
            r["community_id"],
            r["role_name"],
            r["role_type"],
            r["primary_attribute_name"],
            r["primary_attribute_value"],
            r["assignment_rule"],
            r["avg_internal_jaccard"],
            r["recommendation_score"],
            r["entitlement_count"],
            r["attribute_count"],
            r["user_footprint"],
        ))
        role_id = cursor.lastrowid

        member_batch = []
        for m in r["members"]:
            member_batch.append((
                role_id,
                r["community_id"],
                m["node_type"],
                m["node_name"],
                m["attr_name"],
                m["attr_val"],
                m["source_system"],
                m["population_size"],
                m["internal_centrality"],
                m["is_primary"],
            ))

        cursor.executemany(sql_member, member_batch)

    db_connection.commit()
    cursor.close()
    print("✅ Successfully stored unified roles and member nodes in MySQL.")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    try:
        print("🔗 Connecting to MySQL bundleBuilder...")
        connection = mysql.connector.connect(**DB_CONFIG)

        f_sets, f_meta, total_ids = load_feature_populations(connection)
        graph = compute_sparse_jaccard_graph(f_sets, f_meta)
        roles = mine_unified_roles(graph, f_sets)
        save_roles_to_db(connection, roles)

        print("\n🏆 TOP DISCOVERED UNIFIED ROLES:")
        for idx, r in enumerate(roles[:8], 1):
            print(f"  {idx}. {r['role_name']} ({r['role_type']})")
            print(f"     Criteria: {r['assignment_rule']}")
            print(f"     Entitlements: {r['entitlement_count']} items | Footprint: {r['user_footprint']} users | Cohesion: {r['avg_internal_jaccard']*100:.1f}%\n")

        connection.close()

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
