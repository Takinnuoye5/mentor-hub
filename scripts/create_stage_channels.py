import os
import time
import sys
import json
import socket
import re
import difflib
import unicodedata
from typing import List, Optional, Dict
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from pathlib import Path
import gspread
from oauth2client.service_account import ServiceAccountCredentials
# Load .env from project root, not current working directory
load_dotenv(dotenv_path=str(Path(__file__).parent.parent / '.env'))

# Debug: Check what was loaded
env_path = str(Path(__file__).parent.parent / '.env')
print(f"DEBUG: Loading .env from: {env_path}")
print(f"DEBUG: File exists: {os.path.exists(env_path)}")
google_creds_env = os.getenv("GOOGLE_CREDENTIALS_FILE")
print(f"DEBUG: After load_dotenv, GOOGLE_CREDENTIALS_FILE = {google_creds_env}")

# Import core modules
try:
    from mentor_hub.core import user_cache
    from mentor_hub.core.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SPREADSHEET_NAME
except ImportError:
    # Fallback for direct execution during development
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core import user_cache
    from core.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SPREADSHEET_NAME

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")

bot_client = WebClient(token=BOT_TOKEN)
user_client = WebClient(token=USER_TOKEN)

# Non-interactive mode flag (set by scheduler or other automation tools)
NON_INTERACTIVE_MODE = False

# Google Sheets configuration (imported from core.config)
SPREADSHEET_NAME = GOOGLE_SPREADSHEET_NAME
WORKSHEET_NAME = "Mentors"  # Will be set based on latest worksheet

users_cache = None

TRACKS = {
    "backend": ["U0AFF5KUAPR", "U0AFWJSFNAE", "U0AH4HF1NLU"],
    "frontend": ["U0AFQ6KAGGK", "U0AGZ0AQYUQ", "U0AH4HF1NLU"],
    "uiux": ["U0AFUGBJHFG", "U0AG06GJH44", "U0AH4HF1NLU"],
    "marketing": ["U0AG9G4EMJ5", "U0AH39BDADN", "U0AG0J3Q0SE", "U0AH4HF1NLU"],
    "video": ["U0AG9G4EMJ5", "U0AH39BDADN", "U0AG0J3Q0SE", "U0AH4HF1NLU"],
    "data-analysis": ["U0AG0P7Q6P6", "U0AGRN1NJ2C", "U0AFWKG57M0", "U0AH4HF1NLU"],
    "pm": ["U0AFVCW8DDZ", "U0AFT5WEV2R", "U0AH4HF1NLU"],
    "qa": ["U0AG0ABH752", "U0AFSUTV49M", "U0AFUDX98ES", "U0AH4HF1NLU"],
    "mobile": ["U0AFL4MGQBZ", "U0AGRA6LSF2", "U0AFP8YQ05R", "U0AFUDZPMPY", "U0AH4HF1NLU"],
    "virtual-assistant": ["U0AG06P0ATE", "U0AFWD7QC5V", "U0AFX2HJVDG", "U0AH4HF1NLU"],
    "devops": ["U0AG1JK34BF", "U0AGQJRUGUT", "U0AH4HF1NLU"],
}



def fetch_all_users(max_retries=3, use_cache_file=True):
    """Fetch and cache all users from the workspace with pagination.
    
    Args:
        max_retries: Maximum number of retries when API calls fail
        use_cache_file: Whether to try loading from all_users.json as fallback
    """
    global users_cache
    if users_cache is not None:
        print(f"   ✅ Using already loaded cache with {len(users_cache)} users")
        return users_cache
    
    # First, try to load from user_cache
    print("📥 Loading users from cache...")
    user_cache.load_user_cache()
    cached_users = list(user_cache.user_cache.values())
    if cached_users:
        print(f"   ✅ Loaded {len(cached_users)} users from user_cache.json")
        users_cache = cached_users
        return users_cache
        
    # Next, try loading from all_users.json as backup if available
    if use_cache_file and os.path.exists("all_users.json"):
        print("📥 Attempting to load users from all_users.json...")
        try:
            with open("all_users.json", 'r', encoding='utf-8') as f:
                all_users = json.load(f)
                
            if all_users:
                print(f"   ✅ Successfully loaded {len(all_users)} users from all_users.json")
                
                # Also add these users to the user_cache for consistency
                for user in all_users:
                    user_id = user.get("id")
                    if user_id:
                        user_cache.add_to_cache(user_id, user)
                
                users_cache = all_users
                return users_cache
        except Exception as e:
            print(f"   ⚠️ Failed to load all_users.json: {e}")
    
    # If we reach here, advise running the preload script instead
    print("\n⚠️ No cached user data found!")
    print("⚠️ To avoid timeouts, please run 'python preload_user_cache.py' first")
    print("⚠️ Continuing with limited user fetch, but this may fail...\n")
    
    # Try to fetch a small number of users as a fallback
    print("📥 Attempting limited API fetch of users (fallback)...")
    
    users = []
    cursor = None
    page = 1
    retry_count = 0
    max_pages = 3  # Limit to just a few pages to avoid timeout
    
    while page <= max_pages:
        try:
            # Add timeout to the request to prevent hanging
            resp = bot_client.users_list(cursor=cursor, limit=100, timeout=10)
            batch = resp.get("members", [])
            users.extend(batch)
            print(f"   🧭 Page {page}: Retrieved {len(batch)} users (total so far: {len(users)})")
            
            # Add users to cache right away
            for user in batch:
                user_id = user.get("id")
                if user_id:
                    user_cache.add_to_cache(user_id, user)
            
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            page += 1
            retry_count = 0  # Reset retry count after successful call
            
            if not cursor or page > max_pages:
                print("   ⚠️ Stopping after limited fetch to avoid timeouts")
                break
                
            # Add small delay between requests to avoid rate limiting
            time.sleep(0.5)
            
        except Exception as e:
            retry_count += 1
            if retry_count > max_retries:
                print(f"   ⚠️ Max retries ({max_retries}) reached, using {len(users)} users collected so far")
                break
                
            wait_time = retry_count * 2
            error_message = str(e)
            if len(error_message) > 100:
                error_message = error_message[:97] + "..."
            print(f"   ⚠️ Error on page {page}, retry {retry_count}/{max_retries}, waiting {wait_time}s: {error_message}")
            time.sleep(wait_time)
    
    if users:
        users_cache = users
        print(f"   ✅ Cached {len(users_cache)} users total\n")
        
        # Save to user_cache.json
        user_cache.save_user_cache()
            
        return users_cache
    else:
        print(f"❌ Failed to fetch any users from Slack API")
        return []


