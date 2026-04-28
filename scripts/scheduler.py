#!/usr/bin/env python3
"""
Automated scheduler for stage creation and mentor assignment.

This script:
1. Creates a new stage every 2 days (after the last stage was created)
2. Automatically adds new mentors to existing channels

Usage:
    python scheduler.py              # Check and run tasks if needed
    python scheduler.py --force-stage # Force create next stage regardless of time
    python scheduler.py --force-add   # Force add mentors to channels
"""

import os
import sys
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from slack_sdk import WebClient
from dotenv import load_dotenv

# Load environment
load_dotenv(dotenv_path=str(Path(__file__).parent.parent / '.env'))
BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN_HNG14")
bot_client = WebClient(token=BOT_TOKEN)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========================================
# CONFIGURATION FLAGS
# ========================================
STAGE_CREATION_ENABLED = False  # Set to False to pause automatic stage creation (mentors will still sync)
# ========================================

# State file to track last executions
STATE_FILE = Path(__file__).parent / ".scheduler_state.json"
DEFAULT_STATE = {
    "last_stage_created": None,
    "last_stage_number": 0,
    "last_mentor_sync": None,
}

# Interval settings (in hours)
STAGE_CREATION_INTERVAL = 48  # 2 days = 48 hours
MENTOR_SYNC_INTERVAL = 1    # 1 hour (syncs mentors every hour)


