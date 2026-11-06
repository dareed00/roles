#!/usr/bin/env python3
"""
bundleBuilder - Suggested Business Role Object Synthesizer
Merges Exact HR Matches and Rank-1 Fuzzy Matches into cohesive Business Role Objects.
Filters out:
  • SUGGESTED_AP (which belong strictly in IT Roles)
  • Declined entitlements in Role_Entitlement_Exclusions
  • Ignored or Separated roles in Ignored_Suggested_Roles
"""

import os
import sys
import re
from collections import defaultdict
import mysql.connector
from mysql.connector import Error

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Utils.config import (
    open_connection,
    close_db_connection,
    MINING_LIMITS,
    DB_CONFIG,
)


def canonicalize_attributes(raw_attrs):
    if not raw_attrs:
        return ()
    cleaned = [
        (str(attr_name).strip().lower(), str(attr_val).strip().lower())
        for attr_name, attr_val in raw_attrs
    ]
    return tuple(sorted(cleaned, key=lambda x: (x[0], x)))


def canonicalize_rule_string(rule_str):
    if not rule_str:
        return ""
    rule_str = rule_str.strip()
    if " AND " in rule_str.upper():
        op = " AND "
        clauses = re.split(r'\s+AND\s+', rule_str, flags=re.IGNORECASE)
    elif " OR " in rule_str.upper():
        op = " OR "
        clauses = re.split(r'\s+OR\s+', rule_str, flags=re.IGNORECASE)
    else:
        return rule_str.strip()

    cleaned_clauses = sorted(c.strip(" ()") for c in clauses if c.strip())
    return op.join(cleaned_clauses)


def pluralize_title(title):
    t = title.strip()
    if t.endswith("s") or t.endswith("sh") or t.endswith("ch") or t.endswith("x") or t.endswith("z"):
        return f"{t}es"
    if t.endswith("y") and not t[-2].lower() in "aeiou":
        return f"{t[:-1]}ies"
    return f"{t}s"


def generate_smart_role_name(raw_attrs, rule_type):
    if not raw_attrs:
        return "Suggested Business Role"

    if len(raw_attrs) == 1:
        attr_name, attr_val = raw_attrs[0]
        attr_name = attr_name.lower()

        if attr_name in ("jobtitle", "title"):
            return f"All {pluralize_title(attr_val)}"
        elif attr_name in ("department", "dept"):
            return f"All {attr_val} Department Employees"
        elif attr_name in ("location", "city", "site"):
            return f"{attr_val} Location Users"
        elif attr_name in ("country", "countrycode"):
            return f"All {attr_val} Based Employees"
        elif attr_name == "ismanager" and str(attr_val).upper() in ("TRUE", "1", "YES"):
            return "All People Managers"
        elif attr_name == "type":
            return f"All {attr_val} Workers"
        elif attr_name == "division":
            return f"All {attr_val} Division Employees"
        else:
            return f"All {attr_val} {attr_name.title()} Users"

    if "AND" in rule_type.upper():
        attr_dict = {name.lower(): val for name, val in raw_attrs}
        if "department" in attr_dict and "location" in attr_dict:
            return f"All {attr_dict['department']} Employees in {attr_dict['location']}"
        if "jobtitle" in attr_dict and "location" in attr_dict:
            return f"{attr_dict['location']} {pluralize_title(attr_dict['jobtitle'])}"
        if "jobtitle" in attr_dict and "country" in attr_dict:
            return f"{attr_dict['country']} {pluralize_title(attr_dict['jobtitle'])}"
        if "jobtitle" in attr_dict and "ismanager" in attr_dict and str(attr_dict["ismanager"]).upper() in ("TRUE", "1", "YES"):
            return f"{attr_dict['jobtitle']} People Managers"
        if "department" in attr_dict and "ismanager" in attr_dict and str(attr_dict["ismanager"]).upper() in ("TRUE", "1", "YES"):
            return f"{attr_dict['department']} Department Managers"
        if "jobtitle" in attr_dict and "type" in attr_dict:
            return f"All {attr_dict['type']} {pluralize_title(attr_dict['jobtitle'])}"

        clauses = [f"{v} {k.title()}" for k, v in attr_dict.items()]
        return " & ".join(clauses) + " Users"

    if "OR" in rule_type.upper():
        grouped = defaultdict(list)
        for a_name, a_val in raw_attrs:
            grouped[a_name.lower()].append(a_val)
            
        if len(grouped) == 1:
            attr_name = list(grouped.keys())[0]
            vals = list(grouped.values())[0]
            val_str = " & ".join(vals[:3])
            if len(vals) > 3:
                val_str += f" & {len(vals)-3} More"

            if attr_name in ("location", "city"):
                return f"All {val_str} Location Users"
            elif attr_name in ("jobtitle", "title"):
                return f"All {val_str} Staff"
            elif attr_name == "department":
                return f"All {val_str} Department Employees"
            else:
                return f"All {val_str} {attr_name.title()} Users"
        else:
            return f"Cross-Attribute Role ({len(raw_attrs)} Criteria)"

    return f"Role for {raw_attrs[0]}"