def get_lead_id(identifier, users=None):
    """Convert a track lead identifier to a Slack user ID.
    
    Args:
        identifier: Either a Slack user ID (U...) or a username/display name
        users: Optional list of cached users for name lookup
    
    Returns:
        Slack user ID string or None if not found
    """
    if not identifier:
        return None
    
    # If it's already a Slack ID format (starts with U and is alphanumeric), return it
    if isinstance(identifier, str) and identifier.startswith('U') and len(identifier) >= 9:
        # Validate it looks like a proper Slack ID
        if identifier[1:].replace('_', '').isalnum():
            return identifier
    
    # Otherwise treat it as a username and look it up
    return get_user_id_by_username(identifier, users)


def get_user_id_by_username(username, users=None):
    """Get a user's Slack ID by username, display name, or real name (case-insensitive)."""
    if username is None or username == "":
        print(f"⚠️ Empty username provided to get_user_id_by_username")
        return None
        
    # Hardcoded special users to ensure they work even if user lookup fails
    special_users = {
        "tmcoded": "U09ADU5RJJP",  # TMCoded (fixed ID)
        "phoenix": "U026P1K51MJ",  # Phoenix (fixed ID)
        "thenobi": "U02N7UD3LKP",  # TheShinobi (alternative spelling)
        "theshinobi": "U02N7UD3LKP",  # TheShinobi (fixed ID)
        "naza": "U02DF9FQ4JL",     # Naza (fixed ID)
        "you": "U09C0AAHT0Q",      # Your user ID
    }
    
    if username.lower() in special_users:
        print(f"✅ Using hardcoded ID for special user: {username}")
        return special_users[username.lower()]
    
    if users is None:
        users = users_cache or []

    username_lower = username.lower()
    
    # First try exact match in the provided user list
    for user in users:
        if user.get("deleted"):
            continue

        profile = user.get("profile", {})
        slack_name = user.get("name", "").lower()
        display_name = profile.get("display_name", "").lower()
        real_name = user.get("real_name", "").lower()

        # Full match
        if username_lower in {slack_name, display_name, real_name}:
            return user["id"]
        
        # Partial match for common cases (first name or partial display name)
        if (display_name and username_lower in display_name.split()) or \
           (real_name and username_lower in real_name.split()) or \
           (slack_name and username_lower in slack_name.split()):
            print(f"✅ Found {username} (partial match) in user list")
            return user["id"]
    
    # If not found in the provided list, try user_cache lookup
    # This is important if we're working with a partial user list
    try:
        cached_users = list(user_cache.user_cache.values())
        for user in cached_users:
            if user.get("deleted"):
                continue
                
            profile = user.get("profile", {})
            slack_name = user.get("name", "").lower()
            display_name = profile.get("display_name", "").lower()
            real_name = user.get("real_name", "").lower()

            # Full match
            if username_lower in {slack_name, display_name, real_name}:
                print(f"✅ Found {username} in user_cache (not in main list)")
                return user["id"]
                
            # Partial match for common cases (first name or partial display name)
            if (display_name and username_lower in display_name.split()) or \
               (real_name and username_lower in real_name.split()) or \
               (slack_name and username_lower in slack_name.split()):
                print(f"✅ Found {username} (partial match) in user_cache")
                return user["id"]
    except Exception as e:
        print(f"⚠️ Error checking user_cache: {str(e)}")
    
    # Attempt to use the API as a last resort for critical users
    try:
        # Try to look up by email for leads/admins who might use email as display name
        if '@' in username_lower:
            # Use the user_cache module's function that already has retry logic
            user_data = user_cache.get_user_with_api_fallback(
                username_lower, 
                user_client=user_client if USER_TOKEN else None,
                bot_client=bot_client
            )
            if user_data and user_data.get("id"):
                print(f"✅ Found {username} via API lookup")
                return user_data.get("id")
    except Exception:
        pass  # Ignore API lookup errors

    # As a final attempt, try a fuzzy name match against known users
    try:
        def normalize(s: str) -> str:
            if not s:
                return ""
            # remove accents, punctuation and collapse whitespace
            s = unicodedata.normalize('NFKD', s)
            s = ''.join(ch for ch in s if not unicodedata.combining(ch))
            s = re.sub(r"[^\w\s]", "", s)
            s = re.sub(r"\s+", " ", s).strip().lower()
            return s

        candidates = {}
        for user in (users or []) + list(user_cache.user_cache.values()):
            if not user:
                continue
            profile = user.get("profile", {})
            names = [user.get("name", ""), profile.get("display_name", ""), user.get("real_name", "")]
            for n in names:
                key = normalize(n)
                if key:
                    candidates.setdefault(key, user.get("id"))

        if candidates:
            norm_query = normalize(username)
            # find closest match
            best = difflib.get_close_matches(norm_query, candidates.keys(), n=1, cutoff=0.78)
            if best:
                matched_key = best[0]
                matched_id = candidates.get(matched_key)
                if matched_id:
                    print(f"🔎 Fuzzy matched '{username}' -> '{matched_key}' (id={matched_id})")
                    return matched_id
    except Exception as e:
        print(f"⚠️ Error during fuzzy matching for {username}: {e}")

    # No match found after all attempts
    print(f"⚠️ Could not find user: {username}")
    return None


