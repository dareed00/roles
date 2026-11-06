#!/usr/bin/env python3
"""
bundleBuilder - Exact Correlation Finder
Discovers:
  1. Single Attribute Exact Matches
  2. 2, 3, 4-Way Unions (OR conditions using subsets)
  3. 2-Way Intersections (AND conditions using supersets)
"""

import os
import sys
from collections import defaultdict
from itertools import combinations
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


ALLOWED_ATTRIBUTES = (
    "jobTitle", "department", "location", "country", 
    "type", "isManager", "division", "costCenter",
)

def load_identity_sets():
    try:
         db_connection = get_db_connection(config.get("Database"))
    	if not db_connection return
    
    	cursor = db_connection.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.")

        cursor.execute("""
            SELECT DISTINCT identity_id, entitlement_name 
            FROM (
                SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
                UNION
                SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
            ) t
        """)
        ent_sets = defaultdict(set)
        for row in cursor.fetchall():
            ent_sets[row["entitlement_name"].strip()].add(row["identity_id"])

        where_clause = "WHERE attribute_value IS NOT NULL AND TRIM(attribute_value) != ''"
        params = []
        if ALLOWED_ATTRIBUTES:
            placeholders = ", ".join(["%s"] * len(ALLOWED_ATTRIBUTES))
            where_clause += f" AND attribute_name IN ({placeholders})"
            params.extend(ALLOWED_ATTRIBUTES)

        cursor.execute(f"""
            SELECT identity_id, attribute_name, attribute_value
            FROM Identity_Attributes_Filtered {where_clause}
        """, params)

        attr_sets = defaultdict(set)
        for row in cursor.fetchall():
            key = (row["attribute_name"].strip(), row["attribute_value"].strip())
            attr_sets[key].add(row["identity_id"])

        cursor.close()
        db_connection.close()
        return ent_sets, attr_sets

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)

def format_union_rule(components):
    grouped = defaultdict(list)
    for a_name, a_val, _ in components:
        grouped[a_name].append(a_val)
    clauses = []
    for a_name, vals in grouped.items():
        if len(vals) == 1:
            clauses.append(f"{a_name} = '{vals[0]}'")
        else:
            in_vals = ", ".join(f"'{v}'" for v in vals)
            clauses.append(f"{a_name} IN ({in_vals})")
    match_type = "Same-Attribute Union (OR)" if len(clauses) == 1 else "Cross-Attribute Union (OR)"
    return " OR ".join(f"({c})" if " IN " not in c and len(clauses) > 1 else c for c in clauses), match_type


