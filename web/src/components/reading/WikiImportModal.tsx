"use client";
import { memo } from "react";
import type { Lang } from "@/app/lang";
import type { WikiSelection } from "./utils";

interface WikiImportModalProps {
  wikiSelection: WikiSelection | null;
  wikiChecked: Set<string>;
  setWikiChecked: (fn: (prev: Set<string>) => Set<string>) => void;
  batchSave: (selected: any[]) => void;
  setWikiSelection: (val: WikiSelection | null) => void;
  wikiDialogRef: React.RefObject<HTMLDivElement | null>;
  lang: Lang;
}

function WikiImportModalInner({
  wikiSelection,
  wikiChecked,
  setWikiChecked,
  batchSave,
  setWikiSelection,
  wikiDialogRef,
  lang,
}: WikiImportModalProps) {
  if (!wikiSelection) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="wiki-dialog-title"
    >
      <div
        ref={wikiDialogRef}
        className="bg-white rounded-2xl p-6 w-[480px] max-h-[75vh] overflow-y-auto shadow-2xl"
      >
        <div className="mb-5">
          <h3 id="wiki-dialog-title" className="font-bold text-xl text-ink mb-1">
            {lang === "zh"
              ? `本章 ${(wikiSelection.wikis?.length || 0) + (wikiSelection.concepts?.length || 0)} 个概念已沉淀`
              : `${(wikiSelection.wikis?.length || 0) + (wikiSelection.concepts?.length || 0)} Concepts Merged`}
          </h3>
          <p className="text-sm text-ink-soft">
            {lang === "zh"
              ? "勾选要导入 Wiki 的概念，未勾选的会被丢弃"
              : "Check concepts to import into your Wiki. Unchecked will be discarded."}
          </p>
        </div>
        <div className="space-y-1.5">
          {(wikiSelection.wikis || []).map((w: any, i: number) => {
            const typeLabel = w.type || w.entry_type || "concept";
            const typeColor =
              typeLabel === "case"
                ? "bg-surface-blue text-blue-700"
                : typeLabel === "viewpoint"
                  ? "bg-surface-purple text-purple-700"
                  : "bg-surface-amber text-amber-700";
            return (
              <label
                key={i}
                className="flex items-start gap-3 p-3 rounded-xl hover:bg-ink-bg cursor-pointer border border-transparent hover:border-border transition-all"
              >
                <input
                  type="checkbox"
                  checked={wikiChecked.has(`w-${i}`)}
                  onChange={() =>
                    setWikiChecked((prev) => {
                      const n = new Set(prev);
                      if (n.has(`w-${i}`)) n.delete(`w-${i}`);
                      else n.add(`w-${i}`);
                      return n;
                    })
                  }
                  className="mt-0.5 h-4 w-4 accent-ink focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-ink">{w.name}</span>
                    <span className={"text-[10px] px-1.5 py-0.5 rounded-full " + typeColor}>
                      {w.type || w.entry_type || "concept"}
                    </span>
                  </div>
                  <div className="text-xs text-ink-soft line-clamp-2">
                    {w.content?.substring(0, 120)}
                  </div>
                </div>
              </label>
            );
          })}
          {(wikiSelection.concepts || []).map((c: any, i: number) => (
            <label
              key={`c${i}`}
              className="flex items-start gap-3 p-3 rounded-xl hover:bg-ink-bg cursor-pointer border border-transparent hover:border-border transition-all"
            >
              <input
                type="checkbox"
                checked={wikiChecked.has(`c-${i}`)}
                onChange={() =>
                  setWikiChecked((prev) => {
                    const n = new Set(prev);
                    if (n.has(`c-${i}`)) n.delete(`c-${i}`);
                    else n.add(`c-${i}`);
                    return n;
                  })
                }
                className="mt-0.5 h-4 w-4 accent-ink focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-ink mb-0.5">{c.name}</div>
                <div className="text-xs text-ink-soft line-clamp-2">
                  {c.definition?.substring(0, 120)}
                </div>
              </div>
            </label>
          ))}
        </div>
        <div className="flex gap-3 mt-5 pt-4 border-t border-border-light">
          <button
            onClick={() => setWikiSelection(null)}
            className="cursor-pointer rounded-xl py-2.5 px-4 text-sm text-ink-soft hover:text-ink border border-border hover:border-ink-muted flex-1 transition-colors focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
          >
            {lang === "zh" ? "取消" : "Cancel"}
          </button>
          <button
            onClick={() => {
              const checked: any[] = [];
              wikiChecked.forEach((key) => {
                if (key.startsWith("w-")) {
                  const idx = parseInt(key.slice(2));
                  if (wikiSelection.wikis?.[idx]) checked.push(wikiSelection.wikis[idx]);
                }
                if (key.startsWith("c-")) {
                  const idx = parseInt(key.slice(2));
                  if (wikiSelection.concepts?.[idx]) checked.push(wikiSelection.concepts[idx]);
                }
              });
              if (checked.length > 0) batchSave(checked);
            }}
            className="cursor-pointer rounded-xl py-2.5 px-4 text-sm font-medium text-white bg-ink hover:bg-black flex-1 transition-colors focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
          >
            {lang === "zh" ? "确认导入" : "Import"}
          </button>
        </div>
      </div>
    </div>
  );
}

export const WikiImportModal = memo(WikiImportModalInner);
