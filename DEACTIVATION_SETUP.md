# Deactivated Interns Notification System - Setup Guide

## Overview

This system automatically notifies interns who have been deactivated from the HNG 14 internship program. It:

1. Reads a Google Sheet containing deactivated interns
2. Fetches email addresses from Slack profiles
3. Sends professional notification emails via Gmail API
4. Logs all sent emails for record-keeping

## Files

- **`notify_deactivated_interns.py`** - Main script to send notifications
- **`config_deactivation.py`** - Configuration and settings
- **`email_templates.py`** - Email content templates

## Setup Steps

### Step 1: Prepare Your Google Sheet

Create or update a Google Sheet with the following columns (minimum required):

**Required Columns:**
- `Slack ID` - The Slack user ID of the intern
- `Status` - Mark as "Deactivated" when intern should be notified

**Optional Columns:**
- `Display Name` - Intern's name (for personalization)
- `Email` - If email is already in sheet (if not, will fetch from Slack)
- `Stage` - Which stage they failed (for reference)
- `Feedback` - Specific feedback about why they didn't continue
- `Date` - When they were deactivated

### Step 2: Configure the System

Edit `scripts/config_deactivation.py`:

```python
# Update the sheet name
DEACTIVATION_SHEET_NAME = "Your Sheet Name Here"

# Update column names to match your sheet
COLUMNS = {
    'slack_id': 'Slack ID',           # Your actual column name
    'display_name': 'Display Name',   # Your actual column name
    'email': 'Email',                 # Your actual column name
    'status': 'Status',               # Your actual column name
    # ... etc
}

# Adjust status values if different
STATUS_VALUES = {
    'deactivated': ['Deactivated', 'DEACTIVATED', 'Failed'],  # Add your values
    'active': ['Active'],
}
```

### Step 3: Setup Gmail API

#### 3a. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project: "HNG Mentor Hub"
3. Enable the Gmail API:
   - Go to "APIs & Services" → "Library"
   - Search for "Gmail API"
   - Click "Enable"

#### 3b. Create Service Account

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "Service Account"
3. Fill in:
   - Service account name: `hng-mentor-notifications`
   - Grant no roles (we'll setup email access)
4. Click "Create and Continue"
5. Click "Create Key" → JSON
6. Save the JSON file as `hng14-gmail-credentials.json` in the project root

#### 3c. Enable Send-As Permission

1. In [Google Admin Console](https://admin.google.com/):
   - Go to "Apps" → "Google Workspace" → "Gmail"
   - Scroll to "Gmail API access"
   - Check "Enable API access for all users" or specific user
   - Save

2. Grant the service account Send-As permission:
   - The service account email will be something like: `hng-mentor-notifications@{project-id}.iam.gserviceaccount.com`
   - In Gmail, go to Settings → Forwarding and POP/IMAP
   - Add the service account email as a delegate

### Step 4: Update .env File

Add these to your `.env` file:

```bash
# Gmail Configuration
GMAIL_SENDER_EMAIL=hng@gmail.com
GMAIL_CREDENTIALS_FILE=hng14-gmail-credentials.json

# Slack Configuration  
SLACK_BOT_TOKEN_HNG14=xoxb-your-token-here
```

### Step 5: Validate Configuration

Run the configuration validator:

```bash
python scripts/config_deactivation.py
```

Expected output:
```
🔍 Validating deactivation configuration...

✅ Configuration looks good!

Sheet: Your Sheet Name
Gmail Sender: hng@gmail.com
Dry Run: True
```

## Usage

### Dry-Run (Preview Emails - No Sending)

```bash
python scripts/notify_deactivated_interns.py
```

This will:
- Read the deactivated interns from the sheet
- Show a preview of who would be notified
- NOT send any actual emails

### List Only

```bash
python scripts/notify_deactivated_interns.py --list-only
```

Shows just the list of interns who would be notified.

### Send Emails (With Confirmation)

```bash
python scripts/notify_deactivated_interns.py --send
```

This will:
- Read deactivated interns
- Ask for confirmation before sending
- Send actual notification emails
- Log all sent emails

### Send Emails (Skip Confirmation)

```bash
python scripts/notify_deactivated_interns.py --send --skip-confirm
```

Sends emails without asking for confirmation (useful for cron jobs).

## Email Content

The system sends a professional email containing:

1. **Personal greeting** - Uses intern's name
2. **Notification** - Clear that they didn't progress
3. **Reason** - Brief explanation of performance review
4. **Optional feedback** - Specific feedback if available in sheet
5. **Encouragement** - Next steps and how to reapply
6. **Next cohort info** - When they can try again

Edit `scripts/email_templates.py` to customize the message.

## Logging

All sent emails are logged to `logs/deactivation_emails.log` with:
- Timestamp
- Intern Slack ID and name
- Email address
- Success/failure status
- Gmail message ID

## Troubleshooting

### Issue: "GMAIL_CREDENTIALS_FILE not found"

**Solution:**
- Ensure `hng14-gmail-credentials.json` is in the project root directory
- Update path in `.env` if stored elsewhere

### Issue: "Failed to connect to Google Sheets"

**Solution:**
- Verify `DEACTIVATION_SHEET_NAME` matches exactly (case-sensitive)
- Check that the Gmail credentials file has Sheets API permissions
- Ensure the sheet is shared with the service account email

### Issue: "No email in Slack profile"

**Solution:**
- Add an `Email` column to your Google Sheet with email addresses
- Update `config_deactivation.py` to use that column
- Ensure Slack users have email addresses in their profiles

### Issue: "Gmail API errors"

**Solution:**
- Verify service account has Send-As permissions
- Check that Gmail API is enabled in Google Cloud Console
- Ensure the credentials file is valid JSON

## Advanced: Scheduling

To run this automatically on a schedule, add a cron job:

```bash
# Daily at 10 AM
0 10 * * * cd /path/to/mentor-hub && python scripts/notify_deactivated_interns.py --send --skip-confirm

# Weekly on Monday at 9 AM
0 9 * * 1 cd /path/to/mentor-hub && python scripts/notify_deactivated_interns.py --send --skip-confirm
```

## Support

For issues or questions, refer to:
- `config_deactivation.py` - for configuration details
- `email_templates.py` - for email customization
- `notify_deactivated_interns.py` - for implementation details
