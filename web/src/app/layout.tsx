import type { Metadata } from "react";
import "./globals.css";
import { Nav } from "./nav";
import { LangProvider } from "./lang";
import { FeedbackButton } from "./feedback";

export const metadata: Metadata = { title: "朽瓜" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh">
      <head><link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700&display=swap" rel="stylesheet" /></head>
      <body className="min-h-screen bg-white">
        <LangProvider>
          <Nav />
          <main className="max-w-5xl mx-auto px-6 py-12">{children}</main>
          <FeedbackButton />
        </LangProvider>
      </body>
    </html>
  );
}
