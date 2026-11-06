#!/usr/bin/env python3
"""
bundleBuilder - 1, 2, 3, and 4-Attribute Exact Correlation & Union Finder
Discovers:
  1. Single Attribute Exact Matches (Jaccard = 1.0)
  2. 2-Attribute Exact Unions (A OR B)
  3. 3-Attribute Exact Unions (A OR B OR C)
  4. 4-Attribute Exact Unions (A OR B OR C OR D)
"""

import os
import sys
from collections import defaultdict
from itertools import combinations
import mysql.connector
from mysql.connector import Error

# ==============================================================================
# 1. DATABASE CONFIGURATION & FILTERS
# ==============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}

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


# ==============================================================================
# 2. DATA EXTRACTION
# ==============================================================================
def load_identity_sets():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor(dictionary=True)

        print("🔗 Connected to MySQL bundleBuilder.")

        # Entitlements
        print("📦 Extracting Entitlement user sets...")
        cur.execute("""
            SELECT DISTINCT identity_id, entitlement_name 
            FROM (
                SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
                UNION
                SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
            ) t
        """)
        ent_sets = defaultdict(set)
        for row in cur.fetchall():
            ent_sets[row["entitlement_name"].strip()].add(row["identity_id"])

        # Attributes
        print("🏷️ Extracting Attribute user sets...")
        where_clause = "WHERE attribute_value IS NOT NULL AND TRIM(attribute_value) != ''"
        params = []
        if ALLOWED_ATTRIBUTES:
            placeholders = ", ".join(["%s"] * len(ALLOWED_ATTRIBUTES))
            where_clause += f" AND attribute_name IN ({placeholders})"
            params.extend(ALLOWED_ATTRIBUTES)

        cur.execute(f"""
            SELECT identity_id, attribute_name, attribute_value
            FROM Identity_Attributes_Filtered
            {where_clause}
        """, params)

        attr_sets = defaultdict(set)
        for row in cur.fetchall():
            key = (row["attribute_name"].strip(), row["attribute_value"].strip())
            attr_sets[key].add(row["identity_id"])

        cur.close()
        conn.close()

        print(f"✅ Loaded {len(ent_sets):,} Entitlements and {len(attr_sets):,} Distinct Attribute Values.\n")
        return ent_sets, attr_sets

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


# ==============================================================================
# 3. RULE FORMATTING HELPER
# ==============================================================================
def format_union_rule(components):
    """Formats attribute components into clean SQL clauses (e.g. IN or OR)."""
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

    if len(clauses) == 1 and len(grouped[list(grouped.keys())[0]]) > 1:
        match_type = "Same-Attribute Union (OR)"
    else:
        match_type = "Cross-Attribute Union (OR)"

    rule_str = " OR ".join(f"({c})" if " IN " not in c and len(clauses) > 1 else c for c in clauses)
    return rule_str, match_type


