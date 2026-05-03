"""
文档解析服务 —— PaddleOCR + PyMuPDF + ebooklib。
输入：上传文件；输出：统一 Markdown 文本。
⚠️ 预留切换口：vision_model / ocr_engine 可通过配置切换
"""
import os
import uuid
from pathlib import Path
from app.config import settings


async def parse_document(file_path: str, original_filename: str) -> dict:
    """
    解析上传文件 → 输出 Markdown。
    返回: {"text": "...", "token_count": N, "chapter_count": N, "warnings": [...]}
    """
    ext = Path(original_filename).suffix.lower()
    warnings = []

    toc = []
    match ext:
        case ".epub":
            text, w, toc = _parse_epub(file_path)
        case ".pdf":
            text, w, toc = _parse_pdf(file_path)
        case ".txt":
            text, w, toc = _parse_txt(file_path)
        case _:
            raise ValueError(f"不支持的文件格式: {ext}")

    warnings.extend(w)
    from app.services.llm_service import count_tokens

    return {
        "text": text,
        "token_count": count_tokens(text),
        "chapter_count": _count_chapters(text, toc),
        "warnings": warnings,
    }


def _parse_epub(file_path: str) -> tuple[str, list[str]]:
    """电子书：ebooklib 提取 HTML + TOC → 纯文本 → Markdown"""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    warnings = []
    book = epub.read_epub(file_path)

    # 提取 TOC 获取真实章节数
    toc_chapters = []
    for item in book.toc:
        if isinstance(item, tuple):
            title = item[0].title if hasattr(item[0], 'title') else str(item[0])
            toc_chapters.append(title)
        elif hasattr(item, 'title'):
            toc_chapters.append(item.title)

    chapters = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator="\n")
        if text.strip():
            chapters.append(text.strip())

    if not chapters:
        raise ValueError("解析 ePub 失败：未找到文本内容")

    # 拼接文本：用 TOC 标题作为章节分隔符
    text = "\n\n---\n\n".join(chapters)
    return text, warnings, toc_chapters


def _parse_pdf(file_path: str) -> tuple[str, list[str]]:
    """PDF 解析。先 PyMuPDF 提取文字层；扫描版走 PaddleOCR。"""
    import fitz
    warnings = []
    doc = fitz.open(file_path)
    pages_text = []
    total_chars = 0

    for page in doc:
        text = page.get_text()
        pages_text.append(text)
        total_chars += len(text.strip())
    doc.close()

    if total_chars < 100:
        warnings.append("检测到扫描版 PDF，启用 PaddleOCR 识别")
        return _parse_pdf_with_ocr(file_path), warnings, []

    return "\n\n".join(pages_text), warnings, []


def _parse_pdf(file_path: str) -> tuple[str, list[str]]:
    """
    PDF 解析。
    先用 PyMuPDF 尝试提取文字层；如果文字层几乎为空（扫描版），
    则走 PaddleOCR 流水线。
    """
    import fitz  # PyMuPDF
    warnings = []
    doc = fitz.open(file_path)
    pages_text = []
    total_chars = 0

    for page in doc:
        text = page.get_text()
        pages_text.append(text)
        total_chars += len(text.strip())

    doc.close()

    if total_chars < 100:  # 扫描版 PDF，几乎没有文字层
        warnings.append("检测到扫描版 PDF，启用 PaddleOCR 识别")
        return _parse_pdf_with_ocr(file_path), warnings

    return "\n\n".join(pages_text), warnings


def _parse_pdf_with_ocr(file_path: str) -> str:
    """
    PaddleOCR 版分析 + OCR。
    PP-StructureV3: 自动检测栏位、表格、公式、插图。
    ⚠️ 预留切换口：ocr_engine != "paddleocr" 时走备选方案
    """
    if settings.ocr_engine != "paddleocr":
        raise NotImplementedError(f"OCR 引擎 {settings.ocr_engine} 尚未集成")
    try:
        from paddleocr import PPStructureV3
        engine = PPStructureV3()
        result = engine(file_path)
        return _structure_result_to_markdown(result)
    except ImportError:
        raise ImportError("PaddleOCR 未安装。请运行: pip install paddleocr")


def _structure_result_to_markdown(result: list) -> str:
    """PaddleOCR 结构 → 统一 Markdown"""
    lines = []
    for item in result:
        item_type = item.get("type", "")
        if item_type == "text":
            lines.append(item.get("res", ""))
        elif item_type == "table":
            lines.append(item.get("res", ""))  # PP-Structure 直接输出 Markdown 表格
        elif item_type == "figure":
            caption = item.get("img_caption", "")
            lines.append(f"> [图] {caption}" if caption else "> [图]")
        elif item_type == "formula":
            lines.append(f"$${item.get('res', '')}$$")
        else:
            lines.append(item.get("res", ""))
    return "\n\n".join(lines)


def _parse_txt(file_path: str) -> tuple[str, list[str], list[str]]:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    return text, [], []


def _count_chapters(text: str, toc: list[str] = None) -> int:
    """
    统计章节数：三层 fallback
    1. TOC（最准）
    2. 标题模式匹配
    3. 均分（兜底——后续导读中 AI 会修正）
    """
    # Layer 1: TOC
    if toc and len(toc) > 0:
        return len(toc)

    # Layer 2: 标题模式
    import re
    patterns = [
        r"第[一二三四五六七八九十百千\d]+章",
        r"Chapter\s+\d+",
        r"CHAPTER\s+\d+",
        r"PART\s+[IVX\d]+",
        r"第[一二三四五六七八九十百千\d]+节",
    ]
    count = 0
    for p in patterns:
        count += len(re.findall(p, text))

    # 如果标题数在合理范围内（2-200），使用标题数
    if 2 <= count <= 200:
        return count

    # Layer 3: 均分（按 5000 字/章估算）
    return max(len(text) // 5000, 1)


async def save_parsed_text(text: str, book_id: str) -> str:
    """保存解析后文本到文件系统"""
    dir_path = Path(settings.book_storage_path) / str(book_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / "content.md"
    file_path.write_text(text, encoding="utf-8")
    return str(file_path.resolve())
