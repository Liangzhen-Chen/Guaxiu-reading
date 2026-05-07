"""
苏格拉底导读服务 —— Prompt 管理 + 被引用的工具函数。

⚠️ Prompt 文本在 prompts_private.py（不上传 Git），
   本地开发时复制 prompts_example.py → prompts_private.py 填入真实 prompt。

P5-5: 删除未调用函数: build_context, socratic_chat_stream, get_socratic_prompt, extract_concepts。
      保留 _p, detect_language, compress_conversation, generate_chapter_structure,
      generate_assessment_question（当前仍被 reading.py 和 books.py 使用）。
"""
from app.config import settings
from app.services.llm_service import chat, chat_stream, count_tokens

# ── 从私有文件导入 Prompt ──
try:
    from prompts_private import (
        CHAPTER_STRUCTURE_TEMPLATE, DEEP_EXTRA,
        SOCRATIC_BASE, SOCRATIC_DEEP_EXTRA,
        CONCEPT_EXTRACTION_PROMPT, ASSESSMENT_PROMPT, COMPRESSION_PROMPT,
        CHAPTER_STRUCTURE_TEMPLATE_EN, DEEP_EXTRA_EN,
        SOCRATIC_BASE_EN, SOCRATIC_DEEP_EXTRA_EN,
        CONCEPT_EXTRACTION_PROMPT_EN, ASSESSMENT_PROMPT_EN, COMPRESSION_PROMPT_EN,
        P1_BOOK_PARSE, P2_CHAPTER_WIKIS,
        P4_READING_CYCLE, P5_CHAPTER_CONFIRM,
        P1_BOOK_PARSE_EN, P2_CHAPTER_WIKIS_EN,
        P4_READING_CYCLE_EN, P5_CHAPTER_CONFIRM_EN,
    )
except ImportError:
    raise ImportError(
        "prompts_private.py 未找到。"
        "请复制 prompts_example.py → prompts_private.py 并填入真实 prompt 文本。"
    )

# ── 语言切换映射 ──
_PROMPTS = {
    "zh": {
        "chapter": CHAPTER_STRUCTURE_TEMPLATE,
        "deep": DEEP_EXTRA, "socratic": SOCRATIC_BASE,
        "socratic_deep": SOCRATIC_DEEP_EXTRA,
        "extraction": CONCEPT_EXTRACTION_PROMPT, "assessment": ASSESSMENT_PROMPT,
        "compress": COMPRESSION_PROMPT,
        "p1_parse": P1_BOOK_PARSE, "p2_wikis": P2_CHAPTER_WIKIS,
        "p4_reading": P4_READING_CYCLE, "p5_confirm": P5_CHAPTER_CONFIRM,
    },
    "en": {
        "chapter": CHAPTER_STRUCTURE_TEMPLATE_EN,
        "deep": DEEP_EXTRA_EN, "socratic": SOCRATIC_BASE_EN,
        "socratic_deep": SOCRATIC_DEEP_EXTRA_EN,
        "extraction": CONCEPT_EXTRACTION_PROMPT_EN, "assessment": ASSESSMENT_PROMPT_EN,
        "compress": COMPRESSION_PROMPT_EN,
        "p1_parse": P1_BOOK_PARSE_EN, "p2_wikis": P2_CHAPTER_WIKIS_EN,
        "p4_reading": P4_READING_CYCLE_EN, "p5_confirm": P5_CHAPTER_CONFIRM_EN,
    },
}


def _p(key: str, language: str = "zh") -> str:
    """获取指定语言的 prompt"""
    return _PROMPTS.get(language, _PROMPTS["zh"])[key]


def detect_language(text: str) -> str:
    """检测文本语言：分析前 10000 字符中文字符比例。
    中文占比超过 10% 判为 zh，否则判为 en。"""
    sample = text[:10000].strip()
    if not sample:
        return "zh"
    chinese_chars = sum(1 for c in sample if '一' <= c <= '鿿')
    chinese_ratio = chinese_chars / len(sample)
    return "zh" if chinese_ratio > 0.1 else "en"


# ── 保留：仍被 reading.py 直接调用的函数 ──

async def generate_chapter_structure(
    book_title: str, chapter_index: int, chapter_text: str,
    mode: str = "quick", language: str = "zh",
) -> dict:
    """Prompt A: 生成章节导读框架"""
    extra = ""
    if mode == "deep":
        extra = _p("deep", language)
    # Use replace() instead of format() for prompt safety (P5-8)
    prompt = _p("chapter", language)
    prompt = prompt.replace("{book_title}", book_title)
    prompt = prompt.replace("{chapter_index}", str(chapter_index))
    prompt = prompt.replace("{extra_instructions}", extra)

    result = await chat(
        [{"role": "system", "content": prompt}, {"role": "user", "content": chapter_text}],
        temperature=0.3, max_tokens=2000,
        response_format={"type": "json_object"},
    )
    import json, re
    try:
        return json.loads(result)
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r'\{.*\}', result, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    json_str = result.strip()
    if json_str.startswith('{'):
        open_cnt = json_str.count('{') - json_str.count('}')
        json_str += '}' * open_cnt
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    return {"error": "章节框架解析失败", "raw": result[:500]}


async def generate_assessment_question(
    book_title: str, author: str, category: str,
    conversation_history: list[dict], language: str = "zh",
) -> str:
    """Prompt D: 生成下一轮背景评估问题（选择题卡片格式）"""
    import json, re
    prompt = _p("assessment", language)
    prompt = prompt.replace("{book_title}", book_title)
    prompt = prompt.replace("{author}", author or "Unknown")
    prompt = prompt.replace("{category}", category or "General")
    messages = [{"role": "system", "content": prompt}, *conversation_history]
    result = await chat(messages, temperature=0.7)

    try:
        json.loads(result)
        return result
    except (json.JSONDecodeError, TypeError):
        pass

    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', result, re.DOTALL)
    if m:
        try:
            json.loads(m.group(1))
            return m.group(1)
        except (json.JSONDecodeError, TypeError):
            pass

    m = re.search(r'\{.*\}', result, re.DOTALL)
    if m:
        try:
            json.loads(m.group(0))
            return m.group(0)
        except (json.JSONDecodeError, TypeError):
            pass

    return json.dumps({"question": result[:200], "options": []}, ensure_ascii=False)


async def compress_conversation(old_messages: list[dict], language: str = "zh") -> str:
    """Prompt E: 调用 LLM 压缩旧对话为简短摘要"""
    dialogue = "\n".join(
        f"{m['role']}: {m['content']}" for m in old_messages
    )
    prompt = _p("compress", language)
    prompt = prompt.replace("{old_conversation}", dialogue)
    try:
        result = await chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=300,
        )
        return result.strip()
    except Exception:
        user_messages = [m["content"] for m in old_messages if m.get("role") == "user"]
        return f"Previous summary: {'; '.join(user_messages[-5:])}" if user_messages else ""
