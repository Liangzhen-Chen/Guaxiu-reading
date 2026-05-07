"""
预处理服务 —— 后台文档解析和逐章 Wiki 生成。
P5-2: 从 books.py 提取 _parse_in_background、_preprocess_book。

包括：
- P1 书籍解析（含 one_liner + 章节验证）
- P2 逐章 Wiki 生成（P5-6: asyncio.gather + Semaphore 并发）
- fallback Wiki 生成
"""
import json as _json
import asyncio
import logging
from sqlalchemy import select, update
from app.database import async_session
from app.models.book import Book
from app.services.parser_service import parse_document, save_parsed_text
from app.services.socratic_service import _p, detect_language
from app.services.llm_service import chat
from app.services.json_validator import extract_json
from app.utils.chapter_utils import extract_chapter_text, get_chapter_markers

logger = logging.getLogger("xiugua.preprocess")


async def parse_in_background(book_id: str, raw_path: str, filename: str, title: str):
    """后台解析文档 + 生成章节框架。CPU 密集部分在线程池运行，不阻塞事件循环。"""
    import re as _re

    # Step 1: CPU-heavy parsing in thread pool
    async def _do_parse():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _parse_sync, raw_path, filename)

    try:
        result = await _do_parse()
    except Exception as e:
        async with async_session() as db:
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    parse_status="failed",
                    parse_error=f"文档解析失败: {str(e)[:400]}",
                )
            )
            await db.commit()
        return

    # Step 2: DB operations in main event loop
    async with async_session() as db:
        try:
            text_path = await save_parsed_text(result["text"], book_id)

            parse_error_val = None
            category = None
            one_liner_val = None
            final_chapter_count = result["chapter_count"]

            # P1: Generate one_liner + chapter validation
            p1_ok = False
            try:
                _pattern = r"(Part\s+[IVXLCDM]+|第[一二三四五六七八九十百千\d]+章|Chapter\s+\d+|CHAPTER\s+\d+)"
                _parts = _re.split(_pattern, result["text"])
                _seen = set()
                regex_chapters = []
                i = 1
                while i < len(_parts):
                    title_str = _parts[i].strip()
                    norm = _re.sub(r'\s+', ' ', title_str).upper()
                    if norm not in _seen:
                        _seen.add(norm)
                        snippet = (_parts[i + 1] if i + 1 < len(_parts) else "")[:60].strip().replace('\n', ' ')
                        regex_chapters.append(f"  {title_str} | {snippet}")
                    i += 2
                regex_list = "\n".join(regex_chapters) if regex_chapters else "（未检测到章标题）"

                full_text = result["text"]
                text_sample = full_text[500:40000]
                if len(full_text) > 50000:
                    mid = len(full_text) // 2
                    text_sample += "\n...(书中段)...\n" + full_text[mid:mid+10000]

                book_language = detect_language(full_text)
                p1_prompt = _p("p1_parse", book_language).replace("{regex_chapters}", regex_list)
                p1_data = None
                for p1_attempt in range(3):
                    raw = await chat(
                        [{"role": "system", "content": p1_prompt},
                         {"role": "user", "content": text_sample}],
                        temperature=0.3 + p1_attempt * 0.15, max_tokens=8192,
                        response_format={"type": "json_object"},
                    )
                    try:
                        p1_data = extract_json(raw)
                        if p1_data.get("keep_chapters") or p1_data.get("validated_chapters"):
                            break
                    except ValueError:
                        continue
                if p1_data:
                    one_liner_val = p1_data.get("one_liner", "")
                    category = _json.dumps(p1_data, ensure_ascii=False)
                    await db.execute(
                        update(Book).where(Book.id == book_id).values(language=book_language)
                    )
                    keep_chapters = p1_data.get("keep_chapters", [])
                    if not keep_chapters:
                        vc = p1_data.get("validated_chapters", [])
                        keep_chapters = [c["regex_title"] for c in vc if c.get("action") == "keep"]
                    keep_chapters = [c.split(" | ")[0].strip() for c in keep_chapters if c.strip()]
                    if keep_chapters:
                        final_chapter_count = len(keep_chapters)
                        p1_ok = True
            except Exception as e:
                logger.warning("P1 failed: %s", e)

            # Fallback: old Prompt A framework (only if P1 failed)
            if not p1_ok:
                try:
                    from app.services.socratic_service import generate_chapter_structure
                    ch1_text = result["text"][:10000]
                    framework = await generate_chapter_structure(
                        book_title=title, chapter_index=1,
                        chapter_text=ch1_text, mode="quick", language="zh",
                    )
                    if isinstance(framework, dict) and "error" not in framework:
                        category = _json.dumps(framework, ensure_ascii=False)
                except Exception as fe:
                    parse_error_val = f"framework: {str(fe)[:200]}"

            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    text_path=text_path,
                    token_count=result["token_count"],
                    chapter_count=final_chapter_count,
                    category=category,
                    one_liner=one_liner_val,
                    parse_status="done",
                    parse_error=parse_error_val,
                )
            )
            await db.commit()
        except Exception as e:
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    parse_status="failed",
                    parse_error=str(e)[:500],
                )
            )
            await db.commit()


