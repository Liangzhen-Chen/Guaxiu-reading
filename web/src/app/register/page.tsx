"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";

const API = "https://xiugua-reading.cn";

export default function RegisterPage() {
  const [email, setEmail] = useState(""); const [pwd, setPwd] = useState(""); const [pwd2, setPwd2] = useState("");
  const [err, setErr] = useState(""); const router = useRouter();
  const { lang } = useLang();

  async function submit() {
    if (!email || !pwd) { setErr(t("fillAll", lang)); return; }
    if (pwd !== pwd2) { setErr(t("passwordMismatch", lang)); return; }
    setErr("");
    const res = await fetch(`${API}/api/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: pwd }) });
    if (res.ok) { const d = await res.json(); localStorage.setItem("token", d.access_token); router.push("/books"); }
    else { const d = await res.json(); setErr(d.detail || t("registerFailed", lang)); }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <h1 className="font-display text-2xl font-bold text-center mb-10 text-[#1d1d1f]">{t("register", lang)}</h1>
      {err && <p className="text-sm text-red-500 text-center mb-4">{err}</p>}
      <input className="w-full border-b border-[#d2d2d7] px-1 py-3 text-sm mb-4 placeholder:text-[#86868b]" placeholder={t("email", lang)} value={email} onChange={e => setEmail(e.target.value)} />
      <input className="w-full border-b border-[#d2d2d7] px-1 py-3 text-sm mb-4 placeholder:text-[#86868b]" type="password" placeholder={t("password", lang)} value={pwd} onChange={e => setPwd(e.target.value)} />
      <input className="w-full border-b border-[#d2d2d7] px-1 py-3 text-sm mb-8 placeholder:text-[#86868b]" type="password" placeholder={t("confirmPassword", lang)} value={pwd2} onChange={e => setPwd2(e.target.value)} onKeyDown={e => e.key === "Enter" && submit()} />
      <button onClick={submit} className="cursor-pointer w-full rounded-full bg-[#1d1d1f] text-white py-3 text-sm font-medium hover:bg-black transition-colors mb-3">{t("register", lang)}</button>
      <div className="text-center text-sm text-[#86868b]">{t("hasAccount", lang)}<a href="/login" className="text-[#1d1d1f] underline">{t("login", lang)}</a></div>
    </div>
  );
}
