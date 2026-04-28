#!/usr/bin/env python3
"""
Notify deactivated interns via email.

This script:
1. Reads a Google Sheet of deactivated interns
2. Fetches their email addresses from Slack profiles
3. Sends professional deactivation notification emails
4. Logs all sent emails

Usage:
    python notify_deactivated_interns.py                    # Dry-run (preview)
    python notify_deactivated_interns.py --send             # Send actual emails
    python notify_deactivated_interns.py --send --skip-confirm  # Send without confirmation
    python notify_deactivated_interns.py --list-only        # Just list who would be notified
"""

import os
import sys
import json
import argparse
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from mentor_hub.scripts import config_deactivation as config
    from mentor_hub.scripts import email_templates
    from mentor_hub.core.config import GOOGLE_SPREADSHEET_NAME, GOOGLE_CREDENTIALS_FILE
except ImportError:
    import config_deactivation as config
    import email_templates

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    print("❌ Missing dependencies. Install with: pip install gspread oauth2client")
    sys.exit(1)

try:
    from slack_sdk import WebClient
except ImportError:
    print("❌ Missing slack-sdk. Install with: pip install slack-sdk")
    sys.exit(1)

try:
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials
    from google.oauth2 import service_account
except ImportError:
    print("❌ Missing google-auth libraries. Install with: pip install google-auth-oauthlib")
    sys.exit(1)

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# SLACK CLIENT SETUP
# ============================================================================

slack_bot_token = os.getenv("SLACK_BOT_TOKEN_HNG14")
if not slack_bot_token:
    logger.error("❌ SLACK_BOT_TOKEN_HNG14 not set in .env")
    sys.exit(1)

slack_client = WebClient(token=slack_bot_token)

# ============================================================================
# GOOGLE SHEETS SETUP
# ============================================================================

def setup_google_sheets():
    """Setup connection to Google Sheets."""
    try:
        if not config.GMAIL_CREDENTIALS_FILE or not Path(config.GMAIL_CREDENTIALS_FILE).exists():
            logger.error(f"❌ Gmail credentials file not found: {config.GMAIL_CREDENTIALS_FILE}")
            return None, None
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(config.GMAIL_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        
        # Try to open the deactivation sheet
        try:
            # First try by name
            spreadsheet = client.open(config.DEACTIVATION_SHEET_NAME)
            worksheet = spreadsheet.sheet1  # Get first worksheet
            logger.info(f"✅ Opened spreadsheet: {config.DEACTIVATION_SHEET_NAME}")
            return spreadsheet, worksheet
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"❌ Sheet not found: {config.DEACTIVATION_SHEET_NAME}")
            return None, None
            
    except Exception as e:
        logger.error(f"❌ Failed to connect to Google Sheets: {e}")
        return None, None


def get_deactivated_interns(worksheet) -> List[Dict]:
    """
    Read deactivated interns from Google Sheet.
    
    Returns:
        List of dicts with: slack_id, display_name, email, status, stage, feedback
    """
    try:
        records = worksheet.get_all_records()
        deactivated = []
        
        status_col = config.get_column_name('status')
        slack_id_col = config.get_column_name('slack_id')
        name_col = config.get_column_name('display_name')
        email_col = config.get_column_name('email')
        stage_col = config.get_column_name('stage_failed')
        feedback_col = config.get_column_name('feedback')
        
        for record in records:
            status = record.get(status_col, "").strip()
            
            if config.is_deactivated_status(status):
                slack_id = record.get(slack_id_col, "").strip()
                
                if not slack_id:
                    logger.warning(f"⚠️ Skipping record without Slack ID: {record}")
                    continue
                
                deactivated.append({
                    'slack_id': slack_id,
                    'display_name': record.get(name_col, "").strip() if name_col else "",
                    'email': record.get(email_col, "").strip() if email_col else "",
                    'status': status,
                    'stage': record.get(stage_col, "").strip() if stage_col else "",
                    'feedback': record.get(feedback_col, "").strip() if feedback_col else "",
                })
        
        return deactivated
        
    except Exception as e:
        logger.error(f"❌ Failed to read deactivated interns from sheet: {e}")
        return []


def get_email_from_slack(slack_id: str) -> Optional[str]:
    """
    Fetch email address from Slack user profile.
    
    Returns:
        Email address or None if not found
    """
    try:
        response = slack_client.users_info(user=slack_id)
        if response['ok']:
            user = response['user']
            email = user.get('profile', {}).get('email')
            if email:
                return email
            logger.warning(f"⚠️ No email in Slack profile for {slack_id}")
            return None
    except Exception as e:
        logger.error(f"❌ Failed to fetch Slack profile for {slack_id}: {e}")
        return None


def get_gmail_service():
    """Setup Gmail API service."""
    try:
        if not Path(config.GMAIL_CREDENTIALS_FILE).exists():
            logger.error(f"❌ Gmail credentials not found: {config.GMAIL_CREDENTIALS_FILE}")
            return None
        
        credentials = service_account.Credentials.from_service_account_file(
            config.GMAIL_CREDENTIALS_FILE,
            scopes=['https://www.googleapis.com/auth/gmail.send']
        )
        
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        
        service = build('gmail', 'v1', credentials=credentials)
        return service
        
    except Exception as e:
        logger.error(f"❌ Failed to setup Gmail service: {e}")
        return None


