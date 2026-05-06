"""
LLM 调用服务 —— DeepSeek API，支持流式输出。
⚠️ 预留切换口：修改 model= 参数即可切到任意 OpenAI 兼容模型
"""
import logging
import httpx
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

# ⚠️ 切换模型只需改 .env 中的 LLM_MODEL，或运行时传 model 参数
_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


async def chat_stream(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: httpx.Timeout | None = None,
):
    """
    流式对话 —— 返回 async generator，逐 token 产出。
    调用方: socratic_service 的苏格拉底追问
    """
    if timeout is None:
        timeout = httpx.Timeout(settings.llm_timeout_connect, read=settings.llm_timeout_read)
    client = get_client()
    stream = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        timeout=timeout,
    )
    usage = None
    async for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if chunk.choices and len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    if usage:
        logger.debug("LLM stream usage: prompt_tokens=%s, completion_tokens=%s",
                     usage.prompt_tokens, usage.completion_tokens)


async def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: httpx.Timeout | None = None,
) -> str:
    """非流式对话 —— 用于概念提取等不需要流式输出的场景"""
    if timeout is None:
        timeout = httpx.Timeout(settings.llm_timeout_connect, read=settings.llm_timeout_read)
    client = get_client()
    response = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    logger.debug("LLM chat usage: prompt_tokens=%s, completion_tokens=%s",
                 response.usage.prompt_tokens, response.usage.completion_tokens)
    return response.choices[0].message.content or ""


def count_tokens(text: str) -> int:
    """估算 token 数 —— 中文 1.8 token/字，英文 1.3 token/词"""
    # 简化估算；生产环境可用 tiktoken
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.8 + other_chars * 0.3)