def load_all_mined_rules():
    min_pop = MINING_LIMITS["min_pop"]
    max_pop = MINING_LIMITS["max_pop"]

    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            sys.exit(1)

        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT entitlement_name, MAX(source_name) as source_name FROM entitlements GROUP BY entitlement_name")
        source_map = {row["entitlement_name"]: row["source_name"] for row in cur.fetchall()}

        exact_where = ["r.rule_type != 'SUGGESTED_AP'", "r.population_size >= %s"]
        exact_params = [min_pop]
        if max_pop is not None:
            exact_where.append("r.population_size <= %s")
            exact_params.append(max_pop)

        cur.execute(f"""
            SELECT 
                r.id as rule_id, r.rule_type, r.rule_logic, r.population_size,
                e.entitlement_id, ent.entitlement_name, e.jaccard_score
            FROM Suggested_Discovered_Rules r
            JOIN Suggested_Rule_Entitlements e ON r.id = e.rule_id
            JOIN entitlements ent ON e.entitlement_id = ent.id
            WHERE {' AND '.join(exact_where)}
        """, tuple(exact_params))
        exact_rows = cur.fetchall()

        cur.execute("SELECT rule_id, attribute_name, attribute_value FROM Suggested_Rule_Attributes")
        exact_attrs = defaultdict(list)
        for row in cur.fetchall():
            exact_attrs[row["rule_id"]].append((row["attribute_name"], row["attribute_value"]))

        cur.execute("SELECT rule_id, identity_id FROM Suggested_Rule_Identities")
        exact_identities = defaultdict(set)
        for row in cur.fetchall():
            exact_identities[row["rule_id"]].add(row["identity_id"])

        fuzzy_where = ["r.rule_rank = 1", "r.target_population >= %s"]
        fuzzy_params = [min_pop]
        if max_pop is not None:
            fuzzy_where.append("r.target_population <= %s")
            fuzzy_params.append(max_pop)

        cur.execute(f"""
            SELECT 
                r.id as rule_id, r.entitlement_name, r.entitlement_id, r.rule_type, r.rule_logic,
                r.jaccard_score, r.target_population, r.missing_users_count, r.extra_users_count
            FROM Fuzzy_Discovered_Rules r
            WHERE {' AND '.join(fuzzy_where)}
        """, tuple(fuzzy_params))
        fuzzy_rows = cur.fetchall()

        cur.execute("SELECT rule_id, attribute_name, attribute_value FROM Fuzzy_Rule_Attributes")
        fuzzy_attrs = defaultdict(list)
        for row in cur.fetchall():
            fuzzy_attrs[row["rule_id"]].append((row["attribute_name"], row["attribute_value"]))

        # 3. Fetch Entitlement Exclusions
        try:
            cur.execute("SELECT DISTINCT TRIM(role_name) as role_name, TRIM(entitlement_name) as entitlement_name, TRIM(source_name) as source_name FROM Role_Entitlement_Exclusions")
            exclusions = {(row["role_name"].lower(), row["entitlement_name"].lower(), row["source_name"].lower()) for row in cur.fetchall()}
        except Exception:
            exclusions = set()

        # 4. Fetch Ignored & Separated Role Signatures from Ignored_Suggested_Roles
        ignored_rules = set()
        ignored_names = set()
        try:
            cur.execute("SELECT assignment_rule_signature, role_name FROM Ignored_Suggested_Roles")
            for row in cur.fetchall():
                if row["assignment_rule_signature"]:
                    ignored_rules.add(canonicalize_rule_string(row["assignment_rule_signature"]).lower())
                    ignored_rules.add(row["assignment_rule_signature"].strip().lower())
                if row["role_name"]:
                    ignored_names.add(row["role_name"].strip().lower())
            print(f"🚫 Loaded {len(ignored_rules):,} suppressed role signatures from Ignored_Suggested_Roles.")
        except Exception:
            pass

        return exact_rows, exact_attrs, exact_identities, fuzzy_rows, fuzzy_attrs, source_map, exclusions, ignored_rules, ignored_names

    except Error as e:
        print(f"❌ Database error loading mined rules: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)


def synthesize_roles(exact_rows, exact_attrs, exact_identities, fuzzy_rows, fuzzy_attrs, source_map, exclusions, ignored_rules, ignored_names):
    min_pop = MINING_LIMITS["min_pop"]
    max_pop = MINING_LIMITS["max_pop"]
    batch_size = MINING_LIMITS["batch_size"]
    batch_index = MINING_LIMITS["batch_index"]

    max_label = max_pop if max_pop is not None else "Unlimited"
    print(f"⚙️ Synthesizing Business Roles (Segment: {min_pop} to {max_label})...")
    roles_by_logic = {}

    for row in exact_rows:
        raw_logic = row["rule_logic"].strip()
        r_id = row["rule_id"]
        raw_attributes = exact_attrs.get(r_id, [])

        canonical_key = canonicalize_attributes(raw_attributes)
        if not canonical_key:
            canonical_key = canonicalize_rule_string(raw_logic)

        standard_logic = canonicalize_rule_string(raw_logic)

        if canonical_key not in roles_by_logic:
            sorted_attrs = sorted(raw_attributes, key=lambda x: (str(x[0]).lower(), str(x).lower()))
            role_name = generate_smart_role_name(sorted_attrs, row["rule_type"])
            
            roles_by_logic[canonical_key] = {
                "role_name": role_name,
                "rule_logic": standard_logic,
                "rule_type": row["rule_type"],
                "raw_attributes": sorted_attrs,
                "target_population": row["population_size"],
                "identities": set(exact_identities.get(r_id, set())),
                "entitlements": []
            }
        else:
            roles_by_logic[canonical_key]["identities"].update(exact_identities.get(r_id, set()))
            roles_by_logic[canonical_key]["target_population"] = len(roles_by_logic[canonical_key]["identities"])

        ent_name = row["entitlement_name"]
        src_name = source_map.get(ent_name, "Unknown")
        role_name = roles_by_logic[canonical_key]["role_name"]

        if (role_name.lower(), ent_name.lower(), src_name.lower()) in exclusions:
            continue

        existing_ents = {e["entitlement_name"] for e in roles_by_logic[canonical_key]["entitlements"]}
        if ent_name not in existing_ents:
            roles_by_logic[canonical_key]["entitlements"].append({
                "entitlement_id": row["entitlement_id"],
                "entitlement_name": ent_name,
                "source_name": src_name,
                "match_type": "EXACT",
                "jaccard_score": float(row["jaccard_score"]),
                "missing_count": 0,
                "extra_count": 0
            })

    for row in fuzzy_rows:
        raw_logic = row["rule_logic"].strip()
        r_id = row["rule_id"]
        raw_attributes = fuzzy_attrs.get(r_id, [])

        canonical_key = canonicalize_attributes(raw_attributes)
        if not canonical_key:
            canonical_key = canonicalize_rule_string(raw_logic)

        standard_logic = canonicalize_rule_string(raw_logic)

        if canonical_key not in roles_by_logic:
            sorted_attrs = sorted(raw_attributes, key=lambda x: (str(x[0]).lower(), str(x).lower()))
            role_name = generate_smart_role_name(sorted_attrs, row["rule_type"])

            roles_by_logic[canonical_key] = {
                "role_name": role_name,
                "rule_logic": standard_logic,
                "rule_type": row["rule_type"],
                "raw_attributes": sorted_attrs,
                "target_population": row["target_population"],
                "identities": set(),
                "entitlements": []
            }

        ent_name = row["entitlement_name"]
        src_name = source_map.get(ent_name, "Unknown")
        role_name = roles_by_logic[canonical_key]["role_name"]

        if (role_name.lower(), ent_name.lower(), src_name.lower()) in exclusions:
            continue

        existing_ents = {e["entitlement_name"] for e in roles_by_logic[canonical_key]["entitlements"]}
        if ent_name not in existing_ents:
            roles_by_logic[canonical_key]["entitlements"].append({
                "entitlement_id": row["entitlement_id"],
                "entitlement_name": ent_name,
                "source_name": src_name,
                "match_type": "FUZZY",
                "jaccard_score": float(row["jaccard_score"]),
                "missing_count": row["missing_users_count"],
                "extra_count": row["extra_users_count"]
            })

    synthesized_roles = []
    suppressed_roles_cnt = 0

    for canon_key, role in roles_by_logic.items():
        r_logic = role["rule_logic"].strip()
        r_name = role["role_name"].strip()

        # Check against Ignored_Suggested_Roles (both IGNORED and SEPARATED roles)
        if r_logic.lower() in ignored_rules or r_name.lower() in ignored_names:
            print(f"   🚫 Suppressing previously Ignored/Separated role: '{r_name}' ({r_logic})")
            suppressed_roles_cnt += 1
            continue

        ents = role["entitlements"]
        if not ents:
            continue

        pop = role["target_population"]
        if pop < min_pop:
            continue
        if max_pop is not None and pop > max_pop:
            continue

        exact_cnt = sum(1 for e in ents if e["match_type"] == "EXACT")
        fuzzy_cnt = sum(1 for e in ents if e["match_type"] == "FUZZY")
        avg_jaccard = sum(e["jaccard_score"] for e in ents) / len(ents) if ents else 1.0

        description = f"Automated Business Role granting {len(ents)} entitlements ({exact_cnt} exact, {fuzzy_cnt} fuzzy) for users matching: {r_logic}."

        synthesized_roles.append({
            "role_name": r_name,
            "description": description,
            "assignment_rule": r_logic,
            "target_population": pop,
            "exact_count": exact_cnt,
            "fuzzy_count": fuzzy_cnt,
            "total_count": len(ents),
            "avg_jaccard": avg_jaccard,
            "entitlements": ents,
            "identities": role["identities"]
        })

    if suppressed_roles_cnt:
        print(f"   ✓ Filtered out {suppressed_roles_cnt:,} roles found in Ignored_Suggested_Roles.")

    synthesized_roles.sort(key=lambda x: (x["total_count"], x["target_population"]), reverse=True)

    if batch_size is not None and batch_size > 0:
        start_idx = batch_index * batch_size
        end_idx = start_idx + batch_size
        synthesized_roles = synthesized_roles[start_idx:end_idx]

    return synthesized_roles


def persist_suggested_roles(roles_list):
    clear_all = MINING_LIMITS["clear_all_discovered"]
    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            sys.exit(1)

        cur = conn.cursor()
        if clear_all or MINING_LIMITS["batch_size"] is None:
            cur.execute("DELETE FROM Suggested_Role_Identities")
            cur.execute("DELETE FROM Suggested_Role_Entitlements")
            cur.execute("DELETE FROM Suggested_Roles")
        else:
            role_names = [r["role_name"][:250] for r in roles_list]
            if role_names:
                placeholders = ", ".join(["%s"] * len(role_names))
                cur.execute(f"DELETE FROM Suggested_Roles WHERE role_name IN ({placeholders})", tuple(role_names))

        sql_role = """
            INSERT INTO Suggested_Roles 
            (role_name, description, assignment_rule, target_population, 
             exact_entitlements_count, fuzzy_entitlements_count, total_entitlements_count, avg_jaccard_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        sql_ent = """
            INSERT INTO Suggested_Role_Entitlements 
            (role_id, entitlement_id, entitlement_name, source_name, match_type, jaccard_score, missing_users_count, extra_users_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        sql_id = "INSERT INTO Suggested_Role_Identities (role_id, identity_id, status) VALUES (%s, %s, %s)"

        ents_batch = []
        ids_batch = []

        for role in roles_list:
            cur.execute(sql_role, (
                role["role_name"][:250],
                role["description"],
                role["assignment_rule"],
                role["target_population"],
                role["exact_count"],
                role["fuzzy_count"],
                role["total_count"],
                float(role["avg_jaccard"])
            ))
            role_id = cur.lastrowid

            for e in role["entitlements"]:
                ents_batch.append((
                    role_id,
                    e["entitlement_id"],
                    str(e["entitlement_name"])[:250],
                    str(e["source_name"])[:250],
                    e["match_type"],
                    float(e["jaccard_score"]),
                    e["missing_count"],
                    e["extra_count"]
                ))

            for uid in role["identities"]:
                ids_batch.append((role_id, str(uid)[:250], "ELIGIBLE"))

        if ents_batch:
            cur.executemany(sql_ent, ents_batch)
        if ids_batch:
            chunk_size = 10000
            for i in range(0, len(ids_batch), chunk_size):
                cur.executemany(sql_id, ids_batch[i:i + chunk_size])

        conn.commit()
        print(f"✅ Success! {len(roles_list):,} Business Roles persisted.")

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)


def run_business_role_synthesis():
    exact_rows, exact_attrs, exact_identities, fuzzy_rows, fuzzy_attrs, source_map, exclusions, ignored_rules, ignored_names = load_all_mined_rules()
    roles = synthesize_roles(exact_rows, exact_attrs, exact_identities, fuzzy_rows, fuzzy_attrs, source_map, exclusions, ignored_rules, ignored_names)
    persist_suggested_roles(roles)
    return roles


if __name__ == "__main__":
    run_business_role_synthesis()
