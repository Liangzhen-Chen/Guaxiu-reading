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
  const [typeFilter, setTypeFilter] = useState("all");
  const [bookFilter, setBookFilter] = useState("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  async function delEntry(id: string) {
    if (!confirm("确定删除这个概念吗？")) return;
    try {
      const res = await fetch(API + "/api/wiki/" + id, { method: "DELETE", headers: { Authorization: `Bearer ${getToken()}` } });
      if (res.ok) { setEntries(prev => prev.filter(e => e.id !== id)); showToast("已删除", "success"); }
      else showToast("删除失败", "error");
    } catch { showToast("网络错误", "error"); }
  }

  async function updateEntry(id: string, fields: Record<string, any>) {
    try {
      const res = await fetch(API + "/api/wiki/" + id, {
        method: "PUT", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify(fields),
      });
      if (res.ok) {
        setEntries(prev => prev.map(e => e.id === id ? { ...e, ...fields } : e));
        showToast("已更新", "success");
      } else showToast("更新失败", "error");
    } catch { showToast("网络错误", "error"); }
  }

  const TYPE_CYCLE: Record<string, string> = { concept: "viewpoint", viewpoint: "case", case: "concept" };
  const TYPE_LABEL: Record<string, string> = { concept: "概念", viewpoint: "观点", case: "案例" };
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

  // Gather unique book titles for filter
  const bookTitles = [...new Set(entries.map(e => e.book_title).filter(Boolean))] as string[];
  // Filter entries client-side
  const filtered = entries.filter(e => {
    if (typeFilter !== "all") {
      const st = e.entry_subtype || e.entry_type || "concept";
      if (st !== typeFilter) return false;
    }
    if (bookFilter !== "all" && e.book_title !== bookFilter) return false;
    return true;
  });

  if (!token) return <div className="text-center py-24 text-ink-soft">请先登录</div>;

  return (
    <div>
      <h1 className="font-display text-2xl font-bold mb-6 text-amber-deep">知识库 · {totalCount} 个概念{weekAddition > 0 ? ` · 本周+${weekAddition}` : ""}</h1>
      <div className="flex gap-3 mb-3">
        <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === "Enter" && load(search)}
          placeholder="搜索概念…" className="flex-1 rounded-lg px-4 py-3 text-sm bg-white border border-border focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2" />
        <button onClick={() => load(search)} className="rounded-lg px-5 py-3 text-sm font-medium text-white bg-ink focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">搜索</button>
      </div>
      <div className="flex gap-3 mb-6">
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="rounded-lg px-3 py-2 text-sm bg-white border border-border focus-visible:ring-2 focus-visible:ring-stone-500">
          <option value="all">全部类型</option>
          <option value="concept">概念</option>
          <option value="viewpoint">观点</option>
          <option value="case">案例</option>
        </select>
        <select value={bookFilter} onChange={e => setBookFilter(e.target.value)} className="rounded-lg px-3 py-2 text-sm bg-white border border-border focus-visible:ring-2 focus-visible:ring-stone-500">
          <option value="all">全部书籍</option>
          {bookTitles.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <span className="text-xs text-ink-muted self-center ml-auto">{filtered.length} 个结果</span>
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
          {filtered.map(e => (
            <div key={e.id} className="rounded-xl p-5 bg-white border border-border hover:border-ink-muted transition-colors relative group">
              <div className="mb-1">
                <div className="flex items-center gap-2 mb-0.5">
                  {(() => {
                    const st = (e.entry_subtype || e.entry_type || "concept") as string;
                    const label = TYPE_LABEL[st] || "概念";
                    const colors = st === "viewpoint" ? "bg-purple-50 text-purple-700" :
                                   st === "case" ? "bg-blue-50 text-blue-700" :
                                   "bg-amber-50 text-amber-700";
                    return <button onClick={(ev) => { ev.stopPropagation(); updateEntry(e.id, { entry_type: st, entry_subtype: TYPE_CYCLE[st] || "concept" }); }}
                      className={"text-xs px-2 py-0.5 rounded cursor-pointer hover:opacity-80 " + colors}
                      title="点击切换类型">{label}</button>;
                  })()}
                </div>
                {(e.book_title || e.chapter_index != null) && (
                  <div className="text-xs text-ink-soft leading-relaxed space-y-0.5">
                    {e.book_title && <div>来源：{e.book_title}</div>}
                    {e.chapter_index != null && <div>章节：第{e.chapter_index}章</div>}
                  </div>
                )}
              </div>
              <h3 className="font-display text-lg font-semibold mb-1">{e.concept_name}</h3>
              {editingId === e.id ? (
                <textarea value={editText} onChange={ev => setEditText(ev.target.value)}
                  onBlur={() => { if (editText !== e.ai_definition) updateEntry(e.id, { ai_definition: editText }); setEditingId(null); }}
                  onKeyDown={ev => { if (ev.key === "Escape") setEditingId(null); }}
                  className="w-full text-sm p-2 rounded border border-amber-300 focus:outline-none focus:ring-1 focus:ring-amber-400 resize-none"
                  rows={3} autoFocus />
              ) : (
                <p className="text-sm text-ink-soft leading-relaxed cursor-pointer hover:bg-amber-50 rounded p-1 -m-1"
                  onClick={() => { setEditingId(e.id); setEditText(e.ai_definition || ""); }}
                  title="点击编辑">{e.ai_definition || "(点击添加定义)"}</p>
              )}
              {e.tags && <div className="flex gap-1 mt-3 flex-wrap">{e.tags.map((t: string, i: number) => (
                <span key={i} className="text-xs px-2 py-0.5 rounded border border-border text-ink-soft">{t}</span>
              ))}</div>}
              <button onClick={(ev) => { ev.stopPropagation(); delEntry(e.id); }}
                className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 flex items-center justify-center rounded-full text-ink-muted hover:text-red-500 hover:bg-red-50 text-xs"
                title="删除">✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
