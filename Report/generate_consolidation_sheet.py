# generate_consolidation_sheet.py

from openpyxl.styles import Alignment, Font, PatternFill

from collections import defaultdict
import report_utils as utils

def style_sub_header(cell, text):
    """Styles the sub-header row for entitlements."""
    cell.value = text
    cell.font = Font(bold=True, color="4F81BD")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

def generate_sheet(wb, cursor, config):
    """Generates the 'Role Consolidation Candidates' worksheet with a clean, grouped, and merged structure."""
    print("--- Generating Excel Report: Section 1 (Role Consolidation) ---")
    ws = wb.create_sheet("Role Consolidation Candidates")

    headers = ["Rank", "Community ID", "Recommendation Score", "Avg. Cohesion", "Core Population (Users with ALL Entitlements)"]
    descriptions = [
        "The rank of this potential role.", "The unique ID for this cluster.", "A score indicating the strength of this candidate.",
        "The average similarity between all entitlements in this community.", "The list of users who have ALL entitlements in this community."
    ]
    
    for i, header_text in enumerate(headers, 1):
        utils.style_header(ws.cell(row=1, column=i), header_text)
        utils.style_description(ws.cell(row=2, column=i), descriptions[i-1])

    row_idx = 3
    cursor.execute("SELECT * FROM Potential_Roles ORDER BY recommendation_score DESC LIMIT %s", (config['TOP_N_CANDIDATES'],))
    potential_roles = cursor.fetchall()

    for i, role in enumerate(potential_roles):
        # --- THE FIX IS HERE: Track start row for merging ---
        merge_start_row = row_idx
        
        cursor.execute("SELECT * FROM Potential_Role_Entitlements WHERE potential_role_id = %s", (role['id'],))
        members = cursor.fetchall()
        all_member_user_sets = [utils.get_entitlement_population_ids(cursor, m['entitlement_id']) for m in members]
        core_population_ids = set.intersection(*all_member_user_sets) if all_member_user_sets else set()

        # --- Write the Primary Info Row ---
        ws.cell(row=row_idx, column=1).value = i + 1
        ws.cell(row=row_idx, column=2).value = role['community_id']
        ws.cell(row=row_idx, column=3).value = f"{role['recommendation_score']:.2f}"
        cohesion_analysis_text = utils.get_cohesion_analysis(role['avg_internal_jaccard'])
        ws.cell(row=row_idx, column=4).value = cohesion_analysis_text
       
   
        
        if core_population_ids:
            ws.cell(row=row_idx, column=5).value = utils.format_delta_text(utils.get_user_context(cursor, core_population_ids), core_population_ids)
        else:
            ws.cell(row=row_idx, column=5).value = "No single user has all entitlements."
        
        ws.cell(row=row_idx, column=5).alignment = Alignment(wrap_text=True, vertical="top")
        row_idx += 1

        # --- Write the Sub-Header ---
        sub_headers = ["Member Entitlement", "Source", "Population", "Direct", "Indirect", "Already Included Roles", "Already Included Access Profiles", "Outliers (Users Missing This Entitlement)"]
        for j, text in enumerate(sub_headers, 1):
            style_sub_header(ws.cell(row=row_idx, column=j+1), text)
        row_idx += 1

        # --- Write Each Member Entitlement Row ---
        community_users = set.union(*all_member_user_sets) if all_member_user_sets else set()
        # Reset the user sets for the loop
        all_member_user_sets = [utils.get_entitlement_population_ids(cursor, m['entitlement_id']) for m in members] 
        for member_idx, member in enumerate(members):
            ws.cell(row=row_idx, column=2).value = member['entitlement_name']
            ws.cell(row=row_idx, column=3).value = member['entitlement_source']
            ws.cell(row=row_idx, column=4).value = member['population_size']
            
            breakdown = utils.get_assignment_breakdown(cursor, member['entitlement_id'], member['population_size'])
            ws.cell(row=row_idx, column=5).value = breakdown['direct']
            ws.cell(row=row_idx, column=6).value = breakdown['indirect']

            parent_bundles = utils.get_parent_bundles(cursor, member['entitlement_id'])
            ws.cell(row=row_idx, column=7).value = ", ".join(parent_bundles['roles']) if parent_bundles['roles'] else "None"
            ws.cell(row=row_idx, column=8).value = ", ".join(parent_bundles['access_profiles']) if parent_bundles['access_profiles'] else "None"
            
            current_ent_users = all_member_user_sets[member_idx]
            missing_users = community_users - current_ent_users
            if missing_users:
                 ws.cell(row=row_idx, column=9).value = utils.format_delta_text(utils.get_user_context(cursor, missing_users), missing_users)
                 ws.cell(row=row_idx, column=9).alignment = Alignment(wrap_text=True, vertical="top")
            
            row_idx += 1
        
        # --- THE FIX IS HERE: Perform the merge operation ---
        merge_end_row = row_idx - 1
        if merge_end_row > merge_start_row:
            ws.merge_cells(start_row=merge_start_row, start_column=1, end_row=merge_end_row, end_column=1)
            # Apply vertical alignment to the merged cell
            ws.cell(row=merge_start_row, column=1).alignment = Alignment(vertical="top", horizontal="center")

        row_idx += 1 # Add blank row for spacing

    utils.auto_fit_columns(ws)
