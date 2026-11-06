#!/usr/bin/env python3
"""
bundleBuilder - Compound & Multi-Value Union Role Mining Engine (Deduplicated)
Discovers:
  1. Single Attribute Multi-Value Unions (e.g., location IN ('Detroit', 'Flint'))
  2. Cross-Attribute Compound Intersections (e.g., dept='Finance' AND location IN ('Detroit', 'Flint'))
"""

import os
import sys
import pickle
from datetime import datetime
from collections import defaultdict
from itertools import combinations
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

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}
GRAPH_PICKLE_FILE = "tripartite_graph.gpickle"

# Mining Hyperparameters
MIN_ENTITLEMENT_CO_OCCURRENCE_JACCARD = 0.50  # Access clustering threshold
MIN_ATTRIBUTE_SUPPORT = 0.65                 # % of target users who must match attribute
MIN_ROLE_FOOTPRINT = 1                       # Minimum valid population


# ==============================================================================
# 1. PLURALIZATION & NAMING HELPER
# ==============================================================================
def pluralize_phrase(text):
    if not text:
        return ""
    words = text.strip().split()
    if not words:
        return ""
    last = words[-1].lower()
    
    collective = {"staff", "personnel", "faculty", "sales", "operations", "finance", "legal", "marketing", "it", "security", "data"}
    if last in collective or (last.endswith("s") and not last.endswith(("ss", "us", "is"))):
        return text

    irregulars = {
        "doctor": "doctors", "nurse": "nurses", "analyst": "analysts", "specialist": "specialists",
        "lead": "leads", "manager": "managers", "engineer": "engineers", "developer": "developers",
        "architect": "architects", "administrator": "administrators", "consultant": "consultants",
        "intern": "interns", "contractor": "contractors", "employee": "employees", "user": "users"
    }
    if last in irregulars:
        words[-1] = irregulars[last].capitalize() if words[-1][0].isupper() else irregulars[last]
        return " ".join(words)

    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        words[-1] = words[-1][:-1] + ("IES" if words[-1].isupper() else "ies")
    elif last.endswith(("s", "x", "z", "ch", "sh", "ss")):
        words[-1] = words[-1] + ("ES" if words[-1].isupper() else "es")
    else:
        words[-1] = words[-1] + ("S" if words[-1].isupper() else "s")
    return " ".join(words)


# ==============================================================================
# 2. CANDIDATE ATTRIBUTE & MULTI-VALUE UNION GENERATOR
# ==============================================================================
def generate_candidate_attribute_features(G, target_identity_set):
    target_count = len(target_identity_set)
    if target_count == 0:
        return []

    attrs_by_name = defaultdict(lambda: defaultdict(set))
    for uid in target_identity_set:
        for neighbor in G.neighbors(uid):
            if G.nodes[neighbor].get("node_type") == "ATTRIBUTE":
                a_name = G.nodes[neighbor]["attribute_name"]
                a_val = G.nodes[neighbor]["attribute_value"]
                attrs_by_name[a_name][a_val].add(uid)

    candidate_features = []

    for a_name, val_uids_map in attrs_by_name.items():
        # A. Single-value candidates
        for a_val, target_overlap in val_uids_map.items():
            support = len(target_overlap) / target_count
            if support >= MIN_ATTRIBUTE_SUPPORT:
                attr_node = f"ATTR::{a_name}={a_val}"
                all_uids = set(n for n in G.neighbors(attr_node) if G.nodes[n].get("node_type") == "IDENTITY") if attr_node in G else set()
                candidate_features.append({
                    "attribute_name": a_name,
                    "values": [a_val],
                    "label": f"{a_name}='{a_val}'",
                    "display_label": a_val,
                    "uids": all_uids,
                    "support": support,
                    "is_union": False
                })

        # B. Pairwise same-attribute unions
        val_list = list(val_uids_map.keys())
        if len(val_list) >= 2:
            for v1, v2 in combinations(val_list, 2):
                combined_target_overlap = val_uids_map[v1] | val_uids_map[v2]
                support = len(combined_target_overlap) / target_count
                v1_supp = len(val_uids_map[v1]) / target_count
                v2_supp = len(val_uids_map[v2]) / target_count
                
                if support >= MIN_ATTRIBUTE_SUPPORT and support > max(v1_supp, v2_supp):
                    node1 = f"ATTR::{a_name}={v1}"
                    node2 = f"ATTR::{a_name}={v2}"
                    uids1 = set(n for n in G.neighbors(node1) if G.nodes[n].get("node_type") == "IDENTITY") if node1 in G else set()
                    uids2 = set(n for n in G.neighbors(node2) if G.nodes[n].get("node_type") == "IDENTITY") if node2 in G else set()
                    union_uids = uids1 | uids2

                    candidate_features.append({
                        "attribute_name": a_name,
                        "values": [v1, v2],
                        "label": f"{a_name} IN ('{v1}', '{v2}')",
                        "display_label": f"{v1} & {v2}",
                        "uids": union_uids,
                        "support": support,
                        "is_union": True
                    })

    return candidate_features