def get_channel_only(channel_name, verbose=True):
    """Retrieve an EXISTING channel by name without creating or unarchiving it.
    
    Returns:
        - Channel ID if found and NOT archived
        - None if not found, archived, or any error
    
    This is used by mentor sync to only add mentors to active channels.
    """
    channel_name = channel_name.lower().replace("_", "-").replace(" ", "-")
    if verbose:
        print(f"🔍 Looking for channel: {channel_name}")

    cursor = None
    for attempt in range(3):
        try:
            while True:
                resp = bot_client.conversations_list(
                    types="public_channel,private_channel",
                    limit=200,
                    cursor=cursor,
                )
                for ch in resp.get("channels", []):
                    if ch["name"] == channel_name:
                        is_archived = ch.get("is_archived", False)
                        if is_archived:
                            if verbose:
                                print(f"⏭️  Channel {channel_name} is archived - skipping")
                            return None
                        if verbose:
                            privacy = "private" if ch.get("is_private", False) else "public"
                            print(f"✅ Found active {privacy} channel: {channel_name}")
                        return ch["id"]
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            break
        except SlackApiError as e:
            if verbose:
                print(f"⚠️ Slack API error while listing channels: {e.response['error']}")
            time.sleep(2)
        except Exception as e:
            if verbose:
                print(f"⚠️ Network read error (attempt {attempt+1}/3): {e}")
            time.sleep(3)

    if verbose:
        print(f"❌ Channel not found: {channel_name}")
    return None


def get_or_create_channel(channel_name, is_private=True):
    """Create or retrieve a channel by name."""
    channel_name = channel_name.lower().replace("_", "-").replace(" ", "-")
    print(f"\n🔍 Checking/creating channel: {channel_name} (private={is_private})")

    # Step 1: First try to find the channel using bot token
    cursor = None
    channel_id = None
    channel_is_archived = False
    
    for attempt in range(3):
        try:
            while True:
                resp = bot_client.conversations_list(
                    types="public_channel,private_channel",
                    limit=200,
                    cursor=cursor,
                )
                for ch in resp.get("channels", []):
                    if ch["name"] == channel_name:
                        privacy = "private" if ch.get("is_private", False) else "public"
                        print(f"ℹ️ Found existing {privacy} channel: {channel_name}")
                        channel_id = ch["id"]
                        channel_is_archived = ch.get("is_archived", False)
                        if channel_is_archived:
                            print(f"⚠️ Channel {channel_name} is archived, attempting to unarchive...")
                            try:
                                # Try with user token first (higher permissions)
                                user_client.conversations_unarchive(channel=channel_id)
                                print(f"✅ Successfully unarchived channel: {channel_name}")
                                channel_is_archived = False
                            except Exception as e:
                                print(f"❌ Failed to unarchive with user token: {e}")
                                try:
                                    # Fallback to bot token
                                    bot_client.conversations_unarchive(channel=channel_id)
                                    print(f"✅ Successfully unarchived channel: {channel_name}")
                                    channel_is_archived = False
                                except Exception as e2:
                                    print(f"❌ Failed to unarchive with bot token: {e2}")
                        return channel_id
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            break
        except SlackApiError as e:
            print(f"⚠️ Slack API error while listing channels: {e.response['error']}")
            time.sleep(2)
        except Exception as e:
            print(f"⚠️ Network read error (attempt {attempt+1}/3): {e}")
            time.sleep(3)

    # Step 2: Create the channel - with private setting first
    print(f"🔄 Channel '{channel_name}' not found. Attempting to create as private...")
    
    # First attempt: Try user token with private=True (using the deprecated parameter that works)
    try:
        # Use is_private=True parameter - this is what actually works based on testing
        resp = user_client.conversations_create(name=channel_name, is_private=True)
        is_private = resp["channel"]["is_private"]
        if is_private:
            print(f"✅ Created new private channel: {channel_name}")
        else:
            print(f"⚠️ Channel created but appears to be public: {channel_name}")
        
        # Add bot to the channel so it can invite users
        try:
            bot_id = bot_client.auth_test()["user_id"]
            user_client.conversations_invite(channel=resp["channel"]["id"], users=[bot_id])
            print(f"✅ Added bot to channel: {channel_name}")
        except Exception as e:
            print(f"⚠️ Could not add bot to channel: {str(e)}")
            
        return resp["channel"]["id"]
    except SlackApiError as e:
        user_err = e.response.get("error", "")
        print(f"⚠️ User token couldn't create private channel: {user_err}")
    
    # Ask user if they want to create public channel instead
    print("\n⚠️⚠️⚠️ IMPORTANT ⚠️⚠️⚠️")
    print(f"Failed to create private channel '{channel_name}'.")
    print(f"Do you want to create it as a public channel instead?")
    print("You can manually convert it to private afterwards in Slack settings.")
    print("⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️\n")
    
    confirm = input(f"Create public channel '{channel_name}'? (yes/no): ")
    if confirm.lower() not in ["yes", "y"]:
        print("❌ Channel creation cancelled by user")
        return None
    
    # Try with user token for public channel
    try:
        resp = user_client.conversations_create(name=channel_name, is_private=False)
        print(f"✅ Created new public channel: {channel_name}")
        
        # Add bot to the channel so it can invite users
        try:
            bot_id = bot_client.auth_test()["user_id"]
            user_client.conversations_invite(channel=resp["channel"]["id"], users=[bot_id])
            print(f"✅ Added bot to channel: {channel_name}")
        except Exception as e:
            print(f"⚠️ Could not add bot to channel: {str(e)}")
            
        return resp["channel"]["id"]
    except SlackApiError as e:
        user_err = e.response.get("error", "")
        print(f"❌ User token couldn't create public channel: {user_err}")
        return None


