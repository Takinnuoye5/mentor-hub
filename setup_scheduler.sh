#!/bin/bash
# Setup script for mentor-hub scheduler automation
# Run this on the server to install the cron jobs

echo "Setting up Mentor Hub Scheduler..."
echo ""

# Get the mentor-hub directory
MENTOR_HUB_DIR="/home/ubuntu/mentor-hub"
VENV_PYTHON="$MENTOR_HUB_DIR/venv/bin/python"
SCRIPTS_DIR="$MENTOR_HUB_DIR/scripts"
LOG_DIR="$MENTOR_HUB_DIR/logs"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Check if Python venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Error: Python venv not found at $VENV_PYTHON"
    echo "Please ensure mentor-hub is properly installed"
    exit 1
fi

echo "✅ Found Python venv at $VENV_PYTHON"
echo "✅ Scripts directory: $SCRIPTS_DIR"
echo "✅ Log directory: $LOG_DIR"
echo ""

# New cron entries
SCHEDULER_CRON="0 * * * * cd $SCRIPTS_DIR && /home/ubuntu/mentor-hub/venv/bin/python scheduler.py >> $LOG_DIR/scheduler.log 2>&1"

echo "📝 Adding cron job to run scheduler every hour..."
echo "   $SCHEDULER_CRON"
echo ""

# Add to crontab (preserve existing cron jobs)
(crontab -l 2>/dev/null || echo "") | grep -v "scheduler.py" | (cat; echo "$SCHEDULER_CRON") | crontab -

echo "✅ Cron job installed successfully!"
echo ""
echo "📋 Current cron jobs:"
crontab -l
echo ""
echo "📜 Scheduler logs will be written to: $LOG_DIR/scheduler.log"
echo ""
echo "🧪 Testing scheduler (dry run)..."
$VENV_PYTHON $SCRIPTS_DIR/scheduler.py
echo ""
echo "✅ Setup complete!"
