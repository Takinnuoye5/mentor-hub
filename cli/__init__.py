"""
Slack Stage Manager
-------------------

A small, repo-friendly CLI wrapper around existing channel automation scripts.

Usage:
    python -m slack_stage_manager --help

This package calls into the current project's scripts (create_stage_channels.py,
add_mentors_to_existing_stage.py) to provide a unified, clean interface for:
  - Creating stage and track channels
  - Incrementally adding mentors from the latest Google Sheet

It does not copy logic yet; it provides a thin layer to make it easier to split
into a dedicated GitHub repository later. You can evolve these wrappers into a
standalone package by inlining the bridged functions.
"""

__all__ = [
    "__version__",
]

__version__ = "0.1.0"
