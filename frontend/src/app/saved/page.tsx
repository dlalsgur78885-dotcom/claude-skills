"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, resolveImageUrl } from "@/lib/api";
import type { Post, Channel } from "@/lib/types";

export default function SavedPage() {
  const [posts, setPosts] = useState<Post[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPosts(await api.getSavedPosts(200, 0));
    } catch {
      setPosts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    api.getChannels().then(setChannels).catch(() => setChannels([]));
  }, [load]);

  const channelMap = new Map<number, Channel>();
  for (const c of channels) channelMap.set(c.id, c);

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    if (selected.size === posts.length) setSelected(new Set());
    else setSelected(new Set(posts.map((p) => p.id)));
  }

  async function bulkRemoveFromSaved() {
    if (selected.size === 0 || busy) return;
    if (!confirm(`선택한 ${selected.size}개를 내 소재에서 빼시겠습니까?\n수집된 소재로 돌아갑니다 (5일 TTL 적용).`)) return;
    setBusy(true);
    const ids = Array.from(selected);
    await Promise.allSettled(ids.map((id) => api.unsavePost(id)));
    setBusy(false);
    setSelected(new Set());
    load();
  }

  async function bulkDeleteSelected() {
    if (selected.size === 0 || busy) return;
    if (!confirm(`선택한 ${selected.size}개 소재를 완전히 삭제할까요?\n이 소재로 만든 캐러셀 작업은 보존됩니다 (되돌릴 수 없음).`)) return;
    setBusy(true);
    const ids = Array.from(selected);
    await Promise.allSettled(ids.map((id) => api.deletePost(id)));
    setBusy(false);
    setSelected(new Set());
    load();
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 960, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
            내 소재
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 4 }}>
            보관한 소재는 자동 삭제되지 않습니다
            {!loading && <span style={{ marginLeft: 8, color: "var(--text-secondary)" }}>{posts.length}개</span>}
          </p>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", paddingTop: 80 }}>
          <div className="spinner" />
        </div>
      ) : posts.length === 0 ? (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "60px 24px", textAlign: "center", background: "var(--bg-subtle)" }}>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500, margin: 0 }}>보관한 소재가 없습니다</p>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>
            <Link href="/posts" style={{ color: "var(--accent-text)" }}>수집된 소재</Link>에서 보관하고 싶은 소재를 선택해 추가하세요
          </p>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "var(--bg-subtle)", borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: "10px 0 10px 16px", width: 36 }}>
                  <input
                    type="checkbox"
                    checked={posts.length > 0 && selected.size === posts.length}
                    ref={(el) => { if (el) el.indeterminate = selected.size > 0 && selected.size < posts.length; }}
                    onChange={toggleAll}
                    style={{ cursor: "pointer", accentColor: "var(--accent)" }}
                  />
                </th>
                <th style={{ textAlign: "left", padding: "10px 16px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: 70 }}>썸네일</th>
                <th style={{ textAlign: "left", padding: "10px 12px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12 }}>제목</th>
                <th style={{ textAlign: "left", padding: "10px 12px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: 140 }}>채널</th>
                <th style={{ textAlign: "right", padding: "10px 12px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: 80 }}>좋아요</th>
                <th style={{ textAlign: "right", padding: "10px 16px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: 110 }}>보관일</th>
              </tr>
            </thead>
            <tbody>
              {posts.map((p) => {
                const ch = channelMap.get(p.channel_id);
                const thumb = p.images?.[0];
                const isSel = selected.has(p.id);
                return (
                  <tr
                    key={p.id}
                    style={{ borderBottom: "1px solid var(--border)", background: isSel ? "var(--accent-muted)" : "transparent", transition: "background 0.12s" }}
                    onMouseEnter={(e) => { if (!isSel) e.currentTarget.style.background = "var(--bg-subtle)"; }}
                    onMouseLeave={(e) => { if (!isSel) e.currentTarget.style.background = "transparent"; }}
                  >
                    <td style={{ padding: "10px 0 10px 16px" }}>
                      <input
                        type="checkbox"
                        checked={isSel}
                        onChange={() => toggleOne(p.id)}
                        style={{ cursor: "pointer", accentColor: "var(--accent)" }}
                      />
                    </td>
                    <td style={{ padding: "8px 16px" }}>
                      {thumb && (
                        <Link href={`/posts/${p.id}`} style={{ display: "block" }}>
                          <div style={{
                            width: 48, height: 48, borderRadius: 5,
                            background: `var(--bg-overlay) center/cover no-repeat`,
                            backgroundImage: `url("${resolveImageUrl(thumb.processed_path || thumb.raw_path || thumb.source_url || "")}")`,
                            border: "1px solid var(--border)",
                          }} />
                        </Link>
                      )}
                    </td>
                    <td style={{ padding: "12px 12px", color: "var(--text-primary)" }}>
                      <Link href={`/posts/${p.id}`} style={{ color: "inherit", textDecoration: "none" }}>
                        {p.caption ? p.caption.slice(0, 80) : <span style={{ color: "var(--text-tertiary)" }}>(제목 없음)</span>}
                      </Link>
                    </td>
                    <td style={{ padding: "12px 12px", color: "var(--text-secondary)" }}>
                      {ch ? `@${ch.instagram_handle}` : "-"}
                    </td>
                    <td style={{ padding: "12px 12px", textAlign: "right", color: "var(--text-secondary)" }}>
                      {p.like_count.toLocaleString()}
                    </td>
                    <td style={{ padding: "12px 16px", textAlign: "right", color: "var(--text-tertiary)", fontSize: 12 }}>
                      {p.saved_at ? new Date(p.saved_at).toLocaleDateString("ko-KR") : "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected.size > 0 && (
        <div style={{
          position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)",
          display: "flex", alignItems: "center", gap: 8,
          padding: "10px 16px",
          background: "var(--bg-elevated)", border: "1px solid var(--border)",
          borderRadius: 10, boxShadow: "0 4px 24px rgba(0,0,0,0.25)", zIndex: 50,
        }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", marginRight: 4 }}>
            {selected.size}개 선택
          </span>
          <button
            onClick={() => router.push(`/create?refs=${Array.from(selected).join(",")}`)}
            style={{ padding: "6px 14px", fontSize: 12, fontWeight: 500, color: "white", background: "var(--accent)", border: "none", borderRadius: 6, cursor: "pointer" }}
          >
            캐러셀 생성
          </button>
          <button
            onClick={bulkRemoveFromSaved}
            disabled={busy}
            style={{ padding: "6px 14px", fontSize: 12, fontWeight: 500, color: "var(--text-secondary)", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}
            title="내 소재에서 빼서 수집된 소재로 되돌림 (5일 TTL 다시 적용)"
          >
            내 소재에서 빼기
          </button>
          <button
            onClick={bulkDeleteSelected}
            disabled={busy}
            style={{ padding: "6px 14px", fontSize: 12, fontWeight: 500, color: "var(--red)", background: "var(--red-muted)", border: "none", borderRadius: 6, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}
          >
            삭제
          </button>
          <div style={{ width: 1, height: 20, background: "var(--border)", margin: "0 4px" }} />
          <button
            onClick={() => setSelected(new Set())}
            style={{ padding: "6px 12px", fontSize: 12, color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer" }}
          >
            해제
          </button>
        </div>
      )}
    </div>
  );
}
