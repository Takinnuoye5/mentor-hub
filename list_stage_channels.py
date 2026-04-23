#!/usr/bin/env python3
"""List all stage-zero and stage-one channels."""

from slack_sdk import WebClient
import os
from dotenv import load_dotenv

try:
    load_dotenv()
    BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN_HNG14')
    print(f"BOT_TOKEN loaded: {bool(BOT_TOKEN)}")
    
    client = WebClient(token=BOT_TOKEN)
    
    all_channels = []
    cursor = None
    count = 0
    while True:
        print(f"Fetching batch {count+1}...", flush=True)
        resp = client.conversations_list(limit=100, cursor=cursor, exclude_archived=False)
        batch = resp.get('channels', [])
        all_channels.extend(batch)
        print(f"  Got {len(batch)} channels, total so far: {len(all_channels)}", flush=True)
        cursor = resp.get('response_metadata', {}).get('next_cursor')
        count += 1
        if not cursor or count > 10:  # Safety limit
            break

    stage_zero = sorted([c for c in all_channels if 'stage-zero' in c['name']], key=lambda x: x['name'])
    stage_one = sorted([c for c in all_channels if 'stage-one' in c['name']], key=lambda x: x['name'])

    print('\nStage-Zero Channels:')
    for ch in stage_zero:
        print(f'  {ch["name"]}')

    print(f'\nStage-One Channels:')
    for ch in stage_one:
        print(f'  {ch["name"]}')

    print(f'\nTotal channels: {len(all_channels)}')
except Exception as e:
    print(f"Error: {e}", flush=True)
    import traceback
    traceback.print_exc()
