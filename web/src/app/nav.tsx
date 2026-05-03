"use client";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useLang, t } from "./lang";

const nonAppPages = ["/", "/login", "/register"];

export function Nav() {
  const [show, setShow] = useState(false);
  const p = usePathname();
  const { lang, setLang } = useLang();

  useEffect(() => { setShow(!!localStorage.getItem("token")); }, [p]);

  return (
    <nav className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
      <a href="/" className="font-display text-lg font-bold text-[#1d1d1f] no-underline">朽瓜 <span className="font-normal text-[#86868b] text-sm">Xiugua</span></a>
      <div className="flex gap-5 text-sm text-[#86868b] items-center">
        {show && <a href="/books" className="hover:text-[#1d1d1f]">{t("bookshelf", lang)}</a>}
        {show && <a href="/wiki" className="hover:text-[#1d1d1f]">{t("wiki", lang)}</a>}
        {!show && p !== "/login" && <a href="/login" className="hover:text-[#1d1d1f]">{t("login", lang)}</a>}
        <button onClick={() => { if (lang !== "zh") { localStorage.setItem("lang", "zh"); window.location.reload(); } }} className={`text-xs px-2 py-0.5 rounded ${lang === "zh" ? "bg-[#1d1d1f] text-white" : "text-[#86868b] hover:text-[#1d1d1f]"}`}>中文</button>
        <button onClick={() => { if (lang !== "en") { localStorage.setItem("lang", "en"); window.location.reload(); } }} className={`text-xs px-2 py-0.5 rounded ${lang === "en" ? "bg-[#1d1d1f] text-white" : "text-[#86868b] hover:text-[#1d1d1f]"}`}>EN</button>
      </div>
    </nav>
  );
}
