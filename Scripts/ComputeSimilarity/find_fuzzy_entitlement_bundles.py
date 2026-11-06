#!/usr/bin/env python3
"""
bundleBuilder - Fuzzy Peer Entitlement Correlator
Discovers "Fuzzy Access Profiles" by comparing Entitlements to Entitlements 
using the Dynamic Population-Scaled Threshold.
Filters out exact 100% matches (Jaccard = 1.0) to prevent redundancy.
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


def load_entitlement_data():
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

        cursor.execute("SELECT id, entitlement_name FROM entitlements")
        ent_id_map = {row["entitlement_name"].strip(): row["id"] for row in cursor.fetchall()}

        cursor.close()
        db_connection.close()
        return ent_sets, ent_id_map
    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)


# ==============================================================================
# DYNAMIC CALIBRATION CURVE
# ==============================================================================
def is_valid_near_match(intersection_size, union_size):
    if union_size == 0: return False
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


# ==============================================================================
# PEER ENTITLEMENT ENGINE (EXCLUDES EXACT 1.0 MATCHES)
# ==============================================================================
def find_fuzzy_entitlement_bundles(ent_sets):
    print("⚡ Executing Fuzzy Peer-to-Peer Entitlement Search...")
    
    valid_correlations = []
    
    filtered_ents = {name: uids for name, uids in ent_sets.items() if len(uids) > 1}
    ent_items = list(filtered_ents.items())
    
    print(f"   ► Evaluating combinations for {len(ent_items)} viable entitlements...")

    for (name_a, uids_a), (name_b, uids_b) in combinations(ent_items, 2):
        intersection = len(uids_a & uids_b)
        union = len(uids_a | uids_b)
        
        # SKIP if no overlap OR if it's an exact 100% match (already in exact tables)
        if intersection == 0 or intersection == union:
            continue
        
        if is_valid_near_match(intersection, union):
            jaccard = intersection / union
            missing_b_uids = uids_a - uids_b  # Users who have A, but missing B
            missing_a_uids = uids_b - uids_a  # Users who have B, but missing A
            
            valid_correlations.append({
                "ent_a": name_a,
                "ent_b": name_b,
                "jaccard": jaccard,
                "intersection": intersection,
                "union": union,
                "missing_b_count": len(missing_b_uids),
                "missing_a_count": len(missing_a_uids),
                "missing_b_uids": list(missing_b_uids),
                "missing_a_uids": list(missing_a_uids)
            })

    valid_correlations.sort(key=lambda x: x["jaccard"], reverse=True)
    print(f"🎯 Discovered {len(valid_correlations)} Pure Fuzzy Peer Bundles (Filtered 100% Exact Matches).")
    return valid_correlations


# ==============================================================================
# DATABASE PERSISTENCE LOGIC
# ==============================================================================
def persist_peer_bundles_to_mysql(correlations, ent_id_map):
    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor()

        print("\n💾 Clearing old peer bundles and saving new batch...")
        cursor.execute("DELETE FROM Fuzzy_Entitlement_Exceptions")
        cursor.execute("DELETE FROM Fuzzy_Entitlement_Correlations")

        sql_corr = """
            INSERT INTO Fuzzy_Entitlement_Correlations 
            (entitlement_a_name, entitlement_a_id, entitlement_b_name, entitlement_b_id, 
             jaccard_score, intersection_size, union_size, missing_b_count, missing_a_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        sql_exc  = "INSERT INTO Fuzzy_Entitlement_Exceptions (correlation_id, identity_id, exception_type) VALUES (%s, %s, %s)"

        exceptions_batch = []
        rule_count = 0

        for corr in correlations:
            ent_a_id = ent_id_map.get(corr["ent_a"])
            ent_b_id = ent_id_map.get(corr["ent_b"])

            cursor.execute(sql_corr, (
                str(corr["ent_a"])[:250],
                ent_a_id,
                str(corr["ent_b"])[:250],
                ent_b_id,
                float(corr["jaccard"]),
                corr["intersection"],
                corr["union"],
                corr["missing_b_count"],
                corr["missing_a_count"]
            ))
            corr_id = cursor.lastrowid
            rule_count += 1

            for uid in corr["missing_b_uids"]:
                exceptions_batch.append((corr_id, str(uid)[:250], 'MISSING_B'))
                
            for uid in corr["missing_a_uids"]:
                exceptions_batch.append((corr_id, str(uid)[:250], 'MISSING_A'))

        print(f"   • Inserting {len(exceptions_batch):,} Specific User Exceptions...")
        chunk_size = 10000
        for i in range(0, len(exceptions_batch), chunk_size):
            chunk = exceptions_batch[i:i + chunk_size]
            cursor.executemany(sql_exc, chunk)

        db_connection.commit()
        cursor.close()
        db_connection.close()
        print(f"✅ Success! {rule_count} fuzzy peer correlations persisted into MySQL.")

    except Error as e:
        print(f"❌ Database persistence error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    ent_sets, ent_id_map = load_entitlement_data()
    correlations = find_fuzzy_entitlement_bundles(ent_sets)
    
    print("\n" + "=" * 80)
    print("🏆 PREVIEW: TOP 10 STRONGEST FUZZY PEER BUNDLES (Exceptions > 0)")
    print("=" * 80)
    for idx, corr in enumerate(correlations[:10], start=1):
        print(f"[{idx}] {corr['ent_a']}")
        print(f"    & {corr['ent_b']}")
        print(f"   ► Jaccard    : {corr['jaccard'] * 100:.2f}% (Intersection: {corr['intersection']})")
        print(f"   ► Exceptions : {corr['missing_b_count']} missing B | {corr['missing_a_count']} missing A\n")

    persist_peer_bundles_to_mysql(correlations, ent_id_map)
