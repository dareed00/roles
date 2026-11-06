#┌────────────────────────────────────────────────────────────────────────────────────────┐
#│ 1. PRE-FLIGHT AUTHENTICATION (OAuth2 Client Credentials Grant /oauth/token)            │
#├────────────────────────────────────────────────────────────────────────────────────────┤
#│ 2. MANIFEST INGESTION (Reads Deploy/isc_it_roles_deployment_manifest.json)             │
#|────────────────────────────────────────────────────────────────────────────────────────┤
#│ 3. SAFETY MODE & DRY-RUN OPTION (--dry-run flag to inspect calls with 0 risk)          │
#├────────────────────────────────────────────────────────────────────────────────────────┤
#│ 4. EXECUTION ENGINES:                                                                  │
#│    • POST Engine: Creates net-new Access Profiles (/v3/access-profiles)                │
#│    • PATCH Engine: Updates existing Access Profiles via application/json-patch+json   │
#├────────────────────────────────────────────────────────────────────────────────────────┤
#│ 5. GOVERNANCE AUDIT & DATABASE UPDATE                                                  │
#│    • Records returned ISC Access Profile IDs back into MySQL bundleBuilder             │
#│    • Logs deployment status and HTTP responses into ApprovedRoleModel_AuditLog         │
#└────────────────────────────────────────────────────────────────────────────────────────┘


