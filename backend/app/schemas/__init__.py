"""Pydantic 数据模型 —— 请求/响应校验"""
from app.schemas.user import UserCreate, UserResponse, TokenResponse, WechatLoginRequest
from app.schemas.book import BookResponse, BookListResponse, BookCreate
from app.schemas.conversation import ConversationMessage, ConversationResponse
from app.schemas.wiki import WikiEntryResponse, WikiEntryCreate, WikiEntryUpdate
from app.schemas.reading import (
    ModeSelection, AssessmentRequest, ReadingRequest,
    ReadingResponse, ProgressResponse
)
