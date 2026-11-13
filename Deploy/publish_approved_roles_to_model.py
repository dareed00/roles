#!/usr/bin/env python3
"""
bundleBuilder - Production Publishing & Audit Engine (With Existing-Role Split Merge)
Promotes approved business roles and access profiles from Suggested_* to ApprovedRoleModel_*,
matching existing production roles by canonical assignment_rule first so split roles
merge directly into existing ApprovedRoleModel_Roles without creating duplicates.
"""

import os
import sys
import re
import uuid
from collections import defaultdict
import mysql.connector
from mysql.connector import Error

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Utils.config import open_connection, close_db_connection, DB_CONFIG


def parse_multi_value_clauses(assignment_rule_str):
    if not assignment_rule_str:
        return []
    rule = str(assignment_rule_str).strip()
    pairs = []

    in_matches = re.finditer(r"([A-Za-z0-9_\-]+)\s+IN\s*\(([^)]+)\)", rule, flags=re.IGNORECASE)
    for m in in_matches:
        attr_name = m.group(1).strip()
        for rv in m.group(2).split(","):
            clean_v = rv.strip().strip("'\"")
            if clean_v and (attr_name, clean_v) not in pairs:
                pairs.append((attr_name, clean_v))

    eq_matches = re.finditer(r"([A-Za-z0-9_\-]+)\s*=\s*'([^']+)'", rule, flags=re.IGNORECASE)
    for m in eq_matches:
        pair = (m.group(1).strip(), m.group(2).strip())
        if pair not in pairs:
            pairs.append(pair)

    return pairs


def build_canonical_rule_key(assignment_rule_str):
    if not assignment_rule_str:
        return ()
    clauses = parse_multi_value_clauses(assignment_rule_str)
    if not clauses:
        return ("RAW", str(assignment_rule_str).strip().lower())
    norm_clauses = tuple(sorted((a.strip().lower(), v.strip().lower()) for a, v in clauses))
    if len(norm_clauses) == 1:
        return ("SINGLE", norm_clauses)
    rule_upper = str(assignment_rule_str).upper()
    op = "AND" if (" AND " in rule_upper and " IN " not in rule_upper) else "OR"
    return (op, norm_clauses)


