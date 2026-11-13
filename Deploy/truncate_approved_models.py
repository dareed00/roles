#!/usr/bin/env python3
"""
RoleMiner Testing Utility - Database Clean-up
Script: Deploy/truncate_approved_models.py

Truncates all ApprovedRoleModel_* production tables to enable fresh testing,
handling InnoDB foreign key constraints gracefully.
"""

import sys
import pymysql

# Centralized DB Connection Settings
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "password",  # Fixed fallback credential
    "database": "bundleBuilder",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# The exact order matters to avoid foreign key dependency blocks
TABLES_TO_CLEAR = [
    # 1. Clear mapping/junction tables first
    "CurrentRoleModel_RoleEffectiveEntitlements",
    "CurrentRoleModel_RoleEntitlements",
    "CurrentRoleModel_AccessProfileEntitlements",
    "CurrentRoleModel_RoleSimilarity",
    "CurrentRoleModel_AccessProfileSimilarity",
    # 2. Clear master/definition tables last
    "CurrentRoleModel_Roles",
    "CurrentRoleModel_AccessProfiles",
    "ApprovedRoleModel_Roles",
    "ApprovedRoleModel_RoleEntitlements",
    "ApprovedRoleModel_AuditLog",
    "ApprovedRoleModel_AccessProfiles",
    "ApprovedRoleModel_AccessProfileEntitlements",
    "AuditEventLog_Attributes",
    "ApprovedRoleModel_Roles",
    "ApprovedRoleModel"
]


def truncate_testing_tables():
    print("----------------------------------------------------------------------")
    print("--- EXECUTING: truncate_approved_models.py")
    print("----------------------------------------------------------------------")
    print("🔗 Connecting to MySQL database 'bundleBuilder'...")
    
    try:
        conn = pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        sys.exit(1)

    try:
        with conn.cursor() as cursor:
            # 💡 Temp disable foreign key constraints to ensure a clean sweep
            print("🔑 Temporarily disabling foreign key checks...")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            
            for table in TABLES_TO_CLEAR:
                print(f"🧹 Truncating table: '{table}'...")
                try:
                    cursor.execute(f"TRUNCATE TABLE `{table}`;")
                except pymysql.err.ProgrammingError as e:
                    # Soft check if tables aren't created yet in this development database
                    if e.args[0] == 1146:
                        print(f"   ℹ️ Table '{table}' does not exist yet. Skipping.")
                        continue
                    raise

            # 💡 Re-enable foreign key constraints to maintain database integrity
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            conn.commit()
            print("💾 Database changes successfully committed.")
            print("🎉 Clean sweep complete! Staging tables are ready for a fresh run.")

    except Exception as e:
        print(f"❌ Execution failed during truncation: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    truncate_testing_tables()
