"""
朽瓜（Xiugua）后端配置
所有配置通过环境变量读取，不硬编码密钥。
⚠️ 模型切换口：LLM_MODEL / VISION_MODEL 通过 .env 切换
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # ── 数据库 ──
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/xiugua"

    # ── JWT ──
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 43200  # 30 天

    # ── DeepSeek / LLM ──
    # ⚠️ 预留切换口：改为 deepseek-v4-pro / qwen-max 等待 OpenAI 兼容模型的 model_id 即可
    deepseek_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    llm_fallback_model: str = "deepseek-v4-pro"
    llm_base_url: str = "https://api.deepseek.com"

    # ── 视觉模型 ──
    # ⚠️ 预留切换口：默认 PaddleOCR 内置 VLM，可切换为 qwen-vl-plus 等
    vision_model: str = "paddleocr-vl-1.5"
    vision_fallback_model: str = ""

    # ── OCR ──
    # ⚠️ 预留切换口：默认 PaddleOCR，可切换为 baidu-ocr-api
    ocr_engine: str = "paddleocr"

    # ── 上下文管理 ──
    context_max_tokens: int = 900_000       # 触发压缩阈值
    context_window_rounds: int = 20         # 保留最近 N 轮完整对话

    # ── 文件存储 ──
    # ⚠️ 预留切换口：默认本地文件系统，可切换为 S3 / OSS 路径
    book_storage_path: str = str(BASE_DIR / "data" / "books")
    max_upload_size_mb: int = 50

    # ── Google Books API ──
    google_books_api_key: str = ""

    # ── 微信小程序 ──
    wechat_app_id: str = ""
    wechat_app_secret: str = ""

    # ── Cobrand ──
    app_name: str = "朽瓜"
    app_version: str = "0.1.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# 确保存储目录存在
Path(settings.book_storage_path).mkdir(parents=True, exist_ok=True)
