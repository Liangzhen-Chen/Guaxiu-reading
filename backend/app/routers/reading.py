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
    socratic_chat_stream
)
from app.services.llm_service import chat, count_tokens

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
    """导读对话 (Prompt A + B)。章节框架自动缓存，断点自动续接。"""
    book = await _get_book(db, data.book_id, user.id)
    progress = book.progress
    if not progress or progress.status not in ("reading", "paused"):
        raise HTTPException(status_code=400, detail="请先选择阅读模式")

    # 断点续接：paused 状态下恢复
    if progress.status == "paused":
        progress.status = "reading"
        await db.commit()

    mode = progress.mode
    chapter = max(progress.current_chapter, 1)

    # 读全书文本
    book_text = ""
    if book.text_path:
        try:
            with open(book.text_path, "r", encoding="utf-8") as f:
                book_text = f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail="书籍文本未找到")

    # 获取或生成章节框架（缓存在 progress.assessment_result 中）
    stored = {}
    if progress.assessment_result:
        try:
            stored = json.loads(progress.assessment_result)
        except json.JSONDecodeError:
            pass
    frameworks = stored.get("chapter_frameworks", {})

    chapter_key = str(chapter)
    if chapter_key not in frameworks:
        chapter_text = _extract_chapter_text(book_text, chapter, book.chapter_count or 1)
        framework = await generate_chapter_structure(
            book_title=book.title, chapter_index=chapter,
            chapter_text=chapter_text, mode=mode,
            language=progress.language,
        )
        frameworks[chapter_key] = framework
        stored["chapter_frameworks"] = frameworks
        progress.assessment_result = json.dumps(stored, ensure_ascii=False)
        await db.commit()

    framework = frameworks[chapter_key]

    # 获取本章对话历史（断点续接的关键）
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

    # 流式对话
    async def generate():
        full_response = ""
        async for token in socratic_chat_stream(
            mode=mode, chapter_framework=framework, book_text=book_text,
            conversation_history=history, user_message=data.message,
            language=progress.language,
        ):
            full_response += token
            yield token

        # 保存 AI 回应 + 处理章节切换
        db2 = async_session()
        try:
            db2.add(Conversation(
                book_id=book.id, chapter_index=chapter,
                round_index=round_idx + 1, role="assistant",
                content=full_response,
                metadata_={"chapter": chapter, "mode": mode},
            ))
            progress2 = (await db2.execute(
                select(ReadingProgress).where(ReadingProgress.book_id == book.id)
            )).scalar_one_or_none()

            if progress2:
                progress2.total_rounds = round_idx + 2

                # ── 章节切换（AI 自动或用户 /next 触发）──
                if _is_chapter_end(full_response) or data.message.strip() == "/next":
                    try:
                        concepts_data = await extract_concepts(
                            chapter,
                            history + [{"role": "assistant", "content": full_response}],
                            language=progress.language,
                        )
                        count = 0
                        for c in concepts_data.get("concepts", []):
                            db2.add(WikiEntry(
                                user_id=user.id, book_id=book.id,
                                concept_name=c["name"], entry_type="concept",
                                chapter_index=chapter,
                                ai_definition=c.get("definition", ""),
                                evidence=c.get("evidence", []),
                                source_quote=c.get("source_quote"),
                                tags=c.get("tags", []),
                            ))
                            count += 1
                        for v in concepts_data.get("viewpoints", []):
                            db2.add(WikiEntry(
                                user_id=user.id, book_id=book.id,
                                concept_name=v["statement"][:300], entry_type="viewpoint",
                                chapter_index=chapter,
                                ai_definition=v.get("statement", ""),
                                evidence=v.get("evidence", []),
                                tags=v.get("tags", []),
                            ))
                            count += 1

                        total = book.chapter_count or 1
                        if chapter >= total:
                            progress2.status = "completed"
                            yield f"\n\n[全书导读完成！{count} 条概念/观点已存入 Wiki。]"
                        else:
                            progress2.current_chapter = chapter + 1
                            progress2.status = "paused"
                            yield f"\n\n[第{chapter}章完成。{count} 条概念/观点已提取。输入任意内容进入第{chapter + 1}章。]"
                    except Exception as e:
                        yield f"\n\n[概念提取出错: {e}]"

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

    return resp


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
        raise HTTPException(status_code=400, detail="尚未开始导读")

    resp = _to_progress_response(book, progress)

    chapter = max(progress.current_chapter, 1)
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

    return resp


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
