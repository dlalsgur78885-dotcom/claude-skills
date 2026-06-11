"use client";

import { useEffect, useState } from "react";
import { api, resolveImageUrl, type LayoutHint } from "@/lib/api";
import type { Channel, TemplateSummary } from "@/lib/types";
import { SlideClassifier } from "@/components/template-editor/SlideClassifier";
import { displayLayoutName } from "@/components/template-editor/types";


interface Props {
  channel: Channel;
  onClose: () => void;
  onChannelUpdate: (ch: Channel) => void;
}

export function ChannelTemplatesModal({ channel, onClose, onChannelUpdate }: Props) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [defaultId, setDefaultId] = useState<number | null>(channel.default_template_id);
  const [color, setColor] = useState(channel.brand_primary_color ?? "#000000");
  const [loading, setLoading] = useState(true);

  const [postUrl, setPostUrl] = useState("");
  const [name, setName] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [slideUrls, setSlideUrls] = useState<string[]>([]);
  const [hints, setHints] = useState<LayoutHint[]>([]);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const [uploadingLogo, setUploadingLogo] = useState(false);

  async function loadPreview() {
    if (!postUrl.trim() || loadingPreview) return;
    setLoadingPreview(true);
    setGenError("");
    try {
      const res = await api.previewSlides(postUrl.trim());
      setSlideUrls(res.slide_urls);
      setHints(res.slide_urls.map((_, i) => ({ slide_index: i, kind: "single" })));
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "미리보기 실패");
    } finally {
      setLoadingPreview(false);
    }
  }

  function resetPreview() {
    setSlideUrls([]);
    setHints([]);
  }

  useEffect(() => {
    loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel.id]);

  async function loadTemplates() {
    try {
      const data = await api.listChannelTemplates(channel.id);
      setTemplates(data.templates);
      setDefaultId(data.default_template_id);
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
      setGenError("최소 1개 슬라이드의 레이아웃(단일/그리드)을 분류해주세요");
      return;
    }
    setGenerating(true);
    setGenError("");
    try {
      await api.createChannelTemplate(channel.id, {
        post_url: postUrl.trim(),
        template_name: name.trim(),
        layout_hints: hints,
      });
      setPostUrl("");
      setName("");
      resetPreview();
      await loadTemplates();
    } catch (err) {
      setGenError(err instanceof Error ? err.message : "생성 실패");
    } finally {
      setGenerating(false);
    }
  }

  async function setDefault(templateId: number) {
    setDefaultId(templateId);
    try {
      const updated = (await api.updateChannel(channel.id, {
        default_template_id: templateId,
      })) as Channel;
      onChannelUpdate(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "기본 템플릿 설정 실패");
      setDefaultId(channel.default_template_id);
    }
  }

  async function removeTemplate(id: number) {
    if (!confirm("이 템플릿을 삭제하시겠습니까?")) return;
    try {
      await api.deleteTemplate(id);
      await loadTemplates();
    } catch (err) {
      alert(err instanceof Error ? err.message : "삭제 실패");
    }
  }

  async function uploadLogo(file: File) {
    setUploadingLogo(true);
    try {
      const res = await api.uploadChannelLogo(channel.id, file);
      onChannelUpdate({ ...channel, brand_logo_path: res.brand_logo_path });
    } catch (err) {
      alert(err instanceof Error ? err.message : "업로드 실패");
    } finally {
      setUploadingLogo(false);
    }
  }

  async function saveBrand() {
    try {
      const updated = (await api.updateChannel(channel.id, {
        brand_primary_color: color,
      })) as Channel;
      onChannelUpdate(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "저장 실패");
    }
  }


  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-base)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          width: "100%",
          maxWidth: 720,
          maxHeight: "85vh",
          overflowY: "auto",
          padding: 24,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 17, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
              @{channel.instagram_handle} 템플릿
            </h2>
            <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>
              {templates.length}개 등록됨
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              padding: "6px 12px",
              fontSize: 12,
              color: "var(--text-secondary)",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            닫기
          </button>
        </div>

        {/* Brand color */}
        <section
          style={{
            padding: 14,
            marginBottom: 16,
            background: "var(--bg-subtle)",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        >
          <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 8 }}>
            브랜드 컬러
          </h3>
          <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
            템플릿 렌더링 시 항상 이 컬러가 우선합니다 (Gemini가 잘못 추출한 색을 덮어씀).
          </p>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              style={{ width: 40, height: 32, border: "1px solid var(--border)", borderRadius: 4, padding: 0, cursor: "pointer" }}
            />
            <input
              type="text"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              style={{
                flex: 1,
                padding: "7px 10px",
                fontSize: 12,
                background: "var(--bg-overlay)",
                color: "var(--text-primary)",
                border: "1px solid var(--border)",
                borderRadius: 5,
                fontFamily: "monospace",
              }}
            />
            <button
              onClick={saveBrand}
              style={{
                padding: "7px 14px",
                fontSize: 12,
                fontWeight: 500,
                color: "white",
                background: "var(--accent)",
                border: "none",
                borderRadius: 5,
                cursor: "pointer",
              }}
            >
              저장
            </button>
          </div>
        </section>

        {/* Brand logo */}
        <section
          style={{
            padding: 14,
            marginBottom: 16,
            background: "var(--bg-subtle)",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        >
          <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 8 }}>
            브랜드 로고
          </h3>
          <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
            템플릿이 logo decoration을 가지면 이 로고가 자동으로 들어갑니다 (PNG 권장, 투명 배경).
          </p>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            {channel.brand_logo_path && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={resolveImageUrl(channel.brand_logo_path)}
                alt=""
                style={{ width: 64, height: 64, objectFit: "contain", borderRadius: 6, background: "var(--bg-overlay)", border: "1px solid var(--border)" }}
              />
            )}
            <label
              style={{
                padding: "7px 14px",
                fontSize: 12,
                fontWeight: 500,
                color: uploadingLogo ? "var(--text-tertiary)" : "var(--text-secondary)",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: 5,
                cursor: uploadingLogo ? "default" : "pointer",
              }}
            >
              {uploadingLogo ? "업로드 중…" : channel.brand_logo_path ? "로고 변경" : "로고 업로드"}
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp,image/svg+xml"
                disabled={uploadingLogo}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadLogo(f);
                }}
                style={{ display: "none" }}
              />
            </label>
          </div>
        </section>

        {/* Templates list */}
        <section style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 8 }}>
            템플릿 목록
          </h3>
          {loading ? (
            <p style={{ fontSize: 12, color: "var(--text-tertiary)" }}>로딩 중...</p>
          ) : templates.length === 0 ? (
            <p style={{ fontSize: 12, color: "var(--text-tertiary)" }}>아직 이 채널에 템플릿이 없습니다.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {templates.map((t) => (
                <div
                  key={t.id}
                  style={{
                    padding: 12,
                    background: defaultId === t.id ? "rgba(0,200,100,0.08)" : "var(--bg-subtle)",
                    border: `1px solid ${defaultId === t.id ? "rgba(0,200,100,0.4)" : "var(--border)"}`,
                    borderRadius: 8,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{t.name}</span>
                        {defaultId === t.id && (
                          <span
                            style={{
                              fontSize: 10,
                              padding: "1px 6px",
                              background: "rgba(0,200,100,0.2)",
                              color: "rgb(120,220,170)",
                              borderRadius: 4,
                            }}
                          >
                            기본
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>
                        {t.layouts.map(displayLayoutName).join(", ") || "레이아웃 없음"}
                      </div>
                      {t.source_post_url && (
                        <a
                          href={t.source_post_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ fontSize: 11, color: "var(--accent)", marginTop: 4, display: "inline-block" }}
                        >
                          원본 →
                        </a>
                      )}
                    </div>
                    <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                      {defaultId !== t.id && (
                        <button
                          onClick={() => setDefault(t.id)}
                          style={{
                            padding: "4px 10px",
                            fontSize: 11,
                            color: "var(--accent-text)",
                            background: "var(--accent-muted)",
                            border: "none",
                            borderRadius: 4,
                            cursor: "pointer",
                          }}
                        >
                          기본으로
                        </button>
                      )}
                      <button
                        onClick={() => removeTemplate(t.id)}
                        style={{
                          padding: "4px 10px",
                          fontSize: 11,
                          color: "var(--red)",
                          background: "var(--red-muted)",
                          border: "none",
                          borderRadius: 4,
                          cursor: "pointer",
                        }}
                      >
                        삭제
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Add template */}
        <section
          style={{
            padding: 14,
            background: "var(--bg-subtle)",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        >
          <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 4 }}>
            새 템플릿 추가
          </h3>
          <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
            벤치 게시글 URL을 넣으면 AI Vision(Gemini 3.1 Pro + Claude Sonnet 4)이 분석해서 자동 생성합니다 (30~60초, ~$0.15).
          </p>
          <form onSubmit={generate} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <input
                type="url"
                value={postUrl}
                onChange={(e) => setPostUrl(e.target.value)}
                placeholder="https://www.instagram.com/p/XXXX/"
                required
                style={{
                  padding: "7px 10px",
                  fontSize: 12,
                  background: "var(--bg-overlay)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                }}
              />
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="템플릿 이름 (예: 그리드 형식)"
                required
                style={{
                  padding: "7px 10px",
                  fontSize: 12,
                  background: "var(--bg-overlay)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                }}
              />
              {slideUrls.length > 0 && (
                <div style={{ padding: 10, background: "var(--bg-base)", border: "1px solid var(--border)", borderRadius: 6 }}>
                  <SlideClassifier slideUrls={slideUrls} hints={hints} onChange={setHints} />
                </div>
              )}
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                {slideUrls.length === 0 ? (
                  <button
                    type="button"
                    onClick={loadPreview}
                    disabled={loadingPreview || !postUrl.trim()}
                    style={{
                      padding: "7px 14px",
                      fontSize: 12,
                      fontWeight: 500,
                      color: "white",
                      background: "var(--accent)",
                      border: "none",
                      borderRadius: 5,
                      cursor: loadingPreview || !postUrl.trim() ? "not-allowed" : "pointer",
                      opacity: loadingPreview || !postUrl.trim() ? 0.5 : 1,
                    }}
                  >
                    {loadingPreview ? "불러오는 중…" : "1단계: 미리보기"}
                  </button>
                ) : (
                  <>
                    <button
                      type="submit"
                      disabled={generating}
                      style={{
                        padding: "7px 14px",
                        fontSize: 12,
                        fontWeight: 500,
                        color: "white",
                        background: "var(--accent)",
                        border: "none",
                        borderRadius: 5,
                        cursor: generating ? "default" : "pointer",
                        opacity: generating ? 0.6 : 1,
                      }}
                    >
                      {generating ? "AI 분석 중…" : "2단계: 생성"}
                    </button>
                    <button
                      type="button"
                      onClick={resetPreview}
                      disabled={generating}
                      style={{
                        padding: "7px 14px",
                        fontSize: 12,
                        color: "var(--text-secondary)",
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border)",
                        borderRadius: 5,
                        cursor: generating ? "default" : "pointer",
                      }}
                    >
                      다시
                    </button>
                  </>
                )}
                {genError && (
                  <span style={{ fontSize: 11, color: "#e85b5b" }}>{genError}</span>
                )}
              </div>
            </form>
        </section>
      </div>
    </div>
  );
}
