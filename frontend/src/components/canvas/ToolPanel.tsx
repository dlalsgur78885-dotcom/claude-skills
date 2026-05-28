"use client";

import { useState, useEffect } from "react";
import { api, resolveImageUrl } from "@/lib/api";
import { TransparentToggle } from "./TransparentToggle";
import { type UserFont } from "@/lib/fonts";

interface ToolPanelProps {
  onAddText: () => void;
  onAddRect: () => void;
  onAddCircle: () => void;
  onAddGradientOverlay?: () => void;
  onImportPsd?: (file: File) => void;
  onImportImage?: (file: File) => void;
  // Background color of the current slide — moved here from the top toolbar
  // so the user finds canvas-affecting controls all in the left panel.
  bgColor?: string;
  onApplyBgToCurrent?: (color: string) => void;
  onApplyBgToAll?: (color: string) => void;
  // Bulk-edit every text object across all slides — the "전체 수정" modal.
  // `changes` carries only the user-opted-in fabric props (fill / fontFamily
  // / fontSize / lineHeight / charSpacing). One confirm, one apply pass.
  onApplyTextPropsToAll?: (changes: Record<string, unknown>) => void;
  // Uploaded fonts, for the "전체 수정" modal's font dropdown.
  userFonts?: UserFont[];
  // Instagram caption + hashtag chips generated upstream (콘텐츠 확인 step).
  // We don't allow editing them here — the editor's role is the visual side,
  // captions belong to the post flow. Show-and-copy is enough.
  caption?: string;
  hashtags?: string[];
  // Instagram URL of the benchmark post this carousel was generated from.
  // When present, the toolbar surfaces a "원본 링크 보기" button right below
  // the caption button so users can pop the source open in a new tab without
  // backtracking through the works list.
  sourcePostUrl?: string;
  // CTA image — registered once on the backend, then dropped onto a fresh
  // last slide. This panel owns registration/persistence; the canvas owns the
  // insert (creating the new slide + placing the image full-bleed).
  onAddCta?: (imageUrl: string) => void;
}

