"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { API } from "../../config";

function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

function renderMD(text: string) {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-3 mb-1">$1</h2>')
    .replace(/`([^`]+)`/g, '<code class="bg-stone-200 px-1 rounded text-sm">$1</code>')
    .replace(/^---$/gm, '<hr class="my-2 border-stone-200"/>')
    .replace(/^- (.+)$/gm, '<li class="ml-4">$1</li>')
    .replace(/\n/g, '<br/>')
}

function L() { return typeof window !== "undefined" ? localStorage.getItem("lang") || "zh" : "zh"; }

export default function ReadPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const router = useRouter();
  const [status, setStatus] = useState("loading");
  const [mode, setMode] = useState("quick");
  const [chapter, setChapter] = useState(1);
  const [total, setTotal] = useState(0);
  const [messages, setMessages] = useState<{role:string;content:string;isSummary?:boolean}[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [concepts, setConcepts] = useState<string[]>([]);
  const [currentConcept, setCurrentConcept] = useState(0);
  const [originalText, setOriginalText] = useState("");
  const [wikiSelection, setWikiSelection] = useState<any>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const loadingChapter = useRef(0);

  useEffect(() => { loadState(); }, [book_id]);

  async function loadState() {
    const res = await fetch(`${API}/api/reading/resume/${book_id}`, { headers: { Authorization: `Bearer ${T()}` } });
    if (!res.ok) { setStatus("select-mode"); return; }
    const d = await res.json();
    setMode(d.mode); setChapter(d.current_chapter||1); setTotal(d.total_chapters||0);
    if (d.last_messages?.length) setMessages(d.last_messages.map((m:any)=>({role:m.role,content:m.content})));
    const s = d.status === "not_started" ? "select-mode" : d.status;
    setStatus(s);
    if (s === "reading") {
      loadChapterText(d.current_chapter||1);
      if (!d.last_messages?.length && !started.current) {
        started.current = true;
        setTimeout(() => sendMsg("开始"), 600);
      }
    }
  }

  async function loadChapterText(ch: number) {
    if (loadingChapter.current === ch) return;
    loadingChapter.current = ch;
    try {
      const res = await fetch(`${API}/api/reading/chapter/${book_id}?chapter=${ch}`, { headers: { Authorization: `Bearer ${T()}` } });
      if (res.ok) { const d = await res.json(); setOriginalText(d.text); }
    } catch(e) {}
  }

  async function selectMode(m: string) {
    setMode(m);
    await fetch(`${API}/api/reading/mode`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, mode: m, language: L() }) });
    setStatus("assessment");
  }

  async function sendMsg(msg?: string) {
    const text = msg || input;
    if (!text.trim() || streaming) return;
    setInput(""); setStreaming(true);

    if (status === "assessment") {
      const res = await fetch(`${API}/api/reading/assessment`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, message: text }) });
      const d = await res.json();
      setMessages(prev => [...prev, { role: "user", content: text }, { role: "assistant", content: d.ai_message }]);
      if (d.assessment_complete && !started.current) { setStatus("reading"); started.current = true; loadChapterText(chapter); setTimeout(() => sendMsg("开始"), 600); }
      setStreaming(false);
    } else {
      setMessages(prev => [...prev, { role: "user", content: text }]);
      const res = await fetch(`${API}/api/reading/chat`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, message: text }) });
      const reader = res.body?.getReader();
      if (!reader) { setStreaming(false); return; }
      const decoder = new TextDecoder(); let full = "";
      const isFirst = messages.length === 0;
      setMessages(prev => [...prev, { role: "assistant", content: "", isSummary: isFirst }]);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        // Use markdown rendering instead of stripping
        // MD rendered via renderMD() in the JSX(/\*\*([^*]+)\*\*/g, '$1').replace(/^###+\s?/gm, '').replace(/^---+\s?$/gm, '').replace(/`([^`]+)`/g, '$1');
        setMessages(prev => { const copy = [...prev]; copy[copy.length-1] = { ...copy[copy.length-1], content: full }; return copy; });
      }
      const matches = full.match(/\[\[([^\]]+)\]\]/g);
      if (matches) setConcepts(matches.map(m => m.slice(2, -2)));
      const wikiMatch = full.match(/<!--WIKI_SELECTION:(.*?)-->/);
      if (wikiMatch) { try { const d = JSON.parse(wikiMatch[1]); if (d.concepts?.length || d.viewpoints?.length) setWikiSelection(d); } catch(e) {} }
      if (full.includes("章完成")) {
        const nextCh = chapter + 1;
        if (nextCh <= total) { setChapter(nextCh); loadChapterText(nextCh); setMessages([]); setConcepts([]); setCurrentConcept(0); started.current = false; }
        loadState();
        return;
      }
      setStreaming(false);
    }
  }

  async function batchSave(selected: any[]) {
    await fetch(`${API}/api/wiki/batch`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify(selected) });
    setWikiSelection(null); loadState();
  }

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  if (status === "loading") return <div className="text-center py-20 text-stone-400">…</div>;
  if (status === "select-mode") {
    return (
      <div className="max-w-lg mx-auto mt-16">
        <h1 className="font-display text-2xl mb-8 text-center text-stone-800">{L()==="zh"?"选择阅读深度":"Choose Depth"}</h1>
        {[{id:"quick",t:"快速导读",d:"AI讲解为主，15分钟/章",icon:"⚡"},{id:"balanced",t:"原文交互",d:"原文与对话交替，30分钟/章",icon:"📖"},{id:"deep",t:"深度精读",d:"逐段精读，45分钟/章",icon:"🔍"}].map(m=>(
          <div key={m.id} onClick={()=>selectMode(m.id)} className={`cursor-pointer rounded-xl p-5 mb-3 transition-all ${mode===m.id?"border-2 border-stone-800 bg-stone-50":"border border-stone-200 bg-white"}`}>
            <span className="text-2xl mr-3">{m.icon}</span>
            <span className="font-display font-semibold">{m.t}</span>
            <span className="text-sm ml-2 text-stone-400">{m.d}</span>
          </div>
        ))}
        <button onClick={()=>selectMode(mode)} className="cursor-pointer w-full mt-6 rounded-xl py-3 text-sm font-medium text-white bg-stone-900 hover:bg-black">确认 →</button>
      </div>
    );
  }

  const progress = total > 0 ? Math.round((chapter / total) * 100) : 0;

  return (
    <div className="max-w-7xl mx-auto">
      {/* Chapter header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="font-display font-bold text-lg text-stone-800">第 {chapter} 章{total>0?` / ${total}`:""}</span>
          <div className="h-1.5 w-40 rounded-full bg-stone-100 hidden sm:block"><div className="h-1.5 rounded-full bg-stone-800 transition-all duration-700" style={{width:`${progress}%`}}/></div>
        </div>
        <div className="flex gap-3 text-xs text-stone-400">
          <button onClick={()=>router.push(`/read/${book_id}/toc`)} className="hover:text-stone-800">目录</button>
          <span>{mode==="quick"?"快速":mode==="balanced"?"交互":"深度"}</span>
        </div>
      </div>

      {/* Three columns */}
      <div className="flex gap-4">
        {/* LEFT: Guide */}
        <div className="w-40 shrink-0 hidden lg:block">
          <div className="sticky top-20 rounded-xl border border-stone-200 bg-white p-3">
            <div className="text-xs font-semibold text-stone-400 mb-2 uppercase tracking-wide">本章引导</div>
            {concepts.length > 0 ? concepts.map((c,i)=>(
              <div key={i} onClick={()=>{setCurrentConcept(i);sendMsg(L()==="zh"?`聊聊「${c}」`:`About "${c}"`);}}
                className={`text-xs px-2 py-1 rounded cursor-pointer mb-0.5 transition-colors ${
                  i<currentConcept?"text-stone-300 line-through":i===currentConcept?"bg-stone-900 text-white":"text-stone-500 hover:bg-stone-50"
                }`}>
                {i<currentConcept?"✓ ":i===currentConcept?"● ":""}{c}
              </div>
            )) : <div className="text-xs text-stone-400">AI 分析中…</div>}
            <button onClick={()=>sendMsg("/next")} className="mt-3 w-full text-xs py-1 rounded border border-stone-200 text-stone-400 hover:bg-stone-50">跳过本章 →</button>
          </div>
        </div>

        {/* CENTER: Original Text / Summary */}
        <div className="w-80 shrink-0 hidden md:block">
          <div className="sticky top-20 rounded-xl border border-stone-200 bg-white p-4 max-h-[70vh] overflow-y-auto">
            <div className="text-xs font-semibold text-stone-400 mb-2 uppercase tracking-wide">
              {mode==="quick"?"AI 概要":"原文"}
            </div>
            <div className="text-sm leading-relaxed text-stone-600 whitespace-pre-wrap">
              {originalText ? originalText.substring(0, 2000) + (originalText.length>2000?"...":"") : "加载中…"}
            </div>
          </div>
        </div>

        {/* RIGHT: Chat */}
        <div className="flex-1 min-w-0">
          <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
            <div className="p-4 space-y-4 max-h-[55vh] overflow-y-auto">
              {status==="assessment" && (
                <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-sm text-stone-600 mb-2">
                  {L()==="zh"?"正在了解你的背景，请回答 AI 的问题":"AI is learning about your background"}
                </div>
              )}
              {messages.map((m,i)=>(
                <div key={i} className={`flex ${m.role==="user"?"justify-end":"justify-start"}`}>
                  <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                    m.isSummary?"bg-amber-50 border border-amber-200 text-stone-700":
                    m.role==="user"?"bg-stone-900 text-white":"bg-stone-50 border border-stone-100 text-stone-700"
                  }`}>
                    {m.isSummary && <div className="text-xs text-amber-500 mb-1 font-medium">📋 本章概要</div>}
                    {<span dangerouslySetInnerHTML={{ __html: renderMD(m.content) }} />}
                  </div>
                </div>
              ))}
              {streaming && messages.length===0 && <p className="text-stone-400 text-sm text-center py-8">AI 正在准备…</p>}
              <div ref={bottomRef}/>
            </div>
            <div className="flex gap-2 p-3 border-t border-stone-100">
              <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&sendMsg()}
                placeholder={status==="assessment"?"回答…":"写下你的理解…"}
                className="flex-1 rounded-xl px-4 py-2.5 text-sm outline-none bg-stone-50 border border-stone-200 focus:border-stone-400"
                disabled={streaming}/>
              <button onClick={()=>sendMsg()} disabled={streaming}
                className={`cursor-pointer rounded-xl px-5 py-2.5 text-sm font-medium text-white ${streaming?"bg-stone-400":"bg-stone-900 hover:bg-black"}`}>
                {streaming?"…":"发送"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Wiki Selection Modal */}
      {wikiSelection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
          <div className="bg-white rounded-2xl p-6 w-96 max-h-[70vh] overflow-y-auto shadow-xl">
            <h3 className="font-semibold mb-2 text-lg">{L()==="zh"?"选择导入 Wiki":"Import to Wiki"}</h3>
            <div className="space-y-2">
              {wikiSelection.concepts?.map((c:any,i:number)=>(
                <label key={`c${i}`} className="flex items-start gap-2 p-2 rounded-lg hover:bg-stone-50 cursor-pointer">
                  <input type="checkbox" defaultChecked className="mt-0.5"/>
                  <div><div className="text-sm font-medium">{c.name}</div><div className="text-xs text-stone-400">{c.definition?.substring(0,80)}</div></div>
                </label>
              ))}
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={()=>setWikiSelection(null)} className="cursor-pointer rounded-xl py-2.5 px-4 text-sm text-stone-400 border">取消</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