def add_users_to_channel(channel_id, user_ids, channel_name, batch_size=10, max_retries=3):
    """Add users using bot token with batch processing and retry logic.
    
    Args:
        channel_id: ID of the channel to add users to
        user_ids: List of user IDs to add (can include "@username" for bots without IDs)
        channel_name: Name of channel for logging purposes
        batch_size: Number of users to add in each API call (smaller is more reliable)
        max_retries: Maximum number of retry attempts on failure
    """
    # Separate regular user IDs from username strings (marked with @)
    valid_user_ids = []
    username_invites = []  # Bots that need username-based invitation
    
    for uid in user_ids:
        if not uid:
            continue
        if isinstance(uid, str) and uid.startswith("@"):
            # This is a username, not a user ID
            username_invites.append(uid[1:])  # Remove the @ prefix
        else:
            valid_user_ids.append(uid)
    
    if not valid_user_ids and not username_invites:
        print(f"⚠️ No valid users to add to {channel_name}")
        return []
    
    # Make sure TMCoded is at the front of the list to be added first
    tmcoded_id = next((uid for uid in valid_user_ids if uid == "TMCoded"), None)
    if tmcoded_id:
        valid_user_ids.remove(tmcoded_id)
        valid_user_ids.insert(0, tmcoded_id)
    
    # Make sure bot is in the channel before adding users
    bot_id = bot_client.auth_test()["user_id"]
    
    try:
        # First check if bot is already in channel
        is_bot_in_channel = False
        try:
            bot_client.conversations_info(channel=channel_id)
            is_bot_in_channel = True
        except SlackApiError:
            print(f"   ⚠️ Bot not in channel {channel_name} - trying to add it...")
        
        if not is_bot_in_channel:
            # Try with user token (which has higher permissions)
            try:
                user_client.conversations_invite(channel=channel_id, users=[bot_id])
                print(f"   ✅ Added bot to channel: {channel_name}")
            except SlackApiError as e:
                error_message = str(e)
                if "is_archived" in error_message:
                    # Try to unarchive the channel first with user token
                    try:
                        user_client.conversations_unarchive(channel=channel_id)
                        print(f"   ✅ Unarchived channel {channel_name}")
                        time.sleep(1)
                        # Try adding bot again
                        user_client.conversations_invite(channel=channel_id, users=[bot_id])
                        print(f"   ✅ Added bot to channel: {channel_name}")
                    except Exception as unarch_error:
                        print(f"   ❌ Could not unarchive channel: {str(unarch_error)}")
                else:
                    print(f"   ❌ Could not add bot to channel {channel_name}: {error_message}")
    except Exception as e:
        print(f"   ❌ Error checking/adding bot: {str(e)}")
    
    # First, check who is already in the channel to avoid unnecessary API calls
    already_in_channel = set()
    try:
        cursor = None
        members_found = 0
        
        print(f"   🔍 Checking existing members in {channel_name}...")
        
        # Use pagination to get channel members
        for attempt in range(3):  # Limited retries for channel members
            try:
                while True:
                    resp = bot_client.conversations_members(channel=channel_id, limit=100, cursor=cursor)
                    members = resp.get("members", [])
                    already_in_channel.update(members)
                    members_found += len(members)
                    
                    cursor = resp.get("response_metadata", {}).get("next_cursor")
                    if not cursor:
                        break
                    time.sleep(0.5)  # Small delay between pagination calls
                
                print(f"   ℹ️ Found {members_found} existing members in {channel_name}")
                break  # Success, exit retry loop
                
            except Exception as e:
                if attempt < 2:  # We have 3 attempts total (0,1,2)
                    wait_time = (attempt + 1) * 2
                    error_msg = str(e)
                    if len(error_msg) > 100:
                        error_msg = error_msg[:97] + "..."
                    print(f"   ⚠️ Error checking members (attempt {attempt+1}/3): {error_msg}")
                    time.sleep(wait_time)
                else:
                    print(f"   ⚠️ Failed to check channel members after 3 attempts")
    
    except Exception as e:
        print(f"   ⚠️ Could not check existing members: {str(e)}")
    
    # Filter out users already in the channel
    users_to_add = []
    already_added = []
    
    for uid in valid_user_ids:
        if uid in already_in_channel:
            already_added.append(uid)
        else:
            users_to_add.append(uid)
    
    if already_added:
        print(f"   ℹ️ {len(already_added)} users already in {channel_name}")
    
    if not users_to_add:
        print(f"   ✅ All users are already in {channel_name}")
        return []
        
    print(f"   ➕ Adding {len(users_to_add)} users to {channel_name} (in batches of {batch_size})")
        
    # Split users into batches to avoid API limits - use smaller batch size for reliability
    batches = [users_to_add[i:i+batch_size] for i in range(0, len(users_to_add), batch_size)]
    added_count = 0
    failed_count = 0
    actually_added: List[str] = []
    
    for batch_num, batch in enumerate(batches, 1):
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # Make sure we're passing the users as a comma-separated string, not an array
                users_param = ",".join(batch)
                bot_client.conversations_invite(channel=channel_id, users=users_param)
                added_count += len(batch)
                actually_added.extend(batch)
                print(f"   ➕ Added batch {batch_num}/{len(batches)}: {len(batch)} users to {channel_name}")
                
                # Short delay between batches to avoid rate limiting
                if batch_num < len(batches):
                    time.sleep(2.0)  # Increased delay for reliability
                break
                
            except SlackApiError as e:
                err = e.response["error"]
                if err == "already_in_channel":
                    print(f"   ℹ️ Users already in {channel_name}")
                    break
                elif "channel_not_found" in err:
                    print(f"   ⚠️ Channel not accessible: {channel_name}")
                    return
                elif "not_in_channel" in err:
                    print(f"   ⚠️ Bot not in channel {channel_name} - trying to add it...")
                    # Try to add the bot to the channel using the user token
                    try:
                        bot_id = bot_client.auth_test()["user_id"]
                        user_client.conversations_invite(channel=channel_id, users=[bot_id])
                        print(f"   ✅ Added bot to channel {channel_name}, retrying...")
                        # Now try again to add users
                        users_param = ",".join(batch)
                        bot_client.conversations_invite(channel=channel_id, users=users_param)
                        added_count += len(batch)
                        actually_added.extend(batch)
                        print(f"   ➕ Added batch {batch_num}/{len(batches)}: {len(batch)} users to {channel_name}")
                        continue
                    except Exception as e:
                        print(f"   ❌ Could not add bot to channel {channel_name}: {str(e)}")
                        return
                elif "is_archived" in err:
                    print(f"   ⚠️ Channel {channel_name} is archived - trying to unarchive it...")
                    try:
                        # Try with user token first
                        user_client.conversations_unarchive(channel=channel_id)
                        print(f"   ✅ Unarchived channel {channel_name}, retrying...")
                        # Try again to add users
                        users_param = ",".join(batch)
                        bot_client.conversations_invite(channel=channel_id, users=users_param)
                        added_count += len(batch)
                        actually_added.extend(batch)
                        print(f"   ➕ Added batch {batch_num}/{len(batches)}: {len(batch)} users to {channel_name}")
                        continue
                    except Exception as e:
                        print(f"   ❌ Could not unarchive channel {channel_name}: {str(e)}")
                        return
                else:
                    # Check if it's a user_not_found error (non-retriable)
                    if "user_not_found" in err:
                        print(f"   ⚠️ One or more users in batch {batch_num} not found in Slack workspace - skipping this batch")
                        failed_count += len(batch)
                        break  # Don't retry, user doesn't exist
                    # Try with user token if bot token fails
                    try:
                        print(f"   ⚠️ Bot failed to add users - trying with user token...")
                        users_param = ",".join(batch)
                        user_client.conversations_invite(channel=channel_id, users=users_param)
                        added_count += len(batch)
                        actually_added.extend(batch)
                        print(f"   ➕ Added batch {batch_num}/{len(batches)} with user token: {len(batch)} users to {channel_name}")
                        break  # Success with user token, no need to retry
                    except Exception as e2:
                        # Check again for user_not_found in the second attempt
                        e2_str = str(e2)
                        if "user_not_found" in e2_str:
                            print(f"   ⚠️ One or more users in batch {batch_num} not found in Slack (with user token) - skipping")
                            failed_count += len(batch)
                            break
                        # Both tokens failed, retry with bot token
                        retry_count += 1
                        if retry_count <= max_retries:
                            wait_time = retry_count * 3  # Increased wait time
                            print(f"   ⚠️ Failed to add batch {batch_num} (retry {retry_count}/{max_retries}, waiting {wait_time}s): {err}")
                            time.sleep(wait_time)
                        else:
                            print(f"   ❌ Failed to add batch {batch_num} after {max_retries} retries: {err}")
                            failed_count += len(batch)
                            break
                        
            except Exception as e:
                retry_count += 1
                if retry_count <= max_retries:
                    wait_time = retry_count * 3  # Increased wait time
                    error_msg = str(e)
                    if len(error_msg) > 100:
                        error_msg = error_msg[:97] + "..."
                    print(f"   ⚠️ Network error adding batch {batch_num} (retry {retry_count}/{max_retries}, waiting {wait_time}s): {error_msg}")
                    time.sleep(wait_time)
                else:
                    print(f"   ❌ Failed to add batch {batch_num} after {max_retries} retries")
                    failed_count += len(batch)
                    break
    
    if failed_count > 0:
        print(f"   ⚠️ Added {added_count}/{len(users_to_add)} users to {channel_name} ({failed_count} failed)")
    else:
        print(f"   ✅ Successfully added {added_count}/{len(users_to_add)} users to {channel_name}")
    
    # Now handle username-based invitations for bots (like Thanos)
    if username_invites:
        print(f"\n   🤖 Adding bots by username to {channel_name}...")
        for username in username_invites:
            try:
                # Try to find the bot by display name using the users list
                bot_user = None
                for user in (users_cache or []) + list(user_cache.user_cache.values()):
                    if not user:
                        continue
                    profile = user.get("profile", {})
                    if profile.get("display_name", "").lower() == username.lower() or user.get("name", "").lower() == username.lower():
                        bot_user = user
                        break
                
                if bot_user:
                    bot_id = bot_user.get("id")
                    try:
                        users_param = bot_id
                        bot_client.conversations_invite(channel=channel_id, users=users_param)
                        actually_added.append(bot_id)
                        print(f"   ✅ Added bot '{username}' ({bot_id}) to {channel_name}")
                    except Exception as e:
                        print(f"   ⚠️ Failed to add bot '{username}': {str(e)}")
                else:
                    print(f"   ⚠️ Could not find bot by username '{username}' in user list")
            except Exception as e:
                print(f"   ⚠️ Error processing bot '{username}': {str(e)}")

    return actually_added


