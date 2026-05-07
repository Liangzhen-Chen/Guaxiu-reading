#!/bin/bash
# =============================================================================
# 朽瓜（Xiugua）数据库备份 crontab 安装脚本
# =============================================================================
# 功能：
#   1. 将每日备份脚本注册到当前用户的 crontab
#   2. 验证 crontab 是否添加成功
#
# 用法：
#   ./setup-cron.sh
#
# crontab 条目：
#   0 3 * * * /opt/xiugua/backend/scripts/backup-db.sh >> /opt/xiugua/backups/cron.log 2>&1
#
# 说明：
#   每天凌晨 3:00 执行备份（业务低峰期）。
#   日志输出到 /opt/xiugua/backups/cron.log，便于排查。
# =============================================================================

set -euo pipefail

# ── 脚本路径 ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup-db.sh"
BACKUP_DIR="/opt/xiugua/backups"
CRON_LOG="${BACKUP_DIR}/cron.log"
CRON_JOB="0 3 * * * ${BACKUP_SCRIPT} >> ${CRON_LOG} 2>&1"

# ── 检查备份脚本是否存在 ──
if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo "ERROR: 备份脚本不存在: ${BACKUP_SCRIPT}"
    echo "请确保 backup-db.sh 已创建并位于 scripts/ 目录下。"
    exit 1
fi

if [ ! -x "$BACKUP_SCRIPT" ]; then
    echo "设置 backup-db.sh 为可执行..."
    chmod +x "$BACKUP_SCRIPT"
fi

# ── 创建备份目录 ──
mkdir -p "$BACKUP_DIR"

# ── 检查 crontab 是否已存在相同条目（防重复添加） ──
if crontab -l 2>/dev/null | grep -Fq "$BACKUP_SCRIPT"; then
    echo "crontab 中已存在备份条目，跳过添加。"
    echo "当前条目如下："
    crontab -l | grep "$BACKUP_SCRIPT"
    exit 0
fi

# ── 添加 crontab 条目 ──
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "已添加 crontab 条目："
echo "  ${CRON_JOB}"

# ── 验证 ──
echo ""
echo "验证当前 crontab："
if crontab -l | grep -q "$BACKUP_SCRIPT"; then
    echo "  ✓ crontab 条目添加成功。"
    echo ""
    echo "备份将在明天凌晨 3:00 首次执行。"
    echo "日志文件：${CRON_LOG}"
    echo ""
    echo "手动测试备份："
    echo "  ${BACKUP_SCRIPT}"
else
    echo "  ✗ crontab 条目添加失败，请手动检查。"
    exit 1
fi
