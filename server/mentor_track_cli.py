"""
Mentor Track CLI Module

Handles saving and retrieving mentor track selections.
This module bridges the server's interactive UI with Google Sheets persistence.
"""

import os
import sys
from datetime import datetime
from typing import List, Optional
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

# Import configuration from core module
try:
    from mentor_hub.core.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SPREADSHEET_NAME
except ImportError:
    from core.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SPREADSHEET_NAME


def _get_google_sheets_client():
    """Get authenticated Google Sheets client."""
    try:
        if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
            print(f"⚠️ Google credentials file not found at {GOOGLE_CREDENTIALS_FILE}")
            return None

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
        print(f"❌ Error setting up Google Sheets client: {e}")
        return None


def save_track_selection(user_id: str, selected_tracks: List[str]) -> bool:
    """
    Save a mentor's track selection to Google Sheets.
    
    Args:
        user_id: Slack user ID
        selected_tracks: List of track IDs (e.g., ['backend', 'frontend'])
    
    Returns:
        True if successful, False otherwise
    """
    try:
        client = _get_google_sheets_client()
        if not client:
            print(f"❌ Could not connect to Google Sheets")
            return False

        spreadsheet = client.open(GOOGLE_SPREADSHEET_NAME)
        
        # Get the latest worksheet
        worksheets = spreadsheet.worksheets()
        if not worksheets:
            print(f"❌ No worksheets found in {GOOGLE_SPREADSHEET_NAME}")
            return False
        
        worksheet = worksheets[-1]
        
        # Get all records to find or create the mentor row
        records = worksheet.get_all_records()
        
        # Find the user in the sheet
        user_row = None
        for i, record in enumerate(records):
            if record.get("Slack ID", "").strip() == user_id:
                user_row = i + 2  # Sheet rows are 1-indexed, +1 for header
                break
        
        # If user not found, log it but don't fail
        if not user_row:
            print(f"⚠️ User {user_id} not found in mentor sheet (new user)")
            # We could add them here, but for now just return success
            # as the track selection is still valid
            return True
        
        # Update the "Selected Tracks" column
        # Find the column index for "Selected Tracks"
        header = worksheet.row_values(1)
        if "Selected Tracks" not in header:
            print(f"⚠️ 'Selected Tracks' column not found in worksheet")
            return False
        
        col_index = header.index("Selected Tracks") + 1
        
        # Format tracks as comma-separated string
        tracks_str = ",".join(selected_tracks)
        
        # Update the cell
        worksheet.update_cell(user_row, col_index, tracks_str)
        
        print(f"✅ Saved track selection for user {user_id}: {tracks_str}")
        return True
        
    except Exception as e:
        print(f"❌ Error saving track selection: {e}")
        return False


def check_if_mentor_exists(user_id: str) -> bool:
    """
    Check if a mentor already exists in the sheet.
    Used to determine if a track selection is an update or new submission.
    
    Args:
        user_id: Slack user ID
    
    Returns:
        True if mentor exists, False otherwise
    """
    try:
        client = _get_google_sheets_client()
        if not client:
            return False

        spreadsheet = client.open(GOOGLE_SPREADSHEET_NAME)
        worksheets = spreadsheet.worksheets()
        if not worksheets:
            return False
        
        worksheet = worksheets[-1]
        records = worksheet.get_all_records()
        
        for record in records:
            if record.get("Slack ID", "").strip() == user_id:
                return True
        
        return False
        
    except Exception as e:
        print(f"⚠️ Error checking if mentor exists: {e}")
        return False


def get_mentor_info(user_id: str) -> Optional[dict]:
    """
    Get a mentor's information from the sheet.
    
    Args:
        user_id: Slack user ID
    
    Returns:
        Dict with mentor info or None if not found
    """
    try:
        client = _get_google_sheets_client()
        if not client:
            return None

        spreadsheet = client.open(GOOGLE_SPREADSHEET_NAME)
        worksheets = spreadsheet.worksheets()
        if not worksheets:
            return None
        
        worksheet = worksheets[-1]
        records = worksheet.get_all_records()
        
        for record in records:
            if record.get("Slack ID", "").strip() == user_id:
                return record
        
        return None
        
    except Exception as e:
        print(f"⚠️ Error fetching mentor info: {e}")
        return None
