import pandas as pd
import os
from typing import List, Dict, Any

def _build_filter_expression(df: pd.DataFrame, condition: Dict[str, Any], temp_col_suffix: str) -> pd.Series:
    """
    Builds a single pandas Series boolean expression for one filter condition.
    Handles case-insensitivity and different operators.
    """
    column = condition['column']
    operator = condition['operator'].upper()
    value = condition['value']
    
    if column not in df.columns:
        raise ValueError(f"Filter column '{column}' not found in the Excel file.")

    # Create a temporary lowercase version of the column for case-insensitive comparisons
    temp_col_name = f"{column}_{temp_col_suffix}"
    df[temp_col_name] = df[column].astype(str).str.lower()
    
    if operator == "EQUALS":
        return df[temp_col_name] == str(value).lower()
    elif operator == "NOT_EQUALS":
        return df[temp_col_name] != str(value).lower()
    elif operator == "IN":
        # Ensure value is iterable and convert all elements to lowercase
        if not isinstance(value, (list, set, tuple)):
            raise ValueError(f"Operator 'IN' requires a list or set for value. Got: {type(value)}")
        lower_values = {str(v).lower() for v in value}
        return df[temp_col_name].isin(lower_values)
    elif operator == "NOT_IN":
        if not isinstance(value, (list, set, tuple)):
            raise ValueError(f"Operator 'NOT_IN' requires a list or set for value. Got: {type(value)}")
        lower_values = {str(v).lower() for v in value}
        return ~df[temp_col_name].isin(lower_values)
    elif operator == "CONTAINS":
        return df[temp_col_name].str.contains(str(value).lower(), na=False)
    elif operator == "GREATER_THAN":
        return pd.to_numeric(df[column], errors='coerce') > value
    elif operator == "LESS_THAN":
        return pd.to_numeric(df[column], errors='coerce') < value
    else:
        raise ValueError(f"Unsupported operator: {operator}")

def filter_excel_users_complex(
    excel_file_path: str,
    filter_config: Dict[str, Any],
    output_dir: str = '.'
) -> None:
    """
    Reads an Excel file and filters users based on multiple complex conditions (AND/OR logic),
    then saves the filtered users into a new Excel file.

    Args:
        excel_file_path (str): The path to the input Excel file.
        filter_config (Dict[str, Any]): A dictionary defining the filter logic and conditions.
                                       Example:
                                       {
                                           "logic": "AND", # or "OR"
                                           "conditions": [
                                               {"column": "cloudLifecycleState", "operator": "EQUALS", "value": "active"},
                                               {"column": "type", "operator": "EQUALS", "value": "Employee"}
                                           ]
                                       }

        output_dir (str): The directory where the output Excel file will be saved.
                          Defaults to the current directory.
    """
    try:
        df = pd.read_excel(excel_file_path)
    except FileNotFoundError:
        print(f"Error: The Excel file '{excel_file_path}' was not found.")
        return
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return

    if not filter_config or "logic" not in filter_config or "conditions" not in filter_config:
        print("Error: Invalid filter_config. Must contain 'logic' and 'conditions'.")
        return

    filter_logic = filter_config['logic'].upper()
    conditions_list = filter_config['conditions']

    if not conditions_list:
        print("No conditions specified in filter_config.")
        return

    # Build individual boolean series for each condition
    boolean_series_list = []
    for i, condition in enumerate(conditions_list):
        try:
            boolean_series_list.append(_build_filter_expression(df, condition, f"temp_{i}"))
        except ValueError as e:
            print(f"Error in filter condition '{condition}': {e}")
            return # Stop processing if a condition is invalid

    # Combine boolean series using AND or OR logic
    if filter_logic == "AND":
        final_filter = pd.Series(True, index=df.index)
        for series in boolean_series_list:
            final_filter &= series
    elif filter_logic == "OR":
        final_filter = pd.Series(False, index=df.index)
        for series in boolean_series_list:
            final_filter |= series
    else:
        print(f"Error: Unsupported filter logic '{filter_logic}'. Must be 'AND' or 'OR'.")
        return

    filtered_df = df[final_filter].copy() # Use .copy() to avoid SettingWithCopyWarning

    # Remove temporary columns
    temp_cols = [col for col in df.columns if col.startswith(f"{col.split('_temp_')[0]}_temp_")]
    df.drop(columns=temp_cols, errors='ignore', inplace=True)
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(excel_file_path))[0]
    
    # Generate a descriptive filename
    filter_description = "_".join([f"{c['column']}_{c['operator']}_{str(c['value']).replace(' ', '').replace('/', '-')}" for c in conditions_list])
    #output_file_name = f"{base_name}_filtered_{filter_logic}_{filter_description[:100]}.xlsx" # Truncate long descriptions
    output_file_name = f"RevisedAccessFile.xlsx"
    output_path = os.path.join(output_dir, output_file_name)

    if not filtered_df.empty:
        filtered_df.to_excel(output_path, index=False)
        print(f"Successfully filtered {len(filtered_df)} users to: {output_path}")
    else:
        print("No users found matching the specified filter criteria.")
    
# --- How to use the function ---
if __name__ == "__main__":
    # IMPORTANT: Replace 'path/to/your/original_excel_file.xlsx' with the actual path
    original_excel_file = '/Users/dana.reed/RoleMiner/Files/my_AccessDemo.xlsx'
    output_dir='/Users/dana.reed/RoleMiner/Output'
    
    # Example 1: Active Employees (AND logic)
    filter_active_employees = {
        "logic": "AND",
        "conditions": [
            {"column": "cloudLifecycleState", "operator": "EQUALS", "value": "active"},
            {"column": "type", "operator": "EQUALS", "value": "Employee"},
            {"column":"Access Type", "operator": "EQUALS", "value": "ENTITLEMENT"}
        ]
    }
    print("\n--- Filtering for Active Employees ---")
    filter_excel_users_complex(original_excel_file, filter_active_employees,output_dir)

    # Example 2: Finance OR HR Department users (OR logic)
   # filter_finance_hr = {
   #     "logic": "OR",
   #     "conditions": [
   #         {"column": "department", "operator": "EQUALS", "value": "Finance"},
   #         {"column": "department", "operator": "EQUALS", "value": "HR"}
   #     ]
   # }
   # print("\n--- Filtering for Finance OR HR Department users ---")
   # filter_excel_users_complex(original_excel_file, filter_finance_hr)

    # Example 3: Users in USA or Canada, AND jobTitle contains 'Manager'
   # filter_country_manager = {
   #     "logic": "AND",
   #     "conditions": [
    #        {"column": "country", "operator": "IN", "value": ["USA", "Canada"]},
    #        {"column": "jobTitle", "operator": "CONTAINS", "value": "Manager"}
    #    ]
    #}
    #print("\n--- Filtering for USA/Canada Managers ---")
    #filter_excel_users_complex(original_excel_file, filter_country_manager)
    
    # Example 4: Inactive users NOT of type 'Contractor'
   # filter_inactive_not_contractor = {
    #    "logic": "AND",
    #    "conditions": [
    #        {"column": "cloudLifecycleState", "operator": "EQUALS", "value": "inactive"},
    #        {"column": "type", "operator": "NOT_EQUALS", "value": "Contractor"}
   #     ]
   # }
   # print("\n--- Filtering for Inactive users NOT Contractor ---")
   # filter_excel_users_complex(original_excel_file, filter_inactive_not_contractor)
