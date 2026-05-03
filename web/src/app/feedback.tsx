"use client";
import { useState, useEffect } from "react";
import { useLang } from "./lang";

import { API } from "./config";

function FeedbackModal({ open, onClose, lang }: { open: boolean; onClose: () => void; lang: string }) {
  const [msg, setMsg] = useState("");
  const [contact, setContact] = useState("");
  const [sent, setSent] = useState(false);

  async function submit() {
    if (!msg.trim()) return;
    await fetch(API + "/api/analytics/feedback", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: msg, contact: contact || undefined }),
    });
    setSent(true);
    setTimeout(() => { onClose(); setSent(false); setMsg(""); setContact(""); }, 1500);
  }

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20" onClick={onClose}>
      <div className="bg-white rounded-2xl p-6 w-80 shadow-xl" onClick={e => e.stopPropagation()}>
        <h3 className="font-semibold mb-4 text-[#1d1d1f]">{lang === "zh" ? "反馈" : "Feedback"}</h3>
        {sent ? (
          <p className="text-sm text-green-600 text-center py-8">{lang === "zh" ? "感谢反馈！" : "Thanks!"}</p>
        ) : (
          <>
            <textarea className="w-full border border-[#d2d2d7] rounded-lg p-3 text-sm mb-3 h-28 resize-none placeholder:text-[#86868b]" placeholder={lang === "zh" ? "遇到了什么问题？" : "What went wrong?"} value={msg} onChange={e => setMsg(e.target.value)} />
            <input className="w-full border border-[#d2d2d7] rounded-lg p-2 text-sm mb-4 placeholder:text-[#86868b]" placeholder={lang === "zh" ? "联系方式（选填）" : "Contact (optional)"} value={contact} onChange={e => setContact(e.target.value)} />
            <button onClick={submit} className="w-full rounded-full bg-[#1d1d1f] text-white py-2 text-sm font-medium hover:bg-black transition-colors">{lang === "zh" ? "提交" : "Submit"}</button>
          </>
        )}
      </div>
    </div>
  );
}

function SatisfactionPopup({ onRate }: { onRate: (ok: boolean) => void }) {
  const { lang } = useLang();
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
      <div className="bg-white rounded-2xl p-6 w-72 shadow-xl text-center">
        <p className="text-sm mb-4 text-[#1d1d1f]">{lang === "zh" ? "刚才的回答有帮助吗？" : "Was that response helpful?"}</p>
        <div className="flex gap-3 justify-center">
          <button onClick={() => onRate(true)} className="rounded-full bg-[#1d1d1f] text-white px-6 py-2 text-sm font-medium hover:bg-black">👍 {lang === "zh" ? "有用" : "Yes"}</button>
          <button onClick={() => onRate(false)} className="rounded-full border border-[#d2d2d7] text-[#1d1d1f] px-6 py-2 text-sm font-medium hover:bg-[#f5f5f7]">👎 {lang === "zh" ? "没用" : "No"}</button>
        </div>
      </div>
    </div>
  );
}

export function FeedbackButton({ showSatisfaction }: { showSatisfaction?: boolean }) {
  const [open, setOpen] = useState(false);
  const { lang } = useLang();

  return (
    <>
      <button onClick={() => setOpen(true)} className="fixed bottom-6 right-6 text-sm font-medium text-white bg-[#1d1d1f] hover:bg-black rounded-full px-5 py-3 shadow-lg transition-colors">
        {lang === "zh" ? "💬 反馈" : "💬 Feedback"}
      </button>
      <FeedbackModal open={open} onClose={() => setOpen(false)} lang={lang} />
    </>
  );
}

// Hook for satisfaction popup during reading
export function useSatisfactionPopup() {
  const [showPopup, setShowPopup] = useState(false);
  const [callback, setCallback] = useState<((ok: boolean) => void) | null>(null);

  function askSatisfaction(onRated: (ok: boolean) => void) {
    setCallback(() => onRated);
    setShowPopup(true);
  }

  function handleRate(ok: boolean) {
    setShowPopup(false);
    if (callback) callback(ok);
  }

  const Popup = showPopup ? <SatisfactionPopup onRate={handleRate} /> : null;

  return { askSatisfaction, Popup };
}
