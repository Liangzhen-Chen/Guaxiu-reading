"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";
import { track } from "../track";

const API = "http://localhost:8000";
function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

export default function BooksPage() {
  const [books, setBooks] = useState<any[]>([]); const [up, setUp] = useState(false);
  const router = useRouter(); const { lang } = useLang();

  useEffect(() => { track("page_view"); if (!T()) { router.push("/login"); return; } load(); }, []);

  async function load() {
    const res = await fetch(API + "/api/books", { headers: { Authorization: `Bearer ${T()}` } });
    if (res.ok) setBooks((await res.json()).items || []);
    else { localStorage.removeItem("token"); router.push("/login"); }
  }

  async function doUp(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return; setUp(true);
    const fd = new FormData(); fd.append("file", f); fd.append("title", f.name.replace(/\.[^.]+$/, ""));
    await fetch(API + "/api/books/upload", { method: "POST", headers: { Authorization: `Bearer ${T()}` }, body: fd });
    track("book_import", { format: f.name.split(".").pop() });
    await load(); setUp(false);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-10">
        <h1 className="font-display text-3xl font-bold text-[#1d1d1f]">{t("bookshelf", lang)}</h1>
        <label className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-[#1d1d1f] text-white px-5 py-2 text-sm font-medium hover:bg-black transition-colors">
          {up ? t("uploading", lang) : t("importBook", lang)}
          <input type="file" accept=".epub,.pdf,.txt" className="hidden" onChange={doUp} disabled={up} />
        </label>
      </div>
      {books.length === 0 ? (
        <div className="text-center py-24 text-[#86868b]"><p className="text-lg mb-2">{t("noBooks", lang)}</p><p className="text-sm">{t("noBooksHint", lang)}</p></div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {books.map((b: any) => (
            <a key={b.id} href={`/read/${b.id}`} className="group block rounded-2xl p-6 bg-[#f5f5f7] hover:bg-[#e8e8ed] transition-colors">
              <h3 className="font-semibold mb-1 group-hover:text-black transition-colors">{b.title}</h3>
              <p className="text-sm text-[#86868b] mb-4">{b.author || "—"} · {b.file_format?.toUpperCase()}</p>
              <div className="h-1 rounded-full bg-[#d2d2d7]"><div className="h-1 rounded-full bg-[#1d1d1f] transition-all" style={{ width: `${b.progress_percent || 0}%` }} /></div>
              <p className="text-xs text-[#86868b] mt-2">{b.progress_status === "completed" ? t("completed", lang) : b.progress_status === "not_started" ? t("notStarted", lang) : `${b.progress_percent}%`}</p>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