def publish_approved_role_model():
    event_id = str(uuid.uuid4())[:8]
    print(f"🚀 Initiating Role Model Publication & Audit Stream [Event ID: {event_id}]...")

    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            print("❌ Failed to connect to MySQL database.")
            sys.exit(1)

        cur = conn.cursor(dictionary=True)

        # ----------------------------------------------------------------------
        # 1. PUBLISH APPROVED BUSINESS ROLES & HANDLE SPLIT MERGES / RETIREMENTS
        # ----------------------------------------------------------------------
        print("🏛️ [1/2] Publishing Approved Business Roles & Merging Split Roles...")

        cur.execute("""
            SELECT 
                id, role_name, approval_status, resolution_action, hierarchy_type,
                parent_role_id, dimension_attribute, dimension_value,
                deploy_target, approved_role_name, owner_id, owner_name,
                description, assignment_rule, target_population, total_entitlements_count
            FROM Suggested_Roles
            WHERE approval_status IN ('APPROVED', 'ACCEPT', 'SPLIT_RETIRED')
        """)
        staged_roles = cur.fetchall()

        # Fetch all staged entitlements (both included and explicitly excluded)
        cur.execute("""
            SELECT 
                sre.role_id, sre.entitlement_id, sre.entitlement_name,
                sre.source_name, sre.match_type, sre.is_included
            FROM Suggested_Role_Entitlements sre
            JOIN Suggested_Roles sr ON sre.role_id = sr.id
            WHERE sr.approval_status IN ('APPROVED', 'ACCEPT')
        """)
        staged_ents_by_role = defaultdict(list)
        excluded_ent_names_by_role = defaultdict(set)
        for e in cur.fetchall():
            if e["is_included"] == 1:
                staged_ents_by_role[e["role_id"]].append(e)
            else:
                excluded_ent_names_by_role[e["role_id"]].add(str(e["entitlement_name"]).strip().lower())

        # Load existing production ApprovedRoleModel_Roles (indexed by ID AND by Canonical Rule Key)
        cur.execute("""
            SELECT 
                id, name, description, assignment_rule, owner_id, owner_name,
                deploy_target, status, version_number, hierarchy_type, parent_role_id,
                dimension_attribute, dimension_value
            FROM ApprovedRoleModel_Roles
        """)
        existing_prod_by_id = {}
        existing_prod_by_rule = {}
        for r in cur.fetchall():
            existing_prod_by_id[r["id"]] = r
            canon_key = build_canonical_rule_key(r["assignment_rule"])
            if canon_key:
                existing_prod_by_rule[canon_key] = r

        cur.execute("""
            SELECT role_id, entitlement_id, entitlement_name, source_name, match_type
            FROM ApprovedRoleModel_RoleEntitlements
        """)
        existing_prod_ents_by_role = defaultdict(dict)
        for pe in cur.fetchall():
            existing_prod_ents_by_role[pe["role_id"]][str(pe["entitlement_name"]).strip().lower()] = pe

        roles_published = 0
        roles_updated = 0
        roles_retired = 0
        audit_records = []

        for sr in staged_roles:
            candidate_id_str = f"BR-{int(sr['id']):04d}"
            rule = sr["assignment_rule"]
            canon_key = build_canonical_rule_key(rule)

            # Match existing production role by Canonical Rule FIRST, then by candidate ID
            matched_prod_role = existing_prod_by_rule.get(canon_key) or existing_prod_by_id.get(candidate_id_str)
            role_id_str = matched_prod_role["id"] if matched_prod_role else candidate_id_str

            # Handle SPLIT_RETIRED composite roles
            if sr["approval_status"] == "SPLIT_RETIRED":
                if matched_prod_role and matched_prod_role["status"] == "ACTIVE":
                    new_ver = int(matched_prod_role["version_number"] or 1) + 1
                    cur.execute("""
                        UPDATE ApprovedRoleModel_Roles
                        SET status = 'DEACTIVATED',
                            version_number = %s,
                            deactivated_timestamp = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (new_ver, role_id_str))
                    cur.execute("DELETE FROM ApprovedRoleModel_RoleEntitlements WHERE role_id = %s", (role_id_str,))
                    audit_records.append((
                        event_id, "BUSINESS_ROLE", role_id_str, matched_prod_role["name"], new_ver,
                        "DEACTIVATE", "status", "ACTIVE", "DEACTIVATED",
                        "Admin Reviewer", "Composite role split into constituent single-attribute roles"
                    ))
                    roles_retired += 1
                # Clean up the retired composite role from Suggested_Roles
                cur.execute("DELETE FROM Suggested_Roles WHERE id = %s", (sr["id"],))
                continue

            final_name = (sr["approved_role_name"] or (matched_prod_role["name"] if matched_prod_role else sr["role_name"])).strip()
            desc = sr["description"]
            owner_id = sr["owner_id"] or (matched_prod_role["owner_id"] if matched_prod_role else "IAM-Admins")
            owner_name = sr["owner_name"] or (matched_prod_role["owner_name"] if matched_prod_role else "IAM Security Team")
            deploy_target = sr["deploy_target"] or "BOTH"
            pop = int(sr["target_population"] or 0)
            h_type = sr.get("hierarchy_type") or "STANDARD"
            p_id = f"BR-{int(sr['parent_role_id']):04d}" if sr.get("parent_role_id") else None
            dim_attr = sr.get("dimension_attribute")
            dim_val = sr.get("dimension_value")

            staged_ents = staged_ents_by_role.get(sr["id"], [])
            explicitly_excluded_names = excluded_ent_names_by_role.get(sr["id"], set())

            if matched_prod_role:
                current_ver = int(matched_prod_role["version_number"] or 1)
                has_structural_change = False

                if matched_prod_role["name"] != final_name:
                    has_structural_change = True
                    audit_records.append((
                        event_id, "BUSINESS_ROLE", role_id_str, final_name, current_ver + 1,
                        "UPDATE", "name", matched_prod_role["name"], final_name, "Admin Reviewer", "Role renamed in review"
                    ))
                if matched_prod_role["assignment_rule"] != rule:
                    has_structural_change = True
                    audit_records.append((
                        event_id, "BUSINESS_ROLE", role_id_str, final_name, current_ver + 1,
                        "MODIFY_RULE", "assignment_rule", matched_prod_role["assignment_rule"], rule, "Admin Reviewer", "Membership rule adjusted"
                    ))

                # Additive Merge of Entitlements into Existing Role:
                # Start with existing production entitlements (minus any explicitly excluded in this review)
                merged_ents_map = {}
                existing_ent_map = existing_prod_ents_by_role.get(role_id_str, {})
                for e_key, old_e in existing_ent_map.items():
                    if e_key not in explicitly_excluded_names:
                        merged_ents_map[e_key] = old_e
                    else:
                        has_structural_change = True
                        audit_records.append((
                            event_id, "ROLE_ENTITLEMENT", role_id_str, final_name, current_ver + 1,
                            "REMOVE_ENTITLEMENT", "entitlement", f"{old_e['entitlement_name']} ({old_e['source_name']})", None,
                            "Admin Reviewer", "Entitlement removed or split out during review"
                        ))

                # Add all included staging entitlements (including newly SPLIT entitlements!)
                for ce in staged_ents:
                    e_key = str(ce["entitlement_name"]).strip().lower()
                    if e_key not in existing_ent_map:
                        has_structural_change = True
                        audit_records.append((
                            event_id, "ROLE_ENTITLEMENT", role_id_str, final_name, current_ver + 1,
                            "ADD_ENTITLEMENT", "entitlement", None, f"{ce['entitlement_name']} ({ce['source_name']})",
                            "Admin Reviewer", "Entitlement added / merged into existing role"
                        ))
                    merged_ents_map[e_key] = ce

                new_ver = current_ver + 1 if has_structural_change else current_ver

                cur.execute("""
                    UPDATE ApprovedRoleModel_Roles
                    SET name = %s,
                        description = %s,
                        assignment_rule = %s,
                        owner_id = %s,
                        owner_name = %s,
                        deploy_target = %s,
                        status = 'ACTIVE',
                        version_number = %s,
                        target_population = %s,
                        hierarchy_type = %s,
                        parent_role_id = %s,
                        dimension_attribute = %s,
                        dimension_value = %s,
                        last_modified_timestamp = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    final_name, desc, rule, owner_id, owner_name, deploy_target,
                    new_ver, pop, h_type, p_id, dim_attr, dim_val, role_id_str
                ))
                roles_updated += 1
                final_ents_to_write = list(merged_ents_map.values())
            else:
                cur.execute("""
                    INSERT INTO ApprovedRoleModel_Roles
                    (id, name, description, assignment_rule, owner_id, owner_name,
                     deploy_target, status, version_number, target_population,
                     hierarchy_type, parent_role_id, dimension_attribute, dimension_value,
                     created_timestamp, activated_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 1, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    role_id_str, final_name, desc, rule, owner_id, owner_name,
                    deploy_target, pop, h_type, p_id, dim_attr, dim_val
                ))

                audit_records.append((
                    event_id, "BUSINESS_ROLE", role_id_str, final_name, 1,
                    "CREATE", "role", None, f"Created {h_type} role '{final_name}' with {len(staged_ents)} entitlements",
                    "Admin Reviewer", "Promoted from suggested role model"
                ))

                for ce in staged_ents:
                    audit_records.append((
                        event_id, "ROLE_ENTITLEMENT", role_id_str, final_name, 1,
                        "ADD_ENTITLEMENT", "entitlement", None, f"{ce['entitlement_name']} ({ce['source_name']})",
                        "Admin Reviewer", "Initial entitlement provisioning"
                    ))

                roles_published += 1
                final_ents_to_write = staged_ents

            # Persist the merged entitlements for this role
            cur.execute("DELETE FROM ApprovedRoleModel_RoleEntitlements WHERE role_id = %s", (role_id_str,))
            if final_ents_to_write:
                sql_armre = """
                    INSERT IGNORE INTO ApprovedRoleModel_RoleEntitlements
                    (role_id, role_name, entitlement_id, entitlement_name, source_name, match_type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                armre_batch = [
                    (
                        role_id_str,
                        final_name,
                        str(ce["entitlement_id"] or ce["entitlement_name"])[:255],
                        str(ce["entitlement_name"])[:255],
                        str(ce["source_name"] or "Unknown")[:255],
                        str(ce.get("match_type") or "APPROVED_BIRTHRIGHT")[:50],
                    )
                    for ce in final_ents_to_write
                ]
                cur.executemany(sql_armre, armre_batch)

        print(f"   ✓ Published {roles_published:,} net-new roles, merged/updated {roles_updated:,} existing roles, and retired {roles_retired:,} split composite roles.")

        # ----------------------------------------------------------------------
        # 2. PUBLISH APPROVED IT ROLES / ACCESS PROFILES
        # ----------------------------------------------------------------------
        print("🛠️ [2/2] Publishing Approved IT Roles / Access Profiles & Auditing...")

        cur.execute("""
            SELECT 
                id, it_role_name, approval_status, deploy_target, approved_role_name,
                owner_id, owner_name, primary_source, description, entitlements_count
            FROM Suggested_IT_Roles
            WHERE approval_status IN ('APPROVED', 'ACCEPT')
        """)
        staged_it_roles = cur.fetchall()

        cur.execute("""
            SELECT 
                sire.it_role_id, sire.entitlement_id, sire.entitlement_name, sire.source_name
            FROM Suggested_IT_Role_Entitlements sire
            JOIN Suggested_IT_Roles sir ON sire.it_role_id = sir.id
            WHERE sir.approval_status IN ('APPROVED', 'ACCEPT')
              AND sire.is_included = 1
        """)
        staged_it_ents_by_role = defaultdict(list)
        for ie in cur.fetchall():
            staged_it_ents_by_role[ie["it_role_id"]].append(ie)

        cur.execute("SELECT id, name, version_number FROM ApprovedRoleModel_AccessProfiles")
        existing_prod_aps = {r["id"]: r for r in cur.fetchall()}

        cur.execute("SELECT access_profile_id, entitlement_id FROM ApprovedRoleModel_AccessProfileEntitlements")
        existing_prod_ap_ents = {(r["access_profile_id"], str(r["entitlement_id"])) for r in cur.fetchall()}

        aps_published = 0
        aps_updated = 0

        for sir in staged_it_roles:
            ap_id_str = f"ITR-{int(sir['id']):04d}"
            final_ap_name = (sir["approved_role_name"] or sir["it_role_name"]).strip()
            desc = sir["description"]
            prim_source = sir["primary_source"] or "Enterprise"
            owner_id = sir["owner_id"]
            owner_name = sir["owner_name"] or "IAM Security Team"
            deploy_target = sir["deploy_target"] or "BOTH"

            current_ap_ents = staged_it_ents_by_role.get(sir["id"], [])

            if ap_id_str in existing_prod_aps:
                prod_ap = existing_prod_aps[ap_id_str]
                cur_ver = int(prod_ap["version_number"] or 1)
                has_ap_change = False

                if prod_ap["name"] != final_ap_name:
                    has_ap_change = True
                    audit_records.append((
                        event_id, "IT_ROLE", ap_id_str, final_ap_name, cur_ver + 1,
                        "UPDATE", "name", prod_ap["name"], final_ap_name, "Admin Reviewer", "Access Profile renamed"
                    ))

                for ce in current_ap_ents:
                    e_id_str = str(ce["entitlement_id"] or ce["entitlement_name"])
                    if (ap_id_str, e_id_str) not in existing_prod_ap_ents:
                        has_ap_change = True
                        audit_records.append((
                            event_id, "AP_ENTITLEMENT", ap_id_str, final_ap_name, cur_ver + 1,
                            "ADD_ENTITLEMENT", "entitlement", None, f"{ce['entitlement_name']} ({ce['source_name']})",
                            "Admin Reviewer", "Entitlement mapped to Access Profile"
                        ))

                new_ap_ver = cur_ver + 1 if has_ap_change else cur_ver

                cur.execute("""
                    UPDATE ApprovedRoleModel_AccessProfiles
                    SET name = %s,
                        description = %s,
                        primary_source = %s,
                        owner_id = %s,
                        owner_name = %s,
                        deploy_target = %s,
                        status = 'ACTIVE',
                        version_number = %s,
                        last_modified_timestamp = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (final_ap_name, desc, prim_source, owner_id, owner_name, deploy_target, new_ap_ver, ap_id_str))
                aps_updated += 1
            else:
                cur.execute("""
                    INSERT INTO ApprovedRoleModel_AccessProfiles
                    (id, name, description, primary_source, owner_id, owner_name,
                     deploy_target, status, version_number, created_timestamp, activated_timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (ap_id_str, final_ap_name, desc, prim_source, owner_id, owner_name, deploy_target))

                audit_records.append((
                    event_id, "IT_ROLE", ap_id_str, final_ap_name, 1,
                    "CREATE", "access_profile", None, f"Created IT Role '{final_ap_name}' with {len(current_ap_ents)} entitlements",
                    "Admin Reviewer", "Promoted from suggested IT models"
                ))

                for ce in current_ap_ents:
                    audit_records.append((
                        event_id, "AP_ENTITLEMENT", ap_id_str, final_ap_name, 1,
                        "ADD_ENTITLEMENT", "entitlement", None, f"{ce['entitlement_name']} ({ce['source_name']})",
                        "Admin Reviewer", "Initial permission bundle"
                    ))

                aps_published += 1

            cur.execute("DELETE FROM ApprovedRoleModel_AccessProfileEntitlements WHERE access_profile_id = %s", (ap_id_str,))
            if current_ap_ents:
                sql_armape = """
                    INSERT IGNORE INTO ApprovedRoleModel_AccessProfileEntitlements
                    (access_profile_id, access_profile_name, entitlement_id, entitlement_name, source_name)
                    VALUES (%s, %s, %s, %s, %s)
                """
                armape_batch = [
                    (
                        ap_id_str,
                        final_ap_name,
                        str(ce["entitlement_id"] or ce["entitlement_name"])[:255],
                        str(ce["entitlement_name"])[:255],
                        str(ce["source_name"] or "Unknown")[:255],
                    )
                    for ce in current_ap_ents
                ]
                cur.executemany(sql_armape, armape_batch)

        print(f"   ✓ Published {aps_published:,} net-new Access Profiles and updated {aps_updated:,} existing profiles.")

        # ----------------------------------------------------------------------
        # 3. RECORD AUDIT LOG ENTRIES
        # ----------------------------------------------------------------------
        if audit_records:
            print(f"📝 Recording {len(audit_records):,} immutable audit events in ApprovedRoleModel_AuditLog...")
            sql_audit = """
                INSERT INTO ApprovedRoleModel_AuditLog
                (event_id, entity_type, entity_id, entity_name, version_number,
                 action_type, field_name, old_value, new_value, changed_by, change_reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            for i in range(0, len(audit_records), 5000):
                cur.executemany(sql_audit, audit_records[i:i + 5000])

        conn.commit()
        print("\n" + "=" * 80)
        print(f"🎉 Production Publishing Complete! Total Audit Events Logged: {len(audit_records):,}")
        print("=" * 80)

    except Error as e:
        if conn:
            conn.rollback()
        print(f"❌ Database error during production publishing: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)


if __name__ == "__main__":
    publish_approved_role_model()