def _notify_new_members(channel_id: str, user_ids: List[str], channel_name: str, context: Optional[str] = None):
    """Post a minimal message that only mentions the newly added users.

    Args:
        channel_id: Slack channel ID
        user_ids: list of user IDs that were actually added
        channel_name: friendly name for logs
        context: optional extra text, e.g., the track name
    """
    if not user_ids:
        return
    try:
        # Filter out non-user-id values (keep only proper Slack IDs)
        valid_ids = [uid for uid in user_ids if uid and isinstance(uid, str) and (uid.startswith('U') or uid.startswith('B'))]
        
        if not valid_ids:
            return
        
        # Just mention the users, no extra message
        mention_text = " ".join([f"<@{uid}>" for uid in valid_ids])
        bot_client.chat_postMessage(channel=channel_id, text=mention_text)
        print(f"   💬 Posted mention in {channel_name} for {len(valid_ids)} user(s)")
    except Exception as e:
        print(f"   ⚠️ Could not post mention in {channel_name}: {e}")


def setup_google_sheets():
    """Set up Google Sheets API connection and return the latest mentor selections"""
    global WORKSHEET_NAME
    
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    print(f"DEBUG: GOOGLE_CREDENTIALS_FILE = {GOOGLE_CREDENTIALS_FILE}")
    print(f"DEBUG: File exists = {os.path.exists(GOOGLE_CREDENTIALS_FILE) if GOOGLE_CREDENTIALS_FILE else 'N/A'}")
    
    try:
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            GOOGLE_CREDENTIALS_FILE, scope
        )
        gc = gspread.authorize(credentials)
        
        # Try to open existing spreadsheet
        try:
            spreadsheet = gc.open(SPREADSHEET_NAME)
            print(f"✅ Opened spreadsheet: {SPREADSHEET_NAME}")
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"❌ Spreadsheet not found: {SPREADSHEET_NAME}")
            return None, None
        
        # Get all worksheets
        all_worksheets = spreadsheet.worksheets()

        # Find the static "Mentors" worksheet (NOT the dated ones)
        worksheet = None
        for ws in all_worksheets:
            if ws.title == "Mentors":
                worksheet = ws
                break
        
        if not worksheet:
            print("❌ Mentor worksheet 'Mentors' not found")
            return None, None

        WORKSHEET_NAME = worksheet.title
        print(f"✅ Using worksheet: {WORKSHEET_NAME}")
    
        return spreadsheet, worksheet
    except Exception as e:
        print(f"❌ Error setting up Google Sheets: {str(e)}")
        return None, None

