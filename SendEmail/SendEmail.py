import smtplib
import ssl
from email.message import EmailMessage

def send_email(sender_email, sender_password, receiver_email, subject, body, smtp_server='smtp.gmail.com', smtp_port=587):
    """
    Sends an email using Python's smtplib and email.message modules.

    Args:
        sender_email (str): The email address of the sender.
        sender_password (str): The password for the sender's email account.
                                For Gmail, this should be an app-specific password.
        receiver_email (str): The email address of the recipient.
        subject (str): The subject of the email.
        body (str): The plain text body of the email.
        smtp_server (str): The SMTP server address (default is 'smtp.gmail.com').
        smtp_port (int): The SMTP server port (default is 587 for TLS).
    """

    # Create a new EmailMessage object
    msg = EmailMessage()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.set_content(body)

    # Create a secure SSL context
    context = ssl.create_default_context()

    try:
        # Connect to the SMTP server
        # For TLS (port 587), use smtplib.SMTP and then starttls()
        # For SSL (port 465), use smtplib.SMTP_SSL directly
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)  # Secure the connection
            server.login(sender_email, sender_password)  # Log in to the email account
            server.send_message(msg)  # Send the email
        print("Email sent successfully!")
    except smtplib.SMTPAuthenticationError:
        print("Failed to authenticate. Please check your email and password (or app password).")
    except smtplib.SMTPConnectError as e:
        print(f"Failed to connect to the SMTP server: {e}. Check server address and port.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    # --- Configuration ---
    # IMPORTANT: Do not hardcode your email and password in production code.
    # Use environment variables or a secure configuration management system.
    # For Gmail, you will likely need to generate an "App password"
    # from your Google Account security settings if you have 2-Step Verification enabled.
    # See: https://myaccount.google.com/apppasswords

    SENDER_EMAIL = "your_email@example.com"  # Replace with your email address
    SENDER_PASSWORD = "your_app_password"  # Replace with your app password or email password
    RECEIVER_EMAIL = "recipient_email@example.com"  # Replace with the recipient's email address
    EMAIL_SUBJECT = "Hello from Python!"
    EMAIL_BODY = """
    This is a test email sent from a Python script.
    It demonstrates sending a plain text email using smtplib and email.message modules.
    """

    # --- Call the function to send the email ---
    # Uncomment the following line and replace with actual credentials to run:
    # send_email(SENDER_PASSWORD, SENDER_PASSWORD, RECEIVER_EMAIL, EMAIL_SUBJECT, EMAIL_BODY)

    print("To send an email, please uncomment the `send_email` call in the `if __name__ == '__main__'` block ")
    print("and replace the placeholder credentials and email addresses with your actual details.")
    print("For Gmail, remember to use an App Password if you have 2-Step Verification enabled.")
