"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, resolveImageUrl, proxiedImageUrl } from "@/lib/api";
import type { ElementEditItem, Post, PostElements, PostUsageJob } from "@/lib/types";

// raw_path may be either a local /api/images/raw/... path (backend has it
// downloaded) OR a remote Instagram CDN URL (the post was ingested but the
// images weren't pinned locally — expires fast / CORS-blocked). Always send
// remote URLs through the backend image proxy so they actually render.
function imgSrc(raw?: string | null): string {
  if (!raw) return "";
  if (raw.startsWith("/")) return resolveImageUrl(raw);
  if (raw.startsWith("http")) return proxiedImageUrl(raw);
  return raw;
}

const STAGE_LABEL: Record<string, string> = {
  queued: "대기 중",
  download: "슬라이드 다운로드 중",
  analyze: "이미지 분석·요소 추출 중",
  awaiting_review: "검토 대기",
  collect: "이미지 수집 중",
  done: "완료",
};

type EditRow = ElementEditItem & { tempKey: string };

function rowFromElement(e: { id: number; name: string; search_query: string; selected: boolean }): EditRow {
  return { id: e.id, name: e.name, search_query: e.search_query, selected: e.selected, tempKey: `db-${e.id}` };
}

export default function PostDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const postId = Number(params?.id);

  const [post, setPost] = useState<Post | null>(null);
  const [data, setData] = useState<PostElements | null>(null);
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [edits, setEdits] = useState<EditRow[]>([]);
  const [editingActive, setEditingActive] = useState(false);
  const pollRef = useRef<number | null>(null);

  const load = useCallback(async () => {
    if (!postId) return;
    try {
      const [p, els] = await Promise.all([
        api.getPost(postId),
        api.getPostElements(postId).catch(() => ({ job: null, elements: [] }) as PostElements),
      ]);
      setPost(p);
      setData(els);
    } catch (e) {
      setError(e instanceof Error ? e.message : "로드 실패");
    }
  }, [postId]);

  useEffect(() => { load(); }, [load]);

  // Whenever elements load and pipeline is awaiting review, prime the editor.
  useEffect(() => {
    if (!data) return;
    if (data.job?.status === "awaiting_review") {
      setEdits(data.elements.map(rowFromElement));
      setEditingActive(true);
    } else if (data.job?.status === "running" || data.job?.status === "pending") {
      setEditingActive(false);
    }
  }, [data]);

  useEffect(() => {
    const job = data?.job;
    if (!job) return;
    if (job.status === "running" || job.status === "pending") {
      pollRef.current = window.setTimeout(load, 2500);
      return () => {
        if (pollRef.current) window.clearTimeout(pollRef.current);
      };
    }
  }, [data?.job, load]);

  async function triggerAnalyze() {
    setBusy(true);
    setError("");
    try {
      await api.triggerUsePost(postId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "분석 트리거 실패");
    } finally {
      setBusy(false);
    }
  }

  async function saveAndCollect() {
    setBusy(true);
    setError("");
    try {
      const payload = edits
        .filter((r) => r.name.trim())
        .map(({ id, name, search_query, selected }) => ({ id, name, search_query, selected }));
      await api.editElements(postId, payload);
      const anySelected = payload.some((r) => r.selected);
      if (!anySelected) {
        throw new Error("선택된 요소가 없습니다");
      }
      await api.triggerCollect(postId);
      setEditingActive(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "수집 시작 실패");
    } finally {
      setBusy(false);
    }
  }

  function updateRow(key: string, patch: Partial<EditRow>) {
    setEdits((rows) => rows.map((r) => (r.tempKey === key ? { ...r, ...patch } : r)));
  }

  function removeRow(key: string) {
    setEdits((rows) => rows.filter((r) => r.tempKey !== key));
  }

  function addRow() {
    setEdits((rows) => [
      ...rows,
      { name: "", search_query: "", selected: true, tempKey: `new-${Date.now()}-${rows.length}` },
    ]);
  }

  if (!postId) return null;

  const job: PostUsageJob | null = data?.job ?? null;
  const isRunning = job?.status === "running" || job?.status === "pending";
  const isAwaiting = job?.status === "awaiting_review";
  const elements = data?.elements ?? [];

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, minWidth: 0 }}>
          <button
            onClick={() => router.back()}
            title="뒤로가기"
            aria-label="뒤로가기"
            style={{
              flexShrink: 0,
              marginTop: 2,
              padding: "6px 10px",
              fontSize: 12, fontWeight: 500,
              color: "var(--text-secondary)",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: 4,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--border-strong, var(--text-tertiary))"; e.currentTarget.style.color = "var(--text-primary)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--text-secondary)"; }}
          >
            ← 뒤로
          </button>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.02em" }}>
            {post?.caption ? (post.caption.length > 80 ? post.caption.slice(0, 80) + "…" : post.caption) : "게시물"}
          </h1>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>
            {post && (
              <>
                슬라이드 {post.slide_count}장 · 좋아요 {post.like_count.toLocaleString()} · 댓글 {post.comment_count.toLocaleString()}
                {post.post_url && (
                  <>
                    {" · "}
                    <a href={post.post_url} target="_blank" rel="noreferrer" style={{ color: "var(--text-secondary)", textDecoration: "underline" }}>원본 보기</a>
                  </>
                )}
              </>
            )}
          </p>
        </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          {/* Direct shortcut to /create with this post as a reference. Lets the
              user skip the elements pipeline and jump straight to carousel
              generation. */}
          <Link
            href={`/create?refs=${postId}`}
            style={{
              padding: "8px 16px", fontSize: 13, fontWeight: 600,
              color: "white",
              background: "var(--accent)",
              border: "none", borderRadius: 6,
              textDecoration: "none",
              whiteSpace: "nowrap",
              display: "inline-flex", alignItems: "center", gap: 4,
            }}
          >
            ✨ 이 소재로 캐러셀 만들기
          </Link>
          <button
            onClick={triggerAnalyze}
            disabled={busy || isRunning}
            style={{
              padding: "8px 16px", fontSize: 13, fontWeight: 500,
              color: "var(--text-secondary)",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)", borderRadius: 6,
              cursor: busy || isRunning ? "default" : "pointer",
              whiteSpace: "nowrap",
              opacity: busy || isRunning ? 0.6 : 1,
            }}
          >
            {isRunning
              ? STAGE_LABEL[job?.stage ?? ""] || "처리 중…"
              : isAwaiting
                ? "다시 분석"
                : job?.status === "done"
                  ? "다시 분석"
                  : "요소 분석"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: 6, background: "rgba(220,38,38,0.1)", color: "#f87171", fontSize: 12 }}>
          {error}
        </div>
      )}

      {job?.status === "failed" && job.error && (
        <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: 6, background: "rgba(220,38,38,0.1)", color: "#f87171", fontSize: 12 }}>
          파이프라인 실패: {job.error}
        </div>
      )}

      {/* 슬라이드 미리보기 */}
      <section style={{ marginBottom: 32 }}>
        <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8, letterSpacing: "-0.01em" }}>슬라이드</h2>
        <div style={{ display: "flex", gap: 8, overflowX: "auto", padding: "4px 0" }}>
          {post?.images.map((img) => (
            <div
              key={img.id}
              style={{
                flexShrink: 0, width: 160, height: 200,
                background: "var(--bg-overlay)", borderRadius: 6, overflow: "hidden",
                border: "1px solid var(--border)",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imgSrc(img.raw_path)}
                alt={`슬라이드 ${img.slide_index + 1}`}
                loading="lazy"
                onError={(e) => {
                  const el = e.currentTarget as HTMLImageElement;
                  // Fallback chain: raw_path 404 (locally cached file was
                  // wiped by cleanup) → try source_url (original Instagram
                  // CDN, routed through the proxy). If that also fails,
                  // dim the placeholder so the user knows it's broken.
                  const fallback = img.source_url ? imgSrc(img.source_url) : "";
                  if (fallback && el.dataset.fellBack !== "1") {
                    el.dataset.fellBack = "1";
                    el.src = fallback;
                  } else {
                    el.style.opacity = "0.3";
                  }
                }}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            </div>
          ))}
        </div>
      </section>

      {/* 검토/편집 모드 — analyze 끝나고 collect 시작 전 */}
      {isAwaiting && editingActive && (
        <section style={{ marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", margin: 0, letterSpacing: "-0.01em" }}>
              요소 검토 · 키워드 설정
              <span style={{ marginLeft: 8, color: "var(--text-tertiary)", fontWeight: 400 }}>
                선택 {edits.filter((r) => r.selected).length} / 전체 {edits.length}
              </span>
            </h2>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {edits.map((row) => (
              <div
                key={row.tempKey}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr 1.5fr auto",
                  gap: 8,
                  alignItems: "center",
                  padding: "8px 12px",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  background: row.selected ? "var(--bg-elevated)" : "var(--bg-subtle)",
                  opacity: row.selected ? 1 : 0.55,
                }}
              >
                <input
                  type="checkbox"
                  checked={row.selected}
                  onChange={(e) => updateRow(row.tempKey, { selected: e.target.checked })}
                  style={{ width: 16, height: 16, cursor: "pointer" }}
                />
                <input
                  type="text"
                  value={row.name}
                  placeholder="요소 이름"
                  onChange={(e) => updateRow(row.tempKey, { name: e.target.value })}
                  style={{
                    fontSize: 13, fontWeight: 500, color: "var(--text-primary)",
                    background: "transparent", border: "none", outline: "none",
                    padding: "4px 0",
                  }}
                />
                <input
                  type="text"
                  value={row.search_query}
                  placeholder="이미지 검색어 (한국어 OK)"
                  onChange={(e) => updateRow(row.tempKey, { search_query: e.target.value })}
                  style={{
                    fontSize: 13, color: "var(--text-secondary)",
                    background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 4,
                    padding: "4px 8px", outline: "none",
                  }}
                />
                <button
                  onClick={() => removeRow(row.tempKey)}
                  title="삭제"
                  style={{
                    background: "transparent", border: "none", color: "var(--text-tertiary)",
                    cursor: "pointer", fontSize: 16, lineHeight: 1, padding: "4px 8px",
                  }}
                >×</button>
              </div>
            ))}

            <button
              onClick={addRow}
              style={{
                padding: "8px 12px", fontSize: 12, color: "var(--text-secondary)",
                background: "transparent", border: "1px dashed var(--border)", borderRadius: 6,
                cursor: "pointer",
              }}
            >+ 요소 추가</button>
          </div>

          <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button
              onClick={saveAndCollect}
              disabled={busy || !edits.some((r) => r.selected && r.name.trim())}
              style={{
                padding: "10px 18px", fontSize: 13, fontWeight: 500, color: "white",
                background: busy ? "var(--bg-overlay)" : "var(--accent)",
                border: "none", borderRadius: 6,
                cursor: busy ? "default" : "pointer",
              }}
            >
              {busy ? "처리 중…" : "선택한 요소로 이미지 수집 시작"}
            </button>
          </div>
        </section>
      )}

      {/* 수집 결과 풀 — collect 끝나면 표시 */}
      <section>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-secondary)", margin: 0, letterSpacing: "-0.01em" }}>
            추출된 요소
            {elements.length > 0 && <span style={{ marginLeft: 8, color: "var(--text-tertiary)", fontWeight: 400 }}>{elements.length}개</span>}
          </h2>
          {job?.finished_at && (
            <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
              {new Date(job.finished_at).toLocaleString("ko-KR")}
            </span>
          )}
        </div>

        {elements.length === 0 ? (
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "40px 20px", textAlign: "center", background: "var(--bg-subtle)" }}>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: 0 }}>
              {isRunning ? STAGE_LABEL[job?.stage ?? ""] || "처리 중…" : "아직 분석 결과가 없습니다. ‘이 게시물 쓸게요’ 버튼을 눌러주세요."}
            </p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {elements.map((el) => (
              <div key={el.id} style={{
                border: "1px solid var(--border)", borderRadius: 8, padding: 16,
                background: "var(--bg-elevated)", opacity: el.selected ? 1 : 0.55,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                  <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                    {el.name}
                    {!el.selected && <span style={{ fontSize: 11, color: "var(--text-tertiary)", marginLeft: 8, fontWeight: 400 }}>(미선택)</span>}
                  </h3>
                  <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>검색어: {el.search_query}</span>
                </div>
                {el.source_text && (
                  <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: "0 0 12px 0", fontStyle: "italic" }}>
                    “{el.source_text}”
                  </p>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))", gap: 6 }}>
                  {el.images.length === 0 ? (
                    <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>수집된 이미지 없음</span>
                  ) : el.images.map((img) => (
                    <a
                      key={img.id}
                      href={img.source_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ position: "relative", display: "block", aspectRatio: "1 / 1", background: "var(--bg-overlay)", borderRadius: 4, overflow: "hidden", border: "1px solid var(--border)" }}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={imgSrc(img.url || img.thumbnail_url)}
                        alt={el.name}
                        loading="lazy"
                        style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                      />
                      {img.quality_score > 0 && (
                        <span style={{
                          position: "absolute", top: 4, right: 4,
                          padding: "1px 6px", borderRadius: 3,
                          fontSize: 10, fontWeight: 600,
                          background: "rgba(0,0,0,0.6)", color: "white",
                        }}>{Math.round(img.quality_score)}</span>
                      )}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