def get_mentor_selections():
    """Get mentor track selections from the Google Sheet"""
    spreadsheet, worksheet = setup_google_sheets()
    
    if not worksheet:
        print("❌ Could not access worksheet")
        return []
    
    try:
        # Get all records
        records = worksheet.get_all_records()
        
        if not records:
            print("❌ No records found in the worksheet")
            return []
        
        print(f"✅ Found {len(records)} mentor records")
        
        # Get column headers to understand the format
        headers = worksheet.row_values(1)
        print(f"DEBUG: Column headers in sheet: {', '.join(headers)}")
        
        # Process records to extract Slack IDs and track selections
        mentors = []
        for record in records:
            # Extract data from record - different sheets might have different column names
            timestamp = record.get("Timestamp", "").strip()
            user_id = record.get("Slack ID", "").strip()
            display_name = record.get("Display Name", record.get("Name", "")).strip()
            selected_tracks_str = record.get("Selected Tracks", "").strip()
            
            # Skip rows with missing timestamp (incomplete/malformed submissions)
            if not timestamp:
                continue
            
            print(f"DEBUG: Processing record: {display_name} | {user_id} | {selected_tracks_str}")
            
            if (display_name or user_id) and selected_tracks_str:
                selected_tracks = [track.strip() for track in selected_tracks_str.split(",")]
                
                # If user_id doesn't exist but we have display_name, try to find the user
                if not user_id and display_name:
                    user_id = get_user_id_by_username(display_name, fetch_all_users())
                    if user_id:
                        print(f"✅ Found user ID for {display_name}: {user_id}")
                
                if user_id:
                    mentors.append({
                        "user_id": user_id,
                        "tracks": selected_tracks,
                        "display_name": display_name
                    })
                    print(f"✅ Valid mentor: {display_name}, Tracks: {selected_tracks_str}")
        
        print(f"✅ Processed {len(mentors)} valid mentor records")
        return mentors
    except Exception as e:
        print(f"❌ Error getting mentor selections: {str(e)}")
        return []

