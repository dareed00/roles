#!/usr/bin/env python3
"""
bundleBuilder - IT / Functional Role Synthesizer
Clusters correlated entitlements (without HR rules) into cohesive multi-entitlement 
IT Roles / Access Profiles with semantic naming, adoption profiling, and population segmentation.
"""

import os
import sys
import re
import argparse
from collections import defaultdict
from typing import Optional
import mysql.connector
from mysql.connector import Error

# ==============================================================================
# 1. DYNAMIC SYSTEM PATH RESOLUTION & UTILS.CONFIG IMPORTS
# ==============================================================================
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Utils.config import (
    open_connection,
    close_db_connection,
    MiningConfig,
    get_mining_config,
    DB_CONFIG,
)


# ==============================================================================
# 2. SEMANTIC IT ROLE NAMING ENGINE
# ==============================================================================
def find_common_prefix(strings):
    if not strings:
        return ""
    words_list = [re.split(r'[_:\-\s]+', s.strip()) for s in strings]
    common = []
    for parts in zip(*words_list):
        if len(set(p.lower() for p in parts)) == 1:
            common.append(parts[0])
        else:
            break
    return " ".join(common).strip()


def generate_it_role_name(ent_names, source_names):
    clean_sources = [s for s in source_names if s and s.lower() not in ("unknown", "none", "")]
    primary_source = max(set(clean_sources), key=clean_sources.count) if clean_sources else "Enterprise"
    
    prefix = find_common_prefix(ent_names)
    if prefix and len(prefix) >= 4 and prefix.lower() != primary_source.lower():
        clean_prefix = re.sub(r'[_:\-]+', ' ', prefix).title()
        return f"{primary_source} {clean_prefix} Access Profile", primary_source
    
    if len(ent_names) == 2:
        return f"{primary_source} Core Functional Bundle ({len(ent_names)} Entitlements)", primary_source
    
    return f"{primary_source} Functional Role ({len(ent_names)} Permissions)", primary_source


# ==============================================================================
# 3. GRAPH CLUSTERING (CONNECTED COMPONENTS WITH POPULATION FILTERING)
# ==============================================================================
class UnionFind:
    def __init__(self):
        self.parent = {}
    
    def find(self, item):
        if item not in self.parent:
            self.parent[item] = item
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]
    
    def union(self, a, b):
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a


def load_it_role_sources():
    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            print("❌ Could not establish database connection.")
            sys.exit(1)

        cur = conn.cursor(dictionary=True)
        print("🔗 Connected to MySQL bundleBuilder.")

        cur.execute("SELECT id, entitlement_name, source_name FROM entitlements")
        ent_meta = {}
        for row in cur.fetchall():
            ent_meta[row["entitlement_name"].strip()] = {
                "id": row["id"],
                "source": row["source_name"] or "Unknown"
            }

        print("👥 Loading Entitlement Identity Sets...")
        cur.execute("""
            SELECT identity_id, entitlement_name 
            FROM (
                SELECT identity_id, entitlement_name FROM IdentityEffectiveEntitlements_Filtered
                UNION
                SELECT identity_id, entitlement_name FROM IdentityEntitlementAssignments_Filtered
            ) t
        """)
        ent_users = defaultdict(set)
        for row in cur.fetchall():
            ent_users[row["entitlement_name"].strip()].add(str(row["identity_id"]).strip())

        cur.execute("""
            SELECT r.id, e.entitlement_id, ent.entitlement_name 
            FROM Suggested_Discovered_Rules r
            JOIN Suggested_Rule_Entitlements e ON r.id = e.rule_id
            JOIN entitlements ent ON e.entitlement_id = ent.id
            WHERE r.rule_type = 'SUGGESTED_AP'
        """)
        exact_aps = defaultdict(list)
        for row in cur.fetchall():
            exact_aps[row["id"]].append(row["entitlement_name"].strip())

        cur.execute("""
            SELECT entitlement_a_name, entitlement_b_name, jaccard_score 
            FROM Fuzzy_Entitlement_Correlations
            WHERE jaccard_score >= 0.85
        """)
        peer_correlations = cur.fetchall()

        try:
            cur.execute("SELECT DISTINCT TRIM(role_name) as role_name, TRIM(entitlement_name) as entitlement_name, TRIM(source_name) as source_name FROM Role_Entitlement_Exclusions")
            exclusions = {(row["role_name"].lower(), row["entitlement_name"].lower(), row["source_name"].lower()) for row in cur.fetchall()}
        except Exception:
            exclusions = set()

        return ent_meta, ent_users, exact_aps, peer_correlations, exclusions

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)


