const isLocal = typeof window !== "undefined" && window.location.hostname === "localhost";
export const API = isLocal ? "http://127.0.0.1:8000" : "";
