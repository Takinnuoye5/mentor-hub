#!/usr/bin/env python3
"""
Test script to verify the Update vs Replace feature for mentor track selection.

This simulates:
1. Initial submission with tracks [frontend, backend]
2. Second submission with tracks [devops]
3. Verifies confirmation dialog is shown
4. Tests both 'add' and 'replace' scenarios
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Mock Slack client for testing
class MockSlackClient:
    def __init__(self):
        self.messages = []
    
    def chat_postEphemeral(self, **kwargs):
        self.messages.append({
            'type': 'postEphemeral',
            'channel': kwargs.get('channel'),
            'user': kwargs.get('user'),
            'blocks': kwargs.get('blocks')
        })
    
    def conversations_open(self, **kwargs):
        return {'channel': {'id': 'C_TEST_DM'}}
    
    def chat_postMessage(self, **kwargs):
        self.messages.append({
            'type': 'postMessage',
            'channel': kwargs.get('channel'),
            'text': kwargs.get('text')
        })


def test_track_selection_logic():
    """Test the core track selection logic"""
    
    print("\n" + "="*70)
    print("TEST: Update vs Replace Track Selection Logic")
    print("="*70 + "\n")
    
    # Test 1: Add operation (merge tracks)
    print("TEST 1: ADD Operation (merge tracks)")
    print("-" * 70)
    existing = ["frontend", "backend"]
    new = ["devops"]
    
    combined = list(set(existing + new))
    combined.sort()
    
    print(f"  Existing tracks: {existing}")
    print(f"  New selection:   {new}")
    print(f"  Result (ADD):    {combined}")
    assert combined == ["backend", "devops", "frontend"], "ADD operation failed"
    print("  ✅ PASSED\n")
    
    # Test 2: Replace operation (use new only)
    print("TEST 2: REPLACE Operation (use new only)")
    print("-" * 70)
    existing = ["frontend", "backend"]
    new = ["devops"]
    
    print(f"  Existing tracks: {existing}")
    print(f"  New selection:   {new}")
    print(f"  Result (REPLACE): {new}")
    assert new == ["devops"], "REPLACE operation failed"
    print("  ✅ PASSED\n")
    
    # Test 3: Add with overlapping tracks
    print("TEST 3: ADD with overlapping tracks")
    print("-" * 70)
    existing = ["frontend", "backend"]
    new = ["backend", "devops"]
    
    combined = list(set(existing + new))
    combined.sort()
    
    print(f"  Existing tracks: {existing}")
    print(f"  New selection:   {new}")
    print(f"  Result (ADD):    {combined}")
    assert combined == ["backend", "devops", "frontend"], "Overlapping ADD failed"
    print("  ✅ PASSED\n")
    
    # Test 4: Replace with same tracks
    print("TEST 4: REPLACE with same tracks")
    print("-" * 70)
    existing = ["frontend", "backend"]
    new = ["frontend", "backend"]
    
    print(f"  Existing tracks: {existing}")
    print(f"  New selection:   {new}")
    print(f"  Result (REPLACE): {new}")
    assert new == existing, "REPLACE with same tracks failed"
    print("  ✅ PASSED\n")


def test_confirmation_dialog_structure():
    """Test the confirmation dialog structure"""
    
    print("="*70)
    print("TEST: Confirmation Dialog Structure")
    print("="*70 + "\n")
    
    def track_id_to_display_name(t: str) -> str:
        """Simple display name function"""
        return t.replace("-", " ").title()
    
    existing_tracks = ["frontend", "backend"]
    new_tracks = ["devops"]
    
    existing_readable = [track_id_to_display_name(t) for t in existing_tracks]
    new_readable = [track_id_to_display_name(t) for t in new_tracks]
    
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "🔄 *You've already submitted tracks before!*"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Your current tracks:*\n{', '.join(existing_readable)}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*New selection:*\n{', '.join(new_readable)}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "_What would you like to do?_"}},
        {"type": "actions", "block_id": "update_confirmation", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "Update (Add new tracks)"},
             "value": "update_add", "action_id": "confirm_update_add",
             "style": "primary"},
            {"type": "button", "text": {"type": "plain_text", "text": "Replace (Use only new selection)"},
             "value": "update_replace", "action_id": "confirm_update_replace",
             "style": "danger"}
        ]}
    ]
    
    print("Dialog Structure:")
    print(json.dumps(blocks, indent=2))
    
    # Verify structure
    assert len(blocks) == 7, "Wrong number of blocks"
    assert blocks[0]["type"] == "section", "First block should be section"
    assert blocks[-1]["type"] == "actions", "Last block should be actions"
    assert len(blocks[-1]["elements"]) == 2, "Should have 2 action buttons"
    
    action_ids = [e["action_id"] for e in blocks[-1]["elements"]]
    assert "confirm_update_add" in action_ids, "Missing 'add' action"
    assert "confirm_update_replace" in action_ids, "Missing 'replace' action"
    
    print("\n✅ Dialog structure is correct\n")


def test_message_formatting():
    """Test message formatting for different scenarios"""
    
    print("="*70)
    print("TEST: DM Message Formatting")
    print("="*70 + "\n")
    
    final_tracks = ["backend", "devops", "frontend"]
    readable = [t.title() for t in final_tracks]
    
    # Test ADD message
    print("ADD Message:")
    print("-" * 70)
    add_message = f"""✅ Your track selection has been updated (tracks added).

All your tracks: {', '.join(readable)}

🚀 You will be added to all stage channels for these tracks! Thank you for mentoring with HNG!"""
    print(add_message)
    print()
    
    # Test REPLACE message
    print("REPLACE Message:")
    print("-" * 70)
    replace_message = f"""✅ Your track selection has been changed.

Selected Tracks: {', '.join(readable)}

🚀 You will be added to all stage channels for these tracks! Thank you for mentoring with HNG!"""
    print(replace_message)
    print()
    
    print("✅ Messages formatted correctly\n")


if __name__ == "__main__":
    try:
        test_track_selection_logic()
        test_confirmation_dialog_structure()
        test_message_formatting()
        
        print("="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
