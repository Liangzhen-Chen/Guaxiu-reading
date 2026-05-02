"use client";
import { createContext, useContext, useState, useEffect, ReactNode } from "react";

export type Lang = "zh" | "en";

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "zh", setLang: () => {} });

export function useLang() { return useContext(LangCtx); }

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("zh");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setLang((localStorage.getItem("lang") as Lang) || "zh");
    setReady(true);
  }, []);

  function switchLang(l: Lang) {
    localStorage.setItem("lang", l);
    setLang(l);
  }

  return <LangCtx.Provider value={{ lang, setLang: switchLang }}>{ready ? children : <div />}</LangCtx.Provider>;
}

// Common translations used across pages
const T: Record<string, Record<Lang, string>> = {
  bookshelf: { zh: "书架", en: "Books" },
  wiki: { zh: "Wiki", en: "Wiki" },
  login: { zh: "登录", en: "Sign In" },
  register: { zh: "注册", en: "Register" },
  importBook: { zh: "+ 导入新书", en: "+ Import Book" },
  uploading: { zh: "上传中…", en: "Uploading…" },
  noBooks: { zh: "书架上还没有书", en: "No books yet" },
  noBooksHint: { zh: "点击「导入新书」开始", en: "Click Import to start" },
  notStarted: { zh: "未开始", en: "Not started" },
  completed: { zh: "已完成", en: "Completed" },
  searchConcept: { zh: "搜索概念…", en: "Search concepts…" },
  search: { zh: "搜索", en: "Search" },
  noWiki: { zh: "知识库为空", en: "Wiki is empty" },
  noWikiHint: { zh: "完成导读后，概念会自动沉淀", en: "Complete a reading to see concepts" },
  concept: { zh: "概念", en: "Concept" },
  viewpoint: { zh: "观点", en: "Viewpoint" },
  chapter: { zh: "章", en: "Ch" },
  selectMode: { zh: "选择阅读深度", en: "Choose Depth" },
  quick: { zh: "快速导读", en: "Quick Guide" },
  balanced: { zh: "原文交互", en: "Interactive" },
  deep: { zh: "深度精读", en: "Deep Read" },
  quickDesc: { zh: "AI讲解为主，15分钟/章", en: "AI-led, 15min/ch" },
  balancedDesc: { zh: "原文与对话交替，30分钟/章", en: "Mix text & chat, 30min/ch" },
  deepDesc: { zh: "逐段精读，45分钟/章", en: "Paragraph by paragraph, 45min/ch" },
  confirm: { zh: "确认", en: "Confirm" },
  assessment: { zh: "背景评估", en: "Assessment" },
  send: { zh: "发送", en: "Send" },
  email: { zh: "邮箱", en: "Email" },
  password: { zh: "密码", en: "Password" },
  confirmPassword: { zh: "确认密码", en: "Confirm Password" },
  noAccount: { zh: "还没有账号？", en: "No account? " },
  hasAccount: { zh: "已有账号？", en: "Already have one? " },
  wechatLogin: { zh: "微信用户请扫码登录", en: "WeChat users: scan QR to login" },
  fillAll: { zh: "请填写所有字段", en: "Please fill all fields" },
  passwordMismatch: { zh: "两次密码不一致", en: "Passwords don't match" },
  loginFailed: { zh: "登录失败", en: "Login failed" },
  registerFailed: { zh: "注册失败", en: "Registration failed" },
};
export function t(key: string, lang: Lang): string { return T[key]?.[lang] || key; }
