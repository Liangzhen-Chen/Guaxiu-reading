"""导读路由 —— 核心：苏格拉底式流式对话"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.models.book import Book
from app.models.conversation import Conversation
from app.models.reading_progress import ReadingProgress
from app.models.wiki import WikiEntry
from app.schemas.reading import (
    ModeSelection, AssessmentRequest, AssessmentResponse,
    ReadingRequest, ProgressResponse
)
from app.middleware.auth import get_current_user
from app.services.socratic_service import (
    get_socratic_prompt, build_context, extract_concepts,
    generate_assessment_question, generate_chapter_structure,
    socratic_chat_stream, _p,
)
from app.services.llm_service import chat, chat_stream, count_tokens

router = APIRouter(prefix="/api/reading", tags=["reading"])

ASSESSMENT_CHAPTER = -1


@router.post("/mode", response_model=ProgressResponse)
async def select_mode(
    data: ModeSelection,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """选择阅读模式，开始或继续导读"""
    book = await _get_book(db, data.book_id, user.id)
    progress = book.progress
    if progress is None:
        progress = ReadingProgress(
            book_id=book.id, mode=data.mode, status="assessment",
            language=data.language,
        )
        db.add(progress)
    else:
        progress.mode = data.mode
    await db.commit()
    await db.refresh(progress)
    return _to_progress_response(book, progress)


@router.post("/assessment")
async def assessment(
    data: AssessmentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """背景评估对话 (Prompt D)，3-5 轮后自动输出用户画像并进入 reading 状态"""
    book = await _get_book(db, data.book_id, user.id)

    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == ASSESSMENT_CHAPTER,
        ).order_by(Conversation.round_index)
    )
    history = [{"role": m.role, "content": m.content} for m in prev.scalars().all()]

    round_idx = len([m for m in history if m["role"] == "user"])
    db.add(Conversation(
        book_id=book.id, chapter_index=ASSESSMENT_CHAPTER,
        round_index=round_idx, role="user", content=data.message
    ))
    history.append({"role": "user", "content": data.message})

    ai_response = await generate_assessment_question(
        book_title=book.title, author=book.author or "未知",
        category=book.category or "通用", conversation_history=history,
        language=book.progress.language if book.progress else "zh",
    )

    db.add(Conversation(
        book_id=book.id, chapter_index=ASSESSMENT_CHAPTER,
        round_index=round_idx + 1, role="assistant", content=ai_response
    ))

    assessment_complete = False
    try:
        result = json.loads(ai_response)
        if result.get("assessment_complete"):
            assessment_complete = True
            progress = book.progress
            if progress:
                progress.status = "reading"
                progress.assessment_result = json.dumps(
                    {"profile": result.get("profile", {}), "chapter_frameworks": {}},
                    ensure_ascii=False,
                )
    except (json.JSONDecodeError, TypeError):
        assessment_complete = round_idx >= 2

    if assessment_complete and book.progress and book.progress.status != "reading":
        book.progress.status = "reading"
        if book.progress.current_chapter == 0:
            book.progress.current_chapter = 1
        # Eagerly generate chapter 1 framework so /resume has concepts
        try:
            if book.text_path:
                with open(book.text_path, "r", encoding="utf-8") as f:
                    ch1_text = _extract_chapter_text(f.read(), 1, book.chapter_count or 1)
                framework = await generate_chapter_structure(
                    book_title=book.title, chapter_index=1,
                    chapter_text=ch1_text, mode=book.progress.mode,
                    language=book.progress.language,
                )
                book.progress.assessment_result = json.dumps(
                    {"profile": result.get("profile", {}), "chapter_frameworks": {"1": framework}},
                    ensure_ascii=False,
                )
        except: pass

    await db.commit()

    return AssessmentResponse(
        ai_message=ai_response,
        assessment_complete=assessment_complete,
        next_action="enter_reading" if assessment_complete else "continue",
    )


@router.post("/chat")
async def reading_chat(
    data: ReadingRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """v4.0: Wiki-based reading loop (P4)。从预生成 Wiki 清单读取，JSON 输出分发三栏。"""
    book = await _get_book(db, data.book_id, user.id)
    progress = book.progress
    if not progress or progress.status not in ("reading", "paused"):
        raise HTTPException(status_code=400, detail="请先选择阅读模式")

    if progress.status == "paused":
        progress.status = "reading"
        await db.commit()

    mode = progress.mode
    chapter = max(progress.current_chapter, 1)
    language = progress.language or "zh"

    # 从预处理结果读取 Wiki 清单
    wiki_checklist = []
    if book.preprocess_progress:
        ch_wikis = book.preprocess_progress.get("chapter_wikis", {}).get(str(chapter), {})
        wiki_checklist = ch_wikis.get("wikis", [])

    current_wiki_id = progress.current_wiki_id
    if not current_wiki_id and wiki_checklist:
        current_wiki_id = wiki_checklist[0].get("id", "")
        progress.current_wiki_id = current_wiki_id
        await db.commit()

    completed_wikis = progress.completed_wikis or []

    # 读全书文本
    book_text = ""
    if book.text_path:
        try:
            with open(book.text_path, "r", encoding="utf-8") as f:
                book_text = f.read()
        except FileNotFoundError:
            pass

    # 获取对话历史
    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == chapter,
        ).order_by(Conversation.round_index)
    )
    history = [{"role": m.role, "content": m.content} for m in prev.scalars().all()]

    # 保存用户消息
    round_idx = len([m for m in history if m["role"] == "user"])
    db.add(Conversation(
        book_id=book.id, chapter_index=chapter,
        round_index=round_idx, role="user", content=data.message,
    ))
    await db.commit()
    history.append({"role": "user", "content": data.message})

    # 组装 P4 prompt
    mode_desc = (
        "快速模式：以AI概括为主，原文为辅。追问2-3轮即可。"
        if mode == "quick" else
        "深度模式：以原文为主，AI解析为辅。可多轮深挖每个Wiki。"
    )
    profile = {}
    if progress.assessment_result:
        try: profile = json.loads(progress.assessment_result).get("profile", {})
        except: pass

    p4_prompt = _p("p4_reading", language).format(
        book_title=book.title,
        mode_description=mode_desc,
        wiki_checklist=json.dumps(wiki_checklist, ensure_ascii=False),
        current_wiki=f"{current_wiki_id}",
        completed_wikis=json.dumps(completed_wikis, ensure_ascii=False),
        user_profile=json.dumps(profile, ensure_ascii=False),
        language_instruction="中文对话" if language == "zh" else "English conversation",
    )

    system_msgs = [{"role": "system", "content": f"{p4_prompt}\n\n## 全书原文\n{book_text[:50000]}"}]
    messages = system_msgs + history

    # 流式对话（先收集完整响应，解析JSON，再返回文本）
    async def generate():
        # Collect full response from AI
        full_response = ""
        async for token in chat_stream(messages, temperature=0.7, max_tokens=4096):
            full_response += token

        # Parse JSON response
        try:
            from app.services.json_validator import extract_json
            parsed = extract_json(full_response)
            ai_text = parsed.get("ai_response", full_response)
        except Exception:
            parsed = {"ai_response": full_response, "current_wiki": {"id": current_wiki_id, "name": ""}, "reading_material": "", "wiki_transition": False, "transition_message": ""}
            ai_text = full_response

        # Stream the display text to the user
        yield ai_text
        # Append wiki metadata for frontend
        yield f"\n<!--V4_META:{json.dumps(parsed, ensure_ascii=False)}-->"

        db2 = async_session()
        try:
            db2.add(Conversation(
                book_id=book.id, chapter_index=chapter,
                round_index=round_idx + 1, role="assistant",
                content=full_response,
                metadata_={"chapter": chapter, "mode": mode, "v4": True},
            ))
            progress2 = (await db2.execute(
                select(ReadingProgress).where(ReadingProgress.book_id == book.id)
            )).scalar_one_or_none()

            if progress2:
                progress2.total_rounds = round_idx + 2

                # Update wiki state
                if parsed.get("current_wiki", {}).get("id"):
                    new_wiki_id = parsed["current_wiki"]["id"]
                    if new_wiki_id != progress2.current_wiki_id:
                        # Wiki changed: mark old as done
                        if progress2.current_wiki_id:
                            done = list(progress2.completed_wikis or [])
                            if progress2.current_wiki_id not in done:
                                done.append(progress2.current_wiki_id)
                            progress2.completed_wikis = done
                        progress2.current_wiki_id = new_wiki_id

                # Chapter end check
                if data.message.strip() == "/next" or _is_chapter_end(full_response) or len(history) >= 20:
                    yield "\n\n[CHAPTER_END]"
                    total = book.chapter_count or 1
                    if chapter >= total:
                        progress2.status = "completed"
                    else:
                        progress2.current_chapter = chapter + 1
                        progress2.status = "paused"

            await db2.commit()
        finally:
            await db2.close()

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@router.get("/progress/{book_id}", response_model=ProgressResponse)
async def get_progress(
    book_id: uuid.UUID,
    include_history: bool = Query(default=False, description="是否返回最近对话"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取阅读进度。include_history=true 时返回上轮对话（用于断点续接前端展示）"""
    book = await _get_book(db, book_id, user.id)
    progress = book.progress
    resp = _to_progress_response(book, progress)

    # 提取章节框架概念用于前端左侧引导栏
    if progress and progress.assessment_result:
        try:
            stored = json.loads(progress.assessment_result)
            ch_key = str(max(progress.current_chapter, 1))
            fw = stored.get("chapter_frameworks", {}).get(ch_key, {})
            def _theses(node):
                items = []
                if isinstance(node, dict):
                    if node.get("thesis"): items.append(node["thesis"])
                    for b in node.get("branches", []): items.extend(_theses(b))
                return items
            resp.chapter_concepts = _theses(fw.get("argument_tree", {}))
        except: pass

    if include_history and progress and progress.status not in ("not_started",):
        chapter = max(progress.current_chapter, 1)
        prev = await db.execute(
            select(Conversation).where(
                Conversation.book_id == book.id,
                Conversation.chapter_index.in_([chapter, ASSESSMENT_CHAPTER]),
            ).order_by(Conversation.round_index)
        )
        # 动态属性：用 FastAPI response_model 不校验额外字段，这里手动加
        resp.last_messages = [
            {"role": m.role, "content": m.content, "round": m.round_index}
            for m in prev.scalars().all()[-6:]  # 最近 6 条
        ]

    # For not_started books, try to get concepts from parsed framework
    if not progress or progress.status == "not_started":
        try:
            if book.category:
                framework = json.loads(book.category)
                def _theses2(node):
                    items = []
                    if isinstance(node, dict):
                        if node.get("thesis"): items.append(node["thesis"])
                        for b in node.get("branches", []): items.extend(_theses2(b))
                    return items
                resp.chapter_concepts = _theses2(framework.get("argument_tree", {}))
        except: pass
    return resp


