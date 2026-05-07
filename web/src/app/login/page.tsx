"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";
import { track } from "../track";

import { API, timeoutSignal } from "../config";

export default function LoginPage() {
  const [email, setEmail] = useState(""); const [pwd, setPwd] = useState("");
  const [err, setErr] = useState(""); const router = useRouter();
  const { lang } = useLang();

  useEffect(() => { track("page_view"); }, []);
  useEffect(() => { document.title = lang === "zh" ? "登录 | 朽瓜" : "Sign In | Xiugua"; }, [lang]);

  async function submit() {
    if (!email || !pwd) { setErr(t("fillAll", lang)); return; }
    setErr("");
    try {
      const res = await fetch(API + "/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password: pwd }),
        signal: timeoutSignal(30000).signal,
      });
      if (res.ok) {
        const d = await res.json().catch(() => ({} as any));
        if (d.access_token) { localStorage.setItem("token", d.access_token); router.push("/books"); return; }
        setErr(t("loginFailed", lang));
      } else {
        const d = await res.json().catch(() => ({} as any));
        const msg = Array.isArray(d.detail) ? d.detail[0]?.msg : (d.detail || "");
        setErr(msg || t("loginFailed", lang));
      }
    } catch {
      setErr("网络连接失败，请检查网络后重试");
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <h1 className="font-display text-2xl font-bold text-center mb-10 text-ink">{t("login", lang)}</h1>
      {err && <p id="login-error" className="text-sm text-red-500 text-center mb-4" role="alert">{err}</p>}
      <label htmlFor="login-email" className="sr-only">{t("email", lang)}</label>
      <input id="login-email" className="w-full border-b border-border px-1 py-3 text-sm mb-4 placeholder:text-ink-soft focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2" placeholder={t("email", lang)} value={email} onChange={e => setEmail(e.target.value)} aria-invalid={err ? "true" : undefined} aria-describedby={err ? "login-error" : undefined} />
      <label htmlFor="login-password" className="sr-only">{t("password", lang)}</label>
      <input id="login-password" className="w-full border-b border-border px-1 py-3 text-sm mb-8 placeholder:text-ink-soft focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2" type="password" placeholder={t("password", lang)} value={pwd} onChange={e => setPwd(e.target.value)} onKeyDown={e => e.key === "Enter" && submit()} aria-invalid={err ? "true" : undefined} aria-describedby={err ? "login-error" : undefined} />
      <button onClick={submit} className="cursor-pointer w-full rounded-xl bg-ink text-white py-3 text-sm font-medium hover:bg-black transition-colors mb-3 focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">{t("login", lang)}</button>
      <div className="text-center text-sm text-ink-soft">{t("noAccount", lang)}<a href="/register" className="text-ink underline focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2">{t("register", lang)}</a></div>

      <div className="relative my-8">
        <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-border"></div></div>
        <div className="relative flex justify-center"><span className="px-3 text-xs text-ink-soft bg-white">{lang === "zh" ? "微信用户" : "WeChat Users"}</span></div>
      </div>

      <div className="text-center bg-[#f5f5f7] rounded-xl p-4">
        <p className="text-sm text-ink mb-1">{lang === "zh" ? "微信小程序登录" : "Login via Mini Program"}</p>
        <p className="text-xs text-ink-soft">{lang === "zh" ? "搜索「朽瓜」小程序，扫码即可登录" : "Search \"Xiugua\" in WeChat Mini Programs"}</p>
        <p className="text-xs text-ink-soft mt-1">{lang === "zh" ? "登录后在网页端可绑定邮箱" : "Bind email after login to access on web"}</p>
      </div>
    </div>
  );
}
