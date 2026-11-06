# filter_and_copy_identity_data.py

import mysql.connector
from mysql.connector import Error

def _build_sql_condition(condition, alias="IA"):
    """Builds a SQL condition string and its parameter from a condition dictionary."""
    # This function provided by you is correct and remains unchanged.
    field, operator, value = condition["field"], condition["operator"].upper(), condition.get("value")
    field_sql = f"CAST({alias}.{field} AS CHAR)" if field == "AttributeValue" else f"{alias}.{field}"
    
    if operator == "EQ": return f"{field_sql} = %s", [value]
    if operator == "NEQ": return f"{field_sql} != %s", [value]
    if operator == "CONTAINS": return f"{field_sql} LIKE %s", [f"%{value}%"]
    if operator == "STARTSWITH": return f"{field_sql} LIKE %s", [f"{value}%"]
    if operator == "ENDSWITH": return f"{field_sql} LIKE %s", [f"%{value}"]
    if operator == "ISNULL": return f"{field_sql} IS NULL", []
    if operator == "NOTNULL": return f"{field_sql} IS NOT NULL", []
    
    if operator in ["GT", "GTE", "LT", "LTE"]:
        field_sql = f"CAST({alias}.{field} AS DECIMAL(20, 2))"
        op_map = {"GT": ">", "GTE": ">=", "LT": "<", "LTE": "<="}
        return f"{field_sql} {op_map[operator]} %s", [value]
        
    raise ValueError(f"Unsupported operator: {operator}")

