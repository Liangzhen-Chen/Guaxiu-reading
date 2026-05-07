"""书籍路由 —— 导入、列表、删除"""
import os
import uuid
import logging
from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db, async_session
from app.models.user import User
from app.models.book import Book
from app.models.reading_progress import ReadingProgress
from app.schemas.book import BookResponse, BookListResponse
from app.middleware.auth import get_current_user
from app.services.parser_service import parse_document, save_parsed_text
from app.config import settings
from app.services.preprocess_service import parse_in_background, preprocess_book

logger = logging.getLogger("xiugua.books")
router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("", response_model=BookListResponse)
async def list_books(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取用户书架"""
    result = await db.execute(
        select(Book).where(Book.user_id == user.id).order_by(Book.created_at.desc())
        .options(selectinload(Book.progress))
    )
    books = result.scalars().all()
    items = []
    for b in books:
        pct = 0
        status_val = "not_started"
        if b.progress:
            pct = (b.progress.current_chapter / max(b.chapter_count or 1, 1)) * 100
            status_val = b.progress.status
        pp = b.preprocess_progress or {}
        items.append(BookResponse(
            id=b.id, title=b.title, author=b.author, category=None,
            cover_url=b.cover_url, file_format=b.file_format,
            file_size_bytes=b.file_size_bytes, token_count=b.token_count,
            chapter_count=b.chapter_count, parse_status=b.parse_status,
            preprocess_status=b.preprocess_status,
            preprocess_progress={"total_chapters": pp.get("total_chapters", b.chapter_count or 0), "completed_chapters": pp.get("completed_chapters", 0)},
            preprocess_done=pp.get("completed_chapters", 0),
            one_liner=b.one_liner,
            created_at=b.created_at, progress_status=status_val,
            progress_percent=int(pct),
        ))
    # Compute reading streak from all user's reading_progress.updated_at
    streak_count = 0
    try:
        rp_result = await db.execute(
            select(ReadingProgress.updated_at)
            .join(Book, ReadingProgress.book_id == Book.id)
            .where(Book.user_id == user.id, ReadingProgress.updated_at.isnot(None))
            .order_by(ReadingProgress.updated_at.desc())
        )
        raw_dates = [r[0].date() for r in rp_result.all() if r[0] is not None]
        unique_dates = sorted(set(raw_dates), reverse=True)
        streak_count = _compute_streak(unique_dates)
    except Exception:
        logger.warning("Failed to compute reading streak", exc_info=True)

    return BookListResponse(items=items, total=len(items), streak_count=streak_count)


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取单本书详情"""
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user.id)
        .options(selectinload(Book.progress))
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    pct = 0
    status_val = "not_started"
    if book.progress:
        pct = (book.progress.current_chapter / max(book.chapter_count or 1, 1)) * 100
        status_val = book.progress.status
    return BookResponse(
        id=book.id, title=book.title, author=book.author, category=book.category,
        cover_url=book.cover_url, file_format=book.file_format,
        file_size_bytes=book.file_size_bytes, token_count=book.token_count,
        chapter_count=book.chapter_count, parse_status=book.parse_status,
        preprocess_status=book.preprocess_status,
        preprocess_progress=book.preprocess_progress,
        one_liner=book.one_liner,
        created_at=book.created_at, progress_status=status_val,
        progress_percent=int(pct),
    )


