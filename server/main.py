#!/usr/bin/env python3
"""
Mentor Track Slack Command Handler

This script handles the /mentor-track Slack command to allow mentors
to select their preferred tracks directly from Slack.

Production-ready server with proper logging, security, and error handling.
"""

import logging
import os
import sys
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
        
        logger.info(f"Received /mentor-track from user {user_id} in channel {channel_id}")
        logger.debug(f"DEBUG: Allowed channels = {[MENTORS_CHANNEL_ID, MENTOR_RANDOM_CHANNEL_ID]}, Got channel_id = '{channel_id}'")
        
        # ✅ CHANNEL RESTRICTION: Only allow command in mentors and mentors-random channels
        allowed_channels = [MENTORS_CHANNEL_ID, MENTOR_RANDOM_CHANNEL_ID]
        if channel_id not in allowed_channels:
            error_message = f"""❌ The `/mentor-track` command can only be used in:
• <#{MENTORS_CHANNEL_ID}> (mentors)
• <#{MENTOR_RANDOM_CHANNEL_ID}> (mentors-random)

Please use the command in one of these channels."""
            logger.warning(f"⚠️  User {user_id} tried /mentor-track in restricted channel {channel_id}")
            return JSONResponse(content={"text": error_message}, status_code=200)
        
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
    response_url = payload.get("response_url", "")
    
    # Store response URL for this interaction
    if response_url:
        response_urls[user_id] = response_url
    
    try:
        if action_id == "track_checkboxes":
            actions = payload.get("actions", [])
            if actions:
                selected = [o.get("value") for o in actions[0].get("selected_options", [])]
                active_selections[user_id] = selected
                logger.info(f"User {user_id} selected: {selected}")
        
        elif action_id == "submit_tracks":
            _process_submission(user_id, payload)
        
        elif action_id == "confirm_update_add":
            _handle_update_confirmation(user_id, "add", response_url)
        
        elif action_id == "confirm_update_replace":
            _handle_update_confirmation(user_id, "replace", response_url)
    
    except Exception as e:
        logger.error(f"Error processing action: {e}")


