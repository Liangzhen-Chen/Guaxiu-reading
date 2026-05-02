const API = "http://122.51.236.219:8000";
export function track(event: string, props?: Record<string, any>, durationMs?: number) {
  const page = typeof window !== "undefined" ? window.location.pathname : "";
  fetch(API + "/api/analytics/event", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, page, props, duration_ms: durationMs }),
  }).catch(() => {});
}
