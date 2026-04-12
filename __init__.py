"""
Mentor Hub
==========

A unified platform for managing HNG cohort mentors and stage automation on Slack.

Modules:
- cli: Command-line interface for automation
- core: Shared utilities and configuration
- scripts: Standalone automation scripts
- server: FastAPI web server for Slack interactions
"""

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "core",
    "scripts",
    "server",
    "cli",
]
