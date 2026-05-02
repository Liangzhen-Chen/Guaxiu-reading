"""埋点路由"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.analytics_event import AnalyticsEvent
from app.middleware.auth import get_optional_user

from app.models.feedback import Feedback

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.post("/event", status_code=201)
async def track_event(request: Request, db: AsyncSession = Depends(get_db), user = Depends(get_optional_user)):
    data = await request.json()
    db.add(AnalyticsEvent(user_id=str(user.id) if user else None, event=data["event"], page=data.get("page"), props=data.get("props"), duration_ms=data.get("duration_ms")))
    await db.commit()


@router.post("/feedback", status_code=201)
async def submit_feedback(request: Request, db: AsyncSession = Depends(get_db), user = Depends(get_optional_user)):
    data = await request.json()
    db.add(Feedback(user_id=str(user.id) if user else None, content=data["content"], contact=data.get("contact")))
    await db.commit()
    return {"ok": True}