def _handle_update_confirmation(user_id: str, action_type: str, response_url: str = "") -> None:
    """Handle the confirmation of track update (add or replace)"""
    try:
        # Get pending update data
        if not hasattr(_process_submission, 'pending_updates'):
            logger.warning(f"No pending update found for {user_id}")
            return
        
        pending = _process_submission.pending_updates.get(user_id)
        if not pending:
            logger.warning(f"No pending update found for {user_id}")
            return
        
        new_tracks = pending['new_tracks']
        existing_tracks = pending['existing_tracks']
        payload = pending['payload']
        
        # Use button click response_url if available, otherwise use stored one
        if not response_url:
            response_url = payload.get("response_url", "")
        
        try:
            from server.mentor_track_cli import save_track_selection, get_mentor_existing_tracks
        except ImportError:
            from mentor_track_cli import save_track_selection, get_mentor_existing_tracks
        
        if action_type == "add":
            # Merge tracks: add new ones to existing
            combined_tracks = list(set(existing_tracks + new_tracks))
            combined_tracks.sort()
            logger.info(f"Update ADD: {user_id} will have tracks {combined_tracks}")
            final_tracks = combined_tracks
            # Only sync NEW tracks (ones not already in existing)
            tracks_to_sync = list(set(new_tracks) - set(existing_tracks))
            sync_mode = "update"  # For ADD: only sync new tracks
        else:  # replace
            # Use only new tracks
            logger.info(f"Update REPLACE: {user_id} will have tracks {new_tracks}")
            final_tracks = new_tracks
            # Sync all tracks for replace (they're completely changing tracks)
            tracks_to_sync = final_tracks
            sync_mode = "new"  # For REPLACE: treat like new submission
        
        # Save tracks
        if save_track_selection(user_id, final_tracks):
            readable = [track_id_to_display_name(t) for t in final_tracks]
            action_msg = "added to" if action_type == "add" else "changed to"
            
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": "✅ *Track selection updated!*"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"Your tracks have been {action_msg}: *{', '.join(readable)}*"}}
            ]
            
            # Update the confirmation dialog with the success message
            if response_url:
                try:
                    requests.post(response_url, json={
                        "replace_original": True,
                        "text": "✅ Track selection updated",
                        "blocks": blocks
                    }, timeout=API_REQUEST_TIMEOUT)
                except Exception as e:
                    logger.error(f"Error updating confirmation dialog: {e}")
            
            # Send DM
            try:
                if not TESTING_MODE:
                    dm = bot_client.conversations_open(users=user_id)
                    if action_type == "add":
                        tracks_to_sync_readable = [track_id_to_display_name(t) for t in tracks_to_sync]
                        if tracks_to_sync:
                            message = f"""✅ Your track selection has been updated (tracks added).

New tracks added: {', '.join(tracks_to_sync_readable)}
All your tracks: {', '.join(readable)}

🚀 You will be added to all stage channels for the new track(s)! Thank you for mentoring with HNG!"""
                        else:
                            message = f"""✅ Your track selection was already complete.

Your tracks: {', '.join(readable)}

Thank you for mentoring with HNG!"""
                    else:
                        message = f"""✅ Your track selection has been changed.

Selected Tracks: {', '.join(readable)}

🚀 You will be added to all stage channels for these tracks! Thank you for mentoring with HNG!"""
                    
                    bot_client.chat_postMessage(channel=dm["channel"]["id"], text=message)
            except Exception as e:
                logger.error(f"DM error: {e}")
            
            # 🚀 INSTANT MENTOR SYNC
            # For ADD: only sync new tracks (mentor already in existing channels) - use direct API
            # For REPLACE: sync all tracks using script approach like new submission
            logger.info(f"🚀 Triggering instant mentor sync for {user_id} with tracks: {tracks_to_sync} (mode: {sync_mode})")
            if tracks_to_sync:
                _trigger_instant_mentor_sync(user_id, tracks_to_sync, sync_mode=sync_mode)
            else:
                logger.info(f"No tracks to sync for {user_id}")
            
            # Notify admin
            notify_admin_channel(user_id, final_tracks, is_update=True)
        
        # Clean up pending update
        del _process_submission.pending_updates[user_id]
    
    except Exception as e:
        logger.error(f"Error handling update confirmation: {e}")



