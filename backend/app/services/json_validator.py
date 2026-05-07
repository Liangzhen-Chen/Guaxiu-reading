"""
通用 AI JSON 提取 + 校验 + 重试机制。
所有 AI 调用点复用此模块，确保 JSON 输出可靠。
"""
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Track which fallback strategies are used (for debugging JSON reliability)
_fallback_used: set[str] = set()


def extract_json(raw: str) -> dict:
    """
    从 AI 原始输出中提取 JSON。
    预处理 + 四层 fallback:
      0. 预处理：移除尾部逗号、转换单引号 JSON
      1. 直接 json.loads
      2. 从 ```json 代码块提取
      3. 正则提取 { } 对象
      4. 补全截断的 JSON
    """
    raw = raw.strip()

    # 预处理 0a: 移除对象/数组末尾的逗号 (trailing comma)
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)

    # 预处理 0b: 将单引号键/值转换为双引号 (兼容 Python dict 风格输出)
    # 匹配单引号括起来的键，如 {'key': ...} -> {"key": ...}
    raw = re.sub(r"(?<!\\)'([^']*)'(?=\s*:)", r'"\1"', raw)
    # 匹配单引号括起来的值，如 {"key": 'value'} -> {"key": "value"}
    raw = re.sub(r'(?<=:)\s*\'([^\']*)\'(?=\s*[,}\]])', r'"\1"', raw)

    # 策略1: 直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 策略2: 从 ```json 代码块提取
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    if m:
        _mark_fallback("code_block")
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 策略3: 提取 { } 对象
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        _mark_fallback("braces_extract")
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 策略4: 补全截断的 JSON（补齐缺失的 }）
    json_str = raw.strip().rstrip(',')
    if json_str.startswith('{'):
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        missing = open_braces - close_braces
        if missing > 0:
            json_str += '}' * missing
            _mark_fallback("truncation_repair")
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

    raise ValueError("Failed to extract valid JSON from AI response")


def _mark_fallback(strategy: str) -> None:
    """Track which fallback strategy was used and log it."""
    if strategy not in _fallback_used:
        _fallback_used.add(strategy)
        logger.warning("JSON fallback strategy used: %s — check AI output quality", strategy)


def reset_fallback_tracking() -> None:
    """Reset fallback tracking (useful between requests)."""
    _fallback_used.clear()


async def ai_json_with_retry(
    chat_fn,
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    retries: int = 3,
) -> dict:
    """
    调用 AI → 提取 JSON → 失败则重试。

    Args:
        chat_fn: LLM 调用函数 (async, 返回 str)
        messages: 消息列表
        temperature: 温度
        max_tokens: 最大 token
        retries: 最大重试次数

    Returns:
        Parsed JSON dict

    Raises:
        ValueError after all retries exhausted
    """
    last_raw = ""
    messages = [*messages]  # shallow copy to avoid mutating the caller's original list
    for attempt in range(retries):
        try:
            raw = await chat_fn(messages, temperature=temperature, max_tokens=max_tokens)
            last_raw = raw
            return extract_json(raw)
        except ValueError as e:
            if attempt == retries - 1:
                raise ValueError(
                    f"AI JSON extraction failed after {retries} attempts. "
                    f"Last raw (first 300 chars): {last_raw[:300]}"
                )
            # 把错误信息塞回 message 让 AI 修正
            messages.append({"role": "assistant", "content": last_raw})
            messages.append({
                "role": "user",
                "content": (
                    f"Your response was not valid JSON: {str(e)}\n"
                    "Please output ONLY the JSON object. No markdown, no extra text. "
                    "Ensure all braces and brackets are properly closed."
                ),
            })

    raise ValueError("Unreachable")