# ==============================================================================
# 3. GREEDY MULTI-ATTRIBUTE SELECTION
# ==============================================================================
def discover_optimal_compound_rule(G, target_identity_set, all_identities_set):
    target_count = len(target_identity_set)
    if target_count == 0:
        return None

    candidates = generate_candidate_attribute_features(G, target_identity_set)
    if not candidates:
        return None

    def feature_precision(feat):
        feat_uids = feat["uids"]
        inter = len(feat_uids & target_identity_set)
        return inter / len(feat_uids) if feat_uids else 0

    candidates.sort(key=feature_precision, reverse=True)

    selected_features = []
    used_attribute_names = set()
    current_matched_users = set(all_identities_set)
    best_jaccard = 0.0

    for feat in candidates:
        if feat["attribute_name"] in used_attribute_names:
            continue

        candidate_intersect = current_matched_users & feat["uids"]
        intersection = len(candidate_intersect & target_identity_set)
        union = len(candidate_intersect | target_identity_set)
        jaccard = intersection / union if union > 0 else 0

        if jaccard >= best_jaccard or not selected_features:
            selected_features.append(feat)
            used_attribute_names.add(feat["attribute_name"])
            current_matched_users = candidate_intersect
            best_jaccard = jaccard
        elif len(candidate_intersect) < target_count * 0.5:
            break

    if not selected_features:
        return None

    intersection = len(current_matched_users & target_identity_set)
    footprint = len(current_matched_users)
    coverage = intersection / footprint if footprint > 0 else 0.0
    purity = intersection / target_count if target_count > 0 else 0.0
    jaccard = intersection / len(current_matched_users | target_identity_set) if len(current_matched_users | target_identity_set) > 0 else 0.0

    return {
        "features": selected_features,
        "matched_identities": current_matched_users,
        "role_footprint": footprint,
        "coverage": coverage,
        "purity": purity,
        "jaccard": jaccard
    }