def send_email_gmail(service, to_email: str, subject: str, body: str) -> bool:
    """
    Send email via Gmail API.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from email.mime.text import MIMEText
        import base64
        
        message = MIMEText(body)
        message['to'] = to_email
        message['from'] = config.GMAIL_SENDER_EMAIL
        message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = {'raw': raw_message}
        
        send_result = service.users().messages().send(userId='me', body=send_message).execute()
        
        logger.info(f"✅ Email sent to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send email to {to_email}: {e}")
        return False


def log_sent_email(intern_data: Dict, email: str, success: bool, message_id: Optional[str] = None):
    """Log sent email to file."""
    if not config.LOG_SENT_EMAILS:
        return
    
    try:
        log_dir = Path(config.LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'slack_id': intern_data['slack_id'],
            'display_name': intern_data['display_name'],
            'email': email,
            'success': success,
            'message_id': message_id,
        }
        
        with open(config.LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
            
    except Exception as e:
        logger.warning(f"⚠️ Failed to log email: {e}")


def main():
    parser = argparse.ArgumentParser(description="Notify deactivated interns via email")
    parser.add_argument('--send', action='store_true', help='Actually send emails (default is dry-run)')
    parser.add_argument('--skip-confirm', action='store_true', help='Skip confirmation before sending')
    parser.add_argument('--list-only', action='store_true', help='Only list who would be notified')
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Deactivated Interns Notification System")
    logger.info("=" * 60)
    
    # Validate configuration
    is_valid, errors = config.validate_config()
    if not is_valid:
        logger.error("❌ Configuration errors:")
        for error in errors:
            logger.error(f"   {error}")
        sys.exit(1)
    
    logger.info("✅ Configuration valid\n")
    
    # Setup Google Sheets
    spreadsheet, worksheet = setup_google_sheets()
    if not worksheet:
        logger.error("❌ Failed to connect to Google Sheets")
        sys.exit(1)
    
    # Get deactivated interns
    logger.info("📋 Reading deactivated interns from sheet...")
    deactivated_interns = get_deactivated_interns(worksheet)
    
    if not deactivated_interns:
        logger.info("✅ No deactivated interns found")
        return
    
    logger.info(f"📧 Found {len(deactivated_interns)} deactivated interns\n")
    
    # Prepare email list
    emails_to_send = []
    for intern in deactivated_interns:
        email = intern['email']
        
        if not email and intern['slack_id']:
            logger.info(f"📧 Fetching email for {intern['slack_id']}...")
            email = get_email_from_slack(intern['slack_id'])
        
        if email:
            emails_to_send.append({
                'intern': intern,
                'email': email,
            })
        else:
            logger.warning(f"⚠️ No email found for {intern.get('display_name', intern['slack_id'])}")
    
    if not emails_to_send:
        logger.error("❌ No valid emails found for any interns")
        sys.exit(1)
    
    logger.info(f"\n✅ Ready to send {len(emails_to_send)} emails\n")
    
    # Show preview
    logger.info("📋 PREVIEW:")
    for item in emails_to_send[:3]:  # Show first 3
        intern = item['intern']
        logger.info(f"   To: {item['email']}")
        logger.info(f"   Name: {intern['display_name']}")
        logger.info(f"   Stage: {intern['stage']}\n")
    
    if len(emails_to_send) > 3:
        logger.info(f"   ... and {len(emails_to_send) - 3} more\n")
    
    # Dry-run or send
    if args.list_only:
        logger.info("📋 Interns who would be notified:")
        for item in emails_to_send:
            logger.info(f"   ✓ {item['email']} ({item['intern']['display_name']})")
        return
    
    if not args.send:
        logger.info("🔍 DRY-RUN MODE (no emails will be sent)")
        logger.info("   Use --send flag to actually send emails")
        return
    
    # Confirm before sending
    if config.REQUIRE_CONFIRMATION and not args.skip_confirm:
        confirm = input(f"\n⚠️  About to send {len(emails_to_send)} emails. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("❌ Cancelled")
            return
    
    # Get Gmail service
    logger.info("\n📧 Setting up Gmail service...")
    gmail_service = get_gmail_service()
    if not gmail_service:
        logger.error("❌ Failed to setup Gmail service")
        sys.exit(1)
    
    # Send emails
    logger.info(f"📧 Sending {len(emails_to_send)} emails...\n")
    
    sent_count = 0
    failed_count = 0
    
    for idx, item in enumerate(emails_to_send, 1):
        intern = item['intern']
        email = item['email']
        
        # Generate email content
        email_content = email_templates.get_deactivation_email(
            intern_name=intern['display_name'] or intern['slack_id'],
            stage_number=int(intern['stage']) if intern['stage'] and intern['stage'].isdigit() else None,
            feedback=intern['feedback'] if config.INCLUDE_FEEDBACK else None
        )
        
        logger.info(f"[{idx}/{len(emails_to_send)}] Sending to {email}...")
        
        success = send_email_gmail(
            gmail_service,
            email,
            email_content['subject'],
            email_content['body']
        )
        
        log_sent_email(intern, email, success)
        
        if success:
            sent_count += 1
        else:
            failed_count += 1
        
        # Rate limiting
        if idx < len(emails_to_send):
            time.sleep(config.EMAIL_DELAY)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Sent: {sent_count}/{len(emails_to_send)}")
    logger.info(f"❌ Failed: {failed_count}/{len(emails_to_send)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
