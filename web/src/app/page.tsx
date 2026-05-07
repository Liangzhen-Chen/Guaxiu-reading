"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useLang } from "./lang";
import { track } from "./track";
import { API } from "./config";

export default function Landing() {
  const { lang } = useLang();
  const [continueInfo, setContinueInfo] = useState<{title: string; chapter: number; bookId: string} | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { document.title = "朽瓜"; }, []);
  useEffect(() => { track("page_view"); }, []);

  const loggedIn = typeof window !== "undefined" && localStorage.getItem("token");

  // P5-20: Fetch "continue reading" info for logged-in users
  useEffect(() => {
    if (!loggedIn) { setLoading(false); return; }
    const token = localStorage.getItem("token") || "";
    (async () => {
      try {
        const res = await fetch(`${API}/api/books`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(10000),
        });
        if (!res.ok) { setLoading(false); return; }
        const books = await res.json();
        if (!Array.isArray(books) || books.length === 0) { setLoading(false); return; }
        // Find the most recently active book (reading or paused status)
        const active = books.find((b: any) =>
          b.status === "reading" || b.status === "paused"
        );
        if (active && active.current_chapter > 0) {
          setContinueInfo({
            title: active.title || active.book_title || "",
            chapter: active.current_chapter || 1,
            bookId: active.id || active.book_id || "",
          });
        }
        setLoading(false);
      } catch {
        setLoading(false);
      }
    })();
  }, [loggedIn]);

  return (
    <div className="min-h-[75vh] flex flex-col items-center justify-center text-center">
      <h1 className="font-display text-7xl font-bold tracking-tight mb-4 text-ink">
        {lang === "zh" ? "读完书，记得住" : "Read. Retain. Remember."}
      </h1>
      <p className="text-lg mb-6 max-w-lg leading-relaxed text-ink-soft">
        {lang === "zh"
          ? "AI 陪你逐章对话，追问你、验证你、帮你把知识沉淀下来。"
          : "AI reads with you chapter by chapter — questioning, verifying, and building your knowledge."}
      </p>

      <div className="flex gap-4 mb-16 text-sm text-ink-muted">
        <span>📖 {lang === "zh" ? "上传即读" : "Upload & read"}</span>
        <span>·</span>
        <span>💬 {lang === "zh" ? "AI追问" : "AI questions"}</span>
        <span>·</span>
        <span>🧠 {lang === "zh" ? "自动Wiki" : "Auto Wiki"}</span>
      </div>

      {!loading && loggedIn && continueInfo ? (
        <Link
          href={`/read/${continueInfo.bookId}`}
          className="btn btn-primary px-10 py-3.5 text-base tracking-wide focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2"
        >
          {lang === "zh"
            ? `继续阅读《${continueInfo.title}》第 ${continueInfo.chapter} 章 →`
            : `Continue "${continueInfo.title}" Ch ${continueInfo.chapter} →`}
        </Link>
      ) : (
        <Link
          href={loggedIn ? "/books" : "/login"}
          className="btn btn-primary px-10 py-3.5 text-base tracking-wide focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2"
        >
          {loggedIn
            ? (lang === "zh" ? "进入书架 →" : "My Books →")
            : (lang === "zh" ? "立即开始" : "Get Started")}
        </Link>
      )}
      <p className="text-xs mt-6 text-ink-muted">xiugua-reading.cn · v2026.05.07-5bc</p>
    </div>
  );
}
