"""
苏格拉底导读服务 —— 核心业务逻辑。
编排 LLM 调用，管理多轮对话记忆，控制追问深度。

⚠️ Prompt 文本在 prompts_private.py（不上传 Git），
   本地开发时复制 prompts_example.py → prompts_private.py 填入真实 prompt。
   Prompt 版本追踪见: 项目管理/03-prompts/
"""
from app.config import settings
from app.services.llm_service import chat, chat_stream, count_tokens

# ── 从私有文件导入 Prompt ──
try:
    from prompts_private import (
        CHAPTER_STRUCTURE_TEMPLATE, BALANCED_EXTRA, DEEP_EXTRA,
        SOCRATIC_BASE, SOCRATIC_BALANCED_EXTRA, SOCRATIC_DEEP_EXTRA,
        CONCEPT_EXTRACTION_PROMPT, ASSESSMENT_PROMPT, COMPRESSION_PROMPT,
        CHAPTER_STRUCTURE_TEMPLATE_EN, BALANCED_EXTRA_EN, DEEP_EXTRA_EN,
        SOCRATIC_BASE_EN, SOCRATIC_BALANCED_EXTRA_EN, SOCRATIC_DEEP_EXTRA_EN,
        CONCEPT_EXTRACTION_PROMPT_EN, ASSESSMENT_PROMPT_EN, COMPRESSION_PROMPT_EN,
    )
except ImportError:
    raise ImportError(
        "prompts_private.py 未找到。"
        "请复制 prompts_example.py → prompts_private.py 并填入真实 prompt 文本。"
    )

# ── 语言切换映射 ──
_PROMPTS = {
    "zh": {
        "chapter": CHAPTER_STRUCTURE_TEMPLATE, "balanced": BALANCED_EXTRA,
        "deep": DEEP_EXTRA, "socratic": SOCRATIC_BASE,
        "socratic_balanced": SOCRATIC_BALANCED_EXTRA, "socratic_deep": SOCRATIC_DEEP_EXTRA,
        "extraction": CONCEPT_EXTRACTION_PROMPT, "assessment": ASSESSMENT_PROMPT,
        "compress": COMPRESSION_PROMPT,
    },
    "en": {
        "chapter": CHAPTER_STRUCTURE_TEMPLATE_EN, "balanced": BALANCED_EXTRA_EN,
        "deep": DEEP_EXTRA_EN, "socratic": SOCRATIC_BASE_EN,
        "socratic_balanced": SOCRATIC_BALANCED_EXTRA_EN, "socratic_deep": SOCRATIC_DEEP_EXTRA_EN,
        "extraction": CONCEPT_EXTRACTION_PROMPT_EN, "assessment": ASSESSMENT_PROMPT_EN,
        "compress": COMPRESSION_PROMPT_EN,
    },
}

def _p(key: str, language: str = "zh") -> str:
    """获取指定语言的 prompt"""
    return _PROMPTS.get(language, _PROMPTS["zh"])[key]


def get_chapter_structure_prompt(mode: str, book_title: str, chapter_index: int, language: str = "zh") -> str:
    extra = ""
    if mode == "balanced":
        extra = _p("balanced", language)
    elif mode == "deep":
        extra = _p("deep", language)
    return _p("chapter", language).format(
        book_title=book_title, chapter_index=chapter_index, extra_instructions=extra,
    )


def get_socratic_prompt(mode: str, chapter_framework: dict, language: str = "zh") -> str:
    import json
    framework_str = json.dumps(chapter_framework, ensure_ascii=False, indent=2)
    prompt = _p("socratic", language).format(chapter_framework=framework_str)
    if mode == "balanced":
        prompt += _p("socratic_balanced", language)
    elif mode == "deep":
        prompt += _p("socratic_deep", language)
    return prompt


async def build_context(
    book_text: str,
    conversation_history: list[dict],
    current_chapter: int,
    language: str = "zh",
) -> list[dict]:
    """构建送给 LLM 的完整上下文。超过阈值时异步调用 Prompt E 压缩旧对话。"""
    history_text = "\n".join(m.get("content", "") for m in conversation_history)
    total_estimate = count_tokens(book_text) + count_tokens(history_text)

    if total_estimate > settings.context_max_tokens:
        window = settings.context_window_rounds
        recent = conversation_history[-(window * 2):]
        old = conversation_history[:-(window * 2)]
        if old:
            old_summary = await compress_conversation(old, language)
            recent.insert(0, {"role": "system", "content": old_summary})
        conversation_history = recent

    messages = [{"role": "system", "content": f"以下是本书全文，请基于此书进行苏格拉底式导读：\n\n{book_text}"}]
    messages.extend(conversation_history)
    return messages


