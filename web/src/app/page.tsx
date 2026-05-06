"use client";
import { useEffect } from "react";
import Link from "next/link";
import { useLang } from "./lang";
import { track } from "./track";

export default function Landing() {
  const { lang } = useLang();
  useEffect(() => { track("page_view"); }, []);
  const loggedIn = typeof window !== "undefined" && localStorage.getItem("token");

  return (
    <div className="min-h-[75vh] flex flex-col items-center justify-center text-center">
      <h1 className="font-display text-7xl font-bold tracking-tight mb-4 text-ink">
        {lang === "zh" ? "读完书，记得住" : "Read. Retain. Remember."}
      </h1>
      <p className="text-lg mb-6 max-w-lg leading-relaxed text-ink-soft">
        {lang === "zh"
          ? "AI 陪你逐章对话，追问你、验证你、帮你把知识沉淀下来。"
          : "AI reads with you chapter by chapter — questioning, verifying, and building your knowledge."}
      </p>

      <div className="flex gap-4 mb-16 text-sm text-ink-muted">
        <span>📖 {lang === "zh" ? "上传即读" : "Upload & read"}</span>
        <span>·</span>
        <span>💬 {lang === "zh" ? "AI追问" : "AI questions"}</span>
        <span>·</span>
        <span>🧠 {lang === "zh" ? "自动Wiki" : "Auto Wiki"}</span>
      </div>

      <Link href={loggedIn ? "/books" : "/login"}
        className="btn btn-primary px-10 py-3.5 text-base tracking-wide focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">
        {loggedIn ? (lang === "zh" ? "进入书架 →" : "My Books →") : (lang === "zh" ? "立即开始" : "Get Started")}
      </Link>
      <p className="text-xs mt-6 text-ink-muted">xiugua-reading.cn · v2026.05.03-ux3</p>
    </div>
  );
}
