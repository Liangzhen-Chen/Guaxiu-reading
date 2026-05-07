"""导读路由 —— 核心：苏格拉底式流式对话
P5-1: 只保留路由端点，调用新 service。"""
import json
import logging
import re as _re
import httpx
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete
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
    ReadingRequest, ProgressResponse,
)
from app.middleware.auth import get_current_user
from app.services.socratic_service import (
    _p, generate_assessment_question, generate_chapter_structure,
)
from app.services.llm_service import chat, chat_stream, count_tokens
from app.services.reading_service import (
    build_reading_prompt, manage_wiki_state,
    parse_v4_meta, update_wiki_progress, handle_chapter_end,
    compress_history,
)
from app.services.chapter_service import (
    build_wiki_checklist, get_chapter_wikis, extract_theses,
)
from app.utils.chapter_utils import get_chapter_text as _raw_chapter_text, get_chapter_markers

logger = logging.getLogger("xiugua.reading")
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

    # D2: Reset assessment conversation when starting a new assessment
    if book.progress and book.progress.assessment_result:
        book.progress.assessment_result = None
        await db.execute(
            delete(Conversation).where(
                Conversation.book_id == book.id,
                Conversation.chapter_index == ASSESSMENT_CHAPTER,
            )
        )

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
        round_index=round_idx, role="user", content=data.message,
    ))
    history.append({"role": "user", "content": data.message})

    ai_response = await generate_assessment_question(
        book_title=book.title, author=book.author or "未知",
        category=book.category or "通用", conversation_history=history,
        language=book.progress.language if book.progress else "zh",
    )

    db.add(Conversation(
        book_id=book.id, chapter_index=ASSESSMENT_CHAPTER,
        round_index=round_idx + 1, role="assistant", content=ai_response,
    ))

    assessment_complete = False
    try:
        result = json.loads(ai_response)
        if result.get("assessment_complete"):
            assessment_complete = True
            progress = book.progress
            if progress:
                progress.status = "reading"
                # P5-4: assessment_result is now JSONB, store as dict directly
                progress.assessment_result = {
                    "profile": result.get("profile", {}),
                    "chapter_frameworks": {},
                }
    except (json.JSONDecodeError, TypeError):
        assessment_complete = round_idx >= 2

    if assessment_complete and book.progress:
        if book.progress.status != "reading":
            book.progress.status = "reading"
        # P5-7: current_chapter default is 1
        if book.progress.current_chapter == 0:
            book.progress.current_chapter = 1
        try:
            if book.text_path:
                ch1_text = _raw_chapter_text(
                    book.text_path, 1, book.chapter_count or 1,
                    get_chapter_markers(book),
                )
                framework = await generate_chapter_structure(
                    book_title=book.title, chapter_index=1,
                    chapter_text=ch1_text, mode=book.progress.mode,
                    language=book.progress.language,
                )
                book.progress.assessment_result = {
                    "profile": result.get("profile", {}),
                    "chapter_frameworks": {"1": framework},
                }
        except Exception:
            logger.warning("assessment: eager chapter 1 framework generation failed", exc_info=True)

    await db.commit()

    return AssessmentResponse(
        ai_message=ai_response,
        assessment_complete=assessment_complete,
        next_action="enter_reading" if assessment_complete else "continue",
    )