@router.get("/chapter/{book_id}")
async def get_chapter_text(book_id: uuid.UUID, chapter: int = 1, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """获取指定章节的原文"""
    book = await _get_book(db, book_id, user.id)
    if not book.text_path:
        raise HTTPException(status_code=404, detail="书籍文本未找到")
    try:
        with open(book.text_path, "r", encoding="utf-8") as f:
            full_text = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="书籍文本未找到")
    chapter_text = _extract_chapter_text(full_text, chapter, book.chapter_count or 1)
    return {"chapter": chapter, "total": book.chapter_count, "text": chapter_text[:3000]}


@router.get("/resume/{book_id}", response_model=ProgressResponse)
async def resume_reading(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """断点续接：返回当前进度 + 最近对话，前端直接用此数据恢复导读界面"""
    book = await _get_book(db, book_id, user.id)
    progress = book.progress
    if not progress:
        # Return book info for overview page
        resp = ProgressResponse(
            book_id=book.id, book_title=book.title,
            mode="quick", current_chapter=0, total_chapters=book.chapter_count or 1,
            total_rounds=0, status="not_started", progress_percent=0,
        )
        try:
            if book.category:
                framework = json.loads(book.category)
                def _t(node):
                    items = []
                    if isinstance(node, dict):
                        if node.get("thesis"): items.append(node["thesis"])
                        for b in node.get("branches", []): items.extend(_t(b))
                    return items
                resp.chapter_concepts = _t(framework.get("argument_tree", {}))
        except: pass
        return resp

    resp = _to_progress_response(book, progress)

    # v4.0: Wiki state
    resp.current_wiki_id = progress.current_wiki_id
    resp.completed_wikis = progress.completed_wikis or []

    # Build wiki checklist for left column
    chapter = max(progress.current_chapter, 1)
    wiki_checklist = []
    if book.preprocess_progress:
        ch_wikis = book.preprocess_progress.get("chapter_wikis", {}).get(str(chapter), {})
        for w in ch_wikis.get("wikis", []):
            wiki_id = w.get("id", "")
            status = "active" if wiki_id == progress.current_wiki_id else (
                "done" if wiki_id in (progress.completed_wikis or []) else "pending"
            )
            wiki_checklist.append({"id": wiki_id, "name": w.get("name", ""), "status": status})
    resp.wiki_checklist = wiki_checklist

    # 加载最近对话
    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index.in_([chapter, ASSESSMENT_CHAPTER]),
        ).order_by(Conversation.round_index)
    )
    resp.last_messages = [
        {"role": m.role, "content": m.content, "round": m.round_index}
        for m in prev.scalars().all()
    ]

    # For not_started books, try to get concepts from parsed framework
    if not progress or progress.status == "not_started":
        try:
            if book.category:
                framework = json.loads(book.category)
                def _theses2(node):
                    items = []
                    if isinstance(node, dict):
                        if node.get("thesis"): items.append(node["thesis"])
                        for b in node.get("branches", []): items.extend(_theses2(b))
                    return items
                resp.chapter_concepts = _theses2(framework.get("argument_tree", {}))
        except: pass
    return resp


