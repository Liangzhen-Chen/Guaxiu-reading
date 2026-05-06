const isLocal = typeof window !== "undefined" && window.location.hostname === "localhost";
// 生产环境走 Vercel rewrite 代理（避免海外直连丢包）
// next.config.ts 将 /api/* 转发到 ECS
export const API = isLocal ? "http://127.0.0.1:8000" : "";
