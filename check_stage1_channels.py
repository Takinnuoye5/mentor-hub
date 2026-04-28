#!/usr/bin/env python3
"""
Check which stage-1 channels exist and their archive status.
"""
import os
import re
from slack_sdk import WebClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=str(Path(__file__).parent / '.env'))
BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
bot_client = WebClient(token=BOT_TOKEN)

print("🔍 Checking for stage-1 channels...\n")

cursor = None
stage1_channels = []
stage1_pattern = re.compile(r'^stage-1')

while True:
    resp = bot_client.conversations_list(
        types="private_channel",
        limit=200,
        cursor=cursor,
    )
    
    for ch in resp.get("channels", []):
        if stage1_pattern.match(ch["name"]):
            is_archived = ch.get("is_archived", False)
            status = "🔴 ARCHIVED" if is_archived else "🟢 ACTIVE"
            print(f"{status} | {ch['name']}")
            stage1_channels.append({
                'name': ch['name'],
                'id': ch['id'],
                'archived': is_archived
            })
    
    cursor = resp.get("response_metadata", {}).get("next_cursor")
    if not cursor:
        break

print(f"\n📊 Summary:")
print(f"   Total stage-1 channels: {len(stage1_channels)}")

active = [ch for ch in stage1_channels if not ch['archived']]
archived = [ch for ch in stage1_channels if ch['archived']]

print(f"   Active: {len(active)}")
if active:
    for ch in active:
        print(f"      - {ch['name']}")

print(f"   Archived: {len(archived)}")
if archived:
    for ch in archived:
        print(f"      - {ch['name']}")
