#!/usr/bin/env python3
"""
Script to create and delete a test channel.
Useful for verifying the full workflow is working.
"""
import os
import sys
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time

load_dotenv()

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
USER_TOKEN = os.getenv("SLACK_USER_TOKEN_HNG14")

bot_client = WebClient(token=BOT_TOKEN)
user_client = WebClient(token=USER_TOKEN)

TEST_CHANNEL_NAME = "test-hng14-verification"


def create_test_channel():
    """Create a test channel."""
    print(f"\n{'='*60}")
    print(f"🔨 Creating test channel: #{TEST_CHANNEL_NAME}")
    print(f"{'='*60}\n")
    
    try:
        # Create the channel
        resp = user_client.conversations_create(
            name=TEST_CHANNEL_NAME, 
            is_private=True
        )
        
        channel_id = resp["channel"]["id"]
        print(f"✅ Channel created successfully!")
        print(f"   Channel ID: {channel_id}")
        print(f"   Name: #{TEST_CHANNEL_NAME}")
        print(f"   Type: Private\n")
        
        # Add bot to channel
        try:
            bot_id = bot_client.auth_test()["user_id"]
            user_client.conversations_invite(channel=channel_id, users=[bot_id])
            print(f"✅ Bot added to channel\n")
        except Exception as e:
            print(f"⚠️  Could not add bot: {str(e)}\n")
        
        return channel_id
    
    except SlackApiError as e:
        error = e.response.get("error", "")
        print(f"❌ Error creating channel: {error}\n")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}\n")
        return None


def delete_test_channel(channel_id):
    """Delete the test channel."""
    print(f"\n{'='*60}")
    print(f"🗑️  Deleting test channel: #{TEST_CHANNEL_NAME}")
    print(f"{'='*60}\n")
    
    try:
        user_client.conversations_archive(channel=channel_id)
        print(f"✅ Channel archived successfully!")
        print(f"   The channel has been deleted from HNG14\n")
        return True
    
    except SlackApiError as e:
        error = e.response.get("error", "")
        print(f"❌ Error deleting channel: {error}\n")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}\n")
        return False


def main():
    print("\n" + "="*60)
    print("🧪 HNG14 CHANNEL TEST")
    print("="*60)
    print("\nThis script will:")
    print("1. Create a test channel")
    print("2. Wait for your confirmation")
    print("3. Delete the test channel")
    print("="*60)
    
    # Create test channel
    channel_id = create_test_channel()
    
    if not channel_id:
        print("❌ Failed to create test channel")
        sys.exit(1)
    
    print("📍 The test channel is now visible in your Slack workspace!")
    print("   Look for: #test-hng14-verification\n")
    
    # Wait for user confirmation
    while True:
        confirm = input("✅ Can you see the channel? Type 'yes' to delete it: ").strip().lower()
        
        if confirm in ['yes', 'y']:
            break
        elif confirm in ['no', 'n']:
            print("\n⚠️  Not deleting. You can delete it manually from Slack.\n")
            sys.exit(0)
        else:
            print("Please type 'yes' or 'no'")
    
    # Delete test channel
    time.sleep(1)
    if delete_test_channel(channel_id):
        print("="*60)
        print("✅ TEST COMPLETE - All operations working correctly!")
        print("="*60)
        print("\n🎉 Your HNG14 setup is ready to go!")
        print("\nNext steps:")
        print("   1. Run: python create_stage_channels.py")
        print("   2. Check that all 11 track channels were created")
        print("   3. Verify track leads are in each channel\n")
    else:
        print("⚠️  Could not delete test channel automatically")
        print("   You can delete it manually: /archive #test-hng14-verification\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(0)
