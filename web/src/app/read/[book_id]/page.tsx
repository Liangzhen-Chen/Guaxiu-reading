"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { API } from "../../config";
import { showToast } from "../../toast";
import { useLang } from "../../lang";
import { T } from "@/components/reading/utils";
import { AssessmentPanel } from "@/components/reading/AssessmentPanel";
import { ChatPanel } from "@/components/reading/ChatPanel";
import { WikiChecklist } from "@/components/reading/WikiChecklist";
import { ReadingMaterial } from "@/components/reading/ReadingMaterial";
import { WikiImportModal } from "@/components/reading/WikiImportModal";

export default function ReadPage() {
  const { book_id } = useParams<{ book_id: string }>();
  const router = useRouter();
  const { lang } = useLang();
  const [status, setStatus] = useState("loading");
  const [mode, setMode] = useState("quick");
  const [chapter, setChapter] = useState(1);
  const [total, setTotal] = useState(0);
  const [messages, setMessages] = useState<{role:string;content:string}[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [concepts, setConcepts] = useState<string[]>([]);
  const [chapterTitle, setChapterTitle] = useState("");
  const [readingMaterial, setReadingMaterial] = useState("");
  const [wikiChecklist, setWikiChecklist] = useState<any[]>([]);
  const [currentWikiId, setCurrentWikiId] = useState("");
  const [wikiSelection, setWikiSelection] = useState<any>(null);
  const [assessmentQ, setAssessmentQ] = useState<{question:string; options:{label:string;value:string}[]}|null>(null);
  const [assessmentLoading, setAssessmentLoading] = useState(false);
  const [error, setError] = useState("");
  const [assessmentError, setAssessmentError] = useState("");
  const [showModeSwitch, setShowModeSwitch] = useState(false);
  const [ratedMsgs, setRatedMsgs] = useState<Record<number, "up"|"down">>({});
  const [mobilePanel, setMobilePanel] = useState<"chat" | "wiki" | "reading">("chat");
  // Desktop always shows all 3 columns; mobile shows 1 at a time
  const [forceDesktop, setForceDesktop] = useState(true);
  useEffect(() => {
    const check = () => setForceDesktop(window.innerWidth >= 1024);
    check(); window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  const showWiki = forceDesktop || mobilePanel === "wiki";
  const showReading = forceDesktop || mobilePanel === "reading";
  const showChat = forceDesktop || mobilePanel === "chat";

  // P5-19: Chapter celebration state
  const [showCelebration, setShowCelebration] = useState(false);
  const [celebrationStats, setCelebrationStats] = useState<{wikiCount: number; chatRounds: number} | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const wikiDialogRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const readingFirstMsg = useRef(false);
  const readingTriggered = useRef(false);
  const currentWikiIdRef = useRef(currentWikiId);
  const assessmentFailCount = useRef(0);
  const assessmentTriggered = useRef(false);
  const pollCount = useRef(0);

  useEffect(() => { currentWikiIdRef.current = currentWikiId; }, [currentWikiId]);
  useEffect(() => { pollCount.current = 0; loadState(); }, [book_id]);
  useEffect(() => {
    document.title = chapterTitle ? `${chapterTitle} | 朽瓜` : "阅读 | 朽瓜";
  }, [chapterTitle]);
  useEffect(() => {
    if (status !== "select-mode") return;
    if (concepts.length > 0 || pollCount.current >= 10) return;
    const t = setInterval(async () => {
      pollCount.current++;
      try {
        // P5-16: Use lightweight wiki-status endpoint for polling
        const wikiRes = await fetch(`${API}/api/reading/wiki-status/${book_id}`, {
          headers: { Authorization: `Bearer ${T()}` },
          signal: AbortSignal.timeout(15000),
        });
        if (wikiRes.ok) {
          const d = await wikiRes.json();
          if (d.wiki_checklist?.length) setWikiChecklist(d.wiki_checklist);
          if (d.chapter_concepts?.length) setConcepts(d.chapter_concepts);
        }
      } catch {
        // Poll failures are expected on initial load
      }
    }, 2000);
    return () => clearInterval(t);
  }, [status, concepts.length]);

  // P5-21: Pre-select "quick" mode (already default, ensure visual highlight)
  // Use open polling for wiki_status instead of full /resume (P5-16)

  // Auto-trigger first assessment message
  useEffect(() => {
    if (status === "assessment" && !assessmentTriggered.current) {
      assessmentTriggered.current = true;
      setTimeout(() => sendMsg(lang==="zh"?"开始评估":"Start assessment", true), 400);
    }
    if (status !== "assessment") assessmentTriggered.current = false;
  }, [status]);

  function handleStartReading() {
    setShowCelebration(false);
    setShowStartButton(false);
    readingFirstMsg.current = true;
    sendMsg(lang==="zh"?"请介绍本章要点":"Introduce this chapter", true);
  }

  const [showStartButton, setShowStartButton] = useState(false);

  async function loadChapterText(ch: number) {
    for (let i = 0; i < 3; i++) {
      const res = await fetch(`${API}/api/reading/chapter/${book_id}?chapter=${ch}`, { headers: { Authorization: `Bearer ${T()}` } });
      if (res.ok) { /* text not used directly in new architecture */ return; }
      if (i < 2) await new Promise(r => setTimeout(r, 1000));
    }
  }

  async function loadState() {
    // Phase 1: Lightweight wiki-status for metadata (mode, chapter, wiki checklist)
    let hasHistory = false;
    try {
      const wikiRes = await fetch(`${API}/api/reading/wiki-status/${book_id}`, {
        headers: { Authorization: `Bearer ${T()}` },
        signal: AbortSignal.timeout(15000),
      });
      if (wikiRes.ok) {
        const d = await wikiRes.json();
        if (d.mode) setMode(d.mode);
        if (d.current_chapter) {
          setChapter(d.current_chapter);
          setChapterTitle(lang==="zh"?`第 ${d.current_chapter} 章`:`Ch ${d.current_chapter}`);
        }
        if (d.total_chapters) setTotal(d.total_chapters);
        if (d.wiki_checklist?.length) setWikiChecklist(d.wiki_checklist);
        if (d.current_wiki_id) setCurrentWikiId(d.current_wiki_id);
        if (d.chapter_concepts?.length) setConcepts(d.chapter_concepts);
        if (d.status && d.status !== "loading") {
          setStatus(d.status === "not_started" ? "select-mode" : d.status);
        }
        hasHistory = !!d.has_history;
      }
    } catch {
      // wiki-status is optional; fall through to /resume
    }

    // Phase 2: Always call /resume for messages + reading material (authoritative)
    try {
      const res = await fetch(`${API}/api/reading/resume/${book_id}`, { headers: { Authorization: `Bearer ${T()}` } });
      if (res.ok) {
        const d = await res.json();
        // Don't overwrite state already set by wiki-status, but fill in gaps
        if (!hasHistory) {
          // First load or no history — wiki-status handles metadata
          setReadingMaterial(d.reading_material || "");
        } else {
          // Has history — use /resume metadata (more complete)
          if (d.mode) setMode(d.mode);
          if (d.current_chapter) {
            setChapter(d.current_chapter);
            setChapterTitle(lang==="zh"?`第 ${d.current_chapter} 章`:`Ch ${d.current_chapter}`);
          }
          if (d.total_chapters) setTotal(d.total_chapters);
          if (d.wiki_checklist?.length) setWikiChecklist(d.wiki_checklist);
          if (d.current_wiki_id) setCurrentWikiId(d.current_wiki_id);
          if (d.reading_material) setReadingMaterial(d.reading_material);
          if (d.chapter_concepts?.length) setConcepts(d.chapter_concepts);
          const s = d.status === "not_started" ? "select-mode" : d.status;
          setStatus(s);
        }
        const hasMessages = d.last_messages?.length > 0;
        if (hasMessages) {
          setMessages(d.last_messages.map((m:any)=>({role:m.role,content:m.content})));
          readingTriggered.current = true;
        }
        if (!hasMessages && d.status === "reading") {
          setShowStartButton(true);
        }
      }
    } catch {
      // If /resume also fails, wiki-status already set basic state; don't show error
    }
  }

  async function switchMode(newMode: string) {
    setShowModeSwitch(false);
    try {
      await fetch(`${API}/api/reading/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
        body: JSON.stringify({ book_id, mode: newMode, language: lang }),
        signal: AbortSignal.timeout(30000),
      });
    } catch {
      showToast(lang==="zh"?"模式切换失败，请重试":"Mode switch failed, please retry", "error");
      return;
    }
    setMode(newMode);
    loadState();
  }

  async function selectMode(m: string) {
    setMode(m);
    try {
      await fetch(`${API}/api/reading/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
        body: JSON.stringify({ book_id, mode: m, language: lang }),
        signal: AbortSignal.timeout(30000),
      });
    } catch {
      setError("模式设置失败，请检查网络后重试");
      showToast("模式设置失败，请检查网络后重试", "error");
      return;
    }
    setStatus("assessment");
  }

  async function sendMsg(msg?: string, silent?: boolean) {
    const text = msg || input;
    if (!text.trim() || streaming) return;
    if (!silent) setInput("");
    setStreaming(true);
    setError("");

    // P5-18: Skip assessment handler
    if (text === "/skip-assessment") {
      try {
        // If not yet in assessment, set mode first
        await fetch(`${API}/api/reading/mode`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
          body: JSON.stringify({ book_id, mode: mode, language: lang }),
          signal: AbortSignal.timeout(30000),
        });
        // Call assessment with a special message for backend
        const aRes = await fetch(`${API}/api/reading/assessment`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
          body: JSON.stringify({ book_id, message: "/skip-assessment" }),
          signal: AbortSignal.timeout(30000),
        });
        if (aRes.ok) {
          setAssessmentQ(null);
          setStatus("reading");
          setShowCelebration(false);
          loadState();
          setShowStartButton(true);
          started.current = true;
        } else {
          showToast("跳过评估失败", "error");
        }
      } catch {
        showToast("跳过评估请求失败", "error");
      }
      setStreaming(false);
      return;
    }

    if (status === "assessment") {
      // --- Assessment branch ---
      setAssessmentLoading(true);
      setAssessmentError("");
      assessmentFailCount.current = 0;
      try {
        const res = await fetch(`${API}/api/reading/assessment`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
          body: JSON.stringify({ book_id, message: text }),
        });
        setAssessmentLoading(false);
        const d = await res.json();
        if (!res.ok) {
          showToast(d.detail || "评估请求失败", "error");
          setStreaming(false);
          return;
        }
        if (d.assessment_complete) {
          setAssessmentQ(null);
          setStatus("reading");
          loadState();
          setShowStartButton(true);
          started.current = true;
        } else {
          try {
            const parsed = JSON.parse(d.ai_message);
            if (parsed.question && parsed.options?.length) {
              setAssessmentQ(parsed);
              assessmentFailCount.current = 0;
            }
          } catch {
            assessmentFailCount.current++;
            if (assessmentFailCount.current >= 3) {
              setAssessmentError("评估响应格式异常，请重试");
            }
          }
        }
        setStreaming(false);
      } catch {
        setAssessmentLoading(false);
        showToast("评估请求网络异常，请重试", "error");
        setStreaming(false);
      }
    } else {
      // --- Chat/Reading branch ---
      const isSummary = readingFirstMsg.current;
      readingFirstMsg.current = false;
      if (!silent) setMessages(prev => [...prev, { role: "user", content: text }]);
      const res = await fetch(`${API}/api/reading/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
        body: JSON.stringify({ book_id, message: text }),
        signal: AbortSignal.timeout(300000),
      });
      if (!res.ok) {
        showToast("对话请求失败，请重试", "error");
        setStreaming(false);
        return;
      }
      const reader = res.body?.getReader();
      if (!reader) {
        showToast("无法获取响应流，请重试", "error");
        setStreaming(false);
        return;
      }
      const decoder = new TextDecoder(); let full = "";
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);
      while (true) {
        try {
          const { done, value } = await reader.read();
          if (done) break;
          full += decoder.decode(value, { stream: true });
        } catch {
          showToast("连接中断，请重试", "error");
          setStreaming(false);
          return;
        }
        const metaMatch = full.match(/<!--V4_META:([\s\S]*?)-->/);
        const displayText = (metaMatch ? full.replace(/<!--V4_META:[\s\S]*?-->/, '') : full)
          .replace(/<!--CHAPTER_END[^>]*-->/g, '').trim();
        setMessages(prev => { const copy = [...prev]; copy[copy.length-1] = { role: "assistant", content: displayText }; return copy; });
        if (metaMatch) {
          try {
            const parsed = JSON.parse(metaMatch[1]);
            if (parsed.current_wiki?.id) {
              setCurrentWikiId(parsed.current_wiki.id);
              const prevWikiId = currentWikiIdRef.current;
              setWikiChecklist(prev => prev.map((w: any) => ({
                ...w, status: w.id === parsed.current_wiki.id ? "active" :
                  w.id === prevWikiId ? "done" : w.status
              })));
            }
            if (parsed.reading_material) setReadingMaterial(parsed.reading_material);
            if (isSummary) { setChapterTitle(lang==="zh"?`第 ${chapter} 章`:`Ch ${chapter}`); }
          } catch { /* non-critical */ }
        }
        if (full.includes("<!--CHAPTER_END")) {
          setReadingMaterial("");

          // P5-19: Auto-save wikis silently, show celebration instead of modal
          const ceMatch = full.match(/<!--CHAPTER_END:([\s\S]*?)-->/);
          const wikiData = ceMatch ? (() => { try { return JSON.parse(ceMatch[1]); } catch { return null; } })() : null;

          const currentRounds = messages.filter(m => m.role === "assistant").length + 1;
          if (wikiData?.wikis?.length) {
            // Auto-save all wikis silently
            batchSave(wikiData.wikis).then(() => {
              // Show celebration with stats (capture rounds before promise)
              setCelebrationStats({
                wikiCount: wikiData.wikis.length,
                chatRounds: currentRounds,
              });
              setShowCelebration(true);
            });
          } else {
            // No wikis, try API fetch
            try {
              const wRes = await fetch(`${API}/api/reading/chapter-end`, {
                method: "POST",
                headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
                body: JSON.stringify({ book_id, chapter_index: chapter }),
              });
              if (wRes.ok) {
                const wData = await wRes.json();
                if (wData.wikis?.length) {
                  batchSave(wData.wikis).then(() => {
                    setCelebrationStats({ wikiCount: wData.wikis.length, chatRounds: currentRounds });
                    setShowCelebration(true);
                  });
                }
              }
            } catch { /* silent fail */ }
          }

          setChapterTitle("");
          setStreaming(false);
          setShowStartButton(true);
          loadState();
          return;
        }
      }
      if (isSummary) { setChapterTitle(lang==="zh"?`第 ${chapter} 章`:`Ch ${chapter}`); }
      setStreaming(false);
    }
  }

  async function handleSatisfaction(msgIndex: number, ok: boolean) {
    setRatedMsgs(prev => ({ ...prev, [msgIndex]: ok ? "up" : "down" }));
    try {
      await fetch(`${API}/api/analytics/event`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
        body: JSON.stringify({ event: "satisfaction", props: { ok } }),
      });
    } catch { /* non-critical */ }
  }

  async function batchSave(selected: any[]) {
    await fetch(`${API}/api/wiki/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` },
      body: JSON.stringify(selected),
    });
    localStorage.setItem("wiki_recent_count", String(selected.length));
    localStorage.setItem("wiki_recent_time", Date.now().toString());
    const weekStart = new Date();
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    const weekKey = `wiki_week_${weekStart.toISOString().split("T")[0]}`;
    const prevWeek = parseInt(localStorage.getItem(weekKey) || "0", 10);
    localStorage.setItem(weekKey, String(prevWeek + selected.length));
    setWikiSelection(null); // Clear modal after save
  }

  // P3-1: Wiki checkbox state
  const [wikiChecked, setWikiChecked] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (wikiSelection) {
      const checked = new Set<string>();
      (wikiSelection.wikis || []).forEach((_: any, i: number) => checked.add(`w-${i}`));
      (wikiSelection.concepts || []).forEach((_: any, i: number) => checked.add(`c-${i}`));
      setWikiChecked(checked);
    }
  }, [wikiSelection]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Focus trap for Wiki import dialog
  useEffect(() => {
    if (!wikiSelection) return;
    const prevFocus = document.activeElement as HTMLElement;
    const t = setTimeout(() => {
      const dlg = wikiDialogRef.current;
      if (!dlg) return;
      const focusable = dlg.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      focusable[0]?.focus();
    }, 50);
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") { setWikiSelection(null); return; }
      if (e.key !== "Tab") return;
      const dlg = wikiDialogRef.current;
      if (!dlg) return;
      const focusable = dlg.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener("keydown", handleKey);
    return () => { clearTimeout(t); document.removeEventListener("keydown", handleKey); prevFocus?.focus(); };
  }, [wikiSelection]);

  if (status === "loading") {
    return (
      <div className="text-center py-20 text-ink-soft">
        <span className="inline-block w-6 h-6 border-2 border-ink-muted border-t-ink-soft rounded-full animate-spin"></span>
      </div>
    );
  }

  if (status === "select-mode") {
    return (
      <div className="max-w-2xl mx-auto mt-8 px-4">
        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-surface-red border border-color-danger/20 text-sm text-color-danger">{error}</div>
        )}
        <h1 className="font-display text-3xl font-bold mb-2 text-ink">{lang==="zh"?"选择阅读模式":"Select Reading Mode"}</h1>
        <p className="text-sm text-ink-soft mb-6">{lang==="zh"?"AI 会根据你选择的深度，调整追问的层次和对话的节奏。":"AI will adjust the depth of questioning and pace of dialogue based on your choice."}</p>

        {wikiChecklist.length > 0 ? (
          <div className="rounded-xl border border-border bg-white p-5 mb-6">
            <div className="text-xs font-semibold text-ink-soft mb-3 uppercase tracking-wide">{lang==="zh"?"本章 Wiki 预览":"Chapter Wiki Preview"}</div>
            <div className="flex flex-wrap gap-2">
              {wikiChecklist.map((w:any,i:number)=>(
                <span key={i} className="text-sm px-3 py-1 rounded-full bg-surface-amber text-amber-deep border border-amber-deep/20">{w.name}</span>
              ))}
            </div>
          </div>
        ) : concepts.length > 0 ? (
          <div className="rounded-xl border border-border bg-white p-5 mb-6">
            <div className="text-xs font-semibold text-ink-soft mb-3 uppercase tracking-wide">{lang==="zh"?"本书核心论点":"Core Arguments"}</div>
            <div className="flex flex-wrap gap-2">
              {concepts.map((c,i)=>(
                <span key={i} className="text-sm px-3 py-1 rounded-full bg-surface-amber text-amber-deep border border-amber-deep/20">{c}</span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mb-6">
          <div className="text-xs font-semibold text-ink-soft mb-3 uppercase tracking-wide">{lang==="zh"?"阅读深度":"Reading Depth"}</div>
          <div className="space-y-2">
            {[{id:"quick",t_zh:"快速模式",t_en:"Quick Mode",d_zh:"AI概括为主，15-20分钟/章",d_en:"AI summary, 15-20min/ch",icon:"⚡",desc_zh:"以AI讲解和概括为主，几乎不涉及原文，适合快速了解全书",desc_en:"AI explains and summarizes with minimal original text. Best for quick overviews."},{id:"deep",t_zh:"深度模式",t_en:"Deep Mode",d_zh:"原文精读，30-40分钟/章",d_en:"Close reading, 30-40min/ch",icon:"🔍",desc_zh:"大量原文引用，AI逐段解析追问，适合精读掌握",desc_en:"Heavy original text with AI paragraph-by-paragraph analysis. Best for deep mastery."}].map(m=>(
              <div key={m.id} onClick={()=>setMode(m.id)} tabIndex={0} className={`cursor-pointer rounded-xl p-4 transition-all focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 ${mode===m.id?"border-2 border-ink bg-ink-bg":"border border-border bg-white"}`}>
                <div className="flex items-center gap-2 mb-1"><span className="text-xl">{m.icon}</span><span className="font-display font-semibold">{lang==="zh"?m.t_zh:m.t_en}</span><span className="text-xs text-ink-soft">{lang==="zh"?m.d_zh:m.d_en}</span></div>
                <p className="text-xs text-ink-soft ml-8">{lang==="zh"?m.desc_zh:m.desc_en}</p>
              </div>
            ))}
          </div>
        </div>

        {/* P5-18: Quick start button directly goes to reading */}
        <div className="flex gap-2">
          <button onClick={()=>selectMode(mode)}
            className="cursor-pointer flex-1 rounded-xl py-3 text-sm font-medium text-white bg-ink hover:bg-black focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2">
            {lang==="zh"?"开始评估 →":"Start Assessment →"}
          </button>
          <button onClick={async ()=>{
            setMode(mode);
            try {
              await fetch(`${API}/api/reading/mode`, {
                method:"POST",
                headers:{"Content-Type":"application/json",Authorization:`Bearer ${T()}`},
                body:JSON.stringify({book_id,mode:mode,language:lang}),
                signal:AbortSignal.timeout(30000),
              });
              await sendMsg("/skip-assessment", true);
            } catch {
              setError("快速开始失败");
            }
          }}
            className="cursor-pointer rounded-xl py-3 px-4 text-sm font-medium text-ink border border-border hover:bg-ink-bg focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2">
            {lang==="zh"?"快速开始 →":"Quick Start →"}
          </button>
        </div>
      </div>
    );
  }

  const progress = total > 0 ? Math.round((chapter / total) * 100) : 0;

  return (
    <div className="px-6 pb-20 lg:pb-0 max-w-full overflow-hidden">
      {error && (
        <div className="mb-4 px-4 py-3 rounded-xl bg-surface-red border border-color-danger/20 text-sm text-color-danger">{error}</div>
      )}

      {/* Top bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="font-display font-bold text-xl">{chapterTitle || (lang==="zh"?`第 ${chapter} 章`:`Ch ${chapter}`)}</span>
          {total > 0 && <span className="text-ink-soft">/ {total}</span>}
          <div className="h-2.5 w-32 rounded-full bg-ink-bg hidden sm:block">
            <div className="h-2.5 rounded-full bg-gradient-to-r from-amber-500 to-amber-300 transition-all" style={{width:`${progress}%`}}/>
          </div>
        </div>
        <div className="flex gap-3 text-xs text-ink-soft items-center">
          <button onClick={()=>router.push(`/read/${book_id}/toc`)}
            className="hover:text-ink focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 rounded">
            {lang==="zh"?"目录":"TOC"}
          </button>
          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
            mode==="quick"?"bg-amber-100 text-amber-700":"bg-purple-100 text-purple-700"
          }`}>
            {mode==="quick"?(lang==="zh"?"快速":"Quick"):(lang==="zh"?"深度":"Deep")}
          </span>
          <div className="relative">
            <button onClick={()=>setShowModeSwitch(!showModeSwitch)}
              className="hover:text-ink underline focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 rounded">
              {lang==="zh"?"切换模式":"Switch"}
            </button>
            {showModeSwitch && (
              <div className="absolute right-0 top-6 z-20 bg-white border border-border rounded-xl shadow-lg p-1.5 min-w-[100px]">
                {[{id:"quick",zh:"快速",en:"Quick"},{id:"deep",zh:"深度",en:"Deep"}].map(m=>(
                  <button key={m.id} onClick={()=>switchMode(m.id)}
                    className={`block w-full text-left px-3 py-1.5 rounded-lg text-xs whitespace-nowrap focus-visible:ring-2 focus-visible:ring-ink-soft focus-visible:ring-offset-2 ${
                      mode===m.id?"bg-ink-bg text-ink":"text-ink-soft hover:bg-ink-bg"
                    }`}>
                    {lang==="zh"?m.zh:m.en}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        {/* LEFT: Wiki Checklist */}
        {showWiki && (
        <div className="w-1/6 shrink-0 min-w-[160px]">
          <WikiChecklist
            wikiChecklist={wikiChecklist}
            currentWikiId={currentWikiId}
            streaming={streaming}
            sendMsg={sendMsg}
            lang={lang}
            status={status}
          />
        </div>
        )}
        {/* CENTER: Reading Material */}
        {showReading && (
        <div className="w-1/4 shrink-0 min-w-[220px]">
          <ReadingMaterial
            readingMaterial={readingMaterial}
            lang={lang}
            mode={mode}
          />
        </div>
        )}
        {/* RIGHT: Chat / Assessment */}
        {showChat && (
        <div className="flex-1 min-w-0 overflow-hidden">
          {status === "assessment" ? (
            <AssessmentPanel
              status={status}
              assessmentQ={assessmentQ}
              assessmentLoading={assessmentLoading}
              assessmentError={assessmentError}
              sendMsg={sendMsg}
              streaming={streaming}
              lang={lang}
            />
          ) : (
            <ChatPanel
              messages={messages}
              streaming={streaming}
              input={input}
              setInput={setInput}
              sendMsg={sendMsg}
              showStartButton={showStartButton}
              handleStartReading={handleStartReading}
              handleSatisfaction={handleSatisfaction}
              ratedMsgs={ratedMsgs}
              lang={lang}
              mode={mode}
              currentWikiId={currentWikiId}
              wikiChecklist={wikiChecklist}
              chapterTitle={chapterTitle}
              showCelebration={showCelebration}
              celebrationStats={celebrationStats}
            />
          )}
        </div>
        )}
      </div>

      {/* P3-9: Mobile bottom navigation */}
      <div className="fixed bottom-0 left-0 right-0 z-40 flex lg:hidden items-center justify-around bg-white border-t border-border px-4 py-2 pb-[env(safe-area-inset-bottom,8px)] shadow-lg">
        <button onClick={()=>setMobilePanel("wiki")}
          className={`flex flex-col items-center gap-0.5 text-xs ${mobilePanel==="wiki"?"text-ink font-medium":"text-ink-soft"}`}>
          <span className="text-lg">📖</span>
          <span>{lang==="zh"?"Wiki":"Wiki"}</span>
        </button>
        <button onClick={()=>setMobilePanel("reading")}
          className={`flex flex-col items-center gap-0.5 text-xs ${mobilePanel==="reading"?"text-ink font-medium":"text-ink-soft"}`}>
          <span className="text-lg">📄</span>
          <span>{lang==="zh"?"原文":"Reading"}</span>
        </button>
        <button onClick={()=>setMobilePanel("chat")}
          className={`flex flex-col items-center gap-0.5 text-xs ${mobilePanel==="chat"?"text-ink font-medium":"text-ink-soft"}`}>
          <span className="text-lg">💬</span>
          <span>{lang==="zh"?"对话":"Chat"}</span>
        </button>
      </div>

      {/* Wiki selection modal (for non-auto-import scenarios) */}
      <WikiImportModal
        wikiSelection={wikiSelection}
        wikiChecked={wikiChecked}
        setWikiChecked={setWikiChecked}
        batchSave={batchSave}
        setWikiSelection={setWikiSelection}
        wikiDialogRef={wikiDialogRef}
        lang={lang}
      />

      <div ref={bottomRef} />
    </div>
  );
}
