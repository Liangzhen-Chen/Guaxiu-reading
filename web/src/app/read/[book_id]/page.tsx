"use client";
import { useState, useEffect, useRef } from "react";
import { useParams } from "next/navigation";

const API = "https://api.xiugua-reading.cn";
function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }
function L() { return typeof window !== "undefined" ? localStorage.getItem("lang") || "zh" : "zh"; }

async function trackEvent(e: string, p?: any) {
  fetch(API + "/api/analytics/event", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event: e, page: window.location.pathname, props: p }) }).catch(() => {});
}

export default function ReadPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const [status, setStatus] = useState("loading");
  const [mode, setMode] = useState("quick");
  const [chapter, setChapter] = useState(1);
  const [total, setTotal] = useState(0);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const roundCount = useRef(0);
  const [satisfaction, setSatisfaction] = useState(false);
  const started = useRef(false);

  useEffect(() => { loadState(); }, [book_id]);

  async function loadState() {
    const res = await fetch(`${API}/api/reading/resume/${book_id}`, { headers: { Authorization: `Bearer ${T()}` } });
    if (!res.ok) { setStatus("select-mode"); return; }
    const d = await res.json();
    setMode(d.mode); setChapter(d.current_chapter || 1); setTotal(d.total_chapters || 0);
    if (d.last_messages?.length) { setMessages(d.last_messages); }
    const s = d.status === "not_started" ? "select-mode" : d.status;
    setStatus(s);
    // 如果状态是 reading 且之前没有导读对话（评估对话不算），自动触发
    const hasReading = d.last_messages?.some((m: any) => m.round > -1);
    if (s === "reading" && !hasReading) {
      setTimeout(() => sendMsg("开始"), 300);
    }
  }

  async function selectMode(m: string) {
    setMode(m);
    await fetch(`${API}/api/reading/mode`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, mode: m, language: L() }) });
    setStatus("assessment");
    trackEvent("mode_select", { mode: m });
  }

  async function sendMsg(msg?: string) {
    const text = msg || input;
    if (!text.trim() || streaming) return;
    setInput(""); setStreaming(true);

    if (status === "assessment") {
      const res = await fetch(`${API}/api/reading/assessment`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, message: text }) });
      const d = await res.json();
      setMessages(prev => [...prev, { role: "user", content: text }, { role: "assistant", content: d.ai_message }]);
      if (d.assessment_complete) {
        setStatus("reading");
        setTimeout(() => sendMsg("开始"), 500);
      }
      setStreaming(false);
    } else {
      setMessages(prev => [...prev, { role: "user", content: text }]);
      const res = await fetch(`${API}/api/reading/chat`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, message: text }) });
      const reader = res.body?.getReader();
      if (!reader) { setStreaming(false); return; }
      const decoder = new TextDecoder();
      let full = "";
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        setMessages(prev => { const copy = [...prev]; copy[copy.length - 1] = { role: "assistant", content: full }; return copy; });
      }
      if (full.includes("章完成")) { loadState(); return; }
      setStreaming(false);
      roundCount.current += 1;
      if (roundCount.current > 3 && Math.random() < 0.05) setSatisfaction(true);
    }
  }

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  if (status === "loading") return <div className="text-center py-20 text-stone-400">加载中…</div>;

  if (status === "select-mode") {
    return (
      <div className="max-w-lg mx-auto mt-16">
        <h1 className="font-display text-2xl mb-8 text-center text-amber-700">选择阅读深度</h1>
        <div className="space-y-3">
          {[{ id: "quick", title: "快速导读", desc: "AI讲解为主，15分钟/章", icon: "⚡" }, { id: "balanced", title: "原文交互", desc: "原文与对话交替，30分钟/章", icon: "📖" }, { id: "deep", title: "深度精读", desc: "逐段精读，45分钟/章", icon: "🔍" }].map(m => (
            <div key={m.id} onClick={() => selectMode(m.id)} className={`cursor-pointer rounded-xl p-5 transition-all ${mode === m.id ? "border-2 border-amber-600 bg-amber-50" : "border border-stone-200 bg-white"}`}>
              <span className="text-2xl mr-3">{m.icon}</span>
              <span className="font-display font-semibold">{m.title}</span>
              <span className="text-sm ml-2 text-stone-400">{m.desc}</span>
            </div>
          ))}
        </div>
        <button onClick={() => selectMode(mode)} className="cursor-pointer w-full mt-6 rounded-xl py-3 text-sm font-medium text-white bg-stone-900 hover:bg-black transition-colors">确认 →</button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-4 text-xs text-stone-400">
        <span>{status === "assessment" ? "背景评估" : `第 ${chapter} 章`}{total > 0 && ` / ${total}`}</span>
        <span>{mode === "quick" ? "快速" : mode === "balanced" ? "交互" : "深度"}</span>
        {status === "paused" && <span className="text-amber-600">等待继续</span>}
      </div>

      <div className="rounded-xl overflow-hidden border border-stone-200 bg-white">
        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${m.role === "user" ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-800"}`}>
                {m.content}
              </div>
            </div>
          ))}
          {streaming && messages[messages.length - 1]?.role === "assistant" && !messages[messages.length - 1]?.content && (
            <div className="flex justify-start"><div className="rounded-xl px-4 py-2.5 text-sm bg-stone-100 text-stone-400">…</div></div>
          )}
          {satisfaction && (
            <div className="flex justify-start">
              <div className="rounded-xl px-4 py-2 text-sm flex items-center gap-3 bg-stone-50">
                <span className="text-stone-400">{L() === "zh" ? "有帮助吗？" : "Helpful?"}</span>
                <button onClick={() => { trackEvent("satisfaction", { ok: true }); setSatisfaction(false); }} className="hover:scale-110">👍</button>
                <button onClick={() => { trackEvent("satisfaction", { ok: false }); setSatisfaction(false); }} className="hover:scale-110">👎</button>
                <button onClick={() => setSatisfaction(false)} className="text-stone-300 text-xs">✕</button>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="flex gap-2 p-3 border-t border-stone-200">
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && sendMsg()}
            placeholder={status === "assessment" ? "回答…" : status === "paused" ? "输入任意内容继续…" : "写下你的理解…"}
            className="flex-1 rounded-lg px-3 py-2 text-sm outline-none bg-stone-50 border border-stone-200 focus:border-amber-400"
            disabled={streaming} />
          <button onClick={() => sendMsg()} disabled={streaming}
            className={`cursor-pointer rounded-lg px-4 py-2 text-sm font-medium text-white ${streaming ? "bg-stone-400" : "bg-stone-900 hover:bg-black"}`}>
            {streaming ? "…" : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
