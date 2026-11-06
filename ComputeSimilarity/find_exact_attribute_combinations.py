#!/usr/bin/env python3
"""
bundleBuilder - Exact (100% Jaccard = 1.0000) Attribute Combination Finder
Discovers exact birthright HR rules and exact multi-entitlement Access Profiles (SUGGESTED_AP).
"""

import os
import sys
from collections import defaultdict
from itertools import combinations
from typing import List, Set, Dict, Tuple
import mysql.connector
from mysql.connector import Error

# ==============================================================================
# DYNAMIC SYSTEM PATH RESOLUTION & CENTRAL IMPORTS
# ==============================================================================
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Utils.config import (
    open_connection,
    close_db_connection,
    MINING_LIMITS,
    ALLOWED_ATTRIBUTES,
    HIERARCHY_FAMILIES,
    MAX_CONTAINMENT_RATIO,
)


def in_same_hierarchy_family(attr_name_1: str, attr_name_2: str) -> bool:
    a1, a2 = str(attr_name_1).strip().lower(), str(attr_name_2).strip().lower()
    if a1 == a2:
        return False
    for family in HIERARCHY_FAMILIES:
        if a1 in family and a2 in family:
            return True
    return False


def is_hierarchical_or_redundant_pair(c1: Tuple, c2: Tuple) -> bool:
    name1, val1, uids1 = c1
    name2, val2, uids2 = c2

    if in_same_hierarchy_family(name1, name2):
        return True

    min_pop = min(len(uids1), len(uids2))
    if min_pop == 0:
        return True

    intersection_size = len(uids1 & uids2)
    if str(name1).strip().lower() != str(name2).strip().lower():
        containment = intersection_size / min_pop
        if containment >= MAX_CONTAINMENT_RATIO:
            return True

    return False


def canonical_sort_components(components):
    return sorted(components, key=lambda item: (str(item[0]).strip().lower(), str(item).strip().lower()))


def format_or_rule(components):
    sorted_comps = canonical_sort_components(components)
    grouped = defaultdict(list)
    for n, v, u in sorted_comps: 
        val_str = str(v)
        if val_str not in grouped[str(n)]:
            grouped[str(n)].append(val_str)

    clauses = []
    for a_name in sorted(grouped.keys(), key=lambda k: k.lower()):
        vals = sorted(grouped[a_name], key=lambda v: v.lower())
        if len(vals) == 1: 
            clauses.append(f"{a_name} = '{vals[0]}'")
        else: 
            clauses.append(f"{a_name} IN ({', '.join(f'''{v}''' for v in vals)})")

    match_type = "Same-Attribute Union (OR)" if len(clauses) == 1 else "Cross-Attribute Union (OR)"
    return " OR ".join(f"({cl})" if " IN " not in cl and len(clauses) > 1 else cl for cl in clauses), match_type


def format_and_rule(components):
    sorted_comps = canonical_sort_components(components)
    clauses = [f"{str(n)} = '{str(v)}'" for n, v, u in sorted_comps]
    return " AND ".join(clauses), "Intersection (AND)"


def load_identity_sets():
    db_connection = None
    cursor = None
    try:
        db_connection = open_connection()
        if not db_connection:
            print("❌ Could not establish database connection.")
            sys.exit(1)

        cursor = db_connection.cursor(dictionary=True)
        print("🔗 Connected to MySQL database.")

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

        cursor.execute("SELECT id, entitlement_name FROM entitlements")
        ent_id_map = {row["entitlement_name"].strip(): row["id"] for row in cursor.fetchall()}

        return ent_sets, attr_sets, ent_id_map

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    finally:
        if db_connection:
            close_db_connection(db_connection, cursor)


