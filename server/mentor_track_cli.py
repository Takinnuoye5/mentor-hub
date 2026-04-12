"""
Mentor Track CLI Module

Handles saving and retrieving mentor track selections.
This module bridges the server's interactive UI with Google Sheets persistence.
"""

import os
import sys
import logging
import traceback
from datetime import datetime
from typing import List, Optional
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Import configuration from core module
try:
    from mentor_hub.core.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SPREADSHEET_NAME
except ImportError:
    from core.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SPREADSHEET_NAME


def _get_google_sheets_client():
    """Get authenticated Google Sheets client."""
    try:
        if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
            logger.warning(f"⚠️ Google credentials file not found at {GOOGLE_CREDENTIALS_FILE}")
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
        logger.error(f"❌ Error setting up Google Sheets client: {e}")
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
    logger.info(f"\n🔍 STARTING save_track_selection for user: {user_id}, tracks: {selected_tracks}")
    
    try:
        logger.info(f"1️⃣ Getting Google Sheets client...")
        client = _get_google_sheets_client()
        if not client:
            logger.error(f"❌ Could not connect to Google Sheets")
            return False

        logger.info(f"2️⃣ Opening spreadsheet: {GOOGLE_SPREADSHEET_NAME}")
        spreadsheet = client.open(GOOGLE_SPREADSHEET_NAME)
        logger.info(f"✅ Spreadsheet opened successfully")
        
        # Get the latest worksheet
        worksheets = spreadsheet.worksheets()
        logger.info(f"3️⃣ Found {len(worksheets)} worksheets")
        if not worksheets:
            logger.error(f"❌ No worksheets found in {GOOGLE_SPREADSHEET_NAME}")
            return False
        
        worksheet = worksheets[-1]
        logger.info(f"✅ Using worksheet: {worksheet.title}")
        
        # Get the header row first
        logger.info(f"4️⃣ Getting header row...")
        header = worksheet.row_values(1)
        logger.info(f"DEBUG: Header columns ({len(header)} total): {header}")
        
        if "Selected Tracks" not in header:
            logger.error(f"❌ 'Selected Tracks' column NOT found in worksheet!")
            logger.error(f"   Available columns: {header}")
            return False
        logger.info(f"✅ 'Selected Tracks' column found at index {header.index('Selected Tracks')}")
        
        # Get all records to find or create the mentor row
        logger.info(f"5️⃣ Getting all records from worksheet...")
        records = worksheet.get_all_records()
        logger.info(f"✅ Found {len(records)} total records in sheet")
        
        # Find the user in the sheet
        logger.info(f"6️⃣ Searching for user {user_id}...")
        user_row = None
        user_row_index = None
        for i, record in enumerate(records):
            slack_id = record.get("Slack ID", "").strip()
            logger.info(f"   Record {i}: Slack ID='{slack_id}'")
            if slack_id == user_id:
                user_row = i + 2  # Sheet rows are 1-indexed, +1 for header
                user_row_index = i
                logger.info(f"✅ FOUND user at record index {i}, sheet row {user_row}")
                break
        
        # If user not found, add them to the sheet
        if user_row is None:
            logger.info(f"⚠️ User {user_id} NOT in sheet - adding as new user")
            try:
                tracks_str = ",".join(selected_tracks)
                # Append a new row - just add to the end
                worksheet.append_row([user_id, "", "", "", tracks_str])
                logger.info(f"✅ Successfully appended new user with tracks: {tracks_str}")
                return True
            except Exception as e:
                logger.error(f"❌ Error appending new user to sheet: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False
        
        # Update the "Selected Tracks" column for existing user
        logger.info(f"7️⃣ Updating existing user's tracks...")
        col_index = header.index("Selected Tracks") + 1  # +1 because columns are 1-indexed
        tracks_str = ",".join(selected_tracks)
        
        logger.info(f"   Row: {user_row}, Column: {col_index}, Value: {tracks_str}")
        worksheet.update_cell(user_row, col_index, tracks_str)
        logger.info(f"✅ Successfully updated cell")
        
        logger.info(f"✅ COMPLETED - Updated track selection for user {user_id}: {tracks_str}\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ FAILED - Error saving track selection: {e}")
        logger.error(traceback.format_exc())
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