@router.post("/upload", response_model=BookResponse, status_code=201)
async def upload_book(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传新书，立即返回，后台异步解析"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".epub", ".pdf", ".txt"):
        raise HTTPException(status_code=400, detail="支持 ePub / PDF / TXT 格式")

    book_id = uuid.uuid4()
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    os.makedirs(book_dir, exist_ok=True)
    raw_path = os.path.join(book_dir, f"original{ext}")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件不能超过 {settings.max_upload_size_mb}MB")
    if not _validate_magic_bytes(content, ext):
        raise HTTPException(status_code=400, detail=f"文件格式校验失败：扩展名 {ext} 与实际文件内容不匹配")
    with open(raw_path, "wb") as f:
        f.write(content)

    book = Book(
        id=book_id, user_id=user.id,
        title=title or os.path.splitext(file.filename or "未命名")[0],
        author=author or None,
        original_filename=file.filename or "",
        file_format=ext.lstrip("."),
        file_path=raw_path,
        file_size_bytes=len(content),
        parse_status="pending",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    # P5-2: Background task moved to preprocess_service
    background.add_task(parse_in_background, str(book_id), raw_path, file.filename or "", book.title)

    return BookResponse(
        id=book.id, title=book.title, author=book.author, category=book.category,
        cover_url=book.cover_url, file_format=book.file_format,
        file_size_bytes=book.file_size_bytes, token_count=book.token_count,
        chapter_count=book.chapter_count, parse_status=book.parse_status,
        preprocess_status=book.preprocess_status,
        preprocess_progress=book.preprocess_progress,
        one_liner=book.one_liner,
        created_at=book.created_at, progress_status="not_started", progress_percent=0,
    )


@router.post("/presign", status_code=200)
async def presign_upload(
    data: dict,
    user: User = Depends(get_current_user),
):
    """获取COS预签名上传URL"""
    from app.services.cos_service import get_presigned_upload
    try:
        result = get_presigned_upload(
            user_id=str(user.id),
            filename=data.get("filename", "book.epub"),
            file_type=data.get("file_type", "epub"),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"COS 上传配置失败: {str(e)}")


@router.post("/import-cos", response_model=BookResponse, status_code=201)
async def import_from_cos(
    background: BackgroundTasks,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """从COS导入书籍→下载→创建记录→后台解析"""
    from app.services.cos_service import download_from_cos, delete_from_cos
    key = data.get("key", "")
    filename = data.get("filename", "")
    if not key:
        raise HTTPException(status_code=400, detail="缺少COS key")

    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in (".epub", ".pdf", ".txt"):
        ext = ".epub" if "epub" in (filename or "").lower() else ".pdf" if "pdf" in (filename or "").lower() else ".txt"

    book_id = uuid.uuid4()
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    os.makedirs(book_dir, exist_ok=True)
    local_path = os.path.join(book_dir, f"original{ext}")

    if not download_from_cos(key, local_path):
        raise HTTPException(status_code=500, detail="COS 下载失败，请重试")

    try:
        delete_from_cos(key)
    except Exception:
        pass

    file_size = os.path.getsize(local_path)
    if file_size > settings.max_upload_size_mb * 1024 * 1024:
        os.remove(local_path)
        raise HTTPException(status_code=400, detail=f"文件不能超过 {settings.max_upload_size_mb}MB")

    with open(local_path, "rb") as _f:
        file_header = _f.read(4)
    if not _validate_magic_bytes(file_header, ext):
        os.remove(local_path)
        raise HTTPException(status_code=400, detail=f"文件格式校验失败：扩展名 {ext} 与实际文件内容不匹配")

    book = Book(
        id=book_id, user_id=user.id,
        title=data.get("title") or os.path.splitext(filename or "未命名")[0],
        author=data.get("author") or None,
        original_filename=filename or "",
        file_format=ext.lstrip("."),
        file_path=local_path,
        file_size_bytes=file_size,
        parse_status="pending",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    background.add_task(parse_in_background, str(book_id), local_path, filename or "", book.title)

    return BookResponse(
        id=book.id, title=book.title, author=book.author, category=book.category,
        cover_url=book.cover_url, file_format=book.file_format,
        file_size_bytes=book.file_size_bytes, token_count=book.token_count,
        chapter_count=book.chapter_count, parse_status=book.parse_status,
        preprocess_status=book.preprocess_status,
        preprocess_progress=book.preprocess_progress,
        one_liner=book.one_liner,
        created_at=book.created_at, progress_status="not_started", progress_percent=0,
    )


@router.post("/{book_id}/preprocess")
async def start_preprocess(
    book_id: uuid.UUID,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """触发"AI帮你读"：逐章预生成Wiki。前两章完成后标记ready。"""
    book = await _get_book_readonly(db, book_id, user.id)
    if book.parse_status != "done":
        raise HTTPException(status_code=400, detail="书籍尚未解析完成")
    if book.preprocess_status == "processing":
        raise HTTPException(status_code=400, detail="预处理进行中")
    if not book.text_path:
        raise HTTPException(status_code=400, detail="书籍文本不存在")

    await db.execute(
        update(Book).where(Book.id == book_id).values(preprocess_status="processing")
    )
    await db.commit()

    # P5-2: Background task moved to preprocess_service
    background.add_task(
        preprocess_book, str(book_id), book.title,
        book.text_path, book.chapter_count or 1,
    )

    return {
        "status": "started",
        "total_chapters": book.chapter_count,
        "message": "AI已开始逐章生成Wiki",
    }


@router.get("/{book_id}/preprocess/status")
async def get_preprocess_status(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """轮询预处理进度"""
    book = await _get_book_readonly(db, book_id, user.id)
    progress = book.preprocess_progress or {}
    return {
        "status": book.preprocess_status,
        "total_chapters": book.chapter_count,
        "completed_chapters": progress.get("completed_chapters", 0),
        "ready_to_read": book.preprocess_status == "ready",
    }


@router.delete("/{book_id}", status_code=204)
async def delete_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除书籍及其文件"""
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user.id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    import shutil
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    try:
        if os.path.exists(book_dir):
            shutil.rmtree(book_dir)
    except Exception:
        pass
    await db.delete(book)
    await db.commit()


# ── helpers ──

async def _get_book_readonly(db: AsyncSession, book_id: uuid.UUID, user_id: uuid.UUID) -> Book:
    result = await db.execute(select(Book).where(Book.id == book_id, Book.user_id == user_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return book


_MAGIC_BYTES = {
    ".pdf": (b"%PDF", 4),
    ".epub": (b"PK\x03\x04", 4),
}


def _validate_magic_bytes(content: bytes, ext: str) -> bool:
    """Validate file header matches expected magic bytes for the extension."""
    if ext in _MAGIC_BYTES:
        expected, length = _MAGIC_BYTES[ext]
        return content[:length] == expected
    return True  # txt: no magic byte validation


def _compute_streak(dates: list[date]) -> int:
    """Compute consecutive reading streak from descending unique dates."""
    if not dates:
        return 0
    today = date.today()
    if dates[0] != today and dates[0] != today - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i - 1] - dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak
