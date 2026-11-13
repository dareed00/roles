#!/usr/bin/env python3
# Scripts/Utils/config.py
"""
bundleBuilder - Unified Configuration & Utilities
Centralizes:
  • Database connection helpers & datetime sanitization
  • SailPoint ISC API credentials (CONNECTION_MAP)
  • Storage directory paths (FILES_DIR & JSON file targets)
  • Mining thresholds and UI limits (MINING_LIMITS & MiningConfig)
"""

import os
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Set, Optional, Dict, Any
import mysql.connector
from mysql.connector import Error

# ==============================================================================
# 1. DIRECTORY PATH RESOLUTION (/RoleMiner/Files)
# ==============================================================================
_utils_dir = os.path.dirname(os.path.abspath(__file__))      # Scripts/Utils
_scripts_dir = os.path.dirname(_utils_dir)                   # Scripts
PROJECT_ROOT = os.path.dirname(_scripts_dir)                 # RoleMiner root

FILES_DIR = os.getenv("ROLEMINER_FILES_DIR", os.path.join(PROJECT_ROOT, "Files"))
os.makedirs(FILES_DIR, exist_ok=True)

# ==============================================================================
# GENERAL ROLE MEMBERSHIP FILTER
# ==============================================================================
# This filter is automatically prepended to every role's assignment rule:
# Final Rule = "(GENERAL_ROLE_FILTER) AND (Mined Demographic Criteria)"
GENERAL_ROLE_FILTER = os.getenv("GENERAL_ROLE_FILTER", "cloudLifecycleState = 'active'")


def format_full_assignment_rule(mined_rule_logic: str, general_filter: str = None) -> str:
    """
    Combines the global scoping filter with the mined role criteria into:
    (General Filter) AND (Role Filter)
    """
    gen = general_filter if general_filter is not None else GENERAL_ROLE_FILTER
    clean_rule = str(mined_rule_logic).strip()
    
    if not gen or not gen.strip():
        return clean_rule
        
    gen_clean = gen.strip()
    # Prevent duplicate prepending if already present
    if gen_clean.lower() in clean_rule.lower():
        return clean_rule
        
    return f"({gen_clean}) AND ({clean_rule})"


JSON_PATHS = {
    "identities": os.path.join(FILES_DIR, "identities.json"),
    "identity_assignments": os.path.join(FILES_DIR, "identity_assignments.json"),
    "accounts": os.path.join(FILES_DIR, "accounts.json"),
    "entitlements": os.path.join(FILES_DIR, "entitlements.json"),
    "access_profiles": os.path.join(FILES_DIR, "access_profiles.json"),
    "roles": os.path.join(FILES_DIR, "roles.json"),
    "audit_events": os.path.join(FILES_DIR, "audit_events.json"),
}


# ==============================================================================
# 2. DATABASE CONFIGURATION & HELPERS
# ==============================================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),  # Safe password configured
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
    """Safely closes connection and cursor handles."""
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


def format_datetime_for_mysql(dt_val):
    """
    Converts ISO 8601 timestamps (e.g. '2024-09-24T15:33:45.993Z') 
    to MySQL-compatible DATETIME format ('YYYY-MM-DD HH:MM:SS').
    Strips fractional milliseconds, 'T' delimiters, and trailing 'Z'.
    """
    if not dt_val:
        return None
    val = str(dt_val).strip().replace("T", " ").rstrip("Z")
    if "." in val:
        val = val.split(".")[0]
    return val if val else None


# ==============================================================================
# 3. SAILPOINT ISC API CONNECTION MAP
# ==============================================================================
CONNECTION_MAP = {
    "ISC": {
        "ClientId": "5961a1294d6243888ddbbc88efe31c78",
        "ClientSecret": "83044fc7ad661161564524cf336ff68ad9dd3f7f7afb88434bcffe4833cdac69",
        "BaseURL": "https://company12640-poc.api.identitynow-demo.com"
    }
}

# ==============================================================================
# 4. CENTRALIZED MINING CONFIGURATION FOR UI INTEGRATION
# ==============================================================================
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
    "Functional_Business_Unit", "Job_Family_Group", "Job_Family", "Job_Code"
)

HIERARCHY_FAMILIES = [
    {"city", "state", "location", "country", "site", "region"},
    {"jobcode", "job_code", "jobtitle", "job_title", "job_family", "job_family_group", "career_level"},
    {"department", "division", "functional_business_unit", "company", "company_-_id", "costcenter", "cost_center"},
    {"type", "worker_type", "worker_sub-type", "ismanager", "ismgmt", "exempt"},
]

MAX_CONTAINMENT_RATIO = 0.95


@dataclass
class MiningConfig:
    min_pop: int = 2
    max_pop: Optional[int] = None
    batch_size: Optional[int] = None
    batch_index: int = 0
    clear_all: bool = False
    min_jaccard: float = 0.50
    max_containment_ratio: float = 0.95

    allowed_attributes: List[str] = field(default_factory=lambda: [
        "jobTitle", "department", "location", "country", 
        "type", "isManager", "division", "costCenter",
        "Functional_Business_Unit", "Job_Family_Group", "Job_Family", "Job_Code",
        "Management_Level_2", "Management_Level_3", "Management_Level_4", "Management_Level_5"
    ])

    hierarchy_families: List[Set[str]] = field(default_factory=lambda: [
        {"city", "state", "location", "country", "site", "region"},
        {"jobcode", "job_code", "jobtitle", "job_title", "job_family", "job_family_group", "career_level"},
        {
            "supervisory_organization", "management_level_2", "management_level_3",
            "management_level_4", "management_level_5", "management_level_6",
            "management_level_7", "management_level_8", "management_level_9", "management_level_10"
        },
        {"department", "division", "functional_business_unit", "company", "company_-_id", "costcenter", "cost_center"},
        {"type", "worker_type", "worker_sub-type", "ismanager", "ismgmt", "exempt"},
    ])

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["hierarchy_families"] = [list(f) for f in self.hierarchy_families]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MiningConfig":
        if "hierarchy_families" in data and isinstance(data["hierarchy_families"], list):
            data["hierarchy_families"] = [set(f) for f in data["hierarchy_families"]]
        return cls(**data)

    def apply_preset(self, preset_name: str):
        preset = preset_name.upper().strip()
        if preset == "BROAD_BIRTHRIGHT":
            self.min_pop = 75
            self.max_pop = None
        elif preset == "CORE_FUNCTIONAL":
            self.min_pop = 10
            self.max_pop = 75
        elif preset == "MICRO_BUNDLE":
            self.min_pop = 1
            self.max_pop = 4
        elif preset == "ALL":
            self.min_pop = 2
            self.max_pop = None


def get_mining_config(**overrides) -> MiningConfig:
    return MiningConfig(**overrides)
