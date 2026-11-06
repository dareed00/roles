#!/usr/bin/env python3
"""
bundleBuilder - Excel Identity, Attribute & Entitlement Ingestion Engine
Reads a flat Excel or CSV data source where each row is an identity-to-entitlement mapping.
Maps:
  • 'User_Name'   --> Identity ID & Identity Name
  • 'Entitlement' --> Entitlement ID & Entitlement Name
  • Other columns --> Identity_Attributes & Identity_Attributes_Filtered
Populates base and _Filtered tables in MySQL bundleBuilder.
"""

import os
import sys
import argparse
from collections import defaultdict
import pandas as pd
import mysql.connector
from mysql.connector import Error

# ==============================================================================
# DATABASE CONFIGURATION
# ==============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}

BATCH_SIZE = 10000

# Attribute name normalization mapping
ATTRIBUTE_NAME_MAP = {
    "job_title": "jobTitle",
    "jobtitle": "jobTitle",
    "job title": "jobTitle",
    "title": "jobTitle",
    "department": "department",
    "dept": "department",
    "location": "location",
    "country": "country",
    "type": "type",
    "employee_type": "type",
    "employeetype": "type",
    "user_type": "type",
    "ismanager": "isManager",
    "is_manager": "isManager",
    "is manager": "isManager",
    "division": "division",
    "costcenter": "costCenter",
    "cost_center": "costCenter",
    "cost center": "costCenter",
}

# Personal identifiers to exclude from role mining tables (Identity_Attributes_Filtered & Attribute_Populations)
EXCLUDED_MINING_ATTRIBUTES = {
    "employee_id", "first_name", "last_name", "worker", "full_legal_name", 
    "request_id_user_key", "provisioning_date", "continuous_service_date", 
    "hire_date", "id", "manager_id", "worker_s_manager", "crd_id", "primaryworkemail"
}

IDENTITY_DIRECT_COLUMNS = {
    "email": "email",
    "primaryworkemail": "email",
    "firstname": "firstName",
    "first_name": "firstName",
    "lastname": "lastName",
    "last_name": "lastName",
    "displayname": "displayName",
    "full_legal_name": "displayName",
    "employeenumber": "employeeNumber",
    "employee_id": "employeeNumber",
    "status": "status",
}


def resolve_file_path():
    parser = argparse.ArgumentParser(description="Ingest user & entitlement data into MySQL bundleBuilder.")
    parser.add_argument("file_path", nargs="?", default=None, help="Path to the source file (.xlsx or .csv)")
    args, _ = parser.parse_known_args()

    chosen_path = args.file_path
    if not chosen_path:
        try:
            chosen_path = input("Enter path to source file (.xlsx or .csv): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nOperation cancelled.")
            sys.exit(0)

    chosen_path = os.path.expanduser(chosen_path.strip("'\""))
    if not os.path.exists(chosen_path):
        print(f"❌ Error: File '{chosen_path}' not found.")
        sys.exit(1)

    return chosen_path


def normalize_attr_name(raw_col):
    clean = str(raw_col).strip()
    lower = clean.lower()
    return ATTRIBUTE_NAME_MAP.get(lower, clean)


