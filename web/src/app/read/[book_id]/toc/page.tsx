"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { API } from "../../../config";
import { useLang } from "../../../lang";

function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

export default function TocPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const { lang } = useLang();
  const [progress, setProgress] = useState<any>(null);
  const router = useRouter();

  useEffect(() => { document.title = lang === "zh" ? "目录 | 朽瓜" : "Table of Contents | Xiugua"; }, [lang]);
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

  if (!progress) return <div className="text-center py-20 text-ink-muted">{lang==="zh"?"加载中…":"Loading…"}</div>;

  const total = progress.total_chapters || 1;
  const current = progress.current_chapter || 0;

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="font-display text-2xl font-bold mb-2 text-ink">{progress.book_title}</h1>
      <p className="text-sm text-ink-muted mb-8">
        {progress.mode === "quick" ? (lang==="zh"?"快速":"Quick") : (lang==="zh"?"深度":"Deep")} · {total} {lang==="zh"?"章":"Ch"} · {progress.status === "completed" ? (lang==="zh"?"已读完":"Completed") : `${Math.round(progress.progress_percent)}%`}
      </p>

      <div className="space-y-1">
        {Array.from({ length: total }, (_, i) => i + 1).map(ch => (
          <div
            key={ch}
            className={`flex items-center justify-between rounded-lg px-4 py-3 ${
              ch === current ? "bg-ink text-white" :
              ch < current ? "bg-ink-bg text-ink-soft" :
              "text-ink-secondary"
            }`}
          >
            <span className="text-sm font-medium">{chapters[ch-1] || (lang==="zh"?`第 ${ch} 章`:`Ch ${ch}`)}</span>
            <span className="text-xs">
              {ch < current ? "✓" : ch === current ? (lang==="zh"?"当前":"Current") : ""}
            </span>
          </div>
        ))}
      </div>

      {progress.status !== "not_started" && (
        <button
          onClick={() => router.push(`/read/${book_id}`)}
          className="cursor-pointer w-full mt-8 rounded-xl py-3 text-sm font-medium text-white bg-ink hover:bg-black transition-colors"
        >
          {progress.status === "completed" ? (lang==="zh"?"回顾导读":"Review") : (lang==="zh"?"继续阅读":"Continue Reading")}
        </button>
      )}
    </div>
  );
}
