"""埋点 + 反馈路由 + 运营数据分析"""
import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.analytics_event import AnalyticsEvent
from app.models.feedback import Feedback
from app.models.user import User
from app.models.book import Book
from app.middleware.auth import get_optional_user, get_current_user
from app.config import settings

logger = logging.getLogger(__name__)


class FeedbackCreate(BaseModel):
    """反馈提交 —— 带字段最大长度限制。"""
    content: str = Field(..., min_length=1, max_length=2000)
    contact: str | None = Field(None, max_length=200)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ── Helpers ──

def _admin_guard(user: User) -> None:
    """Raise 403 if user is not in admin_emails."""
    if user.email not in settings.admin_emails:
        raise HTTPException(status_code=403, detail="Forbidden")


def _tz_now() -> datetime:
    """Current UTC datetime with timezone."""
    return datetime.now(timezone.utc)


def _start_of_day(dt: datetime | None = None) -> datetime:
    """Start of the current UTC day."""
    dt = dt or _tz_now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_month(dt: datetime | None = None) -> datetime:
    """Start of the current UTC month."""
    dt = dt or _tz_now()
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ── Event tracking (public) ──


@router.post("/event", status_code=201)
async def track_event(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_optional_user),
):
    data = await request.json()
    db.add(
        AnalyticsEvent(
            user_id=str(user.id) if user else None,
            event=data["event"],
            page=data.get("page"),
            props=data.get("props"),
            duration_ms=data.get("duration_ms"),
        )
    )
    await db.commit()


