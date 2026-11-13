#!/usr/bin/env python3
"""RoleMiner - Unified Delta Comparator (Suggested vs.

Approved & Current Role Models)
File: ComputeSimilarity/compare_suggested_vs_approved.py
"""

from collections import defaultdict
import os
import re
import sys
import pymysql

# Database configuration (using fallback password 'password')
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "password",
    "database": "bundleBuilder",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}


def norm(val):
  """Cleans, strips, and lowercases text for matching."""
  if val is None:
    return ""
  return str(val).strip().lower()


def pick_field(row, candidates, default=None):
  """Picks the first non-null field matching candidate column names (case-insensitive)."""
  if not row:
    return default
  lower_row = {str(k).lower(): v for k, v in row.items()}
  for c in candidates:
    v = lower_row.get(c.lower())
    if v is not None:
      return v
  return default


def canonicalize_rule(rule_str):
  """Normalizes assignment rule syntax so differences in spacing, casing,

  or clause order do not prevent matching.
  """
  if not rule_str:
    return ""
  s = str(rule_str).strip().lower()
  s = s.replace('"', "'")
  s = re.sub(r"\s+", " ", s)

  def sort_in(match):
    prefix = match.group(1).strip()
    items = [
        x.strip().strip("'") for x in match.group(2).split(",") if x.strip()
    ]
    items.sort()
    return f"{prefix} in ({', '.join(repr(i) for i in items)})"

  s = re.sub(
      r"([a-z0-9_.\-]+)\s+in\s*\(([^)]+)\)", sort_in, s, flags=re.IGNORECASE
  )

  if " and " in s and " or " not in s:
    parts = [p.strip().strip("()") for p in s.split(" and ") if p.strip()]
    parts.sort()
    return " AND ".join(parts)
  return s


def table_exists(cur, table_name):
  cur.execute("SHOW TABLES LIKE %s", (table_name,))
  return bool(cur.fetchone())


def ensure_columns(cur):
  """Ensures 'already_defined' exists on all 4 Suggested_* tables."""
  migrations = [
      (
          "Suggested_Roles",
          "already_defined",
          "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0",
      ),
      (
          "Suggested_Role_Entitlements",
          "already_defined",
          "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0 AFTER"
          " `already_in_role`",
      ),
      (
          "Suggested_IT_Roles",
          "already_defined",
          "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0 AFTER"
          " `approval_status`",
      ),
      (
          "Suggested_IT_Role_Entitlements",
          "already_defined",
          "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0 AFTER"
          " `already_in_role`",
      ),
  ]
  for tbl, col, sql in migrations:
    if table_exists(cur, tbl):
      cur.execute(f"SHOW COLUMNS FROM `{tbl}` LIKE %s", (col,))
      if not cur.fetchone():
        cur.execute(f"ALTER TABLE `{tbl}` {sql}")


def load_entitlement_id_map(cur):
  """Maps entitlement_id -> normalized entitlement_name from `entitlements`."""
  id_map = {}
  if table_exists(cur, "entitlements"):
    cur.execute("SELECT * FROM `entitlements`")
    for r in cur.fetchall():
      eid = pick_field(r, ["id", "entitlement_id"])
      ename = norm(pick_field(r, ["entitlement_name", "name", "value"]))
      if eid is not None and ename:
        id_map[str(eid)] = ename
  return id_map


