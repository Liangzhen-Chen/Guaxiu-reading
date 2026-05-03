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
      <h1 className="font-display text-7xl font-bold tracking-wide mb-4 text-[#1d1d1f]">
        {lang === "zh" ? "读完书，记得住" : "Read. Retain. Remember."}
      </h1>
      <p className="text-lg text-[#86868b] mb-6 max-w-lg leading-relaxed">
        {lang === "zh"
          ? "AI 陪你逐章对话，追问你、验证你、帮你把知识沉淀下来。"
          : "AI reads with you chapter by chapter — questioning, verifying, and building your knowledge."}
      </p>

      <div className="flex gap-3 mb-20 text-sm text-[#86868b]">
        <span>📖 {lang === "zh" ? "上传即读" : "Upload & read"}</span>
        <span>·</span>
        <span>💬 {lang === "zh" ? "AI追问" : "AI questions"}</span>
        <span>·</span>
        <span>🧠 {lang === "zh" ? "自动Wiki" : "Auto Wiki"}</span>
      </div>

      <Link href={loggedIn ? "/books" : "/login"}
        className="inline-block rounded-full bg-[#1d1d1f] text-white px-10 py-3.5 text-sm font-medium hover:bg-black transition-colors tracking-wide">
        {loggedIn ? (lang === "zh" ? "进入书架 →" : "My Books →") : (lang === "zh" ? "立即开始" : "Get Started")}
      </Link>
      <p className="text-xs text-[#86868b] mt-6">xiugua-reading.cn</p>
    </div>
  );
}
