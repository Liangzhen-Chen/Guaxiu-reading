"""导读路由 —— 核心：苏格拉底式流式对话"""
import json
import httpx
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, delete
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

    if assessment_complete and book.progress:
        if book.progress.status != "reading":
            book.progress.status = "reading"
        if book.progress.current_chapter == 0:
            book.progress.current_chapter = 1
        # Eagerly generate chapter 1 framework so /resume has concepts
        try:
            if book.text_path:
                with open(book.text_path, "r", encoding="utf-8") as f:
                    ch1_text = _extract_chapter_text(f.read(), 1, book.chapter_count or 1, _get_chapter_markers(book))
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

    # Limit to last 30 rounds (60 messages) to avoid context overload
    if len(history) > 60:
        history = history[-60:]

    # 保存用户消息
    round_idx = len([m for m in history if m["role"] == "user"])
    db.add(Conversation(
        book_id=book.id, chapter_index=chapter,
        round_index=round_idx, role="user", content=data.message,
    ))
    await db.commit()
    history.append({"role": "user", "content": data.message})

    # /next shortcut: skip AI call, directly advance chapter
    if data.message.strip() == "/next":
        async def generate():
            db2 = async_session()
            try:
                progress2 = (await db2.execute(
                    select(ReadingProgress).where(ReadingProgress.book_id == book.id)
                )).scalar_one_or_none()
                if progress2:
                    total = book.chapter_count or 1
                    if chapter >= total:
                        progress2.status = "completed"
                        progress2.current_wiki_id = None
                        progress2.completed_wikis = []
                    else:
                        progress2.current_chapter = chapter + 1
                        progress2.status = "paused"
                        progress2.current_wiki_id = None
                        progress2.completed_wikis = []
                    await db2.commit()
                yield "\n\n<!--CHAPTER_END-->"
            finally:
                await db2.close()
        return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")

    # 组装 P4 prompt
    if mode == "quick":
        mode_desc = "快速模式"
        mode_sop = """## 快速模式 SOP
1. **进入新 Wiki 时**：reading_material 必须放**当前 wiki 概念的详细概括**（该概念的定义、核心要点、与读者的关联，不是整章总览）。ai_response 提出 1-2 个苏格拉底式追问引导用户思考
2. **用户回答后**：判定理解程度。若准确则追问 1 个不同角度的问题；若基本准确则确认后 wiki_transition=true，current_wiki.id 更新为 wiki_checklist 中的下一个；若有偏差则换个方式再追问一次
3. **过渡时**：reading_material 必须立即切换为新 wiki 概念的内容
4. **每连续完成 4-5 个 wiki**：在 ai_response 中顺带问一句"前面这些有什么问题吗"，但不要停下
5. **禁止**：主动问用户"要不要继续"、"想先了解哪个"、"给你几个选项"——所有过渡由你判定"""
    else:
        mode_desc = "深度模式"
        mode_sop = """## 深度模式 SOP
1. **进入新 Wiki 时**：不直接给出总结。reading_material 放**当前 wiki 概念相关的原文段落**（从 wiki 的 quotes 中选取，至少2-3段），ai_response 提出引导性问题让用户自己从原文中提炼理解（如"你觉得这段话的核心观点是什么？"）；ai_response 中以「> 原文：」格式引用关键原文
2. **用户初次回答后**：不立即评判对错。换一段原文或换个角度，再问 1-2 次，引导用户深化理解（2-3 轮原文引导）
3. **用户理解后**：进入苏格拉底追问阶段（2-3 轮），从不同场景/角度验证理解
4. **判定理解后 wiki_transition=true**，current_wiki.id 更新为 wiki_checklist 中的下一个。reading_material 立即切换为新 wiki 概念的内容
5. **禁止**：主动问用户"要不要继续"、给选项——所有过渡由你判定"""

    profile = {}
    if progress.assessment_result:
        try: profile = json.loads(progress.assessment_result).get("profile", {})
        except: pass

    # Language detection: if book text is predominantly English but UI is Chinese, add instruction
    lang_instruction = "中文对话" if language == "zh" else "English conversation"
    if language == "zh" and book_text:
        sample = book_text[:2000]
        ascii_chars = sum(1 for c in sample if ord(c) < 128)
        if ascii_chars > len(sample) * 0.6:
            # Book is mostly English, user wants Chinese
            lang_instruction = """重要语言规则：本书原文为英文。你必须使用中文进行对话和提问。
- ai_response 全部用中文，包括对用户的理解反馈、追问等
- reading_material 可以用英文原文（保持原汁原味），但如果引用原文后需附带中文解释
- 禁止直接用英文与用户对话"""

    # No wiki fallback message
    no_wiki_note = ""
    if not wiki_checklist:
        no_wiki_note = "\n## ⚠️ 本章暂无预生成Wiki清单。请基于全书原文和对话历史，自行从文本中提炼概念来引导用户。行为如同快速模式。"

    # P6: Compress conversation history if too many rounds
    user_rounds = len([m for m in history if m["role"] == "user"])
    if user_rounds > 15:
        from app.services.socratic_service import compress_conversation
        # Keep last ~10 user rounds (walk backwards from end)
        keep_rounds = 10
        split_idx = len(history)
        counted = 0
        for i in range(len(history) - 1, -1, -1):
            if history[i]["role"] == "user":
                counted += 1
            if counted > keep_rounds:
                split_idx = i
                break
        if split_idx > 0:
            old_part = history[:split_idx]
            recent_part = history[split_idx:]
            try:
                compressed = await compress_conversation(old_part, language)
                recent_part.insert(0, {"role": "system", "content": f"[Previous conversation summary]: {compressed}"})
                history = recent_part
            except Exception:
                pass  # compression failure is non-critical

    p4_prompt = _p("p4_reading", language).format(
        book_title=book.title,
        mode_description=mode_desc,
        mode_sop=mode_sop,
        wiki_checklist=json.dumps(wiki_checklist, ensure_ascii=False) if wiki_checklist else "[]",
        current_wiki=f"{current_wiki_id}",
        completed_wikis=json.dumps(completed_wikis, ensure_ascii=False),
        user_profile=json.dumps(profile, ensure_ascii=False),
        language_instruction=lang_instruction,
    )

    import logging
    logger = logging.getLogger("xiugua.reading")
    logger.info("P4 call: mode=%s book=%s chapter=%d lang=%s", mode, book.id, chapter, language)

    system_msgs = [{"role": "system", "content": f"{p4_prompt}{no_wiki_note}"}]
    messages = system_msgs + history

    # 流式对话（先收集完整响应，解析JSON，再返回文本）
    async def generate():
        # Collect full response from AI
        full_response = ""
        async for token in chat_stream(messages, temperature=0.5, max_tokens=4096, timeout=httpx.Timeout(30.0, read=120.0)):
            full_response += token

        # Parse JSON response
        try:
            from app.services.json_validator import extract_json
            parsed = extract_json(full_response)
            ai_text = parsed.get("ai_response", full_response)
        except Exception:
            parsed = {"ai_response": full_response, "current_wiki": {"id": current_wiki_id, "name": ""}, "reading_material": "", "wiki_transition": False, "transition_message": ""}
            ai_text = full_response

        # D3: Save conversation to DB FIRST, then yield to user
        all_done = False
        db2 = async_session()
        try:
            db2.add(Conversation(
                book_id=book.id, chapter_index=chapter,
                round_index=round_idx + 1, role="assistant",
                content=ai_text + f"\n<!--V4_META:{json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))}-->",
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

                # Auto chapter end: all wikis completed, or fallback to round count
                all_done = (
                    (wiki_checklist and len(progress2.completed_wikis or []) >= len(wiki_checklist))
                    or (not wiki_checklist and (progress2.total_rounds or 0) > 10)
                )
                if all_done:
                    total = book.chapter_count or 1
                    if chapter >= total:
                        progress2.status = "completed"
                        progress2.current_wiki_id = None
                        progress2.completed_wikis = []
                    else:
                        progress2.current_chapter = chapter + 1
                        progress2.status = "paused"
                        progress2.current_wiki_id = None
                        progress2.completed_wikis = []

            await db2.commit()
        finally:
            await db2.close()

        # Yield to user after DB write succeeded
        yield ai_text
        yield f"\n<!--V4_META:{json.dumps(parsed, ensure_ascii=False, separators=(',', ':'))}-->"

        if all_done:
            yield "\n\n<!--CHAPTER_END-->"

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
            resp.chapter_concepts = _extract_theses(fw.get("argument_tree", {}))
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
                resp.chapter_concepts = _extract_theses(framework.get("argument_tree", {}))
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
    chapter_text = _extract_chapter_text(full_text, chapter, book.chapter_count or 1, _get_chapter_markers(book))
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
        # v4.0: Build wiki_checklist from preprocess data even for not_started
        wiki_checklist = _build_wiki_checklist(book, 1, None)
        resp.wiki_checklist = wiki_checklist
        try:
            if book.category:
                framework = json.loads(book.category)
                resp.chapter_concepts = _extract_theses(framework.get("argument_tree", {}))
        except: pass
        return resp

    resp = _to_progress_response(book, progress)

    # v4.0: Wiki state
    resp.current_wiki_id = progress.current_wiki_id
    resp.completed_wikis = progress.completed_wikis or []

    # Build wiki checklist for left column
    if progress.current_chapter <= 0:
        progress.current_chapter = 1  # fix stale chapter from old assessment bug
    chapter = progress.current_chapter
    resp.wiki_checklist = _build_wiki_checklist(book, chapter, progress)

    # 加载最近对话（仅当前章节，不含评估对话）
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
        # Strip V4_META marker, extract reading_material if present
        meta_match = _re2.search(r'<!--V4_META:([\s\S]*?)-->', content)
        if meta_match:
            try:
                parsed = json.loads(meta_match.group(1))
                last_material = parsed.get("reading_material", "")
            except: pass
            content = _re2.sub(r'<!--V4_META:[\s\S]*?-->', '', content).strip()
        clean_messages.append({"role": m.role, "content": content, "round": m.round_index})
    resp.last_messages = clean_messages
    resp.reading_material = last_material  # restore center column content

    # For not_started books, try to get concepts from parsed framework
    if not progress or progress.status == "not_started":
        try:
            if book.category:
                framework = json.loads(book.category)
                resp.chapter_concepts = _extract_theses(framework.get("argument_tree", {}))
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


def _build_wiki_checklist(book, chapter: int, progress) -> list:
    """Build wiki checklist for the left column from preprocess data."""
    items = []
    if book.preprocess_progress:
        ch_wikis = book.preprocess_progress.get("chapter_wikis", {}).get(str(chapter), {})
        for w in ch_wikis.get("wikis", []):
            wiki_id = w.get("id", "")
            status = "pending"
            if progress:
                if wiki_id == progress.current_wiki_id:
                    status = "active"
                elif wiki_id in (progress.completed_wikis or []):
                    status = "done"
            items.append({"id": wiki_id, "name": w.get("name", ""), "status": status})
    return items


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


def _extract_chapter_text(full_text: str, chapter: int, total_chapters: int,
                          markers: list | None = None) -> str:
    """
    提取指定章节文本。
    优先用 P1 验证过的 keep 章节名按位置切分；fallback 到正则。
    """
    import re
    pattern = r"(第[一二三四五六七八九十百千\d]+章|Chapter\s+\d+|CHAPTER\s+\d+)"

    # Strategy 1: P1-validated keepers with regex positions
    if markers:
        # Find all regex matches with positions
        regex_matches = [(m.group(0), m.start()) for m in re.finditer(pattern, full_text)]
        # Filter to only keepers (AI-validated)
        keeper_titles = set(m.strip().upper().replace(' ', '') for m in markers)
        keeper_positions = [(title, pos) for title, pos in regex_matches
                           if title.strip().upper().replace(' ', '') in keeper_titles]
        # Deduplicate by position (keep first occurrence of each title)
        seen = set()
        unique_positions = []
        for title, pos in keeper_positions:
            norm = title.strip().upper().replace(' ', '')
            if norm not in seen:
                seen.add(norm)
                unique_positions.append((title, pos))
        unique_positions.sort(key=lambda x: x[1])

        if chapter <= len(unique_positions):
            _, start_pos = unique_positions[chapter - 1]
            if chapter < len(unique_positions):
                _, end_pos = unique_positions[chapter]
                return full_text[start_pos:end_pos]
            return full_text[start_pos:]

    # Strategy 2: Regex split + dedup
    parts = re.split(pattern, full_text)
    if len(parts) > 2:
        chapter_map = {}
        chapter_order = []
        i = 1
        while i < len(parts):
            title = parts[i]
            content = parts[i + 1] if i + 1 < len(parts) else ""
            if title in chapter_map:
                chapter_map[title] += "\n\n" + content
            else:
                chapter_map[title] = content
                chapter_order.append(title)
            i += 2
        chapters = [title + chapter_map[title] for title in chapter_order]
        if chapter <= len(chapters):
            return chapters[chapter - 1]

    # Strategy 3: Even split
    chunk_size = len(full_text) // max(total_chapters, 1)
    start = (chapter - 1) * chunk_size
    end = start + chunk_size if chapter < total_chapters else len(full_text)
    return full_text[start:end]


def _get_chapter_markers(book) -> list | None:
    """从 book.category (P1 JSON) 提取 keep 章节标题列表"""
    import json
    try:
        if book.category:
            data = json.loads(book.category)
            keep = data.get("keep_chapters", [])
            if keep:
                # Clean: remove snippet text after " | "
                return [c.split(" | ")[0].strip() for c in keep if c.strip()]
            vc = data.get("validated_chapters", [])
            if vc: return [c["regex_title"] for c in vc if c.get("action") == "keep"]
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _extract_theses(node) -> list:
    """Recursively extract thesis statements from an argument tree node."""
    items = []
    if isinstance(node, dict):
        if node.get("thesis"):
            items.append(node["thesis"])
        for b in node.get("branches", []):
            items.extend(_extract_theses(b))
    return items


def async_session():
    from app.database import async_session as _session
    return _session()
