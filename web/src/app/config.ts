const host = typeof window !== "undefined" ? window.location.hostname : "";
const isLocal = host === "localhost" || host === "127.0.0.1" || host.startsWith("192.168.");
// 生产环境走 Vercel rewrite 代理（避免海外直连丢包）
// next.config.ts 将 /api/* 转发到 ECS
export const API = isLocal ? "http://127.0.0.1:8000" : "";

/**
 * Cross-browser AbortSignal.timeout fallback.
 * Older browsers (some Chromium 89-, Safari 14-) do not support AbortSignal.timeout().
 * Uses AbortController + setTimeout as a polyfill when needed.
 */
export function timeoutSignal(ms: number): { signal: AbortSignal; clear: () => void } {
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    try {
      return { signal: AbortSignal.timeout(ms), clear: () => {} };
    } catch {
      // fall through to fallback
    }
  }
  // Fallback: AbortController + setTimeout for older browsers
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), ms);
  return {
    signal: controller.signal,
    clear: () => clearTimeout(timer),
  };
}
