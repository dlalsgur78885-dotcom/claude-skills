"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Channel, CarouselListItem, Category } from "@/lib/types";

export default function Dashboard() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [carousels, setCarousels] = useState<CarouselListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showChannels, setShowChannels] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [scrapeMsg, setScrapeMsg] = useState("");

  const loadData = useCallback(async () => {
    try {
      const [ch, ca] = await Promise.all([
        api.getChannels().catch(() => []),
        api.getCarousels().catch(() => []),
      ]);
      setChannels(ch);
      setCarousels(ca);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleScrape() {
    setScraping(true);
    setScrapeMsg("");
    try {
      const res = await api.triggerScrape();
      setScrapeMsg(res.message);
    } catch (err) {
      setScrapeMsg(err instanceof Error ? err.message : "실패");
    } finally {
      setScraping(false);
      setTimeout(() => setScrapeMsg(""), 4000);
    }
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 960, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 32, display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
            대시보드
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 4 }}>
            캐러셀 자동화 현황을 한눈에 확인하세요
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {scrapeMsg && (
            <span style={{ fontSize: 12, color: "var(--green)" }}>{scrapeMsg}</span>
          )}
          <button
            onClick={handleScrape}
            disabled={scraping}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "7px 14px",
              fontSize: 12,
              fontWeight: 500,
              background: scraping ? "var(--bg-overlay)" : "var(--accent)",
              color: scraping ? "var(--text-tertiary)" : "white",
              borderRadius: 6,
              border: "1px solid var(--border)",
              cursor: scraping ? "not-allowed" : "pointer",
            }}
          >
            {scraping ? (
              <>
                <div className="spinner" style={{ width: 12, height: 12 }} />
                수집 중...
              </>
            ) : (
              <>
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                지금 수집
              </>
            )}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 40 }}>
        <StatCard
          label="벤치마크 채널"
          value={loading ? "—" : String(channels.length)}
          onClick={() => setShowChannels(true)}
          sub={`${loading ? "—" : channels.length}개 등록`}
          icon={
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.348 14.652a3.75 3.75 0 0 1 0-5.304m5.304 0a3.75 3.75 0 0 1 0 5.304m-7.425 2.121a6.75 6.75 0 0 1 0-9.546m9.546 0a6.75 6.75 0 0 1 0 9.546M12 12h.008v.008H12V12Z" />
            </svg>
          }
        />
        <StatCard
          label="생성된 캐러셀"
          value={loading ? "—" : String(carousels.length)}
          href="/editor/new"
          sub="새로 만들기"
          icon={
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z" />
            </svg>
          }
        />
        <StatCard
          label="수집된 소재"
          value={loading ? "—" : "—"}
          href="/posts"
          sub="소재 보기"
          icon={
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
            </svg>
          }
        />
      </div>

      {/* Recent carousels */}
      <section>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", margin: 0 }}>최근 캐러셀</h2>
          <Link
            href="/editor/new"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontSize: 12,
              color: "var(--accent-text)",
              fontWeight: 500,
            }}
          >
            <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            새로 만들기
          </Link>
        </div>

        {carousels.length === 0 ? (
          <div
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "48px 24px",
              textAlign: "center",
              background: "var(--bg-subtle)",
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                margin: "0 auto 12px",
                borderRadius: 8,
                background: "var(--accent-muted)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <svg width="18" height="18" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="var(--accent-text)">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.53 16.122a3 3 0 0 0-5.78 1.128 2.25 2.25 0 0 1-2.4 2.245 4.5 4.5 0 0 0 8.4-2.245c0-.399-.078-.78-.22-1.128Zm0 0a15.998 15.998 0 0 0 3.388-1.62m-5.043-.025a15.994 15.994 0 0 1 1.622-3.395m3.42 3.42a15.995 15.995 0 0 0 4.764-4.648l3.876-5.814a1.151 1.151 0 0 0-1.597-1.597L14.146 6.32a15.996 15.996 0 0 0-4.649 4.763m3.42 3.42a6.776 6.776 0 0 0-3.42-3.42" />
              </svg>
            </div>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500, margin: 0 }}>
              아직 생성된 캐러셀이 없습니다
            </p>
            <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>
              첫 캐러셀을 만들어 시작해보세요
            </p>
            <Link
              href="/editor/new"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                marginTop: 20,
                padding: "7px 16px",
                background: "var(--accent)",
                color: "white",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 500,
              }}
            >
              <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              첫 캐러셀 만들기
            </Link>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
            {carousels.slice(0, 6).map((c) => (
              <Link
                key={c.id}
                href={`/editor/${c.id}`}
                style={{
                  display: "block",
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  padding: "14px 16px",
                  textDecoration: "none",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
              >
                <p style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.title || "제목 없음"}
                </p>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                  <span
                    style={{
                      fontSize: 11,
                      padding: "2px 8px",
                      borderRadius: 4,
                      fontWeight: 500,
                      background:
                        c.status === "finalized"
                          ? "var(--green-muted)"
                          : c.status === "editing"
                          ? "var(--amber-muted)"
                          : "var(--bg-overlay)",
                      color:
                        c.status === "finalized"
                          ? "var(--green)"
                          : c.status === "editing"
                          ? "var(--amber)"
                          : "var(--text-tertiary)",
                    }}
                  >
                    {c.status === "draft" ? "초안" : c.status === "editing" ? "편집 중" : "완료"}
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                    {new Date(c.updated_at).toLocaleDateString("ko-KR")}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Channel Management Modal */}
      {showChannels && (
        <ChannelModal
          channels={channels}
          onClose={() => setShowChannels(false)}
          onRefresh={loadData}
        />
      )}
    </div>
  );
}

/* ─── Stat Card ─── */

function StatCard({
  label,
  value,
  href,
  onClick,
  icon,
  sub,
}: {
  label: string;
  value: string;
  href?: string;
  onClick?: () => void;
  icon: React.ReactNode;
  sub?: string;
}) {
  const inner = (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
        <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0 }}>{label}</p>
        <span style={{ color: "var(--text-tertiary)", opacity: 0.6 }}>{icon}</span>
      </div>
      <p style={{ fontSize: 28, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.03em", margin: 0 }}>
        {value}
      </p>
      <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 6 }}>{sub}</p>
    </>
  );

  const baseStyle: React.CSSProperties = {
    display: "block",
    background: "var(--bg-elevated)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "18px 20px",
    cursor: "pointer",
    textAlign: "left",
    width: "100%",
    textDecoration: "none",
  };

  if (onClick) {
    return (
      <button
        onClick={onClick}
        style={baseStyle}
        onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
        onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
      >
        {inner}
      </button>
    );
  }

  return (
    <Link
      href={href || "/"}
      style={baseStyle}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
    >
      {inner}
    </Link>
  );
}

