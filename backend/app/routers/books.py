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
        pp = b.preprocess_progress or {}
        items.append(BookResponse(
            id=b.id, title=b.title, author=b.author, category=None,  # don't send large blobs in list
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
            final_chapter_count = result["chapter_count"]

            # P1 FIRST: Generate one_liner + chapter validation (runs before old framework)
            p1_ok = False
            try:
                from app.services.socratic_service import _p
                from app.services.llm_service import chat as llm_chat
                from app.services.json_validator import extract_json

                # Build deduplicated regex chapter list
                import re as _re
                _pattern = r"(Part\s+[IVXLCDM]+|第[一二三四五六七八九十百千\d]+章|Chapter\s+\d+|CHAPTER\s+\d+)"
                _parts = _re.split(_pattern, result["text"])
                _seen = set()
                regex_chapters = []
                i = 1
                while i < len(_parts):
                    title = _parts[i].strip()
                    norm = _re.sub(r'\s+', ' ', title).upper()
                    if norm not in _seen:
                        _seen.add(norm)
                        snippet = (_parts[i + 1] if i + 1 < len(_parts) else "")[:60].strip().replace('\n', ' ')
                        regex_chapters.append(f"  {title} | {snippet}")
                    i += 2
                regex_list = "\n".join(regex_chapters) if regex_chapters else "（未检测到章标题）"

                # Sample text: skip front matter, include beginning + middle
                full_text = result["text"]
                text_sample = full_text[500:40000]  # skip potential ads/copyright
                if len(full_text) > 50000:
                    mid = len(full_text) // 2
                    text_sample += "\n...(书中段)...\n" + full_text[mid:mid+10000]

                p1_prompt = _p("p1_parse", "zh").replace("{regex_chapters}", regex_list)
                raw = await llm_chat(
                    [{"role": "system", "content": p1_prompt}, {"role": "user", "content": text_sample}],
                    temperature=0.3, max_tokens=8192,
                )
                p1_data = extract_json(raw)
                one_liner_val = p1_data.get("one_liner", "")
                category = _json.dumps(p1_data, ensure_ascii=False)
                # Keep only AI-validated chapters (compact format)
                keep_chapters = p1_data.get("keep_chapters", [])
                if not keep_chapters:
                    # Fallback: try old validated_chapters format
                    vc = p1_data.get("validated_chapters", [])
                    keep_chapters = [c["regex_title"] for c in vc if c.get("action") == "keep"]
                # Clean markers: remove snippet text after " | "
                keep_chapters = [c.split(" | ")[0].strip() for c in keep_chapters if c.strip()]
                if keep_chapters:
                    final_chapter_count = len(keep_chapters)
                    p1_ok = True
            except Exception as e:
                print(f"[P1] failed: {e}")

            # Fallback: old Prompt A framework (only if P1 failed)
            if not p1_ok:
                try:
                    from app.services.socratic_service import generate_chapter_structure
                    ch1_text = result["text"][:10000]
                    framework = await generate_chapter_structure(
                        book_title=title, chapter_index=1,
                        chapter_text=ch1_text, mode="quick", language="zh",
                    )
                    if isinstance(framework, dict) and "error" not in framework:
                        category = _json.dumps(framework, ensure_ascii=False)
                except Exception as fe:
                    parse_error_val = f"framework: {str(fe)[:200]}"

            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    text_path=text_path,
                    token_count=result["token_count"],
                    chapter_count=final_chapter_count,
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


from app.routers.reading import _extract_chapter_text, _get_chapter_markers


async def _fetch_google_toc(title: str, author: str) -> str:
    """尝试从 Google Books API 获取目录信息"""
    import urllib.request
    import urllib.parse
    import json as _json
    try:
        query = f'intitle:"{title}"'
        if author:
            query += f'+inauthor:"{author}"'
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(query)}&maxResults=3"
        req = urllib.request.Request(url, headers={"User-Agent": "Xiugua/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        items = data.get("items", [])
        if not items:
            return "（Google Books 未找到此书）"
        # Find best match with TOC
        for item in items:
            info = item.get("volumeInfo", {})
            toc = info.get("tableOfContents", "")
            if toc:
                book_title = info.get("title", "")
                return f"Google Books 找到《{book_title}》，目录如下：\n{toc[:3000]}"
        return "（Google Books 找到此书但无目录信息）"
    except Exception as e:
        return f"（Google Books API 查询失败: {str(e)[:100]}）"


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


import re as _re

def _fallback_wikis(text: str, min_concepts: int = 3) -> list[dict]:
    """Extract basic wiki concepts from text when LLM fails."""
    # Strategy: find lines that look like headings or contain key terms
    lines = text.strip().split('\n')
    candidates: list[tuple[str, str]] = []

    # Grab lines that look like definitions: "X is/refers to/means Y"
    for line in lines:
        line = line.strip()
        if len(line) < 10:
            continue
        # Match patterns: "X is ...", "X — ...", "X refers to ..."
        for pat in [r'^(.+?)是', r'^(.+?)指', r'^(.+?)—', r'^(.+?)：', r'^(.+?) is ', r'^(.+?) refers to']:
            m = _re.search(pat, line)
            if m:
                term = m.group(1).strip()
                if 2 <= len(term) <= 40 and term not in [c[0] for c in candidates]:
                    candidates.append((term, line[:200]))
                    break

    # If not enough heading-style candidates, take longest meaningful lines
    if len(candidates) < min_concepts:
        for line in lines[:100]:
            line = line.strip()
            if len(line) > 30 and len(line) < 300 and line not in [c[0] for c in candidates]:
                # Take first meaningful phrase as concept name
                phrase = line.split('。')[0].split('.')[0].strip()
                if len(phrase) > 4:
                    candidates.append((phrase[:40], line[:200]))
                if len(candidates) >= min_concepts:
                    break

    # Build wiki entries
    wikis = []
    for i, (name, context) in enumerate(candidates[:max(min_concepts, 5)]):
        wikis.append({
            "id": f"fb_{i+1}",
            "name": name,
            "content": context,
            "type": "concept",
            "quotes": [{"text": context, "context": "自动提取自原文"}]
        })
    return wikis or [{"id": "fb_1", "name": "本章导览", "content": text[:500], "type": "concept", "quotes": []}]


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
            # Get AI markers from book
            from sqlalchemy import select as _select
            book_obj = (await db.execute(_select(Book).where(Book.id == book_id))).scalar_one_or_none()
            markers = _get_chapter_markers(book_obj) if book_obj else None

            with open(text_path, "r", encoding="utf-8") as f:
                full_text = f.read()

            for ch in range(1, total_chapters + 1):
                ch_text = _extract_chapter_text(full_text, ch, total_chapters, markers)
                if not ch_text.strip():
                    continue

                prompt = _p("p2_wikis", "zh")
                prompt = prompt.replace("{book_title}", title)
                prompt = prompt.replace("{chapter_index}", str(ch))

                wiki_data = None
                for attempt in range(3):  # Retry up to 3 times
                    raw = await chat(
                        [{"role": "system", "content": prompt}, {"role": "user", "content": ch_text[:30000]}],
                        temperature=0.3 + attempt * 0.15, max_tokens=4096,
                    )
                    try:
                        wiki_data = extract_json(raw)
                        wikis = wiki_data.get("wikis", [])
                        if not wikis:
                            # Empty wikis — force retry with stronger instruction
                            prompt_retry = prompt + "\n\n⚠️ 上一轮你返回了空的 wikis 数组。必须基于本章文本提取至少 3 个概念。"
                            prompt = prompt_retry  # use this for remaining attempts
                            continue
                        break
                    except ValueError:
                        continue  # JSON parse failed, retry

                if wiki_data:
                    chapter_wikis[str(ch)] = wiki_data
                    progress["completed_chapters"] = ch

                    # Keep processing, mark ready_to_read after 2 chapters
                    pp_data = {**progress, "chapter_wikis": chapter_wikis, "ready_to_read": ch >= 2}
                    await db.execute(
                        update(Book).where(Book.id == book_id).values(
                            preprocess_status="ready" if ch >= 2 else "processing",
                            preprocess_progress=pp_data,
                        )
                    )
                    await db.commit()
                else:
                    # All retries exhausted — generate minimal fallback wikis from text
                    print(f"WARNING: Chapter {ch} wiki generation failed after 3 attempts, using fallback")
                    fallback = {
                        "chapter_index": ch,
                        "chapter_title": f"第{ch}章",
                        "chapter_summary": ch_text[:500],
                        "wikis": _fallback_wikis(ch_text)
                    }
                    chapter_wikis[str(ch)] = fallback
                    progress["completed_chapters"] = ch
                    pp_data = {**progress, "chapter_wikis": chapter_wikis, "ready_to_read": ch >= 2}
                    await db.execute(
                        update(Book).where(Book.id == book_id).values(
                            preprocess_status="ready" if ch >= 2 else "processing",
                            preprocess_progress=pp_data,
                        )
                    )
                    await db.commit()

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
    # 删除文件（忽略错误，确保 DB 记录一定删除）
    import shutil
    book_dir = os.path.join(settings.book_storage_path, str(book_id))
    try:
        if os.path.exists(book_dir):
            shutil.rmtree(book_dir)
    except Exception:
        pass
    await db.delete(book)
    await db.commit()