@router.post("/chat")
async def reading_chat(
    data: ReadingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """v4.0: Wiki-based reading loop (P4)。"""
    book = await _get_book(db, data.book_id, user.id)
    progress = book.progress

    # P4-8: Lock ReadingProgress for update
    if progress:
        stmt = select(ReadingProgress).where(ReadingProgress.id == progress.id).with_for_update()
        await db.execute(stmt)
        await db.refresh(progress)

    # /next command
    if data.message.strip() == "/next":
        if progress and progress.status == "assessment":
            async def _assessment_blocker():
                yield "抱歉，你当前正在背景评估阶段，请先完成评估再进入阅读。"
            return StreamingResponse(_assessment_blocker(), media_type="text/plain; charset=utf-8")

        ch = progress.current_chapter if progress else 1
        if progress:
            total_ch = book.chapter_count or 1
            if ch >= total_ch:
                progress.status = "completed"
            else:
                progress.current_chapter = ch + 1
                progress.status = "paused"
                progress.current_wiki_id = None
                progress.completed_wikis = []
            await db.commit()

        wiki_data = get_chapter_wikis(book, ch)

        async def gen():
            if await request.is_disconnected():
                return
            yield f"<!--CHAPTER_END:{json.dumps(wiki_data, ensure_ascii=False, separators=(',', ':'))}-->"
        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")

    if not progress or progress.status not in ("reading", "paused"):
        raise HTTPException(status_code=400, detail="请先选择阅读模式")

    if progress.status == "paused":
        progress.status = "reading"
        await db.commit()

    chapter = progress.current_chapter
    # Use book's detected language for AI conversation, fall back to user preference
    language = book.language or progress.language or "zh"

    # Wiki list from preprocess
    wiki_checklist = []
    if book.preprocess_progress:
        ch_wikis = book.preprocess_progress.get("chapter_wikis", {}).get(str(chapter), {})
        wiki_checklist = ch_wikis.get("wikis", [])

    current_wiki_id = progress.current_wiki_id
    # Reset to first wiki if: no current wiki, or current wiki not in this chapter's checklist
    wiki_ids = {w.get("id") for w in wiki_checklist} if wiki_checklist else set()
    if (not current_wiki_id or current_wiki_id not in wiki_ids) and wiki_checklist:
        current_wiki_id = wiki_checklist[0].get("id", "")
        progress.current_wiki_id = current_wiki_id
        progress.completed_wikis = []
        await db.commit()

    # Get conversation history
    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == chapter,
        ).order_by(Conversation.round_index)
    )
    history = [{"role": m.role, "content": m.content} for m in prev.scalars().all()]

    if len(history) > 60:
        history = history[-60:]

    # Wiki state management: force-skip if stuck
    force_skip_note = manage_wiki_state(progress, wiki_checklist, history, chapter)

    # Strip V4_META markers
    for msg in history:
        msg["content"] = _re.sub(r'<!--V4_META:[\s\S]*?-->', '', msg["content"]).strip()

    # Save user message
    round_idx = len([m for m in history if m["role"] == "user"])
    db.add(Conversation(
        book_id=book.id, chapter_index=chapter,
        round_index=round_idx, role="user", content=data.message,
    ))
    await db.commit()
    history.append({"role": "user", "content": data.message})

    # Language mismatch: ask user preference on first round
    lang_mismatch_note = ""
    if len(history) <= 2 and book.language and book.language != (progress.language or "zh"):
        ui_lang = "中文" if (progress.language or "zh") == "zh" else "English"
        book_lang = "中文" if book.language == "zh" else "English"
        lang_mismatch_note = (
            f"[重要：这本书的语言是{book_lang}，但你的界面语言是{ui_lang}。"
            f"请先询问用户希望用哪种语言进行对话。]"
        )

    # Build P4 prompt
    p4_prompt, no_wiki_note = build_reading_prompt(
        progress, book, wiki_checklist, chapter, language,
    )
    if lang_mismatch_note:
        p4_prompt = lang_mismatch_note + "\n" + p4_prompt

    # P6: Compress conversation if too many rounds
    history = await compress_history(history, language)
    # Note: compress_history is imported from reading_service; register import above

    logger.info("P4 call: mode=%s book=%s chapter=%d lang=%s",
                progress.mode if progress else "?", book.id, chapter, language)

    system_msgs = [{"role": "system", "content": f"{p4_prompt}{no_wiki_note}{force_skip_note}"}]
    messages = system_msgs + history

    async def generate():
        full_response = ""
        disconnected = False
        token_count = 0
        usage_container = []  # P5-12: capture usage info

        async for token in chat_stream(
            messages, temperature=0.3, max_tokens=4096,
            timeout=httpx.Timeout(30.0, read=120.0), top_p=0.9,
            usage_container=usage_container,
        ):
            full_response += token
            yield token

            token_count += 1
            if token_count % 5 == 0 and await request.is_disconnected():
                logger.warning("P2-7 client disconnected: book=%s ch=%d user=%s",
                               book.id, chapter, user.id)
                disconnected = True
                break

        if disconnected:
            return

        # Parse V4_META
        parsed, ai_text, ai_signaled_chapter_end = parse_v4_meta(
            full_response, current_wiki_id,
        )

        # Save conversation
        conversation = Conversation(
            book_id=book.id, chapter_index=chapter,
            round_index=round_idx + 1, role="assistant",
            content=ai_text + f"\n<!--V4_META:{json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))}-->",
            metadata_={"chapter": chapter, "mode": progress.mode if progress else "quick", "v4": True},
        )
        # P5-12: Write tokens_used
        if usage_container:
            conversation.tokens_used = usage_container[0].get("completion_tokens", 0)
        db.add(conversation)

        progress2 = (await db.execute(
            select(ReadingProgress).where(ReadingProgress.book_id == book.id)
        )).scalar_one_or_none()

        all_done = False
        if progress2:
            progress2.total_rounds = round_idx + 2
            update_wiki_progress(progress2, parsed)
            all_done = handle_chapter_end(
                progress2, parsed, ai_signaled_chapter_end, book, chapter,
            )

        await db.commit()

        yield f"\n<!--V4_META:{json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))}-->"

        if all_done:
            yield f"\n\n<!--CHAPTER_END:{json.dumps(get_chapter_wikis(book, chapter), ensure_ascii=False, separators=(',', ':'))}-->"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@router.get("/progress/{book_id}", response_model=ProgressResponse)