# ==============================================================================
# 4. EXACT CORRELATION MINING ENGINE (1, 2, 3, & 4-WAY UNIONS)
# ==============================================================================
def find_exact_correlations(ent_sets, attr_sets):
    single_matches = []
    two_way_matches = []
    three_way_matches = []
    four_way_matches = []

    print("⚡ Searching for 100% Exact Matches (1, 2, 3, and 4-Attribute Unions)...\n")

    for ent_name, ent_uids in ent_sets.items():
        ent_pop = len(ent_uids)
        if ent_pop == 0:
            continue

        # ----------------------------------------------------------------------
        # PASS 1: Single Attribute Exact Matches
        # ----------------------------------------------------------------------
        pure_subsets = []

        for (a_name, a_val), a_uids in attr_sets.items():
            a_pop = len(a_uids)

            if a_pop == ent_pop and a_uids == ent_uids:
                single_matches.append({
                    "entitlement_name": ent_name,
                    "population": ent_pop,
                    "rule": f"{a_name} = '{a_val}'",
                })
            elif a_pop < ent_pop and a_uids.issubset(ent_uids):
                pure_subsets.append((a_name, a_val, a_uids))

        # ----------------------------------------------------------------------
        # PASS 2: 2-Attribute Exact Unions (A OR B)
        # ----------------------------------------------------------------------
        valid_2way_pairs = set()

        if len(pure_subsets) >= 2:
            for i in range(len(pure_subsets)):
                c1 = pure_subsets[i]
                for j in range(i + 1, len(pure_subsets)):
                    c2 = pure_subsets[j]

                    # Sum-bound pruning
                    if (len(c1[2]) + len(c2[2])) < ent_pop:
                        continue

                    union_uids = c1[2] | c2[2]
                    if len(union_uids) == ent_pop:
                        rule_str, m_type = format_union_rule([c1, c2])
                        valid_2way_pairs.add((i, j))
                        two_way_matches.append({
                            "entitlement_name": ent_name,
                            "population": ent_pop,
                            "match_type": m_type,
                            "rule": rule_str,
                            "components": [f"{c1[0]}='{c1}' ({len(c1[2])})", f"{c2[0]}='{c2}' ({len(c2[2])})"],
                        })

        # ----------------------------------------------------------------------
        # PASS 3: 3-Attribute Exact Unions (A OR B OR C)
        # ----------------------------------------------------------------------
        valid_3way_tuples = set()
        
        if len(pure_subsets) >= 3:
            for i in range(len(pure_subsets)):
                c1 = pure_subsets[i]
                for j in range(i + 1, len(pure_subsets)):
                    c2 = pure_subsets[j]
                    if (i, j) in valid_2way_pairs:
                        continue

                    for k in range(j + 1, len(pure_subsets)):
                        c3 = pure_subsets[k]
                        if (i, k) in valid_2way_pairs or (j, k) in valid_2way_pairs:
                            continue

                        # Sum-bound pruning
                        if (len(c1[2]) + len(c2[2]) + len(c3[2])) < ent_pop:
                            continue

                        union_uids = c1[2] | c2[2] | c3[2]
                        if len(union_uids) == ent_pop:
                            valid_3way_tuples.add((i, j, k))
                            rule_str, m_type = format_union_rule([c1, c2, c3])
                            three_way_matches.append({
                                "entitlement_name": ent_name,
                                "population": ent_pop,
                                "match_type": m_type,
                                "rule": rule_str,
                                "components": [
                                    f"{c1[0]}='{c1}' ({len(c1[2])})",
                                    f"{c2[0]}='{c2}' ({len(c2[2])})",
                                    f"{c3[0]}='{c3}' ({len(c3[2])})",
                                ],
                            })

        # ----------------------------------------------------------------------
        # PASS 4: 4-Attribute Exact Unions (A OR B OR C OR D)
        # ----------------------------------------------------------------------
        if len(pure_subsets) >= 4:
            for i in range(len(pure_subsets)):
                c1 = pure_subsets[i]
                for j in range(i + 1, len(pure_subsets)):
                    c2 = pure_subsets[j]
                    if (i, j) in valid_2way_pairs: continue

                    for k in range(j + 1, len(pure_subsets)):
                        c3 = pure_subsets[k]
                        if any(pair in valid_2way_pairs for pair in [(i,k), (j,k)]): continue
                        if (i, j, k) in valid_3way_tuples: continue

                        for l in range(k + 1, len(pure_subsets)):
                            c4 = pure_subsets[l]
                            
                            # Minimality Checks (skip if any subset combo already matches)
                            if any(pair in valid_2way_pairs for pair in [(i,l), (j,l), (k,l)]): continue
                            if any(tri in valid_3way_tuples for tri in [(i,j,l), (i,k,l), (j,k,l)]): continue
                            
                            # Sum-bound Pruning
                            if (len(c1[2]) + len(c2[2]) + len(c3[2]) + len(c4[2])) < ent_pop: continue

                            union_uids = c1[2] | c2[2] | c3[2] | c4[2]
                            if len(union_uids) == ent_pop:
                                rule_str, m_type = format_union_rule([c1, c2, c3, c4])
                                four_way_matches.append({
                                    "entitlement_name": ent_name,
                                    "population": ent_pop,
                                    "match_type": m_type,
                                    "rule": rule_str,
                                    "components": [
                                        f"{c1[0]}='{c1}' ({len(c1[2])})",
                                        f"{c2[0]}='{c2}' ({len(c2[2])})",
                                        f"{c3[0]}='{c3}' ({len(c3[2])})",
                                        f"{c4[0]}='{c4}' ({len(c4[2])})"
                                    ]
                                })

    # Sort descending by population size
    single_matches.sort(key=lambda x: x["population"], reverse=True)
    two_way_matches.sort(key=lambda x: x["population"], reverse=True)
    three_way_matches.sort(key=lambda x: x["population"], reverse=True)
    four_way_matches.sort(key=lambda x: x["population"], reverse=True)

    return single_matches, two_way_matches, three_way_matches, four_way_matches


