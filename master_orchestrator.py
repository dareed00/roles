# master_orchestrator.py

import subprocess
import os
import sys

# --- Configuration ---
# Define the base path of your project. Assumes this script is in the root.
# os.path.dirname(os.path.abspath(__file__)) gets the directory of the current script.
PROJECT_BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# ==============================================================================
# === THE COMPLETE, ORDERED WORKFLOW ===
# ==============================================================================
# This list defines every step, its directory, and whether it is active.
# The sequence is based on the dependencies we have built:
# 1. Fetch raw data from the source.
# 2. Bulk load raw data into the main database tables.
# 3. Filter the raw data into the '_Filtered' tables.
# 4. Update the main 'entitlements' table with correct population counts from filtered data.
# 5. Generate attribute-based populations and correlations.
# 6. Analyze attribute communities (Attribute-Based Role Mining).
# 7. Generate entitlement-based similarities.
# 8. Analyze entitlement communities (Entitlement-Based Role Mining).
# 9. (Optional) Compute final statistics.
WORKFLOW_STEPS = [
    ### --- STAGE 1: Data Fetching and Raw Loading ---
  #XXX {"dir": "UploadDataToDB", "script": "fetch_entitlements_to_json.py", "active": True},
  #XXX {"dir": "UploadDataToDB", "script": "fetch_access_profiles_to_json.py", "active": True},
  #XXX {"dir": "UploadDataToDB", "script": "fetch_roles_to_json.py", "active": True},
  #XXX {"dir": "UploadDataToDB", "script": "fetch_identities_to_json.py", "active": True},
  #XXX {"dir": "UploadDataToDB", "script": "fetch_identity_assignments_to_json.py", "active": True},
  #XXX {"dir": "FetchAuditEvents", "script": "fetch_audit_events_to_json.py", "active": True},
  {"dir": "UploadDataToDB", "script": "UploadEmpower.py", "active": True},
   #XXX{"dir": "UploadDataToDB", "script": "master_bulk_loader.py", "active": True},
   #XXX{"dir": "FetchAuditEvents", "script": "bulk_upload_audit_events.py", "active": True},
   #XXX{"dir": "FetchAuditEvents", "script": "update_entity_audit_dates.py", "active": True},
     
    ### --- STAGE 2: Compute Effective Access ---
  #XXX {"dir": "PopulateEffectiveAccess", "script": "compute_current_role_model_effective_role_access.py", "active": True},
  #XXX {"dir": "PopulateEffectiveAccess", "script": "compute_effective_identity_access.py", "active": True},
 
    ###--- STAGE 3: Data Filtering and Preparation ---
  #XXX {"dir": "UploadDataToDB", "script": "filter_and_copy_identity_data.py", "active": True}, # Assuming you placed it here

   #XXX  {"dir": "ComputeSimilarity", "script": "populate_tripartite_graph.py", "active": True},
   #XXX  {"dir": "ComputeSimilarity", "script": "mine_compound_roles.py", "active": True},
   #XXX  {"dir": "ComputeSimilarity", "script": "find_exact_attribute_correlations.py", "active": True},
   #XXX  {"dir": "ComputeSimilarity", "script": "find_exact_attribute_unions_4way.py", "active": True},  
   #XXX  {"dir": "ComputeSimilarity", "script": "find_exact_attribute_combinations.py", "active": True},
     #XXX     {"dir": "ComputeSimilarity", "script": "find_fuzzy_attribute_combinations.py", "active": True},
     #XXX     {"dir": "ComputeSimilarity", "script": "find_fuzzy_entitlement_bundles.py", "active": True},
     #XXX     {"dir": "ComputeSimilarity", "script": "synthesize_it_roles.py", "active": True},
     #XXX     {"dir": "SuggestRoles", "script": "synthesize_suggested_roles.py", "active": True},
    
    # 4. Compare Suggested vs. Approved and flag already_in_role in MySQL
     #XXX     {"dir": "ComputeSimilarity", "script": "compare_suggested_vs_approved.py", "active": True},
     #XXX     {"dir": "Report", "script": "generate_suggested_it_roles_pdf.py", "active": True},
     # 5. Re-generate the PDF Catalog with Delta Fading
     #XXX     {"dir": "Report", "script": "generate_suggested_roles_pdf.py", "active": True},
     #XXX     {"dir": "Report", "script": "generate_executive_dashboard_pdf.py", "active": True},
    #6 generate workbook and pdf
     #XXX     {"dir": "Report", "script": "generate_role_approval_workbook.py", "active": True},
   #XXX   {"dir": "Injest", "script": "import_role_approvals_from_excel.py", "active": True},
    
    #7 when complete, load workbook
   #XXX   {"dir": "Deploy", "script": "publish_approved_roles_to_model.py", "active": True},
    
    #8 look for IT roles and overlap of them inside business roles
    #XXX  {"dir": "ComputeSimilarity", "script": "detect_role_hierarchy_overlap.py", "active": True},
    
    #9 build isc json roles document
    #XXX  {"dir": "Deploy", "script": "generate_isc_it_role_payloads.py", "active": True},
   
   
#10 deploy roles to isc puts and patches
   #XXX   {"dir": "Deploy", "script": "execute_isc_it_role_deployment.py", "active": True},

    ### --- STAGE 5: Other Analyses (Based on your provided script) ---
    # {"dir": "CreateStatistics", "script": "compute_statistics.py", "active": True},
    # {"dir": "CreateStatistics", "script": "compute_entitlement_profiles.py", "active": True},
    # {"dir": "ComputeSimilarity", "script": "build_unified_graph_roles.py", "active": True},
   

    ### --- STAGE 4: Entitlement-Based Role Mining ---
    #OLD Note: Renamed your script for clarity to avoid conflict with the other Louvain analysis
    # {"dir": "MineRoles", "script": "compute_entitlement_similarity.py", "active": True}, # Your original tracing script
    # {"dir": "MineRoles", "script": "generate_entitlement_graph_edges.py", "active": True},
    # {"dir": "MineRoles", "script": "analyze_entitlement_communities.py", "active": True},
    # {"dir": "MineRoles", "script": "analyze_and_load_potential_roles.py", "active": True},    
    # {"dir": "MineRoles", "script": "generate_entitlement_to_attribute_correlations.py", "active": True},
    # {"dir": "MineRoles", "script": "generate_attribute_graph_edges.py", "active": True},
    # {"dir": "MineRoles", "script": "analyze_attribute_communities.py", "active": True},
    # {"dir": "MineRoles", "script": "analyze_and_load_potential_attribute_roles.py", "active": True},
    #END OLD
   
   
   
   
   
   
            #OLD{"dir": "PopulateEffectiveAccess", "script": "update_entitlement_populations.py", "active": True}, # This MUST run after filtering
         #OLD{"dir": "MineRoles", "script": "generate_and_load_populations.py", "active": True}, # This depends on the filtered attribute data

   
      #XXX   {"dir": "Report", "script": "generate_exact_unions_pdf.py", "active": True},
    #            {"dir": "Report", "script": "generate_attribute_driven_report.py", "active": True},
   ## {"dir": "Report", "script": "generate_excel_report.py", "active": True},
   ## {"dir": "Report", "script": "generate_role_report.py", "active": True},
    
  #  {"dir": "ActiveAlerting", "script": "trigger_bundle_suggestion.py", "active": True},
  #  {"dir": "ActiveAlerting", "script": "trigger_near_correlation_suggestion.py", "active": True},
  #  {"dir": "ActiveAlerting", "script": "trigger_dormant_entitlement_review.py", "active": True},
  #  {"dir": "ActiveAlerting", "script": "trigger_dormant_bundle_review.py", "active": True},
  #  {"dir": "ActiveAlerting", "script": "trigger_similar_bundle_suggestion.py", "active": True},
  #  {"dir": "ActiveAlerting", "script": "trigger_attribute_correlation_suggestion.py", "active": True}

]	