def load_state():
    """Load scheduler state from file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")
            return DEFAULT_STATE.copy()
    return DEFAULT_STATE.copy()


def save_state(state):
    """Save scheduler state to file."""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        logger.info(f"State saved: {state}")
    except Exception as e:
        logger.error(f"Failed to save state file: {e}")


def should_create_stage(state):
    """Check if enough time has passed to create a new stage."""
    if state["last_stage_created"] is None:
        logger.info("No previous stage creation recorded, ready to create first stage")
        return True
    
    try:
        last_created = datetime.fromisoformat(state["last_stage_created"])
        time_since = datetime.now() - last_created
        hours_since = time_since.total_seconds() / 3600
        
        if hours_since >= STAGE_CREATION_INTERVAL:
            logger.info(f"✅ {hours_since:.1f} hours since last stage - ready to create new stage")
            return True
        else:
            remaining = STAGE_CREATION_INTERVAL - hours_since
            logger.info(f"⏳ {remaining:.1f} hours until next stage creation")
            return False
    except Exception as e:
        logger.error(f"Error checking stage creation time: {e}")
        return False


def should_sync_mentors(state):
    """Check if enough time has passed to sync mentors to channels."""
    if state["last_mentor_sync"] is None:
        logger.info("No previous mentor sync recorded, ready to sync")
        return True
    
    try:
        last_sync = datetime.fromisoformat(state["last_mentor_sync"])
        time_since = datetime.now() - last_sync
        hours_since = time_since.total_seconds() / 3600
        
        if hours_since >= MENTOR_SYNC_INTERVAL:
            logger.info(f"✅ {hours_since:.1f} hours since last sync - ready to sync mentors")
            return True
        else:
            remaining = MENTOR_SYNC_INTERVAL - hours_since
            logger.info(f"⏳ {remaining:.1f} hours until next mentor sync")
            return False
    except Exception as e:
        logger.error(f"Error checking mentor sync time: {e}")
        return False


def create_next_stage(state):
    """Create the next stage by running create_stage_channels.py directly."""
    try:
        next_stage = state["last_stage_number"] + 1
        logger.info(f"🚀 Creating stage {next_stage}...")
        
        # Run the script the same way it's run manually: python create_stage_channels.py <stage_number>
        import subprocess
        result = subprocess.run(
            [sys.executable, "create_stage_channels.py", str(next_stage)],
            cwd=Path(__file__).parent,
            capture_output=False,
            timeout=1800  # 30 minute timeout (increased to handle large mentor batches and retries)
        )
        
        if result.returncode == 0:
            # Update state on success
            state["last_stage_created"] = datetime.now().isoformat()
            state["last_stage_number"] = next_stage
            save_state(state)
            logger.info(f"✅ Stage {next_stage} created successfully")
            return True
        else:
            logger.error(f"❌ Failed to create stage {next_stage} (exit code: {result.returncode})")
            return False
        
    except Exception as e:
        logger.error(f"❌ Failed to create stage: {e}", exc_info=True)
        return False


def sync_mentors_to_channels(state):
    """Add new mentors to ALL ACTIVE stage channels by discovering which stages exist and are not archived"""
    try:
        logger.info("🔄 Discovering active stages...")
        
        # Discover which stages are actually active (not archived)
        active_stages = _discover_active_stages()
        
        if not active_stages:
            logger.warning("⚠️ No active stage channels found, skipping mentor sync")
            return False
        
        logger.info(f"✅ Found active stages: {sorted(active_stages)}")
        logger.info("🔄 Syncing mentors to all active stage channels...")
        
        # Sync mentors to each active stage
        import subprocess
        all_success = True
        
        for stage_num in sorted(active_stages):
            logger.info(f"  → Syncing mentors to stage-{stage_num}...")
            result = subprocess.run(
                [sys.executable, "add_mentors_to_existing_stage.py", str(stage_num)],
                cwd=Path(__file__).parent,
                capture_output=False,
                timeout=600  # 10 minute timeout per stage
            )
            
            if result.returncode != 0:
                logger.error(f"❌ Failed to sync mentors for stage {stage_num} (exit code: {result.returncode})")
                all_success = False
            else:
                logger.info(f"✅ Mentors synced for stage-{stage_num}")
        
        if all_success:
            # Update state on success
            state["last_mentor_sync"] = datetime.now().isoformat()
            save_state(state)
            logger.info(f"✅ All mentors synced to active stages: {sorted(active_stages)}")
            return True
        else:
            logger.warning(f"⚠️ Mentor sync completed with some errors for active stages")
            state["last_mentor_sync"] = datetime.now().isoformat()
            save_state(state)
            return False
        
    except Exception as e:
        logger.error(f"❌ Failed to sync mentors: {e}", exc_info=True)
        return False


def _discover_active_stages():
    """Discover which stage channels are active (exist and not archived).
    
    Returns a set of stage numbers, e.g., {1, 2, 3, 4}
    """
    stages = set()
    cursor = None
    stage_pattern = re.compile(r'^stage-(\d+)$')
    
    for attempt in range(3):
        try:
            while True:
                resp = bot_client.conversations_list(
                    types="private_channel",
                    limit=200,
                    cursor=cursor,
                )
                
                for ch in resp.get("channels", []):
                    # Match "stage-N" pattern (main channel only, not track channels)
                    match = stage_pattern.match(ch["name"])
                    if match:
                        stage_num = int(match.group(1))
                        # Only include if NOT archived
                        if not ch.get("is_archived", False):
                            stages.add(stage_num)
                            logger.info(f"  ✅ Found active stage: stage-{stage_num}")
                        else:
                            logger.info(f"  ⏭️  Skipping archived stage: stage-{stage_num}")
                
                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break
            
            return stages
            
        except Exception as e:
            logger.warning(f"⚠️ Error discovering stages (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                import time
                time.sleep(2)
    
    logger.error("❌ Could not discover active stages")
    return stages


def main():
    """Main scheduler logic."""
    # Parse command line arguments
    force_stage = "--force-stage" in sys.argv
    force_add = "--force-add" in sys.argv
    
    logger.info("=" * 60)
    logger.info("Mentor Hub Scheduler Starting")
    logger.info("=" * 60)
    
    # Load current state
    state = load_state()
    logger.info(f"Current state: {state}")
    
    # Check and create stage if needed (but only if enabled)
    if not STAGE_CREATION_ENABLED and not force_stage:
        logger.info("⏸️ Stage creation DISABLED (waiting for manual approval)")
    elif force_stage or should_create_stage(state):
        logger.info("🎬 Stage creation check: TRIGGERED")
        create_next_stage(state)
    else:
        logger.info("⏳ Stage creation check: NOT YET")
    
    # Check and sync mentors if needed (ALWAYS ENABLED)
    if force_add or should_sync_mentors(state):
        logger.info("👥 Mentor sync check: TRIGGERED")
        sync_mentors_to_channels(state)
    else:
        logger.info("⏳ Mentor sync check: NOT YET")
    
    logger.info("=" * 60)
    logger.info("Scheduler completed")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