# ==============================================================================
# 5. OUTPUT REPORTING
# ==============================================================================
def print_results(single_matches, two_way_matches, three_way_matches, four_way_matches):
    print("=" * 95)
    print("1. SINGLE-ATTRIBUTE EXACT MATCHES (Jaccard = 1.0000)")
    print("=" * 95)
    if single_matches:
        for idx, m in enumerate(single_matches, 1):
            print(f"[{idx:02d}] Entitlement: '{m['entitlement_name']}'")
            print(f"     Population:  {m['population']} identities")
            print(f"     Exact Rule:  {m['rule']}")
            print("-" * 95)
    else:
        print("None found.")

    print("\n" + "=" * 95)
    print("2. TWO-ATTRIBUTE EXACT UNIONS (S_E == S_A1 ∪ S_A2)")
    print("=" * 95)
    if two_way_matches:
        for idx, m in enumerate(two_way_matches, 1):
            print(f"[{idx:02d}] Entitlement: '{m['entitlement_name']}'")
            print(f"     Population:  {m['population']} identities")
            print(f"     Type:        {m['match_type']}")
            print(f"     Exact Rule:  {m['rule']}")
            print(f"     Components:  {', '.join(m['components'])}")
            print("-" * 95)
    else:
        print("None found.")

    print("\n" + "=" * 95)
    print("3. THREE-ATTRIBUTE EXACT UNIONS (S_E == S_A1 ∪ S_A2 ∪ S_A3)")
    print("=" * 95)
    if three_way_matches:
        for idx, m in enumerate(three_way_matches, 1):
            print(f"[{idx:02d}] Entitlement: '{m['entitlement_name']}'")
            print(f"     Population:  {m['population']} identities")
            print(f"     Type:        {m['match_type']}")
            print(f"     Exact Rule:  {m['rule']}")
            print(f"     Components:  {', '.join(m['components'])}")
            print("-" * 95)
    else:
        print("None found.")

    print("\n" + "=" * 95)
    print("4. FOUR-ATTRIBUTE EXACT UNIONS (S_E == S_A1 ∪ S_A2 ∪ S_A3 ∪ S_A4)")
    print("=" * 95)
    if four_way_matches:
        for idx, m in enumerate(four_way_matches, 1):
            print(f"[{idx:02d}] Entitlement: '{m['entitlement_name']}'")
            print(f"     Population:  {m['population']} identities")
            print(f"     Type:        {m['match_type']}")
            print(f"     Exact Rule:  {m['rule']}")
            print(f"     Components:  {', '.join(m['components'])}")
            print("-" * 95)
    else:
        print("None found.")

    print(f"\n📊 SUMMARY: {len(single_matches)} Single Matches, {len(two_way_matches)} 2-Way Unions, {len(three_way_matches)} 3-Way Unions, {len(four_way_matches)} 4-Way Unions.")


# ==============================================================================
# ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    ents, attrs = load_identity_sets()
    singles, two_ways, three_ways, four_ways = find_exact_correlations(ents, attrs)
    print_results(singles, two_ways, three_ways, four_ways)
