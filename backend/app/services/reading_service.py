"""
阅读服务 —— P4 循环核心逻辑：Prompt 构建、Wiki 状态管理、CHAPTER_END 检测。
P5-1: 从 reading.py 提取 P4 prompt 构建、wiki 状态管理、CHAPTER_END 检测。
"""
import json
import hashlib
import logging
from app.services.socratic_service import _p, compress_conversation as _compress_conv

logger = logging.getLogger("xiugua.reading_service")

# P2-13: Compression result cache (avoid re-compressing identical conversation segments)
_compression_cache: dict[str, str] = {}

# P4-7: SOP templates (string constants, no f-string injection)
_QUICK_SOP = (
    "## 快速模式 SOP\n"
    "1. **进入新 Wiki 时**：reading_material 必须放**当前 wiki 概念的详细概括**"
    "（该概念的定义、核心要点、与读者的关联，不是整章总览）。"
    "ai_response 提出 1-2 个苏格拉底式追问引导用户思考\n"
    "2. **用户回答后**：判定理解程度。若准确则追问 1 个不同角度的问题；"
    "若基本准确则确认后 wiki_transition=true，current_wiki.id 更新为 wiki_checklist 中的下一个；"
    "若有偏差则换个方式再追问一次\n"
    "3. **过渡时**：reading_material 必须立即切换为新 wiki 概念的内容\n"
    "4. **每连续完成 4-5 个 wiki**：在 ai_response 中顺带问一句\"前面这些有什么问题吗\"，但不要停下\n"
    "5. **禁止**：主动问用户\"要不要继续\"、\"想先了解哪个\"、\"给你几个选项\"——所有过渡由你判定"
)

_DEEP_SOP = (
    "## 深度模式 SOP\n"
    "1. **进入新 Wiki 时**：不直接给出总结。reading_material 放**当前 wiki 概念相关的原文段落**"
    "（从 wiki 的 quotes 中选取，至少2-3段），ai_response 提出引导性问题让用户自己从原文中提炼理解"
    "（如\"你觉得这段话的核心观点是什么？\"）；ai_response 中以「> 原文：」格式引用关键原文\n"
    "2. **用户初次回答后**：不立即评判对错。换一段原文或换个角度，再问 1-2 次，"
    "引导用户深化理解（2-3 轮原文引导）\n"
    "3. **用户理解后**：进入苏格拉底追问阶段（2-3 轮），从不同场景/角度验证理解\n"
    "4. **判定理解后 wiki_transition=true**，current_wiki.id 更新为 wiki_checklist 中的下一个。"
    "reading_material 立即切换为新 wiki 概念的内容\n"
    "5. **禁止**：主动问用户\"要不要继续\"、给选项——所有过渡由你判定"
)


def build_reading_prompt(progress, book, wiki_checklist, chapter, language):
    """构建 P4 阅读循环 system prompt（含所有占位符替换）。

    Returns:
        (p4_prompt, no_wiki_note)
    """
    mode = progress.mode if progress else "quick"
    language = language or "zh"

    mode_desc = "快速模式" if mode == "quick" else "深度模式"
    mode_sop = _QUICK_SOP if mode == "quick" else _DEEP_SOP

    # P5-4: Read profile from assessment_result (now JSONB, not JSON string)
    profile = {}
    if progress and progress.assessment_result:
        if isinstance(progress.assessment_result, dict):
            profile = progress.assessment_result.get("profile", {})
        elif isinstance(progress.assessment_result, str):
            try:
                profile = json.loads(progress.assessment_result).get("profile", {})
            except Exception:
                logger.warning("Failed to parse assessment_result str", exc_info=True)

    lang_instruction = "中文对话" if language == "zh" else "English conversation"

    no_wiki_note = ""
    if not wiki_checklist:
        no_wiki_note = (
            "\n## ⚠️ 本章暂无预生成Wiki清单。"
            "请基于全书原文和对话历史，自行从文本中提炼概念来引导用户。行为如同快速模式。"
        )

    chapter_context = _build_chapter_context(book, chapter)

    p4_prompt = _p("p4_reading", language)
    p4_prompt = p4_prompt.replace("{book_title}", book.title)
    p4_prompt = p4_prompt.replace("{mode_description}", mode_desc)
    p4_prompt = p4_prompt.replace("{mode_sop}", mode_sop)
    p4_prompt = p4_prompt.replace(
        "{wiki_checklist}",
        json.dumps(wiki_checklist, ensure_ascii=False) if wiki_checklist else "[]",
    )
    p4_prompt = p4_prompt.replace(
        "{current_wiki}",
        f"{progress.current_wiki_id if progress else ''}",
    )
    p4_prompt = p4_prompt.replace(
        "{completed_wikis}",
        json.dumps(progress.completed_wikis or [] if progress else [], ensure_ascii=False),
    )
    p4_prompt = p4_prompt.replace(
        "{user_profile}",
        json.dumps(profile, ensure_ascii=False),
    )
    p4_prompt = p4_prompt.replace("{language_instruction}", lang_instruction)
    p4_prompt = p4_prompt.replace("{chapter_context}", chapter_context)

    logger.info("P4 prompt built: mode=%s book=%s chapter=%d lang=%s",
                mode, book.id, chapter, language)

    return p4_prompt, no_wiki_note


