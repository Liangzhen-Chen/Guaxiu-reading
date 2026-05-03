"""认证路由 —— 邮箱注册/登录 + 微信登录 + 个人信息"""
import os, uuid, httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, TokenResponse, UserResponse, WechatLoginRequest, ProfileUpdate
from app.services.auth_service import hash_password, verify_password, create_token
from app.middleware.auth import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

AVATAR_DIR = os.path.join(settings.book_storage_path, "..", "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="此邮箱已注册")
    import random, string
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name or f"读者{''.join(random.choices(string.ascii_lowercase, k=5))}",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
async def login(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


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

    if user is None:
        user = User(
            wechat_openid=openid,
            wechat_unionid=wx_data.get("unionid"),
            display_name=data.nickname or f"微信用户{openid[-6:]}",
            avatar_url=data.avatar_url,
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
        await db.commit()

    token = create_token(str(user.id))
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
async def get_profile(user: User = Depends(get_current_user)):
    return UserResponse.model_validate(user)


@router.put("/profile", response_model=UserResponse)
async def update_profile(data: ProfileUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if data.display_name is not None: user.display_name = data.display_name
    if data.avatar_url is not None: user.avatar_url = data.avatar_url
    await db.commit(); await db.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/avatar", response_model=UserResponse)
async def upload_avatar(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    ext = os.path.splitext(file.filename or ".png")[1] or ".png"
    filename = f"{user.id}{ext}"
    filepath = os.path.join(AVATAR_DIR, filename)
    content = await file.read()
    if len(content) > 2 * 1024 * 1024: raise HTTPException(status_code=400, detail="头像不能超过 2MB")
    with open(filepath, "wb") as f: f.write(content)
    user.avatar_url = f"/avatars/{filename}"
    await db.commit(); await db.refresh(user)
    return UserResponse.model_validate(user)
