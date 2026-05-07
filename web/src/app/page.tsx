"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useLang } from "./lang";
import { track } from "./track";
import { API } from "./config";

/* ------------------------------------------------------------------ */
/*  Scroll-reveal hook — keeps hero visible, reveals below-fold on    */
/*  scroll. Respects prefers-reduced-motion.                          */
/* ------------------------------------------------------------------ */
function useScrollReveal(threshold = 0.12) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  const prefersMotion = useRef(true);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    prefersMotion.current = !mq.matches;
  }, []);

  useEffect(() => {
    if (!prefersMotion.current) return;
    const el = ref.current;
    if (!el) return;

    // If already near the viewport, keep visible; otherwise hide.
    const rect = el.getBoundingClientRect();
    const isNearViewport = rect.top < window.innerHeight * 0.85;
    if (!isNearViewport) {
      setVisible(false);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold, rootMargin: "0px 0px -48px 0px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);

  return [ref, visible] as const;
}

function RevealWrap({
  children,
  className = "",
  delay = 0,
  as: Tag = "div",
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "section";
}) {
  const [ref, visible] = useScrollReveal();
  return (
    <Tag
      ref={ref}
      className={`transition-all duration-700 ease-out will-change-transform ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-8"
      } ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </Tag>
  );
}

/* ------------------------------------------------------------------ */
/*  Feature / step data                                               */
/* ------------------------------------------------------------------ */

interface Feature {
  title_zh: string;
  title_en: string;
  desc_zh: string;
  desc_en: string;
}

const features: Feature[] = [
  {
    title_zh: "AI 主动引导",
    title_en: "AI-Guided Dialogue",
    desc_zh:
      "不是你在搜索答案，而是 AI 像导师一样追问你、验证你的理解。每一次对话都是思考的深化，而不是信息的快速消费。",
    desc_en:
      "Instead of you searching for answers, AI questions and verifies your understanding like a mentor. Each conversation deepens your thinking.",
  },
  {
    title_zh: "Wiki 知识沉淀",
    title_en: "Wiki Knowledge Base",
    desc_zh:
      "每读一章，AI 自动提取概念、建立关联。读完一本书，留下的不是零散笔记，而是一座结构化的个人 Wiki 知识库。",
    desc_en:
      "After each chapter, AI extracts concepts and builds connections. You finish a book not with scattered notes, but with a structured personal Wiki.",
  },
  {
    title_zh: "逐章拆解深入",
    title_en: "Chapter by Chapter",
    desc_zh:
      "不赶进度，不跳内容。一章一章深入讨论，每个概念吃透再进入下一章。阅读不是速度竞赛，而是理解的积累。",
    desc_en:
      "No rush, no skipping. Deep discussion chapter by chapter. Master each concept before moving on. Reading is not a speed contest.",
  },
  {
    title_zh: "概览 / 精读双模式",
    title_en: "Overview & Deep Mode",
    desc_zh:
      "快速概览模式五分钟把握一章全貌；深度精读模式沉浸式逐句追问。同一本书，两种节奏，适配你的每一种阅读状态。",
    desc_en:
      "Quick overview mode captures the essence in minutes; deep reading mode immerses you in every sentence. One book, two paces.",
  },
];

interface Step {
  num: number;
  title_zh: string;
  title_en: string;
  desc_zh: string;
  desc_en: string;
}

const steps: Step[] = [
  {
    num: 1,
    title_zh: "上传你的书",
    title_en: "Upload Your Book",
    desc_zh: "支持 ePub / PDF / TXT 格式，上传即自动解析章节结构。",
    desc_en: "Upload ePub, PDF, or TXT — chapters are parsed automatically.",
  },
  {
    num: 2,
    title_zh: "AI 预解析生成 Wiki",
    title_en: "AI Parses & Generates Wiki",
    desc_zh:
      "AI 自动识别每章核心概念，预生成 Wiki 概念清单，为深度对话做好准备。",
    desc_en:
      "AI identifies key concepts in each chapter and pre-generates a Wiki entry list, ready for deep dialogue.",
  },
  {
    num: 3,
    title_zh: "逐章对话，开始阅读",
    title_en: "Start Reading Chapter by Chapter",
    desc_zh:
      "从第一章开始，AI 带着你逐概念对话——追问、验证、总结。读完即沉淀。",
    desc_en:
      "From chapter one, AI dialogues with you concept by concept — questioning, verifying, summarizing. Read and retain.",
  },
];

/* ------------------------------------------------------------------ */
/*  Main landing component                                            */
/* ------------------------------------------------------------------ */
export default function Landing() {
  const { lang } = useLang();
  const [continueInfo, setContinueInfo] = useState<{
    title: string;
    chapter: number;
    bookId: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    document.title = "朽瓜 — AI 带着你读书";
  }, []);

  useEffect(() => {
    track("page_view");
  }, []);

  const loggedIn =
    typeof window !== "undefined" && localStorage.getItem("token");

  // Fetch "continue reading" info for logged-in users
  useEffect(() => {
    if (!loggedIn) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoading(false);
      return;
    }
    const token = localStorage.getItem("token") || "";
    (async () => {
      try {
        const res = await fetch(`${API}/api/books`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(10000),
        });
        if (!res.ok) {
          setLoading(false);
          return;
        }
        const books = await res.json();
        if (!Array.isArray(books) || books.length === 0) {
          setLoading(false);
          return;
        }
        const active = books.find(
          (b: { status: string; current_chapter?: number }) =>
            b.status === "reading" || b.status === "paused"
        );
        if (active && active.current_chapter > 0) {
          setContinueInfo({
            title: active.title || active.book_title || "",
            chapter: active.current_chapter || 1,
            bookId: active.id || active.book_id || "",
          });
        }
        setLoading(false);
      } catch {
        setLoading(false);
      }
    })();
  }, [loggedIn]);

  const t = (zh: string, en: string) => (lang === "zh" ? zh : en);

  /* ---- CTA button ---- */
  const renderCTA = (size: "default" | "large" = "default") => {
    const base =
      "btn btn-primary inline-flex items-center gap-2 " +
      "focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:ring-offset-2 " +
      (size === "large"
        ? "px-10 py-4 text-base tracking-wide"
        : "px-8 py-3 text-sm");

    if (loading) return null;

    if (loggedIn && continueInfo) {
      return (
        <Link href={`/read/${continueInfo.bookId}`} className={base}>
          <span>
            {t(
              `继续阅读《${continueInfo.title}》第 ${continueInfo.chapter} 章`,
              `Continue "${continueInfo.title}" Ch ${continueInfo.chapter}`
            )}
          </span>
          <span className="link-arrow">&rarr;</span>
        </Link>
      );
    }

    return (
      <Link href={loggedIn ? "/books" : "/login"} className={base}>
        <span>
          {loggedIn
            ? t("进入书架", "My Books")
            : t("开始你的第一本书", "Start Your First Book")}
        </span>
        <span className="link-arrow">&rarr;</span>
      </Link>
    );
  };

  /* ---- Feature cards (render twice — zh & en will differ) ---- */
  const renderFeatureCards = () => (
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
      {features.map((f, i) => (
        <div
          key={i}
          className="feature-card card p-6 md:p-7 flex flex-col gap-3 cursor-default"
        >
          <span className="section-rule" />
          <h3 className="font-display text-xl font-bold tracking-tight text-ink">
            {t(f.title_zh, f.title_en)}
          </h3>
          <p className="text-sm leading-relaxed text-ink-soft">
            {t(f.desc_zh, f.desc_en)}
          </p>
        </div>
      ))}
    </div>
  );

  /* ---- Steps ---- */
  const renderSteps = () => (
    <div className="flex flex-col md:flex-row gap-8 md:gap-6 lg:gap-10 items-start">
      {steps.map((s, i) => (
        <div key={i} className="flex-1 flex gap-4 md:flex-col md:text-center md:items-center">
          <div className="step-num">{s.num}</div>
          <div className="flex flex-col gap-1.5 md:items-center">
            <h3 className="font-display text-lg font-bold tracking-tight text-ink">
              {t(s.title_zh, s.title_en)}
            </h3>
            <p className="text-sm leading-relaxed text-ink-soft max-w-[260px] md:mx-auto">
              {t(s.desc_zh, s.desc_en)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );

  /* ================================================================ */
  /*  RENDER                                                          */
  /* ================================================================ */
  return (
    <div className="overflow-hidden">
      {/* ---- HERO ---- */}
      <section className="hero-glow relative pt-8 pb-12 md:pt-16 md:pb-20">
        <div className="relative z-10 max-w-6xl mx-auto">
          {/* Warm label */}
          <div className="text-center md:text-left mb-6">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium text-amber-deep bg-surface-amber/70">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-deep/60" />
              {t("AI 苏格拉底式阅读", "AI Socratic Reading")}
            </span>
          </div>

          <div className="flex flex-col md:flex-row gap-8 md:gap-12 items-start">
            {/* LEFT: Title + Pain points + Selling points */}
            <div className="flex-1 min-w-0">
              <h1 className="font-display text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight text-ink leading-[1.15]">
                {t("不是你看书，是 AI 带着你读", "You Don't Read Alone — AI Reads With You")}
              </h1>
              <p className="mt-4 text-sm sm:text-base md:text-lg leading-relaxed text-ink-soft">
                {t(
                  "苏格拉底式追问，逐章拆解。读过的每一本书，沉淀为你的个人 Wiki 知识库。",
                  "Socratic questioning, chapter by chapter. Every book you read becomes your personal Wiki knowledge base."
                )}
              </p>

              {/* Pain points + Selling points side by side on mobile-stacked */}
              <div className="mt-6 flex flex-col sm:flex-row gap-4 sm:gap-8">
                {/* Pain points */}
                <div className="flex-1 space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted mb-2">
                    {t("你是否有这些困扰", "Sound Familiar?")}
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { zh: "读完就忘，不知道留下了什么", en: "Finish a book, remember nothing" },
                      { zh: "一个人读没人反馈，理解对错不知道", en: "No feedback — am I even understanding this right?" },
                      { zh: "做笔记太累，回头也找不到", en: "Note-taking is exhausting and impossible to revisit" },
                    ].map((item, i) => (
                      <p key={i} className="text-xs text-ink-soft flex items-start gap-1.5">
                        <span className="text-color-danger shrink-0 mt-0.5">&#10005;</span>
                        {t(item.zh, item.en)}
                      </p>
                    ))}
                  </div>
                </div>
                {/* Selling points */}
                <div className="flex-1 space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted mb-2">
                    {t("朽瓜如何解决", "How Xiugua Helps")}
                  </p>
                  <div className="space-y-1.5">
                    {[
                      { zh: "AI 逐章追问，像导师一样带你深入", en: "AI questions you chapter by chapter, like a mentor" },
                      { zh: "自动沉淀 Wiki，读完留下一套知识库", en: "Auto-builds a Wiki — every book leaves a knowledge base" },
                      { zh: "快速 15min / 深度 40min，两种节奏", en: "Quick 15min overview or deep 40min dive" },
                    ].map((item, i) => (
                      <p key={i} className="text-xs text-ink-soft flex items-start gap-1.5">
                        <span className="text-color-success shrink-0 mt-0.5">&#10003;</span>
                        {t(item.zh, item.en)}
                      </p>
                    ))}
                  </div>
                </div>
              </div>

              {/* CTA */}
              <div className="mt-6 flex items-center gap-4">
                {!loading && renderCTA("default")}
                {!loading && !loggedIn && (
                  <p className="text-xs text-ink-muted">{t("免费开始", "Free to start")}</p>
                )}
              </div>
            </div>

            {/* RIGHT: Flow diagram */}
            <div className="hidden md:flex w-72 shrink-0 flex-col items-center gap-3 p-6 rounded-2xl bg-surface-amber/30 border border-amber-deep/10">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted mb-1">
                {t("三步开始", "How It Works")}
              </p>
              <div className="flex flex-col items-center gap-2 w-full">
                {[
                  { zh: "上传一本书", en: "Upload a book" },
                  { zh: "AI 预解析 Wiki", en: "AI parses & builds Wiki" },
                  { zh: "逐章对话阅读", en: "Chapter-by-chapter dialogue" },
                ].map((step, i) => (
                  <div key={i} className="flex items-center gap-3 w-full">
                    <span className="step-num !w-8 !h-8 text-xs">{i + 1}</span>
                    <span className="text-xs text-ink-soft">{t(step.zh, step.en)}</span>
                    {i < 2 && <span className="text-ink-muted text-xs ml-auto">&darr;</span>}
                  </div>
                ))}
              </div>
              <div className="mt-3 pt-3 border-t border-amber-deep/10 w-full text-center">
                <span className="text-xs font-semibold text-amber-deep">
                  {t("→ Wiki 知识库", "→ Your Wiki")}
                </span>
              </div>
            </div>
          </div>

          {/* Format highlights */}
          <div className="mt-10 flex flex-wrap justify-center md:justify-start gap-x-8 gap-y-2 text-xs text-ink-muted">
            <span>{t("ePub / PDF / TXT", "ePub / PDF / TXT")}</span>
            <span className="hidden sm:inline">&middot;</span>
            <span>{t("自动章节解析", "Auto chapter parsing")}</span>
            <span className="hidden sm:inline">&middot;</span>
            <span>{t("Wiki 概念沉淀", "Wiki concept building")}</span>
          </div>

          {/* Scroll indicator */}
          <div className="mt-12 flex flex-col items-center gap-2 animate-bounce">
            <span className="text-xs text-ink-muted">
              {t("向下滚动，了解更多", "Scroll to learn more")}
            </span>
            <svg className="w-5 h-5 text-ink-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </div>
        </div>
      </section>

      {/* ---- FEATURES ---- */}
      <RevealWrap as="section" className="py-16 md:py-24">
        <div className="text-center mb-12 md:mb-16">
          <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight text-ink">
            {t("这才是真正的 AI 阅读", "This Is What AI Reading Should Be")}
          </h2>
          <p className="mt-3 text-sm text-ink-soft max-w-lg mx-auto">
            {t(
              "不是更快地翻页，而是更深入地理解。朽瓜重新定义了人机共读的方式。",
              "Not faster page-turning, but deeper understanding. Xiugua redefines human-AI co-reading."
            )}
          </p>
        </div>
        {renderFeatureCards()}
      </RevealWrap>

      {/* ---- KARPATHY LLM WIKI ---- */}
      <RevealWrap as="section" className="py-16 md:py-24">
        <div className="max-w-3xl mx-auto">
          <div className="text-center mb-10">
            <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight text-ink">
              {t("不止是笔记，是生长的 Wiki", "More Than Notes — A Living Wiki")}
            </h2>
          </div>

          <p className="text-sm text-ink-soft leading-relaxed text-center max-w-xl mx-auto mb-8">
            {t(
              "Andrej Karpathy（前 Tesla AI 总监、OpenAI 联合创始人）提出了「LLM Wiki」的理念：让 AI 帮你持续构建、维护一个结构化知识库，而不是每次都临时拼凑信息。以下是他的原话：",
              "Andrej Karpathy (ex-Tesla AI Director, OpenAI co-founder) proposed \"LLM Wiki\": let AI continuously build and maintain a structured knowledge base for you, instead of piecing things together from scratch every time. In his own words:"
            )}
          </p>

          <div className="quote-amber space-y-5 mt-6">
            <p className="font-display text-lg md:text-xl leading-relaxed text-ink">
              &ldquo;The LLM <strong className="font-bold">incrementally builds and maintains a persistent wiki</strong> — a structured, interlinked collection of markdown files. The knowledge is compiled once and then <em>kept current</em>. The wiki is a <strong className="font-bold">persistent, compounding artifact</strong>. The wiki keeps getting richer with every source you add.&rdquo;
            </p>
            <p className="text-sm text-ink-soft">
              &ldquo;You never (or rarely) write the wiki yourself. <strong className="font-bold">The LLM writes and maintains all of it.</strong> Obsidian is the IDE; the LLM is the programmer; the wiki is the codebase.&rdquo;
            </p>
            <p className="text-sm text-ink-soft">
              &ldquo;Humans abandon wikis because the maintenance burden grows faster than the value. LLMs don't get bored, don't forget to update a cross-reference. <strong className="font-bold">The human's job is to curate sources, direct the analysis, ask good questions. The LLM's job is everything else.</strong>&rdquo;
            </p>
            <p className="text-sm text-ink-soft">
              &ldquo;The tedious part of maintaining a knowledge base is not the reading or the thinking — <strong className="font-bold">it's the bookkeeping.</strong>&rdquo;
            </p>
          </div>

          <p className="mt-8 text-xs text-ink-muted text-center">
            {t(
              "—— Andrej Karpathy, \"LLM Wiki\" (2025)",
              "— Andrej Karpathy, \"LLM Wiki\" (2025)"
            )}
          </p>

          <div className="mt-10 grid gap-6 sm:grid-cols-2 text-center max-w-lg mx-auto">
            {[
              {
                label_zh: "独立记录",
                label_en: "Independent",
                desc_zh: "每个概念独立存储，不遗漏",
                desc_en: "Each concept stored independently",
              },
              {
                label_zh: "持续生长",
                label_en: "Compounding",
                desc_zh: "每本书都在丰富你的知识库",
                desc_en: "Every book enriches your knowledge base",
              },
            ].map((item, i) => (
              <div key={i} className="p-5">
                <div className="section-rule mx-auto mb-3" />
                <h3 className="font-display text-base font-bold text-ink">
                  {t(item.label_zh, item.label_en)}
                </h3>
                <p className="mt-1 text-xs text-ink-soft">
                  {t(item.desc_zh, item.desc_en)}
                </p>
              </div>
            ))}
          </div>
        </div>
      </RevealWrap>

      {/* ---- HOW IT WORKS ---- */}
      <RevealWrap as="section" className="py-16 md:py-24">
        <div className="text-center mb-12 md:mb-16">
          <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight text-ink">
            {t("三步开始", "Get Started in 3 Steps")}
          </h2>
          <p className="mt-3 text-sm text-ink-soft max-w-lg mx-auto">
            {t(
              "从上传到阅读，全程 AI 引导，无需任何配置。",
              "From upload to reading, fully AI-guided. No setup required."
            )}
          </p>
        </div>
        {renderSteps()}

        {/* result callout */}
        <div className="mt-12 md:mt-16 text-center">
          <div className="inline-flex items-center gap-2 px-5 py-3 rounded-xl border border-amber-deep/15 bg-surface-amber/40 text-sm text-amber-deep">
            <span className="font-display font-bold">
              {t("最终：", "Result: ")}
            </span>
            {t(
              "读过的每一本书，都转化成你个人的 Wiki 知识库",
              "Every book you finish becomes part of your personal Wiki library"
            )}
          </div>
        </div>
      </RevealWrap>

      {/* ---- FINAL CTA ---- */}
      <RevealWrap as="section" className="py-16 md:py-24 text-center">
        <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight text-ink">
          {t("准备好开始了吗？", "Ready to Begin?")}
        </h2>
        <p className="mt-3 text-sm text-ink-soft max-w-md mx-auto">
          {t(
            "带上你一直想读却没读完的那本书，让 AI 陪你一起。",
            "Bring that book you've always wanted to finish — and let AI read it with you."
          )}
        </p>
        <div className="mt-8 flex flex-col items-center gap-4">
          {!loading && renderCTA("large")}
        </div>
        <p className="text-xs mt-10 text-ink-muted">
          xiugua-reading.cn &middot; v2026.05.07-5bc
        </p>
      </RevealWrap>
    </div>
  );
}
