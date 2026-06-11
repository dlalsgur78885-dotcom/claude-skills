"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type LayoutHint } from "@/lib/api";
import type { TemplateSummary } from "@/lib/types";
import { TemplateThumbnail } from "@/components/template-editor/TemplateThumbnail";
import { TemplatePreviewModal } from "@/components/template-editor/TemplatePreviewModal";
import { displayLayoutName } from "@/components/template-editor/types";
import { SlideClassifier } from "@/components/template-editor/SlideClassifier";

export default function TemplatesPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const [postUrl, setPostUrl] = useState("");
  const [name, setName] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState<TemplateSummary | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [previewing, setPreviewing] = useState<TemplateSummary | null>(null);
  const [slideUrls, setSlideUrls] = useState<string[]>([]);
  const [hints, setHints] = useState<LayoutHint[]>([]);
  const [loadingPreview, setLoadingPreview] = useState(false);

  async function loadPreview() {
    if (!postUrl.trim() || loadingPreview) return;
    setLoadingPreview(true);
    setError("");
    try {
      const res = await api.previewSlides(postUrl.trim());
      setSlideUrls(res.slide_urls);
      setHints(res.slide_urls.map((_, i) => ({ slide_index: i, kind: "single" })));
    } catch (err) {
      setError(err instanceof Error ? err.message : "미리보기 실패");
    } finally {
      setLoadingPreview(false);
    }
  }

  function resetPreview() {
    setSlideUrls([]);
    setHints([]);
  }

  async function clone(t: TemplateSummary) {
    setBusy(t.id);
    try {
      const cloned = await api.cloneTemplate(t.id);
      router.push(`/templates/${cloned.id}/edit`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "복제 실패");
    } finally {
      setBusy(null);
    }
  }

  async function remove(t: TemplateSummary) {
    if (!confirm(`'${t.name}' 템플릿을 삭제하시겠습니까?`)) return;
    setBusy(t.id);
    try {
      await api.deleteTemplate(t.id);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "삭제 실패");
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
    setSelectedIds(new Set(templates.map((t) => t.id)));
  }

  async function bulkDelete() {
    if (selectedIds.size === 0 || bulkDeleting) return;
    if (!confirm(`선택된 ${selectedIds.size}개 템플릿을 삭제하시겠습니까? 되돌릴 수 없습니다.`)) return;
    setBulkDeleting(true);
    // Per-id results so one failure doesn't abort the rest (Promise.all would).
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => api.deleteTemplate(id)));
    const failed = results
      .map((r, i) => (r.status === "rejected" ? ids[i] : null))
      .filter((x): x is number => x !== null);
    setBulkDeleting(false);
    if (failed.length > 0) {
      alert(`${ids.length - failed.length}개 삭제 완료. ${failed.length}개 실패 (ID: ${failed.join(", ")}).`);
    }
    // Keep failed ids in the selection so the user can retry; drop successes.
    setSelectedIds(new Set(failed));
    load();
  }

  // ─── Sharing ───
  const [shareModal, setShareModal] = useState<{ template: TemplateSummary; url: string } | null>(null);
  async function share(t: TemplateSummary) {
    setBusy(t.id);
    try {
      const res = await api.shareTemplate(t.id);
      const absolute = `${window.location.origin}${res.share_url}`;
      setShareModal({ template: { ...t, share_code: res.share_code, is_public: res.is_public }, url: absolute });
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "공유 실패");
    } finally {
      setBusy(null);
    }
  }
  async function unshare(t: TemplateSummary) {
    if (!confirm("공유를 해제하면 기존 링크는 작동하지 않습니다. 계속할까요?")) return;
    setBusy(t.id);
    try {
      await api.unshareTemplate(t.id);
      setShareModal(null);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "공유 해제 실패");
    } finally {
      setBusy(null);
    }
  }

  // 공유 코드/링크로 가져오기
  const [importCode, setImportCode] = useState("");
  const [importing, setImporting] = useState(false);
  async function importByCode() {
    const raw = importCode.trim();
    if (!raw || importing) return;
    // Accept either bare code or full /templates/import?code=XXX URL
    let code = raw;
    const m = raw.match(/[?&]code=([^&\s]+)/);
    if (m) code = decodeURIComponent(m[1]);
    setImporting(true);
    try {
      const cloned = await api.cloneTemplateByShareCode(code);
      setImportCode("");
      load();
      alert(`'${cloned.name}' 가져오기 완료`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "가져오기 실패");
    } finally {
      setImporting(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const data = await api.listTemplates();
      setTemplates(data.templates);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    if (!postUrl.trim() || !name.trim() || generating) return;
    if (slideUrls.length === 0) return;
    // 없음이 기본값 — 추출할 슬라이드를 하나도 분류하지 않으면 막는다 (피드백 13-4).
    if (!hints.some((h) => h.kind !== "none")) {
      setError("최소 1개 슬라이드의 레이아웃(단일/그리드)을 분류해주세요");
      return;
    }
    setGenerating(true);
    setError("");
    setLastResult(null);
    try {
      const res = await api.generateTemplate({
        post_url: postUrl.trim(),
        template_name: name.trim(),
        layout_hints: hints,
      });
      setLastResult(res);
      setPostUrl("");
      setName("");
      resetPreview();
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "템플릿 생성 실패");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--text-primary)" }}>
          템플릿 스튜디오
        </h1>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginTop: 4 }}>
          벤치마크 인스타그램 게시글 URL을 넣으면 AI Vision(Gemini 3.1 Pro + Claude Sonnet 4)이 분석해서 재사용 가능한 템플릿을 만들어줍니다.
          채널당 한 번만 만들면 그 채널의 모든 새 포스트는 추가 비전 호출 없이 동일 템플릿으로 처리됩니다.
        </p>
      </div>

      {/* Generator */}
      <div
        className="mb-8 p-5 rounded-lg"
        style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}
      >
        <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 12 }}>
          새 템플릿 생성
        </h2>
        <form onSubmit={generate} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              인스타그램 게시글 URL
            </label>
            <input
              type="url"
              value={postUrl}
              onChange={(e) => setPostUrl(e.target.value)}
              placeholder="https://www.instagram.com/p/DXItkDNEZTj/"
              required
              className="px-3 py-2 rounded-md"
              style={{
                background: "var(--bg-base)",
                border: "1px solid var(--border)",
                fontSize: 13,
                color: "var(--text-primary)",
              }}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              템플릿 이름
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 트립앤라이프 스타일"
              required
              className="px-3 py-2 rounded-md"
              style={{
                background: "var(--bg-base)",
                border: "1px solid var(--border)",
                fontSize: 13,
                color: "var(--text-primary)",
              }}
            />
          </div>
          {slideUrls.length > 0 && (
            <div style={{ marginTop: 8, padding: 12, background: "var(--bg-base)", border: "1px solid var(--border)", borderRadius: 6 }}>
              <SlideClassifier slideUrls={slideUrls} hints={hints} onChange={setHints} />
            </div>
          )}
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {slideUrls.length === 0 ? (
              <button
                type="button"
                onClick={loadPreview}
                disabled={loadingPreview || !postUrl.trim()}
                className="px-4 py-2 rounded-md transition-opacity"
                style={{
                  background: "var(--accent)",
                  color: "white",
                  fontSize: 13,
                  fontWeight: 500,
                  opacity: loadingPreview || !postUrl.trim() ? 0.5 : 1,
                  cursor: loadingPreview ? "not-allowed" : "pointer",
                }}
              >
                {loadingPreview ? "슬라이드 불러오는 중…" : "1단계: 슬라이드 미리보기"}
              </button>
            ) : (
              <>
                <button
                  type="submit"
                  disabled={generating}
                  className="px-4 py-2 rounded-md transition-opacity"
                  style={{
                    background: "var(--accent)",
                    color: "white",
                    fontSize: 13,
                    fontWeight: 500,
                    opacity: generating ? 0.6 : 1,
                    cursor: generating ? "not-allowed" : "pointer",
                  }}
                >
                  {generating ? "AI 분석 중… (30~60초)" : "2단계: 템플릿 생성"}
                </button>
                <button
                  type="button"
                  onClick={resetPreview}
                  disabled={generating}
                  style={{
                    padding: "8px 14px",
                    background: "var(--bg-elevated)",
                    color: "var(--text-secondary)",
                    border: "1px solid var(--border)",
                    borderRadius: 5,
                    fontSize: 12,
                    cursor: generating ? "default" : "pointer",
                  }}
                >
                  다시
                </button>
              </>
            )}
            {error && (
              <span style={{ fontSize: 12, color: "#e85b5b" }}>{error}</span>
            )}
          </div>
        </form>

        {lastResult && (
          <div
            className="mt-4 p-3 rounded-md"
            style={{
              background: "rgba(0, 200, 100, 0.06)",
              border: "1px solid rgba(0, 200, 100, 0.25)",
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
              ✓ 생성 완료: {lastResult.name}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
              레이아웃: {lastResult.layouts.map(displayLayoutName).join(", ")}
            </div>
          </div>
        )}
      </div>

      {/* Import-by-share-code */}
      <div
        className="mb-6 p-4 rounded-lg"
        style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}
      >
        <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
          공유받기
        </h2>
        <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 8 }}>
          다른 사용자가 공유한 템플릿 링크나 코드를 붙여넣으면 내 라이브러리에 복사됩니다.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            type="text"
            value={importCode}
            onChange={(e) => setImportCode(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); importByCode(); } }}
            placeholder="공유 링크 또는 코드 (예: /templates/import?code=abc123)"
            style={{
              flex: 1, padding: "8px 12px", fontSize: 13,
              background: "var(--bg-base)", color: "var(--text-primary)",
              border: "1px solid var(--border)", borderRadius: 6, outline: "none",
              fontFamily: "monospace",
            }}
          />
          <button
            onClick={importByCode}
            disabled={importing || !importCode.trim()}
            style={{
              padding: "8px 16px", fontSize: 12, fontWeight: 500,
              color: "white", background: "var(--accent)",
              border: "none", borderRadius: 6,
              cursor: importing || !importCode.trim() ? "default" : "pointer",
              opacity: importing || !importCode.trim() ? 0.5 : 1,
              whiteSpace: "nowrap",
            }}
          >
            {importing ? "가져오는 중…" : "가져오기"}
          </button>
        </div>
      </div>

      {/* List */}
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
            저장된 템플릿 {templates.length > 0 && `(${templates.length})`}
          </h2>
          {templates.length > 0 && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
              {selectedIds.size > 0 ? (
                <>
                  <span style={{ color: "var(--text-secondary)" }}>
                    {selectedIds.size}개 선택됨
                  </span>
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
        </div>

        {loading ? (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>로딩 중...</p>
        ) : templates.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            아직 템플릿이 없습니다. 위에서 첫 템플릿을 생성하세요.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((t) => {
              const checked = selectedIds.has(t.id);
              return (
              <div
                key={t.id}
                className="rounded-lg overflow-hidden"
                style={{
                  background: "var(--bg-subtle)",
                  border: checked ? "1px solid var(--accent)" : "1px solid var(--border)",
                  display: "flex",
                  flexDirection: "column",
                  position: "relative",
                }}
              >
                {/* Selection checkbox (overlay) */}
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
                    onChange={() => toggleSelected(t.id)}
                    style={{
                      position: "absolute", inset: 0, opacity: 0, cursor: "pointer", margin: 0,
                    }}
                  />
                  {checked && (
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M3 8.5l3 3 7-7" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </label>

                {/* Thumbnail (clickable → preview) */}
                <button
                  onClick={() => setPreviewing(t)}
                  style={{
                    background: "var(--bg-overlay)",
                    border: "none",
                    padding: 12,
                    display: "flex",
                    justifyContent: "center",
                    cursor: "pointer",
                    borderBottom: "1px solid var(--border)",
                  }}
                  title="전체 레이아웃 미리보기"
                >
                  <TemplateThumbnail templateId={t.id} size={220} />
                </button>

                {/* Body */}
                <div style={{ padding: 14 }}>
                  <div className="flex items-start justify-between gap-2">
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                        {t.name}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>
                        {t.slug}
                      </div>
                    </div>
                    <span
                      className="px-2 py-0.5 rounded"
                      style={{
                        fontSize: 10,
                        background:
                          t.created_by === "gemini_vision"
                            ? "rgba(120, 100, 255, 0.15)"
                            : "rgba(255, 255, 255, 0.06)",
                        color:
                          t.created_by === "gemini_vision"
                            ? "rgb(180, 165, 255)"
                            : "var(--text-secondary)",
                      }}
                    >
                      {t.created_by === "gemini_vision" ? "AI 생성" : t.created_by === "manual" ? "수동" : "시스템"}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 8 }}>
                    {t.layouts.map(displayLayoutName).join(", ") || "레이아웃 없음"}
                  </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                  {t.user_id !== null ? (
                    <>
                      <Link
                        href={`/templates/${t.id}/edit`}
                        style={{
                          fontSize: 11,
                          padding: "3px 10px",
                          borderRadius: 4,
                          background: "var(--accent-muted)",
                          color: "var(--accent-text)",
                          textDecoration: "none",
                        }}
                      >
                        편집
                      </Link>
                      <button
                        disabled={busy === t.id}
                        onClick={() => share(t)}
                        title={t.is_public ? "공유 링크 보기" : "공유 링크 만들기"}
                        style={{
                          fontSize: 11,
                          padding: "3px 10px",
                          borderRadius: 4,
                          background: t.is_public ? "rgba(100,200,150,0.18)" : "var(--bg-overlay)",
                          color: t.is_public ? "rgb(160,230,190)" : "var(--text-secondary)",
                          border: t.is_public ? "1px solid rgba(100,200,150,0.35)" : "1px solid var(--border)",
                          cursor: "pointer",
                          opacity: busy === t.id ? 0.5 : 1,
                        }}
                      >
                        {t.is_public ? "🔗 공유됨" : "🔗 공유"}
                      </button>
                      <button
                        disabled={busy === t.id}
                        onClick={() => remove(t)}
                        style={{
                          fontSize: 11,
                          padding: "3px 10px",
                          borderRadius: 4,
                          background: "var(--red-muted)",
                          color: "var(--red)",
                          border: "none",
                          cursor: "pointer",
                          opacity: busy === t.id ? 0.5 : 1,
                        }}
                      >
                        삭제
                      </button>
                    </>
                  ) : (
                    <button
                      disabled={busy === t.id}
                      onClick={() => clone(t)}
                      style={{
                        fontSize: 11,
                        padding: "3px 10px",
                        borderRadius: 4,
                        background: "var(--accent-muted)",
                        color: "var(--accent-text)",
                        border: "none",
                        cursor: "pointer",
                        opacity: busy === t.id ? 0.5 : 1,
                      }}
                    >
                      {busy === t.id ? "복제 중…" : "복제 후 편집"}
                    </button>
                  )}
                  {t.source_post_url && (
                    <a
                      href={t.source_post_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: 11, color: "var(--accent)" }}
                    >
                      원본 →
                    </a>
                  )}
                </div>
                </div>
              </div>
              );
            })}
          </div>
        )}
      </div>

      {previewing && (
        <TemplatePreviewModal
          templateId={previewing.id}
          templateName={previewing.name}
          editing={busy === previewing.id}
          onClose={() => setPreviewing(null)}
          onEdit={() => {
            const t = previewing;
            setPreviewing(null);
            if (t.user_id === null) {
              clone(t);
            } else {
              router.push(`/templates/${t.id}/edit`);
            }
          }}
        />
      )}

      {/* Share modal */}
      {shareModal && (
        <div
          onClick={() => setShareModal(null)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)",
            zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "var(--bg-base)", border: "1px solid var(--border)",
              borderRadius: 12, width: "100%", maxWidth: 520, padding: 20,
            }}
          >
            <h3 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 4 }}>
              템플릿 공유
            </h3>
            <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 14 }}>
              아래 링크를 받은 사람은 '{shareModal.template.name}' 템플릿을 자기 라이브러리에 복사해 사용할 수 있습니다.
            </p>
            <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
              <input
                type="text"
                readOnly
                value={shareModal.url}
                onFocus={(e) => e.currentTarget.select()}
                style={{
                  flex: 1, padding: "8px 12px", fontSize: 12, fontFamily: "monospace",
                  background: "var(--bg-overlay)", color: "var(--text-primary)",
                  border: "1px solid var(--border)", borderRadius: 6, outline: "none",
                }}
              />
              <button
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(shareModal.url);
                    alert("링크 복사됨");
                  } catch {
                    alert("복사 실패 — 직접 선택해 복사하세요");
                  }
                }}
                style={{
                  padding: "8px 14px", fontSize: 12, fontWeight: 500, color: "white",
                  background: "var(--accent)", border: "none", borderRadius: 6, cursor: "pointer",
                }}
              >
                복사
              </button>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
              <button
                onClick={() => unshare(shareModal.template)}
                style={{
                  padding: "7px 14px", fontSize: 12,
                  color: "var(--red)", background: "var(--red-muted)",
                  border: "none", borderRadius: 6, cursor: "pointer",
                }}
              >
                공유 해제
              </button>
              <button
                onClick={() => setShareModal(null)}
                style={{
                  padding: "7px 14px", fontSize: 12,
                  color: "var(--text-secondary)", background: "var(--bg-elevated)",
                  border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer",
                }}
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