def filter_and_copy_all_identity_data(db_config, filter_groups, logical_operator_between_groups="AND"):
    """
    Identifies a set of identities and copies all their related data to '_Filtered' tables,
    using the correct identifiers for each table.
    """
    if not filter_groups:
        print("No filter groups provided. No action taken.")
        return

    db_connection = None
    try:
        db_connection = mysql.connector.connect(**db_config)
        cursor = db_connection.cursor()

        # --- Step 1: Identify the set of PRIMARY IDs that match the filter ---
        print("\n--- Step 1: Identifying matching identities ---")
        main_where_clauses, main_params = [], []
        
        for i, group in enumerate(filter_groups):
            group_conditions_sql, group_params_list = [], []
            logic_within = group.get("logic_operator_within_group", "AND").upper()
            if not group["conditions"]: continue
            
            for condition in group["conditions"]:
                sql_part, params = _build_sql_condition(condition, alias=f"IA{i}")
                group_conditions_sql.append(sql_part)
                group_params_list.extend(params)
            
            if group_conditions_sql:
                main_where_clauses.append(f"EXISTS (SELECT 1 FROM Identity_Attributes AS IA{i} WHERE IA{i}.identity_id = T.id AND ({f' {logic_within} '.join(group_conditions_sql)}))")
                main_params.extend(group_params_list)

        if not main_where_clauses:
            print("No valid conditions built. No action taken."); return

        select_filtered_ids_query = f"SELECT T.id FROM Identities AS T WHERE {' AND '.join(main_where_clauses) if logical_operator_between_groups.upper() == 'AND' else ' OR '.join(main_where_clauses)}"
        cursor.execute(select_filtered_ids_query, main_params)
        filtered_primary_ids_tuples = cursor.fetchall()
        
        if not filtered_primary_ids_tuples:
            print("No identities found matching the filter criteria. Aborting."); return
        
        filtered_primary_ids = [item[0] for item in filtered_primary_ids_tuples]
        print(f"-> Found {len(filtered_primary_ids)} identities matching the filter.")

        # ===================================================================
        # === Step 1a: THE FIX - A simple, robust way to get the UIDs ===
        # ===================================================================
        print("  - Fetching corresponding UIDs for the filtered identities...")
        if not filtered_primary_ids:
             filtered_uids = []
        else:
            uid_placeholder = ', '.join(['%s'] * len(filtered_primary_ids))
            # Directly query the Identities table with the IDs we just found
            uid_query = f"SELECT id FROM Identities WHERE id IN ({uid_placeholder})"
            cursor.execute(uid_query, filtered_primary_ids)
            filtered_uids = [item[0] for item in cursor.fetchall()]
        print(f"  -> Successfully fetched {len(filtered_uids)} corresponding UIDs.")


        # --- Step 2: Truncate all _Filtered tables ---
        print("\n--- Step 2: Truncating all _Filtered tables ---")
        filtered_tables = [
            "Identities_Filtered", "Identity_Accounts_Filtered", "Identity_Attributes_Filtered",
            "IdentityRoleAssignments_Filtered", "IdentityAccessProfileAssignments_Filtered",
            "IdentityEffectiveEntitlements_Filtered", "IdentityEntitlementAssignments_Filtered"
        ]
        for table in filtered_tables:
            cursor.execute(f"TRUNCATE TABLE {table}")
            print(f"  - Truncated {table}")

        # --- Step 3: Bulk copy data for the filtered IDs ---
        print("\n--- Step 3: Bulk copying data for filtered identities ---")
        
        id_placeholder = ', '.join(['%s'] * len(filtered_primary_ids))
        uid_placeholder = ', '.join(['%s'] * len(filtered_uids))
        
        copy_configs = [
            (f"INSERT INTO Identities_Filtered SELECT * FROM Identities WHERE id IN ({id_placeholder})", filtered_primary_ids, "Identities"),
            (f"INSERT INTO Identity_Accounts_Filtered SELECT * FROM Identity_Accounts WHERE identity_id IN ({id_placeholder})", filtered_primary_ids, "Identity_Accounts"),
            (f"INSERT INTO Identity_Attributes_Filtered SELECT * FROM Identity_Attributes WHERE identity_id IN ({id_placeholder})", filtered_primary_ids, "Identity_Attributes"),
            (f"INSERT INTO IdentityRoleAssignments_Filtered SELECT * FROM IdentityRoleAssignments WHERE identity_id IN ({id_placeholder})", filtered_primary_ids, "IdentityRoleAssignments"),
            (f"INSERT INTO IdentityAccessProfileAssignments_Filtered SELECT * FROM IdentityAccessProfileAssignments WHERE identity_id IN ({id_placeholder})", filtered_primary_ids, "IdentityAccessProfileAssignments"),
            (f"INSERT INTO IdentityEffectiveEntitlements_Filtered SELECT * FROM IdentityEffectiveEntitlements WHERE identity_id IN ({id_placeholder})", filtered_primary_ids, "IdentityEffectiveEntitlements"),
            (f"INSERT INTO IdentityEntitlementAssignments_Filtered SELECT * FROM IdentityEntitlementAssignments WHERE identity_id IN ({id_placeholder})", filtered_primary_ids, "IdentityEntitlementAssignments")
        ]

        for query, params, table_name in copy_configs:
            if not params:
                print(f"  - Skipping {table_name}, no IDs to filter by.")
                continue
            print(f"  - Copying data for {table_name}...")
            cursor.execute(query, params)
            print(f"  -> Copied {cursor.rowcount} records.")
            
        db_connection.commit()
        print("\nFilter and copy process completed successfully.")

    except Error as e:
        print(f"MySQL database error: {e}")
        if db_connection. db_connection.rollback()
    finally:
        if db_connection.and db_connection.is_connected():
            db_connection.close(); print("MySQL connection closed.")

# --- Example Usage ---
if __name__ == "__main__":
    db_configuration = {
        'host': 'localhost',
        'user': 'root',
        'password': 'password',
        'database': 'bundleBuilder'
    }
    
    filter_set = [
        {
            "conditions": [
                {"field": "attribute_name", "operator": "EQ", "value": "cloudLifecycleState"},
                {"field": "attribute_value", "operator": "EQ", "value": "active"}
            ],
            "logic_operator_within_group": "AND"
        }
    ]
    
    print("\n--- Running filter for active identities ---")
    filter_and_copy_all_identity_data(db_configuration, filter_set, logical_operator_between_groups="AND")
