"use client";
import { useEffect } from "react";
import Link from "next/link";
import { useLang } from "./lang";
import { track } from "./track";

const content = {
  hero: { zh: "读过的书，记得住", en: "Read. Remember. Retain." },
  sub: { zh: "AI 陪你逐章对话，追问、验证、沉淀——把每一本书变成你自己的知识。", en: "AI guides you chapter by chapter, questioning you until you truly understand." },
  steps: [
    { n: "01", zh: "导入", en: "Import", zhD: "上传 ePub、PDF 或 TXT，AI 自动解析全书", enD: "Upload any book, AI parses it instantly" },
    { n: "02", zh: "对话", en: "Discuss", zhD: "AI 逐章追问，用自己的话解释每个概念", enD: "AI questions you chapter by chapter" },
    { n: "03", zh: "沉淀", en: "Build", zhD: "每章概念自动提取，构建你的知识 Wiki", enD: "Auto-build your personal knowledge wiki" },
  ],
  cta: { zh: "立即开始", en: "Get Started" },
};

export default function Landing() {
  const { lang } = useLang();
  useEffect(() => { track("page_view"); }, []);
  const loggedIn = typeof window !== "undefined" && localStorage.getItem("token");
  const c = content;
  return (
    <div className="min-h-[75vh] flex flex-col items-center justify-center text-center">
      <h1 className="font-display text-7xl font-bold tracking-wide mb-4 text-[#1d1d1f]">{c.hero[lang]}</h1>
      <p className="text-lg text-[#86868b] mb-20 max-w-lg leading-relaxed">{c.sub[lang]}</p>

      <div className="grid grid-cols-3 gap-16 max-w-3xl mb-20">
        {c.steps.map(s => (
          <div key={s.n} className="text-left">
            <div className="text-xs font-mono text-[#86868b] mb-2 tracking-widest">{s.n}</div>
            <div className="text-xl font-semibold mb-2 text-[#1d1d1f]">{s[lang]}</div>
            <div className="text-sm text-[#86868b] leading-relaxed">{lang === "zh" ? s.zhD : s.enD}</div>
          </div>
        ))}
      </div>

      <Link href={loggedIn ? "/books" : "/login"} className="inline-block rounded-full bg-[#1d1d1f] text-white px-10 py-3.5 text-sm font-medium hover:bg-black transition-colors tracking-wide">
        {loggedIn ? (lang === "zh" ? "进入书架" : "My Books") : c.cta[lang]}
      </Link>

      <p className="text-xs text-[#86868b] mt-6">xiugua-reading.cn</p>
    </div>
  );
}
