"""认证路由 —— 邮箱注册/登录 + 微信登录 + 个人信息"""
import os
import uuid
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.security import HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.schemas.user import UserCreate, TokenResponse, UserResponse, WechatLoginRequest, ProfileUpdate, ChangePasswordRequest
from app.services.auth_service import hash_password, verify_password, create_token, revoke_token, get_token_jti, revoke_all_user_tokens
from app.middleware.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

AVATAR_DIR = os.path.join(settings.book_storage_path, "..", "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)

# 允许的头像 MIME 类型
ALLOWED_AVATAR_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

# ⽂件魔术字节签名 -> MIME 映射（用于内容类型验证）
MAGIC_BYTES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # WebP — RIFF + "WEBP" at offset 8
]


def _detect_image_mime(data: bytes) -> str | None:
    """Check magic bytes to detect actual image type."""
    for signature, mime in MAGIC_BYTES:
        if mime == "image/webp":
            # WebP: RIFF....WEBP
            if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                return mime
        else:
            if data.startswith(signature):
                return mime
    return None


@router.post("/register", status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    # 密码最小长度校验（Pydantic field_validator 已做完整校验，此处保留为防御纵深）
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="注册失败，请检查输入")
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        # 邮箱已存在 —— 返回相同的 201 状态码和消息体，防止邮箱枚举
        return {"message": "注册成功"}
    import random, string
    now = datetime.now(timezone.utc)
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name or f"读者{''.join(random.choices(string.ascii_lowercase, k=5))}",
        last_login_at=now,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"message": "注册成功"}


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/logout", status_code=200)
async def logout(
    credentials=Depends(HTTPBearer()),
    user: User = Depends(get_current_user),
):
    """登出 —— 吊销当前 JWT 令牌。"""
    jti = get_token_jti(credentials.credentials)
    if jti:
        revoke_token(jti)
    return {"message": "已登出"}


@router.post("/change-password", status_code=200)
async def change_password(
    data: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码 —— 验证旧密码后设置新密码，并吊销该用户所有现有令牌。"""
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    user.password_hash = hash_password(data.new_password)
    await db.commit()
    revoke_all_user_tokens(str(user.id))
    return {"message": "密码已修改，请重新登录"}


@router.post("/wechat-login", response_model=TokenResponse)
async def wechat_login(data: WechatLoginRequest, db: AsyncSession = Depends(get_db)):
    """微信小程序登录：用 code 换取 openid，首次登录自动注册"""
    # 1. 向微信服务器换取 openid
    wx_url = "https://api.weixin.qq.com/sns/jscode2session"
    async with httpx.AsyncClient() as client:
        resp = await client.get(wx_url, params={
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
            "js_code": data.code,
            "grant_type": "authorization_code",
        })
        wx_data = resp.json()

    openid = wx_data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail=f"微信登录失败: {wx_data.get('errmsg', '未知错误')}")

    # 2. 查找或创建用户
    result = await db.execute(select(User).where(User.wechat_openid == openid))
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            wechat_openid=openid,
            wechat_unionid=wx_data.get("unionid"),
            display_name=data.nickname or f"微信用户{openid[-6:]}",
            avatar_url=data.avatar_url,
            last_login_at=now,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # 更新昵称头像
        if data.nickname:
            user.display_name = data.nickname
        if data.avatar_url:
            user.avatar_url = data.avatar_url
        user.last_login_at = now
        await db.commit()

    token = create_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def get_profile(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.put("/profile", response_model=UserResponse)
async def update_profile(data: ProfileUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if data.display_name is not None:
        if len(data.display_name) > 100:
            raise HTTPException(status_code=400, detail="display_name 不能超过 100 个字符")
        user.display_name = data.display_name
    if data.avatar_url is not None: user.avatar_url = data.avatar_url
    await db.commit(); await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/avatar", response_model=UserResponse)
async def upload_avatar(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # 1. 校验 Content-Type 头
    if file.content_type not in ALLOWED_AVATAR_MIMES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的头像格式: {file.content_type}。仅支持 JPEG、PNG、GIF、WebP。",
        )

    # 2. 读文件内容
    content = await file.read()

    # 3. 文件大小校验
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="头像不能超过 2MB")

    # 4. 魔术字节校验 —— 确认文件确实是图片，防止 MIME 伪造
    detected_mime = _detect_image_mime(content)
    if detected_mime is None:
        raise HTTPException(status_code=400, detail="文件内容不是有效的图片格式")
    # 确保声明的 MIME 与实际内容一致
    if detected_mime != file.content_type:
        raise HTTPException(
            status_code=400,
            detail=f"文件实际格式 ({detected_mime}) 与声明的格式 ({file.content_type}) 不一致",
        )

    # 5. 安全写入
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    ext = ext_map[detected_mime]
    filename = f"{user.id}{ext}"
    filepath = os.path.join(AVATAR_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    user.avatar_url = f"/avatars/{filename}"
    await db.commit(); await db.refresh(user)
    return UserResponse.model_validate(user)
