"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";
import { track } from "../track";

import { API } from "../config";
function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

export default function BooksPage() {
  const [books, setBooks] = useState<any[]>([]);
  const [upProgress, setUpProgress] = useState(0);
  const [upStatus, setUpStatus] = useState<"" | "uploading" | "done" | "error">("");
  const router = useRouter(); const { lang } = useLang();

  useEffect(() => { track("page_view"); if (!T()) { router.push("/login"); return; } load(); }, []);

  async function api(url: string, opts?: RequestInit) {
    const res = await fetch(url, { ...opts, headers: { ...opts?.headers, Authorization: `Bearer ${T()}` } });
    if (res.status === 401) { localStorage.removeItem("token"); router.push("/login"); }
    return res;
  }
  async function load() {
    const res = await api(API + "/api/books");
    if (res.ok) setBooks((await res.json()).items || []);
  }

  function doUp(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setUpStatus("uploading"); setUpProgress(0);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API + "/api/books/upload");
    xhr.setRequestHeader("Authorization", "Bearer " + T());
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) setUpProgress(Math.round(ev.loaded / ev.total * 100)); };
    xhr.onload = async () => {
      if (xhr.status === 401) { localStorage.removeItem("token"); router.push("/login"); return; }
      if (xhr.status === 201) { setUpStatus("done"); track("book_import", { format: f.name.split(".").pop() }); await load(); }
      else { setUpStatus("error"); }
      setTimeout(() => { setUpStatus(""); setUpProgress(0); }, 3000);
    };
    xhr.onerror = () => { setUpStatus("error"); setTimeout(() => setUpStatus(""), 3000); };
    const fd = new FormData(); fd.append("file", f); fd.append("title", f.name.replace(/\.[^.]+$/, ""));
    xhr.send(fd);
  }

  const [deleting, setDeleting] = useState<string>("");
  async function delBook(id: string, e: React.MouseEvent) {
    e.stopPropagation(); e.preventDefault();
    if (!confirm("确定删除？")) return;
    const res = await fetch(API + "/api/books/" + id, { method: "DELETE", headers: { Authorization: `Bearer ${T()}` } });
    if (res.status === 401) { localStorage.removeItem("token"); router.push("/login"); }
    else if (res.status === 404) { alert("书籍不属于当前账号，请重新登录"); localStorage.removeItem("token"); router.push("/login"); }
    else if (!res.ok) alert("删除失败");
    else load();
  }async function load() {
    const res = await api(API + "/api/books");
    if (res.ok) setBooks((await res.json()).items || []);
  }

  function doUp(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    setUpStatus("uploading"); setUpProgress(0);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API + "/api/books/upload");
    xhr.setRequestHeader("Authorization", "Bearer " + T());
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) setUpProgress(Math.round(ev.loaded / ev.total * 100)); };
    xhr.onload = async () => {
      if (xhr.status === 401) { localStorage.removeItem("token"); router.push("/login"); return; }
      if (xhr.status === 201) { setUpStatus("done"); track("book_import", { format: f.name.split(".").pop() }); await load(); }
      else { setUpStatus("error"); }
      setTimeout(() => { setUpStatus(""); setUpProgress(0); }, 3000);
    };
    xhr.onerror = () => { setUpStatus("error"); setTimeout(() => setUpStatus(""), 3000); };
    const fd = new FormData(); fd.append("file", f); fd.append("title", f.name.replace(/\.[^.]+$/, ""));
    xhr.send(fd);
  }

  const [deleting, setDeleting] = useState<string>("");
  async function delBook(id: string, e: React.MouseEvent) {
    e.stopPropagation(); e.preventDefault();
    if (!confirm("确定删除？")) return;
    const res = await api(API + "/api/books/" + id, { method: "DELETE" });
    if (res.ok) load();
    else if (res.status !== 401) alert("删除失败");
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
        <div className="mb-6 bg-white rounded-xl p-4 border border-stone-200">
          <div className="flex items-center justify-between mb-2"><span className="text-sm font-medium">上传中</span><span className="text-sm text-stone-400">{upProgress}%</span></div>
          <div className="h-3 rounded-full bg-stone-100"><div className="h-3 rounded-full bg-stone-900 transition-all duration-300" style={{ width: `${upProgress}%` }} /></div>
        </div>
      )}

      {books.length === 0 ? (
        <div className="text-center py-24 text-[#86868b]"><p className="text-lg mb-2">{t("noBooks", lang)}</p><p className="text-sm">{t("noBooksHint", lang)}</p></div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {books.map((b: any) => (
            <div key={b.id} onClick={() => router.push(`/read/${b.id}`)} className="group cursor-pointer relative rounded-2xl p-6 bg-[#f5f5f7] hover:bg-[#e8e8ed] transition-colors">
              <button onClick={(e) => delBook(b.id, e)} className="absolute top-2 right-2 text-sm text-stone-400 hover:text-red-500 hover:bg-red-50 rounded-full w-7 h-7 flex items-center justify-center">✕</button>
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
