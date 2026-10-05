"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";

type NavItem = {
  href: string;
  label: string;
  icon: ReactNode;
  adminOnly?: boolean;
  primary?: boolean;
};

type NavSection = {
  caption: string;
  items: NavItem[];
  adminOnly?: boolean;
};

const STROKE = 1.7;

const icon = (path: string) => (
  <svg width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth={STROKE} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d={path} />
  </svg>
);

const navSections: NavSection[] = [
  {
    caption: "둘러보기",
    items: [
      {
        href: "/",
        label: "대시보드",
        icon: icon("M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z"),
      },
      {
        href: "/channels",
        label: "벤치마크 채널",
        icon: icon("M9.348 14.652a3.75 3.75 0 0 1 0-5.304m5.304 0a3.75 3.75 0 0 1 0 5.304m-7.425 2.121a6.75 6.75 0 0 1 0-9.546m9.546 0a6.75 6.75 0 0 1 0 9.546M12 12h.008v.008H12V12Z"),
      },
      {
        href: "/posts",
        label: "캐러셀 소재",
        icon: icon("m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z"),
      },
      {
        href: "/reels",
        label: "릴스 소재",
        icon: icon("m15.75 10.5 4.72-4.72a.75.75 0 0 1 1.28.53v11.38a.75.75 0 0 1-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25h-9A2.25 2.25 0 0 0 2.25 7.5v9a2.25 2.25 0 0 0 2.25 2.25Z"),
      },
      {
        href: "/saved",
        label: "내 소재",
        // Bookmark — boarded materials are kept indefinitely until the user removes them.
        icon: icon("M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0 1 11.186 0Z"),
      },
    ],
  },
  {
    caption: "만들기",
    items: [
      {
        href: "/create",
        label: "캐러셀 만들기",
        primary: true,
        // Sparkles — primary creative action gets a distinctive icon.
        icon: icon("M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.847.814a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z"),
      },
      {
        // 상황별 일본어 6단계를 한 화면에서 끝내는 길. codex 가 있는 이 PC 에서만 돈다.
        href: "/studio/ja-situations",
        label: "상황별 일본어 원클릭",
        // Bolt — 한 번에 끝난다는 뜻.
        icon: icon("M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"),
      },
      {
        href: "/studio/ja-restaurants",
        label: "일본 맛집 원클릭",
        icon: icon("M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"),
      },
      {
        href: "/studio/ja-restaurants-2",
        label: "일본 맛집 2 원클릭",
        icon: icon("M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"),
      },
      {
        href: "/studio/map",
        label: "지도 원클릭",
        icon: icon("M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"),
      },
      {
        href: "/studio/x-quote",
        label: "X인용 원클릭",
        icon: icon("M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z"),
      },
      {
        href: "/templates",
        label: "템플릿 스튜디오",
        // RectangleStack — stacked layouts read as "templates", not "menu".
        icon: icon("M6.429 9.75 2.25 12l4.179 2.25m0-4.5 5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0 4.179 2.25L12 21.75 2.25 14.25l4.179-2.25m11.142 0-5.571 3-5.571-3"),
      },
    ],
  },
  {
    caption: "내 자산",
    items: [
      {
        href: "/works",
        label: "내 작업",
        icon: icon("M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z"),
      },
    ],
  },
  {
    caption: "관리",
    adminOnly: true,
    items: [
      {
        href: "/admin",
        label: "관리자",
        adminOnly: true,
        icon: icon("M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z"),
      },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useAppStore((s) => s.user);
  const isAdmin = user?.role === "admin";

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(href + "/");
  }

  function handleLogout() {
    api.clearToken();
    router.push("/login");
  }

  return (
    <aside
      className="fixed left-0 top-0 h-full flex flex-col z-20"
      style={{
        width: 220,
        background: "var(--bg-subtle)",
        borderRight: "1px solid rgba(255,255,255,0.12)",
      }}
    >
      {/* Logo */}
      <div className="px-4 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-center gap-2.5">
          <div
            className="flex items-center justify-center flex-shrink-0"
            style={{ width: 24, height: 24, background: "var(--accent)", borderRadius: 6 }}
          >
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2.2} stroke="white">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z" />
            </svg>
          </div>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
            Carousel Studio
          </span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 pt-1 pb-2 overflow-y-auto">
        {navSections.map((section) => {
          if (section.adminOnly && !isAdmin) return null;
          const visibleItems = section.items.filter((it) => !it.adminOnly || isAdmin);
          if (visibleItems.length === 0) return null;

          return (
            <div key={section.caption} className="mt-3 first:mt-1">
              <div
                className="px-2.5 pb-1.5"
                style={{
                  fontSize: 10.5,
                  fontWeight: 600,
                  color: "var(--text-tertiary)",
                  letterSpacing: "0.04em",
                }}
              >
                {section.caption}
              </div>
              {visibleItems.map((item) => {
                const active = isActive(item.href);
                const primary = !!item.primary;

                const baseColor = primary
                  ? "var(--accent-text)"
                  : active
                  ? "var(--text-primary)"
                  : "var(--text-secondary)";

                const baseBg = active
                  ? primary
                    ? "var(--accent-muted)"
                    : "var(--accent-muted)"
                  : "transparent";

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="flex items-center gap-2.5 px-2.5 py-[7px] rounded-[6px] transition-colors"
                    style={{
                      fontSize: 13,
                      fontWeight: active || primary ? 500 : 400,
                      letterSpacing: "-0.005em",
                      color: baseColor,
                      background: baseBg,
                    }}
                    onMouseEnter={(e) => {
                      if (active) return;
                      e.currentTarget.style.background = primary
                        ? "var(--accent-muted)"
                        : "rgba(255,255,255,0.045)";
                      e.currentTarget.style.color = primary ? "var(--accent-text)" : "var(--text-primary)";
                    }}
                    onMouseLeave={(e) => {
                      if (active) return;
                      e.currentTarget.style.background = "transparent";
                      e.currentTarget.style.color = baseColor;
                    }}
                  >
                    <span
                      style={{
                        opacity: active || primary ? 1 : 0.6,
                        color: primary ? "var(--accent)" : "inherit",
                      }}
                    >
                      {item.icon}
                    </span>
                    {item.label}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      {/* User */}
      <div className="p-2" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-[5px]">
          <div
            className="flex items-center justify-center flex-shrink-0 text-white"
            style={{
              width: 22,
              height: 22,
              borderRadius: 4,
              background: "var(--accent)",
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            {user?.username?.charAt(0).toUpperCase() || "?"}
          </div>
          <div className="flex-1 min-w-0">
            <p style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 500 }} className="truncate">
              {user?.username}
            </p>
            <p style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
              {isAdmin ? "관리자" : "작업자"}
            </p>
          </div>
          <button
            onClick={handleLogout}
            title="로그아웃"
            className="flex-shrink-0"
            style={{ color: "var(--text-tertiary)" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-tertiary)")}
          >
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0 0 13.5 3h-6a2.25 2.25 0 0 0-2.25 2.25v13.5A2.25 2.25 0 0 0 7.5 21h6a2.25 2.25 0 0 0 2.25-2.25V15m3 0 3-3m0 0-3-3m3 3H9" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}
