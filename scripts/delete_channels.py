#!/usr/bin/env python3
"""
Interactive script to delete/archive Slack channels.
Lists channels you're in and lets you select which ones to delete.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv(dotenv_path=str(Path(__file__).parent.parent / '.env'))

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")

bot_client = WebClient(token=BOT_TOKEN)
user_client = WebClient(token=USER_TOKEN)

# Your Slack ID (TMCoded)
MY_USER_ID = "U09C0AAHT0Q"


def get_my_channels():
    """Get all channels that you're a member of."""
    print("\n📥 Fetching your channels...")
    
    try:
        my_channels = []
        cursor = None
        
        while True:
            # Get all channels
            resp = bot_client.conversations_list(
                types="public_channel,private_channel",
                limit=200,
                cursor=cursor,
                exclude_archived=False
            )
            
            for channel in resp.get("channels", []):
                # Check if you're a member
                if channel.get("is_member", False):
                    my_channels.append({
                        "id": channel["id"],
                        "name": channel["name"],
                        "is_private": channel.get("is_private", False),
                        "is_archived": channel.get("is_archived", False),
                        "num_members": channel.get("num_members", 0)
                    })
            
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        
        print(f"✅ Found {len(my_channels)} channels you're in\n")
        return my_channels
    
    except Exception as e:
        print(f"❌ Error fetching channels: {str(e)}")
        return []


def display_channels(channels):
    """Display channels in a numbered list."""
    if not channels:
        print("❌ No channels found")
        return
    
    print("="*80)
    print("YOUR CHANNELS")
    print("="*80)
    
    for i, ch in enumerate(channels, 1):
        privacy = "🔒 Private" if ch["is_private"] else "🌐 Public"
        archived = " [ARCHIVED]" if ch["is_archived"] else ""
        members = f"({ch['num_members']} members)"
        
        print(f"{i:3d}. #{ch['name']:30s} {privacy:12s} {members:15s}{archived}")
    
    print("="*80)


def delete_channel(channel_id, channel_name):
    """Delete (archive) a channel."""
    print(f"\n🗑️  Deleting channel: {channel_name}")
    
    try:
        # Slack doesn't allow permanent deletion via API, only archiving
        user_client.conversations_archive(channel=channel_id)
        print(f"✅ Channel archived successfully: {channel_name}")
        print(f"   Note: The channel is archived, not permanently deleted.")
        print(f"   Workspace admins can restore it if needed.")
        return True
    
    except SlackApiError as e:
        error = e.response.get("error", "")
        
        if error == "already_archived":
            print(f"ℹ️  Channel is already archived")
            return True
        elif error == "cant_archive_general":
            print(f"❌ Cannot archive #general channel")
            return False
        elif error == "restricted_action":
            print(f"❌ You don't have permission to archive this channel")
            return False
        else:
            print(f"❌ Error archiving channel: {error}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def main():
    print("="*80)
    print("🗑️  DELETE/ARCHIVE SLACK CHANNELS")
    print("="*80)
    print("\nThis script will help you archive channels you're in.")
    print("Note: Slack API can only ARCHIVE channels, not permanently delete them.")
    print("Workspace admins can restore archived channels if needed.\n")
    
    # Get channels
    channels = get_my_channels()
    
    if not channels:
        print("❌ No channels to delete")
        return
    
    # Display channels
    display_channels(channels)
    
    # Selection loop
    while True:
        print("\nOptions:")
        print("  - Enter channel number(s) to delete (e.g., '1' or '1,3,5')")
        print("  - Enter channel name (e.g., 'test-channel')")
        print("  - Type 'list' to see channels again")
        print("  - Type 'quit' to exit")
        
        user_input = input("\nYour choice: ").strip()
        
        if not user_input:
            continue
        
        if user_input.lower() == 'quit':
            print("\n👋 Exiting...")
            break
        
        if user_input.lower() == 'list':
            display_channels(channels)
            continue
        
        # Parse input - could be numbers or channel name
        channels_to_delete = []
        
        # Check if it's a comma-separated list of numbers
        if ',' in user_input or user_input.isdigit():
            try:
                numbers = [int(n.strip()) for n in user_input.split(',')]
                for num in numbers:
                    if 1 <= num <= len(channels):
                        channels_to_delete.append(channels[num - 1])
                    else:
                        print(f"⚠️  Invalid number: {num}")
            except ValueError:
                print("❌ Invalid input. Use numbers (e.g., '1' or '1,3,5')")
                continue
        else:
            # Try to find channel by name
            channel_name = user_input.lower().replace("#", "").strip()
            found = [ch for ch in channels if ch["name"] == channel_name]
            
            if found:
                channels_to_delete.extend(found)
            else:
                print(f"❌ Channel not found: {channel_name}")
                continue
        
        if not channels_to_delete:
            print("❌ No valid channels selected")
            continue
        
        # Confirm deletion
        print(f"\n⚠️  You are about to archive {len(channels_to_delete)} channel(s):")
        for ch in channels_to_delete:
            privacy = "private" if ch["is_private"] else "public"
            print(f"   - #{ch['name']} ({privacy})")
        
        confirm = input("\nAre you sure? Type 'yes' to confirm: ").strip()
        
        if confirm.lower() == 'yes':
            print("\n" + "="*80)
            deleted_count = 0
            
            for ch in channels_to_delete:
                if delete_channel(ch["id"], ch["name"]):
                    deleted_count += 1
                    # Remove from list
                    channels.remove(ch)
            
            print("="*80)
            print(f"\n✅ Archived {deleted_count} out of {len(channels_to_delete)} channels")
            
            if channels:
                print(f"\n📊 You still have {len(channels)} channels")
            else:
                print("\n✅ All your channels have been processed!")
                break
        else:
            print("❌ Cancelled")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(0)
