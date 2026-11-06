# config.py

DB_CONFIG = {
    'host': 'localhost',
    'database': 'bundleBuilder',
    'user': 'root',
    'password': 'password',
    'port': 3306 # Default MySQL port
}

# Define additional attributes to display for UIDs and load into DB
DISPLAY_ATTRIBUTES = ['type', 'Is Manager', 'country', 'department', 'jobTitle', 'location']

ATTRIBUTE_VALUE_COLUMN_NAME = 'Attribute Value Name'
ACCESS_SOURCE_NAME_COLUMN = 'Access Source Name'
UID_COLUMN_NAME = 'UID'

# --- Role Generation Specific Configuration ---
ROLE_OWNER_NAME = "Service Account" # Placeholder owner for generated roles
ROLE_COMMENTS = "Auto Generated Role by Dana's Role Minier"
ROLE_ENABLED_DEFAULT = False # Set to False as requested
ROLE_REQUESTABLE_DEFAULT = True

# --- Output File Configuration (for generated roles) ---
OUTPUT_DIRECTORY = "/Users/dana.reed/RoleMiner/Output"
OUTPUT_FILENAME = "ISCBundles.json"

# --- NEW: SailPoint ISC API Configuration (for uploading roles) ---
ISC_TENANT_URL = "http://seri.company21602-poc.demohub.sailpointtechnologies.com"
ISC_CLIENT_ID = "YOUR_CLIENT_ID_HERE"      # <<< IMPORTANT: REPLACE WITH YOUR CLIENT ID
ISC_CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE" # <<< IMPORTANT: REPLACE WITH YOUR CLIENT SECRET