def manage_wiki_state(progress, wiki_checklist, history, chapter):
    """检测过长的同 Wiki 轮次，必要时强制推进。

    分析对话历史中同一 wiki 停留的轮数。若超过阈值（5轮），
    直接推进 wiki 指针并返回 force_skip_note 注入 prompt。

    Returns:
        force_skip_note: str，空字符串表示无需推进
    """
    import re as _re
    if not progress or not wiki_checklist:
        return ""

    current_wiki_id = progress.current_wiki_id

    consecutive_same_wiki = 0
    for msg in reversed(history):
        if msg["role"] == "assistant":
            meta_match = _re.search(r'<!--V4_META:([\s\S]*?)-->', msg["content"])
            if meta_match:
                try:
                    meta_obj = json.loads(meta_match.group(1))
                    wiki_id_in_meta = meta_obj.get("current_wiki", {}).get("id", "")
                    if wiki_id_in_meta == current_wiki_id:
                        consecutive_same_wiki += 1
                    else:
                        break
                except (json.JSONDecodeError, TypeError, KeyError):
                    break
            else:
                break
        else:
            break

    force_skip_note = ""
    if consecutive_same_wiki >= 5:
        old_wiki_id = current_wiki_id
        current_idx = next(
            (i for i, w in enumerate(wiki_checklist) if w.get("id") == current_wiki_id),
            -1,
        )
        if current_idx >= 0 and current_idx + 1 < len(wiki_checklist):
            next_wiki = wiki_checklist[current_idx + 1]
            done = list(progress.completed_wikis or [])
            if current_wiki_id and current_wiki_id not in done:
                done.append(current_wiki_id)
            progress.completed_wikis = done
            progress.current_wiki_id = next_wiki.get("id", "")
            logger.warning(
                "P4-9 force-skip: directly advanced wiki %s -> %s book=%s ch=%d",
                old_wiki_id, next_wiki.get("id", ""), progress.book_id, chapter,
            )

        force_skip_note = (
            "\n\n## 强制推进指令：当前 Wiki 已在 5 轮以上未推进，"
            "请直接设定 wiki_transition=true，将 current_wiki 更新为清单中的下一个。"
            "如果用户仍未完全理解，给出简要解释后仍然必须过渡。"
        )
        logger.warning(
            "Max-retries per wiki: force-skipping wiki=%s rounds=%d book=%s ch=%d",
            old_wiki_id, consecutive_same_wiki, progress.book_id, chapter,
        )

    return force_skip_note


def _clean_v4_meta_from_history(history):
    """从对话历史中去除 V4_META 标记。"""
    import re as _re
    for msg in history:
        msg["content"] = _re.sub(
            r'<!--V4_META:[\s\S]*?-->', '', msg["content"]
        ).strip()