def find_exact_correlations(ent_sets, attr_sets):
    single_matches, two_way_or, three_way_or, four_way_or, two_way_and = [], [], [], [], []

    print("⚡ Searching for Exact Matches (Unions/OR and Intersections/AND)...\n")

    for ent_name, ent_uids in ent_sets.items():
        ent_pop = len(ent_uids)
        if ent_pop == 0: continue

        pure_subsets = []
        pure_supersets = []

        for (a_name, a_val), a_uids in attr_sets.items():
            a_pop = len(a_uids)

            # Pass 1: 1-to-1 Exact Match
            if a_pop == ent_pop and a_uids == ent_uids:
                single_matches.append({
                    "entitlement_name": ent_name, "population": ent_pop, "rule": f"{a_name} = '{a_val}'"
                })
            # Subsets for OR logic
            elif a_pop < ent_pop and a_uids.issubset(ent_uids):
                pure_subsets.append((a_name, a_val, a_uids))
            # Supersets for AND logic
            elif a_pop > ent_pop and ent_uids.issubset(a_uids):
                pure_supersets.append((a_name, a_val, a_uids))

        # Pass 2: AND Intersections (S_E = S_A1 ∩ S_A2)
        if len(pure_supersets) >= 2:
            for i in range(len(pure_supersets)):
                c1 = pure_supersets[i]
                for j in range(i + 1, len(pure_supersets)):
                    c2 = pure_supersets[j]
                    
                    # Must be different attribute categories (e.g. location AND jobTitle)
                    if c1[0] == c2[0]: continue

                    intersect_uids = c1[2] & c2[2]
                    if len(intersect_uids) == ent_pop:
                        two_way_and.append({
                            "entitlement_name": ent_name,
                            "population": ent_pop,
                            "match_type": "Cross-Attribute Intersection (AND)",
                            "rule": f"{c1[0]} = '{c1}' AND {c2[0]} = '{c2}'",
                            "components": [f"<b>{c1[0]}</b>='{c1}' ({len(c1[2])})", f"<b>{c2[0]}</b>='{c2}' ({len(c2[2])})"]
                        })

        # OR Unions (2, 3, 4-Way)
        valid_2way_pairs = set()
        if len(pure_subsets) >= 2:
            for i, c1 in enumerate(pure_subsets):
                for j in range(i + 1, len(pure_subsets)):
                    c2 = pure_subsets[j]
                    if (len(c1[2]) + len(c2[2])) < ent_pop: continue
                    if len(c1[2] | c2[2]) == ent_pop:
                        rule_str, m_type = format_union_rule([c1, c2])
                        valid_2way_pairs.add((i, j))
                        two_way_or.append({
                            "entitlement_name": ent_name, "population": ent_pop, "match_type": m_type,
                            "rule": rule_str, "components": [f"<b>{c1[0]}</b>='{c1}' ({len(c1[2])})", f"<b>{c2[0]}</b>='{c2}' ({len(c2[2])})"]
                        })

        valid_3way_tuples = set()
        if len(pure_subsets) >= 3:
            for i, c1 in enumerate(pure_subsets):
                for j in range(i + 1, len(pure_subsets)):
                    if (i, j) in valid_2way_pairs: continue
                    c2 = pure_subsets[j]
                    for k in range(j + 1, len(pure_subsets)):
                        if any(p in valid_2way_pairs for p in [(i,k), (j,k)]): continue
                        c3 = pure_subsets[k]
                        if (len(c1[2]) + len(c2[2]) + len(c3[2])) < ent_pop: continue
                        if len(c1[2] | c2[2] | c3[2]) == ent_pop:
                            valid_3way_tuples.add((i, j, k))
                            rule_str, m_type = format_union_rule([c1, c2, c3])
                            three_way_or.append({
                                "entitlement_name": ent_name, "population": ent_pop, "match_type": m_type,
                                "rule": rule_str, "components": [f"<b>{c1[0]}</b>='{c1}' ({len(c1[2])})", f"<b>{c2[0]}</b>='{c2}' ({len(c2[2])})", f"<b>{c3[0]}</b>='{c3}' ({len(c3[2])})"]
                            })

        if len(pure_subsets) >= 4:
            for i, c1 in enumerate(pure_subsets):
                for j in range(i + 1, len(pure_subsets)):
                    if (i, j) in valid_2way_pairs: continue
                    c2 = pure_subsets[j]
                    for k in range(j + 1, len(pure_subsets)):
                        if any(p in valid_2way_pairs for p in [(i,k), (j,k)]) or (i,j,k) in valid_3way_tuples: continue
                        c3 = pure_subsets[k]
                        for l in range(k + 1, len(pure_subsets)):
                            if any(p in valid_2way_pairs for p in [(i,l), (j,l), (k,l)]) or any(t in valid_3way_tuples for t in [(i,j,l), (i,k,l), (j,k,l)]): continue
                            c4 = pure_subsets[l]
                            if (len(c1[2]) + len(c2[2]) + len(c3[2]) + len(c4[2])) < ent_pop: continue
                            if len(c1[2] | c2[2] | c3[2] | c4[2]) == ent_pop:
                                rule_str, m_type = format_union_rule([c1, c2, c3, c4])
                                four_way_or.append({
                                    "entitlement_name": ent_name, "population": ent_pop, "match_type": m_type,
                                    "rule": rule_str, "components": [f"<b>{c1[0]}</b>='{c1}' ({len(c1[2])})", f"<b>{c2[0]}</b>='{c2}' ({len(c2[2])})", f"<b>{c3[0]}</b>='{c3}' ({len(c3[2])})", f"<b>{c4[0]}</b>='{c4}' ({len(c4[2])})"]
                                })

    single_matches.sort(key=lambda x: x["population"], reverse=True)
    two_way_and.sort(key=lambda x: x["population"], reverse=True)
    two_way_or.sort(key=lambda x: x["population"], reverse=True)
    three_way_or.sort(key=lambda x: x["population"], reverse=True)
    four_way_or.sort(key=lambda x: x["population"], reverse=True)

    return single_matches, two_way_or, three_way_or, four_way_or, two_way_and

if __name__ == "__main__":
    ents, attrs = load_identity_sets()
    s1, s2_or, s3_or, s4_or, s2_and = find_exact_correlations(ents, attrs)
    print(f"📊 SUMMARY: {len(s1)} Single, {len(s2_and)} 2-Way ANDs, {len(s2_or)} 2-Way ORs, {len(s3_or)} 3-Way ORs, {len(s4_or)} 4-Way ORs.")
