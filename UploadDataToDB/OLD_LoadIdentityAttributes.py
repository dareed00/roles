import pandas as pd
import mysql.connector
from mysql.connector import Error

def populate_identity_attributes_from_excel(excel_file_path, db_config):
    """
    Reads an Excel file, iterates through each column (excluding a blacklist),
    and loads the data into the 'IdentityAttributes' MySQL table in the format
    (UID, AttributeName, AttributeValue).

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

        # Define columns to exclude from being treated as identity attributes
        excluded_columns = {
            'Access Type', 'Source', 'Access Display Name', 'Entitlement',
            'Access Description', 'Access Owner Name'
        }

        # The UID column is crucial
        if 'UID' not in df.columns:
            raise ValueError("Excel file must contain a 'UID' column.")

        # Identify attribute columns by excluding UID and the predefined blacklist
        attribute_columns = [col for col in df.columns if col != 'UID' and col not in excluded_columns]

        if not attribute_columns:
            print("No attribute columns found after excluding 'UID' and blacklisted columns. Nothing to process.")
            return

        print(f"Identified attribute columns to process: {', '.join(attribute_columns)}")

        # Establish database connection
        print("Connecting to MySQL database...")
        cnx = mysql.connector.connect(**db_config)
        cursor = cnx.cursor()
        print("Successfully connected to MySQL database.")

        # SQL INSERT statement using INSERT IGNORE to skip duplicates
        # The UNIQUE constraint on (UID, AttributeName, AttributeValue) will handle this.
        insert_query = """
        INSERT IGNORE INTO IdentityAttributes (UID, AttributeName, AttributeValue)
        VALUES (%s, %s, %s)
        """

        records_to_insert = []
        for index, row in df.iterrows():
            uid_value = row['UID']
            if pd.isna(uid_value): # Skip rows if UID is missing
                print(f"Skipping row {index} due to missing UID.")
                continue

            # Ensure UID is string for database
            uid_value = str(uid_value)

            for col_name in attribute_columns:
                attribute_value = row[col_name]
                # Only insert if the attribute value is not null/NaN
                if pd.notna(attribute_value):
                    records_to_insert.append((uid_value, col_name, str(attribute_value)))

        if records_to_insert:
            print(f"Preparing to insert {len(records_to_insert)} records into 'IdentityAttributes' table...")
            cursor.executemany(insert_query, records_to_insert)
            cnx.commit()
            print(f"Successfully inserted/ignored {cursor.rowcount} records.")
        else:
            print("No valid identity attribute records found to insert after processing.")

    except FileNotFoundError:
        print(f"Error: The file '{excel_file_path}' was not found.")
    except ValueError as ve:
        print(f"Data processing error: {ve}")
    except Error as e:
        print(f"MySQL database error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if 'cnx' in locals() and cnx.is_connected():
            cursor.close()
            cnx.close()
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
    # Example for Windows: excel_file = r"C:\Users\YourUser\Documents\your_identity_data.xlsx"
    # Example for macOS/Linux: excel_file = "/Users/YourUser/Documents/your_identity_data.xlsx"
    excel_file = '/Users/dana.reed/RoleMiner/files/my_AccessDemo_active_users.xlsx'  # <<< REMEMBER TO CHANGE THIS!

    populate_identity_attributes_from_excel(excel_file, db_configuration)
