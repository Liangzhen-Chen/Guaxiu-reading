"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";
import { track } from "../track";

const API = "http://122.51.236.219:8000";

export default function LoginPage() {
  const [email, setEmail] = useState(""); const [pwd, setPwd] = useState("");
  const [err, setErr] = useState(""); const router = useRouter();
  const { lang } = useLang();

  useEffect(() => { track("page_view"); }, []);

  async function submit() {
    if (!email || !pwd) { setErr(t("fillAll", lang)); return; }
    setErr("");
    const res = await fetch(`${API}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: pwd }) });
    if (res.ok) { const d = await res.json(); localStorage.setItem("token", d.access_token); router.push("/books"); }
    else { const d = await res.json(); setErr(d.detail || t("loginFailed", lang)); }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <h1 className="font-display text-2xl font-bold text-center mb-10 text-[#1d1d1f]">{t("login", lang)}</h1>
      {err && <p className="text-sm text-red-500 text-center mb-4">{err}</p>}
      <input className="w-full border-b border-[#d2d2d7] px-1 py-3 text-sm mb-4 placeholder:text-[#86868b]" placeholder={t("email", lang)} value={email} onChange={e => setEmail(e.target.value)} />
      <input className="w-full border-b border-[#d2d2d7] px-1 py-3 text-sm mb-8 placeholder:text-[#86868b]" type="password" placeholder={t("password", lang)} value={pwd} onChange={e => setPwd(e.target.value)} onKeyDown={e => e.key === "Enter" && submit()} />
      <button onClick={submit} className="w-full rounded-full bg-[#1d1d1f] text-white py-3 text-sm font-medium hover:bg-black transition-colors mb-3">{t("login", lang)}</button>
      <div className="text-center text-sm text-[#86868b]">{t("noAccount", lang)}<a href="/register" className="text-[#1d1d1f] underline">{t("register", lang)}</a></div>

      <div className="relative my-8">
        <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-[#d2d2d7]"></div></div>
        <div className="relative flex justify-center"><span className="px-3 text-xs text-[#86868b] bg-white">{lang === "zh" ? "微信用户" : "WeChat Users"}</span></div>
      </div>

      <div className="text-center bg-[#f5f5f7] rounded-xl p-4">
        <p className="text-sm text-[#1d1d1f] mb-1">{lang === "zh" ? "微信小程序登录" : "Login via Mini Program"}</p>
        <p className="text-xs text-[#86868b]">{lang === "zh" ? "搜索「朽瓜」小程序，扫码即可登录" : "Search \"Xiugua\" in WeChat Mini Programs"}</p>
        <p className="text-xs text-[#86868b] mt-1">{lang === "zh" ? "登录后在网页端可绑定邮箱" : "Bind email after login to access on web"}</p>
      </div>
    </div>
  );
}