# ==============================================================================
# 4. ROLE MINING & CASE-INSENSITIVE DEDUPLICATION
# ==============================================================================
def mine_roles_from_graph():
    if not os.path.exists(GRAPH_PICKLE_FILE):
        print(f"❌ Graph file '{GRAPH_PICKLE_FILE}' not found! Run 'populate_tripartite_graph.py' first.")
        sys.exit(1)

    print(f"📂 Loading serialized Tripartite Graph from '{GRAPH_PICKLE_FILE}'...")
    with open(GRAPH_PICKLE_FILE, "rb") as f:
        G = pickle.load(f)

    all_identities = set(n for n, d in G.nodes(data=True) if d.get("node_type") == "IDENTITY")
    all_entitlements = [n for n, d in G.nodes(data=True) if d.get("node_type") == "ENTITLEMENT"]
    print(f"👥 Graph contains {len(all_identities):,} Identities and {len(all_entitlements):,} Entitlements.")

    # 1. Cluster Co-occurring Entitlements
    print("🧩 Finding co-occurring entitlement bundles...")
    ent_user_sets = {}
    for ent in all_entitlements:
        uids = set(n for n in G.neighbors(ent) if G.nodes[n].get("node_type") == "IDENTITY")
        if uids:
            ent_user_sets[ent] = uids

    G_ent = nx.Graph()
    ent_list = list(ent_user_sets.keys())
    for i in range(len(ent_list)):
        e1 = ent_list[i]
        s1 = ent_user_sets[e1]
        G_ent.add_node(e1)
        for j in range(i + 1, len(ent_list)):
            e2 = ent_list[j]
            s2 = ent_user_sets[e2]
            inter = len(s1 & s2)
            if inter == 0:
                continue
            jaccard = inter / len(s1 | s2)
            if jaccard >= MIN_ENTITLEMENT_CO_OCCURRENCE_JACCARD:
                G_ent.add_edge(e1, e2, weight=jaccard)

    ent_clusters = list(nx.community.louvain_communities(G_ent, weight="weight", seed=42)) if G_ent.number_of_edges() > 0 else [[e] for e in ent_list]
    print(f"📦 Discovered {len(ent_clusters):,} cohesive entitlement clusters.")

    # 2. Mine Optimal Multi-Attribute Rules
    mined_roles = []
    for cluster_idx, cluster in enumerate(ent_clusters, start=1):
        target_uids = set()
        for ent in cluster:
            target_uids.update(ent_user_sets.get(ent, set()))

        if len(target_uids) < MIN_ROLE_FOOTPRINT:
            continue

        rule_result = discover_optimal_compound_rule(G, target_uids, all_identities)
        if not rule_result or rule_result["role_footprint"] < MIN_ROLE_FOOTPRINT:
            continue

        # Criteria text & display name
        criteria_parts = [f["label"] for f in rule_result["features"]]
        compound_criteria_str = " AND ".join(criteria_parts)

        name_parts = [f["display_label"] for f in rule_result["features"][:3]]
        if name_parts:
            formatted_tokens = [
                pluralize_phrase(p) if i == len(name_parts) - 1 else p 
                for i, p in enumerate(name_parts)
            ]
            role_display_name = f"All {' '.join(formatted_tokens)}"
        else:
            role_display_name = f"Discovered Role #{cluster_idx}"

        if len(role_display_name) > 250:
            role_display_name = role_display_name[:247] + "..."

        # Attributes (Deduplicated case-insensitively)
        parsed_attr_map = {}
        for f in rule_result["features"]:
            for val in f["values"]:
                attr_dedup_key = (f["attribute_name"].lower().strip(), val.lower().strip())
                if attr_dedup_key not in parsed_attr_map:
                    parsed_attr_map[attr_dedup_key] = {
                        "name": f["attribute_name"],
                        "value": val,
                        "population": len(f["uids"])
                    }
        parsed_attributes = list(parsed_attr_map.values())

        # Entitlements (Deduplicated case-insensitively)
        compound_identities = rule_result["matched_identities"]
        entitlement_eval_map = {}

        for ent_node in cluster:
            ent_name = G.nodes[ent_node].get("entitlement_name", ent_node.replace("ENT::", "")).strip()
            ent_uids = ent_user_sets.get(ent_node, set())
            
            inter = len(compound_identities & ent_uids)
            cov = inter / len(compound_identities) if compound_identities else 0
            pur = inter / len(ent_uids) if ent_uids else 0
            jac = inter / len(compound_identities | ent_uids) if (compound_identities | ent_uids) else 0
            status = "CORE" if cov >= 0.85 else ("EVALUATE" if cov >= 0.50 else "OUTLIER")

            # Deduplicate by ent_name (keep the one with highest Jaccard if duplicates exist)
            if ent_name not in entitlement_eval_map or jac > entitlement_eval_map[ent_name]["jaccard"]:
                entitlement_eval_map[ent_name] = {
                    "name": ent_name,
                    "population": len(ent_uids),
                    "coverage": cov,
                    "purity": pur,
                    "jaccard": jac,
                    "status": status
                }

        entitlement_evaluations = list(entitlement_eval_map.values())

        mined_roles.append({
            "role_name": role_display_name,
            "compound_criteria": compound_criteria_str,
            "attribute_count": len(parsed_attributes),
            "entitlement_count": len(entitlement_evaluations),
            "role_footprint": rule_result["role_footprint"],
            "avg_coverage": rule_result["coverage"],
            "avg_purity": rule_result["purity"],
            "avg_jaccard": rule_result["jaccard"],
            "missing_identities_count": len(compound_identities - target_uids),
            "extra_identities_count": len(target_uids - compound_identities),
            "attributes": parsed_attributes,
            "entitlements": entitlement_evaluations
        })

    mined_roles.sort(key=lambda r: (r["avg_jaccard"], r["role_footprint"]), reverse=True)
    print(f"🎯 Successfully generated {len(mined_roles):,} validated compound roles.")
    persist_roles_to_mysql(mined_roles)


