import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "./nav";
import { LangProvider } from "./lang";
import { FeedbackButton } from "./feedback";
import { ToastContainer } from "./toast";

export const metadata: Metadata = { title: "朽瓜" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <head><link rel="preconnect" href="https://fonts.googleapis.com" /><link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" /></head>
      <body className="min-h-screen bg-white">
        <LangProvider>
          <Nav />
          <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:bg-white focus:text-ink focus:border focus:border-ink-muted focus:rounded-xl focus:text-sm focus:font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-stone-500">
            跳到主要内容
          </a>
          <main id="main-content" className="px-6 py-12">{children}</main>
          <FeedbackButton />
          <ToastContainer />
        </LangProvider>
      </body>
    </html>
  );
}