def create_stage_channels(stage_number):
    """Create or populate all stage and track channels."""
    stage_name = f"stage-{stage_number}"
    print(f"🚀 Starting {stage_name} channel creation...\n")

    # Check if preload_user_cache.py was run first
    if not os.path.exists("user_cache.json") and not os.path.exists("all_users.json"):
        print("⚠️ WARNING: No user cache files found!")
        print("⚠️ For best results, run 'python preload_user_cache.py' first")
        print("⚠️ Continuing anyway, but expect potential issues with user lookups...\n")

    try:
        all_users = fetch_all_users(max_retries=3, use_cache_file=True)
        if not all_users:
            print("⚠️ Warning: No users were loaded! Using minimal information for lead lookups.")
            # Continue with empty user list - we'll create basic user profiles when needed
            all_users = []
    except Exception as e:
        print(f"❌ Error fetching users: {e}")
        print("⚠️ Continuing with minimal user information...")
        all_users = []
        
    all_leads = set(user for leads in TRACKS.values() for user in leads)

    # Main stage channel
    stage_channel_id = get_or_create_channel(stage_name)  # is_private=True by default
    if not stage_channel_id:
        print(f"❌ Could not access or create {stage_name}")
        return
    
    # Dictionary to store all created channel IDs
    created_channels = {
        "main": stage_channel_id
    }

    # Collect all lead IDs and print them for debugging
    lead_ids = []
    print(f"\n🔍 Looking up user IDs for {len(all_leads)} track leads...")
    missing_leads = []
    for identifier in all_leads:
        user_id = get_lead_id(identifier, all_users)
        if user_id:
            lead_ids.append(user_id)
            print(f"   ✅ Resolved lead '{identifier}' -> {user_id}")
        else:
            print(f"   ❌ Could not resolve lead identifier: {identifier}")
            missing_leads.append(identifier)
    
    if missing_leads:
        print('\n⚠️ Summary: Could not find the following lead identifiers:')
        for m in sorted(set(missing_leads)):
            print(f"   - {m}")
        print("⚠️ Consider updating TRACKS with correct Slack IDs or usernames.\n")
    
    print(f"\n🔍 Adding {len(lead_ids)} track leads to main {stage_name} channel...")
    add_users_to_channel(stage_channel_id, lead_ids, stage_name)

    # Track-specific channels
    print(f"\n📌 Creating track-specific {stage_name} channels...\n")
    created = 0

    for track, leads in TRACKS.items():
        track_channel = f"{stage_name}-{track}"
        channel_id = get_or_create_channel(track_channel)  # is_private=True by default
        if not channel_id:
            print(f"⚠️ Skipping {track_channel} (cannot access)\n")
            continue
            
        # Store channel ID for later use
        created_channels[track] = channel_id

        # Get and display track lead IDs for debugging
        track_ids = []
        print(f"\n🔍 Looking up user IDs for {len(leads)} '{track}' track leads...")
        missing = []
        for identifier in leads:
            user_id = get_lead_id(identifier, all_users)
            if user_id:
                track_ids.append(user_id)
                print(f"   ✅ Resolved '{identifier}' -> {user_id}")
            else:
                print(f"   ❌ Could not resolve: {identifier}")
                missing.append(identifier)
        
        if missing:
            print(f"   ⚠️ Missing track leads for '{track}': {', '.join(missing)}")
        
        print(f"🔍 Adding {len(track_ids)} track leads to {track_channel}...")
        add_users_to_channel(channel_id, track_ids, track_channel)
        created += 1
        time.sleep(0.3)

    print("\n🎯 Summary:")
    print(f"   ✅ Created/Found: {created + 1} channels")
    print(f"   👥 Total unique leads added: {len(all_leads)}")
    
    # Add mentors from Google Sheet to the appropriate channels
    add_mentors_to_stage_channels(stage_number, created_channels)


