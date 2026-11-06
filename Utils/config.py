#!/usr/bin/env python3
# Scripts/Utils/config.py
"""
bundleBuilder - Unified Configuration & Utilities
Houses database connection helpers and centralizes mining thresholds/ranges for UI integration.
"""

import os
import sys
import mysql.connector
from mysql.connector import Error

# ==============================================================================
# 1. DATABASE CONFIGURATION
# ==============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),  # Central password defined
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


def get_db_connection(config_dict=None):
    """Establishes and returns a connection to the MySQL database."""
    target_config = config_dict if config_dict is not None else DB_CONFIG
    try:
        connection = mysql.connector.connect(**target_config)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"❌ Failed to connect to MySQL database: {e}")
        return None


def open_connection(config_dict=None):
    """Standardized connection helper used across all pipeline files."""
    return get_db_connection(config_dict)


def close_db_connection(connection, cursor=None):
    try:
        if cursor:
            cursor.close()
    except Exception:
        pass
    try:
        if connection and connection.is_connected():
            connection.close()
    except Exception:
        pass


# ==============================================================================
# 2. CENTRALIZED MINING CONFIGURATION FOR UI INTEGRATION
# ==============================================================================
# These parameters can be programmatically updated by your UI code prior to run.
MINING_LIMITS = {
    "min_pop": 75,                 # Minimum entitlement population size to inspect
    "max_pop": None,               # Maximum population size (None = Unlimited)
    "batch_size": None,            # Chunk size for batch execution (None = Process all)
    "batch_index": 0,              # 0-based index offset for batched runs
    "clear_all_discovered": True,  # If True, wipes old staging records before storing batch
}

ALLOWED_ATTRIBUTES = (
    "jobTitle", "department", "location", "country", 
    "type", "isManager", "division", "costCenter",
    "Functional_Business_Unit", "Job_Family_Group", "Job_Family", "Job_Code",
    "Management_Level_2", "Management_Level_3", "Management_Level_4", "Management_Level_5"
)

# Hierarchy Families: Prevents pairing redundant or subordinate dimensions
HIERARCHY_FAMILIES = [
    {"city", "state", "location", "country", "site", "region"},
    {"jobcode", "job_code", "jobtitle", "job_title", "job_family", "job_family_group", "career_level"},
    {
        "supervisory_organization", "management_level_2", "management_level_3",
        "management_level_4", "management_level_5", "management_level_6",
        "management_level_7", "management_level_8", "management_level_9", "management_level_10"
    },
    {"department", "division", "functional_business_unit", "company", "company_-_id", "costcenter", "cost_center"},
    {"type", "worker_type", "worker_sub-type", "ismanager", "ismgmt", "exempt"},
]

MAX_CONTAINMENT_RATIO = 0.95


def apply_preset(preset_name: str):
    """Convenience helper for your UI to quickly apply standard population tiers."""
    preset = str(preset_name).upper().strip()
    if preset == "BROAD_BIRTHRIGHT":
        MINING_LIMITS["min_pop"] = 75
        MINING_LIMITS["max_pop"] = None
    elif preset == "CORE_FUNCTIONAL":
        MINING_LIMITS["min_pop"] = 10
        MINING_LIMITS["max_pop"] = 75
    elif preset == "MICRO_BUNDLE":
        MINING_LIMITS["min_pop"] = 1
        MINING_LIMITS["max_pop"] = 4
    elif preset == "ALL":
        MINING_LIMITS["min_pop"] = 2
        MINING_LIMITS["max_pop"] = None
    print(f"📊 Applied Preset '{preset}': min_pop={MINING_LIMITS['min_pop']}, max_pop={MINING_LIMITS['max_pop']}")


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
OUTPUT_PDF = "Suggested_IT_Roles_Catalog_Report.pdf"

# --- NEW: SailPoint ISC API Configuration (for uploading roles) ---
ISC_TENANT_URL = "http://seri.company21602-poc.demohub.sailpointtechnologies.com"
ISC_CLIENT_ID = "YOUR_CLIENT_ID_HERE"      # <<< IMPORTANT: REPLACE WITH YOUR CLIENT ID
ISC_CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE" # <<< IMPORTANT: REPLACE WITH YOUR CLIENT SECRET

BATCH_SIZE = 5000

# Tier Configuration: (min_pop, max_pop, min_jaccard_threshold, min_size_ratio)
POPULATION_TIER_CONFIG = [
    (1, 3, 0.65, 0.65),
    (4, 8, 0.74, 0.74),
    (9, 14, 0.82, 0.82),
    (15, 20, 0.85, 0.85),
    (21, 30, 0.87, 0.87),
    (31, 50, 0.89, 0.89),
    (51, 75, 0.91, 0.91),
    (76, 100, 0.93, 0.93),
    (101, 150, 0.94, 0.94),
    (151, 225, 0.95, 0.95),
    (226, 300, 0.96, 0.96),
    (301, float("inf"), 0.97, 0.97),
]

# ==============================================================================
# HIERARCHY & REDUNDANCY SUPPRESSION RULES
# ==============================================================================
HIERARCHY_FAMILIES = [
    # Geographic hierarchy
    {"city", "state", "location", "country", "site", "region"},
    # Job architecture hierarchy
    {"jobcode", "job_code", "jobtitle", "job_title", "job_family", "job_family_group", "career_level"},
    # Management hierarchy
    {
        "supervisory_organization", "management_level_2", "management_level_3",
        "management_level_4", "management_level_5", "management_level_6",
        "management_level_7", "management_level_8", "management_level_9", "management_level_10"
    },
    # Organizational & financial hierarchy
    {"department", "division", "functional_business_unit", "company", "company_-_id", "costcenter", "cost_center"},
    # Worker classification hierarchy
    {"type", "worker_type", "worker_sub-type", "ismanager", "ismgmt", "exempt"},
]

# If >= 95% of users with attribute A also have attribute B, one is a subset of the other
MAX_CONTAINMENT_RATIO = 0.95






