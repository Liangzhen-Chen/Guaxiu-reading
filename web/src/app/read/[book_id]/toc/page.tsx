"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { API } from "../../../config";

function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }
function L() { return typeof window !== "undefined" ? localStorage.getItem("lang") || "zh" : "zh"; }

export default function TocPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const [progress, setProgress] = useState<any>(null);
  const router = useRouter();

  useEffect(() => { load(); }, []);

  const [chapters, setChapters] = useState<string[]>([]);

  async function load() {
    const res = await fetch(`${API}/api/reading/progress/${book_id}?include_history=true`, {
      headers: { Authorization: `Bearer ${T()}` },
    });
    if (res.ok) setProgress(await res.json());
    // Fetch chapter names from P1 data
    const bookRes = await fetch(`${API}/api/books/${book_id}`, {
      headers: { Authorization: `Bearer ${T()}` },
    });
    if (bookRes.ok) {
      const book = await bookRes.json();
      try {
        if (book.category) {
          const d = JSON.parse(book.category);
          const kc = d.keep_chapters || [];
          setChapters(kc);
        }
      } catch {}
    }
  }

  if (!progress) return <div className="text-center py-20 text-stone-400">{L()==="zh"?"加载中…":"Loading…"}</div>;

  const total = progress.total_chapters || 1;
  const current = progress.current_chapter || 0;

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="font-display text-2xl font-bold mb-2 text-stone-800">{progress.book_title}</h1>
      <p className="text-sm text-stone-400 mb-8">
        {progress.mode === "quick" ? (L()==="zh"?"快速":"Quick") : (L()==="zh"?"深度":"Deep")} · {total} {L()==="zh"?"章":"Ch"} · {progress.status === "completed" ? (L()==="zh"?"已读完":"Completed") : `${Math.round(progress.progress_percent)}%`}
      </p>

      <div className="space-y-1">
        {Array.from({ length: total }, (_, i) => i + 1).map(ch => (
          <div
            key={ch}
            className={`flex items-center justify-between rounded-lg px-4 py-3 ${
              ch === current ? "bg-stone-900 text-white" :
              ch < current ? "bg-stone-100 text-stone-500" :
              "text-stone-600"
            }`}
          >
            <span className="text-sm font-medium">{chapters[ch-1] || (L()==="zh"?`第 ${ch} 章`:`Ch ${ch}`)}</span>
            <span className="text-xs">
              {ch < current ? "✓" : ch === current ? (L()==="zh"?"当前":"Current") : ""}
            </span>
          </div>
        ))}
      </div>

      {progress.status !== "not_started" && (
        <button
          onClick={() => router.push(`/read/${book_id}`)}
          className="cursor-pointer w-full mt-8 rounded-xl py-3 text-sm font-medium text-white bg-stone-900 hover:bg-black transition-colors"
        >
          {progress.status === "completed" ? (L()==="zh"?"回顾导读":"Review") : (L()==="zh"?"继续阅读":"Continue Reading")}
        </button>
      )}
    </div>
  );
}