def cluster_it_roles(ent_meta, ent_users, exact_aps, peer_correlations, exclusions, config: MiningConfig):
    max_label = config.max_pop if config.max_pop is not None else "Unlimited"
    print(f"⚙️ Executing Graph Clustering on Entitlement Correlations (Role Member Segment: {config.min_pop} to {max_label})...")
    uf = UnionFind()
    edge_scores = defaultdict(dict)

    # 1. Union exact access profiles
    for r_id, ents in exact_aps.items():
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                uf.union(ents[i], ents[j])
                edge_scores[ents[i]][ents[j]] = 1.0
                edge_scores[ents[j]][ents[i]] = 1.0

    # 2. Union peer correlations (J >= 0.85)
    for row in peer_correlations:
        a = row["entitlement_a_name"].strip()
        b = row["entitlement_b_name"].strip()
        score = float(row["jaccard_score"])
        uf.union(a, b)
        edge_scores[a][b] = score
        edge_scores[b][a] = score

    clusters = defaultdict(list)
    for e in set(edge_scores.keys()):
        clusters[uf.find(e)].append(e)

    it_roles = []
    for root, cluster_ents in clusters.items():
        if len(cluster_ents) < 2:
            continue

        sources = [ent_meta.get(e, {}).get("source", "Unknown") for e in cluster_ents]
        role_name, primary_source = generate_it_role_name(cluster_ents, sources)

        # Filter out excluded entitlements
        filtered_ents = []
        for e in cluster_ents:
            source = ent_meta.get(e, {}).get("source", "Unknown")
            if (role_name.lower(), e.lower(), source.lower()) in exclusions:
                print(f"[-] Excluding rejected entitlement '{e}' from IT Role '{role_name}'")
                continue
            filtered_ents.append(e)

        if len(filtered_ents) < 2:
            continue

        cluster_ents = sorted(filtered_ents)
        sources = [ent_meta.get(e, {}).get("source", "Unknown") for e in cluster_ents]
        role_name, primary_source = generate_it_role_name(cluster_ents, sources)

        # Identity adoption profiling
        user_counts = defaultdict(int)
        all_cluster_users = set()
        for e in cluster_ents:
            uids = ent_users.get(e, set())
            all_cluster_users.update(uids)
            for u in uids:
                user_counts[u] += 1

        full_holders = [u for u, cnt in user_counts.items() if cnt == len(cluster_ents)]
        partial_holders = [u for u, cnt in user_counts.items() if cnt < len(cluster_ents)]

        # Filter IT Role by target member population segment (full_holders count)
        member_count = len(full_holders)
        if member_count < config.min_pop:
            continue
        if config.max_pop is not None and member_count > config.max_pop:
            continue

        pair_scores = []
        for i in range(len(cluster_ents)):
            for j in range(i + 1, len(cluster_ents)):
                e1, e2 = cluster_ents[i], cluster_ents[j]
                s1, s2 = ent_users.get(e1, set()), ent_users.get(e2, set())
                inter = len(s1 & s2)
                union = len(s1 | s2)
                pair_scores.append(inter / union if union > 0 else 0)
        
        avg_cohesion = sum(pair_scores) / len(pair_scores) if pair_scores else 1.0

        it_roles.append({
            "role_name": role_name,
            "primary_source": primary_source,
            "entitlements": cluster_ents,
            "entitlements_count": len(cluster_ents),
            "full_holders": full_holders,
            "partial_holders": partial_holders,
            "total_users": len(all_cluster_users),
            "cohesion_score": avg_cohesion,
            "user_counts": user_counts,
            "description": f"IT Functional Role bundling {len(cluster_ents)} {primary_source} permissions. Cohesion: {avg_cohesion*100:.1f}%."
        })

    it_roles.sort(key=lambda x: (x["entitlements_count"], len(x["full_holders"])), reverse=True)

    if config.batch_size is not None and config.batch_size > 0:
        start_idx = config.batch_index * config.batch_size
        end_idx = start_idx + config.batch_size
        total_it = len(it_roles)
        it_roles = it_roles[start_idx:end_idx]
        print(f"   • Batch #{config.batch_index} (Size {config.batch_size}): Selected {len(it_roles):,} of {total_it:,} IT roles.")

    print(f"🎯 Synthesized {len(it_roles):,} Multi-Entitlement IT Roles / Access Profiles.")
    return it_roles


