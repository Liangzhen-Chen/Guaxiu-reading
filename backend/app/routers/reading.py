"""导读路由 —— 核心：苏格拉底式流式对话"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
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

ASSESSMENT_CHAPTER = -1  # 评估对话用 chapter_index = -1 标记


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
            book_id=book.id, mode=data.mode, status="assessment"
        )
        db.add(progress)
    else:
        progress.mode = data.mode
    await db.commit()
    await db.refresh(progress)
    return ProgressResponse(
        book_id=book.id, book_title=book.title, mode=progress.mode,
        current_chapter=progress.current_chapter,
        total_chapters=book.chapter_count,
        total_rounds=progress.total_rounds, status=progress.status,
        progress_percent=int(
            progress.current_chapter / max(book.chapter_count or 1, 1) * 100
        ),
    )


@router.post("/assessment")
async def assessment(
    data: AssessmentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    背景评估对话 (Prompt D)
    用户每发送一条消息，返回 AI 下一轮评估问题。
    3-5 轮后自动输出用户画像 JSON 并进入 reading 状态。
    """
    book = await _get_book(db, data.book_id, user.id)
    mode = book.progress.mode if book.progress else "quick"

    # 获取评估对话历史
    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == ASSESSMENT_CHAPTER,
        ).order_by(Conversation.round_index)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in prev.scalars().all()
    ]

    # 保存用户消息
    round_idx = len([m for m in history if m["role"] == "user"])
    db.add(Conversation(
        book_id=book.id, chapter_index=ASSESSMENT_CHAPTER,
        round_index=round_idx, role="user", content=data.message
    ))
    history.append({"role": "user", "content": data.message})

    # 调用 Prompt D 生成回应
    ai_response = await generate_assessment_question(
        book_title=book.title,
        author=book.author or "未知",
        category=book.category or "通用",
        conversation_history=history,
    )

    # 保存 AI 回应
    db.add(Conversation(
        book_id=book.id, chapter_index=ASSESSMENT_CHAPTER,
        round_index=round_idx + 1, role="assistant", content=ai_response
    ))

    # 判断是否完成评估
    assessment_complete = False
    try:
        result = json.loads(ai_response)
        if result.get("assessment_complete"):
            assessment_complete = True
            progress = book.progress
            if progress:
                progress.status = "reading"
                progress.assessment_result = json.dumps(
                    result.get("profile", {}), ensure_ascii=False
                )
    except (json.JSONDecodeError, TypeError):
        # 还在评估中，继续
        assessment_complete = round_idx >= 2  # 至少 3 轮

    if assessment_complete:
        progress = book.progress
        if progress and progress.status != "reading":
            progress.status = "reading"

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
    """
    导读对话 (Prompt A + B)
    每轮：检查是否需要生成本章框架 → 流式返回苏格拉底追问
    """
    book = await _get_book(db, data.book_id, user.id)
    progress = book.progress
    if not progress or progress.status not in ("reading", "assessment"):
        raise HTTPException(status_code=400, detail="请先选择阅读模式")

    mode = progress.mode
    chapter = progress.current_chapter or 1

    # 读取全书文本
    book_text = ""
    if book.text_path:
        try:
            with open(book.text_path, "r", encoding="utf-8") as f:
                book_text = f.read()
        except FileNotFoundError:
            raise HTTPException(status_code=400, detail="书籍文本未找到，请重新上传")

    # 获取或生成章节框架 (Prompt A)
    # 框架缓存在 progress.assessment_result 中，格式: {"chapter_frameworks": {"1": {...}}}
    frameworks = {}
    if progress.assessment_result:
        try:
            stored = json.loads(progress.assessment_result)
            frameworks = stored.get("chapter_frameworks", {})
        except json.JSONDecodeError:
            pass

    chapter_key = str(chapter)
    if chapter_key not in frameworks:
        # 调用 Prompt A 生成框架
        chapter_text = _extract_chapter_text(book_text, chapter, book.chapter_count or 1)
        framework = await generate_chapter_structure(
            book_title=book.title,
            chapter_index=chapter,
            chapter_text=chapter_text,
            mode=mode,
        )
        frameworks[chapter_key] = framework
        # 保存回 progress
        progress.assessment_result = json.dumps(
            {"chapter_frameworks": frameworks}, ensure_ascii=False
        )
        await db.commit()

    framework = frameworks[chapter_key]

    # 获取导读对话历史
    prev = await db.execute(
        select(Conversation).where(
            Conversation.book_id == book.id,
            Conversation.chapter_index == chapter,
        ).order_by(Conversation.round_index)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in prev.scalars().all()
    ]

    # 保存用户消息
    round_idx = len([m for m in history if m["role"] == "user"])
    db.add(Conversation(
        book_id=book.id, chapter_index=chapter,
        round_index=round_idx, role="user", content=data.message,
    ))
    await db.commit()

    history.append({"role": "user", "content": data.message})

    # 流式返回
    async def generate():
        full_response = ""
        async for token in socratic_chat_stream(
            mode=mode,
            chapter_framework=framework,
            book_text=book_text,
            conversation_history=history,
            user_message=data.message,
        ):
            full_response += token
            yield token

        # 保存 AI 完整回应
        db2 = async_session()
        try:
            db2.add(Conversation(
                book_id=book.id, chapter_index=chapter,
                round_index=round_idx + 1, role="assistant",
                content=full_response,
                metadata_={"chapter": chapter, "mode": mode},
            ))
            # 更新进度
            progress2 = (await db2.execute(
                select(ReadingProgress).where(ReadingProgress.book_id == book.id)
            )).scalar_one_or_none()
            if progress2:
                progress2.total_rounds = round_idx + 2
            await db2.commit()

            # 检查是否本章结束 → 调用 Prompt C 提取概念
            if _is_chapter_end(full_response):
                concepts_data = await extract_concepts(chapter, history + [
                    {"role": "assistant", "content": full_response}
                ])
                for c in concepts_data.get("concepts", []):
                    entry = WikiEntry(
                        user_id=user.id, book_id=book.id,
                        concept_name=c["name"],
                        chapter_index=chapter,
                        ai_definition=c.get("definition", ""),
                        source_quote=c.get("source_quote"),
                        tags=c.get("tags", []),
                    )
                    db2.add(entry)
                for v in concepts_data.get("viewpoints", []):
                    entry = WikiEntry(
                        user_id=user.id, book_id=book.id,
                        concept_name=v["statement"][:300],
                        chapter_index=chapter,
                        ai_definition=v.get("statement", ""),
                        source_quote=None,
                        tags=v.get("tags", []),
                    )
                    db2.add(entry)
                await db2.commit()
        finally:
            await db2.close()

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@router.get("/progress/{book_id}", response_model=ProgressResponse)
async def get_progress(
    book_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    book = await _get_book(db, book_id, user.id)
    progress = book.progress
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


# ── helpers ──

async def _get_book(db: AsyncSession, book_id: uuid.UUID, user_id: uuid.UUID) -> Book:
    result = await db.execute(
        select(Book).where(Book.id == book_id, Book.user_id == user_id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return book


def _extract_chapter_text(full_text: str, chapter: int, total_chapters: int) -> str:
    """
    从全书 Markdown 中提取指定章节文本。
    简单策略：按「第X章」模式分割；如果找不到，返回前 1/N 的文本。
    """
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

    # fallback：均分
    chunk_size = len(full_text) // max(total_chapters, 1)
    start = (chapter - 1) * chunk_size
    end = start + chunk_size if chapter < total_chapters else len(full_text)
    return full_text[start:end]


def _is_chapter_end(response: str) -> bool:
    """检测 AI 回应是否标识了本章结束"""
    markers = ["本章完成", "本章结束", "进入下一章", "章节总结", "本章用户理解的所有概念"]
    return any(m in response for m in markers)


def async_session():
    """创建独立的数据库会话（用于流式回调中保存数据）"""
    from app.database import async_session as _session
    return _session()
