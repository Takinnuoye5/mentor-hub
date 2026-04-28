"""
Configuration for deactivated interns notification system.

Update these settings based on your actual Google Sheet structure.
"""

import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=str(Path(__file__).parent.parent / '.env'))

# ============================================================================
# GOOGLE SHEETS CONFIGURATION
# ============================================================================

# Sheet Configuration
DEACTIVATION_SHEET_NAME = "Deactivated Interns"  # Change to your actual sheet name
DEACTIVATION_SHEET_ID = None  # Optional: specify exact sheet ID if needed

# Column Names (update these to match your actual sheet columns)
# These will be used to identify interns and their status
COLUMNS = {
    'slack_id': 'Slack ID',           # Required: to fetch email from Slack profile
    'display_name': 'Display Name',   # Optional: intern name
    'email': 'Email',                 # Optional: if email is in sheet, use this
    'status': 'Status',               # Required: column that marks deactivation
    'stage_failed': 'Stage',          # Optional: which stage they failed
    'feedback': 'Feedback',           # Optional: specific feedback for intern
    'date_deactivated': 'Date',       # Optional: when they were deactivated
}

# Status Values (what values indicate deactivation in the Status column)
STATUS_VALUES = {
    'deactivated': ['Deactivated', 'DEACTIVATED', 'deactivated', 'Failed'],
    'active': ['Active', 'ACTIVE', 'active'],
    'pending': ['Pending', 'PENDING', 'pending'],
}

# ============================================================================
# GMAIL CONFIGURATION
# ============================================================================

# Gmail sender email (the account that will send notifications)
GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL", "hng@gmail.com")

# Gmail credentials file (must be set in .env)
GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "hng14-gmail-credentials.json")

# Subject line for deactivation emails
EMAIL_SUBJECT = "HNG 14 Internship: Did Not Progress - Next Steps"

# ============================================================================
# SLACK CONFIGURATION
# ============================================================================

# Bot token for fetching user profiles
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")

# ============================================================================
# NOTIFICATION SETTINGS
# ============================================================================

# Send emails or dry-run (preview only)
DRY_RUN = True  # Set to False to actually send emails

# Ask for confirmation before sending batch
REQUIRE_CONFIRMATION = True

# Number of emails to send per batch (to avoid rate limits)
BATCH_SIZE = 10

# Delay between emails (seconds) to avoid Gmail rate limiting
EMAIL_DELAY = 1

# Enable logging of sent emails
LOG_SENT_EMAILS = True

# Log file location
LOG_FILE = str(Path(__file__).parent.parent / "logs" / "deactivation_emails.log")

# ============================================================================
# EMAIL TEMPLATE SETTINGS
# ============================================================================

# Include feedback in email if available
INCLUDE_FEEDBACK = True

# Include stage information in email
INCLUDE_STAGE = True

# Next cohort open date (for the email template)
NEXT_COHORT_DATE = "[Date TBA]"

# Link to HNG website
HNG_WEBSITE = "https://hng.tech"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_deactivated_status(status_value: str) -> bool:
    """Check if a status value indicates deactivation."""
    return status_value in STATUS_VALUES['deactivated']


def get_column_name(key: str) -> str:
    """Get the actual column name from the configuration."""
    return COLUMNS.get(key)


def validate_config() -> tuple[bool, list]:
    """
    Validate that configuration is properly set.
    
    Returns:
        (is_valid, list_of_errors)
    """
    errors = []
    
    if not SLACK_BOT_TOKEN:
        errors.append("❌ SLACK_BOT_TOKEN not set in .env")
    
    if not GMAIL_CREDENTIALS_FILE:
        errors.append("❌ GMAIL_CREDENTIALS_FILE not set in .env")
    elif not Path(GMAIL_CREDENTIALS_FILE).exists():
        errors.append(f"❌ GMAIL_CREDENTIALS_FILE not found: {GMAIL_CREDENTIALS_FILE}")
    
    if not DEACTIVATION_SHEET_NAME:
        errors.append("❌ DEACTIVATION_SHEET_NAME not configured")
    
    # Check required columns
    required_columns = ['slack_id', 'status']
    for col_key in required_columns:
        if col_key not in COLUMNS:
            errors.append(f"❌ Required column '{col_key}' not in COLUMNS config")
    
    return (len(errors) == 0, errors)


if __name__ == "__main__":
    print("🔍 Validating deactivation configuration...\n")
    is_valid, errors = validate_config()
    
    if is_valid:
        print("✅ Configuration looks good!")
        print(f"\nSheet: {DEACTIVATION_SHEET_NAME}")
        print(f"Gmail Sender: {GMAIL_SENDER_EMAIL}")
        print(f"Dry Run: {DRY_RUN}")
    else:
        print("❌ Configuration errors found:\n")
        for error in errors:
            print(f"  {error}")
