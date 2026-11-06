import mysql.connector
import json

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    # --- IMPORTANT ---
    # Replace these placeholder values with your actual database credentials.
    config = {
        'user': 'root',
        'password': 'password',
        'host': 'localhost',
        'database': 'bundleBuilder',
        'raise_on_warnings': True
    }
    try:
        conn = mysql.connector.connect(**config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None

def calculate_effective_entitlements():
    """
    Calculates and populates the IdentityEffectiveEntitlements table.

    This function de-normalizes the relationships between identities, roles,
    access profiles, and entitlements to create a flat record of who has
    what and how they got it.
    """
    conn = get_db_connection()
    if not conn:
        return

    cursor = conn.cursor(dictionary=True) # Use a dictionary cursor for easy column access
    
    try:
        print("Starting effective entitlements calculation...")

        # Step 1: Get all distinct identities to process
        cursor.execute("SELECT DISTINCT UID, AttributeValue FROM IdentityAttributesFiltered WHERE AttributeName = 'displayName'")
        identities = cursor.fetchall()
        if not identities:
            print("No identities found in IdentityAttributesFiltered. Exiting.")
            return
            
        print(f"Found {len(identities)} unique identities to process.")

        # For this script, we will fetch all granting relationships once to be efficient.
        print("Fetching all grant and mapping data from database...")
        cursor.execute("SELECT * FROM CurrentRoleModel_RoleEntitlements")
        role_to_ent = cursor.fetchall()

        cursor.execute("SELECT * FROM CurrentRoleModel_AccessProfileEntitlements")
        ap_to_ent = cursor.fetchall()

        cursor.execute("SELECT * FROM CurrentRoleModel_RoleAccessProfiles")
        role_to_ap = cursor.fetchall()
        
        # In a real-world scenario, you would evaluate role/AP assignment for each identity.
        # Here, we simplify by iterating through all roles/APs for demonstration.
        # A real implementation would have a function: `get_roles_for_identity(identity_attributes)`
        
        # Step 2: Loop through each identity
        for identity in identities:
            identity_id = identity['UID']
            identity_name = identity['AttributeValue'] # Assuming displayName
            print(f"\nProcessing Identity: {identity_name} ({identity_id})")

            # A placeholder for entitlements we find to avoid duplicates for this identity
            processed_entitlements = set()

            # --- PATH A: Entitlements granted directly by a Role ---
            # This path assumes we have a way to know which roles the identity has.
            # Here, we'll iterate through all role->entitlement mappings.
            for grant in role_to_ent:
                key = (identity_id, grant['role_id'], 'N/A', grant['entitlement_id'])
                if key not in processed_entitlements:
                    insert_effective_entitlement(
                        cursor,
                        identity_id=identity_id,
                        identity_name=identity_name,
                        role_id=grant['role_id'],
                        role_name=grant['role_name'],
                        entitlement_id=grant['entitlement_id'],
                        entitlement_name=grant['entitlement_name']
                    )
                    processed_entitlements.add(key)

            # --- PATH B: Entitlements granted directly by an Access Profile ---
            # This path assumes we can determine which APs an identity has.
            # Here, we iterate through all AP->entitlement mappings.
            for grant in ap_to_ent:
                key = (identity_id, 'N/A', grant['access_profile_id'], grant['entitlement_id'])
                if key not in processed_entitlements:
                    insert_effective_entitlement(
                        cursor,
                        identity_id=identity_id,
                        identity_name=identity_name,
                        access_profile_id=grant['access_profile_id'],
                        access_profile_name=grant['access_profile_name'],
                        entitlement_id=grant['entitlement_id'],
                        entitlement_name=grant['entitlement_name']
                    )
                    processed_entitlements.add(key)
            
            # --- PATH C: Entitlements granted by an Access Profile that is INSIDE a Role ---
            # This is a nested join: Role -> Access Profile -> Entitlement
            for r_ap_map in role_to_ap: # For every link between a role and an AP
                for ap_ent_map in ap_to_ent: # For every link between an AP and an entitlement
                    # If the AP in both maps is the same, we have a complete path
                    if r_ap_map['access_profile_id'] == ap_ent_map['access_profile_id']:
                        key = (identity_id, r_ap_map['role_id'], r_ap_map['access_profile_id'], ap_ent_map['entitlement_id'])
                        if key not in processed_entitlements:
                            insert_effective_entitlement(
                                cursor,
                                identity_id=identity_id,
                                identity_name=identity_name,
                                role_id=r_ap_map['role_id'],
                                role_name=r_ap_map['role_name'],
                                access_profile_id=r_ap_map['access_profile_id'],
                                access_profile_name=r_ap_map['access_profile_name'],
                                entitlement_id=ap_ent_map['entitlement_id'],
                                entitlement_name=ap_ent_map['entitlement_name']
                            )
                            processed_entitlements.add(key)


        print("\nCommitting all transactions...")
        conn.commit()
        print("Successfully populated IdentityEffectiveEntitlements table.")

    except mysql.connector.Error as err:
        print(f"\nDatabase Error: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

def insert_effective_entitlement(cursor, identity_id, identity_name, entitlement_id, entitlement_name, role_id=None, role_name=None, access_profile_id=None, access_profile_name=None):
    """Helper function to insert a record into the effective entitlements table."""
    
    query = """
        INSERT INTO IdentityEffectiveEntitlements (
            identity_id, identity_name, role_id, role_name, access_profile_id,
            access_profile_name, entitlement_id, entitlement_name
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE identity_name = VALUES(identity_name);
    """
    # Use 'N/A' or a similar placeholder for IDs/names that are not part of the grant path
    data = (
        identity_id,
        identity_name,
        role_id if role_id else 'N/A',
        role_name if role_name else 'N/A',
        access_profile_id if access_profile_id else 'N/A',
        access_profile_name if access_profile_name else 'N/A',
        entitlement_id,
        entitlement_name
    )
    cursor.execute(query, data)
    print(f"  -> Granting '{entitlement_name}' to {identity_name} via Role: '{role_name}' and AP: '{access_profile_name}'")


# --- Main Execution ---
if __name__ == '__main__':
    # Before running:
    # 1. Make sure all prerequisite tables are populated (Identities, Roles, APs, Entitlements, and their mappings).
    # 2. Update get_db_connection() with your database credentials.
    # 3. Consider clearing the IdentityEffectiveEntitlements table before each run for a fresh calculation.
    
    # You would typically call this function from a scheduler.
    calculate_effective_entitlements()
    print("Example script for calculating effective entitlements is ready.")
    print("NOTE: This script uses a simplified model for identity-to-role/AP assignment.")
    print("Update connection details and uncomment the function call to run.")

