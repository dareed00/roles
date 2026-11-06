# main_upload_roles.py
import json
import os
from isc_api_client import SailPointAPIClient
from config import ISC_TENANT_URL, ISC_CLIENT_ID, ISC_CLIENT_SECRET, OUTPUT_DIRECTORY, OUTPUT_FILENAME

def main():
    """
    Main function to upload SailPoint Role JSON objects from a file to an ISC instance.
    """
    if ISC_CLIENT_ID == "YOUR_CLIENT_ID_HERE" or ISC_CLIENT_SECRET == "YOUR_CLIENT_SECRET_HERE":
        print("ERROR: Please update config.py with your actual ISC_CLIENT_ID and ISC_CLIENT_SECRET.")
        return

    json_file_path = os.path.join(OUTPUT_DIRECTORY, OUTPUT_FILENAME)

    if not os.path.exists(json_file_path):
        print(f"Error: Role JSON file not found at '{json_file_path}'. Please ensure it has been generated.")
        return

    print(f"Attempting to upload roles from '{json_file_path}' to SailPoint ISC tenant: {ISC_TENANT_URL}")

    try:
        # Load roles from the JSON file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            roles_to_upload = json.load(f)
        
        if not roles_to_upload:
            print("No roles found in the JSON file to upload.")
            return

        # Initialize SailPoint API client
        api_client = SailPointAPIClient(ISC_TENANT_URL, ISC_CLIENT_ID, ISC_CLIENT_SECRET)

        successful_uploads = 0
        failed_uploads = 0

        print(f"\n--- Starting Role Upload ({len(roles_to_upload)} roles) ---")
        for i, role_data in enumerate(roles_to_upload):
            role_name = role_data.get('name', f"Unnamed Role {i+1}")
            print(f"Uploading role {i+1}/{len(roles_to_upload)}: '{role_name}'...")
            
            success, message = api_client.create_role(role_data)
            
            if success:
                print(f"  SUCCESS: {message}")
                successful_uploads += 1
            else:
                print(f"  FAILURE: {message}")
                failed_uploads += 1
                
        print("\n--- Role Upload Summary ---")
        print(f"Total roles attempted: {len(roles_to_upload)}")
        print(f"Successful uploads: {successful_uploads}")
        print(f"Failed uploads: {failed_uploads}")

    except FileNotFoundError:
        print(f"Error: The JSON file '{json_file_path}' was not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{json_file_path}'. Ensure it's a valid JSON file.")
    except Exception as e:
        print(f"An unexpected error occurred during role upload: {e}")

if __name__ == "__main__":
    main()
