"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { api, proxiedImageUrl, thumbnailUrl } from "@/lib/api";
import type { Carousel, CarouselListItem } from "@/lib/types";

type Tab = "all" | "draft" | "finalized";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "draft", label: "작업 중" },
  { key: "finalized", label: "완성" },
];

const VALID_TABS: Tab[] = ["all", "draft", "finalized"];

function CarouselThumb({ c }: { c: CarouselListItem }) {
  const imgSrc = c.thumbnail_url || "";
  if (imgSrc) {
    const src = imgSrc.startsWith("http") ? proxiedImageUrl(imgSrc) : thumbnailUrl(imgSrc, 480);
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt="" loading="lazy" style={{ width: "100%", aspectRatio: "1", objectFit: "cover", display: "block" }} />
    );
  }
  return (
    <div style={{
      width: "100%", aspectRatio: "1",
      background: "linear-gradient(135deg, var(--bg-overlay), var(--bg-elevated))",
      display: "flex", alignItems: "center", justifyContent: "center",
      color: "var(--text-tertiary)", fontSize: 12,
    }}>
      미리보기 없음
    </div>
  );
}

function toListItem(c: Carousel): CarouselListItem {
  const cd = (c.canvas_data || {}) as Record<string, unknown>;
  const slides = (cd.canvas_slides as Array<Record<string, unknown>> | undefined) || [];
  let thumbnail_url: string | null = null;
  const first = slides[0];
  if (first && Array.isArray(first.objects)) {
    for (const obj of first.objects as Array<Record<string, unknown>>) {
      const t = String(obj.type || "").toLowerCase();
      if ((t === "image" || t === "fabricimage") && obj.src) {
        thumbnail_url = String(obj.src);
        break;
      }
    }
  }

  return {
    id: c.id,
    user_id: c.user_id,
    source_post_id: c.source_post_id,
    title: c.title,
    template_id: c.template_id,
    status: c.status,
    created_at: c.created_at,
    updated_at: c.updated_at,
    slide_count: slides.length,
    thumbnail_url,
  };
}

