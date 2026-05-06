"use client";
import { useState, useEffect } from "react";

type ToastType = "error" | "success" | "info";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

let nextId = 0;
type Listener = (toast: ToastItem) => void;
const listeners = new Set<Listener>();

export function showToast(message: string, type: ToastType = "error") {
  const toast: ToastItem = { id: ++nextId, message, type };
  listeners.forEach((fn) => fn(toast));
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    const listener: Listener = (toast) => {
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, 4000);
    };
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-4 py-3 rounded-xl shadow-lg text-sm font-medium pointer-events-auto animate-in ${
            t.type === "error"
              ? "bg-red-500 text-white"
              : t.type === "success"
                ? "bg-green-600 text-white"
                : "bg-stone-800 text-white"
          }`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
