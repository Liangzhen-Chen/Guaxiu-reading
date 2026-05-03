#!/bin/bash
# 朽瓜后端部署
# 先设密码: export SSHPASS="你的服务器密码"
set -e

SERVER="ubuntu@122.51.236.219"
DIR="$(dirname "$0")/backend"

echo "Uploading..."
sshpass -e scp -o StrictHostKeyChecking=no -r "$DIR/app" "$DIR/requirements.txt" "$DIR/prompts_private.py" "$SERVER:/opt/xiugua/backend/"

echo "Restarting..."
sshpass -e ssh -o StrictHostKeyChecking=no "$SERVER" '
cd /opt/xiugua/backend && source venv/bin/activate
pip install -r requirements.txt -q
pkill uvicorn 2>/dev/null; sleep 1
nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 > ~/xiugua.log 2>&1 &
sleep 2 && curl -s http://127.0.0.1:8000/health
'

echo "Done!"
