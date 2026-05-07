"""埋点 + 反馈路由"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.analytics_event import AnalyticsEvent
from app.models.feedback import Feedback
from app.middleware.auth import get_optional_user, get_current_user
from app.models.user import User
from app.config import settings


class FeedbackCreate(BaseModel):
    """反馈提交 —— 带字段最大长度限制。"""
    content: str = Field(..., min_length=1, max_length=2000)
    contact: str | None = Field(None, max_length=200)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.post("/event", status_code=201)
async def track_event(request: Request, db: AsyncSession = Depends(get_db), user = Depends(get_optional_user)):
    data = await request.json()
    db.add(AnalyticsEvent(user_id=str(user.id) if user else None, event=data["event"], page=data.get("page"), props=data.get("props"), duration_ms=data.get("duration_ms")))
    await db.commit()

@router.post("/feedback", status_code=201)
async def feedback(data: FeedbackCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """提交反馈 —— 需登录，content/contact 有长度限制。"""
    db.add(Feedback(user_id=str(user.id), content=data.content, contact=data.contact))
    await db.commit()
    return {"ok": True}

@router.get("/dashboard")
async def dashboard(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """管理员看板 —— 仅 admin_emails 白名单内用户可访问。"""
    if user.email not in settings.admin_emails:
        raise HTTPException(status_code=403, detail="Forbidden")
    # 事件总数
    r1 = await db.execute(select(func.count(AnalyticsEvent.id)))
    total = r1.scalar()

    # 各事件类型数
    r2 = await db.execute(
        select(AnalyticsEvent.event, func.count(AnalyticsEvent.id))
        .group_by(AnalyticsEvent.event).order_by(func.count(AnalyticsEvent.id).desc())
    )
    events = [{"event": e, "count": c} for e, c in r2.all()]

    # 满意度
    r3 = await db.execute(
        select(AnalyticsEvent.props["ok"].astext, func.count(AnalyticsEvent.id))
        .where(AnalyticsEvent.event == "satisfaction").group_by(AnalyticsEvent.props["ok"].astext)
    )
    satisfaction = {"up": 0, "down": 0}
    for k, c in r3.all():
        satisfaction["up" if k == "true" else "down"] = satisfaction.get("up" if k == "true" else "down", 0) + c

    # 反馈列表
    r4 = await db.execute(select(Feedback).order_by(Feedback.created_at.desc()).limit(20))
    feedbacks = [{"content": f.content, "contact": f.contact, "time": str(f.created_at)} for f in r4.scalars().all()]

    return {"total_events": total, "events": events, "satisfaction": satisfaction, "feedbacks": feedbacks}
