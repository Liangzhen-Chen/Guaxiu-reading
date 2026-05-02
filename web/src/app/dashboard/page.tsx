"use client";
import { useState, useEffect } from "react";
const API = "https://api.xiugua-reading.cn";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : "";

  useEffect(() => {
    fetch(API + "/api/analytics/dashboard", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json()).then(setData);
  }, []);

  if (!data) return <div className="text-center py-20 text-stone-400">加载中…</div>;

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="font-display text-2xl font-bold mb-8">分析看板</h1>

      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="rounded-xl p-4 bg-[#f5f5f7] text-center"><div className="text-2xl font-bold">{data.total_events}</div><div className="text-xs text-stone-400 mt-1">总事件</div></div>
        <div className="rounded-xl p-4 bg-[#f5f5f7] text-center"><div className="text-2xl font-bold text-green-600">{data.satisfaction.up}</div><div className="text-xs text-stone-400 mt-1">👍</div></div>
        <div className="rounded-xl p-4 bg-[#f5f5f7] text-center"><div className="text-2xl font-bold text-red-500">{data.satisfaction.down}</div><div className="text-xs text-stone-400 mt-1">👎</div></div>
        <div className="rounded-xl p-4 bg-[#f5f5f7] text-center"><div className="text-2xl font-bold">{data.satisfaction.up + data.satisfaction.down > 0 ? Math.round(data.satisfaction.up / (data.satisfaction.up + data.satisfaction.down) * 100) + "%" : "-"}</div><div className="text-xs text-stone-400 mt-1">满意率</div></div>
      </div>

      <div className="mb-8">
        <h2 className="font-semibold mb-3">事件分布</h2>
        <div className="space-y-2">
          {data.events.map((e: any) => (
            <div key={e.event} className="flex items-center gap-3">
              <span className="text-sm w-32">{e.event}</span>
              <div className="flex-1 h-5 rounded-full bg-[#f5f5f7]"><div className="h-5 rounded-full bg-[#1d1d1f]" style={{ width: `${(e.count / data.total_events * 100)}%` }} /></div>
              <span className="text-sm text-stone-400 w-10 text-right">{e.count}</span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="font-semibold mb-3">用户反馈</h2>
        {data.feedbacks.length === 0 ? <p className="text-sm text-stone-400">暂无反馈</p> : data.feedbacks.map((f: any, i: number) => (
          <div key={i} className="rounded-lg p-3 mb-2 bg-[#f5f5f7] text-sm">{f.content}<div className="text-xs text-stone-400 mt-1">{f.time} {f.contact && "· " + f.contact}</div></div>
        ))}
      </div>
    </div>
  );
}
