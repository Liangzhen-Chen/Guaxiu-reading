"use client";
import { memo } from "react";
import type { Lang } from "@/app/lang";

interface AssessmentPanelProps {
  status: string;
  assessmentQ: { question: string; options: { label: string; value: string }[] } | null;
  assessmentLoading: boolean;
  assessmentError: string;
  sendMsg: (msg?: string, silent?: boolean) => void;
  streaming: boolean;
  lang: Lang;
}

function AssessmentPanelInner({
  status,
  assessmentQ,
  assessmentLoading,
  assessmentError,
  sendMsg,
  streaming,
  lang,
}: AssessmentPanelProps) {
  if (status !== "assessment") return null;

  if (assessmentError) {
    return (
      <div className="rounded-2xl border border-border bg-white p-6 text-center">
        <p className="text-sm text-color-danger mb-4">{assessmentError}</p>
        <button
          onClick={() => sendMsg(lang === "zh" ? "开始评估" : "Start assessment", true)}
          className="cursor-pointer rounded-xl px-6 py-3 text-sm font-medium text-white bg-ink hover:bg-black focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
        >
          {lang === "zh" ? "重新开始评估" : "Retry Assessment"}
        </button>
      </div>
    );
  }

  if (assessmentQ) {
    return (
      <div className="rounded-2xl border border-border bg-white p-6">
        <div className="text-xs text-ink-soft mb-1 uppercase tracking-wide">
          {lang === "zh" ? "了解你的阅读背景" : "Learning your background"}
        </div>
        <h3 className="font-semibold text-lg text-ink mb-6">{assessmentQ.question}</h3>
        <div className="space-y-2">
          {assessmentQ.options.map((opt, i) => (
            <button
              key={i}
              onClick={() => { sendMsg(opt.label); }}
              className="w-full text-left cursor-pointer rounded-xl p-4 border border-border hover:border-ink-muted hover:bg-ink-bg transition-colors text-sm text-ink-secondary focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
            >
              {opt.label}
            </button>
          ))}
        </div>
        {/* P5-18: Skip assessment button - let user go directly to reading */}
        <div className="mt-4 pt-4 border-t border-border-light text-center">
          <button
            onClick={() => sendMsg(lang === "zh" ? "跳过评估，直接开始阅读" : "Skip assessment, start reading", true)}
            className="cursor-pointer text-xs text-ink-soft hover:text-ink underline focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 rounded"
          >
            {lang === "zh" ? "跳过评估，直接开始阅读 →" : "Skip to reading →"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-white p-6 text-center">
      {assessmentLoading ? (
        <>
          <span className="inline-block w-6 h-6 border-2 border-ink-muted border-t-ink-soft rounded-full animate-spin mb-3"></span>
          <p className="text-sm text-ink-soft">
            {lang === "zh" ? "AI 正在准备问题…" : "AI is preparing questions…"}
          </p>
        </>
      ) : (
        <>
          <p className="text-sm text-ink-soft mb-3">
            {lang === "zh" ? "点击下方按钮开始评估" : "Click send to start assessment"}
          </p>
          <button
            onClick={() => sendMsg(lang === "zh" ? "开始评估" : "Start assessment", true)}
            disabled={streaming}
            className="cursor-pointer rounded-xl px-6 py-3 text-sm font-medium text-white bg-ink hover:bg-black focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2"
          >
            {lang === "zh" ? "开始评估对话" : "Start Assessment"}
          </button>
          {/* P5-18: Quick start - skip assessment entirely */}
          <div className="mt-4">
            <button
              onClick={async () => {
                // Call mode endpoint with a flag to skip assessment
                await sendMsg("/skip-assessment", true);
              }}
              className="cursor-pointer text-xs text-ink-soft hover:text-ink underline focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 rounded"
            >
              {lang === "zh" ? "快速跳过，直接阅读 →" : "Quick start, skip assessment →"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/** P5-14: Memo-ized to prevent re-renders when unrelated state changes */
export const AssessmentPanel = memo(AssessmentPanelInner);