@router.post("/feedback", status_code=201)
async def feedback(
    data: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交反馈 —— 需登录，content/contact 有长度限制。"""
    db.add(Feedback(user_id=str(user.id), content=data.content, contact=data.contact))
    await db.commit()
    return {"ok": True}


# ── Dashboard (admin) ──


@router.get("/dashboard")
async def dashboard(
    days: int = Query(7, ge=1, le=365, description="返回最近 N 天的数据"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """管理员看板 —— 仅 admin_emails 白名单内用户可访问。支持 ?days=7 参数。"""
    _admin_guard(user)

    now = _tz_now()
    cutoff = now - timedelta(days=days)
    today_start = _start_of_day(now)
    month_start = _start_of_month(now)

    # ── 1. 总事件数 ──
    r1 = await db.execute(select(func.count(AnalyticsEvent.id)))
    total_events: int = r1.scalar() or 0

    # ── 2. 各事件类型数（全部时间） ──
    r2 = await db.execute(
        select(AnalyticsEvent.event, func.count(AnalyticsEvent.id))
        .group_by(AnalyticsEvent.event)
        .order_by(func.count(AnalyticsEvent.id).desc())
    )
    events = [{"event": e, "count": c} for e, c in r2.all()]

    # ── 3. 今日事件数 ──
    r_today = await db.execute(
        select(func.count(AnalyticsEvent.id)).where(
            AnalyticsEvent.created_at >= today_start
        )
    )
    today_events: int = r_today.scalar() or 0

    # ── 4. 满意度 ──
    r3 = await db.execute(
        select(AnalyticsEvent.props["ok"].astext, func.count(AnalyticsEvent.id))
        .where(AnalyticsEvent.event == "satisfaction")
        .group_by(AnalyticsEvent.props["ok"].astext)
    )
    satisfaction = {"up": 0, "down": 0}
    for k, c in r3.all():
        satisfaction["up" if k == "true" else "down"] = (
            satisfaction.get("up" if k == "true" else "down", 0) + c
        )

    # ── 5. DAU / MAU ──
    r_dau = await db.execute(
        select(func.count(func.distinct(User.id))).where(
            User.last_login_at >= today_start
        )
    )
    dau: int = r_dau.scalar() or 0

    r_mau = await db.execute(
        select(func.count(func.distinct(User.id))).where(
            User.last_login_at >= month_start
        )
    )
    mau: int = r_mau.scalar() or 0

    # ── 6. 阅读时长（reading_session 事件） ──
    r_reading_total = await db.execute(
        select(func.coalesce(func.sum(AnalyticsEvent.duration_ms), 0)).where(
            AnalyticsEvent.event == "reading_session"
        )
    )
    total_reading_ms: int = r_reading_total.scalar() or 0
    total_reading_minutes = round(total_reading_ms / 60000, 1)

    r_reading_today = await db.execute(
        select(func.coalesce(func.sum(AnalyticsEvent.duration_ms), 0)).where(
            AnalyticsEvent.event == "reading_session",
            AnalyticsEvent.created_at >= today_start,
        )
    )
    today_reading_ms: int = r_reading_today.scalar() or 0
    today_reading_minutes = round(today_reading_ms / 60000, 1)

    # ── 7. 最近 N 天事件趋势 ──
    r_trend = await db.execute(
        select(
            func.date_trunc("day", AnalyticsEvent.created_at).label("day"),
            func.count(AnalyticsEvent.id),
        )
        .where(AnalyticsEvent.created_at >= cutoff)
        .group_by(text("day"))
        .order_by(text("day"))
    )
    trend = [{"date": str(d), "count": c} for d, c in r_trend.all()]

    # ── 8. 反馈列表 ──
    r4 = await db.execute(
        select(Feedback).order_by(Feedback.created_at.desc()).limit(20)
    )
    feedbacks = [
        {"content": f.content, "contact": f.contact, "time": str(f.created_at)}
        for f in r4.scalars().all()
    ]

    return {
        "total_events": total_events,
        "today_events": today_events,
        "events": events,
        "satisfaction": satisfaction,
        "dau": dau,
        "mau": mau,
        "total_reading_minutes": total_reading_minutes,
        "today_reading_minutes": today_reading_minutes,
        "trend": trend,
        "feedbacks": feedbacks,
    }


# ── 转化漏斗 (admin) ──


@router.get("/funnel")
async def funnel(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """转化漏斗 —— 仅 admin 可访问。"""
    _admin_guard(user)

    # 1. 注册用户总数
    r1 = await db.execute(select(func.count(User.id)))
    total_users: int = r1.scalar() or 0

    # 2. 导入过书的用户数
    r2 = await db.execute(
        select(func.count(func.distinct(Book.user_id)))
    )
    imported_users: int = r2.scalar() or 0

    # 3. 开始阅读的用户数（有 reading_progress 且 status != not_started）
    r3 = await db.execute(
        text("""
            SELECT COUNT(DISTINCT b.user_id)
            FROM books b
            INNER JOIN reading_progress rp ON rp.book_id = b.id
            WHERE rp.status != 'not_started'
        """)
    )
    started_users: int = r3.scalar() or 0

    # 4. 完成至少一章的用户数（current_chapter>1 或 status=completed）
    r4 = await db.execute(
        text("""
            SELECT COUNT(DISTINCT b.user_id)
            FROM books b
            INNER JOIN reading_progress rp ON rp.book_id = b.id
            WHERE rp.current_chapter > 1 OR rp.status = 'completed'
        """)
    )
    chapter_completed_users: int = r4.scalar() or 0

    # 5. 完成过一本书的用户数
    r5 = await db.execute(
        text("""
            SELECT COUNT(DISTINCT b.user_id)
            FROM books b
            INNER JOIN reading_progress rp ON rp.book_id = b.id
            WHERE rp.status = 'completed'
        """)
    )
    book_completed_users: int = r5.scalar() or 0

    return {
        "total_users": total_users,
        "imported_users": imported_users,
        "started_users": started_users,
        "chapter_completed_users": chapter_completed_users,
        "book_completed_users": book_completed_users,
    }


# ── 数据导出 (admin) ──


@router.get("/export")
async def export_data(
    type: str = Query("events", regex="^(events|feedback)$"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """管理员导出埋点或反馈 CSV。"""
    _admin_guard(user)

    cutoff = _tz_now() - timedelta(days=days)
    output = io.StringIO()
    writer = csv.writer(output)

    if type == "events":
        writer.writerow(["id", "user_id", "event", "page", "props", "duration_ms", "created_at"])
        r = await db.execute(
            select(AnalyticsEvent)
            .where(AnalyticsEvent.created_at >= cutoff)
            .order_by(AnalyticsEvent.created_at.desc())
        )
        for ev in r.scalars().all():
            writer.writerow([
                str(ev.id),
                ev.user_id or "",
                ev.event,
                ev.page or "",
                str(ev.props) if ev.props else "",
                ev.duration_ms or "",
                str(ev.created_at),
            ])
    else:
        writer.writerow(["id", "user_id", "content", "contact", "created_at"])
        r = await db.execute(
            select(Feedback)
            .where(Feedback.created_at >= cutoff)
            .order_by(Feedback.created_at.desc())
        )
        for fb in r.scalars().all():
            writer.writerow([
                str(fb.id),
                fb.user_id or "",
                fb.content,
                fb.contact or "",
                str(fb.created_at),
            ])

    csv_content = output.getvalue()
    filename = f"{type}_{_tz_now().strftime('%Y%m%d')}.csv"
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
