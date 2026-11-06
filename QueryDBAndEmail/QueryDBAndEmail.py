import mysql.connector
from collections import defaultdict
from email.message import EmailMessage

def generate_role_creation_emails(db_config, recipient_email='dana.reed@sailpoint.com'):
    """
    Queries a MySQL database's 'exact_correlations' table, groups results into
    'suggested role' objects, and then generates and prints an email for each role.
    The email is addressed to a specified recipient, lists role details, and
    inquires about Identity Security Cloud role creation.

    Args:
        db_config (dict): A dictionary containing database connection parameters
                          (host, user, password, database).
        recipient_email (str): The email address of the recipient.
    """
    try:
        # Establish database connection
        db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True) # Use dictionary=True to get results as dicts

        # Query the exact_correlations table
        # Based on your DDL, the columns are:
        # `primary_grouping_column`, `primary_value`, `attribute_value`, `access_source_name`, `population_size`
        query = """
        SELECT
            primary_value,
            primary_grouping_column,
            attribute_value,
            access_source_name,
            population_size
        FROM
            exact_correlations
        ORDER BY
            primary_value, primary_grouping_column;
        """
        cursor.execute(query)
        records = cursor.fetchall()

        if not records:
            print("No records found in 'exact_correlations' table.")
            return

        # Group results by primary_value and primary_grouping_column
        # Each group forms a "suggested role"
        suggested_roles = defaultdict(lambda: {
            'attributes': [], # List of dictionaries for attribute details
            'population_size': 0 # To store the population size for the role
        })

        for record in records:
            primary_value = record['primary_value']
            primary_grouping_column = record['primary_grouping_column']
            attribute_value = record['attribute_value']
            access_source_name = record['access_source_name']
            population_size = record['population_size'] # Assuming population_size is consistent for a role

            role_key = (primary_value, primary_grouping_column)

            # Store attributes for the role. We want unique combinations for display.
            attribute_detail = {
                'attribute_value': attribute_value,
                'access_source_name': access_source_name
            }
            if attribute_detail not in suggested_roles[role_key]['attributes']:
                suggested_roles[role_key]['attributes'].append(attribute_detail)

            # Assign population size (assuming it's consistent for a given role_key)
            if suggested_roles[role_key]['population_size'] == 0: # Only set if not already set
                suggested_roles[role_key]['population_size'] = population_size


        # Generate and print email for each suggested role
        for (primary_value, primary_grouping_column), role_data in suggested_roles.items():
            role_name = f"{primary_value} (Grouped by {primary_grouping_column})"
            role_attributes = role_data['attributes']
            role_population_size = role_data['population_size']

            msg = EmailMessage()
            msg['Subject'] = f"Inquiry: New Suggested Role for Identity Security Cloud - {primary_value}"
            msg['From'] = "automation@yourdomain.com"  # <<< IMPORTANT: Replace with a suitable sender email
            msg['To'] = recipient_email

            email_body = f"""
Dear Dana Reed,

This email is an automated suggestion for a new role based on correlation analysis from our systems.

We have identified a potential new 'suggested role' with the following characteristics:

Suggested Role Name: {role_name}
Primary Value: {primary_value}
Grouping Column: {primary_grouping_column}
Population Size (Number of UIDs in this correlation): {role_population_size}

Associated Attributes:
"""
            if role_attributes:
                for attr_detail in role_attributes:
                    email_body += f"  - Attribute Value: '{attr_detail['attribute_value']}' from Access Source: '{attr_detail['access_source_name']}'\n"
            else:
                email_body += "  No specific attributes found for this role.\n"

            email_body += """

We believe this could be a strong candidate for formalization as an Identity Security Cloud role to streamline access management and improve governance.

Would you like Identity Security Cloud to make this role for them? Please let us know your decision or if you require further details for review.

Thank you,

Automated Correlation System
SailPoint
"""
            msg.set_content(email_body)

            print(f"\n--- GENERATED EMAIL FOR SUGGESTED ROLE: {role_name} ---")
            print(f"To: {msg['To']}")
            print(f"From: {msg['From']}")
            print(f"Subject: {msg['Subject']}")
            print(f"\n{msg.get_content()}")
            print("--- END OF EMAIL ---\n")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if 'db_connection' in locals() and db_connection.is_connected():
            cursor.close()
            db_connection.close()
            print("MySQL connection closed.")


if __name__ == "__main__":
    # --- IMPORTANT: Configure your database connection details here ---
    db_configuration = {
        'host': 'localhost',
        'user': 'root',         # Updated: your MySQL username
        'password': 'password', # Updated: your MySQL password
        'database': 'bundleBuilder'
    }
    # It's highly recommended to load database credentials from environment variables
    # or a secure configuration management system in a production environment.

    # --- Optional: Setup dummy data for testing if your table is empty ---
    # This section creates the table and inserts some sample data
    # if it doesn't exist or is empty, so you can run the script immediately.


    # Call the main function to generate and print emails
    generate_role_creation_emails(db_configuration, recipient_email='dana.reed@sailpoint.com')
