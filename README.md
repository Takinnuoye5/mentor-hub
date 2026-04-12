# Mentor Hub

A comprehensive system for managing HNG cohort mentors, automating stage channel creation, and coordinating mentor track assignments through Slack integration.

## Overview

Mentor Hub provides two primary modes of operation:

1. **CLI Mode** - Automated batch operations for stage and channel management
2. **Server Mode** - FastAPI-based Slack integration for real-time mentor interactions

## Features

- **Automated Stage Management** - Create, configure, and manage Slack stage channels via CLI
- **Interactive Mentor Tracks** - Slack `/mentor-track` command with multi-select UI for track selection
- **Smart Assignments** - Automatically add mentors to channels based on selected tracks
- **Persistent State** - Google Sheets integration for tracking mentor selections
- **Efficient Caching** - Slack user lookup optimization with local caching
- **Production Ready** - Systemd service integration, comprehensive error handling, activity logging

## Project Structure

```
mentor-hub/
├── cli/                          # Command-line interface
│   ├── cli.py                   # CLI entry point
│   ├── bridge.py                # Command router
│   └── commands/                # Command implementations
├── core/                         # Shared core modules
│   ├── config.py                # Centralized configuration
│   └── user_cache.py            # User caching layer
├── scripts/                      # Standalone automation scripts
│   ├── create_stage_channels.py         # Stage/channel creation
│   ├── add_mentors_to_existing_stage.py # Mentor assignment
│   ├── delete_channels.py               # Channel cleanup
│   ├── find_slack_users.py              # User discovery
│   └── verify_tokens.py                 # Token validation
├── server/                       # FastAPI web server
│   ├── main.py                  # Slack webhook handler
│   ├── handlers.py              # Block/action handlers
│   ├── mentor_track_cli.py      # Persistence layer
│   └── utils/                   # Helper utilities
├── tests/                        # Test suite
│   └── test_integrated.py       # Integration tests
└── requirements.txt              # Python dependencies
```

## Requirements

- Python 3.8+
- Slack Workspace with bot permissions
- Google Sheets API credentials (for persistence)

## Installation

### Local Development

```bash
# Clone repository
git clone https://github.com/yourusername/mentor-hub.git
cd mentor-hub

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate (Windows)

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with:
# - SLACK_BOT_TOKEN_HNG14
# - SLACK_USER_TOKEN_HNG14
# - SLACK_SIGNING_SECRET_HNG14
# - GOOGLE_CREDENTIALS_FILE
```

### Running

**CLI Mode:**
```bash
# Create stages
python -m cli.cli create-stage 2

# Add mentors incrementally
python -m cli.cli mentors-incremental
```

**Server Mode:**
```bash
# Start FastAPI server
python -m server.main
# Listens on http://localhost:3000
```

## Configuration

All configuration is managed through environment variables in `.env`:

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_BOT_TOKEN_HNG14` | Bot user token for API calls | Yes |
| `SLACK_USER_TOKEN_HNG14` | User token for member operations | Yes |
| `SLACK_SIGNING_SECRET_HNG14` | Webhook signature verification | Yes |
| `GOOGLE_CREDENTIALS_FILE` | Path to Google service account JSON | Yes |
| `TESTING_MODE` | Enable test mode (default: false) | No |

## Deployment

### Using systemd (Production)

```bash
# Copy service file
sudo cp mentor-hub.service /etc/systemd/system/

# Enable and start
sudo systemctl enable hngbot
sudo systemctl start hngbot
sudo systemctl status hngbot
```

### Environment Setup

The server requires a systemd service file pointing to your virtual environment and .env file. For details, see deployment documentation or your hosting provider's guides.

## API Endpoints

### Health Checks
- `GET /test` - Simple test endpoint
- `GET /ping` - Health check with timestamp

### Slack Integration
- `POST /slack/mentor-track` - Slash command handler (`/mentor-track`)
- `POST /slack/interactive` - Interactive component handler (selections, buttons)

## Testing

```bash
# Run integrated test suite
python tests/test_integrated.py
```

Tests cover:
- Package imports and module structure
- Configuration loading from environment
- Google Sheets persistence
- Slack API interactions
- CLI command routing
- FastAPI endpoints

## Troubleshooting

**Import errors:** Ensure you're in the virtual environment and requirements are installed:
```bash
pip install -r requirements.txt
```

**Token errors:** Verify tokens in `.env` are correct and have appropriate scopes.

**Google Sheets:** Ensure credentials file exists and service account has editor access to the spreadsheet.

## Support

For issues or questions, check the environment setup or review logs from the systemd service:
```bash
sudo journalctl -u hngbot -f
```

```bash
pip install -r requirements.txt
```

### 3. Usage

#### CLI - Create a Stage

```bash
python -m cli.cli create-stage 2
```

#### CLI - Add Mentors Incrementally

```bash
python -m cli.cli mentors 2 --show-baseline
python -m cli.cli mentors 2              # Process new submissions
python -m cli.cli mentors 2 --process-all  # Backfill all
```

#### Server - Run Slack Command Handler

```bash
python -m server.main
```

## Configuration

All configuration is stored in `.env`. Key variables:

- `SLACK_BOT_TOKEN_HNG14` - Bot user token for Slack API calls
- `SLACK_USER_TOKEN_HNG14` - User token for elevated permissions
- `SLACK_SIGNING_SECRET_HNG14` - Signing secret for request verification
- `GOOGLE_CREDENTIALS_FILE` - Path to Google service account JSON

## Workflow

1. **Stage Creation**
   - Create stage channels with `create-stage` command
   - Automatically adds track leads to channels

2. **Mentor Track Selection**
   - Mentors use `/mentor-track` Slack command
   - Select preferred specialization tracks
   - Admin notification sent

3. **Mentor Assignment**
   - Mentors from Google Sheet are processed
   - Automatically added to selected track channels
   - Notifications posted to track channels

## Development

### Adding New Scripts

1. Place script in `scripts/` folder
2. Update imports to use `core/` modules
3. Add to CLI via `cli/bridge.py` if needed

### Adding New Server Endpoints

1. Create handler in `server/handlers/`
2. Register endpoint in `server/main.py`
3. Add to tests in `tests/`

## Troubleshooting

**"No mentor worksheets found"**
- Check Google Sheet has worksheet named "Mentors" (or "Mentors YYYY-MM-DD")
- Verify service account has sheet access

**"Failed to add users"**
- Check bot has proper scopes (channels:manage, users:read, chat:write)
- Verify tokens in .env are valid

**Import errors**
- Ensure you're in the mentor-hub directory
- Run with `python -m` for proper module loading

## Resources

- [Slack API Documentation](https://api.slack.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Google Sheets API](https://developers.google.com/sheets/api)

## Support

For issues or questions, check the error logs or review the inline code documentation.
