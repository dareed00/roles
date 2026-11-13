#!/usr/bin/env python3
"""
Standardizes 'already_defined' across all 4 Suggested_* tables in bundleBuilder.
"""
import pymysql

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "password",
    "database": "bundleBuilder",
    "charset": "utf8mb4",
}

MIGRATIONS = [
    ("Suggested_Roles", "already_defined", "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0"),
    ("Suggested_Role_Entitlements", "already_defined", "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0 AFTER `already_in_role`"),
    ("Suggested_IT_Roles", "already_defined", "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0 AFTER `approval_status`"),
    ("Suggested_IT_Role_Entitlements", "already_defined", "ADD COLUMN `already_defined` BOOLEAN NOT NULL DEFAULT 0 AFTER `already_in_role`"),
]

conn = pymysql.connect(**DB_CONFIG)
with conn.cursor() as cur:
    for table, col, alter_clause in MIGRATIONS:
        cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,))
        if not cur.fetchone():
            cur.execute(f"ALTER TABLE `{table}` {alter_clause}")
            print(f"✅ Added `{col}` to `{table}`")
        else:
            print(f"ℹ️ `{table}.{col}` already exists")
    conn.commit()
conn.close()