/* ─── Channel Modal ─── */

function ChannelModal({
  channels,
  onClose,
  onRefresh,
}: {
  channels: Channel[];
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [bulk, setBulk] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [adding, setAdding] = useState(false);
  const [results, setResults] = useState<{ handle: string; ok: boolean; msg?: string }[]>([]);

  useEffect(() => {
    api.getCategories().catch(() => []).then(setCategories);
  }, []);

  function parseHandles(raw: string): string[] {
    return raw
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .map((s) => s.replace(/^https?:\/\/(www\.)?instagram\.com\//i, "").replace(/\//g, "").replace(/^@/, ""))
      .filter(Boolean);
  }

  async function addChannels(e: React.FormEvent) {
    e.preventDefault();
    const handles = parseHandles(bulk);
    if (handles.length === 0) return;
    setAdding(true);
    setResults([]);
    const res: { handle: string; ok: boolean; msg?: string }[] = [];
    for (const h of handles) {
      try {
        await api.createChannel({ instagram_handle: h, category });
        res.push({ handle: h, ok: true });
      } catch (err) {
        res.push({ handle: h, ok: false, msg: err instanceof Error ? err.message : "실패" });
      }
    }
    setResults(res);
    setBulk("");
    setAdding(false);
    onRefresh();
  }

  async function removeChannel(id: number) {
    if (!confirm("이 채널을 삭제하시겠습니까?")) return;
    await api.deleteChannel(id);
    onRefresh();
  }

  const inputStyle: React.CSSProperties = {
    background: "var(--bg-overlay)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    padding: "7px 10px",
    fontSize: 13,
    color: "var(--text-primary)",
    outline: "none",
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center" }}>
      {/* Backdrop */}
      <div
        style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.6)" }}
        onClick={onClose}
      />

      {/* Modal */}
      <div
        style={{
          position: "relative",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-strong)",
          borderRadius: 10,
          width: "100%",
          maxWidth: 480,
          margin: "0 16px",
          maxHeight: "80vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 20px",
            borderBottom: "1px solid var(--border)",
          }}
        >
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>벤치마크 채널</h3>
            <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>모니터링할 인스타그램 채널 관리</p>
          </div>
          <button
            onClick={onClose}
            style={{ color: "var(--text-tertiary)", padding: 4, borderRadius: 4 }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-tertiary)")}
          >
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Add form */}
        <form
          onSubmit={addChannels}
          style={{
            padding: "12px 20px",
            borderBottom: "1px solid var(--border)",
            background: "var(--bg-subtle)",
          }}
        >
          <textarea
            value={bulk}
            onChange={(e) => setBulk(e.target.value)}
            placeholder={"URL 또는 핸들을 한 줄에 하나씩 입력\nhttps://www.instagram.com/username\n@username"}
            rows={3}
            style={{
              width: "100%",
              padding: "8px 10px",
              background: "var(--bg-overlay)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              fontSize: 12,
              color: "var(--text-primary)",
              outline: "none",
              resize: "vertical",
              lineHeight: 1.6,
              fontFamily: "inherit",
            }}
            onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
            onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{ ...inputStyle, flex: 1 }}
            >
              <option value="">카테고리 (선택)</option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.name}>{cat.name}</option>
              ))}
            </select>
            <button
              type="submit"
              disabled={adding || !bulk.trim()}
              style={{
                padding: "7px 16px",
                background: "var(--accent)",
                color: "white",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 500,
                opacity: adding || !bulk.trim() ? 0.5 : 1,
                cursor: adding || !bulk.trim() ? "not-allowed" : "pointer",
                flexShrink: 0,
              }}
            >
              {adding ? "추가 중..." : `추가 (${parseHandles(bulk).length}개)`}
            </button>
          </div>
          {results.length > 0 && (
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 3 }}>
              {results.map((r) => (
                <div key={r.handle} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
                  <span style={{ color: r.ok ? "var(--green)" : "var(--red)" }}>
                    {r.ok ? "✓" : "✗"}
                  </span>
                  <span style={{ color: "var(--text-secondary)" }}>@{r.handle}</span>
                  {!r.ok && <span style={{ color: "var(--text-tertiary)" }}>{r.msg}</span>}
                </div>
              ))}
            </div>
          )}
        </form>

        {/* Channel list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 20px" }}>
          {channels.length === 0 ? (
            <div style={{ padding: "40px 0", textAlign: "center" }}>
              <p style={{ fontSize: 13, color: "var(--text-tertiary)" }}>아직 등록된 채널이 없습니다</p>
            </div>
          ) : (
            <div>
              {channels.map((ch) => (
                <div
                  key={ch.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "10px 0",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 6,
                        background: "var(--accent-muted)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "var(--accent-text)",
                        fontSize: 12,
                        fontWeight: 700,
                        flexShrink: 0,
                      }}
                    >
                      {ch.instagram_handle.charAt(0).toUpperCase()}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <p style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          @{ch.instagram_handle}
                        </p>
                      </div>
                      {ch.category && (
                        <span
                          style={{
                            fontSize: 11,
                            color: "var(--text-tertiary)",
                            background: "var(--bg-overlay)",
                            padding: "1px 6px",
                            borderRadius: 4,
                            marginTop: 2,
                            display: "inline-block",
                          }}
                        >
                          {ch.category}
                        </span>
                      )}
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                    <button
                      onClick={() => removeChannel(ch.id)}
                      style={{ padding: 4, borderRadius: 4, color: "var(--text-tertiary)" }}
                      onMouseEnter={(e) => (e.currentTarget.style.color = "var(--red)")}
                      onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-tertiary)")}
                    >
                      <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
