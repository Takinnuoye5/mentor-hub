#!/usr/bin/env python3
"""
Script to find Slack user IDs by searching for usernames using the Slack API.
This will help us find the remaining track leads.
"""
import os
import sys
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import json

load_dotenv()

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")

bot_client = WebClient(token=BOT_TOKEN)
user_client = WebClient(token=USER_TOKEN)

# Names we need to find IDs for
MISSING_LEADS = [
    "EL'TANA",
    "MiKEY",
    "Adaeze",
    "0xCollins",
    "Fiza",
    "Cynth.",
    "Lynn.B",
    "Neon",
    "HendrixX",
    "Her Chaos"
]


def normalize_name(name):
    """Normalize a name for comparison."""
    if not name:
        return ""
    return name.lower().strip().replace(".", "").replace("'", "").replace(" ", "")


def fetch_all_users():
    """Fetch all users from Slack workspace or load from cache."""
    # First try to load from existing user cache
    print("📥 Checking for existing user cache...")
    
    try:
        from mentor_hub.core import user_cache
    except ImportError:
        # Fallback for direct execution
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core import user_cache
    
    try:
        user_cache.load_user_cache()
        cached_users = list(user_cache.user_cache.values())
        if cached_users:
            print(f"✅ Loaded {len(cached_users)} users from user_cache.json\n")
            return cached_users
    except Exception as e:
        print(f"⚠️ Could not load user_cache.json: {e}")
    
    # Try loading from all_users.json as backup
    if os.path.exists("all_users.json"):
        print("📥 Loading from all_users.json...")
        try:
            with open("all_users.json", "r", encoding="utf-8") as f:
                all_users = json.load(f)
            if all_users:
                print(f"✅ Loaded {len(all_users)} users from all_users.json\n")
                return all_users
        except Exception as e:
            print(f"⚠️ Could not load all_users.json: {e}")
    
    # Finally, try fetching from API with better error handling
    print("📥 Fetching all users from Slack API (this may take a while)...")
    all_users = []
    cursor = None
    
    try:
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                while True:
                    response = bot_client.users_list(cursor=cursor, limit=100)  # Reduced limit
                    users = response.get("members", [])
                    all_users.extend(users)
                    print(f"   Fetched {len(all_users)} users so far...")
                    
                    cursor = response.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
                    
                    # Add a small delay between requests
                    import time
                    time.sleep(0.5)
                
                print(f"✅ Fetched {len(all_users)} users\n")
                return all_users
            
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    print(f"⚠️ Error (attempt {retry_count}/{max_retries}): {str(e)[:100]}")
                    print(f"   Retrying in {retry_count * 2} seconds...")
                    import time
                    time.sleep(retry_count * 2)
                else:
                    raise
    
    except SlackApiError as e:
        print(f"❌ Slack API error: {e.response['error']}")
        return []
    except Exception as e:
        print(f"❌ Error fetching users: {str(e)[:200]}")
        return []


def search_users(users, search_names):
    """Search for users by name in the fetched user list."""
    print("🔍 Searching for track leads...\n")
    
    # Create normalized search mapping
    search_map = {normalize_name(name): name for name in search_names}
    found = {}
    
    for user in users:
        if user.get("deleted") or user.get("is_bot"):
            continue
        
        profile = user.get("profile", {})
        user_id = user.get("id", "")
        
        # Get all possible name fields
        slack_name = user.get("name", "").lower()
        display_name = profile.get("display_name", "").lower()
        display_name_normalized = profile.get("display_name_normalized", "").lower()
        real_name = user.get("real_name", "").lower()
        real_name_normalized = profile.get("real_name_normalized", "").lower()
        
        # Check against each search name
        for norm_search, original_name in search_map.items():
            # Try exact matches first
            if norm_search in [
                normalize_name(slack_name),
                normalize_name(display_name),
                normalize_name(display_name_normalized),
                normalize_name(real_name),
                normalize_name(real_name_normalized)
            ]:
                if original_name not in found:
                    found[original_name] = []
                
                found[original_name].append({
                    'id': user_id,
                    'slack_name': user.get("name", ""),
                    'display_name': profile.get("display_name", ""),
                    'real_name': user.get("real_name", "")
                })
    
    return found


def display_results(found, search_names):
    """Display search results."""
    print(f"{'='*80}")
    print(f"📊 SUMMARY: Found matches for {len(found)} out of {len(search_names)} track leads")
    print(f"{'='*80}\n")
    
    if found:
        print("✅ Found users (copy these to update TRACKS):\n")
        
        for name in search_names:
            if name in found:
                matches = found[name]
                if len(matches) == 1:
                    # Single match - show with confidence
                    match = matches[0]
                    print(f'    "{name}" -> "{match["id"]}",  # {match["display_name"] or match["real_name"]} (@{match["slack_name"]})')
                else:
                    # Multiple matches - show all options
                    print(f'\n    "{name}" - Multiple matches found:')
                    for i, match in enumerate(matches, 1):
                        display = match["display_name"] or match["real_name"]
                        print(f'        Option {i}: "{match["id"]}"  # {display} (@{match["slack_name"]})')
        
        print()
    
    # Show what's still missing
    missing = [name for name in search_names if name not in found]
    if missing:
        print(f"\n⚠️ Still not found ({len(missing)}):")
        for name in missing:
            print(f"   - {name}")
        print("\nTip: These users might be using very different display names.")
        print("You can:")
        print("  1. Search for them manually in Slack workspace")
        print("  2. Ask them directly for their Slack user ID")
        print("  3. Check if they've changed their username significantly")


def export_user_cache(users):
    """Export users to a cache file for future reference."""
    try:
        cache_data = {}
        for user in users:
            if not user.get("deleted") and not user.get("is_bot"):
                cache_data[user["id"]] = {
                    "id": user["id"],
                    "name": user.get("name", ""),
                    "real_name": user.get("real_name", ""),
                    "display_name": user.get("profile", {}).get("display_name", "")
                }
        
        with open("slack_users_cache.json", "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
        
        print(f"\n💾 Exported {len(cache_data)} users to slack_users_cache.json")
        print("   (You can search this file manually if needed)")
    except Exception as e:
        print(f"⚠️ Could not export cache: {e}")


def main():
    print("🔍 Searching for Slack user IDs using the Slack API...\n")
    
    # Fetch all users
    users = fetch_all_users()
    
    if not users:
        print("❌ Could not fetch users from Slack")
        return
    
    # Export to cache file for manual searching if needed
    export_user_cache(users)
    
    # Search for our missing leads
    found = search_users(users, MISSING_LEADS)
    
    # Display results
    display_results(found, MISSING_LEADS)


if __name__ == "__main__":
    main()
