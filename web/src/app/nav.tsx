"use client";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { useLang, t } from "./lang";

export function Nav() {
  const p = usePathname();
  const { lang, setLang } = useLang();
  const hasToken = typeof window !== "undefined" && !!localStorage.getItem("token");
  const [show, setShow] = useState(hasToken);

  useEffect(() => { setShow(!!localStorage.getItem("token")); }, [p]);

  return (
    <nav className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
      <Link href="/" className="font-display text-lg font-bold text-ink no-underline">朽瓜 <span className="font-normal text-ink-soft text-sm">Xiugua</span></Link>
      <div className="flex gap-5 text-sm text-ink-soft items-center">
        {show && <Link href="/books" className="text-ink-soft hover:text-ink focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2 rounded">{t("bookshelf", lang)}</Link>}
        {show && <Link href="/wiki" className="text-ink-soft hover:text-ink focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2 rounded">{t("wiki", lang)}</Link>}
        {show && <Link href="/profile" className="text-ink-soft hover:text-ink focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2 rounded">{lang === "zh" ? "我的" : "Me"}</Link>}
        {show && <button onClick={() => { localStorage.removeItem("token"); window.location.href = "/"; }} className="text-ink-soft hover:text-ink focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2 rounded">{lang === "zh" ? "退出" : "Out"}</button>}
        {!show && p !== "/login" && <Link href="/login" className="text-ink-soft hover:text-ink focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2 rounded">{t("login", lang)}</Link>}
        <button onClick={() => { if (lang !== "zh") { localStorage.setItem("lang", "zh"); setLang("zh"); } }} className={`text-xs px-2 py-0.5 rounded-full ${lang === "zh" ? "bg-ink text-white" : "text-ink-soft hover:text-ink"}`}>中文</button>
        <button onClick={() => { if (lang !== "en") { localStorage.setItem("lang", "en"); setLang("en"); } }} className={`text-xs px-2 py-0.5 rounded-full ${lang === "en" ? "bg-ink text-white" : "text-ink-soft hover:text-ink"}`}>EN</button>
      </div>
    </nav>
  );
}
