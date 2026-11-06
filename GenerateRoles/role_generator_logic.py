#!/usr/bin/env python3
# role_generator_logic.py

import os
import sys
import json
from typing import Dict, List, Any, Tuple

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

# Importing configuration metadata from your root-level config.py file
from config import ROLE_OWNER_NAME, ROLE_COMMENTS, ROLE_ENABLED_DEFAULT, ROLE_REQUESTABLE_DEFAULT


# ==============================================================================
# 3. ROLE GENERATION LOGIC
# ==============================================================================
def generate_sailpoint_role_json_from_exact_correlations() -> List[Dict[str, Any]]:
    """
    Queries the 'exact_correlations' table, groups the results, and generates
    SailPoint ISC Role JSON objects based on the specified naming, entitlement,
    criteria, and metadata conventions.

    Returns:
        List[Dict[str, Any]]: A list of generated SailPoint Role JSON objects.
    """
    db_connection = None
    cursor = None
    generated_roles: List[Dict[str, Any]] = []

    try:
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)
            print("Connected to MySQL database. Querying 'exact_correlations'...")
            
            query = (
                "SELECT primary_grouping_column, primary_value, attribute_value, access_source_name "
                "FROM exact_correlations "
                "ORDER BY primary_grouping_column, primary_value;"
            )
            cursor.execute(query)
            records = cursor.fetchall()

            if not records:
                print("No exact correlations found in the database to generate roles.")
                return []

            roles_to_generate: Dict[Tuple[str, str], Dict[str, Any]] = {}

            for row in records:
                primary_grouping_column = row['primary_grouping_column']
                primary_value = row['primary_value']
                attribute_value = row['attribute_value']
                access_source_name = row['access_source_name']

                role_key = (primary_grouping_column, primary_value)

                if role_key not in roles_to_generate:
                    # Initialize a new role structure for this group
                    role_name = f"{primary_value} ({primary_grouping_column}) Access"
                    role_description = (
                        f"Auto-generated role for {primary_value} based on "
                        f"exact correlations from {primary_grouping_column}."
                    )

                    roles_to_generate[role_key] = {
                        "name": role_name,
                        "description": role_description,
                        "type": "ROLE",
                        "owner": {
                            "type": "IDENTITY",
                            "name": ROLE_OWNER_NAME
                        },
                        "enabled": ROLE_ENABLED_DEFAULT,
                        "requestable": ROLE_REQUESTABLE_DEFAULT,
                        "accessProfiles": [],
                        "entitlements": [],
                        "comments": ROLE_COMMENTS,
                        "criteria": {
                            "type": "STANDARD",
                            "criteriaList": [
                                [
                                    {
                                        "type": "IDENTITY_ATTRIBUTE",
                                        "property": primary_grouping_column,
                                        "value": primary_value,
                                        "operation": "EQUALS"
                                    }
                                ]
                            ]
                        }
                    }

                # Add the entitlement to the current role's entitlements list
                entitlement_obj = {
                    "name": attribute_value,
                    "type": "ENTITLEMENT",
                    "source": {
                        "name": access_source_name,
                        "type": "SOURCE"
                    }
                }
                roles_to_generate[role_key]["entitlements"].append(entitlement_obj)

            generated_roles = list(roles_to_generate.values())
            print(f"\nGenerated {len(generated_roles)} SailPoint Role JSON objects in memory.")

    except Exception as e:
        print(f"An error occurred during role generation: {e}")
    finally:
        if db_connection:
            close_db_connection(db_connection, cursor)

    return generated_roles
