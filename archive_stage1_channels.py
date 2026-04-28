#!/usr/bin/env python3
"""
Archive stage-1 channels that were created by mistake.
"""
import os
import re
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")

bot_client = WebClient(token=BOT_TOKEN)
user_client = WebClient(token=USER_TOKEN)

print("🔍 Finding stage-1 channels to archive...\n")

cursor = None
stage1_to_archive = []
stage1_pattern = re.compile(r'^stage-1')

while True:
    resp = bot_client.conversations_list(
        types="private_channel",
        limit=200,
        cursor=cursor,
    )
    
    for ch in resp.get("channels", []):
        if stage1_pattern.match(ch["name"]):
            if not ch.get("is_archived", False):  # Only active channels
                stage1_to_archive.append({
                    'name': ch['name'],
                    'id': ch['id'],
                })
    
    cursor = resp.get("response_metadata", {}).get("next_cursor")
    if not cursor:
        break

if not stage1_to_archive:
    print("✅ No active stage-1 channels found to archive")
else:
    print(f"📋 Found {len(stage1_to_archive)} active stage-1 channels to archive:\n")
    for ch in stage1_to_archive:
        print(f"   - {ch['name']}")
    
    print("\n🔒 Archiving stage-1 channels...\n")
    
    for ch in stage1_to_archive:
        try:
            # Try with user token first (higher permissions)
            user_client.conversations_archive(channel=ch['id'])
            print(f"✅ Archived: {ch['name']}")
        except SlackApiError as e:
            print(f"⚠️  Failed to archive {ch['name']} with user token: {e.response['error']}")
            try:
                # Fallback to bot token
                bot_client.conversations_archive(channel=ch['id'])
                print(f"✅ Archived: {ch['name']} (with bot token)")
            except SlackApiError as e2:
                print(f"❌ Failed to archive {ch['name']}: {e2.response['error']}")
        except Exception as e:
            print(f"❌ Error archiving {ch['name']}: {e}")
    
    print("\n✅ Done!")