async def get_progress(
    book_id: uuid.UUID,
    include_history: bool = Query(default=False, description="是否返回最近对话"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取阅读进度"""
    book = await _get_book(db, book_id, user.id)
    progress = book.progress
    resp = _to_progress_response(book, progress)

    if progress and progress.assessment_result:
        try:
            stored = progress.assessment_result
            if isinstance(stored, str):
                stored = json.loads(stored)
            ch_key = str(progress.current_chapter)
            fw = stored.get("chapter_frameworks", {}).get(ch_key, {})
            resp.chapter_concepts = extract_theses(fw.get("argument_tree", {}))
        except Exception:
            logger.warning("get_progress: failed to extract chapter_concepts", exc_info=True)

    if include_history and progress and progress.status not in ("not_started",):
        chapter = progress.current_chapter
        prev = await db.execute(
            select(Conversation).where(
                Conversation.book_id == book.id,
                Conversation.chapter_index.in_([chapter, ASSESSMENT_CHAPTER]),
            ).order_by(Conversation.round_index)
        )
        resp.last_messages = [
            {"role": m.role, "content": m.content, "round": m.round_index}
            for m in prev.scalars().all()[-6:]
        ]

    if not progress or progress.status == "not_started":
        try:
            if book.category:
                framework = json.loads(book.category)
                resp.chapter_concepts = extract_theses(framework.get("argument_tree", {}))
        except Exception:
            logger.warning("get_progress: not_started path failed", exc_info=True)
    return resp


@router.get("/chapter/{book_id}")
async def get_chapter_text_endpoint(
    book_id: uuid.UUID, chapter: int = 1,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """获取指定章节的原文"""
    book = await _get_book(db, book_id, user.id)
    if not book.text_path:
        raise HTTPException(status_code=404, detail="书籍文本未找到")
    try:
        chapter_text = _raw_chapter_text(
            book.text_path, chapter, book.chapter_count or 1,
            get_chapter_markers(book),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="书籍文本未找到")
    return {"chapter": chapter, "total": book.chapter_count, "text": chapter_text[:3000]}


@router.get("/wiki-status/{book_id}")
async def get_wiki_status(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """轻量wiki状态 —— 仅返回wiki清单和进度，不加载对话历史"""
    book = await _get_book(db, book_id, user.id)
    progress = book.progress

    from app.services.chapter_service import build_wiki_checklist
    chapter = max(progress.current_chapter, 1) if progress else 1
    wiki_checklist = []
    if progress:
        wiki_checklist = build_wiki_checklist(book, chapter, progress)

    return {
        "wiki_checklist": wiki_checklist,
        "current_wiki_id": progress.current_wiki_id if progress else None,
        "completed_wikis": progress.completed_wikis if progress else [],
        "status": progress.status if progress else "not_started",
        "mode": progress.mode if progress else None,
        "current_chapter": chapter,
        "total_chapters": book.chapter_count or 1,
        "has_history": True,
    }


@router.get("/resume/{book_id}", response_model=ProgressResponse)
async def resume_reading(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """断点续接"""
    book = await _get_book(db, book_id, user.id)
    progress = book.progress
    if not progress:
        resp = ProgressResponse(
            book_id=book.id, book_title=book.title,
            mode="quick", current_chapter=0, total_chapters=book.chapter_count or 1,
            total_rounds=0, status="not_started", progress_percent=0,
        )
        resp.wiki_checklist = build_wiki_checklist(book, 1, None)
        try:
            if book.category:
                framework = json.loads(book.category)
                resp.chapter_concepts = extract_theses(framework.get("argument_tree", {}))
        except Exception:
            logger.warning("resume: concepts extract failed", exc_info=True)
        return resp

    resp = _to_progress_response(book, progress)
    resp.current_wiki_id = progress.current_wiki_id
    resp.completed_wikis = progress.completed_wikis or []
    chapter = progress.current_chapter
    resp.wiki_checklist = build_wiki_checklist(book, chapter, progress)

    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == chapter,
        ).order_by(Conversation.round_index)
    )
    import re as _re2
    clean_messages = []
    last_material = ""
    for m in prev.scalars().all():
        content = m.content or ""
        meta_match = _re2.search(r'<!--V4_META:([\s\S]*?)-->', content)
        if meta_match:
            try:
                parsed = json.loads(meta_match.group(1))
                last_material = parsed.get("reading_material", "")
            except Exception:
                logger.warning("resume: V4_META parse failed", exc_info=True)
            content = _re2.sub(r'<!--V4_META:[\s\S]*?-->', '', content).strip()
        clean_messages.append({"role": m.role, "content": content, "round": m.round_index})
    resp.last_messages = clean_messages
    resp.reading_material = last_material

    if progress.status == "not_started":
        try:
            if book.category:
                framework = json.loads(book.category)
                resp.chapter_concepts = extract_theses(framework.get("argument_tree", {}))
        except Exception:
            logger.warning("resume: concepts extract failed", exc_info=True)
    return resp


@router.post("/chapter-end")
async def chapter_end(
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """章末Wiki确认"""
    book_id = data.get("book_id")
    chapter = data.get("chapter_index", 1)
    book = await _get_book(db, book_id, user.id)

    orig_wikis = []
    if book.preprocess_progress:
        orig_wikis = book.preprocess_progress.get("chapter_wikis", {}).get(str(chapter), {}).get("wikis", [])

    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == chapter,
        ).order_by(Conversation.round_index)
    )
    conv = [{"role": m.role, "content": m.content} for m in prev.scalars().all()]

    from app.services.llm_service import chat as chat_nonstream
    from app.services.json_validator import extract_json
    lang = (book.progress.language if book.progress and book.progress.language else "zh")
    p5_prompt = _p("p5_confirm", lang)
    p5_prompt = p5_prompt.replace("{chapter_index}", str(chapter))
    p5_prompt = p5_prompt.replace("{original_wikis}", json.dumps(orig_wikis, ensure_ascii=False))
    p5_prompt = p5_prompt.replace("{conversation_context}", json.dumps(conv, ensure_ascii=False))
    raw = await chat_nonstream(
        [{"role": "user", "content": p5_prompt}],
        temperature=0.3, max_tokens=4096,
        response_format={"type": "json_object"},
    )
    try:
        result = extract_json(raw)
        adjusted_wikis = result.get("wikis", [])

        if adjusted_wikis:
            from sqlalchemy import select as _sel
            for w in adjusted_wikis:
                name = w.get("name", "")
                existing = await db.execute(
                    _sel(WikiEntry).where(
                        WikiEntry.book_id == book.id,
                        WikiEntry.user_id == user.id,
                        WikiEntry.concept_name == name,
                        WikiEntry.chapter_index == chapter,
                    )
                )
                entry = existing.scalar_one_or_none()
                if entry:
                    entry.ai_definition = w.get("content", entry.ai_definition)
                    entry.entry_type = w.get("type", entry.entry_type)
                    entry.entry_subtype = w.get("type", entry.entry_subtype)
                    entry.evidence = w.get("evidence", entry.evidence)
                    entry.source_quotes = w.get("quotes", entry.source_quotes)
                    entry.notes = w.get("notes", entry.notes)
                else:
                    entry = WikiEntry(
                        user_id=user.id, book_id=book.id,
                        concept_name=name, chapter_index=chapter,
                        entry_type=w.get("type", "concept"),
                        entry_subtype=w.get("type", "concept"),
                        ai_definition=w.get("content", ""),
                        evidence=w.get("evidence", None),
                        source_quotes=w.get("quotes", None),
                        notes=w.get("notes", None),
                    )
                    db.add(entry)
            await db.flush()

        if book.preprocess_progress:
            pp = dict(book.preprocess_progress)
            ch_wikis = pp.get("chapter_wikis", {})
            ch_key = str(chapter)
            existing_ch_data = ch_wikis.get(ch_key, {})
            existing_ch_data["wikis"] = adjusted_wikis
            ch_wikis[ch_key] = existing_ch_data
            pp["chapter_wikis"] = ch_wikis
            book.preprocess_progress = pp
            db.add(book)

        # 确保每个 wiki 项都携带 chapter_index，供前端批量调用时使用
        for w in adjusted_wikis:
            if "chapter_index" not in w:
                w["chapter_index"] = chapter
        await db.commit()
        return {"wikis": adjusted_wikis}
    except Exception as e:
        logger.warning("P5 chapter_end failed: %s", e)
        return {"wikis": orig_wikis}


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