def load_and_parse_data(file_path):
    print(f"\n📖 Reading source file: '{file_path}'...")
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path, dtype=str)
    else:
        df = pd.read_excel(file_path, dtype=str)
        
    df.columns = [str(c).strip() for c in df.columns]

    # Locate required columns
    user_col = next((c for c in df.columns if c.lower() in ("user_name", "username", "uid", "user name")), None)
    ent_col = next((c for c in df.columns if c.lower() in ("entitlement", "entitlement_name", "attribute_value_name", "entitlements")), None)
    source_col = next((c for c in df.columns if c.lower() in ("source", "source_name", "access_source_name", "application", "app_name")), None)

    if not user_col or not ent_col:
        raise ValueError(f"Required columns ('User_Name' and 'Entitlement') not found. Columns are: {list(df.columns)}")

    excluded_cols = {user_col, ent_col}
    if source_col:
        excluded_cols.add(source_col)

    attr_cols = [c for c in df.columns if c not in excluded_cols]

    print(f"   • User Column        : '{user_col}'")
    print(f"   • Entitlement Column : '{ent_col}'")
    print(f"   • Source Column      : '{source_col if source_col else 'Default (Enterprise_Source)'}'")
    print(f"   • Attribute Columns  : {attr_cols}")

    identities_meta = {}
    identity_attrs = {}
    identity_attrs_filtered = {}
    attr_populations = {} # Keyed case-insensitively to prevent duplicates: (attr_name_lower, attr_val_lower)
    entitlement_sources = {}
    entitlement_holders = defaultdict(set)
    user_entitlements = defaultdict(set)

    for _, row in df.iterrows():
        raw_user = row.get(user_col)
        if pd.isna(raw_user) or not str(raw_user).strip():
            continue
        user_name = str(raw_user).strip()

        # Initialize identity record
        if user_name not in identities_meta:
            identities_meta[user_name] = {
                "email": None,
                "firstName": None,
                "lastName": None,
                "displayName": user_name,
                "isManager": 0,
                "status": "active",
                "employeeNumber": None,
            }

        # Parse entitlement
        raw_ent = row.get(ent_col)
        if pd.notna(raw_ent) and str(raw_ent).strip():
            ent_val = str(raw_ent).strip()
            src_val = str(row.get(source_col)).strip() if source_col and pd.notna(row.get(source_col)) else "Enterprise_Source"
            
            entitlement_sources[ent_val] = src_val
            entitlement_holders[ent_val].add(user_name)
            user_entitlements[user_name].add(ent_val)

        # Parse attributes
        for col in attr_cols:
            val = row.get(col)
            if pd.isna(val) or not str(val).strip() or str(val).strip().lower() == "nan":
                continue
            val_str = str(val).strip()
            col_lower = col.lower()

            # Map direct metadata if matching defined direct columns
            if col_lower in IDENTITY_DIRECT_COLUMNS:
                target_field = IDENTITY_DIRECT_COLUMNS[col_lower]
                identities_meta[user_name][target_field] = val_str

            # Normalize attribute name
            norm_attr = normalize_attr_name(col)
            if norm_attr == "isManager":
                is_mgr_bool = 1 if val_str.upper() in ("TRUE", "YES", "1", "Y") else 0
                identities_meta[user_name]["isManager"] = is_mgr_bool

            # Save to base table list
            identity_attrs[(user_name, norm_attr)] = val_str

            # Filter out high-cardinality personal identifiers from mining
            if col_lower not in EXCLUDED_MINING_ATTRIBUTES:
                identity_attrs_filtered[(user_name, norm_attr)] = val_str
                
                # Case-insensitive aggregation key to match MySQL unique collation
                group_key = (norm_attr.strip().lower(), val_str.lower())
                if group_key not in attr_populations:
                    attr_populations[group_key] = {
                        "name": norm_attr.strip(),
                        "val": val_str,
                        "uids": set()
                    }
                attr_populations[group_key]["uids"].add(user_name)

    print(f"\n📊 Parsed Aggregates:")
    print(f"   • Unique Identities           : {len(identities_meta):,}")
    print(f"   • Base Identity Attributes     : {len(identity_attrs):,}")
    print(f"   • Filtered Mining Attributes  : {len(identity_attrs_filtered):,}")
    print(f"   • Unique Entitlements         : {len(entitlement_sources):,}")
    print(f"   • Total Assignments           : {sum(len(e) for e in user_entitlements.values()):,}")

    return (
        identities_meta,
        identity_attrs,
        identity_attrs_filtered,
        attr_populations,
        entitlement_sources,
        entitlement_holders,
        user_entitlements,
    )


