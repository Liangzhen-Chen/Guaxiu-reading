"use client";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useLang, t } from "./lang";

export function Nav() {
  const [show, setShow] = useState(false);
  const p = usePathname();
  const { lang, setLang } = useLang();

  useEffect(() => { setShow(!!localStorage.getItem("token")); }, [p]);

  return (
    <nav className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
      <Link href="/" className="font-display text-lg font-bold text-[#1d1d1f] no-underline">朽瓜 <span className="font-normal text-[#86868b] text-sm">Xiugua</span></Link>
      <div className="flex gap-5 text-sm text-[#86868b] items-center">
        {show && <Link href="/books" className="hover:text-[#1d1d1f]">{t("bookshelf", lang)}</Link>}
        {show && <Link href="/wiki" className="hover:text-[#1d1d1f]">{t("wiki", lang)}</Link>}
        {show && <Link href="/profile" className="hover:text-[#1d1d1f]">{lang === "zh" ? "我的" : "Me"}</Link>}
        {show && <button onClick={() => { localStorage.removeItem("token"); window.location.href = "/"; }} className="hover:text-[#1d1d1f] text-[#86868b]">{lang === "zh" ? "退出" : "Out"}</button>}
        {!show && p !== "/login" && <Link href="/login" className="hover:text-[#1d1d1f]">{t("login", lang)}</Link>}
        <button onClick={() => { if (lang !== "zh") { localStorage.setItem("lang", "zh"); window.location.reload(); } }} className={`text-xs px-2 py-0.5 rounded ${lang === "zh" ? "bg-[#1d1d1f] text-white" : "text-[#86868b] hover:text-[#1d1d1f]"}`}>中文</button>
        <button onClick={() => { if (lang !== "en") { localStorage.setItem("lang", "en"); window.location.reload(); } }} className={`text-xs px-2 py-0.5 rounded ${lang === "en" ? "bg-[#1d1d1f] text-white" : "text-[#86868b] hover:text-[#1d1d1f]"}`}>EN</button>
      </div>
    </nav>
  );
}