async def compress_conversation(old_messages: list[dict], language: str = "zh") -> str:
    """Prompt E: 调用 LLM 压缩旧对话为简短摘要"""
    dialogue = "\n".join(
        f"{m['role']}: {m['content']}" for m in old_messages
    )
    prompt = _p("compress", language).format(old_conversation=dialogue)
    try:
        result = await chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=300,
        )
        return result.strip()
    except Exception:
        # LLM 压缩失败 → 降级为简单截断
        user_messages = [m["content"] for m in old_messages if m.get("role") == "user"]
        return f"Previous summary: {'; '.join(user_messages[-5:])}" if user_messages else ""


async def generate_chapter_structure(
    book_title: str, chapter_index: int, chapter_text: str,
    mode: str = "quick", language: str = "zh",
) -> dict:
    """Prompt A: 生成章节导读框架"""
    prompt = get_chapter_structure_prompt(mode, book_title, chapter_index, language)
    result = await chat(
        [{"role": "system", "content": prompt}, {"role": "user", "content": chapter_text}],
        temperature=0.3, max_tokens=2000,
    )
    import json, re
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        pass
    # Try to extract JSON from markdown code block
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result, re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except json.JSONDecodeError: pass
    # Try to extract JSON object from text
    m = re.search(r'\{.*\}', result, re.DOTALL)
    if m:
        try: return json.loads(m.group(0))
        except json.JSONDecodeError: pass
    # Try to fix truncated JSON by closing braces
    json_str = result.strip()
    if json_str.startswith('{'):
        # Count braces and close if needed
        open_cnt = json_str.count('{') - json_str.count('}')
        json_str += '}' * open_cnt
        try: return json.loads(json_str)
        except json.JSONDecodeError: pass
    return {"error": "章节框架解析失败", "raw": result[:500]}


async def socratic_chat_stream(
    mode: str, chapter_framework: dict, book_text: str,
    conversation_history: list[dict], user_message: str,
    language: str = "zh", model: str | None = None,
):
    """Prompt B: 苏格拉底追问，流式返回"""
    system_prompt = get_socratic_prompt(mode, chapter_framework, language)
    messages = [{"role": "system", "content": f"{system_prompt}\n\n## 全书原文\n{book_text}"}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    full_text = "\n".join(m.get("content", "") for m in messages)
    if count_tokens(full_text) > settings.context_max_tokens:
        messages = await build_context(book_text, messages[1:], 0, language)

    async for token in chat_stream(messages, model=model):
        yield token


async def extract_concepts(chapter_index: int, conversation_history: list[dict], language: str = "zh", chapter_concepts: list[str] = None) -> dict:
    """Prompt C: 从对话中提取概念和观点（含 evidence）"""
    concepts_str = ", ".join(chapter_concepts) if chapter_concepts else "（未提供）"
    prompt = _p("extraction", language).format(chapter_index=chapter_index, chapter_concepts=concepts_str)
    dialogue = "\n".join(f"{m['role']}: {m['content']}" for m in conversation_history)
    result = await chat(
        [{"role": "system", "content": prompt}, {"role": "user", "content": f"对话记录：\n\n{dialogue}"}],
        temperature=0.3, max_tokens=3000,
    )
    import json
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {"concepts": [], "viewpoints": []}


async def generate_assessment_question(
    book_title: str, author: str, category: str,
    conversation_history: list[dict], language: str = "zh",
) -> str:
    """Prompt D: 生成下一轮背景评估问题（选择题卡片格式）"""
    import json, re
    prompt = _p("assessment", language).format(
        book_title=book_title, author=author or "Unknown", category=category or "General"
    )
    messages = [{"role": "system", "content": prompt}, *conversation_history]
    result = await chat(messages, temperature=0.7)

    # Try to parse as JSON directly
    try: json.loads(result); return result
    except (json.JSONDecodeError, TypeError): pass

    # Try markdown code block
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result, re.DOTALL)
    if m:
        try: json.loads(m.group(1)); return m.group(1)
        except (json.JSONDecodeError, TypeError): pass

    # Try extracting JSON object
    m = re.search(r'\{.*\}', result, re.DOTALL)
    if m:
        try: json.loads(m.group(0)); return m.group(0)
        except (json.JSONDecodeError, TypeError): pass

    # Fallback: wrap as plain text question
    return json.dumps({"question": result[:200], "options": []}, ensure_ascii=False)