@router.post("/chapter-end")
async def chapter_end(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """v4.0: 章末Wiki确认。将本章对话+原始Wiki发给AI做最终调整。"""
    book_id = data.get("book_id")
    chapter = data.get("chapter_index", 1)
    book = await _get_book(db, book_id, user.id)

    # 获取原始Wiki
    orig_wikis = []
    if book.preprocess_progress:
        orig_wikis = book.preprocess_progress.get("chapter_wikis", {}).get(str(chapter), {}).get("wikis", [])

    # 获取本章对话
    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == chapter,
        ).order_by(Conversation.round_index)
    )
    conv = [{"role": m.role, "content": m.content} for m in prev.scalars().all()]

    # 调用P5
    from app.services.llm_service import chat as chat_nonstream
    from app.services.json_validator import extract_json
    p5_prompt = _p("p5_confirm", "zh").format(
        chapter_index=chapter,
        original_wikis=json.dumps(orig_wikis, ensure_ascii=False),
        conversation_context=json.dumps(conv, ensure_ascii=False),
    )
    raw = await chat_nonstream([{"role": "user", "content": p5_prompt}], temperature=0.3, max_tokens=4096)
    try:
        result = extract_json(raw)
        return {"wikis": result.get("wikis", [])}
    except Exception:
        return {"wikis": orig_wikis}  # fallback to original


# ── helpers ──

async def _get_book(db: AsyncSession, book_id: uuid.UUID, user_id: uuid.UUID) -> Book:
    result = await db.execute(
        select(Book)
        .where(Book.id == book_id, Book.user_id == user_id)
        .options(selectinload(Book.progress))
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return book


def _to_progress_response(book: Book, progress: ReadingProgress | None) -> ProgressResponse:
    return ProgressResponse(
        book_id=book.id, book_title=book.title,
        mode=progress.mode if progress else "quick",
        current_chapter=progress.current_chapter if progress else 0,
        total_chapters=book.chapter_count,
        total_rounds=progress.total_rounds if progress else 0,
        status=progress.status if progress else "not_started",
        progress_percent=int(
            (progress.current_chapter if progress else 0)
            / max(book.chapter_count or 1, 1) * 100
        ),
    )


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


def _is_chapter_end(response: str) -> bool:
    markers = ["本章完成", "本章结束", "进入下一章", "章节总结", "本章用户理解的所有概念"]
    return any(m in response for m in markers)


def async_session():
    from app.database import async_session as _session
    return _session()