# ==============================================================================
# 4. DATABASE PERSISTENCE
# ==============================================================================
def persist_it_roles(it_roles, ent_meta, ent_users, config: MiningConfig):
    conn = None
    cur = None
    try:
        conn = open_connection()
        if not conn:
            print("❌ Could not establish database connection.")
            sys.exit(1)

        cur = conn.cursor()
        print("\n💾 Persisting IT Roles to MySQL bundleBuilder...")

        if config.clear_all or config.batch_size is None:
            cur.execute("DELETE FROM Suggested_IT_Role_Identities")
            cur.execute("DELETE FROM Suggested_IT_Role_Entitlements")
            cur.execute("DELETE FROM Suggested_IT_Roles")
        else:
            role_names = [r["role_name"][:250] for r in it_roles]
            if role_names:
                placeholders = ", ".join(["%s"] * len(role_names))
                cur.execute(f"DELETE FROM Suggested_IT_Roles WHERE it_role_name IN ({placeholders})", tuple(role_names))

        sql_role = """
            INSERT INTO Suggested_IT_Roles 
            (it_role_name, primary_source, description, entitlements_count, 
             full_holders_count, partial_holders_count, bundle_cohesion_score, role_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'FUNCTIONAL_BUNDLE')
        """
        sql_ent = """
            INSERT INTO Suggested_IT_Role_Entitlements 
            (it_role_id, entitlement_id, entitlement_name, source_name, assignment_count)
            VALUES (%s, %s, %s, %s, %s)
        """
        sql_id = """
            INSERT INTO Suggested_IT_Role_Identities 
            (it_role_id, identity_id, held_entitlements_count, coverage_percentage, adoption_status)
            VALUES (%s, %s, %s, %s, %s)
        """

        ents_batch = []
        ids_batch = []

        for role in it_roles:
            cur.execute(sql_role, (
                role["role_name"][:250],
                role["primary_source"][:250],
                role["description"],
                role["entitlements_count"],
                len(role["full_holders"]),
                len(role["partial_holders"]),
                float(role["cohesion_score"])
            ))
            role_id = cur.lastrowid

            for e_name in role["entitlements"]:
                meta = ent_meta.get(e_name, {})
                e_id = meta.get("id")
                source = meta.get("source", "Unknown")
                u_count = len(ent_users.get(e_name, set()))
                ents_batch.append((role_id, e_id, e_name[:250], source[:250], u_count))

            for uid, cnt in role["user_counts"].items():
                coverage = (cnt / role["entitlements_count"]) * 100.0
                status = "FULL_HOLDER" if cnt == role["entitlements_count"] else "PARTIAL_CANDIDATE"
                ids_batch.append((role_id, str(uid)[:250], cnt, float(coverage), status))

        if ents_batch:
            print(f"   • Inserting {len(ents_batch):,} IT Role Entitlements...")
            cur.executemany(sql_ent, ents_batch)

        if ids_batch:
            print(f"   • Inserting {len(ids_batch):,} Identity Adoption mappings...")
            chunk_size = 10000
            for i in range(0, len(ids_batch), chunk_size):
                cur.executemany(sql_id, ids_batch[i:i + chunk_size])

        conn.commit()
        print(f"✅ Success! {len(it_roles):,} IT Roles fully persisted into MySQL.")

    except Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    finally:
        if conn:
            close_db_connection(conn, cur)


# ==============================================================================
# 5. UI & CLI ORCHESTRATION ENTRY POINTS
# ==============================================================================
def parse_cli_to_config() -> MiningConfig:
    parser = argparse.ArgumentParser(description="Synthesize IT Functional Roles by Population Segment")
    parser.add_argument("--preset", type=str, default=None, help="Preset tier: BROAD_BIRTHRIGHT, CORE_FUNCTIONAL, MICRO_BUNDLE, ALL")
    parser.add_argument("--min-pop", type=int, default=None, help="Minimum full-holder member population")
    parser.add_argument("--max-pop", type=int, default=None, help="Maximum full-holder member population")
    parser.add_argument("--batch-size", type=int, default=None, help="Number of IT roles per batch")
    parser.add_argument("--batch-index", type=int, default=None, help="0-based batch offset")
    parser.add_argument("--clear-all", action="store_true", help="Wipe all existing Suggested_IT_Roles before saving")
    args, _ = parser.parse_known_args()

    cfg = get_mining_config()
    if args.preset:
        cfg.apply_preset(args.preset)
    if args.min_pop is not None:
        cfg.min_pop = args.min_pop
    if args.max_pop is not None:
        cfg.max_pop = args.max_pop
    if args.batch_size is not None:
        cfg.batch_size = args.batch_size
    if args.batch_index is not None:
        cfg.batch_index = args.batch_index
    if args.clear_all:
        cfg.clear_all = True

    return cfg


def run_it_role_synthesis(config: Optional[MiningConfig] = None):
    if config is None:
        config = parse_cli_to_config()

    ent_meta, ent_users, exact_aps, peer_correlations, exclusions = load_it_role_sources()
    it_roles = cluster_it_roles(ent_meta, ent_users, exact_aps, peer_correlations, exclusions, config)
    persist_it_roles(it_roles, ent_meta, ent_users, config)
    return it_roles


if __name__ == "__main__":
    run_it_role_synthesis()
