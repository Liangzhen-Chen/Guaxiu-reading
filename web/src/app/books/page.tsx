"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";
import { track } from "../track";

import { API } from "./config";
function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

export default function BooksPage() {
  const [books, setBooks] = useState<any[]>([]);
  const [upProgress, setUpProgress] = useState(0);
  const [upStatus, setUpStatus] = useState<"" | "uploading" | "done" | "error">("");
  const router = useRouter(); const { lang } = useLang();

  useEffect(() => { track("page_view"); if (!T()) { router.push("/login"); return; } load(); }, []);

  async function load() {
    const res = await fetch(API + "/api/books", { headers: { Authorization: `Bearer ${T()}` } });
    if (res.ok) setBooks((await res.json()).items || []);
    else { localStorage.removeItem("token"); router.push("/login"); }
  }

  async function doUp(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setUpStatus("uploading"); setUpProgress(10);
    try {
      const fd = new FormData(); fd.append("file", f); fd.append("title", f.name.replace(/\.[^.]+$/, ""));
      const res = await fetch(API + "/api/books/upload", { method: "POST", headers: { Authorization: `Bearer ${T()}` }, body: fd });
      if (res.ok) { setUpStatus("done"); track("book_import", { format: f.name.split(".").pop() }); await load(); }
      else { const err = await res.json(); setUpStatus("error"); alert(err.detail || "上传失败"); }
    } catch (e: any) { setUpStatus("error"); alert(e.message || "网络错误"); }
    setTimeout(() => { setUpStatus(""); setUpProgress(0); }, 3000);
  }

  const [deleting, setDeleting] = useState<string>("");
  async function delBook(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (deleting || !confirm("确定删除？")) return;
    setDeleting(id);
    await fetch(API + "/api/books/" + id, { method: "DELETE", headers: { Authorization: `Bearer ${T()}` } });
    setDeleting("");
    load();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-10">
        <h1 className="font-display text-3xl font-bold text-[#1d1d1f]">{t("bookshelf", lang)}</h1>
        <label className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-[#1d1d1f] text-white px-5 py-2 text-sm font-medium hover:bg-black transition-colors">
          {upStatus === "uploading" ? `${upProgress}%` : upStatus === "done" ? "✓ 完成" : upStatus === "error" ? "✕ 失败" : t("importBook", lang)}
          <input type="file" accept=".epub,.pdf,.txt" className="hidden" onChange={doUp} disabled={upStatus === "uploading"} />
        </label>
      </div>

      {upStatus === "uploading" && (
        <div className="mb-6"><div className="h-2 rounded-full bg-[#d2d2d7]"><div className="h-2 rounded-full bg-[#1d1d1f] transition-all duration-300" style={{ width: `${upProgress}%` }} /></div><p className="text-xs text-[#86868b] mt-1">上传中… {upProgress}%</p></div>
      )}

      {books.length === 0 ? (
        <div className="text-center py-24 text-[#86868b]"><p className="text-lg mb-2">{t("noBooks", lang)}</p><p className="text-sm">{t("noBooksHint", lang)}</p></div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {books.map((b: any) => (
            <div key={b.id} onClick={() => router.push(`/read/${b.id}`)} className="group cursor-pointer relative rounded-2xl p-6 bg-[#f5f5f7] hover:bg-[#e8e8ed] transition-colors">
              <button onClick={(e) => delBook(b.id, e)} className="absolute top-3 right-3 text-xs text-[#86868b] hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">✕</button>
              <h3 className="font-semibold mb-1">{b.title}</h3>
              <p className="text-sm text-[#86868b] mb-4">{b.author || "—"} · {b.file_format?.toUpperCase()}</p>
              <div className="h-1 rounded-full bg-[#d2d2d7]"><div className="h-1 rounded-full bg-[#1d1d1f] transition-all" style={{ width: `${b.progress_percent || 0}%` }} /></div>
              <p className="text-xs text-[#86868b] mt-2">{b.progress_status === "completed" ? "已完成" : b.progress_status === "not_started" ? "未开始" : `${b.progress_percent}%`}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