def _trigger_instant_mentor_sync(user_id: str, selected_tracks: List[str], sync_mode: str = "new") -> None:
    """
    Trigger instant mentor sync to track channels.
    
    Args:
        user_id: Slack user ID
        selected_tracks: List of tracks to sync to
        sync_mode: "new" for initial submission (sync to ALL tracks), 
                   "update" for adding new tracks only
    
    This runs in a background thread and adds the mentor immediately.
    """
    def _sync():
        try:
            import json
            from pathlib import Path
            
            # Get scheduler state to find current stage
            scheduler_state_file = Path(__file__).parent.parent / "scripts" / ".scheduler_state.json"
            current_stage = 0
            
            if scheduler_state_file.exists():
                try:
                    with open(scheduler_state_file, 'r') as f:
                        state = json.load(f)
                        current_stage = state.get("last_stage_number", 0)
                except Exception as e:
                    logger.warning(f"Could not read scheduler state: {e}")
            
            if current_stage == 0:
                logger.warning("No stages created yet, skipping instant mentor sync")
                return
            
            logger.info(f"🚀 Syncing mentor {user_id} ({sync_mode} mode) to {selected_tracks} channels...")
            
            # For NEW submissions: use the reliable script-based approach
            # For UPDATES: use direct API to only sync new tracks
            if sync_mode == "new":
                # New mentor - use script to add to all their selected tracks
                import subprocess
                scripts_dir = Path(__file__).parent.parent / "scripts"
                for stage_num in range(1, current_stage + 1):
                    try:
                        logger.info(f"  → Running mentor sync script for stage-{stage_num}...")
                        result = subprocess.run(
                            [sys.executable, "add_mentors_to_existing_stage.py", str(stage_num), "--since-minutes", "1"],
                            cwd=scripts_dir,
                            capture_output=True,
                            timeout=60
                        )
                        if result.returncode == 0:
                            logger.info(f"  ✅ Mentor synced to stage-{stage_num}")
                        else:
                            logger.error(f"  ❌ Script failed for stage-{stage_num}: {result.stderr.decode()}")
                    except Exception as e:
                        logger.error(f"  ❌ Error running script for stage-{stage_num}: {e}")
            
            else:  # update mode
                # Updating mentor - use direct API to add to BOTH general stage AND new track channels
                successful_adds = 0
                failed_adds = []
                
                for stage_num in range(1, current_stage + 1):
                    # First, add to the general stage channel (stage-1, stage-2, etc.)
                    general_channel_name = f"stage-{stage_num}"
                    try:
                        logger.info(f"  → Adding {user_id} to #{general_channel_name}...")
                        response = bot_client.conversations_list(limit=1000, exclude_archived=True)
                        channel_id = None
                        
                        for ch in response.get('channels', []):
                            if ch['name'] == general_channel_name:
                                channel_id = ch['id']
                                break
                        
                        if channel_id:
                            try:
                                bot_client.conversations_invite(channel=channel_id, users=[user_id])
                                logger.info(f"  ✅ {user_id} added to #{general_channel_name}")
                                successful_adds += 1
                            except SlackApiError as e:
                                error_code = e.response.get('error', '')
                                if 'already_in_channel' in error_code:
                                    logger.info(f"  ℹ️  {user_id} already in #{general_channel_name}")
                                    successful_adds += 1
                                else:
                                    logger.warning(f"  ⚠️  Could not add {user_id} to #{general_channel_name}: {error_code}")
                                    failed_adds.append((general_channel_name, error_code))
                        else:
                            logger.warning(f"  ❌ Channel #{general_channel_name} not found")
                            failed_adds.append((general_channel_name, "not found"))
                    
                    except Exception as e:
                        logger.error(f"  ❌ Error adding to general stage {stage_num}: {e}")
                        failed_adds.append((general_channel_name, str(e)))
                    
                    # Then, add to track-specific channels
                    for track in selected_tracks:
                        try:
                            channel_name = f"stage-{stage_num}-{track}"
                            logger.info(f"  → Adding {user_id} to #{channel_name}...")
                            
                            # Find channel by name
                            response = bot_client.conversations_list(limit=1000, exclude_archived=True)
                            channel_id = None
                            
                            for ch in response.get('channels', []):
                                if ch['name'] == channel_name:
                                    channel_id = ch['id']
                                    break
                            
                            if not channel_id:
                                logger.warning(f"  ❌ Channel #{channel_name} not found")
                                failed_adds.append((channel_name, "not found"))
                                continue
                            
                            # Invite mentor
                            try:
                                bot_client.conversations_invite(channel=channel_id, users=[user_id])
                                logger.info(f"  ✅ {user_id} added to #{channel_name}")
                                successful_adds += 1
                            except SlackApiError as e:
                                error_code = e.response.get('error', '')
                                if 'already_in_channel' in error_code:
                                    logger.info(f"  ℹ️  {user_id} already in #{channel_name}")
                                    successful_adds += 1
                                else:
                                    logger.warning(f"  ⚠️  Could not add {user_id} to #{channel_name}: {error_code}")
                                    failed_adds.append((channel_name, error_code))
                        
                        except Exception as e:
                            logger.error(f"  ❌ Error processing {track}: {e}")
                            failed_adds.append((track, str(e)))
                
                if successful_adds > 0:
                    logger.info(f"✅ Added {user_id} to {successful_adds} channels")
                if failed_adds:
                    logger.warning(f"⚠️  Failed on {len(failed_adds)} channels: {failed_adds}")
                    
        except Exception as e:
            logger.error(f"Error in instant mentor sync: {e}", exc_info=True)
    
    # Run sync in background thread
    sync_thread = threading.Thread(target=_sync, daemon=True)
    sync_thread.start()
    logger.info(f"🚀 Instant mentor sync ({sync_mode}) triggered for {user_id} - tracks: {selected_tracks}")


