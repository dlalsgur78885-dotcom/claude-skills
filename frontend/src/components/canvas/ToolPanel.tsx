"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { TransparentToggle } from "./TransparentToggle";

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
  // Recolor every text object across all slides at once. No "current color"
  // to mirror (text objects each have their own fill) — the swatch is just a
  // picker, the button commits it everywhere.
  onApplyTextColorToAll?: (color: string) => void;
  // Bulk-apply letter-spacing (charSpacing) to every text object on every
  // slide — feedback slide 7. Bundled with the text-color control in the
  // shared "전체 텍스트" section. Receives raw fabric charSpacing (1/1000 em).
  onApplyCharSpacingToAll?: (value: number) => void;
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

export function ToolPanel({ onAddText, onAddRect, onAddCircle, onAddGradientOverlay, onImportPsd, onImportImage, bgColor, onApplyBgToCurrent, onApplyBgToAll, onApplyTextColorToAll, onApplyCharSpacingToAll, caption, hashtags, sourcePostUrl, onAddCta }: ToolPanelProps) {
  const [captionOpen, setCaptionOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [ctaOpen, setCtaOpen] = useState(false);
  const [ctaUrl, setCtaUrl] = useState<string | null>(null);
  const [ctaBusy, setCtaBusy] = useState(false);
  // Color staged for the "전체 텍스트 색상 변경" bulk action. Local because
  // there's no single "current" text color across a multi-slide deck.
  const [bulkTextColor, setBulkTextColor] = useState("#000000");
  // Letter-spacing staged for the "전체 자간 적용" bulk action. Display units
  // (= charSpacing / 10); 0 = 기본.
  const [bulkCharSpacing, setBulkCharSpacing] = useState(0);

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

      {(onApplyTextColorToAll || onApplyCharSpacingToAll) && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
          <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8, paddingLeft: 2 }}>
            전체 텍스트
          </p>
          {onApplyTextColorToAll && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <label
                title="모든 슬라이드에 적용할 텍스트 색"
                style={{
                  position: "relative",
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  width: 30, height: 26,
                  background: bulkTextColor,
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                  cursor: "pointer",
                  overflow: "hidden",
                  flexShrink: 0,
                }}
              >
                <input
                  type="color"
                  value={bulkTextColor}
                  onChange={(e) => setBulkTextColor(e.target.value)}
                  style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer" }}
                />
              </label>
              <button
                type="button"
                onClick={() => onApplyTextColorToAll(bulkTextColor)}
                title="모든 슬라이드의 텍스트를 이 색으로 일괄 변경"
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
                전체 텍스트 색상 변경
              </button>
            </div>
          )}
          {onApplyCharSpacingToAll && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
              <input
                type="number"
                min="-20"
                max="100"
                step="1"
                value={bulkCharSpacing}
                onChange={(e) => setBulkCharSpacing(Number(e.target.value))}
                title="모든 슬라이드에 적용할 자간 (0 = 기본, 클수록 넓게)"
                style={{
                  width: 44,
                  padding: "4px 6px", fontSize: 11,
                  color: "var(--text-primary)",
                  background: "var(--bg-overlay)",
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                  flexShrink: 0,
                }}
              />
              <button
                type="button"
                onClick={() => onApplyCharSpacingToAll(bulkCharSpacing * 10)}
                title="모든 슬라이드의 모든 텍스트 자간을 일괄 적용"
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
                전체 자간 적용
              </button>
            </div>
          )}
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
            onClick={() => setCtaOpen((o) => !o)}
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
            <svg
              width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"
              style={{ transform: ctaOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s", flexShrink: 0 }}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
            </svg>
          </button>
          {ctaOpen && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
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
                  <span style={{ display: "block", color: "var(--text-primary)" }}>PNG 파일 등록하기</span>
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
              <button
                type="button"
                onClick={() => { if (ctaUrl) onAddCta(ctaUrl); }}
                disabled={!ctaUrl}
                title={ctaUrl ? "등록한 CTA 이미지를 맨 뒤 새 슬라이드로 추가" : "먼저 PNG 파일을 등록하세요"}
                style={{ ...btnStyle, fontSize: 12, opacity: ctaUrl ? 1 : 0.5, cursor: ctaUrl ? "pointer" : "default" }}
                onMouseEnter={(e) => {
                  if (!ctaUrl) return;
                  e.currentTarget.style.background = "var(--bg-overlay)";
                  e.currentTarget.style.borderColor = "var(--border-strong)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                  e.currentTarget.style.borderColor = "var(--border)";
                }}
              >
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                <span style={{ flex: 1 }}>CTA 추가</span>
              </button>
            </div>
          )}
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
