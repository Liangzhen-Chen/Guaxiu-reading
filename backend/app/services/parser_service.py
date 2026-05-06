"""
文档解析服务 —— PaddleOCR + PyMuPDF + ebooklib。
输入：上传文件；输出：统一 Markdown 文本。
⚠️ 预留切换口：vision_model / ocr_engine 可通过配置切换
"""
import os
import uuid
from pathlib import Path
from app.config import settings


def parse_document(file_path: str, original_filename: str) -> dict:
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


def _parse_pdf(file_path: str) -> tuple[str, list[str], list[str]]:
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
        result = engine.predict(file_path)
        return _structure_result_to_markdown(result)
    except ImportError:
        raise ImportError("PaddleOCR 未安装。请运行: pip install paddleocr")


def _structure_result_to_markdown(result: list) -> str:
    """PaddleOCR predict 结果 → 统一 Markdown"""
    lines = []
    for page in result:
        # parsing_res_list 是主要的解析结果
        for item in page.get("parsing_res_list", []):
            label = item.get("label", "")
            content = item.get("content", "")
            if label == "text":
                lines.append(content)
            elif label == "table":
                lines.append(content)
            elif label == "image":
                lines.append("> [图]")
            elif label == "formula":
                lines.append(f"$${content}$$" if content else "")
            else:
                if content:
                    lines.append(content)
        # 单独的表格/公式结果
        for t in page.get("table_res_list", []):
            if isinstance(t, dict) and t.get("content"):
                lines.append(t["content"])
        for f in page.get("formula_res_list", []):
            if isinstance(f, dict) and f.get("content"):
                lines.append(f"$${f['content']}$$")
    return "\n\n".join(lines)


def _parse_txt(file_path: str) -> tuple[str, list[str], list[str]]:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    return text, [], []


def _count_chapters(text: str, toc: list[str] = None) -> int:
    """
    统计章节数：三层 fallback
    1. TOC（过滤前言/目录/版权等非章条目）
    2. 标题模式匹配（仅 Chapter/第X章，不含 Part/Section）
    3. 均分（兜底——后续导读中 AI 会修正）
    """
    _non_chapter = {'目录', '扉页', '版权', '前言', '序', '译者序', '推荐序', '自序',
                    '参考文献', '附录', '索引', '后记', '致谢', '导读',
                    'Contents', 'Copyright', 'Preface', 'Index', 'Appendix',
                    'References', 'Acknowledgments', 'Introduction'}

    # Layer 1: TOC
    if toc and len(toc) > 0:
        filtered = [t for t in toc if t.strip() not in _non_chapter]
        if len(filtered) >= 2:
            return len(filtered)
        # If filtering removed too much, use original
        if len(toc) >= 2:
            return len(toc)

    # Layer 2: 标题模式（仅 Chapter，不含 Part/Section）
    import re
    chapter_patterns = [
        r"第[一二三四五六七八九十百千\d]+章",
        r"Chapter\s+\d+",
        r"CHAPTER\s+\d+",
    ]
    count = 0
    for p in chapter_patterns:
        matches = re.findall(p, text)
        # Deduplicate by normalized form
        unique = set(m.strip().upper().replace(' ', '') for m in matches)
        count += len(unique)

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
