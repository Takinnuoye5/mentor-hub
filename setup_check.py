#!/usr/bin/env python3
"""
Setup Script for Mentor Hub

Verifies all configuration is correct and can be used as a sanity check
before running the application.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def check_env_file():
    """Check if .env exists."""
    if not os.path.exists(".env"):
        print("❌ .env file not found")
        print("📝 Please copy .env.example to .env and edit with your credentials:")
        print("   cp .env.example .env")
        return False
    print("✅ .env file found")
    return True

def check_slack_tokens():
    """Verify Slack tokens are configured."""
    bot_token = os.getenv("SLACK_BOT_TOKEN_HNG14")
    user_token = os.getenv("SLACK_USER_TOKEN_HNG14")
    signing_secret = os.getenv("SLACK_SIGNING_SECRET_HNG14")
    
    missing = []
    if not bot_token:
        missing.append("SLACK_BOT_TOKEN_HNG14")
    if not user_token:
        missing.append("SLACK_USER_TOKEN_HNG14")
    if not signing_secret:
        missing.append("SLACK_SIGNING_SECRET_HNG14")
    
    if missing:
        print(f"❌ Missing Slack configuration: {', '.join(missing)}")
        return False
    
    print("✅ Slack tokens configured")
    return True

def check_google_credentials():
    """Verify Google credentials file exists."""
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
    
    if not creds_file:
        print("⚠️ GOOGLE_CREDENTIALS_FILE not set (optional, needed for Google Sheets integration)")
        return True
    
    if not Path(creds_file).exists():
        print(f"❌ Google credentials file not found: {creds_file}")
        print("📝 Please download your service account JSON and set GOOGLE_CREDENTIALS_FILE")
        return False
    
    print("✅ Google credentials file found")
    return True

def check_package_structure():
    """Verify package structure is correct."""
    required_dirs = [
        "cli",
        "core",
        "scripts",
        "server",
        "tests",
    ]
    
    missing = []
    for dir_name in required_dirs:
        if not Path(dir_name).is_dir():
            missing.append(dir_name)
    
    if missing:
        print(f"❌ Missing directories: {', '.join(missing)}")
        return False
    
    print("✅ Package structure correct")
    return True

def main():
    print("\n" + "="*60)
    print("🚀 MENTOR HUB SETUP VERIFICATION")
    print("="*60 + "\n")
    
    # Load environment
    load_dotenv()
    
    checks = [
        ("Environment File", check_env_file),
        ("Slack Configuration", check_slack_tokens),
        ("Google Configuration", check_google_credentials),
        ("Package Structure", check_package_structure),
    ]
    
    results = []
    for check_name, check_func in checks:
        print(f"\n📋 Checking {check_name}...")
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append((check_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("📊 VERIFICATION SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {check_name}")
    
    print("="*60)
    
    if passed == total:
        print("\n✅ All checks passed! You're ready to use Mentor Hub")
        print("\nNext steps:")
        print("  1. Run: python -m cli.cli create-stage 2")
        print("  2. Or:  python -m server.main")
        return 0
    else:
        print(f"\n❌ {total - passed} check(s) failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
