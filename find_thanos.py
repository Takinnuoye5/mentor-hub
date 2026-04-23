#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from slack_sdk import WebClient

load_dotenv()
token = os.getenv('SLACK_BOT_TOKEN_HNG14')
client = WebClient(token=token)

try:
    result = client.users_list()
    for user in result['members']:
        name = user.get('name', '').lower()
        real_name = user.get('real_name', '').lower()
        profile = user.get('profile', {})
        display_name = profile.get('display_name', '').lower()
        
        if 'thanos' in name or 'thanos' in real_name or 'thanos' in display_name:
            print(f'Found: {user["id"]} - Name: {user.get("name")}, Real: {user.get("real_name")}, Display: {display_name}')
except Exception as e:
    print(f'Error: {e}')
