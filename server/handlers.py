"""
Slack Interactive Handlers for Mentor Track Selection

Handles incoming Slack interactive components (buttons, selections, etc)
and routes them to appropriate processing functions.
"""

import json
import threading
import time
from typing import Dict, Any, Optional
from fastapi.responses import JSONResponse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# These will be injected when imported
bot_client: Optional[WebClient] = None
response_urls: Dict[str, str] = {}
active_selections: Dict[str, list] = {}


def set_client(client: WebClient):
    """Set the bot client for this module."""
    global bot_client
    bot_client = client


def set_response_urls(urls_dict: Dict[str, str]):
    """Set the response URLs dictionary."""
    global response_urls
    response_urls = urls_dict


def set_active_selections(selections_dict: Dict[str, list]):
    """Set the active selections dictionary."""
    global active_selections
    active_selections = selections_dict


def handle_track_selection(payload: Dict[str, Any]) -> None:
    """
    Handle track checkbox selection (track_checkboxes action).
    
    Stores the user's current selection in active_selections.
    """
    user_id = payload.get("user", {}).get("id")
    
    try:
        if "actions" in payload and payload["actions"]:
            action = payload["actions"][0]
            
            if "selected_options" in action:
                # Multi-select dropdown
                selected_options = action.get("selected_options", [])
                active_selections[user_id] = [
                    option.get("value") for option in selected_options
                ]
                print(f"✅ Updated selections for {user_id}: {active_selections[user_id]}")
            elif "selected_option" in action:
                # Single select
                active_selections[user_id] = [
                    action.get("selected_option", {}).get("value")
                ]
                print(f"✅ Updated selections for {user_id}: {active_selections[user_id]}")
    except Exception as e:
        print(f"❌ Error processing track selections: {str(e)}")


def handle_submit_confirmation(
    user_id: str,
    channel_id: str,
    selected_tracks: list,
    response_url: Optional[str] = None,
) -> JSONResponse:
    """
    Handle track submission confirmation.
    
    Returns a processing state message and triggers background work.
    """
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
    
    return JSONResponse(content={
        "response_type": "ephemeral",
        "replace_original": True,
        "text": "Processing your track selection...",
        "blocks": processing_blocks
    })


def format_track_display_names(tracks: list) -> list:
    """
    Convert track IDs to human-readable display names.
    
    Args:
        tracks: List of track IDs (e.g., ['backend', 'frontend'])
    
    Returns:
        List of display names (e.g., ['Backend Development', 'Frontend Development'])
    """
    track_display_map = {
        "frontend": "Frontend Development",
        "backend": "Backend Development",
        "mobile": "Mobile Development",
        "uiux": "Product Design (UI/UX)",
        "pm": "Product Management",
        "devops": "DevOps",
        "data-analysis": "Data Analysis/Science",
        "qa": "Quality Assurance",
        "virtual-assistant": "Virtual Assistant",
        "graphics": "Graphics Design",
        "marketing": "Marketing",
        "video": "Video Production",
        "automations": "Automations",
    }
    
    return [
        track_display_map.get(track, track) for track in tracks
    ]


def create_success_blocks(readable_tracks: list) -> list:
    """
    Create block elements for a successful track selection.
    """
    return [
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


def create_error_blocks(error_message: str = "An unexpected error occurred.") -> list:
    """
    Create block elements for an error state.
    """
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "❌ *Error*"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"_{error_message}_\nPlease try again or contact an administrator."
                }
            ]
        }
    ]


def create_track_selection_blocks(tracks_list: list) -> list:
    """
    Create the interactive block elements for track selection.
    
    Args:
        tracks_list: List of track IDs to display
    
    Returns:
        List of block dictionaries for Slack API
    """
    track_options = []
    
    track_display_map = {
        "frontend": ("Frontend Development", "🌐"),
        "backend": ("Backend Development", "⚙️"),
        "mobile": ("Mobile Development", "📱"),
        "uiux": ("Product Design (UI/UX)", "🎨"),
        "pm": ("Product Management", "📊"),
        "devops": ("DevOps", "🚀"),
        "data-analysis": ("Data Analysis/Science", "📈"),
        "qa": ("Quality Assurance", "🔍"),
        "virtual-assistant": ("Virtual Assistant", "🤖"),
        "graphics": ("Graphics Design", "🖌️"),
        "marketing": ("Marketing", "📣"),
        "video": ("Video Production", "🎬"),
        "automations": ("Automations", "⚡"),
    }
    
    for track in tracks_list:
        display_name, emoji = track_display_map.get(
            track, (track, "📝")
        )
        
        track_options.append({
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {display_name}",
                "emoji": True
            },
            "value": track,
            "description": {
                "type": "plain_text",
                "text": f"Select to mentor in {display_name}",
                "emoji": True
            }
        })
    
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Please select the track(s) you would like to mentor:*"
            }
        },
        {
            "type": "divider"
        },
        {
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
        },
        {
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
        }
    ]
