#!/bin/bash
# =============================================================================
# 朽瓜（Xiugua）PostgreSQL 每日备份脚本
# =============================================================================
# 功能：
#   1. 从 .env 或环境变量读取数据库连接信息
#   2. 使用 pg_dump 导出数据库并 gzip 压缩
#   3. 保留最近 7 天备份，自动清理过期文件
#
# 用法：
#   ./backup-db.sh                          # 自动从 .env 文件读取配置
#   DATABASE_URL=... ./backup-db.sh         # 手动指定连接串
#
# 备份文件：
#   /opt/xiugua/backups/xiugua_backup_2026-05-07.sql.gz
#
# 从 .env 解析时，DATABASE_URL 格式示例：
#   postgresql+asyncpg://user:password@host:port/dbname
#
# 恢复命令示例：
#   gunzip -c /opt/xiugua/backups/xiugua_backup_2026-05-07.sql.gz | \
#     psql -h localhost -U chenliangzhen -d xiugua
# =============================================================================
#
# ── 中长期建议 ──
# 当前备份方案为本地 crontab + pg_dump，存在单点风险（服务器磁盘故障时备份一同丢失）。
# 建议迁移至腾讯云 PostgreSQL（云数据库），享受：
#   - 自动每日备份（可配置保留天数）
#   - 按时间点恢复（PITR，精确到秒级）
#   - 跨可用区高可用
#   - 备份存储于 COS，与计算节点解耦
# 迁移步骤：创建腾讯云 PostgreSQL 实例 → 修改 backend/.env 中的 DATABASE_URL → 下线本地 PostgreSQL。
# ──

set -euo pipefail

# ── 配置 ──
BACKUP_DIR="/opt/xiugua/backups"
RETENTION_DAYS=7
DATE_STR=$(date +%Y-%m-%d)
BACKUP_FILE="${BACKUP_DIR}/xiugua_backup_${DATE_STR}.sql.gz"
LOCK_FILE="${BACKUP_DIR}/.backup.lock"
LOG_FILE="${BACKUP_DIR}/cron.log"     # 被 setup-cron.sh 的 crontab 重写覆盖，此处作为 fallback

# ── 前置检查 ──
# 如果已在运行，退出（防重入）
if [ -f "$LOCK_FILE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN: 另一个备份进程正在运行（锁文件存在），跳过本次执行。" >> "$LOG_FILE"
    exit 0
fi

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 写入锁文件（带进程 ID，方便调试）
echo "$$" > "$LOCK_FILE"

# 清理锁文件（无论成功或失败）
cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# ── 解析数据库连接信息 ──
# 优先级：环境变量 DATABASE_URL > .env 文件
if [ -n "${DATABASE_URL:-}" ]; then
    RAW_URL="$DATABASE_URL"
else
    # 从 .env 文件查找 DATABASE_URL（脚本所在目录的上级 app/ 目录）
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    ENV_FILE="${SCRIPT_DIR}/../.env"

    if [ -f "$ENV_FILE" ]; then
        RAW_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | sed 's/^DATABASE_URL=//' | tr -d '"'"'" | head -1)
    fi
fi

if [ -z "${RAW_URL:-}" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: 无法获取 DATABASE_URL。请设置环境变量或确保 .env 文件存在。" >> "$LOG_FILE"
    exit 1
fi

# pg_dump 不支持 asyncpg 协议，将 postgresql+asyncpg:// 转换为 postgresql://
PG_URL=$(echo "$RAW_URL" | sed 's/^postgresql+asyncpg:\/\//postgresql:\/\//')

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始备份数据库..." >> "$LOG_FILE"

# ── 执行备份 ──
# 使用 pg_dump 导出，gzip 压缩
# PGPASSWORD 用于非交互式密码认证
# shellcheck disable=SC2086
if pg_dump "$PG_URL" --no-owner --clean --if-exists 2>> "$LOG_FILE" | gzip > "$BACKUP_FILE"; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份完成: ${BACKUP_FILE} (${BACKUP_SIZE})" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: pg_dump 失败，请检查数据库连接和权限。" >> "$LOG_FILE"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# ── 清理旧备份（仅保留最近 RETENTION_DAYS 天） ──
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 清理 ${RETENTION_DAYS} 天前的旧备份..." >> "$LOG_FILE"
find "$BACKUP_DIR" -name 'xiugua_backup_*.sql.gz' -type f -mtime +${RETENTION_DAYS} -delete -print >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 备份流程全部完成。" >> "$LOG_FILE"