export default function WorksPage() {
  const params = useSearchParams();
  const router = useRouter();
  const scrollKey = `works-scroll:${params.toString() || "all"}`;
  const didRestoreScrollRef = useRef(false);
  const initialTab: Tab = (() => {
    const t = params.get("tab");
    return VALID_TABS.includes(t as Tab) ? (t as Tab) : "all";
  })();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [items, setItems] = useState<CarouselListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  // Inline title rename: click the title to switch into edit mode, Enter or
  // blur commits, Esc cancels.
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  // Keep tab in sync with URL — sidebar entry "작업 완료" changes ?tab=finalized,
  // so the page picks it up on subsequent navigations too.
  useEffect(() => {
    const t = params.get("tab");
    if (VALID_TABS.includes(t as Tab) && t !== tab) {
      setTab(t as Tab);
    } else if (!t && tab !== "all") {
      setTab("all");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  function switchTab(t: Tab) {
    setTab(t);
    // Push the new tab into the URL so the sidebar highlight + bookmarking
    // work correctly. shallow=true via router.replace keeps it lightweight.
    if (t === "all") router.replace("/works");
    else router.replace(`/works?tab=${t}`);
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const status = tab === "all" ? undefined : tab === "finalized" ? "finalized" : "draft";
      const data = await api.getCarousels(50, 0, status);
      setItems(data);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    didRestoreScrollRef.current = false;

    function saveScroll() {
      try {
        sessionStorage.setItem(scrollKey, String(window.scrollY || 0));
      } catch {
        /* ignore */
      }
    }

    window.addEventListener("scroll", saveScroll, { passive: true });
    window.addEventListener("beforeunload", saveScroll);
    return () => {
      saveScroll();
      window.removeEventListener("scroll", saveScroll);
      window.removeEventListener("beforeunload", saveScroll);
    };
  }, [scrollKey]);

  useEffect(() => {
    if (loading || didRestoreScrollRef.current) return;
    didRestoreScrollRef.current = true;
    const raw = sessionStorage.getItem(scrollKey);
    const y = raw ? Number(raw) : 0;
    if (!Number.isFinite(y) || y <= 0) return;

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.scrollTo({ top: y, left: 0, behavior: "auto" });
      });
    });
  }, [loading, items.length, scrollKey]);

  function saveCurrentScroll() {
    try {
      sessionStorage.setItem(scrollKey, String(window.scrollY || 0));
    } catch {
      /* ignore */
    }
  }

  function keepInCurrentTab(status: CarouselListItem["status"]) {
    return tab === "all" || (tab === "finalized" ? status === "finalized" : status === "draft");
  }

  async function toggleFinalized(c: CarouselListItem) {
    const next: CarouselListItem["status"] = c.status === "finalized" ? "draft" : "finalized";
    setBusy(c.id);
    const before = items;
    setItems((prev) => {
      const updated = prev.map((it) => (it.id === c.id ? { ...it, status: next } : it));
      return updated.filter((it) => keepInCurrentTab(it.status));
    });
    try {
      await api.updateCarousel(c.id, { status: next });
    } catch (e) {
      setItems(before);
      alert(e instanceof Error ? e.message : "상태 변경 실패");
    } finally {
      setBusy(null);
    }
  }

  async function remove(c: CarouselListItem) {
    if (!confirm(`'${c.title || "(제목 없음)"}' 작업을 삭제하시겠습니까?`)) return;
    setBusy(c.id);
    const beforeItems = items;
    const beforeSelected = selectedIds;
    setItems((prev) => prev.filter((it) => it.id !== c.id));
    setSelectedIds((prev) => {
      if (!prev.has(c.id)) return prev;
      const next = new Set(prev);
      next.delete(c.id);
      return next;
    });
    try {
      await api.deleteCarousel(c.id);
    } catch (e) {
      setItems(beforeItems);
      setSelectedIds(beforeSelected);
      alert(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(null);
    }
  }

  function startRename(c: CarouselListItem) {
    setEditingId(c.id);
    setEditingTitle(c.title || "");
  }
  function cancelRename() {
    setEditingId(null);
    setEditingTitle("");
  }
  async function commitRename(c: CarouselListItem) {
    const next = editingTitle.trim();
    // Empty title or no change → just exit edit mode without a PATCH.
    if (!next || next === (c.title || "")) {
      cancelRename();
      return;
    }
    setBusy(c.id);
    try {
      await api.updateCarousel(c.id, { title: next });
      // Optimistic local update so the new name appears before refetch.
      setItems((prev) => prev.map((it) => (it.id === c.id ? { ...it, title: next } : it)));
      setEditingId(null);
      setEditingTitle("");
    } catch (e) {
      alert(e instanceof Error ? e.message : "이름 변경 실패");
    } finally {
      setBusy(null);
    }
  }

  async function clone(c: CarouselListItem) {
    setBusy(c.id);
    try {
      const cloned = toListItem(await api.cloneCarousel(c.id));
      if (keepInCurrentTab(cloned.status)) {
        setItems((prev) => {
          const sourceIndex = prev.findIndex((it) => it.id === c.id);
          if (sourceIndex < 0) return [cloned, ...prev];
          const next = [...prev];
          next.splice(sourceIndex + 1, 0, cloned);
          return next;
        });
      }
    } catch (e) {
      alert(e instanceof Error ? e.message : "복제 실패");
    } finally {
      setBusy(null);
    }
  }

  function toggleSelected(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  function selectAll() {
    setSelectedIds(new Set(items.map((c) => c.id)));
  }

  async function bulkDelete() {
    if (selectedIds.size === 0 || bulkDeleting) return;
    if (!confirm(`선택된 ${selectedIds.size}개 작업을 삭제하시겠습니까? 되돌릴 수 없습니다.`)) return;
    setBulkDeleting(true);
    const ids = Array.from(selectedIds);
    const idSet = new Set(ids);
    const beforeItems = items;
    setItems((prev) => prev.filter((it) => !idSet.has(it.id)));
    setSelectedIds(new Set());
    const results = await Promise.allSettled(ids.map((id) => api.deleteCarousel(id)));
    const failed = results
      .map((r, i) => (r.status === "rejected" ? ids[i] : null))
      .filter((x): x is number => x !== null);
    setBulkDeleting(false);
    if (failed.length > 0) {
      alert(`${ids.length - failed.length}개 삭제 완료. ${failed.length}개 실패 (ID: ${failed.join(", ")}).`);
    }
    if (failed.length > 0) {
      const failedSet = new Set(failed);
      setItems((prev) => {
        const restored = beforeItems.filter((it) => failedSet.has(it.id));
        const existing = new Set(prev.map((it) => it.id));
        return [...prev, ...restored.filter((it) => !existing.has(it.id))]
          .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      });
    }
    setSelectedIds(new Set(failed));
  }

  // Tab switch invalidates the selection — IDs from the previous list might not
  // exist in the new list, and showing "5개 선택됨" with stale IDs is confusing.
  useEffect(() => { setSelectedIds(new Set()); }, [tab]);

  const finalizedCount = items.filter((c) => c.status === "finalized").length;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--text-primary)" }}>내 작업</h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
          저장된 캐러셀 작업물 목록. 작업 중인 것은 다시 편집하고, 완성한 것은 따로 모아 볼 수 있어요.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, borderBottom: "1px solid var(--border)", marginBottom: 18 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => switchTab(t.key)}
            style={{
              padding: "8px 14px", fontSize: 13, fontWeight: 500,
              color: tab === t.key ? "var(--text-primary)" : "var(--text-tertiary)",
              background: "transparent", border: "none", cursor: "pointer",
              borderBottom: tab === t.key ? "2px solid var(--accent)" : "2px solid transparent",
              marginBottom: -1,
            }}
          >
            {t.label}
            {t.key === "finalized" && finalizedCount > 0 && (
              <span style={{
                marginLeft: 6, padding: "1px 6px", borderRadius: 8,
                fontSize: 10, fontWeight: 600,
                background: "rgba(100,200,150,0.18)", color: "rgb(160,230,190)",
              }}>{finalizedCount}</span>
            )}
          </button>
        ))}
      </div>

      {/* Selection bar (only when list has items) */}
      {!loading && items.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, fontSize: 12, marginBottom: 12, flexWrap: "wrap" }}>
          {selectedIds.size > 0 ? (
            <>
              <span style={{ color: "var(--text-secondary)" }}>{selectedIds.size}개 선택됨</span>
              <button
                onClick={clearSelection}
                disabled={bulkDeleting}
                style={{
                  padding: "5px 12px", fontSize: 12,
                  background: "var(--bg-elevated)", color: "var(--text-secondary)",
                  border: "1px solid var(--border)", borderRadius: 5,
                  cursor: bulkDeleting ? "default" : "pointer",
                  opacity: bulkDeleting ? 0.5 : 1,
                }}
              >
                선택 해제
              </button>
              <button
                onClick={bulkDelete}
                disabled={bulkDeleting}
                style={{
                  padding: "5px 12px", fontSize: 12, fontWeight: 500,
                  background: "var(--red-muted)", color: "var(--red)",
                  border: "none", borderRadius: 5,
                  cursor: bulkDeleting ? "default" : "pointer",
                  opacity: bulkDeleting ? 0.5 : 1,
                }}
              >
                {bulkDeleting ? "삭제 중…" : `선택 삭제 (${selectedIds.size})`}
              </button>
            </>
          ) : (
            <button
              onClick={selectAll}
              style={{
                padding: "5px 12px", fontSize: 12,
                background: "var(--bg-elevated)", color: "var(--text-secondary)",
                border: "1px solid var(--border)", borderRadius: 5,
                cursor: "pointer",
              }}
            >
              전체 선택
            </button>
          )}
        </div>
      )}

      {loading ? (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>로딩 중…</p>
      ) : items.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {tab === "finalized" ? "아직 완성한 작업이 없어요. 에디터에서 ‘완성’으로 표시하세요." : "저장된 작업이 없어요."}
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {items.map((c) => {
            const isFinal = c.status === "finalized";
            const checked = selectedIds.has(c.id);
            return (
              <div
                key={c.id}
                style={{
                  background: "var(--bg-subtle)",
                  border: `1px solid ${checked ? "var(--accent)" : isFinal ? "rgba(100,200,150,0.35)" : "var(--border)"}`,
                  borderRadius: 10, overflow: "hidden",
                  display: "flex", flexDirection: "column",
                  position: "relative",
                }}
              >
                {/* Selection checkbox (overlay over thumbnail) */}
                <label
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    position: "absolute", top: 8, left: 8, zIndex: 2,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    width: 24, height: 24, borderRadius: 4,
                    background: checked ? "var(--accent)" : "rgba(0,0,0,0.55)",
                    border: checked ? "1px solid var(--accent)" : "1px solid rgba(255,255,255,0.35)",
                    cursor: "pointer",
                  }}
                  title={checked ? "선택 해제" : "선택"}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleSelected(c.id)}
                    style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer", margin: 0 }}
                  />
                  {checked && (
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M3 8.5l3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </label>
                <Link href={`/editor/${c.id}`} onClick={saveCurrentScroll} style={{ display: "block", background: "var(--bg-overlay)" }}>
                  <CarouselThumb c={c} />
                </Link>
                <div style={{ padding: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    {editingId === c.id ? (
                      <input
                        autoFocus
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onBlur={() => commitRename(c)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur();
                          else if (e.key === "Escape") cancelRename();
                        }}
                        disabled={busy === c.id}
                        style={{
                          flex: 1, fontSize: 13, fontWeight: 500,
                          color: "var(--text-primary)", background: "var(--bg-overlay)",
                          border: "1px solid var(--accent)", borderRadius: 4,
                          padding: "3px 6px", outline: "none",
                          minWidth: 0,
                        }}
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => startRename(c)}
                        title="이름 변경 (클릭)"
                        style={{
                          flex: 1, minWidth: 0,
                          textAlign: "left", padding: "3px 6px",
                          fontSize: 13, fontWeight: 500,
                          color: "var(--text-primary)",
                          background: "transparent", border: "1px solid transparent",
                          borderRadius: 4, cursor: "text",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-overlay)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        {c.title || "(제목 없음)"}
                      </button>
                    )}
                    {isFinal && (
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: "1px 8px", borderRadius: 8,
                        background: "rgba(100,200,150,0.18)", color: "rgb(160,230,190)",
                      }}>✓ 완성</span>
                    )}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginBottom: 10 }}>
                    {new Date(c.updated_at).toLocaleDateString("ko-KR", { year: "2-digit", month: "2-digit", day: "2-digit" })}
                    · 슬라이드 {c.slide_count || 0}
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <Link
                      href={`/editor/${c.id}`}
                      onClick={saveCurrentScroll}
                      style={{
                        flex: 1, padding: "5px 10px", fontSize: 11, fontWeight: 500,
                        color: "var(--accent-text)", background: "var(--accent-muted)",
                        borderRadius: 4, textDecoration: "none", textAlign: "center",
                      }}
                    >
                      편집
                    </Link>
                    <button
                      onClick={() => toggleFinalized(c)}
                      disabled={busy === c.id}
                      style={{
                        padding: "5px 10px", fontSize: 11, fontWeight: 500,
                        color: isFinal ? "var(--text-secondary)" : "rgb(160,230,190)",
                        background: isFinal ? "var(--bg-elevated)" : "rgba(100,200,150,0.18)",
                        border: isFinal ? "1px solid var(--border)" : "1px solid rgba(100,200,150,0.35)",
                        borderRadius: 4, cursor: "pointer",
                        opacity: busy === c.id ? 0.5 : 1,
                      }}
                    >
                      {isFinal ? "되돌리기" : "✓ 완성"}
                    </button>
                    <button
                      onClick={() => clone(c)}
                      disabled={busy === c.id}
                      title="이 작업을 복제하여 새 작업으로 만들기"
                      style={{
                        padding: "5px 8px", fontSize: 11, fontWeight: 500,
                        color: "var(--text-secondary)", background: "var(--bg-elevated)",
                        border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer",
                        opacity: busy === c.id ? 0.5 : 1,
                      }}
                    >
                      복제
                    </button>
                    <button
                      onClick={() => remove(c)}
                      disabled={busy === c.id}
                      style={{
                        padding: "5px 8px", fontSize: 11,
                        color: "var(--red)", background: "var(--red-muted)",
                        border: "none", borderRadius: 4, cursor: "pointer",
                        opacity: busy === c.id ? 0.5 : 1,
                      }}
                    >
                      삭제
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
