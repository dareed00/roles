# generate_excel_report.py

import json
from mysql.connector import Error
import openpyxl
from openpyxl.chart import BarChart, Reference

# Import our new modules
import report_utils as utils
import generate_consolidation_sheet
import generate_attribute_sheet

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

# --- Configuration is now managed here ---
CONFIG = {
    "TOP_N_CANDIDATES": 15,
    "NEAR_MATCH_THRESHOLD": 0.60,
    "OUTPUT_FILENAME": "Role_Engineering_Candidates_Report.xlsx"
}

def main():
    try:
        with open('config.json') as f: db_config = json.load(f)
    except FileNotFoundError:
        print("FATAL: config.json not found."); return

    db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True)
    
    try:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        # --- Generate Detailed Sheets by Calling Modules ---
        generate_consolidation_sheet.generate_sheet(wb, cursor, CONFIG)
        generate_attribute_sheet.generate_sheet(wb, cursor, CONFIG)

        # --- Generate Summary Sheet ---
        ws0 = wb.create_sheet("Summary Dashboard", 0)
        print("\n--- Generating Excel Report: Summary Dashboard ---")
        # (The logic to create stats and charts for the summary sheet goes here,
        # referencing the worksheets created by the other modules, e.g., wb["Role Consolidation Candidates"])
        
        # --- Final Save ---
        wb.save(CONFIG['OUTPUT_FILENAME'])
        print(f"\n--- Successfully generated Excel dashboard: {CONFIG['OUTPUT_FILENAME']} ---")

    except Error as e:
        print(f"    - DATABASE ERROR: {e}")
    finally:
        if cursor: cursor.close()
        if db_connection.and db_connection.is_connected(): db_connection.close(); print("Database connection closed.")

if __name__ == "__main__":
    main()