def find_exact_correlations(ent_sets, attr_sets, ent_id_map):
    min_pop = MINING_LIMITS["min_pop"]
    max_pop = MINING_LIMITS["max_pop"]
    batch_size = MINING_LIMITS["batch_size"]
    batch_index = MINING_LIMITS["batch_index"]

    max_label = max_pop if max_pop is not None else "Unlimited"
    print(f"⚡ Running Exact Engine (Population Range: {min_pop} to {max_label})...")

    filtered_entitlements = []
    for ent_name, uids in ent_sets.items():
        ent_pop = len(uids)
        if ent_pop < min_pop:
            continue
        if max_pop is not None and ent_pop > max_pop:
            continue
        if ent_name in ent_id_map:
            filtered_entitlements.append((ent_name, uids, ent_pop))

    filtered_entitlements.sort(key=lambda x: (-x, x[0].lower()))
    total_matching = len(filtered_entitlements)

    if batch_size is not None and batch_size > 0:
        start_idx = batch_index * batch_size
        end_idx = start_idx + batch_size
        filtered_entitlements = filtered_entitlements[start_idx:end_idx]

    evaluated_ent_ids = [ent_id_map[item[0]] for item in filtered_entitlements]
    cohort_to_ents = defaultdict(list)
    for ent_name, uids, ent_pop in filtered_entitlements:
        cohort_to_ents[frozenset(uids)].append(ent_name)

    discovered_rules = {}
    correlated_ent_ids = set()

    for ent_cohort, ent_names in cohort_to_ents.items():
        ent_uids = set(ent_cohort)
        ent_pop = len(ent_uids)
        overlap_candidates = []
        for (a_name, a_val), a_uids in attr_sets.items():
            inter = len(ent_uids & a_uids)
            if inter > 0:
                overlap_candidates.append((inter, a_name, a_val, a_uids))

        overlap_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = [(a_name, a_val, a_uids) for _, a_name, a_val, a_uids in overlap_candidates[:25]]

        matched_hr_rule = False

        def register_exact_match(components, formatter_func, way_prefix):
            nonlocal matched_hr_rule
            sorted_comps = canonical_sort_components(components)
            rule_str, m_type = formatter_func(sorted_comps)
            raw_attrs = [(str(n), str(v)) for n, v, u in sorted_comps]

            if way_prefix == 1:
                r_type = "SINGLE"
            else:
                op_tag = m_type.split("(")[-1].replace(")", "")
                r_type = f"{way_prefix}_WAY_{op_tag}"

            if rule_str not in discovered_rules:
                discovered_rules[rule_str] = {
                    "rule_type": r_type,
                    "rule_name": f"Exact {r_type}: {rule_str}"[:500],
                    "rule_logic": rule_str,
                    "population_size": ent_pop,
                    "identities": ent_uids,
                    "attributes": raw_attrs,
                    "entitlements": set(),
                }
            for e_name in ent_names:
                e_id = ent_id_map[e_name]
                discovered_rules[rule_str]["entitlements"].add(e_id)
                correlated_ent_ids.add(e_id)

            matched_hr_rule = True

        for c1 in top_candidates:
            name1, val1, uids1 = c1
            if uids1 == ent_uids:
                register_exact_match([c1], format_or_rule, 1)

        if not matched_hr_rule:
            for c1, c2 in combinations(top_candidates, 2):
                if is_hierarchical_or_redundant_pair(c1, c2):
                    continue
                name1, val1, uids1 = c1
                name2, val2, uids2 = c2

                if (uids1 | uids2) == ent_uids and uids1 != ent_uids and uids2 != ent_uids:
                    register_exact_match([c1, c2], format_or_rule, 2)

                if name1 != name2 and (uids1 & uids2) == ent_uids:
                    register_exact_match([c1, c2], format_and_rule, 2)

        if not matched_hr_rule:
            for c1, c2, c3 in combinations(top_candidates, 3):
                if (
                    is_hierarchical_or_redundant_pair(c1, c2)
                    or is_hierarchical_or_redundant_pair(c1, c3)
                    or is_hierarchical_or_redundant_pair(c2, c3)
                ):
                    continue
                name1, val1, uids1 = c1
                name2, val2, uids2 = c2
                name3, val3, uids3 = c3

                if (uids1 | uids2 | uids3) == ent_uids:
                    register_exact_match([c1, c2, c3], format_or_rule, 3)

                if name1 != name2 and name1 != name3 and name2 != name3:
                    if (uids1 & uids2 & uids3) == ent_uids:
                        register_exact_match([c1, c2, c3], format_and_rule, 3)

        if not matched_hr_rule and len(ent_names) >= 2:
            sorted_ents = sorted(ent_names)
            ap_key = f"SUGGESTED_AP::{sorted_ents[0]} (+{len(sorted_ents)-1} more)"
            discovered_rules[ap_key] = {
                "rule_type": "SUGGESTED_AP",
                "rule_name": f"Suggested Access Profile ({len(sorted_ents)} Entitlements, {ent_pop} Users)"[:500],
                "rule_logic": "PURE_ENTITLEMENT_BUNDLE",
                "population_size": ent_pop,
                "identities": ent_uids,
                "attributes": [],
                "entitlements": {ent_id_map[e] for e in sorted_ents},
            }

    return list(discovered_rules.values()), correlated_ent_ids, evaluated_ent_ids


