#!/bin/bash
set -e

# Set up crontab for main.py every 3 minutes
echo "*/3 * * * * /app/venv/bin/python /app/main.py $SPREADSHEET_ID >> /app/logs/main.log 2>&1" | crontab -

# Start cron daemon
crond -b

# Start bot.py in foreground (keeps container alive)
exec /app/venv/bin/python /app/bot.py