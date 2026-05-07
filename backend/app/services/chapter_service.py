"""
章节服务 —— 高层的章节文本读取、Wiki 清单构建。
P5-1: 从 reading.py 提取。
"""
import logging
from app.utils.chapter_utils import get_chapter_markers, get_chapter_text as _get_chapter_text_util

logger = logging.getLogger("xiugua.chapter_service")


def get_chapter_text(book, chapter: int) -> str:
    """获取指定书籍指定章节的原文文本。"""
    if not book.text_path:
        return ""
    try:
        return _get_chapter_text_util(
            book.text_path, chapter, book.chapter_count or 1,
            get_chapter_markers(book),
        )
    except FileNotFoundError:
        return ""


def build_wiki_checklist(book, chapter: int, progress) -> list:
    """从预处理数据构建 Wiki 清单（左侧引导栏用）。"""
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


def get_chapter_wikis(book, chapter: int) -> dict:
    """获取章节原始 Wiki 数据（CHAPTER_END 内联响应用）。"""
    wikis = []
    if book.preprocess_progress:
        ch_wikis = book.preprocess_progress.get("chapter_wikis", {}).get(str(chapter), {})
        for w in ch_wikis.get("wikis", []):
            wikis.append({
                "name": w.get("name", ""),
                "content": w.get("content", w.get("description", "")),
                "type": w.get("type", "concept"),
                "quotes": w.get("quotes", []),
            })
    return {"wikis": wikis}


def extract_theses(node) -> list:
    """递归从论辩树节点提取论点陈述。"""
    items = []
    if isinstance(node, dict):
        if node.get("thesis"):
            items.append(node["thesis"])
        for b in node.get("branches", []):
            items.extend(extract_theses(b))
    return items
