# main_generate.py
import json
import os
from role_generator_logic import generate_sailpoint_role_json_from_exact_correlations
from config import OUTPUT_DIRECTORY, OUTPUT_FILENAME # Import new constants

def main():
    """
    Main function to run the SailPoint Role JSON generation,
    printing to console and saving to a file.
    """
    print("Starting SailPoint Role JSON generation...")
    
    generated_roles = generate_sailpoint_role_json_from_exact_correlations()
    
    if generated_roles:
        print("\n--- Generated SailPoint Role JSON Objects (Console Output) ---\n")
        for i, role_data in enumerate(generated_roles):
            print(f"--- Role {i+1}: {role_data['name']} ---")
            print(json.dumps(role_data, indent=2))
            print("-" * 80)
        
        # --- NEW: Save to File ---
        output_file_path = os.path.join(OUTPUT_DIRECTORY, OUTPUT_FILENAME)
        
        try:
            # Ensure the output directory exists
            os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)
            
            # Write all generated roles as a single JSON array to the file
            with open(output_file_path, 'w', encoding='utf-8') as f:
                json.dump(generated_roles, f, indent=2, ensure_ascii=False)
            print(f"\nSuccessfully saved {len(generated_roles)} role(s) to: {output_file_path}")
        except Exception as e:
            print(f"\nError saving roles to file '{output_file_path}': {e}")
            
    else:
        print("No roles were generated.")

if __name__ == "__main__":
    main()
