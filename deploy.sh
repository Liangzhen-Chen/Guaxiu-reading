#!/bin/bash
# 朽瓜后端部署脚本（SSH 密钥认证版）
# ====================================================
# 使用前请先配置 SSH 密钥对：
#
# 1. 生成密钥对（如已存在则跳过）：
#      ssh-keygen -t ed25519 -f ~/.ssh/xiugua_ecs
#
# 2. 上传公钥到服务器：
#      ssh-copy-id -i ~/.ssh/xiugua_ecs.pub ubuntu@122.51.236.219
#
# 3. （可选）在 ~/.ssh/config 中配置 Host 别名以简化命令：
#      Host xiugua-ecs
#          HostName 122.51.236.219
#          User ubuntu
#          IdentityFile ~/.ssh/xiugua_ecs
#
# 之后该脚本会自动使用 SSH 密钥认证，无需输入密码。
# ====================================================
set -e

SERVER="ubuntu@122.51.236.219"
DIR="$(dirname "$0")/backend"

echo "Uploading..."
scp -r "$DIR/app" "$DIR/requirements.txt" "$DIR/prompts_private.py" "$DIR/alembic.ini" "$DIR/alembic" "$DIR/scripts" "$DIR/deploy" "$SERVER:/opt/xiugua/backend/"

echo "Restarting via systemd..."
ssh "$SERVER" '
	cd /opt/xiugua/backend && source venv/bin/activate
	pip install -r requirements.txt -q
	sudo systemctl restart xiugua
	sleep 2 && curl -s http://127.0.0.1:8000/health
'

echo "Done!"

# ====================================================
# 已从 nohup 切换到 systemd 服务。
# uvicorn 日志写入 /opt/xiugua/logs/uvicorn.log。
#
# 如果 systemd 服务尚未部署，首次执行：
#   ssh "$SERVER" "sudo mkdir -p /opt/xiugua/logs && sudo chown ubuntu:ubuntu /opt/xiugua/logs"
#   scp backend/deploy/xiugua.service "$SERVER:/tmp/xiugua.service"
#   ssh "$SERVER" '
#     sudo cp /tmp/xiugua.service /etc/systemd/system/
#     sudo systemctl daemon-reload
#     sudo systemctl enable xiugua
#     sudo systemctl start xiugua
#   '
# ====================================================
