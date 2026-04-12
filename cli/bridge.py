"""Bridges to existing project scripts so the new CLI stays thin.

This lets us keep using the current code while organizing a clean, reusable CLI
that can be moved into a new repository later without breaking behavior now.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


def override_google_creds_if_set(csc_module: Any) -> None:
    """If GOOGLE_CREDENTIALS_FILE is set in env, override module variable.

    This mirrors the behavior used in add_mentors_to_existing_stage.py so the
    wrapper stays consistent when called via the new CLI.
    """
    env_creds = os.getenv("GOOGLE_CREDENTIALS_FILE")
    if not env_creds:
        return
    try:
        csc_module.GOOGLE_CREDENTIALS_FILE = env_creds
        print(f"🔧 Using GOOGLE_CREDENTIALS_FILE from env: {env_creds}")
    except Exception as e:
        print(f"⚠️ Could not override GOOGLE_CREDENTIALS_FILE: {e}")


def create_stage(stage_number: int) -> None:
    """Create or populate all stage and track channels.

    Delegates to create_stage_channels.create_stage_channels(stage_number).
    """
    try:
        from mentor_hub.scripts import create_stage_channels as csc
    except ImportError:
        # Fallback for direct execution
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import create_stage_channels as csc

    override_google_creds_if_set(csc)
    return csc.create_stage_channels(stage_number)


def mentors_incremental(
    stage: int,
    *,
    dry_run: bool = False,
    process_all: bool = False,
    since_minutes: Optional[int] = None,
    reset_baseline: bool = False,
    show_baseline: bool = False,
    show_newest: bool = False,
    list_new: bool = False,
    baseline_mode: str = "timestamp",
) -> None:
    """Incrementally add mentors to an existing stage.

    Delegates to add_mentors_to_existing_stage.process_incremental.
    """
    try:
        from mentor_hub.scripts import add_mentors_to_existing_stage as am
    except ImportError:
        # Fallback for direct execution
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import add_mentors_to_existing_stage as am

    # The mentors script internally handles overriding GOOGLE_CREDENTIALS_FILE
    # for the create_stage_channels module it imports. No extra override needed
    # here if the env var is already set.

    return am.process_incremental(
        stage,
        dry_run=dry_run,
        process_all=process_all,
        since_minutes=since_minutes,
        reset_baseline=reset_baseline,
        show_baseline=show_baseline,
        show_newest=show_newest,
        list_new=list_new,
        baseline_mode=baseline_mode,
    )
