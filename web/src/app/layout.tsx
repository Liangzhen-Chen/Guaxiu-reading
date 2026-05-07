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
          <main className="px-6 py-12">{children}</main>
          <FeedbackButton />
          <ToastContainer />
        </LangProvider>
      </body>
    </html>
  );
}