export function ToolPanel({ onAddText, onAddRect, onAddCircle, onAddGradientOverlay, onImportPsd, onImportImage, bgColor, onApplyBgToCurrent, onApplyBgToAll, onApplyTextPropsToAll, userFonts, caption, hashtags, sourcePostUrl, onAddCta }: ToolPanelProps) {
  const [captionOpen, setCaptionOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [ctaOpen, setCtaOpen] = useState(false);
  const [ctaUrl, setCtaUrl] = useState<string | null>(null);
  const [ctaBusy, setCtaBusy] = useState(false);
  // "전체 수정" modal — bulk-edit text props across every slide. Each row
  // opts in via its checkbox; only checked props get applied. fontSize /
  // lineHeight / charSpacing values are display units (charSpacing = ÷10).
  const [editAllOpen, setEditAllOpen] = useState(false);
  const [bulkEdit, setBulkEdit] = useState({
    fill:        { on: false, value: "#000000" },
    fontFamily:  { on: false, value: "Pretendard, sans-serif" },
    fontSize:    { on: false, value: 36 },
    lineHeight:  { on: false, value: 1.4 },
    charSpacing: { on: false, value: 0 },
  });
  function applyBulkEdit() {
    if (!onApplyTextPropsToAll) return;
    const changes: Record<string, unknown> = {};
    if (bulkEdit.fill.on) changes.fill = bulkEdit.fill.value;
    if (bulkEdit.fontFamily.on) changes.fontFamily = bulkEdit.fontFamily.value;
    if (bulkEdit.fontSize.on) changes.fontSize = bulkEdit.fontSize.value;
    if (bulkEdit.lineHeight.on) changes.lineHeight = bulkEdit.lineHeight.value;
    // charSpacing input is display units (÷10) — convert to raw fabric value.
    if (bulkEdit.charSpacing.on) changes.charSpacing = bulkEdit.charSpacing.value * 10;
    if (Object.keys(changes).length === 0) {
      alert("적용할 항목을 하나 이상 체크하세요.");
      return;
    }
    onApplyTextPropsToAll(changes);
    setEditAllOpen(false);
  }

  useEffect(() => {
    if (!onAddCta) return;
    api.getCtaImage().then((r) => setCtaUrl(r.url)).catch(() => {});
  }, [onAddCta]);

  async function handleRegisterCta(file: File) {
    setCtaBusy(true);
    try {
      const r = await api.uploadCtaImage(file);
      setCtaUrl(r.url);
    } catch (err) {
      alert("CTA 이미지 등록 실패: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setCtaBusy(false);
    }
  }
  const captionText = (caption || "").trim();
  const tagList = Array.isArray(hashtags) ? hashtags.filter(Boolean) : [];
  const fullText = [
    captionText,
    tagList.length ? tagList.map(t => t.startsWith("#") ? t : `#${t}`).join(" ") : "",
  ].filter(Boolean).join("\n\n");

  async function copyToClipboard() {
    if (!fullText) return;
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Fallback: select the textarea contents so the user can Ctrl+C.
      const ta = document.getElementById("caption-modal-textarea") as HTMLTextAreaElement | null;
      ta?.select();
    }
  }
  const btnStyle: React.CSSProperties = {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 10px",
    borderRadius: 6,
    border: "1px solid var(--border)",
    background: "transparent",
    cursor: "pointer",
    textAlign: "left",
    transition: "background 0.1s, border-color 0.1s",
  };

  return (
    <div
      style={{
        width: 180,
        background: "var(--bg-elevated)",
        borderRight: "1px solid var(--border)",
        padding: "12px",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      <div>
        <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8, paddingLeft: 2 }}>
          도구
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {[
            {
              label: "텍스트",
              desc: "텍스트 박스 추가",
              onClick: onAddText,
              color: "var(--accent)",
              icon: (
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 8h10M7 12h4m1 8-4-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3l-4 4Z" />
                </svg>
              ),
            },
            {
              label: "사각형",
              desc: "사각형 도형 추가",
              onClick: onAddRect,
              color: "var(--amber)",
              icon: (
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 7.5A2.25 2.25 0 0 1 7.5 5.25h9a2.25 2.25 0 0 1 2.25 2.25v9a2.25 2.25 0 0 1-2.25 2.25h-9a2.25 2.25 0 0 1-2.25-2.25v-9Z" />
                </svg>
              ),
            },
            {
              label: "원형",
              desc: "원형 도형 추가",
              onClick: onAddCircle,
              color: "var(--green)",
              icon: (
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
              ),
            },
            ...(onAddGradientOverlay ? [{
              label: "그라데이션",
              desc: "텍스트 강조 오버레이",
              onClick: onAddGradientOverlay,
              color: "#8b5cf6",
              icon: (
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <defs>
                    <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="currentColor" stopOpacity="0.2" />
                      <stop offset="100%" stopColor="currentColor" stopOpacity="1" />
                    </linearGradient>
                  </defs>
                  <rect x="4" y="4" width="16" height="16" rx="2" fill="url(#g1)" stroke="currentColor" />
                </svg>
              ),
            }] : []),
          ].map((tool) => (
            <button
              key={tool.label}
              onClick={tool.onClick}
              style={btnStyle}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-overlay)";
                e.currentTarget.style.borderColor = "var(--border-strong)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.borderColor = "var(--border)";
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  background: `${tool.color}22`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: tool.color,
                  flexShrink: 0,
                }}
              >
                {tool.icon}
              </div>
              <div>
                <p style={{ fontSize: 12, fontWeight: 500, color: "var(--text-primary)", margin: 0 }}>{tool.label}</p>
                <p style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 1 }}>{tool.desc}</p>
              </div>
            </button>
          ))}
        </div>

        {onImportImage && (
          <label
            style={{ ...btnStyle, marginTop: 6, display: "flex" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--bg-overlay)";
              e.currentTarget.style.borderColor = "var(--border-strong)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          >
            <div
              style={{
                width: 28, height: 28, borderRadius: 6,
                background: "#06b6d422",
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#06b6d4", flexShrink: 0,
              }}
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z" />
              </svg>
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: 12, fontWeight: 500, color: "var(--text-primary)", margin: 0 }}>이미지 추가</p>
              <p style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 1 }}>jpg · png · webp · jfif</p>
            </div>
            <input
              type="file"
              accept="image/jpeg,image/jpg,image/png,image/webp,.jpg,.jpeg,.png,.webp,.jfif,.pjpeg"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onImportImage(f);
                e.target.value = "";
              }}
            />
          </label>
        )}

        {onImportPsd && (
          <label
            style={{ ...btnStyle, marginTop: 6, display: "flex" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--bg-overlay)";
              e.currentTarget.style.borderColor = "var(--border-strong)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          >
            <div
              style={{
                width: 28, height: 28, borderRadius: 6,
                background: "#6366f122",
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "#6366f1", flexShrink: 0,
              }}
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 8.25H7.5a2.25 2.25 0 0 0-2.25 2.25v9a2.25 2.25 0 0 0 2.25 2.25h9a2.25 2.25 0 0 0 2.25-2.25v-9a2.25 2.25 0 0 0-2.25-2.25H15M9 12l3 3m0 0 3-3m-3 3V2.25" />
              </svg>
            </div>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: 12, fontWeight: 500, color: "var(--text-primary)", margin: 0 }}>PSD 가져오기</p>
              <p style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 1 }}>레이어별 분해 추가</p>
            </div>
            <input
              type="file"
              accept=".psd,application/x-photoshop,image/vnd.adobe.photoshop"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) onImportPsd(f);
                e.target.value = "";
              }}
            />
          </label>
        )}
      </div>

      {onApplyBgToCurrent && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8, paddingLeft: 2 }}>
            배경 색
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <label
              title="현재 슬라이드 배경색 변경"
              style={{
                position: "relative",
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: 30, height: 26,
                background: bgColor || "#FFFFFF",
                border: "1px solid var(--border)",
                borderRadius: 5,
                cursor: "pointer",
                overflow: "hidden",
                flexShrink: 0,
              }}
            >
              <input
                type="color"
                value={typeof bgColor === "string" && /^#[0-9a-fA-F]{6}$/.test(bgColor) ? bgColor : "#ffffff"}
                onChange={(e) => onApplyBgToCurrent(e.target.value)}
                style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer" }}
              />
            </label>
            <TransparentToggle
              size={26}
              value={bgColor}
              onChange={(next) => onApplyBgToCurrent(next)}
            />
            {onApplyBgToAll && (
              <button
                type="button"
                onClick={() => onApplyBgToAll(bgColor || "#FFFFFF")}
                title="현재 색을 모든 슬라이드에 적용"
                style={{
                  flex: 1,
                  padding: "4px 8px", fontSize: 11,
                  color: "var(--text-secondary)",
                  background: "var(--bg-overlay)",
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                  cursor: "pointer",
                }}
              >
                전체 적용
              </button>
            )}
          </div>
        </div>
      )}

      {onApplyTextPropsToAll && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8, paddingLeft: 2 }}>
            전체 텍스트
          </p>
          <button
            type="button"
            onClick={() => setEditAllOpen(true)}
            title="모든 슬라이드의 모든 텍스트 속성을 한 번에 일괄 수정"
            style={{ ...btnStyle, fontSize: 12 }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--bg-overlay)";
              e.currentTarget.style.borderColor = "var(--border-strong)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          >
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Z" />
            </svg>
            <span style={{ flex: 1 }}>전체 수정</span>
          </button>
        </div>
      )}

      {(captionText || tagList.length > 0) && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8, paddingLeft: 2 }}>
            캡션
          </p>
          <button
            type="button"
            data-caption-trigger="true"
            onClick={() => { setCopied(false); setCaptionOpen(true); }}
            title="콘텐츠 확인 단계에서 만든 인스타그램 캡션 보기"
            style={{
              ...btnStyle,
              fontSize: 12,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--bg-overlay)";
              e.currentTarget.style.borderColor = "var(--border-strong)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          >
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h8M8 14h5M21 12c0 4.97-4.03 9-9 9a8.96 8.96 0 0 1-4.5-1.2L3 21l1.2-4.5A8.96 8.96 0 0 1 3 12c0-4.97 4.03-9 9-9s9 4.03 9 9Z" />
            </svg>
            <span style={{ flex: 1 }}>캡션 보기</span>
          </button>
          {sourcePostUrl && (
            <a
              href={sourcePostUrl}
              target="_blank"
              rel="noopener noreferrer"
              title="이 캐러셀의 원본 인스타그램 게시물 열기 (새 탭)"
              style={{
                ...btnStyle,
                marginTop: 6,
                fontSize: 12,
                textDecoration: "none",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-overlay)";
                e.currentTarget.style.borderColor = "var(--border-strong)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.borderColor = "var(--border)";
              }}
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
              </svg>
              <span style={{ flex: 1 }}>원본 링크 보기</span>
            </a>
          )}
        </div>
      )}
      {!captionText && !tagList.length && sourcePostUrl && (
        // Even without a caption section, still show the original-link button
        // — the user feedback was scoped to the editor toolbar, not "only when
        // caption is present". Render a slim standalone block.
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <a
            href={sourcePostUrl}
            target="_blank"
            rel="noopener noreferrer"
            title="이 캐러셀의 원본 인스타그램 게시물 열기 (새 탭)"
            style={{
              ...btnStyle,
              fontSize: 12,
              textDecoration: "none",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--bg-overlay)";
              e.currentTarget.style.borderColor = "var(--border-strong)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          >
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
            </svg>
            <span style={{ flex: 1 }}>원본 링크 보기</span>
          </a>
        </div>
      )}

      {onAddCta && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8, paddingLeft: 2 }}>
            CTA
          </p>
          <button
            type="button"
            onClick={() => setCtaOpen(true)}
            title="캐러셀 맨 뒷장에 넣을 CTA 이미지를 등록하고 추가합니다"
            style={{ ...btnStyle, fontSize: 12 }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "var(--bg-overlay)";
              e.currentTarget.style.borderColor = "var(--border-strong)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
              e.currentTarget.style.borderColor = "var(--border)";
            }}
          >
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m3.75 13.5 10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75Z" />
            </svg>
            <span style={{ flex: 1 }}>CTA 등록&추가</span>
          </button>
        </div>
      )}

      {onAddCta && ctaOpen && (
        <div
          onClick={() => setCtaOpen(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 10000,
            background: "rgba(0,0,0,0.55)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(360px, 92vw)",
              maxHeight: "86vh", overflowY: "auto",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              boxShadow: "0 18px 48px rgba(0,0,0,0.45)",
              padding: 20,
              display: "flex", flexDirection: "column", gap: 14,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <strong style={{ fontSize: 14 }}>CTA 이미지</strong>
              <button
                type="button"
                onClick={() => setCtaOpen(false)}
                aria-label="닫기"
                style={{
                  width: 26, height: 26, borderRadius: 6,
                  border: "1px solid var(--border)", background: "transparent",
                  cursor: "pointer", color: "var(--text-secondary)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}
              >
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-tertiary)", margin: 0, lineHeight: 1.5 }}>
              PNG 파일을 한 번 등록하면 계정에 저장되어, 다음에도 바로 추가할 수 있습니다.
            </p>

            {/* 등록된 CTA 미리보기 */}
            {ctaUrl ? (
              <img
                src={resolveImageUrl(ctaUrl)}
                alt="등록된 CTA"
                style={{
                  width: "100%", borderRadius: 6,
                  border: "1px solid var(--border)",
                  background: "var(--bg-overlay)",
                }}
              />
            ) : (
              <div style={{
                width: "100%", padding: "32px 0",
                borderRadius: 6, border: "1px dashed var(--border)",
                background: "var(--bg-overlay)",
                fontSize: 12, color: "var(--text-tertiary)", textAlign: "center",
              }}>
                등록된 CTA 이미지가 없습니다
              </div>
            )}

            {/* PNG 등록 / 교체 */}
            <label
              style={{ ...btnStyle, fontSize: 12 }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--bg-overlay)";
                e.currentTarget.style.borderColor = "var(--border-strong)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.borderColor = "var(--border)";
              }}
            >
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
              </svg>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", color: "var(--text-primary)" }}>
                  {ctaUrl ? "PNG 파일 교체하기" : "PNG 파일 등록하기"}
                </span>
                <span style={{ display: "block", fontSize: 10, color: ctaUrl ? "var(--green)" : "var(--text-tertiary)" }}>
                  {ctaBusy ? "업로드 중…" : ctaUrl ? "등록됨 ✓" : "등록된 파일 없음"}
                </span>
              </span>
              <input
                type="file"
                accept="image/png,.png"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleRegisterCta(f);
                  e.target.value = "";
                }}
              />
            </label>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
              <button type="button" onClick={() => setCtaOpen(false)}
                style={{ padding: "7px 14px", fontSize: 12, color: "var(--text-secondary)", background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer" }}>
                취소
              </button>
              <button
                type="button"
                onClick={() => { if (ctaUrl) { onAddCta(ctaUrl); setCtaOpen(false); } }}
                disabled={!ctaUrl}
                title={ctaUrl ? "등록한 CTA 이미지를 현재 슬라이드에 추가" : "먼저 PNG 파일을 등록하세요"}
                style={{ padding: "7px 14px", fontSize: 12, fontWeight: 500, color: "white", background: "var(--accent)", border: "none", borderRadius: 6, cursor: ctaUrl ? "pointer" : "default", opacity: ctaUrl ? 1 : 0.5 }}>
                CTA 추가
              </button>
            </div>
          </div>
        </div>
      )}

      {editAllOpen && (
        <div
          onClick={() => setEditAllOpen(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 10000,
            background: "rgba(0,0,0,0.55)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(380px, 92vw)",
              maxHeight: "86vh", overflowY: "auto",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              boxShadow: "0 18px 48px rgba(0,0,0,0.45)",
              padding: 20,
              display: "flex", flexDirection: "column", gap: 14,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <strong style={{ fontSize: 14 }}>전체 텍스트 수정</strong>
              <button
                type="button"
                onClick={() => setEditAllOpen(false)}
                aria-label="닫기"
                style={{
                  width: 26, height: 26, borderRadius: 6,
                  border: "1px solid var(--border)", background: "transparent",
                  cursor: "pointer", color: "var(--text-secondary)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}
              >
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p style={{ fontSize: 11, color: "var(--text-tertiary)", margin: 0, lineHeight: 1.5 }}>
              체크한 항목만 모든 슬라이드의 모든 텍스트에 일괄 적용됩니다.
            </p>

            {/* 색상 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={bulkEdit.fill.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, fill: { ...p.fill, on: e.target.checked } }))} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)", width: 62, flexShrink: 0 }}>색상</span>
              <label style={{
                position: "relative", width: 36, height: 26,
                background: bulkEdit.fill.value, border: "1px solid var(--border)",
                borderRadius: 5, cursor: bulkEdit.fill.on ? "pointer" : "default",
                overflow: "hidden", opacity: bulkEdit.fill.on ? 1 : 0.4,
              }}>
                <input type="color" value={bulkEdit.fill.value} disabled={!bulkEdit.fill.on}
                  onChange={(e) => setBulkEdit((p) => ({ ...p, fill: { ...p.fill, value: e.target.value } }))}
                  style={{ position: "absolute", inset: 0, opacity: 0, cursor: "inherit" }} />
              </label>
            </div>

            {/* 폰트 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={bulkEdit.fontFamily.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, fontFamily: { ...p.fontFamily, on: e.target.checked } }))} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)", width: 62, flexShrink: 0 }}>폰트</span>
              <select value={bulkEdit.fontFamily.value} disabled={!bulkEdit.fontFamily.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, fontFamily: { ...p.fontFamily, value: e.target.value } }))}
                style={{ flex: 1, minWidth: 0, padding: "5px 6px", fontSize: 12, background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 5, color: "var(--text-primary)", cursor: "pointer", opacity: bulkEdit.fontFamily.on ? 1 : 0.4 }}>
                <option value="Pretendard, sans-serif">기본 (Pretendard)</option>
                {(userFonts || []).map((f) => (
                  <option key={f.family} value={f.family}>{f.family}</option>
                ))}
              </select>
            </div>

            {/* 글꼴 크기 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={bulkEdit.fontSize.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, fontSize: { ...p.fontSize, on: e.target.checked } }))} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)", width: 62, flexShrink: 0 }}>글꼴 크기</span>
              <input type="number" min="1" max="500" step="1"
                value={bulkEdit.fontSize.value} disabled={!bulkEdit.fontSize.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, fontSize: { ...p.fontSize, value: Number(e.target.value) } }))}
                style={{ flex: 1, minWidth: 0, padding: "5px 8px", fontSize: 12, background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 5, color: "var(--text-primary)", opacity: bulkEdit.fontSize.on ? 1 : 0.4 }} />
            </div>

            {/* 행간 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={bulkEdit.lineHeight.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, lineHeight: { ...p.lineHeight, on: e.target.checked } }))} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)", width: 62, flexShrink: 0 }}>행간</span>
              <input type="number" min="0.8" max="3" step="0.1"
                value={bulkEdit.lineHeight.value} disabled={!bulkEdit.lineHeight.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, lineHeight: { ...p.lineHeight, value: Number(e.target.value) } }))}
                style={{ flex: 1, minWidth: 0, padding: "5px 8px", fontSize: 12, background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 5, color: "var(--text-primary)", opacity: bulkEdit.lineHeight.on ? 1 : 0.4 }} />
            </div>

            {/* 자간 — 표시 단위(charSpacing÷10), 0 = 기본 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={bulkEdit.charSpacing.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, charSpacing: { ...p.charSpacing, on: e.target.checked } }))} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)", width: 62, flexShrink: 0 }}>자간</span>
              <input type="number" min="-20" max="100" step="1"
                value={bulkEdit.charSpacing.value} disabled={!bulkEdit.charSpacing.on}
                onChange={(e) => setBulkEdit((p) => ({ ...p, charSpacing: { ...p.charSpacing, value: Number(e.target.value) } }))}
                style={{ flex: 1, minWidth: 0, padding: "5px 8px", fontSize: 12, background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 5, color: "var(--text-primary)", opacity: bulkEdit.charSpacing.on ? 1 : 0.4 }} />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
              <button type="button" onClick={() => setEditAllOpen(false)}
                style={{ padding: "7px 14px", fontSize: 12, color: "var(--text-secondary)", background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer" }}>
                취소
              </button>
              <button type="button" onClick={applyBulkEdit}
                style={{ padding: "7px 14px", fontSize: 12, fontWeight: 500, color: "white", background: "var(--accent)", border: "none", borderRadius: 6, cursor: "pointer" }}>
                적용
              </button>
            </div>
          </div>
        </div>
      )}

      {captionOpen && (
        <div
          data-caption-modal="true"
          onClick={() => setCaptionOpen(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 10000,
            background: "rgba(0,0,0,0.55)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(640px, 92vw)",
              maxHeight: "82vh",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              boxShadow: "0 18px 48px rgba(0,0,0,0.45)",
              padding: 20,
              display: "flex", flexDirection: "column", gap: 12,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <strong style={{ fontSize: 14 }}>캡션</strong>
              <button
                type="button"
                onClick={() => setCaptionOpen(false)}
                aria-label="닫기"
                style={{
                  width: 26, height: 26, borderRadius: 6,
                  border: "1px solid var(--border)", background: "transparent",
                  cursor: "pointer", color: "var(--text-secondary)",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                }}
              >
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <textarea
              id="caption-modal-textarea"
              readOnly
              value={fullText || "(캡션이 비어 있습니다)"}
              style={{
                width: "100%", flex: 1, minHeight: 220,
                padding: 12, fontSize: 13, lineHeight: 1.55,
                fontFamily: "inherit",
                color: "var(--text-primary)",
                background: "var(--bg-overlay)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                resize: "vertical",
                whiteSpace: "pre-wrap",
              }}
            />
            {tagList.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {tagList.map((tag, i) => (
                  <span
                    key={i}
                    style={{
                      fontSize: 11,
                      padding: "3px 9px",
                      borderRadius: 999,
                      background: "rgba(94,106,210,0.18)",
                      color: "var(--accent-text, var(--accent))",
                      border: "1px solid rgba(94,106,210,0.35)",
                    }}
                  >
                    {tag.startsWith("#") ? tag : `#${tag}`}
                  </span>
                ))}
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button
                type="button"
                onClick={copyToClipboard}
                disabled={!fullText}
                style={{
                  padding: "7px 14px", fontSize: 12, fontWeight: 500,
                  color: "white",
                  background: "var(--accent)",
                  border: "none",
                  borderRadius: 6,
                  cursor: fullText ? "pointer" : "default",
                  opacity: fullText ? 1 : 0.5,
                }}
              >
                {copied ? "복사됨 ✓" : "복사"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
