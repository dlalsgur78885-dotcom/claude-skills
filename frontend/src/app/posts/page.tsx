"use client";

import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, resolveImageUrl, proxiedImageUrl, thumbnailUrl } from "@/lib/api";
import type { Post, Channel } from "@/lib/types";

type SortKey = "caption" | "like_count" | "comment_count" | "slide_count" | "post_date";
type SortDir = "asc" | "desc";

const DATE_PRESETS = [1, 7, 30] as const;

function useDebounce<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export default function PostsPage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [minLikes, setMinLikes] = useState("");
  const [maxLikes, setMaxLikes] = useState("");
  const [minComments, setMinComments] = useState("");
  const [maxComments, setMaxComments] = useState("");
  const [minSlides, setMinSlides] = useState("");
  const [maxSlides, setMaxSlides] = useState("");
  const [channelId, setChannelId] = useState<number | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const router = useRouter();
  const [sortKey, setSortKey] = useState<SortKey>("post_date");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [hoveredThumbId, setHoveredThumbId] = useState<number | null>(null);
  const [hoverPos, setHoverPos] = useState<{ top: number; left: number } | null>(null);
  const POPOVER_W = 320;
  const POPOVER_H = 400;
  const POPOVER_GAP = 10;
  const scrollKey = "posts-scroll";
  const lockedScrollKey = `${scrollKey}:locked`;
  const didRestoreScrollRef = useRef(false);
  const navigatingAwayRef = useRef(false);
  const lastScrollYRef = useRef(0);

  function onThumbHover(id: number, e: React.MouseEvent<HTMLDivElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const vh = window.innerHeight;
    const rowCenter = r.top + r.height / 2;
    const top = Math.max(8, Math.min(vh - POPOVER_H - 8, rowCenter - POPOVER_H / 2));
    const left = r.right + POPOVER_GAP;
    setHoverPos({ top, left });
    setHoveredThumbId(id);
  }
  function onThumbLeave(id: number) {
    setHoveredThumbId((cur) => (cur === id ? null : cur));
    setHoverPos(null);
  }

  const dQuery = useDebounce(query, 300);
  const dMinLikes = useDebounce(minLikes, 300);
  const dMaxLikes = useDebounce(maxLikes, 300);
  const dMinComments = useDebounce(minComments, 300);
  const dMaxComments = useDebounce(maxComments, 300);
  const dMinSlides = useDebounce(minSlides, 300);
  const dMaxSlides = useDebounce(maxSlides, 300);

  // Channels load once. Used to render the source handle on each post row —
  // workers asked for "어느 채널이지?" being obvious without a click-through.
  useEffect(() => {
    api.getChannels().then(setChannels).catch(() => setChannels([]));
  }, []);

  const channelMap = useMemo(() => {
    const m = new Map<number, Channel>();
    for (const c of channels) m.set(c.id, c);
    return m;
  }, [channels]);

  const loadPosts = useCallback(async () => {
    setLoading(true);
    try {
      const filters: Parameters<typeof api.getPosts>[3] = {};
      if (dMinLikes) filters.minLikes = Number(dMinLikes);
      if (dMaxLikes) filters.maxLikes = Number(dMaxLikes);
      if (dMinComments) filters.minComments = Number(dMinComments);
      if (dMaxComments) filters.maxComments = Number(dMaxComments);
      if (dMinSlides) filters.minSlides = Number(dMinSlides);
      if (dMaxSlides) filters.maxSlides = Number(dMaxSlides);
      if (dateFrom) filters.dateFrom = dateFrom;
      if (dateTo) filters.dateTo = dateTo;
      if (dQuery.trim()) filters.q = dQuery.trim();
      const data = await api.getPosts(channelId === "" ? undefined : channelId, 200, 0, filters);
      setPosts(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [dMinLikes, dMaxLikes, dMinComments, dMaxComments, dMinSlides, dMaxSlides, channelId, dateFrom, dateTo, dQuery]);

  useEffect(() => {
    loadPosts();
  }, [loadPosts]);

  useEffect(() => {
    const onScroll = () => {
      lastScrollYRef.current = window.scrollY;
      if (navigatingAwayRef.current) return;
      sessionStorage.setItem(scrollKey, String(window.scrollY));
    };
    lastScrollYRef.current = window.scrollY;
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const sorted = [...posts].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    if (sortKey === "caption") return dir * (a.caption || "").localeCompare(b.caption || "");
    if (sortKey === "like_count") return dir * (a.like_count - b.like_count);
    if (sortKey === "comment_count") return dir * (a.comment_count - b.comment_count);
    if (sortKey === "slide_count") return dir * ((a.slide_count || 0) - (b.slide_count || 0));
    if (sortKey === "post_date") {
      const da = a.post_date ? new Date(a.post_date).getTime() : 0;
      const db = b.post_date ? new Date(b.post_date).getTime() : 0;
      return dir * (da - db);
    }
    return 0;
  });

  useEffect(() => {
    if (loading || sorted.length === 0 || didRestoreScrollRef.current) return;
    const raw = sessionStorage.getItem(lockedScrollKey) || sessionStorage.getItem(scrollKey);
    if (!raw) return;
    const y = Number(raw);
    if (!Number.isFinite(y) || y <= 0) return;
    didRestoreScrollRef.current = true;
    requestAnimationFrame(() => {
      window.scrollTo({ top: y, behavior: "auto" });
      lastScrollYRef.current = y;
    });
  }, [loading, sorted.length, lockedScrollKey]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  }

  const activeFilterCount = [minLikes, maxLikes, minComments, maxComments, minSlides, maxSlides, dateFrom, dateTo, channelId === "" ? "" : "1"].filter(Boolean).length;

  function clearFilters() {
    setMinLikes(""); setMaxLikes("");
    setMinComments(""); setMaxComments("");
    setMinSlides(""); setMaxSlides("");
    setChannelId("");
    setDateFrom(""); setDateTo("");
  }

  const allSelected = sorted.length > 0 && selected.size === sorted.length;

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(sorted.map((p) => p.id)));
  }

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function saveCurrentScroll() {
    const y = window.scrollY || lastScrollYRef.current;
    navigatingAwayRef.current = true;
    sessionStorage.setItem(scrollKey, String(y));
    sessionStorage.setItem(lockedScrollKey, String(y));
  }

  const [bulkSaving, setBulkSaving] = useState(false);
  async function bulkSaveSelected() {
    if (selected.size === 0 || bulkSaving) return;
    setBulkSaving(true);
    const ids = Array.from(selected);
    const results = await Promise.allSettled(ids.map((id) => api.savePost(id)));
    const failed = results
      .map((r, i) => (r.status === "rejected" ? ids[i] : null))
      .filter((x): x is number => x !== null);
    setBulkSaving(false);
    if (failed.length > 0) alert(`${ids.length - failed.length}개 보관 완료. ${failed.length}개 실패.`);
    setSelected(new Set(failed));
    loadPosts();
  }

  const [bulkDeleting, setBulkDeleting] = useState(false);
  async function bulkDeleteSelected() {
    if (selected.size === 0 || bulkDeleting) return;
    if (!confirm(`선택된 ${selected.size}개 소재를 삭제할까요?\n이 소재로 만든 캐러셀 작업은 보존됩니다 (되돌릴 수 없음).`)) return;
    setBulkDeleting(true);
    const ids = Array.from(selected);
    const results = await Promise.allSettled(ids.map((id) => api.deletePost(id)));
    const failed = results
      .map((r, i) => (r.status === "rejected" ? ids[i] : null))
      .filter((x): x is number => x !== null);
    setBulkDeleting(false);
    if (failed.length > 0) {
      alert(`${ids.length - failed.length}개 삭제 완료. ${failed.length}개 실패.`);
    }
    setSelected(new Set(failed));
    loadPosts();
  }

  const thStyle = (align: "left" | "right", width?: number): React.CSSProperties => ({
    textAlign: align,
    padding: "10px 16px",
    fontWeight: 500,
    color: "var(--text-tertiary)",
    fontSize: 12,
    cursor: "pointer",
    userSelect: "none",
    whiteSpace: "nowrap",
    ...(width ? { width } : {}),
  });

  function SortIcon({ col }: { col: SortKey }) {
    if (sortKey !== col) return <span style={{ opacity: 0.5, marginLeft: 4 }}>&#8597;</span>;
    return <span style={{ marginLeft: 4 }}>{sortDir === "asc" ? "\u2191" : "\u2193"}</span>;
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 960, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
              수집된 소재
            </h1>
            <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 4 }}>
              벤치마크 채널에서 수집한 캐러셀 소재들
              {!loading && <span style={{ marginLeft: 8, color: "var(--text-secondary)" }}>{sorted.length}개</span>}
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* Search input */}
            <div
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 10px",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                minWidth: 220,
              }}
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="var(--text-tertiary)">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="캡션 검색"
                style={{
                  flex: 1, minWidth: 0,
                  fontSize: 12, color: "var(--text-primary)",
                  background: "transparent", border: "none", outline: "none",
                }}
              />
              {query && (
                <button
                  onClick={() => setQuery("")}
                  aria-label="검색어 지우기"
                  style={{
                    color: "var(--text-tertiary)", background: "none", border: "none",
                    cursor: "pointer", padding: 0, lineHeight: 1, fontSize: 14,
                  }}
                >
                  ×
                </button>
              )}
            </div>

            <button
              onClick={() => setFilterOpen(!filterOpen)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 12px", fontSize: 12, fontWeight: 500,
                color: activeFilterCount > 0 ? "var(--accent-text)" : "var(--text-secondary)",
                background: activeFilterCount > 0 ? "var(--accent-muted)" : "var(--bg-elevated)",
                border: `1px solid ${activeFilterCount > 0 ? "var(--accent)" : "var(--border)"}`,
                borderRadius: 6, cursor: "pointer", transition: "all 0.15s",
              }}
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3c2.755 0 5.455.232 8.083.678.533.09.917.556.917 1.096v1.044a2.25 2.25 0 0 1-.659 1.591l-5.432 5.432a2.25 2.25 0 0 0-.659 1.591v2.927a2.25 2.25 0 0 1-1.244 2.013L9.75 21v-6.568a2.25 2.25 0 0 0-.659-1.591L3.659 7.409A2.25 2.25 0 0 1 3 5.818V4.774c0-.54.384-1.006.917-1.096A48.32 48.32 0 0 1 12 3Z" />
              </svg>
              필터{activeFilterCount > 0 && ` (${activeFilterCount})`}
            </button>
          </div>
        </div>

        {/* Filter panel */}
        {filterOpen && (
          <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <div style={{
              display: "flex", alignItems: "center",
              border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden",
            }}>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", padding: "0 8px", background: "var(--bg-subtle)", alignSelf: "stretch", display: "flex", alignItems: "center" }}>채널</span>
              <select
                value={channelId}
                onChange={(e) => setChannelId(e.target.value === "" ? "" : Number(e.target.value))}
                style={{
                  padding: "6px 8px", fontSize: 12,
                  background: "var(--bg-elevated)", color: "var(--text-primary)",
                  border: "none", borderLeft: "1px solid var(--border)", outline: "none",
                  minWidth: 140, maxWidth: 220,
                }}
              >
                <option value="">전체</option>
                {channels.map((c) => (
                  <option key={c.id} value={c.id}>
                    @{c.instagram_handle}
                    {c.display_name && c.display_name !== c.instagram_handle ? ` · ${c.display_name}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div style={{
              display: "flex", alignItems: "center",
              border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden",
            }}>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", padding: "0 8px", background: "var(--bg-subtle)", alignSelf: "stretch", display: "flex", alignItems: "center" }}>좋아요</span>
              <input type="number" min="0" placeholder="min" value={minLikes} onChange={(e) => setMinLikes(e.target.value)}
                style={{ width: 72, padding: "6px 8px", fontSize: 12, background: "var(--bg-elevated)", color: "var(--text-primary)", border: "none", borderLeft: "1px solid var(--border)", outline: "none", MozAppearance: "textfield" as never }} />
              <input type="number" min="0" placeholder="max" value={maxLikes} onChange={(e) => setMaxLikes(e.target.value)}
                style={{ width: 72, padding: "6px 8px", fontSize: 12, background: "var(--bg-elevated)", color: "var(--text-primary)", border: "none", borderLeft: "1px solid var(--border)", outline: "none", MozAppearance: "textfield" as never }} />
            </div>

            <div style={{
              display: "flex", alignItems: "center",
              border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden",
            }}>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", padding: "0 8px", background: "var(--bg-subtle)", alignSelf: "stretch", display: "flex", alignItems: "center" }}>댓글</span>
              <input type="number" min="0" placeholder="min" value={minComments} onChange={(e) => setMinComments(e.target.value)}
                style={{ width: 72, padding: "6px 8px", fontSize: 12, background: "var(--bg-elevated)", color: "var(--text-primary)", border: "none", borderLeft: "1px solid var(--border)", outline: "none", MozAppearance: "textfield" as never }} />
              <input type="number" min="0" placeholder="max" value={maxComments} onChange={(e) => setMaxComments(e.target.value)}
                style={{ width: 72, padding: "6px 8px", fontSize: 12, background: "var(--bg-elevated)", color: "var(--text-primary)", border: "none", borderLeft: "1px solid var(--border)", outline: "none", MozAppearance: "textfield" as never }} />
            </div>

            <div style={{
              display: "flex", alignItems: "center",
              border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden",
            }}>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", padding: "0 8px", background: "var(--bg-subtle)", alignSelf: "stretch", display: "flex", alignItems: "center" }}>슬라이드</span>
              <input type="number" min="0" placeholder="min" value={minSlides} onChange={(e) => setMinSlides(e.target.value)}
                style={{ width: 64, padding: "6px 8px", fontSize: 12, background: "var(--bg-elevated)", color: "var(--text-primary)", border: "none", borderLeft: "1px solid var(--border)", outline: "none", MozAppearance: "textfield" as never }} />
              <input type="number" min="0" placeholder="max" value={maxSlides} onChange={(e) => setMaxSlides(e.target.value)}
                style={{ width: 64, padding: "6px 8px", fontSize: 12, background: "var(--bg-elevated)", color: "var(--text-primary)", border: "none", borderLeft: "1px solid var(--border)", outline: "none", MozAppearance: "textfield" as never }} />
            </div>

            <div style={{ width: 1, height: 24, background: "var(--border)" }} />

            {DATE_PRESETS.map((d) => {
              const from = new Date(); from.setDate(from.getDate() - d);
              const to = new Date(); to.setDate(to.getDate() - 1);
              const isoFrom = from.toISOString().slice(0, 10);
              const isoTo = to.toISOString().slice(0, 10);
              const isActive = dateFrom === isoFrom && dateTo === isoTo;
              const label = d === 1 ? "어제" : `최근 ${d}일`;
              return (
                <button
                  key={d}
                  onClick={() => {
                    if (isActive) { setDateFrom(""); setDateTo(""); }
                    else { setDateFrom(isoFrom); setDateTo(isoTo); }
                  }}
                  style={{
                    padding: "5px 10px", fontSize: 12, fontWeight: 500,
                    color: isActive ? "var(--accent-text)" : "var(--text-secondary)",
                    background: isActive ? "var(--accent-muted)" : "transparent",
                    border: `1px solid ${isActive ? "var(--accent)" : "var(--border)"}`,
                    borderRadius: 6, cursor: "pointer", transition: "all 0.15s",
                  }}
                >
                  {label}
                </button>
              );
            })}

            {activeFilterCount > 0 && (
              <>
                <div style={{ width: 1, height: 24, background: "var(--border)" }} />
                <button
                  onClick={clearFilters}
                  style={{
                    padding: "5px 8px", fontSize: 11, color: "var(--text-tertiary)",
                    background: "none", border: "none", cursor: "pointer", textDecoration: "underline",
                  }}
                >
                  초기화
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Table */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", paddingTop: 80 }}>
          <div className="spinner" />
        </div>
      ) : sorted.length === 0 ? (
        <div
          style={{
            border: "1px solid var(--border)", borderRadius: 8,
            padding: "60px 24px", textAlign: "center", background: "var(--bg-subtle)",
          }}
        >
          <p style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500, margin: 0 }}>
            {activeFilterCount > 0 || dQuery ? "조건에 맞는 소재가 없습니다" : "수집된 소재가 없습니다"}
          </p>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>
            {activeFilterCount > 0 || dQuery ? "검색어나 필터를 조정해보세요" : "벤치마크 채널을 추가하고 스크래핑을 실행하세요"}
          </p>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "var(--bg-elevated)", borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: "10px 12px", width: 40 }} aria-label="전체 선택">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    style={{ cursor: "pointer", accentColor: "var(--accent)" }}
                    aria-label="전체 선택"
                  />
                </th>
                <th style={thStyle("left")} onClick={() => toggleSort("caption")}>
                  제목<SortIcon col="caption" />
                </th>
                <th style={thStyle("right", 100)} onClick={() => toggleSort("like_count")}>
                  좋아요<SortIcon col="like_count" />
                </th>
                <th style={thStyle("right", 100)} onClick={() => toggleSort("comment_count")}>
                  댓글<SortIcon col="comment_count" />
                </th>
                <th style={thStyle("right", 90)} onClick={() => toggleSort("slide_count")}>
                  슬라이드<SortIcon col="slide_count" />
                </th>
                <th style={thStyle("right", 110)} onClick={() => toggleSort("post_date")}>
                  발행일<SortIcon col="post_date" />
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((post) => {
                const isSelected = selected.has(post.id);
                const channel = channelMap.get(post.channel_id);
                return (
                  <tr
                    key={post.id}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      cursor: "default",
                      background: isSelected ? "var(--accent-muted)" : "transparent",
                      transition: "background 0.12s",
                    }}
                    onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = "rgba(255,255,255,0.025)"; }}
                    onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.background = "transparent"; }}
                  >
                    <td style={{ padding: "10px 12px", width: 40 }}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleOne(post.id)}
                        style={{ cursor: "pointer", accentColor: "var(--accent)" }}
                      />
                    </td>
                    <td style={{ padding: "10px 16px", color: "var(--text-primary)", maxWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <div
                          onMouseEnter={(e) => onThumbHover(post.id, e)}
                          onMouseLeave={() => onThumbLeave(post.id)}
                          style={{
                            position: "relative",
                            width: 56, height: 70, borderRadius: 4,
                            background: "var(--bg-overlay)", flexShrink: 0, overflow: "visible",
                          }}
                        >
                          <div style={{ width: "100%", height: "100%", borderRadius: 4, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
                            {post.images.length > 0 ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={thumbnailUrl(post.images[0].raw_path, 160)}
                                data-source-url={post.images[0].source_url || ""}
                                data-fallback-tried="0"
                                alt=""
                                loading="lazy"
                                style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                                onError={(e) => {
                                  const el = e.currentTarget as HTMLImageElement;
                                  if (el.dataset.fallbackTried === "0" && el.dataset.sourceUrl) {
                                    el.dataset.fallbackTried = "1";
                                    el.src = proxiedImageUrl(el.dataset.sourceUrl);
                                    return;
                                  }
                                  el.style.display = "none";
                                  el.parentElement!.innerHTML = '<svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke-width="1.2" stroke="#555"><path stroke-linecap="round" stroke-linejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z"/></svg>';
                                }}
                              />
                            ) : (
                              <svg width="20" height="20" fill="none" viewBox="0 0 24 24" strokeWidth={1.2} stroke="#555">
                                <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5A2.25 2.25 0 0 0 22.5 18.75V5.25A2.25 2.25 0 0 0 20.25 3H3.75A2.25 2.25 0 0 0 1.5 5.25v13.5A2.25 2.25 0 0 0 3.75 21Z" />
                              </svg>
                            )}
                          </div>
                          {hoveredThumbId === post.id && hoverPos && post.images.length > 0 && (
                            <div
                              style={{
                                position: "fixed",
                                top: hoverPos.top,
                                left: hoverPos.left,
                                width: POPOVER_W,
                                height: POPOVER_H,
                                borderRadius: 8,
                                background: "var(--bg-elevated)",
                                border: "1px solid var(--border)",
                                boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                                overflow: "hidden",
                                pointerEvents: "none",
                                zIndex: 100,
                              }}
                            >
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img
                                src={thumbnailUrl(post.images[0].raw_path, 480)}
                                data-source-url={post.images[0].source_url || ""}
                                data-fallback-tried="0"
                                alt=""
                                style={{ width: "100%", height: "100%", objectFit: "contain", display: "block", background: "var(--bg-overlay)" }}
                                onError={(e) => {
                                  const el = e.currentTarget as HTMLImageElement;
                                  if (el.dataset.fallbackTried === "0" && el.dataset.sourceUrl) {
                                    el.dataset.fallbackTried = "1";
                                    el.src = proxiedImageUrl(el.dataset.sourceUrl);
                                  }
                                }}
                              />
                            </div>
                          )}
                        </div>
                        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                          <Link
                            href={`/posts/${post.id}`}
                            title={post.caption || undefined}
                            onPointerDown={saveCurrentScroll}
                            onMouseDown={saveCurrentScroll}
                            onClick={saveCurrentScroll}
                            style={{
                              minWidth: 0, margin: 0,
                              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                              color: "var(--text-primary)", textDecoration: "none",
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.textDecoration = "underline"; }}
                            onMouseLeave={(e) => { e.currentTarget.style.textDecoration = "none"; }}
                          >
                            {post.caption || "캡션 없음"}
                          </Link>
                          {channel && (
                            <span style={{ fontSize: 11, color: "var(--text-tertiary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                              @{channel.instagram_handle}
                              {channel.display_name && channel.display_name !== channel.instagram_handle && (
                                <span style={{ color: "var(--text-disabled)" }}> · {channel.display_name}</span>
                              )}
                            </span>
                          )}
                        </div>
                        {post.post_url && (
                          <a
                            href={post.post_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            title="원본 인스타그램 포스트 열기"
                            aria-label="원본 열기"
                            style={{
                              display: "inline-flex", alignItems: "center", justifyContent: "center",
                              width: 28, height: 28,
                              color: "var(--text-tertiary)",
                              background: "var(--bg-overlay)",
                              border: "1px solid var(--border)",
                              borderRadius: 4, textDecoration: "none", flexShrink: 0,
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.color = "var(--text-primary)"; }}
                            onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-tertiary)"; }}
                          >
                            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                            </svg>
                          </a>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "right", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                      {post.like_count.toLocaleString()}
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "right", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                      {post.comment_count.toLocaleString()}
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "right", color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                      {post.slide_count || "-"}
                    </td>
                    <td style={{ padding: "10px 16px", textAlign: "right", color: "var(--text-tertiary)", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                      {post.post_date ? new Date(post.post_date).toLocaleDateString("ko-KR") : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Selection bar */}
      {selected.size > 0 && (
        <div
          style={{
            position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
            display: "flex", alignItems: "center", gap: 8,
            padding: "10px 16px",
            background: "var(--bg-elevated)", border: "1px solid var(--border)",
            borderRadius: 10, boxShadow: "0 4px 24px rgba(0,0,0,0.25)", zIndex: 50,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", marginRight: 4 }}>
            {selected.size}개 선택
          </span>
          <button
            onClick={() => router.push(`/create?refs=${Array.from(selected).join(",")}`)}
            style={{
              padding: "6px 14px", fontSize: 12, fontWeight: 500,
              color: "white", background: "var(--accent)",
              border: "none", borderRadius: 6, cursor: "pointer",
            }}
          >
            캐러셀 생성
          </button>
          <button
            onClick={bulkSaveSelected}
            disabled={bulkSaving}
            style={{
              padding: "6px 14px", fontSize: 12, fontWeight: 500,
              color: "var(--accent-text)", background: "var(--accent-muted)",
              border: "none", borderRadius: 6, cursor: bulkSaving ? "default" : "pointer",
              opacity: bulkSaving ? 0.6 : 1,
            }}
            title="내 소재로 보관 (TTL 면제)"
          >
            {bulkSaving ? "보관 중…" : "내 소재로 보관"}
          </button>
          <button
            onClick={bulkDeleteSelected}
            disabled={bulkDeleting}
            style={{
              padding: "6px 14px", fontSize: 12, fontWeight: 500,
              color: "var(--red)", background: "var(--red-muted)",
              border: "none", borderRadius: 6, cursor: bulkDeleting ? "default" : "pointer",
              opacity: bulkDeleting ? 0.6 : 1,
            }}
          >
            {bulkDeleting ? "삭제 중…" : "삭제"}
          </button>
          <div style={{ width: 1, height: 20, background: "var(--border)", margin: "0 4px" }} />
          <button
            onClick={() => setSelected(new Set())}
            style={{
              padding: "6px 12px", fontSize: 12,
              color: "var(--text-tertiary)", background: "none",
              border: "none", cursor: "pointer",
            }}
          >
            해제
          </button>
        </div>
      )}

      <style jsx>{`
        input[type="number"]::-webkit-inner-spin-button,
        input[type="number"]::-webkit-outer-spin-button {
          -webkit-appearance: none;
          margin: 0;
        }
      `}</style>
    </div>
  );
}