# ----------------------------------------------------------------------
# 1. Business Roles & Entitlements Delta
# ----------------------------------------------------------------------
def sync_business_roles_delta(cur, ent_id_map):
  print("🏛️ [1/2] Evaluating Suggested Business Roles & Entitlements Delta...")

  cur.execute("UPDATE Suggested_Roles SET already_defined = 0")
  cur.execute(
      "UPDATE Suggested_Role_Entitlements SET already_in_role = 0,"
      " already_defined = 0"
  )

  prod_role_names = set()
  prod_rules = set()
  prod_bundles = []  # list of frozensets of entitlement names

  # Sources: ApprovedRoleModel_Roles, CurrentRoleModel_Roles
  role_sources = [
      (
          "ApprovedRoleModel_Roles",
          [
              "ApprovedRoleModel_RoleEntitlements",
              "ApprovedRoleModel_RoleEffectiveEntitlements",
          ],
      ),
      (
          "CurrentRoleModel_Roles",
          [
              "CurrentRoleModel_RoleEntitlements",
              "CurrentRoleModel_RoleEffectiveEntitlements",
          ],
      ),
  ]

  for r_table, e_tables in role_sources:
    if not table_exists(cur, r_table):
      continue

    cur.execute(f"SELECT * FROM `{r_table}`")
    raw_roles = cur.fetchall()

    role_ents = defaultdict(set)
    for etable in e_tables:
      if not table_exists(cur, etable):
        continue
      cur.execute(f"SELECT * FROM `{etable}`")
      for erow in cur.fetchall():
        rid = str(pick_field(erow, ["role_id", "id"], "")).strip()
        rname = norm(pick_field(erow, ["role_name", "name"]))
        ename = norm(pick_field(erow, ["entitlement_name", "name"]))
        if not ename:
          eid = str(pick_field(erow, ["entitlement_id"], "")).strip()
          ename = ent_id_map.get(eid, "")
        if ename:
          if rid:
            role_ents[rid].add(ename)
          if rname:
            prod_role_names.add(rname)

    for r in raw_roles:
      rid = str(pick_field(r, ["id", "role_id"], "")).strip()
      rname = norm(
          pick_field(r, ["role_name", "name", "approved_role_name"])
      )
      crule = canonicalize_rule(
          pick_field(r, ["assignment_rule", "assignmentCriteria", "rule_logic"])
      )
      eset = role_ents.get(rid, set())

      if rname:
        prod_role_names.add(rname)
      if crule:
        prod_rules.add(crule)
      if eset:
        prod_bundles.append(frozenset(eset))

  # Fetch Suggested Roles & Entitlements
  cur.execute("SELECT * FROM Suggested_Roles")
  sugg_roles = cur.fetchall()

  cur.execute("SELECT * FROM Suggested_Role_Entitlements")
  sugg_ents = cur.fetchall()

  ents_by_role_id = defaultdict(list)
  for e in sugg_ents:
    rid = e.get("role_id")
    eid = e.get("id")
    ename = norm(pick_field(e, ["entitlement_name", "name"]))
    ents_by_role_id[rid].append((eid, ename))

  matched_roles = []
  matched_ents = []

  for sr in sugg_roles:
    s_id = sr["id"]
    s_name = norm(pick_field(sr, ["role_name", "name"]))
    a_name = norm(pick_field(sr, ["approved_role_name"]))
    s_rule = canonicalize_rule(
        pick_field(sr, ["assignment_rule", "rule_logic"])
    )
    s_tuples = ents_by_role_id.get(s_id, [])
    s_set = frozenset(ename for _, ename in s_tuples if ename)

    is_defined = False
    if (s_name and s_name in prod_role_names) or (
        a_name and a_name in prod_role_names
    ):
      is_defined = True
    elif s_rule and s_rule in prod_rules:
      is_defined = True
    elif s_set and any(s_set == p_set for p_set in prod_bundles):
      is_defined = True

    if is_defined:
      matched_roles.append(s_id)
      # Mark entitlements of defined roles
      for row_id, _ in s_tuples:
        matched_ents.append(row_id)

  if matched_roles:
    placeholders = ",".join(["%s"] * len(matched_roles))
    cur.execute(
        f"UPDATE Suggested_Roles SET already_defined = 1 WHERE id IN"
        f" ({placeholders})",
        tuple(matched_roles),
    )

  if matched_ents:
    placeholders = ",".join(["%s"] * len(matched_ents))
    cur.execute(
        "UPDATE Suggested_Role_Entitlements SET already_in_role = 1,"
        f" already_defined = 1 WHERE id IN ({placeholders})",
        tuple(matched_ents),
    )

  print(
      f"   ✓ Business Roles: {len(matched_roles)}/{len(sugg_roles)} marked"
      " already_defined=1."
  )
  print(
      f"   ✓ Business Role Entitlements: {len(matched_ents)}/{len(sugg_ents)}"
      " marked already_defined=1."
  )


