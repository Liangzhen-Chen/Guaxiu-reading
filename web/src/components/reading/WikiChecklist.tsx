"use client";
import { memo } from "react";
import type { Lang } from "@/app/lang";
import type { WikiItem } from "./utils";

interface WikiChecklistProps {
  wikiChecklist: WikiItem[];
  currentWikiId: string;
  streaming: boolean;
  sendMsg: (msg?: string) => void;
  lang: Lang;
  status: string;
}

function WikiChecklistInner({
  wikiChecklist,
  currentWikiId,
  streaming,
  sendMsg,
  lang,
  status,
}: WikiChecklistProps) {
  const doneCount = wikiChecklist.filter((w) => w.status === "done").length;

  return (
    <div className="w-48 shrink-0 hidden lg:block">
      <div className="sticky top-20 rounded-xl border border-border bg-white p-3 max-h-[70vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold text-ink-soft uppercase tracking-wide">
            {lang === "zh" ? "本章 Wiki" : "Chapter Wiki"}
          </div>
          {wikiChecklist.length > 0 && (
            <div className="text-[10px] text-ink-soft">
              {doneCount}/{wikiChecklist.length} {lang === "zh" ? "已掌握" : "done"}
            </div>
          )}
        </div>
        {wikiChecklist.length > 0 ? (
          wikiChecklist.map((w) => (
            <div
              key={w.id}
              className={`text-xs px-2 py-1 rounded mb-0.5 ${
                w.status === "done"
                  ? "text-ink-muted line-through"
                  : w.id === currentWikiId || w.status === "active"
                    ? "bg-ink text-white"
                    : "text-ink-soft"
              }`}
            >
              {w.status === "done"
                ? "✓ "
                : w.id === currentWikiId || w.status === "active"
                  ? "● "
                  : "○ "}
              {w.name}
            </div>
          ))
        ) : (
          <div className="text-xs text-ink-soft">
            {status === "reading"
              ? lang === "zh"
                ? "暂无 Wiki，请先在书架点击\"AI帮你读\""
                : 'No wiki yet. Click "AI Read" on Bookshelf'
              : lang === "zh"
                ? "开始导读后显示"
                : "Shown after reading starts"}
          </div>
        )}
        <button
          onClick={() => {
            if (!streaming) sendMsg("/next");
          }}
          disabled={streaming}
          className="mt-3 w-full text-xs py-1 rounded border border-border text-ink-soft hover:bg-ink-bg disabled:opacity-50 disabled:cursor-not-allowed focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
        >
          {lang === "zh" ? "跳过本章 →" : "Skip Chapter →"}
        </button>
      </div>
    </div>
  );
}

export const WikiChecklist = memo(WikiChecklistInner);
