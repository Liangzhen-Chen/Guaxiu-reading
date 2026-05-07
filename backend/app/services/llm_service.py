"""
LLM 调用服务 —— DeepSeek API，支持流式输出。
⚠️ 预留切换口：修改 model= 参数即可切到任意 OpenAI 兼容模型
"""
import logging
import time
import asyncio
import httpx
from openai import AsyncOpenAI
from app.config import settings
from app.log_utils import get_request_id

logger = logging.getLogger(__name__)

# ⚠️ 切换模型只需改 .env 中的 LLM_MODEL，或运行时传 model 参数
_client: AsyncOpenAI | None = None


def _log_llm_usage(
    request_id: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    stream: bool = False,
    elapsed_ms: int | None = None,
) -> None:
    """Emit a structured JSON log entry for LLM token usage."""
    if prompt_tokens is None or completion_tokens is None:
        return
    cost_prompt = prompt_tokens * (settings.llm_cost_prompt_per_1m / 1_000_000)
    cost_completion = completion_tokens * (settings.llm_cost_completion_per_1m / 1_000_000)
    logger.info(
        "llm_call",
        extra={
            "request_id": request_id,
            "event": "llm_call",
            "model": model,
            "stream": stream,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": round(cost_prompt + cost_completion, 6),
            "elapsed_ms": elapsed_ms,
        },
    )


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
    top_p: float | None = None,
    usage_container: list | None = None,  # P5-12: mutable list to capture usage info
):
    """
    流式对话 —— 返回 async generator，逐 token 产出。
    P2-12: 主模型失败时自动用 fallback_model 重试 1 次。
    P5-12: usage_container 为一个列表，流结束后填充 usage 信息。
    """
    if timeout is None:
        timeout = httpx.Timeout(settings.llm_timeout_connect, read=settings.llm_timeout_read)
    model_name = model or settings.llm_model
    client = get_client()
    _start = time.perf_counter()
    attempts = [(model_name, client)]
    # P2-12: If not explicitly overridden, add fallback
    if model is None and settings.llm_fallback_model:
        attempts.append((settings.llm_fallback_model, client))

    last_error = None
    for attempt_model, attempt_client in attempts:
        try:
            _start = time.perf_counter()
            kwargs = dict(
                model=attempt_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                timeout=timeout,
            )
            if top_p is not None:
                kwargs["top_p"] = top_p
            stream = await attempt_client.chat.completions.create(**kwargs)
            usage = None
            async for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
            elapsed_ms = int((time.perf_counter() - _start) * 1000)
            if usage:
                _log_llm_usage(
                    request_id=get_request_id(),
                    model=attempt_model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    stream=True,
                    elapsed_ms=elapsed_ms,
                )
                # P5-12: Capture usage info for caller
                if usage_container is not None:
                    usage_container.append({
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                    })
            return  # Success — exit generator
        except (httpx.HTTPError, httpx.TimeoutException, asyncio.TimeoutError) as e:
            last_error = e
            if attempt_model == model_name:
                logger.warning(
                    "LLM stream call failed with primary model=%s, retrying with fallback=%s: %s",
                    model_name, settings.llm_fallback_model, str(e),
                )
                continue
            logger.error(
                "LLM stream call failed with fallback model=%s: %s",
                attempt_model, str(e),
            )
    # All attempts exhausted
    raise last_error or RuntimeError("LLM stream call failed: all attempts exhausted")


async def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: httpx.Timeout | None = None,
    response_format: dict | None = None,
    top_p: float | None = None,
    usage_container: list | None = None,  # P5-12
) -> str:
    """非流式对话 —— 用于概念提取等不需要流式输出的场景。
    P2-12: 主模型失败时自动用 fallback_model 重试 1 次。
    P5-12: usage_container 为一个列表，调用后填充 usage 信息。"""
    if timeout is None:
        timeout = httpx.Timeout(settings.llm_timeout_connect, read=settings.llm_timeout_read)
    model_name = model or settings.llm_model
    client = get_client()

    attempts = [model_name]
    if model is None and settings.llm_fallback_model:
        attempts.append(settings.llm_fallback_model)

    last_error = None
    for attempt_model in attempts:
        try:
            _start = time.perf_counter()
            kwargs = dict(
                model=attempt_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if response_format is not None:
                kwargs["response_format"] = response_format
            if top_p is not None:
                kwargs["top_p"] = top_p
            response = await client.chat.completions.create(**kwargs)
            elapsed_ms = int((time.perf_counter() - _start) * 1000)
            usage = response.usage
            if usage:
                _log_llm_usage(
                    request_id=get_request_id(),
                    model=attempt_model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    stream=False,
                    elapsed_ms=elapsed_ms,
                )
                if usage_container is not None:
                    usage_container.append({
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                    })
            logger.debug("LLM chat usage: prompt_tokens=%s, completion_tokens=%s, elapsed_ms=%s",
                         usage.prompt_tokens, usage.completion_tokens, elapsed_ms)
            return response.choices[0].message.content or ""
        except (httpx.HTTPError, httpx.TimeoutException, asyncio.TimeoutError) as e:
            last_error = e
            if attempt_model == model_name:
                logger.warning(
                    "LLM chat call failed with primary model=%s, retrying with fallback=%s: %s",
                    model_name, settings.llm_fallback_model, str(e),
                )
                continue
            logger.error(
                "LLM chat call failed with fallback model=%s: %s",
                attempt_model, str(e),
            )
    raise last_error or RuntimeError("LLM chat call failed: all attempts exhausted")


def count_tokens(text: str) -> int:
    """P5-11: 估算 token 数 —— 使用 tiktoken cl100k_base，失败时降级到启发式。"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Fallback heuristic
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.8 + other_chars * 0.3)
