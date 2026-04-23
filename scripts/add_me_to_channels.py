#!/usr/bin/env python3
"""
Interactive script to add yourself to selected Slack channels.
Lists all channels and lets you choose which ones to join.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load .env from project root
load_dotenv(dotenv_path=str(Path(__file__).parent.parent / '.env'))

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")

bot_client = WebClient(token=BOT_TOKEN)
user_client = WebClient(token=USER_TOKEN)

# Your user ID
YOUR_USER_ID = "U0AH4HF1NLU"


def get_all_channels():
    """Fetch all accessible channels from both bot and user tokens."""
    channels = []
    seen_ids = set()
    
    print("📥 Fetching all channels (from bot and user perspectives)...")
    
    try:
        # Try bot token first (bot has access to all channels it's added to)
        cursor = None
        while True:
            resp = bot_client.conversations_list(
                types="public_channel,private_channel",
                limit=100,
                cursor=cursor,
            )
            for ch in resp.get("channels", []):
                if ch["id"] not in seen_ids:
                    channels.append(ch)
                    seen_ids.add(ch["id"])
            
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        print(f"⚠️ Warning fetching with bot token: {e}")
    
    try:
        # Also try user token to capture channels user might have that bot doesn't
        cursor = None
        while True:
            resp = user_client.conversations_list(
                types="public_channel,private_channel",
                limit=100,
                cursor=cursor,
            )
            for ch in resp.get("channels", []):
                if ch["id"] not in seen_ids:
                    channels.append(ch)
                    seen_ids.add(ch["id"])
            
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        print(f"⚠️ Warning fetching with user token: {e}")
    
    print(f"✅ Found {len(channels)} channels\n")
    return channels


def display_channels(channels):
    """Display channels in a numbered list (sorted alphabetically)."""
    print("=" * 80)
    print("AVAILABLE CHANNELS (Sorted alphabetically)")
    print("=" * 80)
    
    # Sort channels alphabetically
    sorted_channels = sorted(channels, key=lambda c: c["name"].lower())
    
    for i, channel in enumerate(sorted_channels, 1):
        privacy = "🔒 PRIVATE" if channel.get("is_private") else "🌐 PUBLIC"
        archived = " (ARCHIVED)" if channel.get("is_archived") else ""
        channel_name = channel["name"]
        print(f"{i:3d}. {privacy:12} | #{channel_name}{archived}")
    
    print("=" * 80)
    
    # Return sorted channels so selection indices match display order
    return sorted_channels


def prompt_for_channels(channels):
    """Get user input for which channels to join."""
    selected = []
    
    while True:
        try:
            user_input = input(
                "\nEnter channel numbers (e.g., '1 5 10' or 'all'): "
            ).strip().lower()
            
            if user_input == "all":
                selected = list(range(len(channels)))
                break
            elif user_input == "":
                print("⚠️ Please enter valid channel numbers")
                continue
            else:
                # Parse numbers
                selected = []
                for num_str in user_input.split():
                    try:
                        num = int(num_str) - 1
                        if 0 <= num < len(channels):
                            selected.append(num)
                        else:
                            print(f"⚠️ {num+1} is out of range")
                    except ValueError:
                        print(f"⚠️ '{num_str}' is not a valid number")
                
                if selected:
                    break
                else:
                    print("❌ No valid channels selected. Try again.")
        
        except KeyboardInterrupt:
            print("\n\n❌ Cancelled by user")
            return []
    
    return selected


def add_me_to_channels(channels, selected_indices):
    """Add yourself to selected channels."""
    bot_id = bot_client.auth_test()["user_id"]
    
    print(f"\n{'=' * 80}")
    print(f"ADDING YOU ({YOUR_USER_ID}) TO SELECTED CHANNELS")
    print(f"{'=' * 80}\n")
    
    success_count = 0
    failed_count = 0
    
    for idx in selected_indices:
        if idx >= len(channels):
            continue
        
        channel = channels[idx]
        channel_id = channel["id"]
        channel_name = channel["name"]
        
        print(f"📌 Processing: #{channel_name}")
        
        # Step 1: Make sure bot is in the channel
        try:
            bot_client.conversations_info(channel=channel_id)
            print(f"   ✅ Bot is already in channel")
        except SlackApiError:
            print(f"   ⚠️ Bot not in channel, trying to add it...")
            try:
                user_client.conversations_invite(channel=channel_id, users=[bot_id])
                print(f"   ✅ Added bot to channel")
            except SlackApiError as e:
                if "is_archived" in str(e):
                    print(f"   ❌ Channel is archived - cannot join")
                    failed_count += 1
                    continue
                else:
                    print(f"   ❌ Could not add bot: {e.response['error']}")
                    failed_count += 1
                    continue
        
        # Step 2: Add you to the channel
        try:
            bot_client.conversations_invite(channel=channel_id, users=[YOUR_USER_ID])
            print(f"   ✅ Added you to #{channel_name}")
            success_count += 1
        except SlackApiError as e:
            err = e.response["error"]
            if err == "already_in_channel":
                print(f"   ℹ️ You're already in #{channel_name}")
                success_count += 1
            elif err in ["not_in_channel", "user_not_found"]:
                # Bot can't access, try user token instead
                print(f"   ⚠️ Bot approach failed, trying with user token...")
                try:
                    user_client.conversations_invite(channel=channel_id, users=[YOUR_USER_ID])
                    print(f"   ✅ Added you to #{channel_name} (via user token)")
                    success_count += 1
                except SlackApiError as e2:
                    err2 = e2.response["error"]
                    if err2 == "already_in_channel":
                        print(f"   ℹ️ You're already in #{channel_name}")
                        success_count += 1
                    else:
                        print(f"   ❌ Error: {err2}")
                        failed_count += 1
            else:
                print(f"   ❌ Error adding you: {err}")
                failed_count += 1
        
        print()
    
    # Summary
    print(f"{'=' * 80}")
    print(f"SUMMARY")
    print(f"{'=' * 80}")
    print(f"✅ Successfully added to: {success_count} channel(s)")
    print(f"❌ Failed: {failed_count} channel(s)")
    print(f"{'=' * 80}\n")


def main():
    """Main function."""
    print("\n" + "=" * 80)
    print("ADD ME TO SLACK CHANNELS")
    print("=" * 80)
    print(f"Your User ID: {YOUR_USER_ID}\n")
    
    # Get all channels
    channels = get_all_channels()
    if not channels:
        print("❌ No channels found")
        return
    
    # Display channels (sorted) and get sorted list back
    channels = display_channels(channels)
    
    # Get user selection
    selected_indices = prompt_for_channels(channels)
    if not selected_indices:
        print("❌ No channels selected")
        return
    
    # Show what will be added
    print(f"\n📋 You selected {len(selected_indices)} channel(s):")
    for idx in selected_indices:
        print(f"   • #{channels[idx]['name']}")
    
    confirm = input("\n✅ Confirm and add you to these channels? (yes/no): ").strip().lower()
    if confirm not in ["yes", "y"]:
        print("❌ Cancelled")
        return
    
    # Add you to channels
    add_me_to_channels(channels, selected_indices)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Script interrupted by user")
        sys.exit(0)