def run_script(directory, script_name):
    """Executes a single python script in the specified directory."""
    script_path = os.path.join(PROJECT_BASE_PATH, directory, script_name)
    working_directory = os.path.join(PROJECT_BASE_PATH, directory)
    
    # Check if the script actually exists
    if not os.path.exists(script_path):
        print(f"--- SKIPPING: Script not found at {script_path}")
        return

    print("----------------------------------------------------------------------")
    print(f"--- EXECUTING: {script_name} in /{directory}")
    print("----------------------------------------------------------------------")
    
    try:
        # Use subprocess.run to execute the script.
        # - check=True: This will raise a CalledProcessError if the script fails (returns a non-zero exit code).
        # - cwd: Sets the working directory for the script, just like 'cd'.
        # - sys.executable: Ensures we use the same Python interpreter that is running this master script.
        process = subprocess.run(
            [sys.executable, script_name],
            cwd=working_directory,
            check=True,
            text=True, # Captures output as text
            capture_output=False # Set to True if you want to suppress real-time output and print it later
        )
        # The script's output will be printed to the console in real-time.
        
    except subprocess.CalledProcessError as e:
        print(f"\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"!!! ERROR: Script '{script_name}' failed with exit code {e.returncode}.")
        print(f"!!! WORKFLOW HALTED.")
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        # Exit the entire orchestrator script immediately upon failure.
        sys.exit(1)
    except FileNotFoundError:
        print(f"\n!!! ERROR: Could not find the command '{sys.executable}'. Is Python in your PATH?")
        sys.exit(1)

def main():
    """Runs the entire defined workflow."""
    print("======================================================================")
    print("=== Starting Master Role Mining Orchestrator ===")
    print("======================================================================")

    for i, step in enumerate(WORKFLOW_STEPS):
        if step["active"]:
            print(f"\n>>> Workflow Step {i+1}/{len(WORKFLOW_STEPS)}")
            run_script(step["dir"], step["script"])
        else:
            print(f"\n>>> Workflow Step {i+1}/{len(WORKFLOW_STEPS)} (SKIPPED): {step['script']}")

    print("\n======================================================================")
    print("=== Master Role Mining Orchestrator Completed Successfully! ===")
    print("======================================================================")


if __name__ == "__main__":
    main()

