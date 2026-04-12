"""
User cache for Slack user information
This helps avoid repeated API calls for the same users
and improves performance by keeping user data locally
"""

import os
import json
import time
from datetime import datetime

# Path to cache file
USER_CACHE_FILE = "user_cache.json"

# Global cache dictionary
user_cache = {}

# Cache stats
cache_hits = 0
cache_misses = 0

def load_user_cache():
    """Load user cache from file if it exists"""
    global user_cache
    
    if os.path.exists(USER_CACHE_FILE):
        try:
            with open(USER_CACHE_FILE, 'r', encoding='utf-8') as f:
                user_cache = json.load(f)
            
            user_count = len(user_cache)
            print(f"✅ Loaded cache with {user_count} users from {USER_CACHE_FILE}")
            return True
        except Exception as e:
            print(f"⚠️ Error loading user cache: {e}")
            user_cache = {}
    
    return False

def save_user_cache():
    """Save user cache to file"""
    try:
        with open(USER_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_cache, f, indent=2)
        
        user_count = len(user_cache)
        print(f"✅ Saved cache with {user_count} users to {USER_CACHE_FILE}")
        return True
    except Exception as e:
        print(f"⚠️ Error saving user cache: {e}")
        return False

def get_cached_user(user_id):
    """Get user info from cache if available"""
    global cache_hits, cache_misses
    
    if user_id in user_cache:
        cache_hits += 1
        return user_cache.get(user_id)
    
    cache_misses += 1
    return None

def add_to_cache(user_id, user_data):
    """Add user info to cache"""
    if not user_id or not user_data:
        return False
        
    user_cache[user_id] = user_data
    # We won't save the cache on every add to avoid performance issues
    # It should be saved at the end of processing
    return True

def get_user_with_api_fallback(user_id, user_client=None, bot_client=None):
    """
    Get user info from cache first, then try API if needed
    
    Args:
        user_id: Slack user ID
        user_client: Optional Slack WebClient with user token
        bot_client: Optional Slack WebClient with bot token
    
    Returns:
        User data dict
    """
    # Import socket at the beginning for timeout handling
    import socket
    
    # First check cache
    cached_user = get_cached_user(user_id)
    if cached_user:
        return cached_user
    
    # Create minimal user info as fallback
    minimal_info = {
        "id": user_id,
        "name": f"user-{user_id[-5:]}",
        "real_name": f"User {user_id[-5:]}",
        "profile": {
            "display_name": f"User-{user_id[-5:]}",
            "email": "",
            "phone": ""
        }
    }
    
    # If no clients provided, we can't make API calls
    if not user_client and not bot_client:
        add_to_cache(user_id, minimal_info)
        return minimal_info
    
    # Try API calls with exponential backoff
    max_retries = 3
    retry_delay = 1
    
    # Try with bot token first if available (it should have the users:read scope)
    if bot_client:
        for attempt in range(max_retries):
            try:
                # Set a reasonable timeout
                try:
                    socket.setdefaulttimeout(7)  # 7 second timeout
                except Exception:
                    pass  # Ignore if socket setting fails
                    
                # Make the API call with a timeout
                user_info = bot_client.users_info(user=user_id, timeout=5)
                user_data = user_info.get("user", {})
                
                # Only cache valid user data
                if user_data and "id" in user_data:
                    add_to_cache(user_id, user_data)
                    return user_data
                else:
                    print(f"⚠️ Got incomplete data for user {user_id}")
                    
            except socket.timeout:
                print(f"⏱️ Timeout while fetching user {user_id} - retrying...")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
            except Exception as e:
                # Limit error message length
                error_msg = str(e)
                if len(error_msg) > 100:
                    error_msg = error_msg[:97] + "..."
                print(f"⚠️ Bot token API error for {user_id}: {error_msg}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
    
    # Only try with user token if bot token failed or isn't available
    if user_client:
        retry_delay = 1  # Reset delay for user token attempts
        for attempt in range(max_retries):
            try:
                # Set a reasonable timeout
                try:
                    socket.setdefaulttimeout(7)  # 7 second timeout
                except Exception:
                    pass  # Ignore if socket setting fails
                    
                # Make the API call with a timeout
                user_info = user_client.users_info(user=user_id, timeout=5)
                user_data = user_info.get("user", {})
                
                # Only cache valid user data
                if user_data and "id" in user_data:
                    add_to_cache(user_id, user_data)
                    return user_data
                else:
                    print(f"⚠️ Got incomplete data for user {user_id}")
                    
            except socket.timeout:
                print(f"⏱️ Timeout while fetching user {user_id} - retrying...")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
            except Exception as e:
                # Don't print missing scope errors repeatedly since we know about this issue
                error_msg = str(e)
                if 'missing_scope' not in error_msg:
                    # Limit error message length
                    if len(error_msg) > 100:
                        error_msg = error_msg[:97] + "..."
                    print(f"⚠️ User token API error for {user_id}: {error_msg}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
    
    # All attempts failed, use minimal info
    add_to_cache(user_id, minimal_info)
    return minimal_info

def preload_from_all_users(filename="all_users.json"):
    """Preload user cache from all_users.json file"""
    global user_cache
    
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                all_users = json.load(f)
            
            count = 0
            for user in all_users:
                user_id = user.get("id")
                if user_id:
                    user_cache[user_id] = user
                    count += 1
            
            print(f"✅ Preloaded {count} users from {filename}")
            
            # Save the updated cache
            save_user_cache()
            return count
        else:
            print(f"⚠️ File not found: {filename}")
            return 0
    except Exception as e:
        print(f"⚠️ Error preloading users: {e}")
        return 0

def get_cache_stats():
    """Get statistics about the cache usage"""
    total_requests = cache_hits + cache_misses
    hit_rate = 0
    if total_requests > 0:
        hit_rate = (cache_hits / total_requests) * 100
        
    return {
        "total_entries": len(user_cache),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "hit_rate": hit_rate
    }

def print_cache_stats():
    """Print statistics about the cache usage"""
    stats = get_cache_stats()
    print("\n" + "=" * 50)
    print("📊 USER CACHE STATISTICS")
    print("=" * 50)
    print(f"📁 Total entries: {stats['total_entries']}")
    print(f"✅ Cache hits: {stats['cache_hits']}")
    print(f"❌ Cache misses: {stats['cache_misses']}")
    print(f"📈 Hit rate: {stats['hit_rate']:.1f}%")
    print("=" * 50)
    
def reset_cache_stats():
    """Reset the cache hit/miss statistics"""
    global cache_hits, cache_misses
    cache_hits = 0
    cache_misses = 0

if __name__ == "__main__":
    # Test loading cache
    load_user_cache()
    print(f"Cache has {len(user_cache)} entries")
    
    # Test preloading from all_users.json if available
    if os.path.exists("all_users.json"):
        print("Preloading users from all_users.json...")
        preload_from_all_users()
    
    # Print cache stats
    print_cache_stats()
    
    # Test saving cache
    save_user_cache()