def persist_exact_rules_to_mysql(rules_list, correlated_ent_ids, evaluated_ent_ids):
    clear_all = MINING_LIMITS["clear_all_discovered"]
    if not evaluated_ent_ids and not clear_all:
        print("⚠️ No entitlements were in scope. Skipping database write.")
        return

    db_connection = None
    cursor = None
    try:
        db_connection = open_connection()
        if not db_connection:
            sys.exit(1)

        cursor = db_connection.cursor()

        if clear_all:
            print("\n💾 Clearing ALL old exact rules before saving...")
            cursor.execute("DELETE FROM Suggested_Rule_Identities")
            cursor.execute("DELETE FROM Suggested_Rule_Entitlements")
            cursor.execute("DELETE FROM Suggested_Rule_Attributes")
            cursor.execute("DELETE FROM Suggested_Discovered_Rules")
            cursor.execute("UPDATE entitlements SET is_correlated = 0")
        else:
            chunk_del = 1000
            stale_rule_ids = set()
            for i in range(0, len(evaluated_ent_ids), chunk_del):
                batch_eids = evaluated_ent_ids[i:i + chunk_del]
                placeholders = ", ".join(["%s"] * len(batch_eids))
                cursor.execute(
                    f"SELECT DISTINCT rule_id FROM Suggested_Rule_Entitlements WHERE entitlement_id IN ({placeholders})",
                    tuple(batch_eids)
                )
                for row in cursor.fetchall():
                    stale_rule_ids.add(row[0])

            if stale_rule_ids:
                stale_list = list(stale_rule_ids)
                for i in range(0, len(stale_list), chunk_del):
                    batch_rids = stale_list[i:i + chunk_del]
                    placeholders = ", ".join(["%s"] * len(batch_rids))
                    cursor.execute(
                        f"DELETE FROM Suggested_Discovered_Rules WHERE id IN ({placeholders})",
                        tuple(batch_rids)
                    )

        sql_rule = """
            INSERT INTO Suggested_Discovered_Rules
            (rule_type, rule_name, rule_logic, population_size, entitlement_count, jaccard_score)
            VALUES (%s, %s, %s, %s, %s, 1.0000)
        """
        sql_attr = "INSERT INTO Suggested_Rule_Attributes (rule_id, attribute_name, attribute_value) VALUES (%s, %s, %s)"
        sql_ent  = "INSERT INTO Suggested_Rule_Entitlements (rule_id, entitlement_id, jaccard_score) VALUES (%s, %s, 1.0000)"
        sql_uid  = "INSERT INTO Suggested_Rule_Identities (rule_id, identity_id) VALUES (%s, %s)"

        attrs_batch = []
        ents_batch = []
        uids_batch = []

        for rule in rules_list:
            ent_ids = sorted(rule["entitlements"])
            cursor.execute(sql_rule, (
                rule["rule_type"],
                rule["rule_name"][:500],
                rule["rule_logic"],
                rule["population_size"],
                len(ent_ids),
            ))
            rule_id = cursor.lastrowid

            for a_name, a_val in rule["attributes"]:
                attrs_batch.append((rule_id, str(a_name)[:250], str(a_val)[:250]))

            for e_id in ent_ids:
                ents_batch.append((rule_id, e_id))

            for uid in rule["identities"]:
                uids_batch.append((rule_id, str(uid)[:250]))

        if attrs_batch:
            cursor.executemany(sql_attr, attrs_batch)
        if ents_batch:
            cursor.executemany(sql_ent, ents_batch)
        if uids_batch:
            chunk_size = 10000
            for i in range(0, len(uids_batch), chunk_size):
                cursor.executemany(sql_uid, uids_batch[i:i + chunk_size])

        if correlated_ent_ids:
            chunk_upd = 1000
            corr_list = list(correlated_ent_ids)
            for i in range(0, len(corr_list), chunk_upd):
                batch_corr = corr_list[i:i + chunk_upd]
                placeholders = ", ".join(["%s"] * len(batch_corr))
                cursor.execute(
                    f"UPDATE entitlements SET is_correlated = 1 WHERE id IN ({placeholders})",
                    tuple(batch_corr)
                )

        db_connection.commit()
        print(f"✅ Success! {len(rules_list):,} exact rules persisted into MySQL.")

    except Error as e:
        print(f"❌ Database persistence error: {e}")
        sys.exit(1)
    finally:
        if db_connection:
            close_db_connection(db_connection, cursor)


def run_exact_mining():
    ents, attrs, ent_id_map = load_identity_sets()
    rules, correlated_ids, evaluated_ent_ids = find_exact_correlations(ents, attrs, ent_id_map)
    persist_exact_rules_to_mysql(rules, correlated_ids, evaluated_ent_ids)
    return rules


if __name__ == "__main__":
    run_exact_mining()
