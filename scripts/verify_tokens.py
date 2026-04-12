#!/usr/bin/env python3
"""
Script to verify Slack API tokens are working correctly.
Tests bot token and user token connectivity and scopes.
"""
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

load_dotenv()

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")

def test_token(token, token_type):
    """Test a Slack API token."""
    print(f"\n{'='*60}")
    print(f"Testing {token_type}")
    print(f"{'='*60}")
    
    if not token:
        print(f"❌ No token found for {token_type}")
        return False
    
    client = WebClient(token=token)
    
    try:
        # Test 1: auth.test
        print(f"\n1️⃣ Testing auth.test()...")
        response = client.auth_test()
        
        user_id = response["user_id"]
        user_name = response["user"]
        team_id = response["team_id"]
        team_name = response["team_name"]
        
        print(f"   ✅ Connected successfully!")
        print(f"   📍 Team: {team_name} (ID: {team_id})")
        print(f"   👤 User: @{user_name} (ID: {user_id})")
        
        # Test 2: Get scopes
        print(f"\n2️⃣ Checking available scopes...")
        scopes = response.get("scope", "").split(",") if response.get("scope") else []
        
        if scopes:
            print(f"   ✅ Available scopes ({len(scopes)}):")
            for scope in sorted(scopes):
                print(f"      • {scope.strip()}")
        else:
            print(f"   ⚠️ Could not retrieve scopes")
        
        # Test 3: Try conversations.list (channels:read scope)
        print(f"\n3️⃣ Testing conversations.list()...")
        channels_resp = client.conversations_list(limit=10)
        channel_count = len(channels_resp.get("channels", []))
        print(f"   ✅ Found {channel_count} channels")
        
        if channel_count > 0:
            sample = channels_resp["channels"][0]
            print(f"   📌 Sample: #{sample['name']} (private: {sample.get('is_private', False)})")
        
        # Test 4: Try users.list (users:read scope)
        print(f"\n4️⃣ Testing users.list()...")
        users_resp = client.users_list(limit=10)
        user_count = len(users_resp.get("members", []))
        print(f"   ✅ Found {user_count} users")
        
        if user_count > 0:
            sample_user = users_resp["members"][0]
            print(f"   👤 Sample: @{sample_user.get('name')} ({sample_user.get('real_name', 'N/A')})")
        
        # Test 5: Try chat.postMessage (chat:write scope) - only for user token
        if "chat:write" in " ".join(scopes):
            print(f"\n5️⃣ Testing chat.postMessage() scope availability...")
            print(f"   ✅ chat:write scope is available")
        else:
            print(f"\n5️⃣ Checking chat.postMessage() scope...")
            print(f"   ⚠️  chat:write scope not found (may need for messages)")
        
        print(f"\n✅ {token_type} is working correctly!")
        return True
    
    except SlackApiError as e:
        error = e.response.get("error", "unknown error")
        print(f"\n❌ Error: {error}")
        
        if error == "invalid_auth":
            print(f"   💡 Token is invalid or expired. Check your .env file.")
        elif error == "token_revoked":
            print(f"   💡 Token was revoked. Generate a new one from Slack API.")
        elif error == "token_expired":
            print(f"   💡 Token expired. Refresh it from Slack.")
        elif error == "not_authed":
            print(f"   💡 No authentication provided.")
        elif "missing_scope" in error:
            print(f"   💡 Missing required scopes. Add them in Slack API settings.")
        
        return False
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        return False


def main():
    print("\n" + "="*60)
    print("🔍 SLACK API TOKEN VERIFICATION")
    print("="*60)
    
    bot_ok = test_token(BOT_TOKEN, "BOT TOKEN (xoxb)")
    user_ok = test_token(USER_TOKEN, "USER TOKEN (xoxp)")
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 SUMMARY")
    print(f"{'='*60}")
    
    if bot_ok and user_ok:
        print(f"✅ Both tokens are working correctly!")
        print(f"✅ Ready to use HNG14 workspace!")
        print(f"\n🚀 You can now run:")
        print(f"   - python create_stage_channels.py")
        print(f"   - python create_my_channel.py")
        print(f"   - python delete_channels.py")
    else:
        if not bot_ok:
            print(f"❌ Bot token issue - check your SLACK_BOT_TOKEN_HNG14")
        if not user_ok:
            print(f"❌ User token issue - check your SLACK_USER_TOKEN_HNG14")
        print(f"\n💡 Go to https://api.slack.com/apps to fix the tokens")
    
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
