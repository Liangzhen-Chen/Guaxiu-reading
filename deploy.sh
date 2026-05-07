#!/bin/bash
# 朽瓜后端部署脚本 v2.0
# 支持：零停机部署 / staging 环境
# 用法：bash deploy.sh [staging]
set -e

SERVER="ubuntu@122.51.236.219"
DIR="$(dirname "$0")/backend"
TARGET="${1:-production}"  # production or staging

# ── Staging 配置 ──
if [ "$TARGET" = "staging" ]; then
  PORT=8001
  ENV_FILE="/opt/xiugua/backend/.env.staging"
  SERVICE_NAME="xiugua-staging"
  echo ">>> Deploying to STAGING (port $PORT)"
else
  PORT=8000
  ENV_FILE="/opt/xiugua/backend/.env"
  SERVICE_NAME="xiugua"
  echo ">>> Deploying to PRODUCTION (port $PORT)"
fi

echo "Uploading..."
scp -r "$DIR/app" "$DIR/requirements.txt" "$DIR/prompts_private.py" "$DIR/alembic.ini" "$DIR/alembic" "$DIR/scripts" "$DIR/deploy" "$SERVER:/opt/xiugua/backend/"

echo "Installing dependencies..."
ssh "$SERVER" "cd /opt/xiugua/backend && source venv/bin/activate && pip install -r requirements.txt -q"

echo "Running migrations..."
ssh "$SERVER" "cd /opt/xiugua/backend && source venv/bin/activate && export PYTHONPATH=/opt/xiugua/backend && alembic upgrade head 2>/dev/null || alembic stamp head 2>/dev/null; true"

if [ "$TARGET" = "staging" ]; then
  # Staging: simple restart
  echo "Restarting staging..."
  ssh "$SERVER" "sudo systemctl restart $SERVICE_NAME 2>/dev/null || (cd /opt/xiugua/backend && source venv/bin/activate && nohup uvicorn app.main:app --host 127.0.0.1 --port $PORT > /opt/xiugua/logs/staging.log 2>&1 &)"
else
  # ── 零停机部署：新进程 → 切 Nginx → 停旧进程 ──

  # 1. Determine the alternate port
  CURRENT_PORT=$(ssh "$SERVER" "grep -oP '127.0.0.1:\K\d+' /etc/nginx/sites-enabled/default | head -1 || echo 8000")
  if [ "$CURRENT_PORT" = "8000" ]; then
    NEW_PORT=8001
  else
    NEW_PORT=8000
  fi
  echo "Current port: $CURRENT_PORT → Switching to: $NEW_PORT"

  # 2. Start new instance on alternate port
  echo "Starting new instance on port $NEW_PORT..."
  ssh "$SERVER" "
    cd /opt/xiugua/backend && source venv/bin/activate
    # Kill any stale process on the new port
    pkill -TERM -f \"port $NEW_PORT\" 2>/dev/null || true
    sleep 1
    # Start new uvicorn
    nohup uvicorn app.main:app --host 127.0.0.1 --port $NEW_PORT > /opt/xiugua/logs/uvicorn-$NEW_PORT.log 2>&1 &
    # Wait for health check
    for i in \$(seq 1 10); do
      sleep 1
      if curl -s http://127.0.0.1:$NEW_PORT/health | grep -q '\"ok\"'; then
        echo \"New instance ready on port $NEW_PORT\"
        exit 0
      fi
    done
    echo \"ERROR: New instance failed to start\"
    exit 1
  "

  # 3. Switch Nginx upstream
  echo "Switching Nginx to port $NEW_PORT..."
  ssh "$SERVER" "
    sudo sed -i 's/127.0.0.1:$CURRENT_PORT/127.0.0.1:$NEW_PORT/g' /etc/nginx/sites-enabled/default
    sudo nginx -t && sudo nginx -s reload
    echo \"Nginx switched to port $NEW_PORT\"
  "

  # 4. Gracefully stop old instance
  echo "Stopping old instance on port $CURRENT_PORT..."
  ssh "$SERVER" "pkill -TERM -f \"port $CURRENT_PORT\" 2>/dev/null || true"

  # 5. Update systemd to point to new port (for next restart)
  ssh "$SERVER" "
    sudo sed -i 's/--port $CURRENT_PORT/--port $NEW_PORT/g' /etc/systemd/system/xiugua.service
    sudo systemctl daemon-reload
  "

  echo ">>> Zero-downtime deploy complete. Now serving on port $NEW_PORT"
fi

echo "Done!"
