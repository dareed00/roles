import pandas as pd
import mysql.connector
from mysql.connector import Error

def populate_entitlements_from_excel(excel_file_path, db_config):
    """
    Reads an Excel file, extracts 'Entitlement', 'Source', 'Access Description',
    and 'Access Owner Name' columns, filters for distinct 'Entitlement' and 'Source'
    combinations, and loads the data into the 'entitlements' MySQL table.

    Args:
        excel_file_path (str): The full path to the Excel file.
        db_config (dict): A dictionary containing database connection parameters
                          (host, user, password, database).
    """
    try:
        print(f"Reading Excel file from: {excel_file_path}")
        # Read the Excel file into a pandas DataFrame
        df = pd.read_excel(excel_file_path)
        print(f"Successfully read Excel file. Total rows: {len(df)}")

        # Define the columns to extract and rename them for the database table
        required_cols = {
            'Entitlement': 'entitlement_name',
            'Source': 'source_name',
            'Access Description': 'description',
            'Access Owner Name': 'owner_name'
        }

        # Check if all required columns exist in the DataFrame
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns in Excel file: {', '.join(missing_cols)}")

        # Select and rename columns
        df_selected = df[list(required_cols.keys())].rename(columns=required_cols)

        # Drop rows where 'entitlement_name' or 'source_name' might be missing,
        # as these are NOT NULL in your table.
        df_selected.dropna(subset=['entitlement_name', 'source_name'], inplace=True)
        print(f"After dropping rows with missing Entitlement/Source: {len(df_selected)} rows.")

        # Filter for distinct Entitlement + Source combinations
        # For 'description' and 'owner_name', if duplicates exist,
        # .drop_duplicates() will keep the first occurrence by default.
        df_distinct = df_selected.drop_duplicates(subset=['entitlement_name', 'source_name'])
        print(f"After filtering for distinct Entitlement + Source combinations: {len(df_distinct)} unique entries.")

        if df_distinct.empty:
            print("No distinct entitlement data to load after processing the Excel file.")
            return

        # Establish database connection
        print("Connecting to MySQL database...")
        db_connection = mysql.connector.connect(**db_config)
        cursor = db_connection.cursor()
        print("Successfully connected to MySQL database.")

        # SQL INSERT statement using INSERT IGNORE to skip duplicates
        # The UNIQUE constraint on (entitlement_name, source_name) will handle this.
        insert_query = """
        INSERT IGNORE INTO entitlements (entitlement_name, source_name, description, owner_name)
        VALUES (%s, %s, %s, %s)
        """

        records_to_insert = []
        for index, row in df_distinct.iterrows():
            # Convert NaN to None for database insertion
            description = row['description'] if pd.notna(row['description']) else None
            owner_name = row['owner_name'] if pd.notna(row['owner_name']) else None
            records_to_insert.append((row['entitlement_name'], row['source_name'], description, owner_name))

        if records_to_insert:
            print(f"Inserting {len(records_to_insert)} distinct records into the 'entitlements' table...")
            cursor.executemany(insert_query, records_to_insert)
            db_connection.commit()
            print(f"Successfully inserted/ignored {cursor.rowcount} records.")
        else:
            print("No records to insert after processing.")

    except FileNotFoundError:
        print(f"Error: The file '{excel_file_path}' was not found.")
    except ValueError as ve:
        print(f"Data processing error: {ve}")
    except Error as e:
        print(f"MySQL database error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if 'db_connection' in locals() and db_connection.is_connected():
            cursor.close()
            db_connection.close()
            print("MySQL connection closed.")

# Example Usage
if __name__ == "__main__":
    # --- IMPORTANT: Configure your database connection details here ---
    db_configuration = {
        'host': 'localhost',
        'user': 'root',
        'password': 'password',
        'database': 'bundleBuilder'
    }

    # --- IMPORTANT: Provide the full path to your Excel file here ---
    # Example for Windows: excel_file = r"C:\Users\YourUser\Documents\your_data.xlsx"
    # Example for macOS/Linux: excel_file = "/Users/YourUser/Documents/your_data.xlsx"
    excel_file = '/Users/dana.reed/RoleMiner/files/my_AccessDemo_active_users.xlsx'  # <<< REMEMBER TO CHANGE THIS!

    populate_entitlements_from_excel(excel_file, db_configuration)
