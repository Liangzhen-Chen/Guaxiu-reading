"use client";
import { useState, useEffect, useRef } from "react";
import { track } from "../track";
import { showToast } from "../toast";

import { API } from "../config";
function getToken() { if (typeof window === "undefined") return ""; return localStorage.getItem("token") || ""; }

interface Entry {
  id: string; concept_name: string; entry_type: string; entry_subtype: string; ai_definition: string | null;
  tags: string[] | null; chapter_index: number | null; evidence: any[] | null;
  book_title: string | null;
}

let reqId = 0;

export default function WikiPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [weekAddition, setWeekAddition] = useState(0);
  const token = getToken();

  useEffect(() => {
    const recentCount = localStorage.getItem("wiki_recent_count");
    const recentTime = localStorage.getItem("wiki_recent_time");
    if (recentCount && recentTime) {
      const elapsed = Date.now() - parseInt(recentTime);
      if (elapsed < 60000) {
        showToast(`${recentCount} 个新概念已加入知识库`, "success");
      }
      localStorage.removeItem("wiki_recent_count");
      localStorage.removeItem("wiki_recent_time");
    }
  }, []);

  useEffect(() => { document.title = "Wiki | 朽瓜"; }, []);
  useEffect(() => { track("page_view"); if (token) { load(); } else { setIsLoading(false); } }, []);

  useEffect(() => {
    // Calculate weekly addition from localStorage
    const weekStart = new Date();
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    const weekKey = `wiki_week_${weekStart.toISOString().split("T")[0]}`;
    const wc = parseInt(localStorage.getItem(weekKey) || "0", 10);
    setWeekAddition(wc);
  }, [entries]);

  async function load(q?: string) {
    setError("");
    setIsLoading(true);
    const params = new URLSearchParams();
    if (q) params.set("search", q);
    params.set("limit", "9999");
    const thisReq = ++reqId;
    try {
      const res = await fetch(API + "/api/wiki?" + params.toString(), {
        headers: { Authorization: `Bearer ${getToken()}` },
        signal: AbortSignal.timeout(30000),
      });
      if (thisReq !== reqId) return; // discard stale results
      if (res.status === 401) { localStorage.removeItem("token"); window.location.href = "/login"; return; }
      if (res.ok) {
        const data = await res.json();
        setEntries(data);
        setTotalCount(data.length);
      }
      else setError("加载失败，请稍后重试");
    } catch {
      if (thisReq === reqId) setError("网络连接失败，请检查网络");
    } finally {
      if (thisReq === reqId) setIsLoading(false);
    }
  }

  if (!token) return <div className="text-center py-24 text-ink-soft">请先登录</div>;

  return (
    <div>
      <h1 className="font-display text-2xl font-bold mb-6 text-amber-deep">知识库 · {totalCount} 个概念{weekAddition > 0 ? ` · 本周+${weekAddition}` : ""}</h1>
      <div className="flex gap-3 mb-6">
        <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === "Enter" && load(search)}
          placeholder="搜索概念…" className="flex-1 rounded-lg px-4 py-3 text-sm bg-white border border-border focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2" />
        <button onClick={() => load(search)} className="rounded-lg px-5 py-3 text-sm font-medium text-white bg-ink focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">搜索</button>
      </div>
      {error && <p className="text-center text-sm text-red-500 mb-4">{error}</p>}
      {isLoading ? (
        <div className="text-center py-24 text-ink-soft">
          <span className="inline-block w-6 h-6 border-2 border-ink-muted border-t-ink-soft rounded-full animate-spin"></span>
        </div>
      ) : entries.length === 0 ? (
        <div className="text-center py-24 text-ink-soft">
          <p className="text-lg mb-2">知识库为空</p>
          <p className="text-sm mb-6">完成导读后，概念会自动沉淀到这里</p>
          <a href="/books" className="inline-block rounded-xl bg-ink text-white px-6 py-2.5 text-sm font-medium hover:bg-black transition-colors focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">去书架选书</a>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {entries.map(e => (
            <div key={e.id} className="rounded-xl p-5 bg-white border border-border hover:border-ink-muted transition-colors">
              <div className="flex items-center gap-2 mb-1">
                {(() => {
                  const st = e.entry_subtype || e.entry_type || "concept";
                  const label = st === "viewpoint" ? "观点" : st === "case" ? "案例" : "概念";
                  const colors = st === "viewpoint" ? "bg-purple-50 text-purple-700" :
                                 st === "case" ? "bg-blue-50 text-blue-700" :
                                 "bg-amber-50 text-amber-700";
                  return <span className={"text-xs px-2 py-0.5 rounded "+colors}>{label}</span>;
                })()}
                {e.book_title && (
                  <span className="text-xs text-ink-soft truncate max-w-[200px]">{e.book_title}</span>
                )}
                {e.chapter_index != null && <span className="text-xs text-ink-soft">· 第{e.chapter_index}章</span>}
              </div>
              <h3 className="font-display text-lg font-semibold mb-1">{e.concept_name}</h3>
              <p className="text-sm text-ink-soft leading-relaxed">{e.ai_definition}</p>
              {e.tags && <div className="flex gap-1 mt-3 flex-wrap">{e.tags.map((t: string, i: number) => (
                <span key={i} className="text-xs px-2 py-0.5 rounded border border-border text-ink-soft">{t}</span>
              ))}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