async def compress_history(history, language):
    """压缩过长的对话历史（超过15个用户轮次时）。

    保留最近 10 轮用户对话，将之前的对话压缩为摘要。
    使用压缩缓存避免重复压缩完全相同的对话片段。

    Returns:
        list[dict]: 压缩后的历史（或原历史如果无需压缩）
    """
    user_rounds = len([m for m in history if m["role"] == "user"])
    if user_rounds <= 15:
        return history

    keep_rounds = 10
    split_idx = len(history)
    counted = 0
    for i in range(len(history) - 1, -1, -1):
        if history[i]["role"] == "user":
            counted += 1
        if counted > keep_rounds:
            split_idx = i
            break

    if split_idx <= 0:
        return history

    old_part = history[:split_idx]
    recent_part = history[split_idx:]

    cache_key = hashlib.md5(
        json.dumps([m["content"] for m in old_part], ensure_ascii=False).encode()
    ).hexdigest()

    cached = _compression_cache.get(cache_key)
    if cached:
        compressed = cached
        logger.info("P6 compression cache hit for %s", cache_key[:8])
    else:
        try:
            compressed = await _compress_conv(old_part, language)
            _compression_cache[cache_key] = compressed
        except Exception:
            logger.warning("P6 conversation compression failed", exc_info=True)
            compressed = None

    if compressed:
        recent_part.insert(0, {
            "role": "system",
            "content": f"[Previous conversation summary]: {compressed}",
        })
        return recent_part

    return history


def parse_v4_meta(full_response, current_wiki_id):
    """从完整 AI 响应中解析 V4_META 和纯文内容。

    Returns:
        (parsed, ai_text, ai_signaled_chapter_end)
    """
    import re as _re
    from app.services.json_validator import extract_json

    parsed = {
        "ai_response": full_response,
        "current_wiki": {"id": current_wiki_id, "name": ""},
        "reading_material": "",
        "wiki_transition": False,
        "chapter_end": False,
        "transition_message": "",
    }
    ai_text = full_response

    meta_match = _re.search(r'<!--V4_META:([\s\S]*?)-->', full_response)
    if meta_match:
        try:
            parsed = json.loads(meta_match.group(1))
            ai_text = full_response[:full_response.index('<!--V4_META:')].strip()
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    else:
        try:
            parsed = extract_json(full_response)
            ai_text = parsed.get("ai_response", full_response)
        except Exception:
            pass

    CHAPTER_END_MARKER = "<!--CHAPTER_END-->"
    ai_signaled_chapter_end = CHAPTER_END_MARKER in full_response
    if CHAPTER_END_MARKER in ai_text:
        ai_text = ai_text.replace(CHAPTER_END_MARKER, "").strip()

    return parsed, ai_text, ai_signaled_chapter_end


def update_wiki_progress(progress, parsed):
    """根据 parsed V4_META 更新 ReadingProgress 的 Wiki 状态。

    当 current_wiki.id 变化时，将原 wiki 标记为已完成并设置新 wiki。
    """
    if parsed.get("current_wiki", {}).get("id"):
        new_wiki_id = parsed["current_wiki"]["id"]
        if new_wiki_id != progress.current_wiki_id:
            if progress.current_wiki_id:
                done = list(progress.completed_wikis or [])
                if progress.current_wiki_id not in done:
                    done.append(progress.current_wiki_id)
                progress.completed_wikis = done
            progress.current_wiki_id = new_wiki_id


def handle_chapter_end(progress, parsed, ai_signaled_chapter_end, book, chapter):
    """检测并执行 CHAPTER_END。返回 all_done 布尔值。"""
    all_done = parsed.get("chapter_end", False) or ai_signaled_chapter_end
    if all_done:
        # Bug 1 fix: add current wiki to completed_wikis before clearing
        # (the last wiki was never marked done because current_wiki.id didn't change)
        if progress.current_wiki_id:
            done = list(progress.completed_wikis or [])
            if progress.current_wiki_id not in done:
                done.append(progress.current_wiki_id)
            progress.completed_wikis = done
        total = book.chapter_count or 1
        if chapter >= total:
            progress.status = "completed"
        else:
            progress.current_chapter = chapter + 1
            progress.status = "paused"
        progress.current_wiki_id = None
        progress.completed_wikis = []
    return all_done


def _build_chapter_context(book, chapter):
    """构建当前章节上下文（原文 + 上一章摘要）。"""
    from app.services.chapter_service import get_chapter_text

    chapter_context = ""
    try:
        ch_text = get_chapter_text(book, chapter)
        if ch_text:
            chapter_context = f"## 当前章节原文\n\n{ch_text[:15000]}"
            if chapter > 1 and book.preprocess_progress:
                prev_wikis = (
                    book.preprocess_progress.get("chapter_wikis", {})
                    .get(str(chapter - 1), {})
                )
                prev_summary = prev_wikis.get("chapter_summary", "")
                if prev_summary:
                    chapter_context += f"\n\n## 上一章摘要\n\n{prev_summary}"
    except Exception:
        logger.warning("P2-6: failed to build chapter_context", exc_info=True)

    return chapter_context
