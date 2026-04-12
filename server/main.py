#!/usr/bin/env python3
"""
Mentor Track Slack Command Handler

This script handles the /mentor-track Slack command to allow mentors
to select their preferred tracks directly from Slack.

Production-ready server with proper logging, security, and error handling.
"""

import logging
import os
import json
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Any

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from dotenv import load_dotenv
import requests

# ============================================================================
# LOGGING SETUP
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# LOAD CONFIGURATION
# ============================================================================
load_dotenv()

# Import core modules
try:
    from mentor_hub.core import user_cache
    from mentor_hub.core.config import (
        CHANNEL_IDS, 
        SYSTEM_SETTINGS, 
        TRACKS,
        GOOGLE_CREDENTIALS_FILE,
        GOOGLE_SPREADSHEET_NAME
    )
except ImportError:
    # Fallback for direct execution during development
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        from core import user_cache
        from core.config import (
            CHANNEL_IDS,
            SYSTEM_SETTINGS,
            TRACKS,
            GOOGLE_CREDENTIALS_FILE,
            GOOGLE_SPREADSHEET_NAME
        )
    except ImportError:
        logger.error("Failed to import core modules")
        CHANNEL_IDS = {}
        SYSTEM_SETTINGS = {"testing_mode": False}
        TRACKS = {}
        # Read from environment variables as fallback
        GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE")
        GOOGLE_SPREADSHEET_NAME = os.getenv("GOOGLE_SPREADSHEET_NAME", "HNG 14 Mentor Track Selection")

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================
TESTING_MODE: bool = SYSTEM_SETTINGS.get("testing_mode", False)
LOG_INSTEAD_OF_NOTIFY: bool = SYSTEM_SETTINGS.get("log_instead_of_notify", False)

USER_TOKEN: Optional[str] = os.getenv("SLACK_USER_TOKEN_HNG14")
BOT_TOKEN: Optional[str] = os.getenv("SLACK_BOT_TOKEN_HNG14")
SLACK_SIGNING_SECRET: Optional[str] = os.getenv("SLACK_SIGNING_SECRET_HNG14")
API_REQUEST_TIMEOUT: int = int(os.getenv("API_REQUEST_TIMEOUT", "5"))

# ============================================================================
# VALIDATE ENVIRONMENT ON STARTUP
# ============================================================================
def validate_environment() -> None:
    """Validate all required environment variables on startup"""
    if not BOT_TOKEN:
        raise RuntimeError("SLACK_BOT_TOKEN_HNG14 environment variable is required")
    if not USER_TOKEN:
        raise RuntimeError("SLACK_USER_TOKEN_HNG14 environment variable is required")
    if not SLACK_SIGNING_SECRET:
        raise RuntimeError("SLACK_SIGNING_SECRET_HNG14 environment variable is required")
    if not GOOGLE_CREDENTIALS_FILE:
        raise ValueError("GOOGLE_CREDENTIALS_FILE environment variable is required")
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        raise FileNotFoundError(f"Google credentials file not found: {GOOGLE_CREDENTIALS_FILE}")
    logger.info("✅ All environment variables validated successfully")

# ============================================================================
# INITIALIZE FASTAPI
# ============================================================================
app = FastAPI(title="Mentor Hub - Slack Integration", version="1.0.0")

# ============================================================================
# SLACK CLIENTS & VERIFIER
# ============================================================================
bot_client = WebClient(token=BOT_TOKEN)
signature_verifier = SignatureVerifier(signing_secret=SLACK_SIGNING_SECRET)

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================
MENTORS_CHANNEL_ID: str = CHANNEL_IDS.get("mentors", "C0AEHQ6QGUB")
MENTOR_RANDOM_CHANNEL_ID: str = CHANNEL_IDS.get("mentor_random", "C0AFU2RH486")
BOT_ANNOUNCEMENT_CHANNEL: str = CHANNEL_IDS.get("announcements", "C0AM51P504W")
ADMIN_NOTIFICATION_CHANNEL: str = CHANNEL_IDS.get("admin_notifications", "C0AM51P504W")
DISABLE_ADMIN_NOTIFICATIONS: bool = os.getenv("DISABLE_ADMIN_NOTIFICATIONS", "true").lower() == "true"

# In-memory storage (temporary - should use Redis/DB in production)
active_selections: Dict[str, List[str]] = {}
response_urls: Dict[str, str] = {}

# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_slack_user_id(user_id: str) -> bool:
    """Validate format of Slack user ID"""
    return bool(user_id) and user_id.startswith("U") and len(user_id) > 5

def validate_track_selection(tracks: List[str]) -> bool:
    """Validate all tracks exist in TRACKS config"""
    valid_tracks = set(TRACKS.keys()) if isinstance(TRACKS, dict) else set(TRACKS)
    return all(t in valid_tracks for t in tracks if t)