# ==============================================================================
# 5. DATABASE PERSISTENCE (WITH INSERT IGNORE)
# ==============================================================================
def persist_roles_to_mysql(mined_roles):
    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor()

        print(f"💾 Persisting {len(mined_roles)} compound roles to database...")
        cursor.execute("DELETE FROM Tripartite_Role_Attributes")
        cursor.execute("DELETE FROM Tripartite_Role_Entitlements")
        cursor.execute("DELETE FROM Tripartite_Discovered_Roles")

        sql_role = """
            INSERT INTO Tripartite_Discovered_Roles
            (role_name, compound_criteria, attribute_count, entitlement_count, role_footprint,
             avg_coverage, avg_purity, avg_jaccard, missing_identities_count, extra_identities_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        # Using INSERT IGNORE as a safety guarantee against any database collation collisions
        sql_ent = """
            INSERT IGNORE INTO Tripartite_Role_Entitlements
            (role_id, entitlement_name, entitlement_population, coverage_score, purity_score, jaccard_score, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        sql_attr = """
            INSERT IGNORE INTO Tripartite_Role_Attributes
            (role_id, attribute_name, attribute_value, population_size)
            VALUES (%s, %s, %s, %s)
        """

        for r in mined_roles:
            cursor.execute(sql_role, (
                r["role_name"],
                r["compound_criteria"],
                r["attribute_count"],
                r["entitlement_count"],
                r["role_footprint"],
                r["avg_coverage"],
                r["avg_purity"],
                r["avg_jaccard"],
                r["missing_identities_count"],
                r["extra_identities_count"]
            ))
            role_id = cursor.lastrowid

            # Insert Entitlements with local case-deduplication
            seen_ents = set()
            ent_batch = []
            for e in r["entitlements"]:
                e_key = e["name"].lower().strip()
                if e_key not in seen_ents:
                    seen_ents.add(e_key)
                    ent_batch.append((
                        role_id, e["name"], e["population"], e["coverage"],
                        e["purity"], e["jaccard"], e["status"]
                    ))

            if ent_batch:
                cursor.executemany(sql_ent, ent_batch)

            # Insert Attributes with local case-deduplication
            seen_attrs = set()
            attr_batch = []
            for a in r["attributes"]:
                a_key = (a["name"].lower().strip(), a["value"].lower().strip())
                if a_key not in seen_attrs:
                    seen_attrs.add(a_key)
                    attr_batch.append((role_id, a["name"], a["value"], a["population"]))

            if attr_batch:
                cursor.executemany(sql_attr, attr_batch)

        db_connection.commit()
        cursor.close()
        db_connection.close()
        print("✅ Compound roles with same-attribute unions successfully stored in MySQL!")

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    mine_roles_from_graph()
