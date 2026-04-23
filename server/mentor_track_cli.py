"""
Mentor Track CLI Module

Handles saving and retrieving mentor track selections.
This module bridges the server's interactive UI with Google Sheets persistence.
"""

import os
import sys
import logging
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
    try:
        client = _get_google_sheets_client()
        if not client:
            logger.error(f"Failed to connect to Google Sheets client")
            return False

        spreadsheet = client.open(GOOGLE_SPREADSHEET_NAME)
        
        # Find the "Mentors" worksheet
        worksheets = spreadsheet.worksheets()
        if not worksheets:
            logger.error(f"No worksheets found in {GOOGLE_SPREADSHEET_NAME}")
            return False
        
        # Try to find "Mentors" worksheet, otherwise use the first one
        worksheet = None
        for ws in worksheets:
            if "Mentors" in ws.title:
                worksheet = ws
                break
        
        if not worksheet:
            worksheet = worksheets[0]
        
        logger.debug(f"Using worksheet: {worksheet.title}")
        
        # Get the header row and find column index
        header = worksheet.row_values(1)
        
        if "Selected Tracks" not in header:
            logger.error(f"'Selected Tracks' column not found in worksheet. Available: {header}")
            return False
        
        # Get all records to find or create the mentor row
        records = worksheet.get_all_records()
        
        # Find the user in the sheet
        user_row = None
        for i, record in enumerate(records):
            if record.get("Slack ID", "").strip() == user_id:
                user_row = i + 2  # Sheet rows are 1-indexed, +1 for header
                logger.debug(f"Found user {user_id} at sheet row {user_row}")
                break
        
        # If user not found, add them to the sheet
        if user_row is None:
            try:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                tracks_str = ",".join(selected_tracks)
                
                # Get user display name from Slack if possible
                from slack_sdk import WebClient
                slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN_HNG14"))
                user_info = slack_client.users_info(user=user_id)
                # Use display_name first, fall back to real_name
                display_name = user_info['user'].get('profile', {}).get('display_name', '') or user_info['user'].get('real_name', '')
                email = user_info['user'].get('profile', {}).get('email', '')
                
                # Append: Timestamp, Slack ID, Display Name, Email, Selected Tracks
                worksheet.append_row([timestamp, user_id, display_name, email, tracks_str])
                logger.info(f"Added new mentor {user_id} with tracks: {tracks_str}")
                return True
            except Exception as e:
                logger.error(f"Failed to add new mentor {user_id}: {e}", exc_info=True)
                return False
        
        # Update the "Selected Tracks" column for existing user
        col_index = header.index("Selected Tracks") + 1  # +1 because columns are 1-indexed
        tracks_str = ",".join(selected_tracks)
        
        worksheet.update_cell(user_row, col_index, tracks_str)
        logger.info(f"Updated tracks for mentor {user_id}: {tracks_str}")
        return True
        
    except Exception as e:
        logger.error(f"Error saving track selection for {user_id}: {e}", exc_info=True)
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
        
        # Use the same worksheet selection logic
        worksheet = None
        for ws in worksheets:
            if "Mentors" in ws.title:
                worksheet = ws
                break
        
        if not worksheet:
            worksheet = worksheets[0]
        
        records = worksheet.get_all_records()
        
        for record in records:
            if record.get("Slack ID", "").strip() == user_id:
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking if mentor exists: {e}", exc_info=True)
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
        
        # Use the same worksheet selection logic as save_track_selection
        worksheet = None
        for ws in worksheets:
            if "Mentors" in ws.title:
                worksheet = ws
                break
        
        if not worksheet:
            worksheet = worksheets[0]
        
        records = worksheet.get_all_records()
        
        for record in records:
            if record.get("Slack ID", "").strip() == user_id:
                return record
        
        return None
        
    except Exception as e:
        logger.error(f"Error fetching mentor info: {e}", exc_info=True)
        return None


def get_mentor_existing_tracks(user_id: str) -> List[str]:
    """
    Get a mentor's currently selected tracks from the sheet.
    
    Args:
        user_id: Slack user ID
    
    Returns:
        List of track IDs (e.g., ['backend', 'frontend']) or empty list if not found
    """
    mentor_info = get_mentor_info(user_id)
    if not mentor_info:
        return []
    
    tracks_str = mentor_info.get("Selected Tracks", "").strip()
    if not tracks_str:
        return []
    
    # Parse comma-separated tracks
    tracks = [t.strip() for t in tracks_str.split(",") if t.strip()]
    return tracks
