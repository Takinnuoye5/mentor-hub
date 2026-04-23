#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from slack_sdk import WebClient

os.chdir('/home/ubuntu/mentor-hub')
load_dotenv()

try:
    bot = WebClient(token=os.getenv('SLACK_BOT_TOKEN'))
    
    # Get all channels
    all_ch = []
    cursor = None
    page = 0
    while True:
        resp = bot.conversations_list(limit=1000, cursor=cursor, exclude_archived=True)
        all_ch.extend(resp['channels'])
        cursor = resp.get('response_metadata', {}).get('next_cursor')
        page += 1
        print(f'[Page {page}] Retrieved {len(resp["channels"])} channels, total: {len(all_ch)}')
        if not cursor:
            break
    
    # Show stage channels
    stages = {}
    for ch in all_ch:
        if ch['name'].startswith('stage-'):
            parts = ch['name'].split('-')
            try:
                stage = int(parts[1])
                if stage not in stages:
                    stages[stage] = []
                stages[stage].append(ch['name'])
            except:
                pass
    
    print(f'\n✅ Total channels: {len(all_ch)}')
    print(f'✅ Stages found: {sorted(stages.keys())}')
    print()
    for s in sorted(stages.keys()):
        print(f'Stage {s} ({len(stages[s])} channels):')
        for ch in sorted(stages[s]):
            print(f'  - {ch}')
    
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
