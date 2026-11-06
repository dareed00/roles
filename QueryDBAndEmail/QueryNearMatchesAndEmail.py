import mysql.connector
from collections import defaultdict
from email.message import EmailMessage

def generate_near_role_creation_emails(db_config, recipient_email='dana.reed@sailpoint.com'):
    """
    Queries a MySQL database for \'near_identical_correlations\' and their
    associated \'near_match_differing_uids\', groups results into \'suggested near role\'
    objects, and then generates and prints an email for each near role.
    The email is addressed to a specified recipient, lists near role details,
    including differing UIDs and their HR info, and inquires about Identity
    Security Cloud role creation.

    Args:
        db_config (dict): A dictionary containing database connection parameters
                          (host, user, password, database).
        recipient_email (str): The email address of the recipient.
    """
    try:
      db_connection = get_db_connection(config.get("Database"))
    if not db_connection return
    
    cursor = db_connection.cursor(dictionary=True, buffered=True)# Use dictionary=True to get results as dicts

        # Query the near_identical_correlations table and LEFT JOIN with near_match_differing_uids
        query = """
        SELECT
            nic.id AS correlation_id,
            nic.primary_grouping_column,
            nic.primary_value,
            nic.attribute_value,
            nic.access_source_name,
            nic.jaccard_score,
            nic.primary_population_size,
            nmdu.uid,
            nmdu.is_in_primary_only,
            nmdu.is_in_attribute_only,
            nmdu.type,
            nmdu.is_manager,
            nmdu.country,
            nmdu.department,
            nmdu.jobTitle,
            nmdu.location
        FROM
            near_identical_correlations nic
        LEFT JOIN
            near_match_differing_uids nmdu ON nic.id = nmdu.near_match_correlation_id
        ORDER BY
            nic.id, nmdu.uid;
        """
        cursor.execute(query)
        records = cursor.fetchall()

        if not records:
            print("No records found in 'near_identical_correlations' or 'near_match_differing_uids' tables.")
            return

        # Group results by correlation_id
        suggested_near_roles = defaultdict(lambda: {
            'primary_grouping_column': '',
            'primary_value': '',
            'attribute_value': '',
            'access_source_name': '',
            'jaccard_score': 0.0,
            'primary_population_size': 0,
            'differing_uids': [] # List of dictionaries for differing UID details
        })

        for record in records:
            correlation_id = record['correlation_id']
            # Populate core correlation details (only once per correlation_id)
            if not suggested_near_roles[correlation_id]['primary_value']:
                suggested_near_roles[correlation_id]['primary_grouping_column'] = record['primary_grouping_column']
                suggested_near_roles[correlation_id]['primary_value'] = record['primary_value']
                suggested_near_roles[correlation_id]['attribute_value'] = record['attribute_value']
                suggested_near_roles[correlation_id]['access_source_name'] = record['access_source_name']
                suggested_near_roles[correlation_id]['jaccard_score'] = record['jaccard_score']
                suggested_near_roles[correlation_id]['primary_population_size'] = record['primary_population_size']

            # Add differing UID details if they exist for this correlation
            if record['uid']: # Only add if UID is not NULL (meaning there was a join)
                uid_detail = {
                    'uid': record['uid'],
                    'is_in_primary_only': record['is_in_primary_only'],
                    'is_in_attribute_only': record['is_in_attribute_only'],
                    'type': record['type'],
                    'is_manager': record['is_manager'],
                    'country': record['country'],
                    'department': record['department'],
                    'jobTitle': record['jobTitle'],
                    'location': record['location']
                }
                suggested_near_roles[correlation_id]['differing_uids'].append(uid_detail)


        # Generate and print email for each suggested near role
        for correlation_id, role_data in suggested_near_roles.items():
            primary_value = role_data['primary_value']
            primary_grouping_column = role_data['primary_grouping_column']
            attribute_value = role_data['attribute_value']
            access_source_name = role_data['access_source_name']
            jaccard_score = role_data['jaccard_score']
            primary_population_size = role_data['primary_population_size']
            differing_uids = role_data['differing_uids']

            role_name = f"{primary_value} (Near Match with {attribute_value})"

            msg = EmailMessage()
            msg['Subject'] = f"Inquiry: Potential Near-Identical Role for ISC - {primary_value}"
            msg['From'] = "automation@yourdomain.com"  # <<< IMPORTANT: Replace with a suitable sender email
            msg['To'] = recipient_email

            email_body = f"""
Dear Dana Reed,

This email is an automated suggestion for a potential 'near-identical' role, based on correlation analysis from our systems.

We have identified a correlation that is highly similar but not exact, suggesting a possible role with minor variations.

Suggested Near Role: {role_name}
Primary Grouping Column: {primary_grouping_column}
Primary Value: {primary_value}
Correlated Attribute Value: {attribute_value}
Access Source: {access_source_name}
Jaccard Score (Similarity): {jaccard_score:.4f}
Primary Population Size: {primary_population_size}

Identities differing in this near-match correlation:
"""
            if differing_uids:
                for uid_detail in differing_uids:
                    status = []
                    if uid_detail['is_in_primary_only']:
                        status.append("in Primary only")
                    if uid_detail['is_in_attribute_only']:
                        status.append("in Attribute only")

                    email_body += f"\n  - UID: {uid_detail['uid']} (Status: {', '.join(status) if status else 'unknown'})"
                    if uid_detail['type']: email_body += f"\n    Type: {uid_detail['type']}"
                    if uid_detail['is_manager'] is not None: email_body += f"\n    Is Manager: {uid_detail['is_manager']}"
                    if uid_detail['country']: email_body += f"\n    Country: {uid_detail['country']}"
                    if uid_detail['department']: email_body += f"\n    Department: {uid_detail['department']}"
                    if uid_detail['jobTitle']: email_body += f"\n    Job Title: {uid_detail['jobTitle']}"
                    if uid_detail['location']: email_body += f"\n    Location: {uid_detail['location']}"
                    email_body += "\n" # Add an extra newline for readability between UIDs
            else:
                email_body += "  No specific differing identities found for this near-match correlation.\n"

            email_body += """

This near-identical correlation could represent a role that needs minor adjustments, or perhaps two very similar roles. Formalizing this within Identity Security Cloud can help refine your access model.

Would you like Identity Security Cloud to create a role based on this near-identical correlation, considering the differences highlighted? Please let us know your decision or if you require further details for review.

Thank you,

Automated Correlation System
SailPoint
"""
            msg.set_content(email_body)

            print(f"\n--- GENERATED EMAIL FOR NEAR-IDENTICAL ROLE: {role_name} (ID: {correlation_id}) ---")
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


# Example Usage (replace with your actual database configuration)
if __name__ == "__main__":
    # --- IMPORTANT: Configure your database connection details here ---
    db_configuration = {
        'host': 'localhost',
        'user': 'root',
        'password': 'password',
        'database': 'bundleBuilder'
    }
    # It's highly recommended to load database credentials from environment variables
    # or a secure configuration management system in a production environment.



    # Call the main function to generate and print emails for near-identical correlations
    generate_near_role_creation_emails(db_configuration, recipient_email='dana.reed@sailpoint.com')
