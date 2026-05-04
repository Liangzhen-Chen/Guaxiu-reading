"""
通用 AI JSON 提取 + 校验 + 重试机制。
所有 AI 调用点复用此模块，确保 JSON 输出可靠。
"""
import json
import re
from typing import Any


def extract_json(raw: str) -> dict:
    """
    从 AI 原始输出中提取 JSON。
    四层 fallback:
      1. 直接 json.loads
      2. 从 ```json 代码块提取
      3. 正则提取 { } 对象
      4. 补全截断的 JSON
    """
    raw = raw.strip()

    # 策略1: 直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 策略2: 从 ```json 代码块提取
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 策略3: 提取 { } 对象
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
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
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

    raise ValueError("Failed to extract valid JSON from AI response")


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