def populate_database(
    identities_meta,
    identity_attrs,
    identity_attrs_filtered,
    attr_populations,
    entitlement_sources,
    entitlement_holders,
    user_entitlements,
):
    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        cursor = db_connection.cursor()
        print("\n🔗 Connected to MySQL database.")

        print("🧹 Clearing existing identity, attribute, and entitlement staging tables...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        tables_to_clear = [
            "IdentityEntitlementAssignments_Filtered",
            "IdentityEntitlementAssignments",
            "IdentityEffectiveEntitlements_Filtered",
            "IdentityEffectiveEntitlements",
            "Identity_Attributes_Filtered",
            "Identity_Attributes",
            "Attribute_Populations",
            "Identities_Filtered",
            "Identities",
            "entitlements",
        ]
        for tbl in tables_to_clear:
            cursor.execute(f"TRUNCATE TABLE `{tbl}`;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

        # ------------------------------------------------------------------
        # 1. INSERT IDENTITIES
        # ------------------------------------------------------------------
        print("👤 [1/5] Inserting Identities & Identities_Filtered...")
        sql_identities = """
            INSERT INTO `{table}`
            (`id`, `name`, `email`, `firstName`, `lastName`, `displayName`,
             `inactive`, `isManager`, `status`, `employeeNumber`, `entitlementCount`, `accessCount`)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        identity_rows = []
        for u_name, meta in identities_meta.items():
            ent_cnt = len(user_entitlements.get(u_name, set()))
            inactive_flag = 1 if str(meta["status"]).upper() in ("INACTIVE", "TERMINATED", "DISABLED") else 0
            u_trimmed = u_name[:255]
            identity_rows.append((
                u_trimmed,
                u_trimmed,
                meta["email"][:255] if meta["email"] else None,
                meta["firstName"][:255] if meta["firstName"] else None,
                meta["lastName"][:255] if meta["lastName"] else None,
                meta["displayName"][:255] if meta["displayName"] else u_trimmed,
                inactive_flag,
                meta["isManager"],
                meta["status"][:100] if meta["status"] else "active",
                meta["employeeNumber"][:100] if meta["employeeNumber"] else None,
                ent_cnt,
                ent_cnt,
            ))

        for tbl in ("Identities", "Identities_Filtered"):
            query = sql_identities.format(table=tbl)
            for i in range(0, len(identity_rows), BATCH_SIZE):
                cursor.executemany(query, identity_rows[i:i + BATCH_SIZE])

        # ------------------------------------------------------------------
        # 2. INSERT IDENTITY_ATTRIBUTES (Base and Filtered)
        # ------------------------------------------------------------------
        print("🏷️  [2/5] Inserting Identity_Attributes & Identity_Attributes_Filtered...")
        
        # Insert to base Attributes table
        sql_attrs_base = """
            INSERT INTO `Identity_Attributes`
            (`identity_id`, `attribute_name`, `attribute_value`)
            VALUES (%s, %s, %s)
        """
        attr_rows_base = [
            (u_name[:255], a_name[:255], a_val)
            for (u_name, a_name), a_val in identity_attrs.items()
        ]
        for i in range(0, len(attr_rows_base), BATCH_SIZE):
            cursor.executemany(sql_attrs_base, attr_rows_base[i:i + BATCH_SIZE])

        # Insert to Filtered Attributes table
        sql_attrs_filtered = """
            INSERT INTO `Identity_Attributes_Filtered`
            (`identity_id`, `attribute_name`, `attribute_value`)
            VALUES (%s, %s, %s)
        """
        attr_rows_filtered = [
            (u_name[:255], a_name[:255], a_val)
            for (u_name, a_name), a_val in identity_attrs_filtered.items()
        ]
        for i in range(0, len(attr_rows_filtered), BATCH_SIZE):
            cursor.executemany(sql_attrs_filtered, attr_rows_filtered[i:i + BATCH_SIZE])

        # ------------------------------------------------------------------
        # 3. INSERT ATTRIBUTE_POPULATIONS (WITH DUPLICATE KEY GRACEFULNESS)
        # ------------------------------------------------------------------
        print("📈 [3/5] Inserting Attribute_Populations...")
        sql_attr_pop = """
            INSERT INTO `Attribute_Populations`
            (`attribute_name`, `attribute_value`, `population_size`)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                `population_size` = VALUES(`population_size`),
                `last_calculated` = CURRENT_TIMESTAMP
        """
        pop_rows = [
            (item["name"][:255], item["val"], len(item["uids"]))
            for item in attr_populations.values()
        ]
        for i in range(0, len(pop_rows), BATCH_SIZE):
            cursor.executemany(sql_attr_pop, pop_rows[i:i + BATCH_SIZE])

        # ------------------------------------------------------------------
        # 4. INSERT ENTITLEMENTS
        # ------------------------------------------------------------------
        print("🔑 [4/5] Inserting entitlements catalog...")
        sql_entitlements = """
            INSERT INTO `entitlements`
            (`entitlement_id`, `entitlement_name`, `source_name`, `population_size`)
            VALUES (%s, %s, %s, %s)
        """
        ent_rows = []
        for ent_name, src_name in entitlement_sources.items():
            pop_size = len(entitlement_holders.get(ent_name, set()))
            ent_trimmed = ent_name[:255]
            ent_rows.append((
                ent_trimmed,
                ent_trimmed,
                src_name[:255],
                pop_size,
            ))

        for i in range(0, len(ent_rows), BATCH_SIZE):
            cursor.executemany(sql_entitlements, ent_rows[i:i + BATCH_SIZE])

        # ------------------------------------------------------------------
        # 5. INSERT IDENTITY ENTITLEMENT ASSIGNMENTS
        # ------------------------------------------------------------------
        print("🔗 [5/5] Inserting IdentityEntitlementAssignments & _Filtered...")
        sql_assign = """
            INSERT INTO `{table}`
            (`identity_id`, `identity_name`, `entitlement_id`, `entitlement_name`, `standalone`)
            VALUES (%s, %s, %s, %s, 1)
        """
        assign_rows = []
        for u_name, ents in user_entitlements.items():
            u_trimmed = u_name[:255]
            for ent_name in ents:
                e_trimmed = ent_name[:255]
                assign_rows.append((
                    u_trimmed,
                    u_trimmed,
                    e_trimmed,
                    e_trimmed,
                ))

        for tbl in ("IdentityEntitlementAssignments", "IdentityEntitlementAssignments_Filtered"):
            query = sql_assign.format(table=tbl)
            for i in range(0, len(assign_rows), BATCH_SIZE):
                cursor.executemany(query, assign_rows[i:i + BATCH_SIZE])

        db_connection.commit()
        cursor.close()
        db_connection.close()
        print("\n✅ Success! All records processed and synced successfully.")

    except Error as e:
        print(f"\n❌ Database error during ingestion: {e}")
        sys.exit(1)


if __name__ == "__main__":
    file_path = resolve_file_path()
    parsed_data = load_and_parse_data(file_path)
    populate_database(*parsed_data)
