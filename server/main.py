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
        GOOGLE_CREDENTIALS_FILE = None
        GOOGLE_SPREADSHEET_NAME = "HNG 14 Mentor Track Selection"

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
    timestamp = request_headers.get("X-Slack-Request-Timestamp", "")
    signature = request_headers.get("X-Slack-Signature", "")
    
    # Log debug info
    logger.debug(f"Verifying signature - timestamp: {timestamp}, signature present: {bool(signature)}")
    
    if not timestamp or not signature:
        logger.error(f"Missing headers - timestamp: {bool(timestamp)}, signature: {bool(signature)}")
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
    if not verify_slack_signature(dict(request.headers), raw_body):
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
    if not verify_slack_signature(dict(request.headers), raw_body):
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
            from mentor_track_cli import save_track_selection, check_if_mentor_exists
        except ImportError:
            from server.mentor_track_cli import save_track_selection, check_if_mentor_exists
        
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
#!/usr/bin/env python3
"""
Mentor Track Slack Command Handler

This script handles the /mentor-track Slack command to allow mentors
to select their preferred tracks directly from Slack.
"""

import os
import json
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from dotenv import load_dotenv
from datetime import datetime
import threading
import time
import requests

# Import core modules
try:
    from mentor_hub.core import user_cache
    from mentor_hub.core.config import CHANNEL_IDS, SYSTEM_SETTINGS
except ImportError:
    # Fallback for direct execution during development
    import user_cache
    try:
        from config import CHANNEL_IDS, SYSTEM_SETTINGS
    except ImportError:
        CHANNEL_IDS = {}
        SYSTEM_SETTINGS = {"testing_mode": False}

# Load environment variables
load_dotenv()

# Extract config settings
TESTING_MODE = SYSTEM_SETTINGS.get("testing_mode", False)  # Default to production mode
LOG_INSTEAD_OF_NOTIFY = SYSTEM_SETTINGS.get("log_instead_of_notify", False)

# Get tokens from environment variables
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")
BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET_HNG14")

# Initialize FastAPI app
app = FastAPI()

# Add a simple test endpoint
@app.get("/test")
async def test_endpoint():
    """Simple test endpoint"""
    return {"status": "ok", "message": "Test endpoint working"}

