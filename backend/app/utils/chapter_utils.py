"""
章节文本工具 —— 从原始文本中提取指定章节内容。
提供字节偏移缓存优化大文件的重复读取。

P5-3: 从 reading.py 提取到工具模块。
"""
import json
import re as _re
import logging

logger = logging.getLogger("xiugua.chapter_utils")

# P2-17: Chapter offset cache for large file memory optimization
_chapter_offset_cache: dict[str, list[tuple[int, int]]] = {}


def get_chapter_markers(book) -> list | None:
    """从 book.category (P1 JSON) 提取 keep 章节标题列表"""
    try:
        if book.category:
            data = json.loads(book.category)
            keep = data.get("keep_chapters", [])
            if keep:
                # Clean: remove snippet text after " | "
                return [c.split(" | ")[0].strip() for c in keep if c.strip()]
            vc = data.get("validated_chapters", [])
            if vc:
                return [c["regex_title"] for c in vc if c.get("action") == "keep"]
    except (json.JSONDecodeError, TypeError):
        logger.warning("get_chapter_markers: failed to parse book.category JSON")
    return None


def extract_chapter_text(full_text: str, chapter: int, total_chapters: int,
                          markers: list | None = None) -> str:
    """
    提取指定章节文本。
    优先用 P1 验证过的 keep 章节名按位置切分；fallback 到正则。
    """
    pattern = r"(第[一二三四五六七八九十百千\d]+章|Chapter\s+\d+|CHAPTER\s+\d+)"

    # Strategy 1: P1-validated keepers with regex positions
    if markers:
        regex_matches = [(m.group(0), m.start()) for m in _re.finditer(pattern, full_text)]
        keeper_titles = set(m.strip().upper().replace(' ', '') for m in markers)
        keeper_positions = [(title, pos) for title, pos in regex_matches
                           if title.strip().upper().replace(' ', '') in keeper_titles]
        seen = set()
        unique_positions = []
        for title, pos in keeper_positions:
            norm = title.strip().upper().replace(' ', '')
            if norm not in seen:
                seen.add(norm)
                unique_positions.append((title, pos))
        unique_positions.sort(key=lambda x: x[1])

        if chapter <= len(unique_positions):
            _, start_pos = unique_positions[chapter - 1]
            if chapter < len(unique_positions):
                _, end_pos = unique_positions[chapter]
                return full_text[start_pos:end_pos]
            return full_text[start_pos:]

    # Strategy 2: Regex split + dedup
    parts = _re.split(pattern, full_text)
    if len(parts) > 2:
        chapter_map = {}
        chapter_order = []
        i = 1
        while i < len(parts):
            title = parts[i]
            content = parts[i + 1] if i + 1 < len(parts) else ""
            if title in chapter_map:
                chapter_map[title] += "\n\n" + content
            else:
                chapter_map[title] = content
                chapter_order.append(title)
            i += 2
        chapters = [title + chapter_map[title] for title in chapter_order]
        if chapter <= len(chapters):
            return chapters[chapter - 1]

    # Strategy 3: Even split
    chunk_size = len(full_text) // max(total_chapters, 1)
    start = (chapter - 1) * chunk_size
    end = start + chunk_size if chapter < total_chapters else len(full_text)
    return full_text[start:end]


def get_chapter_text(text_path: str, chapter: int, total_chapters: int,
                     markers: list | None = None) -> str:
    """Get chapter text using cached byte offset indices.

    First call reads the full file to compute and cache chapter boundary byte offsets.
    Subsequent calls use seek+read in binary mode for exact chapter range,
    avoiding full-file reads and regex splits.

    Falls back to full read + extract_chapter_text on cache miss or error.
    """
    if text_path not in _chapter_offset_cache:
        _build_chapter_offset_cache(text_path, markers, total_chapters)

    offsets = _chapter_offset_cache.get(text_path)
    if offsets and 1 <= chapter <= len(offsets):
        try:
            start_byte, end_byte = offsets[chapter - 1]
            with open(text_path, "rb") as f:
                f.seek(start_byte)
                chunk = f.read(end_byte - start_byte)
            return chunk.decode("utf-8")
        except Exception as exc:
            logger.warning(
                "get_chapter_text seek failed for %s ch%d: %s",
                text_path, chapter, exc,
            )

    # Fallback: full file read
    with open(text_path, "r", encoding="utf-8") as f:
        return extract_chapter_text(f.read(), chapter, total_chapters, markers)


def _build_chapter_offset_cache(text_path: str, markers: list | None, total_chapters: int):
    """Build byte-offset cache for chapter boundaries."""
    pattern = r"(第[一二三四五六七八九十百千\d]+章|Chapter\s+\d+|CHAPTER\s+\d+)"

    with open(text_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    char_offsets = _compute_char_offsets(full_text, markers, total_chapters, pattern)

    # Convert character positions to byte positions (UTF-8 safe)
    byte_offsets = []
    for start_char, end_char in char_offsets:
        start_byte = len(full_text[:start_char].encode("utf-8"))
        if end_char is not None:
            end_byte = len(full_text[:end_char].encode("utf-8"))
        else:
            end_byte = len(full_text.encode("utf-8"))
        byte_offsets.append((start_byte, end_byte))

    _chapter_offset_cache[text_path] = byte_offsets
    # Evict oldest entry if cache grows too large
    if len(_chapter_offset_cache) > 500:
        _chapter_offset_cache.pop(next(iter(_chapter_offset_cache)))
    logger.info(
        "Cache built for %s: %d chapters, %d total cached",
        text_path, len(byte_offsets), len(_chapter_offset_cache),
    )


def _compute_char_offsets(full_text: str, markers: list | None, total_chapters: int,
                          pattern: str) -> list[tuple[int, int | None]]:
    """Compute chapter boundaries as character-position offsets.
    Returns [(start_char, end_char), ...]; end_char is None for the last chapter.
    """
    # Strategy 1: P1-validated keepers
    if markers:
        regex_matches = [(m.group(0), m.start()) for m in _re.finditer(pattern, full_text)]
        keeper_titles = set(m.strip().upper().replace(" ", "") for m in markers)
        keeper_positions = sorted([
            pos for title, pos in regex_matches
            if title.strip().upper().replace(" ", "") in keeper_titles
        ])
        if keeper_positions:
            result = []
            for i, pos in enumerate(keeper_positions):
                end = keeper_positions[i + 1] if i + 1 < len(keeper_positions) else None
                result.append((pos, end))
            return result

    # Strategy 2: Regex split + dedup
    parts = _re.split(pattern, full_text)
    if len(parts) > 2:
        chapter_map = {}
        chapter_order = []
        i = 1
        while i < len(parts):
            title = parts[i]
            content = parts[i + 1] if i + 1 < len(parts) else ""
            if title in chapter_map:
                chapter_map[title] += "\n\n" + content
            else:
                chapter_map[title] = content
                chapter_order.append(title)
            i += 2

        offsets = []
        current_pos = 0
        for title in chapter_order:
            idx = full_text.find(title, current_pos)
            if idx >= 0:
                offsets.append(idx)
                current_pos = idx + 1
        offsets.sort()
        if offsets:
            result = []
            for i, pos in enumerate(offsets):
                end = offsets[i + 1] if i + 1 < len(offsets) else None
                result.append((pos, end))
            return result

    # Strategy 3: Even split (by character count)
    chunk_size = len(full_text) // max(total_chapters, 1)
    result = []
    for i in range(total_chapters):
        start = i * chunk_size
        end = (i + 1) * chunk_size if i < total_chapters - 1 else len(full_text)
        result.append((start, end))
    return result
