import pandas as pd
import mysql.connector
from mysql.connector import Error
from typing import Dict, List, Any

# --- Database Configuration (UPDATE IF NECESSARY) ---
DB_CONFIG = {
    'host': 'localhost',
    'database': 'bundleBuilder',
    'user': 'root',
    'password': 'password',
    'port': 3306 # Default MySQL port
}

# --- Excel Column to Database Column Mapping ---
# Map Excel column names (keys) to their corresponding database column names (values).
# Ensure these Excel column names EXACTLY match your spreadsheet's headers (case-sensitive).
EXCEL_COLUMNS_TO_DB_MAP = {
    'UID': 'UID',
    'department': 'department',
    'Attribute Value Name': 'Attribute_Value_Name',
    'Access Source Name': 'Access_Source_Name',
    'type': 'type',
    'Is Manager': 'Is_Manager', # Note: Excel column name might have space, DB column name uses underscore
    'country': 'country',
    'jobTitle': 'jobTitle',
    'location': 'location'
    # Add any other columns from your Excel here that you want to upload
}

def upload_excel_to_db(excel_file_path: str) -> None:
    """
    Reads an Excel file and uploads its data into the `excel_raw_data` table
    in the `bundleBuilder` MySQL database.
    """
    db_connection = None
    try:
        # 1. Read Excel file
        print(f"Reading Excel file: {excel_file_path}")
        df = pd.read_excel(excel_file_path)
        print(f"Found {len(df)} rows in the Excel file.")

        # 2. Filter DataFrame to only include columns we intend to upload
        # and rename them to match DB column names
        df_to_upload = pd.DataFrame()
        missing_excel_cols = []
        for excel_col, db_col in EXCEL_COLUMNS_TO_DB_MAP.items():
            if excel_col in df.columns:
                df_to_upload[db_col] = df[excel_col]
            else:
                missing_excel_cols.append(excel_col)
        
        if missing_excel_cols:
            print(f"Warning: The following Excel columns specified in EXCEL_COLUMNS_TO_DB_MAP were not found in the file: {missing_excel_cols}")
            print("Skipping upload for these columns.")
        
        if df_to_upload.empty:
            print("No data to upload after checking for required columns.")
            return

        # 3. Connect to the database
        db_connection = mysql.connector.connect(**DB_CONFIG)
        if db_connection.is_connected():
            cursor = db_connection.cursor()
            print("Connected to MySQL database. Starting data upload...")

            # 4. Prepare SQL INSERT statement
            # Dynamically get column names from df_to_upload to match DB table order/names
            db_columns = df_to_upload.columns.tolist()
            placeholders = ', '.join(['%s'] * len(db_columns))
            column_names_sql = ', '.join([f'`{col}`' for col in db_columns]) # Quote column names to handle spaces if any
            
            insert_sql = f"INSERT INTO excel_raw_data ({column_names_sql}) VALUES ({placeholders})"

            # 5. Iterate through DataFrame and execute INSERT statements
            rows_uploaded = 0
            for index, row in df_to_upload.iterrows():
                # Convert pandas NaN to None for MySQL NULL
                data_tuple = tuple(None if pd.isna(x) else x for x in row.values)
                try:
                    cursor.execute(insert_sql, data_tuple)
                    rows_uploaded += 1
                except Error as err:
                    print(f"Error inserting row {index+1}: {err}")
                    # Optionally, you can log the row that caused the error:
                    # print(f"Problematic row data: {data_tuple}")
                    db_connection.rollback() # Rollback current transaction if an error occurs
                    raise # Re-raise to stop further processing if an error is critical
            
            db_connection.commit() # Commit all changes if no errors occurred
            print(f"Successfully uploaded {rows_uploaded} rows to `excel_raw_data` table.")

    except FileNotFoundError:
        print(f"Error: The Excel file '{excel_file_path}' was not found.")
    except pd.errors.EmptyDataError:
        print(f"Error: The Excel file '{excel_file_path}' is empty.")
    except Error as e:
        print(f"Database error during upload: {e}")
        if db_connection:
            db_connection.rollback() # Ensure rollback on general DB errors
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if db_connection and db_connection.is_connected():
            cursor.close()
            db_connection.close()
            print("MySQL connection closed.")

# --- How to use the function ---
if __name__ == "__main__":
    # IMPORTANT: Replace 'path/to/your/excel_file.xlsx' with the actual path to your Excel file
	excel_file = '/Users/dana.reed/RoleMiner/files/my_AccessDemo.xlsx'
	upload_excel_to_db(excel_file)