def _process_submission(user_id: str, payload: Dict[str, Any]) -> None:
    """Process track submission - checks if mentor exists and shows confirmation if needed"""
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
        
        logger.info(f"Processing submission for {user_id}: {tracks}")
        
        # Import functions
        try:
            from server.mentor_track_cli import save_track_selection, check_if_mentor_exists, get_mentor_existing_tracks
        except ImportError:
            from mentor_track_cli import save_track_selection, check_if_mentor_exists, get_mentor_existing_tracks
        
        # Check if mentor already exists
        if check_if_mentor_exists(user_id):
            existing_tracks = get_mentor_existing_tracks(user_id)
            logger.info(f"Mentor {user_id} already exists with tracks: {existing_tracks}")
            
            # Store in a temporary dict so we can reference it in confirmation handlers
            if not hasattr(_process_submission, 'pending_updates'):
                _process_submission.pending_updates = {}
            _process_submission.pending_updates[user_id] = {
                'new_tracks': tracks,
                'existing_tracks': existing_tracks,
                'payload': payload
            }
            
            # Show confirmation dialog
            _show_update_confirmation_dialog(user_id, existing_tracks, tracks, payload)
        else:
            # New mentor - save directly
            _save_tracks_and_notify(user_id, tracks, payload, is_update=False)
    
    except Exception as e:
        logger.error(f"Submission error: {e}")


def _show_update_confirmation_dialog(user_id: str, existing_tracks: List[str], new_tracks: List[str], payload: Dict[str, Any]) -> None:
    """Show a confirmation dialog for updating vs replacing tracks"""
    try:
        response_url = payload.get("response_url", "")
        channel_id = payload.get("channel", {}).get("id")
        
        existing_readable = [track_id_to_display_name(t) for t in existing_tracks]
        new_readable = [track_id_to_display_name(t) for t in new_tracks]
        
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": "🔄 *You've already submitted tracks before!*"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Your current tracks:*\n{', '.join(existing_readable)}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*New selection:*\n{', '.join(new_readable)}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "_What would you like to do?_"}},
            {"type": "actions", "block_id": "update_confirmation", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Update (Add new tracks)"},
                 "value": "update_add", "action_id": "confirm_update_add",
                 "style": "primary"},
                {"type": "button", "text": {"type": "plain_text", "text": "Replace (Use only new selection)"},
                 "value": "update_replace", "action_id": "confirm_update_replace",
                 "style": "danger"}
            ]}
        ]
        
        # Update the original form message with the confirmation dialog
        if response_url:
            try:
                requests.post(response_url, json={
                    "replace_original": True,
                    "text": "Track update confirmation",
                    "blocks": blocks
                }, timeout=API_REQUEST_TIMEOUT)
                logger.info(f"Sent update confirmation dialog to {user_id}")
            except Exception as e:
                logger.error(f"Error posting confirmation via response_url: {e}")
                # Fallback to ephemeral message if response_url fails
                bot_client.chat_postEphemeral(channel=channel_id, user=user_id, text="Track update confirmation", blocks=blocks)
        else:
            # No response_url, fall back to ephemeral
            bot_client.chat_postEphemeral(channel=channel_id, user=user_id, text="Track update confirmation", blocks=blocks)
            logger.info(f"Sent update confirmation dialog to {user_id} (ephemeral fallback)")
    
    except Exception as e:
        logger.error(f"Error showing confirmation dialog: {e}")


def _save_tracks_and_notify(user_id: str, tracks: List[str], payload: Dict[str, Any], is_update: bool = False) -> None:
    """Save tracks and send notifications"""
    try:
        from server.mentor_track_cli import save_track_selection
    except ImportError:
        from mentor_track_cli import save_track_selection
    
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
                action_text = "updated" if is_update else "recorded"
                message = f"""✅ Your track selection has been {action_text}.

Selected Tracks: {', '.join(readable)}

🚀 You will be added to all stage channels for these tracks right now! Thank you for mentoring with HNG!"""
                bot_client.chat_postMessage(channel=dm["channel"]["id"], text=message)
        except Exception as e:
            logger.error(f"DM error: {e}")
        
        # 🚀 INSTANT MENTOR SYNC
        logger.info(f"🚀 Triggering instant mentor sync for {user_id} with tracks: {tracks}")
        _trigger_instant_mentor_sync(user_id, tracks, sync_mode="new")
        
        # Notify admin
        notify_admin_channel(user_id, tracks, is_update)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
