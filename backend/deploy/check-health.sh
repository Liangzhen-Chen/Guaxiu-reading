#!/bin/bash
# Xiugua 后端健康检查脚本
# 部署路径: /opt/xiugua/scripts/check-health.sh
# 通过 crontab 每 5 分钟执行一次
#
# 功能:
#   1. curl 请求本地 /health 端点
#   2. 成功时写入带时间戳的日志
#   3. 失败时记录错误，连续失败 3 次时输出严重告警到 syslog

set -euo pipefail

# --- 配置 ---
HEALTH_URL="http://127.0.0.1:8000/health"
LOG_FILE="/opt/xiugua/logs/healthcheck.log"
STATE_FILE="/tmp/xiugua_health_failures"
MAX_FAILURES=3

# --- 确保日志目录存在 ---
mkdir -p "$(dirname "$LOG_FILE")"

# --- 执行健康检查 ---
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "000")
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

if [ "$HTTP_CODE" = "200" ]; then
    # 成功：写入日志，重置失败计数
    echo "$TIMESTAMP OK http_code=$HTTP_CODE" >> "$LOG_FILE"
    rm -f "$STATE_FILE"
    exit 0
else
    # 失败：写入日志，累加失败计数
    echo "$TIMESTAMP FAIL http_code=$HTTP_CODE" >> "$LOG_FILE"

    FAIL_COUNT=1
    if [ -f "$STATE_FILE" ]; then
        FAIL_COUNT=$(($(cat "$STATE_FILE") + 1))
    fi
    echo "$FAIL_COUNT" > "$STATE_FILE"

    if [ "$FAIL_COUNT" -ge "$MAX_FAILURES" ]; then
        # 连续多次失败，写入严重告警
        logger -t "HEALTH_CRITICAL" "Xiugua backend unreachable after ${FAIL_COUNT} consecutive failures (http_code=$HTTP_CODE)"
        echo "$TIMESTAMP CRITICAL consecutive_failures=$FAIL_COUNT http_code=$HTTP_CODE -- alert triggered" >> "$LOG_FILE"
    fi

    exit 1
fi
