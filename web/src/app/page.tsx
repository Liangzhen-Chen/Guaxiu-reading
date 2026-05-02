"use client";
import { useEffect } from "react";
import Link from "next/link";
import { useLang } from "./lang";
import { track } from "./track";

const content = {
  title: { zh: "朽瓜", en: "Xiugua" },
  subtitle: { zh: "AI 陪你读书", en: "Read with AI" },
  sub2: { zh: "追问、验证、沉淀", en: "Question, Verify, Retain" },
  steps: [
    { n: "01", zh: "导入", en: "Import", zhD: "上传 ePub、PDF 或 TXT", enD: "Upload ePub, PDF, or TXT" },
    { n: "02", zh: "对话", en: "Discuss", zhD: "AI 逐章追问，帮你理清思路", enD: "AI questions you chapter by chapter" },
    { n: "03", zh: "沉淀", en: "Build", zhD: "自动搭建你的知识库", enD: "Auto-build your knowledge wiki" },
  ],
  cta: { zh: "立即开始", en: "Get Started" },
};

export default function Landing() {
  const { lang } = useLang();
  useEffect(() => { track("page_view"); }, []);
  const c = content;
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center">
      <h1 className="font-display text-6xl font-bold tracking-wide mb-6 text-[#1d1d1f]">{c.title[lang]}</h1>
      <p className="text-xl text-[#86868b] mb-16 max-w-md leading-relaxed">{c.subtitle[lang]}<br/>{c.sub2[lang]}</p>
      <div className="grid grid-cols-3 gap-12 max-w-2xl mb-16 text-left">
        {c.steps.map(s => (
          <div key={s.n}><div className="text-xs text-[#86868b] mb-2">{s.n}</div><div className="font-semibold mb-1 text-[#1d1d1f]">{s[lang as "zh" | "en"]}</div><div className="text-sm text-[#86868b]">{lang === "zh" ? s.zhD : s.enD}</div></div>
        ))}
      </div>
      <Link href="/login" className="inline-block rounded-full bg-[#1d1d1f] text-white px-8 py-3 text-sm font-medium hover:bg-black transition-colors">{c.cta[lang]}</Link>
    </div>
  );
}
