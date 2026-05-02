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
      <p className="text-center text-xs text-[#86868b] mt-8">{t("wechatLogin", lang)}</p>
    </div>
  );
}
