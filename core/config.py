#!/usr/bin/env python3
"""
Configuration Settings

This file contains centralized configuration settings for the
mentor track selection system. Environment variables override defaults.
"""

import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Slack Channel IDs
CHANNEL_IDS = {
    "mentors": "C09BDFLLBLP",          # Main mentors channel
    "mentor_random": "C09ARQY34MB",    # Mentor random channel
    "announcements": "C09D5HEK1JN",    # Bot announcements channel
    "admin_notifications": "C09D5HEK1JN"  # Admin notifications for track selections
}

# System Settings
SYSTEM_SETTINGS = {
    "testing_mode": os.getenv("TESTING_MODE", "false").lower() == "true",
    "log_instead_of_notify": os.getenv("LOG_INSTEAD_OF_NOTIFY", "false").lower() == "true",
    "debug_level": os.getenv("DEBUG_LEVEL", "standard")
}

# Google Sheets Configuration
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    None  # Must be provided via environment variable
)
GOOGLE_SPREADSHEET_NAME = os.getenv(
    "GOOGLE_SPREADSHEET_NAME",
    "HNG 14 Mentor Track Selection"
)

# Track configuration
TRACKS = {
    "frontend": {
        "name": "Frontend Development",
        "emoji": "🌐",
        "channel_id": "C09BDFLLC5C"
    },
    "backend": {
        "name": "Backend Development",
        "emoji": "⚙️",
        "channel_id": "C09BDEFC7LR"
    },
    "mobile": {
        "name": "Mobile Development",
        "emoji": "📱",
        "channel_id": "C09BDEFC9MK"
    },
    "uiux": {
        "name": "Product Design (UI/UX)",
        "emoji": "🎨",
        "channel_id": "C09BDMFSB2A"
    },
    "pm": {
        "name": "Product Management",
        "emoji": "📊",
        "channel_id": "C09BDHGDSM2"
    },
    "devops": {
        "name": "DevOps",
        "emoji": "🚀",
        "channel_id": "C09BDK45SCN"
    },
    "data-analysis": {
        "name": "Data Analysis/Science",
        "emoji": "📈",
        "channel_id": "C09BDHHQJLD"
    },
    "qa": {
        "name": "Quality Assurance",
        "emoji": "🔍",
        "channel_id": "C09BDMFSCSM"
    },
    "virtual-assistant": {
        "name": "Virtual Assistant",
        "emoji": "🤖",
        "channel_id": "C09BDJL692N"
    },
    "marketing": {
        "name": "Marketing",
        "emoji": "📣",
        "channel_id": "C09BDJL8S4L"
    },
    "video": {
        "name": "Video Production",
        "emoji": "🎬",
        "channel_id": "C09BDJL9U5M"
    }
}

def get_readable_track_name(track_id):
    """Get human-readable track name from track ID"""
    if track_id in TRACKS:
        return TRACKS[track_id]["name"]
    return track_id

def get_track_emoji(track_id):
    """Get emoji for a track"""
    if track_id in TRACKS:
        return TRACKS[track_id]["emoji"]
    return "📝"

def get_track_channel_id(track_id):
    """Get channel ID for a track"""
    if track_id in TRACKS:
        return TRACKS[track_id]["channel_id"]
    return None