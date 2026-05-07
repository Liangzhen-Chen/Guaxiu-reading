"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";

import { API, timeoutSignal } from "../config";

export default function RegisterPage() {
  const [email, setEmail] = useState(""); const [pwd, setPwd] = useState(""); const [pwd2, setPwd2] = useState("");
  const [err, setErr] = useState(""); const router = useRouter();
  const { lang } = useLang();

  useEffect(() => { document.title = lang === "zh" ? "注册 | 朽瓜" : "Register | Xiugua"; }, [lang]);

  async function submit() {
    if (!email || !pwd) { setErr(t("fillAll", lang)); return; }
    if (pwd !== pwd2) { setErr(t("passwordMismatch", lang)); return; }
    setErr("");
    try {
      const res = await fetch(API + "/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password: pwd }),
        signal: timeoutSignal(30000).signal,
      });
      if (res.ok) {
        const d = await res.json().catch(() => ({} as any));
        if (d.access_token) { localStorage.setItem("token", d.access_token); router.push("/books"); return; }
        setErr(t("registerFailed", lang));
      } else {
        const d = await res.json().catch(() => ({} as any));
        const msg = Array.isArray(d.detail) ? d.detail[0]?.msg : (d.detail || "");
        setErr(msg || t("registerFailed", lang));
      }
    } catch {
      setErr("网络连接失败，请检查网络后重试");
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <h1 className="font-display text-2xl font-bold text-center mb-10 text-ink">{t("register", lang)}</h1>
      {err && <p id="reg-error" className="text-sm text-red-500 text-center mb-4" role="alert">{err}</p>}
      <label htmlFor="reg-email" className="sr-only">{t("email", lang)}</label>
      <input id="reg-email" className="w-full border-b border-border px-1 py-3 text-sm mb-4 placeholder:text-ink-soft focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2" placeholder={t("email", lang)} value={email} onChange={e => setEmail(e.target.value)} aria-invalid={err ? "true" : undefined} aria-describedby={err ? "reg-error" : undefined} />
      <label htmlFor="reg-password" className="sr-only">{t("password", lang)}</label>
      <input id="reg-password" className="w-full border-b border-border px-1 py-3 text-sm mb-1 placeholder:text-ink-soft focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2" type="password" placeholder={t("password", lang)} value={pwd} onChange={e => setPwd(e.target.value)} aria-invalid={err ? "true" : undefined} aria-describedby={err ? "reg-error" : undefined} />
      <p className="text-xs text-ink-muted mb-4">{t("至少8位，包含大写字母和数字", "8+ chars, with uppercase & digit")}</p>
      <label htmlFor="reg-password2" className="sr-only">{t("confirmPassword", lang)}</label>
      <input id="reg-password2" className="w-full border-b border-border px-1 py-3 text-sm mb-8 placeholder:text-ink-soft focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2" type="password" placeholder={t("confirmPassword", lang)} value={pwd2} onChange={e => setPwd2(e.target.value)} onKeyDown={e => e.key === "Enter" && submit()} aria-invalid={err ? "true" : undefined} aria-describedby={err ? "reg-error" : undefined} />
      <button onClick={submit} className="cursor-pointer w-full rounded-xl bg-ink text-white py-3 text-sm font-medium hover:bg-black transition-colors mb-3 focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">{t("register", lang)}</button>
      <div className="text-center text-sm text-ink-soft">{t("hasAccount", lang)}<a href="/login" className="text-ink underline focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">{t("login", lang)}</a></div>
    </div>
  );
}
