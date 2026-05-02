"use client";
import { useState, useEffect, useRef } from "react";
import { useParams } from "next/navigation";

const API = "http://localhost:8000";
function getToken() { return localStorage.getItem("token") || ""; }
function getLang() { return localStorage.getItem("lang") || "zh"; }

async function trackEvent(e: string, p?: any) {
  fetch(API + "/api/analytics/event", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event: e, page: window.location.pathname, props: p }),
  }).catch(() => {});
}

type Status = "loading" | "select-mode" | "assessment" | "reading" | "paused" | "completed";

export default function ReadPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const [status, setStatus] = useState<Status>("loading");
  const [mode, setMode] = useState("quick");
  const [chapter, setChapter] = useState(0);
  const [totalChapters, setTotalChapters] = useState(0);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const token = getToken();
  const roundCount = useRef(0);
  const [showSatisfaction, setShowSatisfaction] = useState(false);

  useEffect(() => { loadState(); }, [book_id]);

  async function loadState() {
    const res = await fetch(`${API}/api/reading/resume/${book_id}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { setStatus("select-mode"); return; }
    const d = await res.json();
    setMode(d.mode); setChapter(d.current_chapter); setTotalChapters(d.total_chapters || 0);
    if (d.last_messages) setMessages(d.last_messages);
    setStatus(d.status === "not_started" ? "select-mode" : d.status === "assessment" ? "assessment" : "reading");
  }

  async function selectMode(m: string) {
    setMode(m);
    await fetch(`${API}/api/reading/mode`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ book_id, mode: m, language: getLang() }),
    });
    setStatus("assessment");
    trackEvent("mode_select", { mode: m });
  }

  async function sendMsg(msg?: string) {
    const text = msg || input;
    if (!text.trim() || streaming) return;
    setInput(""); setStreaming(true);

    if (status === "assessment") {
      const res = await fetch(`${API}/api/reading/assessment`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ book_id, message: text }),
      });
      const d = await res.json();
      setMessages(prev => [...prev, { role: "user", content: text }, { role: "assistant", content: d.ai_message }]);
      if (d.next_action === "enter_reading") setStatus("reading");
      setStreaming(false);
    } else {
      const res = await fetch(`${API}/api/reading/chat`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ book_id, message: text }),
      });
      setMessages(prev => [...prev, { role: "user", content: text }]);
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
      if (full.includes("第") && full.includes("章完成")) loadState();
      setStreaming(false);
      roundCount.current += 1;
      if (roundCount.current > 2 && Math.random() < 0.15) setShowSatisfaction(true);
    }
  }

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  if (status === "loading") return <div className="text-center py-20" style={{ color: "#9C9284" }}>加载中…</div>;

  if (status === "select-mode") {
    return (
      <div className="max-w-lg mx-auto mt-16">
        <h1 className="font-chinese text-2xl mb-8 text-center" style={{ color: "#8B6914" }}>选择阅读深度</h1>
        <div className="space-y-3">
          {[{ id: "quick", title: "快速导读", desc: "AI讲解为主，15分钟/章", icon: "⚡" },
            { id: "balanced", title: "原文交互", desc: "原文与对话交替，30分钟/章", icon: "📖" },
            { id: "deep", title: "深度精读", desc: "逐段精读，45分钟/章", icon: "🔍" }].map(m => (
            <div key={m.id} onClick={() => selectMode(m.id)}
              className="cursor-pointer rounded-lg p-5 transition-all"
              style={{ border: mode === m.id ? "2px solid #8B6914" : "1px solid #E0D8C8", background: mode === m.id ? "#EDE4CC" : "#FFFAF5" }}>
              <span className="text-2xl mr-3">{m.icon}</span>
              <span className="font-chinese font-semibold">{m.title}</span>
              <span className="text-sm ml-2" style={{ color: "#9C9284" }}>{m.desc}</span>
            </div>
          ))}
        </div>
        <button onClick={() => selectMode(mode)} className="w-full mt-6 rounded py-3 text-sm font-medium text-white" style={{ background: "#2C2416" }}>
          确认，开始评估 →
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-4 text-xs" style={{ color: "#9C9284" }}>
        <span>{status === "assessment" ? "背景评估" : `第${chapter || 1}章`}{totalChapters > 0 && ` / ${totalChapters}`}</span>
        <span>模式: {mode === "quick" ? "快速" : mode === "balanced" ? "交互" : "深度"}</span>
        {status === "paused" && <span className="text-amber-600">等待继续</span>}
      </div>

      <div className="rounded-lg overflow-hidden" style={{ border: "1px solid #E0D8C8", background: "#FFFAF5" }}>
        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-lg px-4 py-2 text-sm leading-relaxed ${
                m.role === "user"
                  ? "text-white"
                  : "text-[#2C2416]"
              }`} style={{ background: m.role === "user" ? "#2C2416" : "#EDE4CC", borderBottomLeftRadius: m.role === "assistant" ? "4px" : undefined, borderBottomRightRadius: m.role === "user" ? "4px" : undefined }}>
                <div className="whitespace-pre-wrap">{m.content}</div>
              </div>
            </div>
          ))}
          {showSatisfaction && (
            <div className="flex justify-start px-4">
              <div className="rounded-lg px-4 py-2 text-sm flex items-center gap-3" style={{ background: "#f5f5f7" }}>
                <span className="text-[#86868b]">{getLang() === "zh" ? "回答有帮助吗？" : "Was this helpful?"}</span>
                <button onClick={() => { trackEvent("satisfaction", { ok: true }); setShowSatisfaction(false); }} className="hover:scale-110 transition-transform">👍</button>
                <button onClick={() => { trackEvent("satisfaction", { ok: false }); setShowSatisfaction(false); }} className="hover:scale-110 transition-transform">👎</button>
                <button onClick={() => setShowSatisfaction(false)} className="text-[#86868b] hover:text-[#1d1d1f] text-xs">✕</button>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="flex gap-2 p-3 border-t" style={{ borderColor: "#E0D8C8" }}>
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && sendMsg()}
            placeholder={status === "assessment" ? "回答评估问题…" : status === "paused" ? "输入任意内容继续…" : "写下你的理解…"}
            className="flex-1 rounded px-3 py-2 text-sm outline-none" style={{ background: "white", border: "1px solid #E0D8C8" }}
            disabled={streaming} />
          <button onClick={() => sendMsg()} disabled={streaming}
            className="rounded px-4 py-2 text-sm font-medium text-white" style={{ background: streaming ? "#9C9284" : "#2C2416" }}>
            {streaming ? "…" : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
