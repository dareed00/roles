#!/usr/bin/env python3
"""
bundleBuilder - Fuzzy/Near-Match Correlation Finder
Discovers rules using a Dynamic Population-Scaled Threshold.
"""

import os
import sys
from collections import defaultdict
from itertools import combinations
from typing import Tuple
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


def is_valid_near_match(intersection_size, union_size):
    if union_size == 0:
        return False
    exceptions = union_size - intersection_size
    jaccard = intersection_size / union_size

    if union_size < 10:
        return exceptions <= 2
    elif union_size < 50:
        return jaccard >= 0.80 or exceptions <= 5
    else:
        calculated_threshold = 0.85 + ((union_size - 50) // 20) * 0.01
        dynamic_threshold = min(calculated_threshold, 0.98)
        return jaccard >= dynamic_threshold


def find_fuzzy_correlations(ent_sets, attr_sets):
    min_pop = MINING_LIMITS["min_pop"]
    max_pop = MINING_LIMITS["max_pop"]
    batch_size = MINING_LIMITS["batch_size"]
    batch_index = MINING_LIMITS["batch_index"]

    max_label = max_pop if max_pop is not None else "Unlimited"
    print(f"⚡ Running Fuzzy Engine (Population Filter: {min_pop} to {max_label})...")

    filtered_entitlements = []
    for ent_name, ent_uids in ent_sets.items():
        ent_pop = len(ent_uids)
        if ent_pop < min_pop:
            continue
        if max_pop is not None and ent_pop > max_pop:
            continue
        filtered_entitlements.append((ent_name, ent_uids, ent_pop))

    filtered_entitlements.sort(key=lambda x: (-x, x[0].lower()))
    total_matching = len(filtered_entitlements)

    if batch_size is not None and batch_size > 0:
        start_idx = batch_index * batch_size
        end_idx = start_idx + batch_size
        filtered_entitlements = filtered_entitlements[start_idx:end_idx]

    results_by_entitlement = {}
    evaluated_entitlement_names = [item[0] for item in filtered_entitlements]

    for ent_name, ent_uids, ent_pop in filtered_entitlements:
        overlap_candidates = []
        for (a_name, a_val), a_uids in attr_sets.items():
            intersection = len(ent_uids & a_uids)
            if intersection > 0:
                overlap_candidates.append((intersection, a_name, a_val, a_uids))
        
        overlap_candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = [(a_name, a_val, a_uids) for _, a_name, a_val, a_uids in overlap_candidates[:25]]

        valid_rules = []

        def evaluate_and_store(rule_uids, components, formatter_func):
            intersect = len(ent_uids & rule_uids)
            union = len(ent_uids | rule_uids)
            if is_valid_near_match(intersect, union):
                jaccard = intersect / union
                missing_access_uids = rule_uids - ent_uids 
                extra_access_uids = ent_uids - rule_uids   
                
                sorted_components = canonical_sort_components(components)
                rule_str, m_type = formatter_func(sorted_components)
                raw_attrs = [(str(n), str(v)) for n, v, u in sorted_components]
                
                valid_rules.append({
                    "jaccard": jaccard,
                    "rule": rule_str,
                    "type": f"{len(sorted_components)}_WAY_{m_type.split('(')[-1].replace(')','')}",
                    "missing_count": len(missing_access_uids),
                    "extra_count": len(extra_access_uids),
                    "missing_uids": list(missing_access_uids),
                    "extra_uids": list(extra_access_uids),
                    "rule_population": len(rule_uids),
                    "raw_attributes": raw_attrs
                })

        for c1 in top_candidates:
            name1, val1, uids1 = c1
            evaluate_and_store(uids1, [c1], format_or_rule)

        for c1, c2 in combinations(top_candidates, 2):
            if is_hierarchical_or_redundant_pair(c1, c2):
                continue
            name1, val1, uids1 = c1
            name2, val2, uids2 = c2
            
            evaluate_and_store(uids1 | uids2, [c1, c2], format_or_rule)
            if name1 != name2:
                evaluate_and_store(uids1 & uids2, [c1, c2], format_and_rule)

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
            
            evaluate_and_store(uids1 | uids2 | uids3, [c1, c2, c3], format_or_rule)
            if name1 != name2 and name1 != name3 and name2 != name3:
                evaluate_and_store(uids1 & uids2 & uids3, [c1, c2, c3], format_and_rule)

        if valid_rules:
            valid_rules.sort(key=lambda x: (x["jaccard"], - (x["missing_count"] + x["extra_count"])), reverse=True)
            
            seen_logic = set()
            top_5 = []
            for r in valid_rules:
                if r["rule"] not in seen_logic:
                    seen_logic.add(r["rule"])
                    top_5.append(r)
                if len(top_5) == 5:
                    break
                    
            results_by_entitlement[ent_name] = {
                "population": ent_pop,
                "top_candidates": top_5
            }

    return results_by_entitlement, evaluated_entitlement_names


def persist_fuzzy_rules_to_mysql(results_dict, ent_id_map, evaluated_entitlements):
    clear_all = MINING_LIMITS["clear_all_discovered"]
    if not evaluated_entitlements and not clear_all:
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
            print("\n💾 Clearing ALL old fuzzy rules before saving...")
            cursor.execute("DELETE FROM Fuzzy_Rule_Exceptions")
            cursor.execute("DELETE FROM Fuzzy_Rule_Attributes")
            cursor.execute("DELETE FROM Fuzzy_Discovered_Rules")
        else:
            chunk_del = 1000
            for i in range(0, len(evaluated_entitlements), chunk_del):
                batch_names = evaluated_entitlements[i:i + chunk_del]
                placeholders = ", ".join(["%s"] * len(batch_names))
                cursor.execute(
                    f"DELETE FROM Fuzzy_Discovered_Rules WHERE entitlement_name IN ({placeholders})",
                    tuple(batch_names)
                )

        sql_rule = """
            INSERT INTO Fuzzy_Discovered_Rules 
            (entitlement_name, entitlement_id, rule_rank, rule_type, rule_logic, 
             jaccard_score, target_population, rule_population, missing_users_count, extra_users_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        sql_attr = "INSERT INTO Fuzzy_Rule_Attributes (rule_id, attribute_name, attribute_value) VALUES (%s, %s, %s)"
        sql_exc  = "INSERT INTO Fuzzy_Rule_Exceptions (rule_id, identity_id, exception_type) VALUES (%s, %s, %s)"

        attrs_batch = []
        exceptions_batch = []
        rule_count = 0

        for ent_name, data in results_dict.items():
            ent_id = ent_id_map.get(ent_name)
            target_pop = data["population"]

            for rank_idx, rule in enumerate(data["top_candidates"], start=1):
                cursor.execute(sql_rule, (
                    ent_name[:250],
                    ent_id,
                    rank_idx,
                    rule["type"],
                    rule["rule"],
                    float(rule["jaccard"]),
                    target_pop,
                    rule["rule_population"],
                    rule["missing_count"],
                    rule["extra_count"]
                ))
                rule_id = cursor.lastrowid
                rule_count += 1

                for a_name, a_val in rule["raw_attributes"]:
                    attrs_batch.append((rule_id, str(a_name)[:250], str(a_val)[:250]))

                for uid in rule["missing_uids"]:
                    exceptions_batch.append((rule_id, str(uid)[:250], 'MISSING_ACCESS'))
                    
                for uid in rule["extra_uids"]:
                    exceptions_batch.append((rule_id, str(uid)[:250], 'EXTRA_ACCESS'))

        if attrs_batch:
            cursor.executemany(sql_attr, attrs_batch)
        if exceptions_batch:
            chunk_size = 10000
            for i in range(0, len(exceptions_batch), chunk_size):
                chunk = exceptions_batch[i:i + chunk_size]
                cursor.executemany(sql_exc, chunk)

        db_connection.commit()
        print(f"✅ Success! {rule_count:,} fuzzy rule candidates persisted into MySQL.")

    except Error as e:
        print(f"❌ Database persistence error: {e}")
        sys.exit(1)
    finally:
        if db_connection:
            close_db_connection(db_connection, cursor)


def run_fuzzy_mining():
    ents, attrs, ent_id_map = load_identity_sets()
    results, evaluated_ents = find_fuzzy_correlations(ents, attrs)
    persist_fuzzy_rules_to_mysql(results, ent_id_map, evaluated_ents)
    return results


if __name__ == "__main__":
    run_fuzzy_mining()
