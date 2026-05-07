"use client";
import { memo, useMemo, useRef } from "react";
import type { Lang } from "@/app/lang";
import type { ChatMessage, WikiItem } from "./utils";
import { sanitizedMD } from "./utils";

/* ── P5-14: Individual message component wrapped in React.memo ── */
interface MsgBubbleProps {
  msg: ChatMessage;
  showFeedback: boolean;
  rated: "up" | "down" | undefined;
  onRate: (ok: boolean) => void;
}

const MsgBubble = memo(function MsgBubble({ msg, showFeedback, rated, onRate }: MsgBubbleProps) {
  const sanitized = useMemo(() => sanitizedMD(msg.content), [msg.content]);
  return (
    <div className="flex flex-col gap-1">
      <div className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
        <div
          className={`max-w-[85%] rounded-2xl px-4 py-3 text-base leading-relaxed ${
            msg.role === "user"
              ? "bg-ink text-white"
              : "bg-ink-bg border border-border-light"
          }`}
        >
          {msg.role === "assistant" ? (
            <span className="whitespace-pre-wrap" dangerouslySetInnerHTML={sanitized} />
          ) : (
            <span className="whitespace-pre-wrap">{msg.content}</span>
          )}
        </div>
        {showFeedback && (
          <div className="flex items-center gap-1 ml-2 self-end pb-2">
            <span className="text-xs text-ink-muted">|</span>
            <button
              onClick={() => onRate(true)}
              className={`${
                rated === "up" ? "text-amber-500 scale-110" : "text-ink-muted"
              } hover:text-amber-500 transition-all text-xs cursor-pointer focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 ${
                rated ? "opacity-60" : ""
              }`}
              disabled={!!rated}
            >
              &#x1F44D;
            </button>
            <button
              onClick={() => onRate(false)}
              className={`${
                rated === "down" ? "text-red-400 scale-110" : "text-ink-muted"
              } hover:text-amber-500 transition-all text-xs cursor-pointer focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 ${
                rated ? "opacity-60" : ""
              }`}
              disabled={!!rated}
            >
              &#x1F44E;
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

/* ── ChatPanel ── */
interface ChatPanelProps {
  messages: ChatMessage[];
  streaming: boolean;
  input: string;
  setInput: (v: string) => void;
  sendMsg: (msg?: string) => void;
  showStartButton: boolean;
  handleStartReading: () => void;
  handleSatisfaction: (msgIndex: number, ok: boolean) => void;
  ratedMsgs: Record<number, "up" | "down">;
  lang: Lang;
  mode: string;
  currentWikiId: string;
  wikiChecklist: WikiItem[];
  chapterTitle: string;
  /** P5-19: Chapter celebration state */
  showCelebration: boolean;
  celebrationStats: { wikiCount: number; chatRounds: number } | null;
}

function ChatPanelInner({
  messages,
  streaming,
  input,
  setInput,
  sendMsg,
  showStartButton,
  handleStartReading,
  handleSatisfaction,
  ratedMsgs,
  lang,
  mode,
  currentWikiId,
  wikiChecklist,
  chapterTitle,
  showCelebration,
  celebrationStats,
}: ChatPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  /** P5-22: Compute current wiki name and round number for display */
  const wikiProgressLabel = useMemo(() => {
    if (mode !== "deep" || !currentWikiId || wikiChecklist.length === 0) return null;
    const idx = wikiChecklist.findIndex((w) => w.id === currentWikiId || w.status === "active");
    const wiki = idx >= 0 ? wikiChecklist[idx] : null;
    if (!wiki) return null;
    const doneCount = wikiChecklist.filter((w) => w.status === "done").length;
    return `${wiki.name} · 第 ${doneCount + 1}/${wikiChecklist.length} 轮`;
  }, [mode, currentWikiId, wikiChecklist]);

  // P5-19: Celebration overlay
  if (showCelebration) {
    return (
      <div className="rounded-2xl border border-border bg-white overflow-hidden animate-fade-in">
        <div className="p-8 text-center animate-scale-in">
          <div className="text-5xl mb-4">&#x1F389;</div>
          <h2 className="font-display text-2xl font-bold text-ink mb-2">
            {lang === "zh" ? "本章完成！" : "Chapter Complete!"}
          </h2>
          <p className="text-sm text-ink-soft mb-6">
            {chapterTitle || (lang === "zh" ? "本章完成" : "Chapter completed")}
          </p>
          {celebrationStats && (
            <div className="flex justify-center gap-6 mb-6">
              <div className="text-center">
                <div className="text-2xl font-bold text-ink">{celebrationStats.wikiCount}</div>
                <div className="text-xs text-ink-soft">
                  {lang === "zh" ? "Wiki 概念" : "Concepts"}
                </div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-ink">{celebrationStats.chatRounds}</div>
                <div className="text-xs text-ink-soft">
                  {lang === "zh" ? "对话轮次" : "Chat Rounds"}
                </div>
              </div>
            </div>
          )}
          <button
            onClick={() => {
              // Dismiss celebration and start next chapter
              handleStartReading();
            }}
            className="cursor-pointer rounded-xl px-8 py-3 text-sm font-medium text-white bg-ink hover:bg-black transition-all hover:scale-105 focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
          >
            {lang === "zh" ? "继续下一章 →" : "Next Chapter →"}
          </button>
        </div>
      </div>
    );
  }

  const chatMsgs = messages;

  return (
    <div className="rounded-2xl border border-border bg-white overflow-hidden">
      {/* P5-22: Wiki round indicator for deep mode */}
      {wikiProgressLabel && (
        <div className="px-4 pt-3 pb-0">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-purple-50 border border-purple-200 text-xs text-purple-700">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
            {wikiProgressLabel}
          </div>
        </div>
      )}

      <div
        ref={chatContainerRef}
        className="p-3 space-y-3 max-h-[55vh] overflow-y-auto"
        role="log"
        aria-live="polite"
        aria-label={lang === "zh" ? "对话消息" : "Chat messages"}
      >
        {(() => {
          let aiCount = 0;
          return chatMsgs.map((m, i) => {
            const isAi = m.role === "assistant";
            if (isAi) aiCount++;
            const showFeedback = isAi && aiCount % 3 === 0;
            return (
              <MsgBubble
                key={i}
                msg={m}
                showFeedback={showFeedback}
                rated={ratedMsgs[i]}
                onRate={(ok) => handleSatisfaction(i, ok)}
              />
            );
          });
        })()}
        <div ref={bottomRef} />
      </div>

      {showStartButton && (
        <div className="flex justify-center p-3 border-t border-border-light bg-surface-amber">
          <button
            onClick={handleStartReading}
            disabled={streaming}
            className="cursor-pointer rounded-xl px-8 py-3 text-sm font-medium text-white bg-ink hover:bg-black transition-colors hover:scale-105 active:scale-95 focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
          >
            {lang === "zh" ? "开始阅读本章" : "Start Reading"}
          </button>
        </div>
      )}

      <div className="flex gap-2 p-3 border-t border-border-light">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMsg()}
          placeholder={lang === "zh" ? "写下你的理解…" : "Write your understanding…"}
          className="flex-1 rounded-xl px-4 py-2.5 text-sm outline-none bg-ink-bg border border-border focus:border-ink-muted focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
          disabled={streaming}
        />
        <button
          onClick={() => sendMsg()}
          disabled={streaming}
          className={`cursor-pointer rounded-xl px-5 py-2.5 text-sm font-medium text-white focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 ${
            streaming ? "bg-ink-muted" : "bg-ink hover:bg-black"
          }`}
        >
          {streaming ? "…" : lang === "zh" ? "发送" : "Send"}
        </button>
      </div>
    </div>
  );
}

/** P5-14: Memo-ized to prevent re-renders when unrelated state changes */
export const ChatPanel = memo(ChatPanelInner);
