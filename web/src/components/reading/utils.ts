/**
 * Shared utilities for reading page components.
 * Extracted from the monolithic read/[book_id]/page.tsx for reuse.
 */

import DOMPurify from "dompurify";

export function T() {
  return typeof window !== "undefined" ? localStorage.getItem("token") || "" : "";
}

/** Render Markdown-like syntax to HTML (XSS-safe via prior escaping) */
export function renderMD(text: string) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#x27;");
  const html = escaped
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-3 mb-1">$1</h2>')
    .replace(/`([^`]+)`/g, '<code class="bg-ink-bg px-1 rounded text-sm">$1</code>')
    .replace(/\[\[([^\]]+)\]\]/g, '<span class="inline-block bg-amber-100 text-amber-800 text-xs px-1.5 py-0.5 rounded">$1</span>')
    .replace(/^---$/gm, '<hr class="my-2 border-border"/>')
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-2 border-border pl-3 text-ink-soft">$1</blockquote>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal">$2</li>');
  return html.split('\n').map(line => {
    const trimmed = line.trim();
    if (trimmed === '') return '<br/>';
    if (/^<(h[23]|li|blockquote|hr|p|div|ul|ol|table|pre)/.test(trimmed)) return line;
    return line + '<br/>';
  }).join('\n');
}

/** Sanitize rendered Markdown for dangerouslySetInnerHTML */
export function sanitizedMD(text: string): { __html: string } {
  return { __html: DOMPurify.sanitize(renderMD(text)) };
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
