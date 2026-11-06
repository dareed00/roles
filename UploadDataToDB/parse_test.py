# parse_test.py
import json

# ===================================================================
# A sample object representing ONE identity from the API response list.
# This structure, with a nested 'access' list, is based on your
# successful research.
# ===================================================================
sample_identity_object = {
  "id": "2c9180835d2e5168015d32f890ca1581",
  "name": "dana.reed",
  "type": "IDENTITY",
  "access": [
    {
      "id": "2c91808a78243e3c01782f8a5a573d55",
      "name": "Employee",
      "description": "Access for all employees",
      "type": "ROLE"
    },
    {
      "id": "2c91808a78243e3c01782f8a5a571234",
      "name": "Okta",
      "description": "Basic access to Okta",
      "type": "ACCESS_PROFILE"
    },
    {
      "id": "2c91808a78243e3c01782f8a5a575678",
      "name": "CN=All-Users,OU=Groups,DC=example,DC=com",
      "description": "Domain Users Group",
      "type": "ENTITLEMENT"
    }
  ]
}

# This is the data structure our main script receives from the API
api_response_list = [sample_identity_object]

# --- Start of the parsing logic from load_identity_assignments.py ---

print("--- Starting Parse Test ---")

# These lists will hold the final data ready for the database
identity_list = []
role_assignments = []
ap_assignments = []
ent_assignments = []

print("Processing sample API response...")
# Loop through the list of identities returned by the API
for identity in api_response_list:
    identity_id = identity.get('id')
    uid = identity.get('name')
    
    # Add the identity to our list for the IdentityListSummary table
    if identity_id and uid:
        identity_list.append((identity_id, uid))
    
    # Process the nested 'access' list for this identity
    for item in identity.get('access', []):
        item_type = item.get('type')
        item_id = item.get('id')
        item_name = item.get('name')

        # Skip any malformed records
        if not all([identity_id, uid, item_id, item_name]):
            print(f"  - Skipping malformed access item: {item}")
            continue

        # Sort the access item into the correct assignment list
        if item_type == 'ROLE':
            print(f"  - Found ROLE: {item_name}")
            role_assignments.append((identity_id, uid, item_id, item_name))
        elif item_type == 'ACCESS_PROFILE':
            print(f"  - Found ACCESS_PROFILE: {item_name}")
            ap_assignments.append((identity_id, uid, item_id, item_name))
        elif item_type == 'ENTITLEMENT':
            print(f"  - Found ENTITLEMENT: {item_name}")
            ent_assignments.append((identity_id, uid, item_id, item_name))
        else:
            print(f"  - Found unknown type: {item_type}")

print("\n--- PARSING COMPLETE ---")

# --- Print the final, sorted lists ---

print("\n1. Data for 'IdentityListSummary' table:")
print(identity_list)

print("\n2. Data for 'IdentityRoleAssignments' table:")
print(role_assignments)

print("\n3. Data for 'IdentityAccessProfileAssignments' table:")
print(ap_assignments)

print("\n4. Data for 'IdentityEntitlementAssignments' table:")
print(ent_assignments)
