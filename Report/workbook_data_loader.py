#!/usr/bin/env python3
"""
RoleMiner - Staging Data Extraction & Exception Roster Engine
File: Scripts/Report/workbook_data_loader.py
"""

import os
import sys
from collections import defaultdict
from mysql.connector import Error

# Ensure Scripts root is on sys.path for Utils.config
scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)

from Utils.config import open_connection, close_db_connection
from Report.workbook_helpers import parse_hire_date, order_roles_with_dynamic_subtiers


def load_staging_data():
    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            print("❌ Failed to connect to MySQL database.")
            sys.exit(1)
        cur = conn.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.")

        print("📊 Indexing global entitlement user assignments...")
        cur.execute("""
            SELECT identity_id, entitlement_name 
            FROM (
                SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
                UNION
                SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
            ) t
        """)
        ent_users_map = defaultdict(set)
        for row in cur.fetchall():
            ent_users_map[row["entitlement_name"].strip().lower()].add(str(row["identity_id"]).strip())

        print("🛠️ Loading IT Roles and indexing permissions...")
        cur.execute("""
            SELECT
                id, it_role_name, approval_status, already_defined,
                deploy_target, approved_role_name, owner_id, owner_name,
                primary_source, description, entitlements_count,
                full_holders_count, partial_holders_count, bundle_cohesion_score,
                admin_notes,
                created_timestamp AS found_date,
                reviewed_timestamp AS decision_date
            FROM Suggested_IT_Roles
            WHERE approval_status != 'IGNORED'
            ORDER BY already_defined ASC, entitlements_count DESC, full_holders_count DESC
        """)
        it_roles = cur.fetchall()

        cur.execute("""
            SELECT
                sire.it_role_id, sire.entitlement_id, sire.entitlement_name,
                sire.source_name, sire.assignment_count,
                COALESCE(sire.already_defined, sire.already_in_role, 0) AS already_defined,
                COALESCE(sire.already_defined, sire.already_in_role, 0) AS already_in_role,
                sire.is_included,
                sir.created_timestamp AS found_date,
                sire.reviewed_timestamp AS decision_date
            FROM Suggested_IT_Role_Entitlements sire
            LEFT JOIN Suggested_IT_Roles sir ON sire.it_role_id = sir.id
            ORDER BY sire.it_role_id, sire.assignment_count DESC
        """)
        it_ents = cur.fetchall()

        cur.execute("SELECT it_role_id, identity_id, adoption_status FROM Suggested_IT_Role_Identities")
        it_role_all_users = defaultdict(set)
        it_role_full_users = defaultdict(set)
        for row in cur.fetchall():
            it_id = row["it_role_id"]
            u_id = str(row["identity_id"]).strip()
            it_role_all_users[it_id].add(u_id)
            if row["adoption_status"] == "FULL_HOLDER":
                it_role_full_users[it_id].add(u_id)

        it_role_meta = {}
        it_role_ents_set = defaultdict(set)
        it_role_ents_dict = defaultdict(dict)
        ent_to_it_roles_list = defaultdict(list)
        for r in it_roles:
            it_id = r["id"]
            it_role_meta[it_id] = {
                "id_str": f"ITR-{it_id:04d}",
                "name": r["it_role_name"],
                "source": r["primary_source"],
                "total_ents": r["entitlements_count"]
            }

        for e in it_ents:
            it_id = e["it_role_id"]
            e_name = e["entitlement_name"].strip()
            e_norm = e_name.lower()
            it_role_ents_set[it_id].add(e_norm)
            it_role_ents_dict[it_id][e_norm] = e_name
            ent_to_it_roles_list[e_norm].append({
                "it_role_id": it_id,
                "it_role_id_str": f"ITR-{it_id:04d}",
                "it_role_name": it_role_meta.get(it_id, {}).get("name", "Unknown"),
                "total_ents": it_role_meta.get(it_id, {}).get("total_ents", 1)
            })

        print("🏛️ Loading Business Roles and computing IT Role Overlaps...")
        cur.execute("""
            SELECT 
                id, role_name, assignment_rule, target_population,
                exact_entitlements_count, fuzzy_entitlements_count, total_entitlements_count, avg_jaccard_score,
                already_defined, approval_status, resolution_action, hierarchy_type,
                parent_role_id, dimension_attribute, dimension_value, approved_role_name,
                owner_id, owner_name, admin_notes,
                created_timestamp AS found_date,
                reviewed_timestamp AS decision_date
            FROM Suggested_Roles
            WHERE approval_status != 'IGNORED'
            ORDER BY already_defined ASC, total_entitlements_count DESC, target_population DESC
        """)
        raw_biz_roles = cur.fetchall()
        biz_roles = order_roles_with_dynamic_subtiers(raw_biz_roles)

        cur.execute("""
            SELECT
                sre.role_id, sre.entitlement_id, sre.entitlement_name, sre.source_name,
                sre.match_type, sre.jaccard_score, sre.missing_users_count, sre.extra_users_count,
                COALESCE(sre.already_defined, sre.already_in_role, 0) AS already_defined,
                COALESCE(sre.already_defined, sre.already_in_role, 0) AS already_in_role,
                sre.is_included,
                sr.created_timestamp AS found_date,
                sre.reviewed_timestamp AS decision_date
            FROM Suggested_Role_Entitlements sre
            LEFT JOIN Suggested_Roles sr ON sre.role_id = sr.id
            WHERE sr.approval_status != 'IGNORED'
            ORDER BY sre.role_id, sre.match_type ASC, sre.jaccard_score DESC
        """)
        biz_ents = cur.fetchall()

        biz_role_ents_set = defaultdict(set)
        for e in biz_ents:
            b_id = e["role_id"]
            e_norm = e["entitlement_name"].strip().lower()
            biz_role_ents_set[b_id].add(e_norm)

        biz_to_it_overlaps = defaultdict(dict)
        it_to_biz_overlaps = defaultdict(dict)
        overlap_matrix_records = []
        for b in biz_roles:
            b_id = b["id"]
            b_name = b["role_name"]
            b_set = biz_role_ents_set[b_id]
            b_total = len(b_set)
            for it_id, it_set in it_role_ents_set.items():
                if not it_set:
                    continue
                shared = b_set & it_set
                if not shared:
                    continue
                it_total = len(it_set)
                containment_pct = (len(shared) / it_total) * 100.0
                missing_from_biz = [it_role_ents_dict[it_id][en] for en in (it_set - shared)]
                overlap_info = {
                    "containment_pct": containment_pct,
                    "shared_count": len(shared),
                    "total_it": it_total,
                    "total_biz": b_total,
                    "missing_permissions": missing_from_biz
                }
                biz_to_it_overlaps[b_id][it_id] = overlap_info
                it_to_biz_overlaps[it_id][b_id] = overlap_info

                if containment_pct >= 50.0:
                    it_info = it_role_meta.get(it_id, {})
                    rec = (
                        "🟢 100% FULL CONTAINMENT: Replace loose entitlements with IT Role"
                        if containment_pct >= 99.9
                        else f"🟡 PARTIAL OVERLAP ({len(shared)}/{it_total} perms): Consider adding missing permissions"
                    )
                    overlap_matrix_records.append({
                        "biz_id_str": f"BR-{b_id:04d}",
                        "biz_name": b_name,
                        "it_id_str": it_info.get("id_str", f"ITR-{it_id:04d}"),
                        "it_name": it_info.get("name", "Unknown IT Role"),
                        "it_source": it_info.get("source", "Unknown"),
                        "containment_pct": containment_pct,
                        "shared_count": len(shared),
                        "it_total": it_total,
                        "biz_total": b_total,
                        "recommendation": rec,
                        "missing_str": ", ".join(missing_from_biz) if missing_from_biz else "None (100% Complete)"
                    })
        overlap_matrix_records.sort(key=lambda x: (-x["containment_pct"], -x["shared_count"]))

        print("👤 Indexing Identity Profiles...")
        cur.execute("""
            SELECT identity_id, attribute_name, attribute_value 
            FROM Identity_Attributes_Filtered
            WHERE attribute_value IS NOT NULL AND TRIM(attribute_value) != ''
        """)
        raw_attrs = cur.fetchall()

        user_attr_map = defaultdict(dict)
        for row in raw_attrs:
            uid = str(row["identity_id"]).strip()
            name_key = str(row["attribute_name"]).strip().lower()
            user_attr_map[uid][name_key] = str(row["attribute_value"]).strip()

        identity_profiles = {}
        lookup_owners = [
            {"uid": "IAM-Admins", "name": "IAM Security Team", "title": "Governance Workgroup", "dept": "Information Security", "email": "iam-admins@company.com", "type": "Workgroup"},
            {"uid": "Role-Governance-Committee", "name": "Role Governance Board", "title": "Access Review Board", "dept": "Risk & Compliance", "email": "role-governance@company.com", "type": "Workgroup"},
        ]

        for uid, a in user_attr_map.items():
            first = a.get("firstname", a.get("first_name", ""))
            last = a.get("lastname", a.get("last_name", ""))
            full_name = f"{first} {last}".strip() or a.get("displayname", uid)
            title = a.get("jobtitle", a.get("title", "Unknown Title"))
            dept = a.get("department", a.get("dept", "General"))
            email = a.get("email", a.get("mail", f"{uid}@company.com"))
            is_mgr = str(a.get("ismanager", "FALSE")).upper() in ("TRUE", "1", "YES")
            state_raw = a.get("identitystate", a.get("status", a.get("state", "ACTIVE"))).upper()

            hire_date_raw = a.get("startdate", a.get("hiredate", a.get("start_date", a.get("hire_date", None))))
            days_ago, _ = parse_hire_date(hire_date_raw)

            prof = {
                "uid": uid,
                "name": full_name,
                "title": title,
                "department": dept,
                "email": email,
                "state_clean": "ACTIVE" if state_raw in ("ACTIVE", "TRUE", "ENABLED") else state_raw,
                "days_ago": days_ago
            }
            identity_profiles[uid] = prof

            title_lower = title.lower()
            if is_mgr or any(w in title_lower for w in ["manager", "director", "lead", "head", "vp", "chief", "officer", "supervisor", "admin"]):
                lookup_owners.append({"uid": uid, "name": full_name, "title": title, "dept": dept, "email": email, "type": "Identity"})

        seen_names = set()
        deduped_owners = []
        for o in lookup_owners:
            if o["name"] not in seen_names:
                seen_names.add(o["name"])
                deduped_owners.append(o)
        deduped_owners.sort(key=lambda x: (0 if x["type"] == "Workgroup" else 1, x["name"]))

        print("🎯 Fetching Business Role Missing & Extra Identity Exceptions...")
        cur.execute("""
            SELECT 
                r.id as role_id,
                fdr.entitlement_name,
                fre.identity_id,
                fre.exception_type
            FROM Suggested_Roles r
            JOIN Fuzzy_Discovered_Rules fdr ON r.assignment_rule = fdr.rule_logic AND fdr.rule_rank = 1
            JOIN Fuzzy_Rule_Exceptions fre ON fdr.id = fre.rule_id
        """)
        exception_rows = cur.fetchall()

        biz_missing_users = defaultdict(list)
        biz_extra_users = defaultdict(list)
        for row in exception_rows:
            r_id = row["role_id"]
            e_norm = row["entitlement_name"].strip().lower()
            uid = str(row["identity_id"]).strip()
            prof = identity_profiles.get(uid, {"uid": uid, "name": uid, "title": "Unknown", "department": "Unknown", "state_clean": "UNKNOWN", "days_ago": None})

            if row["exception_type"] == "MISSING_ACCESS":
                biz_missing_users[(r_id, e_norm)].append(prof)
            elif row["exception_type"] == "EXTRA_ACCESS":
                biz_extra_users[(r_id, e_norm)].append(prof)

        print("🎯 Computing IT Role Entitlement Exceptions...")
        it_ent_missing_users = defaultdict(list)
        it_ent_extra_users = defaultdict(list)
        for e in it_ents:
            it_id = e["it_role_id"]
            e_norm = e["entitlement_name"].strip().lower()
            holders = ent_users_map.get(e_norm, set())
            cluster_users = it_role_all_users.get(it_id, set())
            missing_uids = cluster_users - holders
            extra_uids = holders - cluster_users
            for uid in missing_uids:
                prof = identity_profiles.get(uid, {"uid": uid, "name": uid, "title": "Unknown", "department": "Unknown", "state_clean": "UNKNOWN", "days_ago": None})
                it_ent_missing_users[(it_id, e_norm)].append(prof)
            for uid in extra_uids:
                prof = identity_profiles.get(uid, {"uid": uid, "name": uid, "title": "Unknown", "department": "Unknown", "state_clean": "UNKNOWN", "days_ago": None})
                it_ent_extra_users[(it_id, e_norm)].append(prof)

        return (
            biz_roles, biz_ents, it_roles, it_ents, deduped_owners,
            ent_to_it_roles_list, biz_to_it_overlaps, it_to_biz_overlaps,
            it_role_meta, overlap_matrix_records,
            biz_missing_users, biz_extra_users,
            it_ent_missing_users, it_ent_extra_users
        )
    except Error as e:
        print(f"❌ Database error loading staging data: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)
