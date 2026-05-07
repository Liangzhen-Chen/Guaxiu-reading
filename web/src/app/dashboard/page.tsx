"use client";
import { useState, useEffect } from "react";
import { API } from "../config";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : "";

  useEffect(() => { document.title = "分析看板 | 朽瓜"; }, []);
  useEffect(() => {
    fetch(API + "/api/analytics/dashboard?days=7", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return <div className="text-center py-20 text-ink-muted">加载中...</div>;

  const satisfactionRate = data.satisfaction.up + data.satisfaction.down > 0
    ? Math.round(data.satisfaction.up / (data.satisfaction.up + data.satisfaction.down) * 100) + "%"
    : "-";

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="font-display text-2xl font-bold mb-8">分析看板</h1>

      {/* Row 1: Core metrics */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <MetricCard value={data.total_events} label="总事件" />
        <MetricCard value={data.today_events} label="今日事件" highlight />
        <MetricCard value={data.dau} label="DAU" highlight />
        <MetricCard value={data.mau} label="MAU" />
      </div>

      {/* Row 2: Satisfaction + Reading */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <MetricCard value={satisfactionRate} label="满意率" />
        <MetricCard value={data.satisfaction.up} label="👍" color="text-green-600" />
        <MetricCard value={data.satisfaction.down} label="👎" color="text-red-500" />
        <MetricCard value={Math.round(data.today_reading_minutes)} label="今日阅读(分钟)" unit="min" highlight />
      </div>

      {/* Row 3: Reading minutes */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <MetricCard value={Math.round(data.total_reading_minutes)} label="总阅读时长" unit="分钟" />
        <MetricCard value={Math.round(data.today_reading_minutes)} label="今日阅读时长" unit="分钟" highlight />
      </div>

      {/* Event distribution */}
      <div className="mb-8">
        <h2 className="font-semibold mb-3">事件分布</h2>
        <div className="space-y-2">
          {data.events.length === 0 ? (
            <p className="text-sm text-ink-muted">暂无事件</p>
          ) : data.events.map((e: any) => (
            <div key={e.event} className="flex items-center gap-3">
              <span className="text-sm w-36 shrink-0">{e.event}</span>
              <div className="flex-1 h-5 rounded-full bg-[#f5f5f7]">
                <div
                  className="h-5 rounded-full bg-[#1d1d1f] transition-all"
                  style={{ width: `${Math.min((e.count / data.total_events) * 100, 100)}%` }}
                />
              </div>
              <span className="text-sm text-ink-muted w-10 text-right">{e.count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Trend chart (simple text-based) */}
      {data.trend && data.trend.length > 0 && (
        <div className="mb-8">
          <h2 className="font-semibold mb-3">近7天事件趋势</h2>
          <div className="space-y-1">
            {data.trend.map((t: any) => {
              const maxCount = Math.max(...data.trend.map((x: any) => x.count), 1);
              return (
                <div key={t.date} className="flex items-center gap-3">
                  <span className="text-xs text-ink-muted w-24 shrink-0">{t.date.slice(0, 10)}</span>
                  <div className="flex-1 h-4 rounded-full bg-[#f5f5f7]">
                    <div
                      className="h-4 rounded-full bg-amber-400 transition-all"
                      style={{ width: `${(t.count / maxCount) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-ink-muted w-8 text-right">{t.count}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Feedback list */}
      <div className="mb-8">
        <h2 className="font-semibold mb-3">用户反馈</h2>
        {data.feedbacks.length === 0 ? (
          <p className="text-sm text-ink-muted">暂无反馈</p>
        ) : data.feedbacks.map((f: any, i: number) => (
          <div key={i} className="rounded-lg p-3 mb-2 bg-[#f5f5f7] text-sm">
            {f.content}
            <div className="text-xs text-ink-muted mt-1">
              {f.time} {f.contact && "· " + f.contact}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MetricCard({
  value,
  label,
  unit,
  highlight,
  color,
}: {
  value: string | number;
  label: string;
  unit?: string;
  highlight?: boolean;
  color?: string;
}) {
  return (
    <div
      className={`rounded-xl p-4 text-center ${
        highlight ? "bg-[#1d1d1f] text-white" : "bg-[#f5f5f7]"
      }`}
    >
      <div className={`text-2xl font-bold ${color || ""}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
        {unit && <span className="text-xs ml-1 font-normal">{unit}</span>}
      </div>
      <div className={`text-xs mt-1 ${highlight ? "text-white/70" : "text-ink-muted"}`}>
        {label}
      </div>
    </div>
  );
}
