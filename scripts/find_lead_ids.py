#!/usr/bin/env python3
"""
Script to find Slack IDs for track leads from the mentor sheet.
This will help us complete the TRACKS dictionary with missing IDs.
"""
import os
import sys
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

# Google Sheets configuration
GOOGLE_CREDENTIALS_FILE = "C:/hng13-cohort-bot-37fdf94a0219.json"
SPREADSHEET_NAME = "HNG Mentor Track Selection"

# Names we need to find IDs for
MISSING_LEADS = [
    "Avi",
    "EL'TANA", 
    "prudentbird",
    "MiKEY",
    "Adaeze",
    "Lawal",
    "0xCollins",
    "Fiza",
    "Cynth.",
    "Lynn.B",
    "CalebJ",
    "Neon",
    "Phelickz",
    "DiLo",
    "HendrixX",
    "Her Chaos",
    "M.I",
    "King Majestic"
]


def setup_google_sheets():
    """Set up Google Sheets API connection."""
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            GOOGLE_CREDENTIALS_FILE, scope
        )
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"❌ Error setting up Google Sheets: {e}")
        sys.exit(1)


def normalize_name(name):
    """Normalize a name for comparison."""
    if not name:
        return ""
    # Convert to lowercase, strip whitespace, remove special chars
    return name.lower().strip().replace(".", "").replace("'", "").replace(" ", "")


def find_lead_ids():
    """Find Slack IDs for the missing track leads."""
    print("🔍 Searching for Slack IDs of track leads in the mentor sheet...\n")
    
    # Connect to Google Sheets
    client = setup_google_sheets()
    
    try:
        spreadsheet = client.open(SPREADSHEET_NAME)
        print(f"✅ Opened spreadsheet: {SPREADSHEET_NAME}")
        
        # Get the latest worksheet
        worksheets = spreadsheet.worksheets()
        if not worksheets:
            print("❌ No worksheets found in spreadsheet")
            return
        
        worksheet = worksheets[-1]  # Get the latest worksheet
        print(f"📄 Using worksheet: {worksheet.title}")
        
        # Get all records
        records = worksheet.get_all_records()
        print(f"📊 Found {len(records)} total records\n")
        
        # Create a mapping of normalized names to search for
        search_names = {normalize_name(name): name for name in MISSING_LEADS}
        
        # Results storage
        found = {}
        
        # Search through all records
        for record in records:
            # Get name and Slack ID from the record
            # Check various possible column names
            name_fields = ['Name', 'Full Name', 'name', 'full_name', 'Display Name', 'display_name']
            id_fields = ['Slack ID', 'SlackID', 'slack_id', 'Slack User ID', 'User ID', 'user_id']
            
            name = None
            slack_id = None
            
            for field in name_fields:
                if field in record and record[field]:
                    name = record[field]
                    break
            
            for field in id_fields:
                if field in record and record[field]:
                    slack_id = record[field]
                    break
            
            if not name or not slack_id:
                continue
            
            # Normalize and check if this matches any of our search names
            norm_name = normalize_name(name)
            
            # Check for exact match or partial match
            for search_norm, original_name in search_names.items():
                if search_norm in norm_name or norm_name in search_norm:
                    # Validate the Slack ID format
                    if isinstance(slack_id, str) and slack_id.startswith('U') and len(slack_id) >= 9:
                        found[original_name] = {
                            'slack_id': slack_id,
                            'sheet_name': name
                        }
                        print(f"✅ Found: {original_name:20s} -> {slack_id} (from sheet: {name})")
        
        # Show results
        print(f"\n{'='*80}")
        print(f"📊 SUMMARY: Found {len(found)} out of {len(MISSING_LEADS)} track leads")
        print(f"{'='*80}\n")
        
        if found:
            print("✅ Found IDs (copy these to update TRACKS):\n")
            for name in MISSING_LEADS:
                if name in found:
                    slack_id = found[name]['slack_id']
                    sheet_name = found[name]['sheet_name']
                    print(f'    "{name}" -> "{slack_id}",  # {sheet_name}')
        
        # Show what's still missing
        missing = [name for name in MISSING_LEADS if name not in found]
        if missing:
            print(f"\n⚠️ Still missing ({len(missing)}):")
            for name in missing:
                print(f"   - {name}")
            print("\nTip: These users might not be in the mentor sheet yet.")
            print("You can find their IDs by:")
            print("  1. Having them fill out the mentor form")
            print("  2. Looking them up in Slack workspace settings")
            print("  3. Using the Slack API to search for them")
        
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ Spreadsheet not found: {SPREADSHEET_NAME}")
        print("   Make sure the service account has access to the sheet")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    find_lead_ids()