# Add health check endpoint for monitoring services
@app.get("/ping")
async def ping():
    """Health check endpoint for monitoring services"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# Initialize Slack client
bot_client = WebClient(token=BOT_TOKEN)

# Channel IDs (HNG 14)
MENTORS_CHANNEL_ID = "C0AEHQ6QGUB"  # HNG 14 mentors channel ID
MENTOR_RANDOM_CHANNEL_ID = "C0AFU2RH486"  # HNG 14 mentor-random channel ID
BOT_ANNOUNCEMENT_CHANNEL = "C0AM51P504W"  # HNG 14 bot announcements channel
ADMIN_NOTIFICATION_CHANNEL = "C0AM51P504W"  # HNG 14 admin notifications channel

# Feature flags
DISABLE_ADMIN_NOTIFICATIONS = True  # Set to True to disable admin channel notifications but keep DMs

# Storage for active track selections and response URLs
active_selections = {}  # Stores user's active track selections
response_urls = {}      # Stores response URLs for updating ephemeral messages

import requests

def update_slack_message(user_id, blocks, text="Message updated", channel_id=None, message_ts=None, response_url=None, replace_original=True):
    """Update a Slack message using the best available method
    
    Attempts three methods in order:
    1. Use provided response_url (best for ephemeral messages)
    2. Use stored response URL for the user if available
    3. Use chat.update API with message_ts (works for non-ephemeral messages)
    
    Returns True if any method succeeds, False otherwise
    """
    updated = False
    success = False
    response_success = False
    
    # Debug the input parameters
    print(f"🔍 update_slack_message parameters: user_id={user_id}, channel_id={channel_id}, message_ts={message_ts}")
    print(f"🔍 response_url available: {bool(response_url)}, stored response_url available: {user_id in response_urls}")
    
    # Method 1: Try using provided response_url
    if response_url:
        try:
            print(f"🔄 Updating message via provided response_url for user {user_id}")
            response = requests.post(
                response_url,
                json={
                    "replace_original": True,  # Always force replace to fix the UI
                    "text": text,
                    "blocks": blocks
                },
                timeout=5  # Add a timeout to prevent hanging
            )
            
            if response.status_code == 200:
                print("✅ Successfully updated message via provided response_url")
                response_success = True
                success = True
            else:
                print(f"❌ Failed to update via provided response_url: {response.status_code} {response.text}")
        except Exception as e:
            print(f"❌ Error using provided response_url: {str(e)}")
    
    # Method 2: Try using stored response URL for user
    stored_url = response_urls.get(user_id)
    if stored_url and not response_success:
        try:
            print(f"🔄 Updating message via stored response_url for user {user_id}")
            response = requests.post(
                stored_url,
                json={
                    "replace_original": True,  # Always force replace to fix the UI
                    "text": text,
                    "blocks": blocks
                },
                timeout=5  # Add a timeout to prevent hanging
            )
            
            if response.status_code == 200:
                print("✅ Successfully updated message via stored response_url")
                success = True
            else:
                print(f"❌ Failed to update via stored response_url: {response.status_code} {response.text}")
        except Exception as e:
            print(f"❌ Error using stored response_url: {str(e)}")
    
    # Method 3: Try using chat.update API
    if channel_id and message_ts and not success:
        try:
            print(f"🔄 Updating message via chat.update for user {user_id}")
            bot_client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=text,
                blocks=blocks
            )
            print("✅ Successfully updated message via chat.update")
            success = True
        except SlackApiError as e:
            print(f"❌ Error updating via chat.update: {e.response['error']}")
            
    # Return success status
    return success

def update_ephemeral_message(user_id, blocks, text="Message updated"):
    """Update an ephemeral message using response URL (legacy function, use update_slack_message instead)"""
    response_url = response_urls.get(user_id)
    if not response_url:
        print(f"❌ No response URL for user {user_id}")
        return False
        
    try:
        return update_slack_message(user_id, blocks, text, response_url=response_url)
    except Exception as e:
        print(f"❌ Error updating ephemeral message: {str(e)}")
        return False
        
def notify_admin_channel(user_id, selected_tracks, is_update=False):
    """Send a notification to the admin channel about track selection"""
    
    # Always skip sending notifications to the admin channel - just log them
    print(f"\n🔕 Admin notifications completely disabled:")
    print(f"   {'🔄 Track Update' if is_update else '✨ New Track Selection'} for user {user_id}")
    print(f"   Selected tracks: {', '.join(selected_tracks)}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return True
        
    # Code below this point is intentionally never reached as admin notifications are disabled
    # Keeping for reference only
    return True
    
    # This code is never executed - for reference only
    try:
        # Get user info
        user_info = bot_client.users_info(user=user_id)
        user_name = user_info["user"]["real_name"]
        user_image = user_info["user"]["profile"]["image_72"]
        
        # Prepare track emojis
        track_emojis = {
            "frontend": "🌐",
            "backend": "⚙️",
            "mobile": "📱",
            "uiux": "🎨",
            "pm": "📊",
            "devops": "🚀",
            "data-analysis": "📈",
            "qa": "🔍",
            "virtual-assistant": "🤖",
            "marketing": "📣",
            "video": "🎬"
        }
        
        # Format tracks with emojis
        formatted_tracks = []
        for track in selected_tracks:
            emoji = track_emojis.get(track, "📝")
            if track == "frontend":
                formatted_tracks.append(f"{emoji} Frontend Development")
            elif track == "backend":
                formatted_tracks.append(f"{emoji} Backend Development")
            elif track == "mobile":
                formatted_tracks.append(f"{emoji} Mobile Development")
            elif track == "uiux":
                formatted_tracks.append(f"{emoji} Product Design (UI/UX)")
            elif track == "pm":
                formatted_tracks.append(f"{emoji} Product Management")
            elif track == "devops":
                formatted_tracks.append(f"{emoji} DevOps")
            elif track == "data-analysis":
                formatted_tracks.append(f"{emoji} Data Analysis/Science")
            elif track == "qa":
                formatted_tracks.append(f"{emoji} Quality Assurance")
            elif track == "virtual-assistant":
                formatted_tracks.append(f"{emoji} Virtual Assistant")
            elif track == "marketing":
                formatted_tracks.append(f"{emoji} Marketing")
            elif track == "video":
                formatted_tracks.append(f"{emoji} Video Production")
            else:
                formatted_tracks.append(f"{emoji} {track}")
        
        # Create notification blocks
        notification_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{'🔄 *Track Update*' if is_update else '✨ *New Track Selection*'}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "image",
                        "image_url": user_image,
                        "alt_text": user_name
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*{user_name}* (<@{user_id}>) {' updated their' if is_update else ' selected'} tracks:"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join([f"• {track}" for track in formatted_tracks])
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_"
                    }
                ]
            }
        ]
        
        # Check for testing mode again (in case it changed during function execution)
        if TESTING_MODE:
            print(f"🧪 [TESTING MODE] Notification prepared but not sent")
            return True
            
        # Send to admin notification channel
        bot_client.chat_postMessage(
            channel=ADMIN_NOTIFICATION_CHANNEL,
            text=f"{'Track Update' if is_update else 'New Track Selection'} from {user_name}",
            blocks=notification_blocks
        )
        
        print(f"✅ Sent {'update' if is_update else 'new selection'} notification to admin channel")
        return True
    except Exception as e:
        print(f"❌ Error sending admin notification: {str(e)}")
        return False

# Available tracks
TRACKS = [
    "frontend",
    "backend",
    "mobile",
    "uiux",
    "pm",
    "devops",
    "data-analysis",
    "qa", 
    "virtual-assistant",
    "marketing",
    "video"
]

# In-memory storage for track selections
# This is temporary - in production, use a database
active_selections = {}

# Initialize user cache in a separate thread
def init_user_cache():
    user_cache.load_user_cache()
    if os.path.exists("all_users.json"):
        user_cache.preload_from_all_users("all_users.json")
    print("✅ User cache initialized")

# Start user cache initialization in background
threading.Thread(target=init_user_cache).start()

@app.post("/slack/mentor-track")
async def handle_mentor_track_command(request: Request):
    """Handle the /mentor-track Slack command"""
    # Verify request is from Slack (in production, implement proper signature verification)
    # if not verify_slack_signature(request):
    #     raise HTTPException(status_code=403, detail="Invalid request")
    
    try:
        # Parse request data
        form_data = await request.form()
        print(f"📝 Received slash command data: {dict(form_data)}")
        user_id = form_data.get("user_id")
        channel_id = form_data.get("channel_id")
        response_url = form_data.get("response_url")
        
        # Store the response URL for later use with ephemeral messages
        if user_id and response_url:
            response_urls[user_id] = response_url
            print(f"📝 Stored response URL for user {user_id}: {response_url[:30]}...")
    except Exception as e:
        print(f"❌ Error processing request: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
    
    # Create blocks for the message
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Please select the track(s) you would like to mentor:*"
            }
        },
        {
            "type": "divider"
        }
    ]
    
    # Add checkboxes for each track
    track_options = []
    for track in TRACKS:
        # Display a more user-friendly track name in the UI
        display_name = track
        if track == "frontend":
            display_name = "Frontend Development"
        elif track == "backend":
            display_name = "Backend Development"
        elif track == "mobile":
            display_name = "Mobile Development"
        elif track == "uiux":
            display_name = "Product Design (UI/UX)"
        elif track == "pm":
            display_name = "Product Management"
        elif track == "devops":
            display_name = "DevOps"
        elif track == "data-analysis":
            display_name = "Data Analysis/Science"
        elif track == "qa":
            display_name = "Quality Assurance"
        elif track == "virtual-assistant":
            display_name = "Virtual Assistant"
        elif track == "marketing":
            display_name = "Marketing"
        elif track == "video":
            display_name = "Video Production"
            
        track_options.append({
            "text": {
                "type": "plain_text",
                "text": display_name,
                "emoji": True
            },
            "value": track,
            "description": {
                "type": "plain_text",
                "text": f"Select to mentor in {display_name}",
                "emoji": True
            }
        })
    
    blocks.append({
        "type": "section",
        "block_id": "track_selection",
        "text": {
            "type": "mrkdwn",
            "text": "Select all tracks you're interested in mentoring:"
        },
        "accessory": {
            "type": "multi_static_select",
            "placeholder": {
                "type": "plain_text",
                "text": "Select tracks"
            },
            "action_id": "track_checkboxes",
            "options": track_options
        }
    })
    
    # Add submit button
    blocks.append({
        "type": "actions",
        "block_id": "track_submit",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Submit Selection"
                },
                "style": "primary",
                "action_id": "submit_tracks",
                "confirm": {
                    "title": {
                        "type": "plain_text",
                        "text": "Confirm Selection"
                    },
                    "text": {
                        "type": "plain_text",
                        "text": "This will save your track selection. Click 'Submit' to continue."
                    },
                    "confirm": {
                        "type": "plain_text",
                        "text": "Submit"
                    }
                }
            }
        ]
    })
    
    # Send ephemeral message with track selection UI
    try:
        # Print debug info
        print(f"💬 Attempting to send message to channel: {channel_id}, user: {user_id}")
        print(f"🤖 Bot token present: {'Yes' if BOT_TOKEN else 'No'}")
        
        # Debug the blocks structure
        import json
        print(f"📦 Block structure: {json.dumps(blocks, indent=2)}")
        
        # Try to get channel info first to debug
        try:
            channel_info = bot_client.conversations_info(channel=channel_id)
            print(f"✅ Channel info: {channel_info['channel']['name']}")
        except SlackApiError as channel_err:
            print(f"❌ Error getting channel info: {channel_err.response['error']}")
        
        # Send the ephemeral message
        bot_client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text="Select your preferred mentoring tracks",
            blocks=blocks
        )
        return Response()
    except SlackApiError as e:
        error_detail = e.response['error']
        print(f"❌ Error sending message: {error_detail}")
        
        # Get more details on the error
        if "response_metadata" in e.response and "messages" in e.response["response_metadata"]:
            print(f"📝 Error details: {e.response['response_metadata']['messages']}")
        
        # Return a helpful error message to Slack
        if error_detail == "channel_not_found":
            return JSONResponse(
                content={"text": "Error: I need to be invited to this channel. Please add the bot to this channel and try again."},
                status_code=200
            )
        else:
            raise HTTPException(status_code=500, detail=f"Failed to send message: {error_detail}")

@app.post("/slack/interactive")
async def handle_interactive_components(request: Request):
    """Handle interactive components like buttons and checkboxes"""
    # Verify request is from Slack (in production, implement proper signature verification)
    # if not verify_slack_signature(request):
    #     raise HTTPException(status_code=403, detail="Invalid request")
    
    try:
        # Parse just enough data to determine action type
        form_data = await request.form()
        raw_payload = form_data.get("payload", "{}")
        payload = json.loads(raw_payload)
        
        # Extract basic info
        action_id = None
        if "actions" in payload and len(payload["actions"]) > 0:
            action_id = payload["actions"][0].get("action_id")
        
        # Start background processing
        bg_thread = threading.Thread(
            target=process_interactive_payload_in_background,
            args=(raw_payload,),
            daemon=True
        )
        bg_thread.start()
        
        # For submit_tracks action, return a UI update immediately
        if action_id == "submit_tracks":
            # Return a response that updates the UI
            return JSONResponse(content={
                "response_type": "ephemeral",
                "replace_original": True,
                "text": "Processing your track selection...",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "⏳ *Processing your track selection...*"
                        }
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "Please wait while we save your selection..."
                            }
                        ]
                    }
                ]
            })
        
        # For all other actions, just acknowledge
        return JSONResponse(content={"text": ""})
    except Exception as e:
        print(f"❌ Error in interactive handler: {str(e)}")
        # Always return something to prevent Slack's error
        return JSONResponse(content={"text": ""})
    except Exception as e:
        print(f"❌ Error processing interactive request: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
    # If we're in the main route handler (not in background processing)
    action_id = payload.get("actions", [{}])[0].get("action_id")
    user_id = payload.get("user", {}).get("id")
    
    # Process based on action_id
    if action_id == "track_checkboxes":
        # Handle multi_static_select
        try:
            # Extract selected values from the multi-select
            if "actions" in payload and payload["actions"]:
                action = payload["actions"][0]
                if "selected_options" in action:
                    # For multi_static_select
                    selected_options = action.get("selected_options", [])
                    active_selections[user_id] = [option.get("value") for option in selected_options]
                elif "selected_option" in action:
                    # For single_static_select
                    active_selections[user_id] = [action.get("selected_option", {}).get("value")]
                print(f"✅ Updated selections for {user_id}: {active_selections[user_id]}")
            else:
                print("⚠️ No actions in payload")
        except Exception as e:
            print(f"❌ Error processing selections: {str(e)}")
            
        return JSONResponse(content={"response_type": "ephemeral", "text": ""})
        
    elif action_id == "submit_tracks_disabled":
        # Handle clicks on the disabled button
        print(f"ℹ️ User {user_id} clicked the disabled submit button - ignoring")
        
        # Send a message to the user to let them know submission is already in progress
        try:
            bot_client.chat_postEphemeral(
                channel=payload.get("channel", {}).get("id"),
                user=user_id,
                text="Your submission is already being processed. Please wait."
            )
        except Exception as e:
            print(f"❌ Error sending message: {str(e)}")
            
        return JSONResponse(content={"response_type": "ephemeral", "text": ""})
        
    elif action_id == "submit_tracks":
        # For submit_tracks action, we now handle it in the background thread
        # to ensure we respond to Slack immediately
        return handle_submit_tracks(payload)
    
    # Default return for any other actions
    return JSONResponse(content={"response_type": "ephemeral", "text": ""})

# This function processes interactive payloads completely in background
# to avoid any possibility of timeouts that cause Slack to show error messages
def process_interactive_payload_in_background(raw_payload):
    """Process interactive payloads in a background thread to avoid timeouts"""
    try:
        # Parse the payload
        payload = json.loads(raw_payload)
        
        # Log info
        print("📝 Processing interactive payload in background thread")
        print(f"📝 Payload type: {payload.get('type')}")
        print(f"📝 Full payload structure: {json.dumps(payload, indent=2)}")
        
        # Extract key information
        action_id = None
        if "actions" in payload and len(payload["actions"]) > 0:
            action_id = payload["actions"][0].get("action_id")
            
        # Process based on action_id
        if action_id == "track_checkboxes":
            # For track selection, update the stored selections
            user_id = payload.get("user", {}).get("id")
            try:
                # Extract selected values
                if "actions" in payload and payload["actions"]:
                    action = payload["actions"][0]
                    if "selected_options" in action:
                        selected_options = action.get("selected_options", [])
                        active_selections[user_id] = [option.get("value") for option in selected_options]
                        print(f"✅ Updated selections for {user_id}: {active_selections[user_id]}")
                    elif "selected_option" in action:
                        active_selections[user_id] = [action.get("selected_option", {}).get("value")]
                        print(f"✅ Updated selections for {user_id}: {active_selections[user_id]}")
            except Exception as e:
                print(f"❌ Error processing track selections: {str(e)}")
                
        elif action_id == "submit_tracks":
            # For track submission, process it
            # First update UI to show processing
            user_id = payload.get("user", {}).get("id")
            channel_id = payload.get("channel", {}).get("id")
            message_ts = payload.get("container", {}).get("message_ts")
            response_url = payload.get("response_url")
            
            # Update UI to show processing state
            processing_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⏳ *Processing your track selection...*"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Please wait while we save your selection..."
                        }
                    ]
                }
            ]
            
            # Try to update the UI first with processing message
            try:
                if response_url:
                    requests.post(
                        response_url,
                        json={
                            "replace_original": True,
                            "text": "Processing your track selection...",
                            "blocks": processing_blocks
                        },
                        timeout=2  # Short timeout to prevent hanging
                    )
            except Exception as e:
                print(f"❌ Error updating UI with processing message: {str(e)}")
                
            # Now process the actual selection
            try:
                # Process the selection using our handler
                handle_submit_tracks(payload)
            except Exception as e:
                print(f"❌ Error processing track submission: {str(e)}")
                
    except Exception as e:
        print(f"❌ Error in background processing: {str(e)}")

# Function to handle all interactive payloads in background thread
def handle_interactive_payload(payload):
    """Process interactive payloads after sending acknowledgment"""
    action_id = payload.get("actions", [{}])[0].get("action_id")
    user_id = payload.get("user", {}).get("id")
    
    if action_id == "track_checkboxes":
        # Handle multi_static_select
        try:
            # Extract selected values from the multi-select
            if "actions" in payload and payload["actions"]:
                action = payload["actions"][0]
                if "selected_options" in action:
                    # For multi_static_select
                    selected_options = action.get("selected_options", [])
                    active_selections[user_id] = [option.get("value") for option in selected_options]
                elif "selected_option" in action:
                    # For single_static_select
                    active_selections[user_id] = [action.get("selected_option", {}).get("value")]
                print(f"✅ Updated selections for {user_id}: {active_selections[user_id]}")
            else:
                print("⚠️ No actions in payload")
        except Exception as e:
            print(f"❌ Error processing selections: {str(e)}")
            
    elif action_id == "submit_tracks_disabled":
        # Handle clicks on the disabled button
        print(f"ℹ️ User {user_id} clicked the disabled submit button - ignoring")
        
        # Send a message to the user to let them know submission is already in progress
        try:
            bot_client.chat_postEphemeral(
                channel=payload.get("channel", {}).get("id"),
                user=user_id,
                text="Your submission is already being processed. Please wait."
            )
        except Exception as e:
            print(f"❌ Error sending message: {str(e)}")
            
    elif action_id == "submit_tracks":
        handle_submit_tracks(payload)

# Handle the submit_tracks action
def handle_submit_tracks(payload):
    """Handle track submission - can be called directly or from background thread"""
    user_id = payload.get("user", {}).get("id")
    channel_id = payload.get("channel", {}).get("id")
    message_ts = payload.get("container", {}).get("message_ts")
    response_url = payload.get("response_url")
    
    print(f"🔄 Handle submit tracks for user {user_id}")
    print(f"🔄 Channel: {channel_id}, message_ts: {message_ts}")
    print(f"🔄 Response URL available: {bool(response_url)}")
    
    # Process the submission
    # Always get selected tracks from the payload state, which is more reliable
    selected_track_values = []
    
    print("🔍 Looking for track selections in payload")
    try:
        # Get selected values directly from the payload
        if "state" in payload and "values" in payload["state"]:
            for block_id, block_values in payload["state"]["values"].items():
                for action_id, action_data in block_values.items():
                    if "selected_options" in action_data:
                        selected_track_values = [option["value"] for option in action_data["selected_options"]]
                        print(f"✅ Found {len(selected_track_values)} tracks in payload state: {selected_track_values}")
    except Exception as e:
        print(f"❌ Error extracting tracks from payload: {str(e)}")
        
    # Fall back to active_selections if needed
    if not selected_track_values:
        selected_track_values = active_selections.get(user_id, [])
        print(f"ℹ️ Using tracks from active_selections: {selected_track_values}")
    
    # Values are now directly the track IDs from TRACKS
    selected_tracks = selected_track_values
    
    if not selected_tracks:
        # No tracks selected - show an error message but keep the original UI
        try:
            bot_client.chat_postEphemeral(
                channel=payload.get("channel", {}).get("id"),
                user=user_id,
                text="⚠️ Please select at least one track before submitting."
            )
            
            # Also highlight the error in the blocks
            message_ts = payload.get("container", {}).get("message_ts")
            channel_id = payload.get("channel", {}).get("id")
            
            if message_ts and channel_id:
                # Get the current blocks
                original_message = bot_client.conversations_history(
                    channel=channel_id,
                    latest=message_ts,
                    inclusive=True,
                    limit=1
                )
                
                if original_message and original_message.get("messages"):
                    # Update the message to highlight the error
                    error_blocks = original_message["messages"][0].get("blocks", [])
                    
                    # Insert an error message
                    error_blocks.insert(1, {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "⚠️ *Please select at least one track before submitting.*"
                        }
                    })
                    
                    # Update the message
                    bot_client.chat_update(
                        channel=channel_id,
                        ts=message_ts,
                        blocks=error_blocks
                    )
        except SlackApiError as e:
            print(f"❌ Error updating message with error: {e.response['error']}")
            
        return JSONResponse(content={"response_type": "ephemeral", "text": ""})
    
    # The important part - actually call process_track_selection with the tracks    
    print(f"🔄 Calling process_track_selection with tracks: {selected_tracks}")
    process_track_selection(
        user_id=user_id,
        selected_tracks=selected_tracks,
        channel_id=channel_id,
        message_ts=message_ts,
        response_url=response_url
    )
    
    # Return for direct calls
    return JSONResponse(content={"response_type": "ephemeral", "text": ""})
        
# Unused legacy code below - keeping for reference
def legacy_handle_submit_tracks(payload):
    """Legacy code for handling track submission"""
    # First, immediately update the UI to show processing and disable the button
    # Create human-readable track names for display
    readable_tracks = []
    selected_tracks = []  # This needs to be defined based on payload
    
    for track in selected_tracks:
        if track == "frontend":
            readable_tracks.append("Frontend Development")
        elif track == "backend":
            readable_tracks.append("Backend Development")
        elif track == "mobile":
            readable_tracks.append("Mobile Development")
        elif track == "uiux":
            readable_tracks.append("Product Design (UI/UX)")
        elif track == "pm":
            readable_tracks.append("Product Management")
        elif track == "devops":
            readable_tracks.append("DevOps")
        elif track == "data-analysis":
            readable_tracks.append("Data Analysis/Science")
        elif track == "qa":
            readable_tracks.append("Quality Assurance")
        elif track == "virtual-assistant":
            readable_tracks.append("Virtual Assistant")
        elif track == "marketing":
            readable_tracks.append("Marketing")
        elif track == "video":
            readable_tracks.append("Video Production")
        else:
            readable_tracks.append(track)
        
        # Get user_id from payload
        user_id = payload.get("user", {}).get("id")
        
        # Update to processing state with disabled button
        # Using a simpler UI to minimize issues with button state
        processing_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⏳ *Processing your track selection...*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"You selected: *{', '.join(readable_tracks)}*"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Please wait while we save your selection..."
                    }
                ]
            }
        ]
        
        # Get message info
        message_ts = payload.get("container", {}).get("message_ts")
        channel_id = payload.get("channel", {}).get("id")
        response_url = response_urls.get(user_id)
        
        # Try to update the message using our unified helper function
        updated = update_slack_message(
            user_id,
            processing_blocks,
            "Processing your track selection...",
            channel_id,
            message_ts,
            response_url
        )
        
        # Ensure we have the user_id (should already be set above, but being extra careful)
        user_id = payload.get("user", {}).get("id")
        
        # If all methods failed, post a new ephemeral message
        if not updated:
            try:
                if channel_id:
                    bot_client.chat_postEphemeral(
                        channel=channel_id,
                        user=user_id,
                        text="Processing your track selection...",
                        blocks=processing_blocks
                    )
            except SlackApiError as e:
                print(f"❌ Error sending processing message: {e.response['error']}")
        
        # Store the response URL for this user
        response_url = payload.get("response_url")
        if response_url:
            # Store in global dict and make it easily accessible
            response_urls[user_id] = response_url
            print(f"📝 Storing response URL for user {user_id} before processing: {response_url[:30]}...")
        
        # Get important information for processing
        channel_id = payload.get("channel", {}).get("id")
        message_ts = payload.get("container", {}).get("message_ts")
        
        # For debugging: log all available info
        print(f"📊 Processing submission with context: user_id={user_id}, channel_id={channel_id}, message_ts={message_ts}")
        print(f"📊 Response URL available: {bool(response_url)}")
        
        # Process the track selection
        thread = threading.Thread(
            target=process_track_selection,
            args=(
                user_id, 
                selected_tracks, 
                channel_id, 
                message_ts,
                response_url
            )
        )
        thread.daemon = True  # Make thread daemonized so it doesn't block shutdown
        thread.start()
        
        # Return immediate response - ALWAYS return a 200 OK to prevent Slack's error message
        return JSONResponse(content={"response_type": "ephemeral", "text": ""})
    
    # Always return a 200 OK for any interactive endpoint to prevent Slack's error message
    return JSONResponse(content={"response_type": "ephemeral", "text": ""})

def force_update_ui(user_id, blocks, text, channel_id=None, message_ts=None, response_url=None):
    """Force an update to the UI using multiple methods to ensure it goes through"""
    print(f"🔄 FORCE UPDATE UI for user {user_id}")
    
    # Try multiple methods to ensure the message gets updated
    updated = False
    
    # Method 1: Try direct response URL update
    if response_url:
        try:
            print(f"🔄 [FORCE] Updating via direct response URL")
            response = requests.post(
                response_url,
                json={
                    "replace_original": True,
                    "text": text,
                    "blocks": blocks
                },
                timeout=5
            )
            if response.status_code == 200:
                updated = True
                print(f"✅ [FORCE] Successfully updated via direct response URL")
            else:
                print(f"❌ [FORCE] Failed via direct response URL: {response.status_code}")
        except Exception as e:
            print(f"❌ [FORCE] Error using direct response URL: {str(e)}")
    
    # Method 2: Try stored response URL
    stored_url = response_urls.get(user_id)
    if stored_url and not updated and stored_url != response_url:
        try:
            print(f"🔄 [FORCE] Updating via stored response URL")
            response = requests.post(
                stored_url,
                json={
                    "replace_original": True,
                    "text": text,
                    "blocks": blocks
                },
                timeout=5
            )
            if response.status_code == 200:
                updated = True
                print(f"✅ [FORCE] Successfully updated via stored response URL")
            else:
                print(f"❌ [FORCE] Failed via stored response URL: {response.status_code}")
        except Exception as e:
            print(f"❌ [FORCE] Error using stored response URL: {str(e)}")
    
    # Method 3: Try using chat.update API
    if channel_id and message_ts and not updated:
        try:
            print(f"🔄 [FORCE] Updating via chat.update API")
            bot_client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=text,
                blocks=blocks
            )
            updated = True
            print(f"✅ [FORCE] Successfully updated via chat.update API")
        except SlackApiError as e:
            print(f"❌ [FORCE] Error updating via chat.update: {e.response['error']}")
    
    # Method 4: Last resort - post a new message
    if not updated:
        try:
            print(f"🔄 [FORCE] Posting new ephemeral message as last resort")
            bot_client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=text,
                blocks=blocks
            )
            print(f"✅ [FORCE] Posted new ephemeral message")
        except Exception as e:
            print(f"❌ [FORCE] Failed to post new message: {str(e)}")
    
    return updated

def process_track_selection(user_id, selected_tracks, channel_id, message_ts=None, response_url=None):
    """Process the track selection and save to Google Sheets"""
    try:
        # Store the response URL for this user to ensure we can update later
        if response_url and user_id:
            response_urls[user_id] = response_url
            print(f"📝 Updated response URL for user {user_id} in process_track_selection")
        
        # Import here to avoid circular imports
        from mentor_track_cli import save_track_selection
        
        if TESTING_MODE:
            print(f"\n🧪 [TESTING MODE] Processing track selection in testing mode")
            print(f"🧪 [TESTING MODE] Notifications and DMs will be logged but not sent")
            
        print(f"💾 Saving track selection for user {user_id}: {selected_tracks}")
        
        # Save the selection
        success = save_track_selection(user_id, selected_tracks)
        
        if success:
            # Get human-readable track names for display
            readable_tracks = []
            for track in selected_tracks:
                if track == "frontend":
                    readable_tracks.append("Frontend Development")
                elif track == "backend":
                    readable_tracks.append("Backend Development")
                elif track == "mobile":
                    readable_tracks.append("Mobile Development")
                elif track == "uiux":
                    readable_tracks.append("Product Design (UI/UX)")
                elif track == "pm":
                    readable_tracks.append("Product Management")
                elif track == "devops":
                    readable_tracks.append("DevOps")
                elif track == "data-analysis":
                    readable_tracks.append("Data Analysis/Science")
                elif track == "qa":
                    readable_tracks.append("Quality Assurance")
                elif track == "virtual-assistant":
                    readable_tracks.append("Virtual Assistant")
                elif track == "marketing":
                    readable_tracks.append("Marketing")
                elif track == "video":
                    readable_tracks.append("Video Production")
                else:
                    readable_tracks.append(track)
            
            # Update the message with confirmation and completely remove the button
            updated_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ *Track selection saved successfully!*"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"You've selected: *{', '.join(readable_tracks)}*"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "✨ *Your selection has been recorded.* To change your selection, use the `/mentor-track` command again."
                        }
                    ]
                }
            ]
            
            # Add debug output to see what messages we're trying to update
            print(f"🔄 Attempting to update message with success confirmation for user {user_id}")
            print(f"🔄 Message info: channel={channel_id}, ts={message_ts}, response_url available: {bool(response_url)}")
            
            # Use our force update function to ensure the UI gets updated
            force_update_ui(
                user_id,
                updated_blocks,
                "✅ Track selection saved successfully!",
                channel_id,
                message_ts,
                response_url
            )
            
            # Delay a bit and try to update again to be extra sure (helps with race conditions)
            time.sleep(0.5)
            try:
                # Try our regular update method as a backup
                update_slack_message(
                    user_id,
                    updated_blocks,
                    "✅ Track selection saved successfully!",
                    channel_id,
                    message_ts,
                    response_url,
                    replace_original=True
                )
            except Exception as e:
                # Silently ignore errors from the backup attempt
                print(f"ℹ️ Backup update attempt: {str(e)}")
            
            # Notify admin channel about the track selection
            # Check if this is an update or new selection by examining the spreadsheet
            is_update = False  # We'll assume it's new for now
            try:
                from mentor_track_cli import check_if_mentor_exists
                is_update = check_if_mentor_exists(user_id)
            except Exception as e:
                print(f"⚠️ Could not determine if this is an update: {str(e)}")
                
            # This notification function now only logs the selection and returns immediately
            # No messages will be sent to the bot-automation channel
            notify_admin_channel(user_id, selected_tracks, is_update)
            
            # Create human-readable track names for the confirmation
            readable_tracks = []
            for track in selected_tracks:
                if track == "frontend":
                    readable_tracks.append("Frontend Development")
                elif track == "backend":
                    readable_tracks.append("Backend Development")
                elif track == "mobile":
                    readable_tracks.append("Mobile Development")
                elif track == "uiux":
                    readable_tracks.append("Product Design (UI/UX)")
                elif track == "pm":
                    readable_tracks.append("Product Management")
                elif track == "devops":
                    readable_tracks.append("DevOps")
                elif track == "data-analysis":
                    readable_tracks.append("Data Analysis/Science")
                elif track == "qa":
                    readable_tracks.append("Quality Assurance")
                elif track == "virtual-assistant":
                    readable_tracks.append("Virtual Assistant")
                elif track == "marketing":
                    readable_tracks.append("Marketing")
                elif track == "video":
                    readable_tracks.append("Video Production")
                else:
                    readable_tracks.append(track)
                    
            confirmation_message = (
                f"✅ Your track selection has been recorded.\n\n"
                f"*Selected Tracks*: {', '.join(readable_tracks)}\n\n"
                f"You will be added to all stage channels for these tracks going forward. Thank you for mentoring with HNG!"
            )
            
            try:
                # Always send a DM with confirmation (even if admin notifications are disabled)
                # Only skip in testing mode
                if TESTING_MODE:
                    print(f"🧪 [TESTING MODE] Would have sent DM with message: \n{confirmation_message[:100]}...")
                else:
                    # Open a DM channel with the user
                    print(f"📲 Opening DM with user {user_id} to send confirmation")
                    dm = bot_client.conversations_open(users=user_id)
                    dm_channel_id = dm["channel"]["id"]
                    
                    # Send the message
                    print(f"📨 Sending confirmation message to user {user_id} via DM")
                    bot_client.chat_postMessage(
                        channel=dm_channel_id,
                        text=confirmation_message
                    )
                    print(f"✅ Successfully sent DM to user {user_id}")
            except Exception as e:
                print(f"❌ Error sending DM to user {user_id}: {str(e)}")
        else:
            # Update UI to show error
            error_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "❌ *There was an error saving your track selection.*"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "Please try again or contact an administrator for assistance."
                        }
                    ]
                }
            ]
            
            # Try to update the message
            updated = update_slack_message(
                user_id,
                error_blocks,
                "❌ Error saving track selection",
                channel_id,
                message_ts,
                response_url,
                replace_original=True
            )
            
            # If update failed, send as new message
            if not updated:
                try:
                    bot_client.chat_postEphemeral(
                        channel=channel_id,
                        user=user_id,
                        text="❌ There was an error saving your track selection. Please try again or contact an administrator."
                    )
                except SlackApiError:
                    pass
    except Exception as e:
        print(f"Error processing track selection: {str(e)}")
        
        # Create error blocks
        error_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "❌ *An unexpected error occurred.*"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Please try again later or contact an administrator."
                    }
                ]
            }
        ]
        
        # Try to update the message
        try:
            update_slack_message(
                user_id,
                error_blocks,
                "❌ Error occurred",
                channel_id,
                message_ts,
                response_url,
                replace_original=True
            )
        except Exception as update_error:
            print(f"Failed to update message with error: {str(update_error)}")
            
            # Last resort: try to send a new ephemeral message
            try:
                bot_client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text="❌ An unexpected error occurred. Please try again later."
                )
            except:
                pass

async def verify_slack_signature(request: Request):
    """Verify that the request is coming from Slack"""
    if not SLACK_SIGNING_SECRET:
        print("⚠️ No signing secret found, skipping signature verification")
        return True
        
    # In a production environment, implement proper signature verification
    # using Slack's signing secret and the request headers
    verifier = SignatureVerifier(SLACK_SIGNING_SECRET)
    
    # Get request headers and body
    headers = request.headers
    body = await request.body()
    
    # Check timestamp to prevent replay attacks
    timestamp = headers.get("X-Slack-Request-Timestamp", "0")
    if abs(time.time() - int(timestamp)) > 60 * 5:
        # The request timestamp is more than five minutes old
        return False
        
    # Get signature from headers
    signature = headers.get("X-Slack-Signature", "")
    
    # Verify the request
    return verifier.is_valid(
        body=body.decode("utf-8") if hasattr(body, "decode") else body,
        timestamp=timestamp,
        signature=signature
    )

if __name__ == "__main__":
    # Print configuration
    print(f"Bot Token present: {'Yes' if BOT_TOKEN else 'No'}")
    print(f"Signing Secret present: {'Yes' if SLACK_SIGNING_SECRET else 'No'}")
    
    import uvicorn
    import time
    
    port = int(os.environ.get("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)