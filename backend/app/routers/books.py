"""书籍路由 —— 导入、列表、删除"""
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks
from sqlalchemy import select, func, update
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
        items.append(BookResponse(
            id=b.id, title=b.title, author=b.author, category=b.category,
            cover_url=b.cover_url, file_format=b.file_format,
            file_size_bytes=b.file_size_bytes, token_count=b.token_count,
            chapter_count=b.chapter_count, parse_status=b.parse_status,
            preprocess_status=b.preprocess_status,
            preprocess_progress=b.preprocess_progress,
            one_liner=b.one_liner,
            created_at=b.created_at, progress_status=status_val,
            progress_percent=int(pct),
        ))
    return BookListResponse(items=items, total=len(items))


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

    background.add_task(_parse_in_background, str(book_id), raw_path, file.filename or "", book.title)

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


async def _parse_in_background(book_id: str, raw_path: str, filename: str, title: str):
    """后台解析文档 + 生成章节框架。CPU 密集部分在线程池运行，不阻塞事件循环。"""
    import json as _json
    import asyncio

    # Step 1: CPU-heavy parsing in thread pool
    async def _do_parse():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _parse_sync, raw_path, filename)

    try:
        result = await _do_parse()
    except Exception as e:
        async with async_session() as db:
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    parse_status="failed",
                    parse_error=f"文档解析失败: {str(e)[:400]}",
                )
            )
            await db.commit()
        return

    # Step 2: DB operations in main event loop
    async with async_session() as db:
        try:
            text_path = await save_parsed_text(result["text"], book_id)

            parse_error_val = None
            category = None
            one_liner_val = None
            try:
                from app.services.socratic_service import generate_chapter_structure
                ch1_text = result["text"][:10000]
                framework = await generate_chapter_structure(
                    book_title=title, chapter_index=1,
                    chapter_text=ch1_text, mode="quick", language="zh",
                )
                if isinstance(framework, dict) and "error" in framework:
                    raise ValueError(framework.get("error", "未返回有效 JSON"))
                category = _json.dumps(framework, ensure_ascii=False)
            except Exception as fe:
                parse_error_val = f"framework: {str(fe)[:200]}"

            # P1: Generate one_liner
            try:
                from app.services.socratic_service import _p
                from app.services.llm_service import chat as llm_chat
                from app.services.json_validator import extract_json
                p1_prompt = _p("p1_parse", "zh")
                raw = await llm_chat(
                    [{"role": "system", "content": p1_prompt}, {"role": "user", "content": result["text"][:30000]}],
                    temperature=0.3, max_tokens=2048,
                )
                p1_data = extract_json(raw)
                one_liner_val = p1_data.get("one_liner", "")
            except Exception:
                pass

            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    text_path=text_path,
                    token_count=result["token_count"],
                    chapter_count=result["chapter_count"],
                    category=category,
                    one_liner=one_liner_val,
                    parse_status="done",
                    parse_error=parse_error_val,
                )
            )
            await db.commit()
        except Exception as e:
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    parse_status="failed",
                    parse_error=str(e)[:500],
                )
            )
            await db.commit()


async def _get_book_readonly(db: AsyncSession, book_id: uuid.UUID, user_id: uuid.UUID) -> Book:
    result = await db.execute(select(Book).where(Book.id == book_id, Book.user_id == user_id))
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return book


def _extract_chapter_text(full_text: str, chapter: int, total_chapters: int) -> str:
    import re
    pattern = r"(第[一二三四五六七八九十百千\d]+章|Chapter\s+\d+|CHAPTER\s+\d+)"
    parts = re.split(pattern, full_text)
    if len(parts) > 2:
        chapters = []
        i = 1
        while i < len(parts):
            chapters.append(parts[i] + (parts[i + 1] if i + 1 < len(parts) else ""))
            i += 2
        if chapter <= len(chapters):
            return chapters[chapter - 1]
    chunk_size = len(full_text) // max(total_chapters, 1)
    start = (chapter - 1) * chunk_size
    end = start + chunk_size if chapter < total_chapters else len(full_text)
    return full_text[start:end]


def _parse_sync(raw_path: str, filename: str) -> dict:
    """同步解析文档，在线程池中运行"""
    import asyncio
    return asyncio.run(parse_document(raw_path, filename))


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
    if not book.text_path:
        raise HTTPException(status_code=400, detail="书籍文本不存在")

    await db.execute(
        update(Book).where(Book.id == book_id).values(preprocess_status="processing")
    )
    await db.commit()

    background.add_task(_preprocess_book, str(book_id), book.title, book.text_path, book.chapter_count or 1)

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


async def _preprocess_book(book_id: str, title: str, text_path: str, total_chapters: int):
    """后台逐章调用 P2 生成 Wiki"""
    import json as _json
    from app.services.socratic_service import _p
    from app.services.llm_service import chat
    from app.services.json_validator import extract_json

    progress = {"total_chapters": total_chapters, "completed_chapters": 0, "chapter_wikis": {}}
    chapter_wikis = {}

    async with async_session() as db:
        try:
            with open(text_path, "r", encoding="utf-8") as f:
                full_text = f.read()

            for ch in range(1, total_chapters + 1):
                ch_text = _extract_chapter_text(full_text, ch, total_chapters)
                if not ch_text.strip():
                    continue

                prompt = _p("p2_wikis", "zh")
                prompt = prompt.replace("{book_title}", title)
                prompt = prompt.replace("{chapter_index}", str(ch))

                raw = await chat(
                    [{"role": "system", "content": prompt}, {"role": "user", "content": ch_text[:30000]}],
                    temperature=0.3, max_tokens=4096,
                )
                try:
                    wiki_data = extract_json(raw)
                    chapter_wikis[str(ch)] = wiki_data
                    progress["completed_chapters"] = ch

                    # Mark ready after 2 chapters
                    if ch >= 2 and progress.get("completed_chapters", 0) >= 2:
                        await db.execute(
                            update(Book).where(Book.id == book_id).values(
                                preprocess_status="ready",
                                preprocess_progress={**progress, "chapter_wikis": chapter_wikis},
                            )
                        )
                    else:
                        await db.execute(
                            update(Book).where(Book.id == book_id).values(
                                preprocess_progress={**progress, "chapter_wikis": chapter_wikis},
                            )
                        )
                    await db.commit()
                except ValueError:
                    continue  # Skip failed chapter, keep processing

            # All chapters done
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    preprocess_status="ready",
                    preprocess_progress={**progress, "chapter_wikis": chapter_wikis},
                )
            )
            await db.commit()
        except Exception as e:
            print(f"Preprocess failed for book {book_id}: {e}")


@router.delete("/{book_id}", status_code=204)
async def delete_book(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user.id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    # 删除文件
    import shutil
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    if os.path.exists(book_dir):
        shutil.rmtree(book_dir)
    await db.delete(book)
    await db.commit()
