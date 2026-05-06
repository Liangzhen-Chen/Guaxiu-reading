"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLang, t } from "../lang";
import { API } from "../config";

function T() { return typeof window !== "undefined" ? localStorage.getItem("token") || "" : ""; }

export default function ProfilePage() {
  const [user, setUser] = useState<any>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const router = useRouter();
  const { lang } = useLang();

  useEffect(() => { if (!T()) { router.push("/login"); return; } load(); }, []);

  async function load() {
    try {
      const res = await fetch(API + "/api/auth/me", { headers: { Authorization: `Bearer ${T()}` }, signal: AbortSignal.timeout(15000) });
      if (res.ok) { const d = await res.json(); setUser(d); setName(d.display_name || ""); }
      else if (res.status === 401) { localStorage.removeItem("token"); router.push("/login"); }
    } catch {}
  }

  async function saveName() {
    setSaving(true);
    try {
      await fetch(API + "/api/auth/profile", { method: "PUT", headers: { "Content-Type": "application/json", Authorization: `Bearer ${T()}` }, body: JSON.stringify({ display_name: name }), signal: AbortSignal.timeout(15000) });
    } catch {}
    setSaving(false);
  }

  async function uploadAvatar(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    try {
      await fetch(API + "/api/auth/avatar", { method: "POST", headers: { Authorization: `Bearer ${T()}` }, body: fd, signal: AbortSignal.timeout(30000) });
    } catch {}
    load();
  }

  if (!user) return <div className="text-center py-20 text-stone-400"><span className="inline-block w-6 h-6 border-2 border-stone-300 border-t-stone-500 rounded-full animate-spin"></span></div>;

  return (
    <div className="max-w-md mx-auto mt-12">
      <h1 className="font-display text-2xl font-bold mb-8 text-stone-800">{lang === "zh" ? "个人中心" : "Profile"}</h1>

      {/* Avatar */}
      <div className="flex items-center gap-4 mb-8">
        <label className="cursor-pointer">
          <div className="w-20 h-20 rounded-full bg-stone-300 flex items-center justify-center text-2xl font-bold text-stone-500 overflow-hidden">
            {user.avatar_url ? <img src={user.avatar_url} className="w-full h-full object-cover" /> : (user.display_name || "?")[0].toUpperCase()}
          </div>
          <input type="file" accept="image/*" className="hidden" onChange={uploadAvatar} />
        </label>
        <div>
          <p className="text-xs text-stone-400">{lang === "zh" ? "点击更换头像" : "Tap to change"}</p>
        </div>
      </div>

      {/* Nickname */}
      <div className="mb-6">
        <label className="text-xs text-stone-400 mb-1 block">{lang === "zh" ? "昵称" : "Nickname"}</label>
        <div className="flex gap-2">
          <input className="flex-1 rounded-xl px-4 py-2.5 text-sm border border-stone-200 outline-none focus:border-stone-400" value={name} onChange={e => setName(e.target.value)} />
          <button onClick={saveName} disabled={saving} className="cursor-pointer rounded-xl px-4 py-2.5 text-sm font-medium text-white bg-stone-900 hover:bg-black">{saving ? "…" : lang === "zh" ? "保存" : "Save"}</button>
        </div>
      </div>

      {/* Email */}
      <div className="mb-6">
        <label className="text-xs text-stone-400 mb-1 block">{lang === "zh" ? "邮箱" : "Email"}</label>
        <p className="text-sm text-stone-600">{user.email}</p>
      </div>

      {/* Stats */}
      <div className="rounded-2xl bg-stone-50 p-5 mb-6">
        <h3 className="text-sm font-semibold mb-3 text-stone-600">{lang === "zh" ? "账户信息" : "Account"}</h3>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div><span className="text-stone-400">{lang === "zh" ? "注册时间" : "Joined"}</span><p className="text-stone-700">{user.created_at?.split("T")[0]}</p></div>
          <div><span className="text-stone-400">ID</span><p className="text-stone-700 text-xs font-mono">{user.id?.slice(0, 8)}…</p></div>
        </div>
      </div>

      <button onClick={() => { localStorage.removeItem("token"); router.push("/"); }}
        className="cursor-pointer w-full rounded-xl py-2.5 text-sm text-stone-400 border border-stone-200 hover:bg-stone-50 transition-colors">
        {lang === "zh" ? "退出登录" : "Sign Out"}
      </button>
    </div>
  );
}