# ----------------------------------------------------------------------
# 2. IT Roles & Access Profiles Delta
# ----------------------------------------------------------------------
def sync_it_roles_delta(cur, ent_id_map):
  print("🛠️ [2/2] Evaluating Suggested IT Roles & Entitlements Delta...")

  cur.execute("UPDATE Suggested_IT_Roles SET already_defined = 0")
  cur.execute(
      "UPDATE Suggested_IT_Role_Entitlements SET already_in_role = 0,"
      " already_defined = 0"
  )

  prod_it_names = set()
  prod_it_bundles = []
  all_prod_it_ents = set()

  it_sources = [
      ("ApprovedRoleModel_IT_Roles", ["ApprovedRoleModel_IT_Role_Entitlements"]),
      ("ApprovedRoleModel_AccessProfiles", ["ApprovedRoleModel_AccessProfileEntitlements"]),
      ("CurrentRoleModel_AccessProfiles", ["CurrentRoleModel_AccessProfileEntitlements"]),
  ]

  for it_table, e_tables in it_sources:
    if not table_exists(cur, it_table):
      continue

    cur.execute(f"SELECT * FROM `{it_table}`")
    raw_it = cur.fetchall()

    it_ents = defaultdict(set)
    for etable in e_tables:
      if not table_exists(cur, etable):
        continue
      cur.execute(f"SELECT * FROM `{etable}`")
      for erow in cur.fetchall():
        it_id = str(
            pick_field(
                erow, ["it_role_id", "access_profile_id", "role_id", "id"], ""
            )
        ).strip()
        rname = norm(
            pick_field(
                erow,
                ["it_role_name", "access_profile_name", "role_name", "name"],
            )
        )
        ename = norm(pick_field(erow, ["entitlement_name", "name"]))
        if not ename:
          eid = str(pick_field(erow, ["entitlement_id"], "")).strip()
          ename = ent_id_map.get(eid, "")
        if ename:
          all_prod_it_ents.add(ename)
          if it_id:
            it_ents[it_id].add(ename)
          if rname:
            prod_it_names.add(rname)

    for r in raw_it:
      it_id = str(
          pick_field(r, ["id", "it_role_id", "access_profile_id"], "")
      ).strip()
      rname = norm(
          pick_field(
              r, ["it_role_name", "access_profile_name", "name", "role_name"]
          )
      )
      eset = it_ents.get(it_id, set())
      if rname:
        prod_it_names.add(rname)
      if eset:
        prod_it_bundles.append(frozenset(eset))

  # Fetch Suggested IT Roles & Entitlements
  cur.execute("SELECT * FROM Suggested_IT_Roles")
  sugg_it_roles = cur.fetchall()

  cur.execute("SELECT * FROM Suggested_IT_Role_Entitlements")
  sugg_it_ents = cur.fetchall()

  it_ents_by_id = defaultdict(list)
  for e in sugg_it_ents:
    it_id = e.get("it_role_id")
    row_id = e.get("id")
    ename = norm(pick_field(e, ["entitlement_name", "name"]))
    it_ents_by_id[it_id].append((row_id, ename))

  matched_it_roles = []
  matched_it_ents = []

  for sr in sugg_it_roles:
    s_id = sr["id"]
    s_name = norm(pick_field(sr, ["it_role_name", "name"]))
    a_name = norm(pick_field(sr, ["approved_role_name"]))
    tuples = it_ents_by_id.get(s_id, [])
    s_set = frozenset(ename for _, ename in tuples if ename)

    is_defined = False
    if (s_name and s_name in prod_it_names) or (
        a_name and a_name in prod_it_names
    ):
      is_defined = True
    elif s_set and any(
        (s_set == p_set or s_set.issubset(p_set)) for p_set in prod_it_bundles
    ):
      is_defined = True

    if is_defined:
      matched_it_roles.append(s_id)
      for row_id, _ in tuples:
        matched_it_ents.append(row_id)
    else:
      # Also check individual permissions already active in production
      for row_id, ename in tuples:
        if ename and ename in all_prod_it_ents:
          matched_it_ents.append(row_id)

  if matched_it_roles:
    placeholders = ",".join(["%s"] * len(matched_it_roles))
    cur.execute(
        f"UPDATE Suggested_IT_Roles SET already_defined = 1 WHERE id IN"
        f" ({placeholders})",
        tuple(matched_it_roles),
    )

  if matched_it_ents:
    placeholders = ",".join(["%s"] * len(matched_it_ents))
    cur.execute(
        "UPDATE Suggested_IT_Role_Entitlements SET already_in_role = 1,"
        f" already_defined = 1 WHERE id IN ({placeholders})",
        tuple(matched_it_ents),
    )

  print(
      f"   ✓ IT Roles: {len(matched_it_roles)}/{len(sugg_it_roles)} marked"
      " already_defined=1."
  )
  print(
      f"   ✓ IT Role Entitlements: {len(matched_it_ents)}/{len(sugg_it_ents)}"
      " marked already_defined=1."
  )


def main():
  print("----------------------------------------------------------------------")
  print("--- EXECUTING: compare_suggested_vs_approved.py in /ComputeSimilarity")
  print("----------------------------------------------------------------------")
  conn = pymysql.connect(**DB_CONFIG)
  try:
    with conn.cursor() as cur:
      ensure_columns(cur)
      ent_id_map = load_entitlement_id_map(cur)
      sync_business_roles_delta(cur, ent_id_map)
      sync_it_roles_delta(cur, ent_id_map)
      conn.commit()
      print("💾 Delta comparison complete! All 4 tables updated.")
  except Exception as e:
    conn.rollback()
    print(f"❌ Error during delta comparison: {e}")
    sys.exit(1)
  finally:
    conn.close()


if __name__ == "__main__":
  main()
