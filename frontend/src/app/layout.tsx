import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Carousel Studio",
  description: "인스타그램 카드뉴스 벤치마킹 수집 및 자동 생성 플랫폼",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full bg-[#1a1a1a] text-[#eeeeee] font-[family-name:var(--font-inter)]">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