def verify_slack_signature(request_headers: Dict[str, str], raw_body: bytes) -> bool:
    """Verify Slack request signature for security"""
    timestamp = request_headers.get("x-slack-request-timestamp") or request_headers.get("X-Slack-Request-Timestamp", "")
    signature = request_headers.get("x-slack-signature") or request_headers.get("X-Slack-Signature", "")
    
    # Log debug info
    logger.debug(f"Verifying signature - timestamp: {timestamp}, signature present: {bool(signature)}")
    
    if not timestamp or not signature:
        logger.error(f"Missing headers - timestamp: {bool(timestamp)}, signature: {bool(signature)}")
        logger.error(f"Available headers: {list(request_headers.keys())}")
        return False
    
    try:
        return signature_verifier.is_valid(timestamp=timestamp, body=raw_body, signature=signature)
    except Exception as e:
        logger.error(f"Error verifying Slack signature: {e}")
        return False

def track_id_to_display_name(track_id: str) -> str:
    """Convert track ID to human-readable name"""
    names = {
        "frontend": "Frontend Development", "backend": "Backend Development",
        "mobile": "Mobile Development", "uiux": "Product Design (UI/UX)",
        "pm": "Product Management", "devops": "DevOps",
        "data-analysis": "Data Analysis/Science", "qa": "Quality Assurance",
        "virtual-assistant": "Virtual Assistant", "marketing": "Marketing",
        "video": "Video Production", "graphics": "Graphics Design",
        "automations": "Automations"
    }
    return names.get(track_id, track_id)

def update_slack_message(
    user_id: str, blocks: List[Dict[str, Any]], text: str = "Message updated",
    channel_id: Optional[str] = None, message_ts: Optional[str] = None,
    response_url: Optional[str] = None, replace_original: bool = True
) -> bool:
    """Update a Slack message using the best available method"""
    logger.debug(f"Updating message for user {user_id}")
    
    # Try response URL
    if response_url:
        try:
            response = requests.post(response_url, json={
                "replace_original": replace_original, "text": text, "blocks": blocks
            }, timeout=API_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return True
        except Exception as e:
            logger.error(f"Error using response_url: {e}")
    
    # Try stored URL
    stored_url = response_urls.get(user_id)
    if stored_url and stored_url != response_url:
        try:
            response = requests.post(stored_url, json={
                "replace_original": replace_original, "text": text, "blocks": blocks
            }, timeout=API_REQUEST_TIMEOUT)
            if response.status_code == 200:
                return True
        except Exception as e:
            logger.error(f"Error using stored response_url: {e}")
    
    # Try chat.update
    if channel_id and message_ts:
        try:
            bot_client.chat_update(channel=channel_id, ts=message_ts, text=text, blocks=blocks)
            return True
        except SlackApiError as e:
            logger.error(f"Error updating via chat.update: {e.response.get('error')}")
    
    return False

def notify_admin_channel(user_id: str, selected_tracks: List[str], is_update: bool = False) -> bool:
    """Send a notification to the admin channel about track selection"""
    if DISABLE_ADMIN_NOTIFICATIONS:
        logger.info(f"Track selection for user {user_id}: {selected_tracks}")
        return True
    
    try:
        user_info = bot_client.users_info(user=user_id)
        user_name = user_info["user"].get("real_name", user_id)
        readable_tracks = [track_id_to_display_name(t) for t in selected_tracks]
        
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"{'🔄 *Track Update*' if is_update else '✨ *New Track Selection*'}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*User*: {user_name}\n*Tracks*: {', '.join(readable_tracks)}"}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"}]}
        ]
        
        if TESTING_MODE:
            logger.info(f"[TESTING] Would send: {readable_tracks}")
            return True
        
        bot_client.chat_postMessage(channel=ADMIN_NOTIFICATION_CHANNEL, text="Track Selection", blocks=blocks)
        logger.info(f"Sent notification for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        return False

# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup_event() -> None:
    """Validate environment and initialize on startup"""
    try:
        validate_environment()
        logger.info("✅ Mentor Hub server started successfully")
        threading.Thread(target=_init_user_cache, daemon=True).start()
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise

def _init_user_cache() -> None:
    """Initialize user cache in background"""
    try:
        user_cache.load_user_cache()
        logger.info("✅ User cache initialized")
    except Exception as e:
        logger.error(f"Failed to initialize user cache: {e}")

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/test")
async def test_endpoint() -> Dict[str, str]:
    """Simple test endpoint"""
    return {"status": "ok", "message": "Test endpoint working"}

@app.get("/ping")
async def ping() -> Dict[str, str]:
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/slack/mentor-track")
async def handle_mentor_track_command(request: Request) -> Response:
    """Handle /mentor-track Slack command"""
    # Verify signature
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not verify_slack_signature(headers, raw_body):
        logger.warning("Unauthorized request to /mentor-track")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    try:
        form_data = await request.form()
        user_id = form_data.get("user_id", "")
        channel_id = form_data.get("channel_id", "")
        response_url = form_data.get("response_url", "")
        
        if not validate_slack_user_id(user_id):
            raise ValueError(f"Invalid user ID: {user_id}")
        
        logger.info(f"Received /mentor-track from user {user_id}")
        
        if response_url:
            response_urls[user_id] = response_url
        
    except Exception as e:
        logger.error(f"Error parsing request: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=400)
    
    # Build track options
    track_list = TRACKS.keys() if isinstance(TRACKS, dict) else TRACKS
    track_options = [
        {"text": {"type": "plain_text", "text": track_id_to_display_name(t), "emoji": True},
         "value": t, "description": {"type": "plain_text", "text": f"Mentor in {track_id_to_display_name(t)}", "emoji": True}}
        for t in track_list
    ]
    
    # Create blocks
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*Please select the track(s) you would like to mentor:*"}},
        {"type": "divider"},
        {"type": "section", "block_id": "track_selection", "text": {"type": "mrkdwn", "text": "Select all tracks you're interested in:"},
         "accessory": {"type": "multi_static_select", "placeholder": {"type": "plain_text", "text": "Select tracks"},
                       "action_id": "track_checkboxes", "options": track_options}},
        {"type": "actions", "block_id": "track_submit", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Submit Selection"},
             "style": "primary", "action_id": "submit_tracks",
             "confirm": {"title": {"type": "plain_text", "text": "Confirm Selection"},
                        "text": {"type": "plain_text", "text": "This will save your track selection."},
                        "confirm": {"type": "plain_text", "text": "Submit"}}}
        ]}
    ]
    
    try:
        bot_client.chat_postEphemeral(channel=channel_id, user=user_id, text="Select your tracks", blocks=blocks)
        logger.info(f"Sent track selection UI to user {user_id}")
        return Response()
    except SlackApiError as e:
        error = e.response.get('error', str(e))
        logger.error(f"Failed to send message: {error}")
        raise HTTPException(status_code=500, detail=f"Failed: {error}")

