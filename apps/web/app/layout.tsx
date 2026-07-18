import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "个人经历 AI 助手",
  description: "基于个人公开知识库的 AI 问答助手。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
