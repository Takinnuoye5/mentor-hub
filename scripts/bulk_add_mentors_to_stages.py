#!/usr/bin/env python3
"""
Bulk add mentors from Google Sheet to existing stage channels.
Does NOT create any channels - only adds to existing ones.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=str(Path(__file__).parent.parent / '.env'))

try:
    from mentor_hub.scripts import create_stage_channels as csc
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import create_stage_channels as csc

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

_env_creds = os.getenv("GOOGLE_CREDENTIALS_FILE")
if _env_creds:
    csc.GOOGLE_CREDENTIALS_FILE = _env_creds

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")
bot_client = WebClient(token=BOT_TOKEN)
user_client = WebClient(token=USER_TOKEN) if USER_TOKEN else None

print(f"DEBUG: BOT_TOKEN set: {bool(BOT_TOKEN)}")
print(f"DEBUG: USER_TOKEN set: {bool(USER_TOKEN)}")
if not USER_TOKEN:
    print("⚠️  WARNING: USER_TOKEN not found in .env, will only use bot token")

# Global channel cache
_channel_cache = {}


def get_all_mentors_from_sheet():
    """Read all mentors from the Google Sheet."""
    print("📑 Reading all mentors from Google Sheet...")
    try:
        spreadsheet, worksheet = csc.setup_google_sheets()
        if not worksheet:
            print("❌ Could not access mentor worksheet")
            return []
        records = worksheet.get_all_records()
        print(f"✅ Found {len(records)} total submissions\n")
        return records
    except Exception as e:
        print(f"❌ Error reading sheet: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_valid_mentors(records):
    """Extract valid mentors from sheet records."""
    mentors = {}
    for record in records:
        slack_id = (record.get("Slack ID") or "").strip()
        tracks_str = (record.get("Selected Tracks") or "").strip()
        timestamp = (record.get("Timestamp") or "").strip()
        
        if not slack_id or not timestamp:
            continue
        
        all_tracks = [t.strip() for t in tracks_str.split(",") if t.strip()]
        valid_tracks = [t for t in all_tracks if t in csc.TRACKS]
        
        if set(all_tracks) - set(valid_tracks):
            invalid = set(all_tracks) - set(valid_tracks)
            print(f"⚠️  {slack_id}: Ignoring invalid tracks: {invalid}")
        
        mentors[slack_id] = {
            "display_name": record.get("Display Name", "").strip(),
            "tracks": valid_tracks,
        }
    
    return mentors


def get_channel_id(channel_name, track=None):
    """Get channel ID by name using both bot and user tokens.
    
    Handles special cases like stage-2-da (shortened from stage-2-data-analysis).
    """
    global _channel_cache
    
    # Build list of names to try
    channel_aliases = {
        "stage-2-data-analysis": "stage-2-da",
    }
    names_to_try = [channel_name]
    if channel_name in channel_aliases:
        names_to_try.append(channel_aliases[channel_name])
    
    # Check cache first
    for name in names_to_try:
        if name in _channel_cache:
            return _channel_cache[name]
    
    # Load all channels from Slack if cache is empty (using both tokens)
    if not _channel_cache:
        try:
            # Fetch from bot token
            cursor = None
            while True:
                resp = bot_client.conversations_list(
                    types="public_channel,private_channel",
                    limit=200,
                    cursor=cursor,
                    exclude_archived=False
                )
                for channel in resp.get("channels", []):
                    _channel_cache[channel["name"]] = channel["id"]
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            
            # Also fetch from user token if available (to get channels bot isn't in)
            if user_client:
                cursor = None
                while True:
                    resp = user_client.conversations_list(
                        types="public_channel,private_channel",
                        limit=200,
                        cursor=cursor,
                        exclude_archived=False
                    )
                    for channel in resp.get("channels", []):
                        if channel["name"] not in _channel_cache:
                            _channel_cache[channel["name"]] = channel["id"]
                    cursor = resp.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
        except SlackApiError as e:
            print(f"⚠️  Error loading channels: {e}")
    
    # Try to find the channel in cache
    for name in names_to_try:
        if name in _channel_cache:
            return _channel_cache[name]
    
    return None


def get_channel_members(channel_id):
    """Get list of user IDs in a channel (try bot first, then user token)."""
    try:
        resp = bot_client.conversations_members(channel=channel_id, limit=1000)
        return set(resp.get("members", []))
    except SlackApiError:
        # Try user token if bot fails and available
        if user_client:
            try:
                resp = user_client.conversations_members(channel=channel_id, limit=1000)
                return set(resp.get("members", []))
            except SlackApiError:
                return set()
        return set()


def add_mentor_to_channel(mentor_id, channel_id):
    """Add a mentor to an existing channel using bot or user token."""
    # Try bot token first
    try:
        bot_client.conversations_invite(channel=channel_id, users=[mentor_id])
        return True, "added"
    except SlackApiError as e:
        err = e.response.get("error", str(e))
        if err == "already_in_channel":
            return True, "already_in"
        elif err in ["not_in_channel", "user_not_found"] and user_client:
            # Bot not in channel, try user token instead
            try:
                user_client.conversations_invite(channel=channel_id, users=[mentor_id])
                return True, "added_via_user"
            except SlackApiError as e2:
                err2 = e2.response.get("error", str(e2))
                if err2 == "already_in_channel":
                    return True, "already_in"
                return False, err2
        return False, err


def bulk_add_mentors(mentors, start_stage=2):
    """Add mentors to existing stage channels (no creation)."""
    print(f"\n{'='*80}")
    print(f"ADDING MENTORS TO EXISTING CHANNELS (Stage {start_stage}+)")
    print(f"{'='*80}\n")
    
    # Pre-load all channels
    print("📡 Loading all channels from Slack...")
    get_channel_id("dummy")  # This triggers the global cache load
    print(f"✅ Loaded {len(_channel_cache)} channels\n")
    
    stats = {"total": len(mentors), "added": 0, "already_in": 0, "failed": 0, "skipped": 0}
    mentor_idx = 0
    
    for slack_id, mentor_info in mentors.items():
        mentor_idx += 1
        display_name = mentor_info.get("display_name", slack_id)
        tracks = mentor_info.get("tracks", [])
        
        # Only print first 5 and last 5 to avoid spam
        if mentor_idx <= 5 or mentor_idx >= len(mentors) - 4:
            print(f"[{mentor_idx}/{len(mentors)}] 👤 {display_name}")
        elif mentor_idx == 6:
            print(f"... (processing {len(mentors) - 10} more mentors) ...")
        
        if not tracks:
            stats["skipped"] += 1
            continue
        
        # Process each stage
        for stage_num in range(start_stage, 5):  # Stages 2, 3, 4
            stage_name = f"stage-{stage_num}"
            
            # Main stage channel
            ch_id = get_channel_id(stage_name)
            if ch_id:
                members = get_channel_members(ch_id)
                if slack_id not in members:
                    success, msg = add_mentor_to_channel(slack_id, ch_id)
                    if success:
                        stats["added"] += 1
                    else:
                        stats["failed"] += 1
                else:
                    stats["already_in"] += 1
            
            # Track channels
            for track in tracks:
                ch_name = f"{stage_name}-{track}"
                ch_id = get_channel_id(ch_name, track)
                if ch_id:
                    members = get_channel_members(ch_id)
                    if slack_id not in members:
                        success, msg = add_mentor_to_channel(slack_id, ch_id)
                        if success:
                            stats["added"] += 1
                        else:
                            stats["failed"] += 1
                    else:
                        stats["already_in"] += 1
        
        time.sleep(0.05)
    
    # Print summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"Total mentors: {stats['total']}")
    print(f"✅ Added: {stats['added']}")
    print(f"ℹ️  Already in channels: {stats['already_in']}")
    print(f"❌ Failed: {stats['failed']}")
    print(f"⏭️  Skipped: {stats['skipped']}")
    print(f"{'='*80}\n")


def main():
    records = get_all_mentors_from_sheet()
    if not records:
        return
    
    mentors = get_valid_mentors(records)
    print(f"📋 Extracted {len(mentors)} valid mentors\n")
    
    bulk_add_mentors(mentors, start_stage=2)
    print("✅ Done!")


if __name__ == "__main__":
    main()
