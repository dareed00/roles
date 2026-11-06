# db_utils.py
import mysql.connector
from mysql.connector import Error
from typing import Any
from config import DB_CONFIG

def get_db_connection():
    """Establishes and returns a database connection."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Error connecting to MySQL database: {e}")
        return None

def close_db_connection(connection: Any, cursor: Any):
    """Closes the database cursor and connection."""
    if cursor:
        cursor.close()
    if connection and connection.is_connected():
        connection.close()
        print("MySQL connection closed.")