#!/usr/bin/env python3
"""
bundleBuilder - SailPoint ISC IT Role (Access Profile) API Deployment Executor
Reads the deployment manifest (isc_it_roles_deployment_manifest.json), authenticates
via OAuth2, and executes POST (create) and PATCH (update) API calls against SailPoint ISC.
Supports dry-run simulations, retry backoff, and database audit synchronization.
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
import urllib.error
import mysql.connector
from mysql.connector import Error

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

DEFAULT_MANIFEST = os.path.join("Deploy", "isc_it_roles_deployment_manifest.json")
EXECUTION_LOG_OUTPUT = os.path.join("Deploy", "isc_deployment_execution_log.json")

# Database Configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "database": os.getenv("DB_NAME", "bundleBuilder"),
}


# ==============================================================================
# 1. SAILPOINT ISC API CLIENT & OAUTH2 HANDLER
# ==============================================================================
class SailPointISCClient:
    def __init__(self, base_url, client_id, client_secret):
        # Normalize base URL (e.g., https://tenant.api.identitynow.com)
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith("http"):
            self.base_url = f"https://{self.base_url}"
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = 0

    def authenticate(self):
        """Retrieves an OAuth2 Bearer token using client_credentials grant."""
        token_url = f"{self.base_url}/oauth/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(token_url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                self.token = res_json["access_token"]
                self.token_expiry = time.time() + res_json.get("expires_in", 3600) - 60
                print(f"🔐 Authenticated successfully to SailPoint ISC ({self.base_url}).")
                return True
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"❌ Authentication Failed [{e.code}]: {err_body}")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Failed to connect to ISC token endpoint: {e}")
            sys.exit(1)

    def _get_headers(self, content_type="application/json"):
        if not self.token or time.time() >= self.token_expiry:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": content_type,
            "Accept": "application/json"
        }

    def execute_request(self, method, endpoint, payload=None, content_type="application/json", max_retries=3):
        """Executes an HTTP request with exponential backoff on 429 rate limits."""
        url = f"{self.base_url}{endpoint}"
        body_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None

        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(url, data=body_bytes, method=method)
            for k, v in self._get_headers(content_type).items():
                req.add_header(k, v)

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp_data = resp.read().decode("utf-8")
                    return {
                        "status_code": resp.status,
                        "success": True,
                        "data": json.loads(resp_data) if resp_data else {}
                    }
            except urllib.error.HTTPError as e:
                resp_data = e.read().decode("utf-8")
                
                # Handle Rate Limiting (429)
                if e.code == 429 and attempt < max_retries:
                    retry_after = int(e.headers.get("Retry-After", 2 ** attempt))
                    print(f"   ⏳ Rate limited (429). Retrying in {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                try:
                    err_json = json.loads(resp_data)
                except Exception:
                    err_json = {"raw_error": resp_data}

                return {
                    "status_code": e.code,
                    "success": False,
                    "error": err_json
                }
            except Exception as e:
                return {
                    "status_code": 0,
                    "success": False,
                    "error": str(e)
                }


# ==============================================================================
# 2. DEPLOYMENT EXECUTION ENGINE
# ==============================================================================
def run_isc_deployment(manifest_path, is_dry_run=False, base_url=None, client_id=None, client_secret=None):
    print("=" * 85)
    print("🚀 SAILPOINT ISC IT ROLE (ACCESS PROFILE) DEPLOYMENT PIPELINE")
    print("=" * 85)

    if not os.path.exists(manifest_path):
        print(f"❌ Error: Deployment manifest '{manifest_path}' not found.")
        print("Please run `python3 Deploy/generate_isc_it_role_payloads.py` first.")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    create_ops = manifest.get("create_operations", [])
    update_ops = manifest.get("update_operations", [])
    total_ops = len(create_ops) + len(update_ops)

    print(f"📄 Loaded Manifest: {manifest_path}")
    print(f"📦 Total Operations : {total_ops:,} ({len(create_ops):,} Creates | {len(update_ops):,} Updates)")

    if is_dry_run:
        print("\n" + "⚠️ " * 15)
        print("🧪 RUNNING IN DRY-RUN MODE: No live HTTP mutations will be executed.")
        print("⚠️ " * 15 + "\n")
    else:
        # Resolve Credentials
        base_url = base_url or os.getenv("SAILPOINT_BASE_URL") or os.getenv("ISC_BASE_URL")
        client_id = client_id or os.getenv("SAILPOINT_CLIENT_ID") or os.getenv("ISC_CLIENT_ID")
        client_secret = client_secret or os.getenv("SAILPOINT_CLIENT_SECRET") or os.getenv("ISC_CLIENT_SECRET")

        if not all([base_url, client_id, client_secret]):
            print("\n❌ Missing ISC Credentials. Please provide them via flags or environment variables:")
            print("   • SAILPOINT_BASE_URL (e.g., https://tenant.api.identitynow.com)")
            print("   • SAILPOINT_CLIENT_ID")
            print("   • SAILPOINT_CLIENT_SECRET\n")
            sys.exit(1)

        client = SailPointISCClient(base_url, client_id, client_secret)
        client.authenticate()

    # Results Logging
    execution_results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dry_run": is_dry_run,
        "created_roles": [],
        "updated_roles": [],
        "failed_roles": []
    }

    db_updates = []

    # ==========================================================================
    # A. EXECUTE POST OPERATIONS (NET-NEW ROLES)
    # ==========================================================================
    print("\n➕ [1/2] Processing Net-New Access Profile Creations (POST)...")
    for idx, op in enumerate(create_ops, start=1):
        role_id = op["local_role_id"]
        role_name = op["role_name"]
        payload = op["payload"]

        print(f"   [{idx:02d}/{len(create_ops):02d}] Creating [{role_id}] {role_name} ({op['entitlements_count']} perms)...", end="", flush=True)

        if is_dry_run:
            print(" 🧪 [DRY-RUN SIMULATED OK]")
            execution_results["created_roles"].append({
                "local_role_id": role_id,
                "role_name": role_name,
                "status": "DRY_RUN_SIMULATED",
                "simulated_endpoint": "POST /v3/access-profiles"
            })
            continue

        res = client.execute_request("POST", "/v3/access-profiles", payload=payload, content_type="application/json")

        if res["success"]:
            isc_id = res["data"].get("id")
            print(f" ✅ [201 CREATED] (ISC ID: {isc_id})")
            execution_results["created_roles"].append({
                "local_role_id": role_id,
                "role_name": role_name,
                "isc_access_profile_id": isc_id,
                "status_code": res["status_code"],
                "status": "SUCCESS"
            })
            db_updates.append((isc_id, role_name, role_id, "POST_CREATE_SUCCESS"))
        else:
            print(f" ❌ [FAILED {res['status_code']}]")
            print(f"      Reason: {res.get('error')}")
            execution_results["failed_roles"].append({
                "local_role_id": role_id,
                "role_name": role_name,
                "operation": "POST",
                "status_code": res["status_code"],
                "error": res.get("error")
            })

        time.sleep(0.2)  # Respectful API pacing

    # ==========================================================================
    # B. EXECUTE PATCH OPERATIONS (EXISTING ROLES)
    # ==========================================================================
    print("\n🔄 [2/2] Processing Existing Access Profile Modifications (PATCH)...")
    for idx, op in enumerate(update_ops, start=1):
        role_id = op["local_role_id"]
        role_name = op["role_name"]
        endpoint = op["endpoint"]
        isc_id = op["isc_access_profile_id"]
        payload = op["payload"]

        print(f"   [{idx:02d}/{len(update_ops):02d}] Patching [{role_id}] {role_name} (ID: {isc_id})...", end="", flush=True)

        if is_dry_run:
            print(" 🧪 [DRY-RUN SIMULATED OK]")
            execution_results["updated_roles"].append({
                "local_role_id": role_id,
                "role_name": role_name,
                "isc_access_profile_id": isc_id,
                "status": "DRY_RUN_SIMULATED",
                "simulated_endpoint": f"PATCH {endpoint}"
            })
            continue

        res = client.execute_request("PATCH", endpoint, payload=payload, content_type="application/json-patch+json")

        if res["success"]:
            print(f" ✅ [200 OK]")
            execution_results["updated_roles"].append({
                "local_role_id": role_id,
                "role_name": role_name,
                "isc_access_profile_id": isc_id,
                "status_code": res["status_code"],
                "status": "SUCCESS"
            })
            db_updates.append((isc_id, role_name, role_id, "PATCH_UPDATE_SUCCESS"))
        else:
            print(f" ❌ [FAILED {res['status_code']}]")
            print(f"      Reason: {res.get('error')}")
            execution_results["failed_roles"].append({
                "local_role_id": role_id,
                "role_name": role_name,
                "operation": "PATCH",
                "status_code": res["status_code"],
                "error": res.get("error")
            })

        time.sleep(0.2)

    # ==========================================================================
    # C. SYNCHRONIZE DEPLOYMENT RESULTS TO MYSQL
    # ==========================================================================
    if not is_dry_run and db_updates:
        print("\n💾 Synchronizing ISC Access Profile IDs and Audit Log into MySQL...")
        try:
            db_connection = mysql.connector.connect(**DB_CONFIG)
            cursor = db_connection.cursor()

            # Record in Audit Log
            sql_audit = """
                INSERT INTO ApprovedRoleModel_AuditLog 
                (event_id, entity_type, entity_id, entity_name, version_number, action_type, field_name, new_value, changed_by, change_reason)
                VALUES (%s, 'IT_ROLE', %s, %s, 1, 'DEPLOY_TO_ISC', 'isc_access_profile_id', %s, 'ISC API Deployment Engine', %s)
            """
            audit_records = [
                (f"ISC-{time.strftime('%Y%m%d%H%M')}", row, row, row[0], row)
                for row in db_updates
            ]
            cursor.executemany(sql_audit, audit_records)
            db_connection.commit()
            cursor.close()
            db_connection.close()
            print("   ✅ Database audit log synchronized successfully.")
        except Error as e:
            print(f"   ⚠️ Database audit log update failed: {e}")

    # ==========================================================================
    # D. WRITE EXECUTION LOG & PRINT SUMMARY
    # ==========================================================================
    with open(EXECUTION_LOG_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(execution_results, f, indent=2)

    print("\n" + "=" * 85)
    print("📊 DEPLOYMENT EXECUTION SUMMARY")
    print("=" * 85)
    print(f"📄 Detailed Log File    : {EXECUTION_LOG_OUTPUT}")
    print(f"✨ Successfully Created : {len(execution_results['created_roles']):,} Access Profiles")
    print(f"🔄 Successfully Updated : {len(execution_results['updated_roles']):,} Access Profiles")
    print(f"❌ Failed Operations   : {len(execution_results['failed_roles']):,} Operations")
    print("=" * 85)

    if execution_results["failed_roles"]:
        print("\n⚠️ Review failed operations in the execution log and resolve payload errors before retrying.")
    else:
        print("\n🎉 Deployment completed successfully!")


# ==============================================================================
# ENTRY POINT & CLI PARSER
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy IT Roles / Access Profiles to SailPoint ISC via API.")
    parser.add_argument("-m", "--manifest", default=DEFAULT_MANIFEST, help="Path to isc_it_roles_deployment_manifest.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate deployment without making live HTTP calls")
    parser.add_argument("--base-url", default=None, help="ISC Base URL (e.g., https://tenant.api.identitynow.com)")
    parser.add_argument("--client-id", default=None, help="ISC OAuth Client ID")
    parser.add_argument("--client-secret", default=None, help="ISC OAuth Client Secret")

    args = parser.parse_args()
    run_isc_deployment(
        manifest_path=args.manifest,
        is_dry_run=args.dry_run,
        base_url=args.base_url,
        client_id=args.client_id,
        client_secret=args.client_secret
    )
