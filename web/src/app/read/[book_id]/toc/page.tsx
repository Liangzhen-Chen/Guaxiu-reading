"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { API } from "../../../config";

function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

export default function TocPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const [progress, setProgress] = useState<any>(null);
  const router = useRouter();

  useEffect(() => { load(); }, []);

  async function load() {
    const res = await fetch(`${API}/api/reading/progress/${book_id}?include_history=true`, {
      headers: { Authorization: `Bearer ${T()}` },
    });
    if (res.ok) setProgress(await res.json());
  }

  if (!progress) return <div className="text-center py-20 text-stone-400">加载中…</div>;

  const total = progress.total_chapters || 1;
  const current = progress.current_chapter || 0;

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="font-display text-2xl font-bold mb-2 text-stone-800">{progress.book_title}</h1>
      <p className="text-sm text-stone-400 mb-8">
        {progress.mode === "quick" ? "快速" : progress.mode === "balanced" ? "交互" : "深度"} · {total} 章 · {progress.status === "completed" ? "已读完" : `${Math.round(progress.progress_percent)}%`}
      </p>

      <div className="space-y-1">
        {Array.from({ length: total }, (_, i) => i + 1).map(ch => (
          <div
            key={ch}
            onClick={() => router.push(`/read/${book_id}`)}
            className={`flex items-center justify-between rounded-lg px-4 py-3 cursor-pointer transition-colors ${
              ch === current ? "bg-stone-900 text-white" :
              ch < current ? "bg-stone-100 text-stone-500" :
              "hover:bg-stone-50 text-stone-600"
            }`}
          >
            <span className="text-sm font-medium">第 {ch} 章</span>
            <span className="text-xs">
              {ch < current ? "✓" : ch === current ? "当前" : ""}
            </span>
          </div>
        ))}
      </div>

      {progress.status !== "not_started" && (
        <button
          onClick={() => router.push(`/read/${book_id}`)}
          className="cursor-pointer w-full mt-8 rounded-xl py-3 text-sm font-medium text-white bg-stone-900 hover:bg-black transition-colors"
        >
          {progress.status === "completed" ? "回顾导读" : "继续阅读"}
        </button>
      )}
    </div>
  );
}