def add_mentors_to_stage_channels(stage_number, channels):
    """Add mentors from Google Sheet to stage channels based on their track selections"""
    stage_name = f"stage-{stage_number}"
    print(f"\n🚀 Adding mentors to {stage_name} channels based on Google Sheet selections...\n")
    
    # Get mentors from Google Sheet
    mentors = get_mentor_selections()
    
    if not mentors:
        print("❌ No mentor records found in Google Sheet")
        return
    
    # Initialize user cache
    user_cache.load_user_cache()
    if os.path.exists("all_users.json"):
        user_cache.preload_from_all_users("all_users.json")
        print(f"✅ Preloaded users from all_users.json")
    
    # Always add specific users to all channels (admins/oversight)
    your_user_id = "U09C0AAHT0Q"        # Your user ID
    additional_user_id = "U09LDCKAFJ6"  # Additional user to add to all channels
    additional_user_id_2 = "U09B9SJPLFK"
    additional_user_id_3 = "U09BBMQG3NG"  # Additional user to add to all channels
    additional_user_id_4 = "U0AEQ5WLNSE"  # Additional user to add to all channels
    additional_user_id_5 = "U0AFJEN4HPA"  # Additional user to add to all channels
    additional_user_id_6 = "U0AE8NEAD55"  # Additional user to add to all channels
    
    # Thanos bot user ID (HNG management bot)
    thanos_id = "U0APSR995F0"
    print(f"✅ Using Thanos bot ID: {thanos_id}")
    
    # Add all mentors to the main stage channel first
    main_channel_id = channels.get("main")
    if main_channel_id:
        print(f"📌 Adding all mentors to main {stage_name} channel...")
        mentor_ids = [mentor["user_id"] for mentor in mentors]

        # Add your user ID if not already in the list
        if your_user_id not in mentor_ids:
            mentor_ids.append(your_user_id)
            print(f"📎 Adding you (U09C0AAHT0Q) to all channels")

        # Add additional user ID if not already in the list
        if additional_user_id not in mentor_ids:
            mentor_ids.append(additional_user_id)
            print(f"📎 Adding additional user (U09LDCKAFJ6) to all channels")

        # Add second additional user ID if not already in the list
        if additional_user_id_2 not in mentor_ids:
            mentor_ids.append(additional_user_id_2)
            print(f"📎 Adding additional user (U09B9SJPLFK) to all channels")

        if additional_user_id_3 not in mentor_ids:
            mentor_ids.append(additional_user_id_3)
            print(f"📎 Adding additional user (U09BBMQG3NG) to all channels")

        if additional_user_id_4 not in mentor_ids:
            mentor_ids.append(additional_user_id_4)
            print(f"📎 Adding additional user (U0AEQ5WLNSE) to all channels")

        if additional_user_id_5 not in mentor_ids:
            mentor_ids.append(additional_user_id_5)
            print(f"📎 Adding additional user (U0AFJEN4HPA) to all channels")

        if additional_user_id_6 not in mentor_ids:
            mentor_ids.append(additional_user_id_6)
            print(f"📎 Adding additional user (U0AE8NEAD55) to all channels")
        
        # Add Thanos bot if we have the ID
        if thanos_id and thanos_id not in mentor_ids:
            mentor_ids.append(thanos_id)
            print(f"🤖 Adding Thanos bot to all channels")

        added_main = add_users_to_channel(main_channel_id, mentor_ids, stage_name)
        # Mention all successfully added members
        _notify_new_members(main_channel_id, added_main, stage_name, context="main channel")
    else:
        print(f"❌ Main channel ID for {stage_name} not found")
    
    # Add mentors to their specific track channels
    print(f"\n📌 Adding mentors to track-specific {stage_name} channels...\n")
    
    # Track statistics
    mentors_added = 0
    total_additions = 0
    # Collect mentions to post one message per channel (avoid spam)
    track_added_map: Dict[str, List[str]] = {}
    track_channel_name_map: Dict[str, str] = {}
    
    for mentor in mentors:
        user_id = mentor["user_id"]
        selected_tracks = mentor["tracks"]
        display_name = mentor["display_name"]
        
        print(f"👤 Processing mentor: {display_name} ({user_id})")
        print(f"   Selected tracks: {', '.join(selected_tracks)}")
        
        mentor_added_to_tracks = 0
        
        for track in selected_tracks:
            track_channel_id = channels.get(track)
            if not track_channel_id:
                print(f"   ❌ No channel ID found for track: {track}")
                continue
                
            try:
                added_ids = add_users_to_channel(track_channel_id, [user_id], f"{stage_name}-{track}")
                if added_ids:
                    track_added_map.setdefault(track_channel_id, []).extend(added_ids)
                    track_channel_name_map[track_channel_id] = f"{stage_name}-{track}"
                mentor_added_to_tracks += 1
                total_additions += 1
            except Exception as e:
                print(f"   ❌ Error adding {user_id} to {track} channel: {str(e)}")
        
        if mentor_added_to_tracks > 0:
            mentors_added += 1
            
    # Post one mention per track channel for all newly added mentors
    for ch_id, ids in track_added_map.items():
        ch_name = track_channel_name_map.get(ch_id, stage_name)
        _notify_new_members(ch_id, ids, ch_name)

    # Add your user ID and additional users to all track channels
    print(f"\n📌 Adding admin users to all track channels...")
    admin_users = [
        (your_user_id, "U09C0AAHT0Q (You)"),
        (additional_user_id, "U09LDCKAFJ6"),
        (additional_user_id_2, "U09B9SJPLFK"),
        (additional_user_id_3, "U09BBMQG3NG"),
        (additional_user_id_4, "U0AEQ5WLNSE"),
        (additional_user_id_5, "U0AFJEN4HPA"),
        (additional_user_id_6, "U0AE8NEAD55"),
    ]
    
    # Add Thanos bot to admin users if resolved
    if thanos_id:
        admin_users.append((thanos_id, "Thanos (Bot)"))
    
    admin_mentions_map: Dict[str, List[str]] = {}
    
    for track, channel_id in channels.items():
        if track != "main":
            for admin_id, admin_label in admin_users:
                added_ids = add_users_to_channel(channel_id, [admin_id], f"{stage_name}-{track}")
                if added_ids:
                    admin_mentions_map.setdefault(channel_id, []).extend(added_ids)
                    print(f"   ✅ Added admin user ({admin_label}) to {track} channel")
    
    # Post mentions for newly added admin users in each track channel
    for ch_id, ids in admin_mentions_map.items():
        ch_name = None
        for track, c_id in channels.items():
            if c_id == ch_id and track != "main":
                ch_name = f"{stage_name}-{track}"
                break
        if ch_name:
            _notify_new_members(ch_id, ids, ch_name)
    
    print(f"\n🎯 Mentor Addition Summary:")
    print(f"   ✅ Added {mentors_added} mentors to their selected track channels")
    print(f"   ✅ Made {total_additions} total channel additions")
    print(f"   ✅ Each mentor was added to the main {stage_name} channel AND to their selected track channels")
    admin_summary = "7 admin users (U09C0AAHT0Q, U09LDCKAFJ6, U09B9SJPLFK, U09BBMQG3NG, U0AEQ5WLNSE, U0AFJEN4HPA, U0AE8NEAD55)"
    if thanos_id:
        admin_summary += " + Thanos (Bot)"
    print(f"   👑 Added {admin_summary} to all channels")
    print(f"   📢 All newly added members were mentioned in their respective channels")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python create_stage_channels.py <stage_number>")
        sys.exit(1)

    try:
        stage = int(sys.argv[1])
        create_stage_channels(stage)
    except ValueError:
        print("❌ Stage number must be an integer")
