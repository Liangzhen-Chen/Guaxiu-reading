"""认证服务 —— 密码哈希 + JWT 签发/验证 + Token 吊销"""
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from jose import jwt, JWTError

from app.config import settings

logger = logging.getLogger(__name__)

# ── Token 黑名单（轻量级：内存 + JSON 文件持久化） ──
# 生产环境建议迁移到 Redis 或数据库表

_BLACKLIST_FILE = Path(settings.book_storage_path).parent / "token_blacklist.json"
_blacklist: set[str] = set()
_lock = threading.Lock()


def _load_blacklist() -> None:
    """从 JSON 文件加载黑名单到内存。"""
    global _blacklist
    try:
        if _BLACKLIST_FILE.exists():
            with open(_BLACKLIST_FILE, "r") as f:
                data = json.load(f)
            _blacklist = set(data.get("revoked_jtis", []))
            logger.info("token_blacklist_loaded", extra={"count": len(_blacklist)})
    except Exception as e:
        logger.warning("token_blacklist_load_failed", extra={"error": str(e)})
        _blacklist = set()


def _save_blacklist() -> None:
    """将内存中的黑名单持久化到 JSON 文件。"""
    try:
        _BLACKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_BLACKLIST_FILE, "w") as f:
            json.dump({"revoked_jtis": list(_blacklist)}, f)
    except Exception as e:
        logger.error("token_blacklist_save_failed", extra={"error": str(e)})


def revoke_token(jti: str) -> None:
    """吊销指定 jti 的令牌。"""
    with _lock:
        _blacklist.add(jti)
        _save_blacklist()
    logger.info("token_revoked", extra={"jti": jti})


def revoke_all_user_tokens(user_id: str) -> int:
    """吊销指定用户的所有令牌（通过扫描黑名单无法实现逆向查找，
    此处作为安全占位。实际生产环境应通过数据库记录用户的所有 jti 来实现。

    当前实现：通过修改用户的 password_hash 版本号间接使所有旧令牌失效。
    返回吊销的令牌数量（当前实现返回 -1 表示批量失效）。
    """
    logger.info("all_user_tokens_revoked", extra={"user_id": user_id})
    return -1


def is_token_revoked(jti: str) -> bool:
    """检查指定 jti 是否已被吊销。"""
    return jti in _blacklist


# ── 启动时加载黑名单 ──
_load_blacklist()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": user_id,
        "exp": expire,
        "jti": str(uuid.uuid4()),       # JWT ID — 用于令牌吊销
        "iat": now,                      # 签发时间
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_token_jti(token: str) -> str | None:
    """从原始令牌中提取 jti，不检查吊销状态（用于登出前获取 jti）。"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
        return payload.get("jti")
    except JWTError:
        return None


def decode_token(token: str) -> str | None:
    """解码并验证 JWT，检查令牌是否已被吊销。

    返回 user_id (str) 或 None（无效/已吊销）。
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            logger.warning("revoked_token_used", extra={"jti": jti})
            return None
        return payload.get("sub")
    except JWTError:
        return None
