"use client";
import { useState, useEffect } from "react";
import { track } from "../track";

import { API } from "../config";
function getToken() { if (typeof window === "undefined") return ""; return localStorage.getItem("token") || ""; }

interface Entry {
  id: string; concept_name: string; entry_type: string; entry_subtype: string; ai_definition: string | null;
  tags: string[] | null; chapter_index: number | null; evidence: any[] | null;
  book_title: string | null;
}

export default function WikiPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [search, setSearch] = useState("");
  const token = getToken();

  useEffect(() => { track("page_view"); if (token) load(); }, []);

  async function load(q?: string) {
    const url = new URL(API + "/api/wiki");
    if (q) url.searchParams.set("search", q);
    const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (res.ok) setEntries(await res.json());
  }

  if (!token) return <div className="text-center py-24 text-stone-400">请先登录</div>;

  return (
    <div>
      <h1 className="font-chinese text-2xl font-bold mb-6" style={{ color: "#8B6914" }}>Wiki</h1>
      <div className="flex gap-3 mb-6">
        <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === "Enter" && load(search)}
          placeholder="搜索概念…" className="flex-1 rounded-lg px-4 py-3 text-sm bg-white border border-stone-200" />
        <button onClick={() => load(search)} className="rounded-lg px-5 py-3 text-sm font-medium text-white bg-stone-900">搜索</button>
      </div>
      {entries.length === 0 ? (
        <div className="text-center py-24 text-stone-400">
          <p className="text-lg mb-2">知识库为空</p>
          <p className="text-sm mb-6">完成导读后，概念会自动沉淀到这里</p>
          <a href="/books" className="inline-block rounded-full bg-stone-900 text-white px-6 py-2.5 text-sm font-medium hover:bg-black transition-colors">去书架选书</a>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {entries.map(e => (
            <div key={e.id} className="rounded-xl p-5 bg-white border border-stone-200 hover:border-stone-300 transition-colors">
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
                  <span className="text-xs text-stone-400 truncate max-w-[200px]">{e.book_title}</span>
                )}
                {e.chapter_index && <span className="text-xs text-stone-400">· 第{e.chapter_index}章</span>}
              </div>
              <h3 className="font-chinese text-lg font-semibold mb-1">{e.concept_name}</h3>
              <p className="text-sm text-stone-500 leading-relaxed">{e.ai_definition}</p>
              {e.tags && <div className="flex gap-1 mt-3 flex-wrap">{e.tags.map((t: string, i: number) => (
                <span key={i} className="text-xs px-2 py-0.5 rounded border border-stone-200 text-stone-400">{t}</span>
              ))}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
