/**
 * Shared utilities for reading page components.
 * Extracted from the monolithic read/[book_id]/page.tsx for reuse.
 */

import DOMPurify from "dompurify";

export function T() {
  return typeof window !== "undefined" ? localStorage.getItem("token") || "" : "";
}

/** Strip V4_META and CHAPTER_END markers from AI response */
export function stripMeta(text: string): string {
  return text
    .replace(/<!--V4_META:[\s\S]*?-->/g, '')
    .replace(/<!--CHAPTER_END[^>]*-->/g, '')
    .trim();
}

/** Render Markdown-like syntax to HTML (XSS-safe via prior escaping).
 *  Uses paragraph-aware rendering: consecutive text lines form <p> blocks,
 *  empty lines separate paragraphs. */
export function renderMD(text: string) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");

  // Inline formatting
  let html = escaped
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="bg-ink-bg px-1 rounded text-sm">$1</code>')
    .replace(/\[\[([^\]]+)\]\]/g, '<span class="inline-block bg-amber-100 text-amber-800 text-xs px-1.5 py-0.5 rounded">$1</span>');

  // Block-level: accumulate lines into paragraphs, preserve special blocks
  const lines = html.split('\n');
  const result: string[] = [];
  let para: string[] = [];

  function flushPara() {
    if (para.length > 0) {
      result.push('<p>' + para.join('<br/>') + '</p>');
      para = [];
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();

    // Empty line: flush current paragraph
    if (trimmed === '') {
      flushPara();
      continue;
    }

    // Special block-level lines (headings, lists, quotes, hr)
    if (/^### (.+)$/.test(trimmed)) {
      flushPara();
      result.push(trimmed.replace(/^### (.+)$/, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>'));
      continue;
    }
    if (/^## (.+)$/.test(trimmed)) {
      flushPara();
      result.push(trimmed.replace(/^## (.+)$/, '<h2 class="text-lg font-semibold mt-3 mb-1">$1</h2>'));
      continue;
    }
    if (/^---$/.test(trimmed)) {
      flushPara();
      result.push('<hr class="my-2 border-border"/>');
      continue;
    }
    if (/^> (.+)$/.test(trimmed)) {
      flushPara();
      result.push(trimmed.replace(/^> (.+)$/, '<blockquote class="border-l-2 border-border pl-3 text-ink-soft">$1</blockquote>'));
      continue;
    }
    if (/^- (.+)$/.test(trimmed)) {
      flushPara();
      result.push(trimmed.replace(/^- (.+)$/, '<li class="ml-4 list-disc">$1</li>'));
      continue;
    }
    if (/^\d+\. (.+)$/.test(trimmed)) {
      flushPara();
      result.push(trimmed.replace(/^\d+\. (.+)$/, '<li class="ml-4 list-decimal">$1</li>'));
      continue;
    }

    // Normal text line: accumulate into paragraph
    para.push(trimmed);
  }
  flushPara();
  return result.join('\n');
}

/** Sanitize + strip meta + render Markdown */
export function sanitizedMD(text: string): { __html: string } {
  return { __html: DOMPurify.sanitize(renderMD(stripMeta(text))) };
}

/** Type for chat message */
export interface ChatMessage {
  role: string;
  content: string;
}

/** Type for wiki checklist item */
export interface WikiItem {
  id: string;
  name: string;
  status: "pending" | "active" | "done";
}

/** Type for wiki selection (chapter-end data) */
export interface WikiSelection {
  wikis?: { name: string; content: string; type: string; quotes?: string[] }[];
  concepts?: { name: string; definition: string }[];
}
