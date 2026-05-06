"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";
import { track } from "../track";

import { API, timeoutSignal } from "../config";
import { showToast } from "../toast";
function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

export default function BooksPage() {
  const [books, setBooks] = useState<any[]>([]);
  const [upProgress, setUpProgress] = useState(0);
  const [upStatus, setUpStatus] = useState<"" | "uploading" | "done" | "error">("");
  const [upStep, setUpStep] = useState("");
  const [loading, setLoading] = useState(true);
  const router = useRouter(); const { lang } = useLang();

  useEffect(() => { track("page_view"); if (!T()) { router.push("/login"); return; } load(); }, []);
  // Bug B1 fix: compute needsPoll as a derived value via useMemo
  const needsPoll = useMemo(() => {
    return books.some((b: any) => {
      if (b.parse_status === "pending" || b.parse_status === "parsing") return true;
      if (b.preprocess_status === "processing") return true;
      const pp = b.preprocess_progress || {};
      return pp.total_chapters > 0 && (pp.completed_chapters || 0) < pp.total_chapters;
    });
  }, [books]);
  useEffect(() => {
    if (!needsPoll) return;
    const t = setInterval(() => load(), 3000);
    return () => clearInterval(t);
  }, [needsPoll]);

  async function api(url: string, opts?: RequestInit) {
    try {
      const topts = timeoutSignal(30000);
      const res = await fetch(url, { ...opts, signal: topts.signal, headers: { ...opts?.headers, Authorization: `Bearer ${T()}` } });
      topts.clear();
      if (res.status === 401) { localStorage.removeItem("token"); router.push("/login"); }
      return res;
    } catch {
      return { ok: false, status: 0 } as Response;
    }
  }
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function load() {
    const t0 = performance.now();
    for (let i = 0; i < 3; i++) {
      if (!mounted.current) return;
      const t1 = performance.now();
      const res = await api(API + "/api/books");
      console.log(`[books] fetch ${i+1}: ${(performance.now()-t1).toFixed(0)}ms, ok=${res.ok}, status=${res.status}`);
      if (res.ok) { setBooks((await res.json()).items || []); console.log(`[books] total: ${(performance.now()-t0).toFixed(0)}ms`); break; }
      if (i < 2) await new Promise(r => setTimeout(r, 1000));
    }
    if (mounted.current) setLoading(false);
  }

  async function doUp(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setUpStatus("uploading"); setUpProgress(0);
    try {
      // Step 1: 获取 COS 预签名上传 URL
      setUpStep("获取上传地址...");
      const presignRes = await api(API + "/api/books/presign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: f.name, file_type: f.name.split(".").pop() || "epub" }),
      });
      // api() returns {ok:false,status:0} on network errors
      if (presignRes.status === 0) {
        setUpStatus("error"); setTimeout(() => setUpStatus(""), 3000); resetInput();
        showToast("网络连接失败，请检查网络后重试", "error");
        return;
      }
      if (!presignRes.ok) {
        const msg = await (presignRes as Response).text().catch(() => "");
        setUpStatus("error"); setTimeout(() => setUpStatus(""), 3000); resetInput();
        showToast("上传配置失败: " + (msg || "请稍后重试"), "error");
        return;
      }
      const { upload_url, key } = await (presignRes as Response).json();

      // Step 2: 直传 COS（带进度条）
      setUpStep("上传中");
      const xhr = new XMLHttpRequest();
      xhr.timeout = 600000;
      xhr.open("PUT", upload_url);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) setUpProgress(Math.round(ev.loaded / ev.total * 100));
      };
      await new Promise<void>((resolve, reject) => {
        xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error("上传失败 " + xhr.status));
        xhr.onerror = () => reject(new Error("网络错误"));
        xhr.ontimeout = () => reject(new Error("上传超时"));
        xhr.send(f);
      });

      // Step 3: 通知后端从 COS 导入
      setUpStep("导入中...");
      setUpProgress(0);
      const importRes = await api(API + "/api/books/import-cos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, filename: f.name, title: f.name.replace(/\.[^.]+$/, "") }),
      });
      if (importRes.status === 401) { localStorage.removeItem("token"); router.push("/login"); return; }
      if (importRes.status === 0) {
        setUpStatus("error"); setTimeout(() => setUpStatus(""), 3000); resetInput();
        showToast("网络连接失败，文件已上传但导入失败，请刷新页面重试", "error");
        return;
      }
      if (importRes.ok) {
        setUpStatus("done"); track("book_import", { format: f.name.split(".").pop() }); await load();
      } else {
        setUpStatus("error");
        try { const d = JSON.parse(await (importRes as Response).text()); showToast(d.detail || "导入失败", "error"); } catch(_) { showToast("导入失败", "error"); }
      }
      setTimeout(() => { setUpStatus(""); setUpProgress(0); }, 3000);
      resetInput();
    } catch (err: any) {
      setUpStatus("error");
      showToast(err.message || "上传失败，请检查网络后重试", "error");
      setTimeout(() => setUpStatus(""), 3000);
      resetInput();
    }
  }

  function resetInput() {
    const el = document.querySelector<HTMLInputElement>('input[type="file"][accept*=".epub"]');
    if (el) el.value = "";
  }

  const [deleting, setDeleting] = useState<string>("");
  const [preprocessLoading, setPreprocessLoading] = useState(false);
  async function startPreprocess(id: string) {
    if (preprocessLoading) return;
    setPreprocessLoading(true);
    try {
      const res = await api(API + "/api/books/" + id + "/preprocess", { method: "POST" });
      if (res.ok) { await load(); }
      else {
        const msg = await res.text().catch(() => "");
        showToast(msg || "AI帮你读启动失败，请稍后重试", "error");
      }
    } catch {
      showToast("网络错误，请稍后重试", "error");
    }
    setPreprocessLoading(false);
  }
  async function delBook(id: string, e: React.MouseEvent) {
    e.stopPropagation(); e.preventDefault();
    if (!confirm("确定删除？")) return;
    setDeleting(id);
    try {
      const res = await api(API + "/api/books/" + id, { method: "DELETE" });
      if (res.ok) { load(); }
      else if (res.status === 404) { showToast("书籍不属于当前账号", "error"); localStorage.removeItem("token"); router.push("/login"); }
      else if (res.status !== 401) { showToast("删除失败，请稍后重试", "error"); }
    } catch {
      showToast("网络错误，请检查后端是否运行", "error");
    }
    setDeleting("");
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-10">
        <h1 className="font-display text-3xl font-bold text-[#1d1d1f]">{t("bookshelf", lang)}</h1>
        <label className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-[#1d1d1f] text-white px-5 py-2 text-sm font-medium hover:bg-black transition-colors">
          {upStatus === "uploading" ? (upStep === "获取上传地址..." || upStep === "导入中..." ? upStep : `${upProgress}%`) : upStatus === "done" ? "✓ 完成" : upStatus === "error" ? "✕ 失败" : t("importBook", lang)}
          <input type="file" accept=".epub,.pdf,.txt" className="hidden" onChange={doUp} disabled={upStatus === "uploading"} />
        </label>
      </div>

      {upStatus === "uploading" && (
        <div className="mb-6 bg-white rounded-xl p-4 border border-stone-200">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">{upStep || "上传中"}</span>
            <span className="text-sm text-stone-400">{upStep === "上传中" ? `${upProgress}%` : upStep === "获取上传地址..." ? "" : upStep === "导入中..." ? "" : `${upProgress}%`}</span>
          </div>
          {upStep === "上传中" && (
            <div className="h-3 rounded-full bg-stone-100">
              <div className="h-3 rounded-full bg-stone-900 transition-all duration-300" style={{ width: `${upProgress}%` }} />
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="text-center py-24 text-[#86868b]"><span className="inline-block w-6 h-6 border-2 border-stone-300 border-t-stone-500 rounded-full animate-spin"></span></div>
      ) : books.length === 0 ? (
        <div className="text-center py-24 text-[#86868b]"><p className="text-lg mb-2">{t("noBooks", lang)}</p><p className="text-sm">{t("noBooksHint", lang)}</p></div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {books.map((b: any) => {
            const parsing = b.parse_status === "pending" || b.parse_status === "parsing";
            const preprocessing = b.preprocess_status === "processing";
            const ready = b.preprocess_status === "ready";
            const isReading = b.progress_status !== "not_started" && b.progress_status !== null;
            const ppProgress = b.preprocess_progress || {};
            const ppDone = ppProgress.completed_chapters || 0;
            const ppTotal = ppProgress.total_chapters || b.chapter_count || 0;
            const ppIncomplete = ppTotal > 0 && ppDone < ppTotal;
            const ppAllDone = ppTotal > 0 && ppDone >= ppTotal;

            return (
            <div key={b.id}
              onClick={() => {
                if (!parsing && !preprocessing) {
                  if (ready || isReading) router.push(`/read/${b.id}`);
                }
              }}
              className={`group relative rounded-2xl p-6 transition-colors ${(parsing || preprocessing) ? "bg-[#f5f5f7] cursor-default" : "bg-[#f5f5f7] hover:bg-[#e8e8ed] cursor-pointer"}`}>
              <button onClick={(e) => delBook(b.id, e)} className="absolute top-2 right-2 text-sm text-stone-400 hover:text-red-500 hover:bg-red-50 rounded-full w-7 h-7 flex items-center justify-center z-10">✕</button>
              <h3 className={`font-semibold mb-1 ${parsing ? "text-stone-400" : ""}`}>{b.title}</h3>
              <p className="text-sm text-[#86868b] mb-2">{b.author || "—"} · {b.file_format?.toUpperCase()}</p>

              {/* One-liner from P1 */}
              {b.one_liner && !parsing && !preprocessing && (
                <p className="text-xs text-[#86868b] italic mb-3 border-t border-b border-stone-200 py-2">{b.one_liner}</p>
              )}

              {parsing ? (
                <div className="flex items-center gap-2 text-xs text-stone-400">
                  <span className="inline-block w-4 h-4 border-2 border-stone-300 border-t-stone-500 rounded-full animate-spin"></span>
                  {b.parse_status === "pending" ? "排队中…" : "解析中…"}
                </div>
              ) : b.parse_status === "failed" ? (
                <div className="text-xs text-red-400">解析失败 {b.parse_error ? `: ${b.parse_error.slice(0, 40)}` : ""}</div>
              ) : preprocessing || (ready && ppIncomplete) ? (
                <div>
                  <div className="h-1.5 rounded-full bg-stone-200 mb-1"><div className="h-1.5 rounded-full bg-stone-600 transition-all" style={{width: ppTotal>0?`${Math.round(ppDone/ppTotal*100)}%`:'20%'}}/></div>
                  <p className="text-xs text-stone-400">AI 正在阅读 第{ppDone}/{ppTotal}章</p>
                  {ready && <p className="text-xs text-stone-400 mt-1">{lang==="zh"?"前两章已完成，可开始阅读":"First 2 chapters ready"}</p>}
                </div>
              ) : !ready && !isReading ? (
                <button onClick={(e) => { e.stopPropagation(); startPreprocess(b.id); }}
                  disabled={preprocessLoading}
                  className="w-full cursor-pointer rounded-lg py-2 text-xs font-medium bg-[#1d1d1f] text-white hover:bg-black disabled:opacity-50 transition-colors mt-1">
                  {preprocessLoading ? "启动中…" : "AI 帮你读 →"}
                </button>
              ) : (
                <div>
                  {isReading && (
                    <div className="h-1 rounded-full bg-[#d2d2d7] mb-1"><div className="h-1 rounded-full bg-[#1d1d1f]" style={{width:`${b.progress_percent||0}%`}}/></div>
                  )}
                  {ppAllDone && !isReading && (
                    <div className="flex items-center gap-1 mb-1"><span className="text-xs text-green-600">AI 已读完</span></div>
                  )}
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-stone-400">{b.progress_status === "completed" ? "已完成" : isReading ? `${b.progress_percent}%` : ppAllDone ? `${ppTotal}章已解析` : `第${ppDone}/${ppTotal}章已解析`}</span>
                    {ready && !isReading && (
                      <span className="text-xs font-medium text-white bg-[#1d1d1f] px-3 py-1 rounded-full">开始阅读</span>
                    )}
                    {isReading && (
                      <span className="text-xs text-stone-400 border border-stone-200 px-3 py-1 rounded-full">继续阅读</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )})}
        </div>
      )}
    </div>
  );
}
