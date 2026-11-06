# generate_attribute_sheet.py

from openpyxl.styles import Alignment
from collections import defaultdict
import report_utils as utils


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

def generate_sheet(wb, cursor, config):
    """Generates the 'Attribute-Driven Candidates' worksheet."""
    print("\n--- Generating Excel Report: Section 2 (Attribute-Driven) ---")
    ws = wb.create_sheet("Attribute-Driven Candidates")
    
    # --- THE FIX IS HERE: Using the full, correct list of headers ---
    headers = ["Rank", "Suggested Role Name", "Driving Attribute", "Attribute Population", "Explained Entitlement", "Entitlement Source", "Entitlement Population", "Correlation", "Correlation Analysis", "Direct Assignments", "Indirect Assignments", "Already Included Roles", "Already Included Access Profiles", "Missing Entitlement (Users)", "Missing Attribute (Users)"]
    descriptions = ["The rank...", "A machine-generated name...", "The specific attribute...", "The total number...", "The specific entitlement...", "The source application...", "The total number...", "The qualitative and quantitative...", "Automated, human-readable...", "The number of users...", "The number of users...", "A list of existing Roles...", "A list of existing Access Profiles...", "Users who HAVE...", "Users who HAVE..."]

    for i, header_text in enumerate(headers, 1):
        utils.style_header(ws.cell(row=1, column=i), header_text)
        utils.style_description(ws.cell(row=2, column=i), descriptions[i-1])

    row_idx = 3
    cursor.execute("SELECT * FROM Entitlement_to_Attribute_Correlations WHERE jaccard_score >= %s", (config['NEAR_MATCH_THRESHOLD'],))
    all_correlations = cursor.fetchall()
    correlations_by_attribute = defaultdict(list)
    for corr in all_correlations:
        correlations_by_attribute[(corr['attribute_name'], corr['attribute_value'])].append(corr)
    sorted_candidates = sorted(correlations_by_attribute.items(), key=lambda item: max(c['jaccard_score'] for c in item[1]), reverse=True)

    rank = 0
    for i, ((attr_name, attr_value), entitlements) in enumerate(sorted_candidates[:config['TOP_N_CANDIDATES']]):
        rank += 1
        merge_start_row, num_entitlements = row_idx, len(entitlements)
        
        suggested_name = f"All {attr_value}s"
        ws.cell(row=row_idx, column=1).value = rank
        ws.cell(row=row_idx, column=2).value = suggested_name
        ws.cell(row=row_idx, column=3).value = f"({attr_name}, '{attr_value}')"
        ws.cell(row=row_idx, column=4).value = entitlements[0]['attribute_population']
        
        for col in range(1, 5):
             ws.cell(row=row_idx, column=col).alignment = Alignment(vertical="top")

        for ent in sorted(entitlements, key=lambda x: x['jaccard_score'], reverse=True):
            ws.cell(row=row_idx, column=5).value = ent['entitlement_name']
            ws.cell(row=row_idx, column=6).value = ent['entitlement_source']
            ws.cell(row=row_idx, column=7).value = ent['entitlement_population']
            
            analysis = utils.get_correlation_analysis(ent['jaccard_score'], ent['attribute_population'])
            ws.cell(row=row_idx, column=8).value = analysis['title']
            ws.cell(row=row_idx, column=9).value = analysis['details']
            
            breakdown = utils.get_assignment_breakdown(cursor, ent['entitlement_id'], ent['entitlement_population'])
            ws.cell(row=row_idx, column=10).value = breakdown['direct']
            ws.cell(row=row_idx, column=11).value = breakdown['indirect']
            
            parent_bundles = utils.get_parent_bundles(cursor, ent['entitlement_id'])
            if parent_bundles['roles']:
                ws.cell(row=row_idx, column=12).value = ', '.join(parent_bundles['roles'])
            if parent_bundles['access_profiles']:
                ws.cell(row=row_idx, column=13).value = ', '.join(parent_bundles['access_profiles'])
            
            ent_users = utils.get_entitlement_population_ids(cursor, ent['entitlement_id'])
            attr_users = utils.get_attribute_population_ids(cursor, attr_name, attr_value)
            in_attr_only = attr_users - ent_users
            in_ent_only = ent_users - attr_users
            if in_attr_only:
                ws.cell(row=row_idx, column=14).value = utils.format_delta_text(utils.get_user_context(cursor, in_attr_only), in_attr_only)
            if in_ent_only:
                ws.cell(row=row_idx, column=15).value = utils.format_delta_text(utils.get_user_context(cursor, in_ent_only), in_ent_only)

            for col_num in [9, 12, 13, 14, 15]:
                ws.cell(row=row_idx, column=col_num).alignment = Alignment(wrap_text=True, vertical="top")
            row_idx += 1
        
        if num_entitlements > 1:
            merge_end_row = row_idx - 1
            for col in range(1, 5):
                ws.merge_cells(start_row=merge_start_row, start_column=col, end_row=merge_end_row, end_column=col)
    
    utils.auto_fit_columns(ws)