async def preprocess_book(book_id: str, title: str, text_path: str, total_chapters: int):
    """P5-2: 后台逐章调用 P2 生成 Wiki。P5-6: asyncio.gather + Semaphore(3) 并发。"""
    async with async_session() as db:
        try:
            from sqlalchemy import select as _select
            book_obj = (await db.execute(
                _select(Book).where(Book.id == book_id)
            )).scalar_one_or_none()
            markers = get_chapter_markers(book_obj) if book_obj else None
            p2_language = book_obj.language if book_obj else "zh"

            with open(text_path, "r", encoding="utf-8") as f:
                full_text = f.read()

            # P5-6: Build concurrent chapter tasks
            chapter_tasks = []
            for ch in range(1, total_chapters + 1):
                ch_text = extract_chapter_text(full_text, ch, total_chapters, markers)
                if not ch_text.strip():
                    continue
                chapter_tasks.append((ch, ch_text))

            prompt_template = _p("p2_wikis", p2_language)
            sem = asyncio.Semaphore(3)
            chapter_wikis: dict[str, dict] = {}
            progress = {"total_chapters": total_chapters, "completed_chapters": 0, "chapter_wikis": {}}

            async def process_one_chapter(ch: int, ch_text: str) -> tuple[int, dict | None]:
                async with sem:
                    prompt = prompt_template.replace("{book_title}", title)
                    prompt = prompt.replace("{chapter_index}", str(ch))

                    wiki_data = None
                    for attempt in range(3):
                        raw = await chat(
                            [{"role": "system", "content": prompt},
                             {"role": "user", "content": ch_text[:30000]}],
                            temperature=0.3 + attempt * 0.15, max_tokens=4096,
                            response_format={"type": "json_object"},
                        )
                        try:
                            wiki_data = extract_json(raw)
                            wikis = wiki_data.get("wikis", [])
                            if not wikis:
                                prompt = (
                                    prompt
                                    + "\n\n⚠️ 上一轮你返回了空的 wikis 数组。必须基于本章文本提取至少 3 个概念。"
                                )
                                continue
                            break
                        except ValueError:
                            continue

                    if not wiki_data:
                        logger.warning("Chapter %d wiki gen failed after 3 attempts, using fallback", ch)
                        return ch, {
                            "chapter_index": ch,
                            "chapter_title": f"第{ch}章",
                            "chapter_summary": ch_text[:500],
                            "wikis": _fallback_wikis(ch_text),
                        }
                    return ch, wiki_data

            results = await asyncio.gather(
                *[process_one_chapter(ch, ct) for ch, ct in chapter_tasks],
                return_exceptions=True,
            )

            for r in results:
                if isinstance(r, Exception):
                    logger.error("P5-6 chapter task failed: %s", r)
                    continue
                ch, wiki_data = r
                if wiki_data:
                    chapter_wikis[str(ch)] = wiki_data
                    progress["completed_chapters"] = ch
                    pp_data = {**progress, "chapter_wikis": chapter_wikis, "ready_to_read": ch >= 2}
                    await db.execute(
                        update(Book).where(Book.id == book_id).values(
                            preprocess_status="ready" if ch >= 2 else "processing",
                            preprocess_progress=pp_data,
                        )
                    )
                    await db.commit()

            # All chapters done
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    preprocess_status="ready",
                    preprocess_progress={**progress, "chapter_wikis": chapter_wikis},
                )
            )
            await db.commit()
        except Exception as e:
            logger.error("Preprocess failed for book %s: %s", book_id, e)
            await db.execute(
                update(Book).where(Book.id == book_id).values(
                    preprocess_status="failed",
                )
            )
            await db.commit()


def _parse_sync(raw_path: str, filename: str) -> dict:
    """同步解析文档，在线程池中运行"""
    return parse_document(raw_path, filename)


def _fallback_wikis(text: str, min_concepts: int = 3) -> list[dict]:
    """当 LLM 失败时，从文本中提取基本 Wiki 概念。"""
    import re as _re
    lines = text.strip().split('\n')
    candidates: list[tuple[str, str]] = []

    for line in lines:
        line = line.strip()
        if len(line) < 10:
            continue
        for pat in [r'^(.+?)是', r'^(.+?)指', r'^(.+?)—', r'^(.+?)：',
                     r'^(.+?) is ', r'^(.+?) refers to']:
            m = _re.search(pat, line)
            if m:
                term = m.group(1).strip()
                if 2 <= len(term) <= 40 and term not in [c[0] for c in candidates]:
                    candidates.append((term, line[:200]))
                    break

    if len(candidates) < min_concepts:
        for line in lines[:100]:
            line = line.strip()
            if len(line) > 30 and len(line) < 300 and line not in [c[0] for c in candidates]:
                phrase = line.split('。')[0].split('.')[0].strip()
                if len(phrase) > 4:
                    candidates.append((phrase[:40], line[:200]))
                if len(candidates) >= min_concepts:
                    break

    wikis = []
    for i, (name, context) in enumerate(candidates[:max(min_concepts, 5)]):
        wikis.append({
            "id": f"fb_{i+1}",
            "name": name,
            "content": context,
            "type": "concept",
            "quotes": [{"text": context, "context": "自动提取自原文"}],
        })
    return wikis or [{
        "id": "fb_1", "name": "本章导览",
        "content": text[:500], "type": "concept", "quotes": [],
    }]