@app.post("/slack/interactive")
async def handle_interactive_components(request: Request) -> JSONResponse:
    """Handle interactive components"""
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not verify_slack_signature(headers, raw_body):
        logger.warning("Unauthorized interactive request")
        raise HTTPException(status_code=403)
    
    try:
        form_data = await request.form()
        payload = json.loads(form_data.get("payload", "{}"))
        
        actions = payload.get("actions", [])
        if not actions:
            return JSONResponse(content={"text": ""})
        
        user_id = payload.get("user", {}).get("id", "")
        if not validate_slack_user_id(user_id):
            return JSONResponse(content={"text": ""})
        
        action_id = actions[0].get("action_id", "")
        threading.Thread(target=_process_action, args=(action_id, payload), daemon=True).start()
        
        return JSONResponse(content={"text": ""})
    except Exception as e:
        logger.error(f"Error in interactive handler: {e}")
        return JSONResponse(content={"text": ""})

def _process_action(action_id: str, payload: Dict[str, Any]) -> None:
    """Process interactive action in background"""
    user_id = payload.get("user", {}).get("id", "")
    
    try:
        if action_id == "track_checkboxes":
            actions = payload.get("actions", [])
            if actions:
                selected = [o.get("value") for o in actions[0].get("selected_options", [])]
                active_selections[user_id] = selected
                logger.info(f"User {user_id} selected: {selected}")
        
        elif action_id == "submit_tracks":
            _process_submission(user_id, payload)
    except Exception as e:
        logger.error(f"Error processing action: {e}")

def _process_submission(user_id: str, payload: Dict[str, Any]) -> None:
    """Process track submission"""
    try:
        # Get selected tracks
        tracks = []
        state = payload.get("state", {}).get("values", {})
        for block in state.values():
            for action in block.values():
                tracks = [o.get("value") for o in action.get("selected_options", [])]
                if tracks:
                    break
        
        if not tracks:
            tracks = active_selections.get(user_id, [])
        
        if not tracks or not validate_track_selection(tracks):
            logger.warning(f"No valid tracks from {user_id}")
            return
        
        logger.info(f"Saving tracks for {user_id}: {tracks}")
        
        # Import and save
        try:
            from server.mentor_track_cli import save_track_selection, check_if_mentor_exists
        except ImportError:
            from mentor_track_cli import save_track_selection, check_if_mentor_exists
        
        if save_track_selection(user_id, tracks):
            readable = [track_id_to_display_name(t) for t in tracks]
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": "✅ *Track selection saved!*"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"Selected: *{', '.join(readable)}*"}}
            ]
            
            update_slack_message(user_id, blocks, "✅ Saved", 
                               payload.get("channel", {}).get("id"), 
                               payload.get("container", {}).get("message_ts"),
                               payload.get("response_url"))
            
            # Send DM
            try:
                if not TESTING_MODE:
                    dm = bot_client.conversations_open(users=user_id)
                    bot_client.chat_postMessage(channel=dm["channel"]["id"], 
                                               text=f"✅ Selected: {', '.join(readable)}")
            except Exception as e:
                logger.error(f"DM error: {e}")
            
            # Notify admin
            is_update = check_if_mentor_exists(user_id)
            notify_admin_channel(user_id, tracks, is_update)
    except Exception as e:
        logger.error(f"Submission error: {e}")

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
