"use client";
import { memo, useMemo } from "react";
import type { Lang } from "@/app/lang";
import { sanitizedMD } from "./utils";

interface ReadingMaterialProps {
  readingMaterial: string;
  lang: Lang;
  mode: string;
}

function ReadingMaterialInner({ readingMaterial, lang, mode }: ReadingMaterialProps) {
  const sanitized = useMemo(
    () =>
      readingMaterial
        ? sanitizedMD(readingMaterial)
        : {
            __html: `<span class="text-ink-soft">${
              lang === "zh"
                ? "对话开始后，AI 生成的阅读材料会出现在这里"
                : "Reading material will appear here once the conversation starts"
            }</span>`,
          },
    [readingMaterial, lang],
  );

  return (
    <div className="w-96 shrink-0 hidden md:block">
      <div className="sticky top-20 rounded-xl border border-border bg-white p-4 max-h-[70vh] overflow-y-auto">
        <div className="text-xs font-semibold text-ink-soft mb-2 uppercase tracking-wide">
          {mode === "deep"
            ? lang === "zh"
              ? "原文"
              : "Original Text"
            : lang === "zh"
              ? "阅读材料"
              : "Reading Material"}
        </div>
        <div
          className="text-sm leading-relaxed text-ink-secondary whitespace-pre-wrap"
          dangerouslySetInnerHTML={sanitized}
        />
      </div>
    </div>
  );
}

export const ReadingMaterial = memo(ReadingMaterialInner);
