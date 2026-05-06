"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { API } from "../../config";

function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }
function L() { return typeof window !== "undefined" ? localStorage.getItem("lang") || "zh" : "zh"; }
function renderMD(text: string) {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-3 mb-1">$1</h2>')
    .replace(/`([^`]+)`/g, '<code class="bg-stone-200 px-1 rounded text-sm">$1</code>')
    .replace(/\[\[([^\]]+)\]\]/g, '<span class="inline-block bg-amber-100 text-amber-800 text-xs px-1.5 py-0.5 rounded">$1</span>')
    .replace(/^---$/gm, '<hr class="my-2 border-stone-200"/>')
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-2 border-stone-300 pl-3 text-stone-500">$1</blockquote>')
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal">$2</li>')
    .replace(/\n/g, '<br/>');
}

export default function ReadPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const router = useRouter();
  const [status, setStatus] = useState("loading");
  const [mode, setMode] = useState("quick");
  const [chapter, setChapter] = useState(1);
  const [total, setTotal] = useState(0);
  const [messages, setMessages] = useState<{role:string;content:string}[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [summary, setSummary] = useState("");
  const [concepts, setConcepts] = useState<string[]>([]);
  const [currentConcept, setCurrentConcept] = useState(0);
  const [chapterTitle, setChapterTitle] = useState("");
  const [chapterText, setChapterText] = useState("");
  const [wikiChecklist, setWikiChecklist] = useState<any[]>([]);
  const [currentWikiId, setCurrentWikiId] = useState("");
  const [readingMaterial, setReadingMaterial] = useState("");
  const [wikiSelection, setWikiSelection] = useState<any>(null);
  const [assessmentQ, setAssessmentQ] = useState<{question:string; options:{label:string;value:string}[]}|null>(null);
  const [assessmentLoading, setAssessmentLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const readingFirstMsg = useRef(false);
  const readingTriggered = useRef(false);

  const pollCount = useRef(0);
  useEffect(() => { pollCount.current = 0; loadState(); }, [book_id]);
  useEffect(() => {
    if (status !== "select-mode") return;
    if (concepts.length > 0 || pollCount.current >= 10) return;
    const t = setInterval(() => { pollCount.current++; loadState(); }, 2000);
    return () => clearInterval(t);
  }, [status, concepts.length]);

  // Auto-trigger first message when status transitions — ensures closure has correct status
  const [showStartButton, setShowStartButton] = useState(false);  // "开始阅读" / "开始本章" button
  const assessmentTriggered = useRef(false);
  useEffect(() => {
    if (status === "assessment" && !assessmentTriggered.current) {
      assessmentTriggered.current = true;
      setTimeout(() => sendMsg(L()==="zh"?"开始评估":"Start assessment", true), 400);
    }
    if (status !== "assessment") assessmentTriggered.current = false;
  }, [status]);

  function handleStartReading() {
    setShowStartButton(false);
    readingFirstMsg.current = true;
    sendMsg(L()==="zh"?"请介绍本章要点":"Introduce this chapter", true);
  }

  async function loadChapterText(ch: number) {
    for (let i = 0; i < 3; i++) {
      const res = await fetch(`${API}/api/reading/chapter/${book_id}?chapter=${ch}`, { headers: { Authorization: `Bearer ${T()}` } });
      if (res.ok) { const d = await res.json(); setChapterText(d.text || ""); return; }
      if (i < 2) await new Promise(r => setTimeout(r, 1000));
    }
  }
  async function loadState() {
    const res = await fetch(`${API}/api/reading/resume/${book_id}`, { headers: { Authorization: `Bearer ${T()}` } });
    if (!res.ok) { setStatus("select-mode"); return; }
    const d = await res.json();
    setMode(d.mode); setChapter(d.current_chapter||1); setTotal(d.total_chapters||0);
    if (d.wiki_checklist?.length) { setWikiChecklist(d.wiki_checklist); }
    if (d.current_wiki_id) { setCurrentWikiId(d.current_wiki_id); }
    if (d.reading_material) { setReadingMaterial(d.reading_material); }
    if (d.chapter_concepts?.length) { setConcepts(d.chapter_concepts); }
    const hasMessages = d.last_messages?.length > 0;
    if (hasMessages) {
      setMessages(d.last_messages.map((m:any)=>({role:m.role,content:m.content})));
      readingTriggered.current = true;  // resume: don't auto-trigger
    }
    const s = d.status === "not_started" ? "select-mode" : d.status;
    setStatus(s);
    if (d.current_chapter > 0) {
      loadChapterText(d.current_chapter);
      setChapterTitle(`第 ${d.current_chapter} 章`);
    }
    if (s === "reading" && !started.current) started.current = true;
    // Show start button for fresh reading entry or chapter transitions (paused→reading)
    if (s === "reading" && (!hasMessages || messages.length === 0)) {
      setShowStartButton(true);
    }
  }

  async function selectMode(m: string) {
    setMode(m);
    await fetch(`${API}/api/reading/mode`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, mode: m, language: L() }) });
    setStatus("assessment");
  }

  async function sendMsg(msg?: string, silent?: boolean) {
    const text = msg || input;
    if (!text.trim() || streaming) return;
    if (!silent) setInput("");
    setStreaming(true);

    if (status === "assessment") {
      setAssessmentLoading(true);
      const res = await fetch(`${API}/api/reading/assessment`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, message: text }) });
      setAssessmentLoading(false);
      const d = await res.json();
      if (!res.ok) { alert(d.detail || "评估请求失败"); setStreaming(false); return; }
      if (d.assessment_complete) {
        setAssessmentQ(null);
        setStatus("reading");
        loadChapterText(1);
        if (!started.current) started.current = true;
        setShowStartButton(true);
        if (!started.current) { started.current = true; }
      } else {
        try {
          const parsed = JSON.parse(d.ai_message);
          if (parsed.question && parsed.options?.length) {
            setAssessmentQ(parsed);
          }
          // If no valid card format, just keep loading state — don't leak raw JSON to chat
        } catch {
          // JSON parse failed — keep assessmentQ null, retry on next round
        }
      }
      setStreaming(false);
    } else {
      const isSummary = readingFirstMsg.current;
      readingFirstMsg.current = false;
      if (!silent) setMessages(prev => [...prev, { role: "user", content: text }]);
      const res = await fetch(`${API}/api/reading/chat`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ book_id, message: text }) });
      const reader = res.body?.getReader();
      if (!reader) { setStreaming(false); return; }
      const decoder = new TextDecoder(); let full = "";
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        // v4.0: Extract V4_META marker from streamed text
        const metaMatch = full.match(/<!--V4_META:([\s\S]*?)-->/);
        const displayText = metaMatch ? full.replace(/<!--V4_META:[\s\S]*?-->/, '').trim() : full;
        setMessages(prev => { const copy = [...prev]; copy[copy.length-1] = { role: "assistant", content: displayText }; return copy; });
        // Parse wiki metadata when complete
        if (metaMatch) {
          try {
            const parsed = JSON.parse(metaMatch[1]);
            if (parsed.current_wiki?.id) {
              setCurrentWikiId(parsed.current_wiki.id);
              setWikiChecklist(prev => prev.map((w: any) => ({
                ...w, status: w.id === parsed.current_wiki.id ? "active" :
                  w.id === currentWikiId ? "done" : w.status
              })));
            }
            setReadingMaterial(parsed.reading_material || "");
            if (isSummary) { setChapterTitle(`第 ${chapter} 章`); }
          } catch {}
        }
        if (full.includes("[CHAPTER_END]")) {
          setReadingMaterial("");
          setMessages([]);
          setChapterTitle("");
          setStreaming(false);
          setShowStartButton(true);  // show button for new chapter
          // Fetch chapter-end wiki list and show import modal
          try {
            const wRes = await fetch(`${API}/api/reading/chapter-end`, {
              method: "POST",
              headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
              body: JSON.stringify({ book_id, chapter_index: chapter }),
            });
            if (wRes.ok) {
              const wData = await wRes.json();
              if (wData.wikis?.length) { setWikiSelection({ wikis: wData.wikis }); }
            }
          } catch {}
          loadState();
          return;
        }
      }
      if (isSummary) { setChapterTitle(`第 ${chapter} 章`); }
      setStreaming(false);
    }
  }

  async function batchSave(selected: any[]) {
    await fetch(`${API}/api/wiki/batch`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify(selected) });
    setWikiSelection(null); loadState();
  }

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  if (status === "loading") return <div className="text-center py-20 text-stone-400"><span className="inline-block w-6 h-6 border-2 border-stone-300 border-t-stone-500 rounded-full animate-spin"></span></div>;
  if (status === "select-mode") {
    return (
      <div className="max-w-2xl mx-auto mt-8">
        <h1 className="font-display text-3xl font-bold mb-2 text-stone-800">{L()==="zh"?"选择阅读模式":"Select Reading Mode"}</h1>
        <p className="text-sm text-stone-400 mb-6">{L()==="zh"?"AI 会根据你选择的深度，调整追问的层次和对话的节奏。":"AI will adjust the depth of questioning and pace of dialogue based on your choice."}</p>

        {/* Concepts from parse */}
        {/* v4.0: Wiki checklist preview (if available from preprocess) */}
        {wikiChecklist.length > 0 ? (
          <div className="rounded-xl border border-stone-200 bg-white p-5 mb-6">
            <div className="text-xs font-semibold text-stone-400 mb-3 uppercase tracking-wide">{L()==="zh"?"本章 Wiki 预览":"Chapter Wiki Preview"}</div>
            <div className="flex flex-wrap gap-2">
              {wikiChecklist.map((w:any,i:number)=>(
                <span key={i} className="text-sm px-3 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">{w.name}</span>
              ))}
            </div>
          </div>
        ) : concepts.length > 0 ? (
          <div className="rounded-xl border border-stone-200 bg-white p-5 mb-6">
            <div className="text-xs font-semibold text-stone-400 mb-3 uppercase tracking-wide">{L()==="zh"?"本书核心论点":"Core Arguments"}</div>
            <div className="flex flex-wrap gap-2">
              {concepts.map((c,i)=>(
                <span key={i} className="text-sm px-3 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">{c}</span>
              ))}
            </div>
          </div>
        ) : null}

        {/* Mode selection */}
        <div className="mb-6">
          <div className="text-xs font-semibold text-stone-400 mb-3 uppercase tracking-wide">{L()==="zh"?"阅读深度":"Reading Depth"}</div>
          <div className="space-y-2">
            {[{id:"quick",t:"快速模式",d:"AI概括为主，15-20分钟/章",icon:"⚡",desc:"以AI讲解和概括为主，几乎不涉及原文，适合快速了解全书"},{id:"deep",t:"深度模式",d:"原文精读，30-40分钟/章",icon:"🔍",desc:"大量原文引用，AI逐段解析追问，适合精读掌握"}].map(m=>(
              <div key={m.id} onClick={()=>setMode(m.id)} className={`cursor-pointer rounded-xl p-4 transition-all ${mode===m.id?"border-2 border-stone-800 bg-stone-50":"border border-stone-200 bg-white"}`}>
                <div className="flex items-center gap-2 mb-1"><span className="text-xl">{m.icon}</span><span className="font-display font-semibold">{m.t}</span><span className="text-xs text-stone-400">{m.d}</span></div>
                <p className="text-xs text-stone-400 ml-8">{m.desc}</p>
              </div>
            ))}
          </div>
        </div>

        <button onClick={()=>selectMode(mode)} className="cursor-pointer w-full rounded-xl py-3 text-sm font-medium text-white bg-stone-900 hover:bg-black">
          {L()==="zh"?"开始评估 →":"Start Assessment →"}
        </button>
      </div>
    );
  }

  const progress = total > 0 ? Math.round((chapter / total) * 100) : 0;
  const chatMsgs = messages.filter(m => m.content !== summary); // exclude summary from chat

  return (
    <div className="px-6" style={{zoom:1.2}}>
      {/* Top bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="font-display font-bold text-xl">{chapterTitle || `第 ${chapter} 章`}</span>
          {total > 0 && <span className="text-stone-400">/ {total}</span>}
          <div className="h-1.5 w-32 rounded-full bg-stone-100 hidden sm:block"><div className="h-1.5 rounded-full bg-stone-800 transition-all" style={{width:`${progress}%`}}/></div>
        </div>
        <div className="flex gap-3 text-xs text-stone-400">
          <button onClick={()=>router.push(`/read/${book_id}/toc`)} className="hover:text-stone-800">目录</button>
          <span>{mode==="quick"?"快速":mode==="balanced"?"交互":"深度"}</span>
        </div>
      </div>

      <div className="flex gap-3">
        {/* LEFT: Wiki Checklist */}
        <div className="w-48 shrink-0 hidden lg:block">
          <div className="sticky top-20 rounded-xl border border-stone-200 bg-white p-3 max-h-[70vh] overflow-y-auto">
            <div className="text-xs font-semibold text-stone-400 mb-2 uppercase tracking-wide">本章 Wiki</div>
            {wikiChecklist.length > 0 ? wikiChecklist.map((w: any) => (
              <div key={w.id}
                className={`text-xs px-2 py-1 rounded mb-0.5 ${
                  w.status === "done" ? "text-stone-300 line-through" :
                  w.id === currentWikiId || w.status === "active" ? "bg-stone-900 text-white" :
                  "text-stone-500"
                }`}>
                {w.status === "done" ? "✓ " : w.id === currentWikiId || w.status === "active" ? "● " : "○ "}{w.name}
              </div>
            )) : <div className="text-xs text-stone-400">
              {status==="reading" ? "暂无 Wiki，请先在书架点击\"AI帮你读\"" : "开始导读后显示"}
            </div>}
            <button onClick={()=>sendMsg("/next")} className="mt-3 w-full text-xs py-1 rounded border border-stone-200 text-stone-400 hover:bg-stone-50">跳过本章 →</button>
          </div>
        </div>

        {/* CENTER: Reading Material */}
        <div className="w-80 shrink-0 hidden md:block">
          <div className="sticky top-20 rounded-xl border border-stone-200 bg-white p-4 max-h-[70vh] overflow-y-auto">
            <div className="text-xs font-semibold text-stone-400 mb-2 uppercase tracking-wide">{mode==="deep"?"原文":"阅读材料"}</div>
            <div className="text-sm leading-relaxed text-stone-600 whitespace-pre-wrap">
              {readingMaterial ? <span>{readingMaterial}</span> :
               <span className="text-stone-400">对话开始后，AI 生成的阅读材料会出现在这里</span>}
            </div>
          </div>
        </div>

        {/* RIGHT: Chat / Assessment */}
        <div className="flex-1 min-w-0">
          {status === "assessment" && assessmentQ ? (
            <div className="rounded-2xl border border-stone-200 bg-white p-6">
              <div className="text-xs text-stone-400 mb-1 uppercase tracking-wide">{L()==="zh"?"了解你的阅读背景":"Learning your background"}</div>
              <h3 className="font-semibold text-lg text-stone-800 mb-6">{assessmentQ.question}</h3>
              <div className="space-y-2">
                {assessmentQ.options.map((opt, i) => (
                  <button key={i} onClick={() => { setAssessmentQ(null); sendMsg(opt.label); }}
                    className="w-full text-left cursor-pointer rounded-xl p-4 border border-stone-200 hover:border-stone-400 hover:bg-stone-50 transition-colors text-sm text-stone-700">
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          ) : status === "assessment" ? (
            <div className="rounded-2xl border border-stone-200 bg-white p-6 text-center">
              {assessmentLoading ? (
                <>
                  <span className="inline-block w-6 h-6 border-2 border-stone-300 border-t-stone-500 rounded-full animate-spin mb-3"></span>
                  <p className="text-sm text-stone-400">{L()==="zh"?"AI 正在准备问题…":"AI is preparing questions…"}</p>
                </>
              ) : (
                <>
                  <p className="text-sm text-stone-400 mb-3">{L()==="zh"?"点击下方发送按钮开始评估":"Click send to start assessment"}</p>
                  <button onClick={()=>sendMsg(L()==="zh"?"开始评估":"Start assessment", true)} disabled={streaming} className="cursor-pointer rounded-xl px-6 py-3 text-sm font-medium text-white bg-stone-900 hover:bg-black">{L()==="zh"?"开始评估对话":"Start Assessment"}</button>
                </>
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
              <div className="p-3 space-y-3 max-h-[55vh] overflow-y-auto">
                {chatMsgs.map((m,i)=>(
                  <div key={i} className={`flex ${m.role==="user"?"justify-end":"justify-start"}`}>
                    <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${m.role==="user"?"bg-stone-900 text-white":"bg-stone-50 border border-stone-100"}`}>
                      {m.role==="assistant" ? <span className="whitespace-pre-wrap">{m.content}</span> : <span className="whitespace-pre-wrap">{m.content}</span>}
                    </div>
                  </div>
                ))}
                <div ref={bottomRef}/>
              </div>
              {showStartButton && (
                <div className="flex justify-center p-3 border-t border-stone-100 bg-amber-50">
                  <button onClick={handleStartReading} disabled={streaming}
                    className="cursor-pointer rounded-xl px-8 py-3 text-sm font-medium text-white bg-stone-900 hover:bg-black transition-colors">
                    {L()==="zh"?"开始阅读本章":"Start Reading"}
                  </button>
                </div>
              )}
              <div className="flex gap-2 p-3 border-t border-stone-100">
                <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&sendMsg()}
                  placeholder={L()==="zh"?"写下你的理解…":"Write your understanding…"}
                  className="flex-1 rounded-xl px-4 py-2.5 text-sm outline-none bg-stone-50 border border-stone-200 focus:border-stone-400"
                  disabled={streaming}/>
                <button onClick={()=>sendMsg()} disabled={streaming} className={`cursor-pointer rounded-xl px-5 py-2.5 text-sm font-medium text-white ${streaming?"bg-stone-400":"bg-stone-900 hover:bg-black"}`}>{streaming?"…":"发送"}</button>
              </div>
            </div>
          )}
        </div>
      </div>
      {wikiSelection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
          <div className="bg-white rounded-2xl p-6 w-96 max-h-[70vh] overflow-y-auto shadow-xl">
            <h3 className="font-semibold mb-3 text-lg">{L()==="zh"?"选择导入 Wiki":"Import to Wiki"}</h3>
            {wikiSelection.wikis?.map((w:any,i:number)=>(
              <label key={i} className="flex items-start gap-2 p-2 rounded-lg hover:bg-stone-50 cursor-pointer">
                <input type="checkbox" defaultChecked className="mt-0.5" data-wiki-index={i}/>
                <div>
                  <div className="text-sm font-medium">{w.name}</div>
                  <div className="text-xs text-stone-400">{w.content?.substring(0,80)}</div>
                  {w.type && <span className="text-2xs px-1.5 py-0.5 rounded bg-stone-100 text-stone-500 ml-1">{w.type}</span>}
                </div>
              </label>
            ))}
            {wikiSelection.concepts?.map((c:any,i:number)=>(
              <label key={`c${i}`} className="flex items-start gap-2 p-2 rounded-lg hover:bg-stone-50 cursor-pointer">
                <input type="checkbox" defaultChecked className="mt-0.5" data-concept-index={i}/>
                <div><div className="text-sm font-medium">{c.name}</div><div className="text-xs text-stone-400">{c.definition?.substring(0,80)}</div></div>
              </label>
            ))}
            <div className="flex gap-2 mt-4">
              <button onClick={()=>setWikiSelection(null)} className="cursor-pointer rounded-xl py-2.5 px-4 text-sm text-stone-400 border flex-1">{L()==="zh"?"取消":"Cancel"}</button>
              <button onClick={(e) => {
                const checked: any[] = [];
                e.currentTarget.parentElement?.querySelectorAll('input:checked').forEach((cb: any) => {
                  const wi = cb.dataset.wikiIndex;
                  const ci = cb.dataset.conceptIndex;
                  if (wi !== undefined && wikiSelection.wikis) checked.push(wikiSelection.wikis[parseInt(wi)]);
                  if (ci !== undefined && wikiSelection.concepts) checked.push(wikiSelection.concepts[parseInt(ci)]);
                });
                if (checked.length > 0) batchSave(checked);
              }} className="cursor-pointer rounded-xl py-2.5 px-4 text-sm font-medium text-white bg-stone-900 hover:bg-black flex-1">{L()==="zh"?"确认导入":"Import"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
