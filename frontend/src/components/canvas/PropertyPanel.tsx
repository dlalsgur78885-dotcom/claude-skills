"use client";

import { useEffect, useRef, useState } from "react";
import { TransparentToggle, isTransparentValue } from "./TransparentToggle";

interface PropertyPanelProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedObject: any;
  selectedTextRange?: { start: number; end: number } | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdate: (prop: string, value: any) => void;
  onChangeLayer?: (action: "forward" | "backward" | "front" | "back") => void;
  onDelete?: () => void;
  onCutout?: (mode: "standard" | "generative") => void;
  cutoutBusy?: boolean;
  onEnhance?: (category: "food" | "landscape" | "portrait") => void;
  enhanceBusy?: boolean;
  // Replace the selected image's source bitmap with a user-uploaded file.
  onReplaceImage?: (file: File) => Promise<void> | void;
  replaceBusy?: boolean;
}

const isBoldWeight = (w: unknown) => {
  const s = String(w);
  return s === "bold" || s === "700" || s === "800" || s === "900";
};

// `TransparentToggle` lives in ./TransparentToggle.tsx — shared with ToolPanel
// and the channel templates modal so every color picker app-wide can opt into
// transparency via the same swatch button. User feedback (carousel studio
// feedback slide 4): "모든 색상을 바꿀 때 '투명' 옵션 추가".

type TabKey = "basic" | "effects" | "ai";

export function PropertyPanel({ selectedObject, selectedTextRange, onUpdate, onChangeLayer, onDelete, onCutout, cutoutBusy, onEnhance, enhanceBusy, onReplaceImage, replaceBusy }: PropertyPanelProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("basic");
  const replaceInputRef = useRef<HTMLInputElement>(null);
  // Single image OR a multi-selection containing at least one image.
  // For activeselection, count how many images so the buttons can show "(N개)".
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const _members: any[] = Array.isArray((selectedObject as { _objects?: unknown[] })?._objects)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ? (selectedObject as any)._objects
    : selectedObject ? [selectedObject] : [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const imageMembers = _members.filter((o: any) => o && (o.type === "image" || o.type === "FabricImage"));
  const isImage = imageMembers.length > 0;
  const imageCount = imageMembers.length;
  // Text members across the selection — a single textbox shows the standard
  // controls; an ActiveSelection containing 2+ textboxes shows the same
  // controls and applies edits to every text member at once.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const textMembers: any[] = _members.filter((o: any) =>
    o && (o.type === "textbox" || o.type === "i-text" || o.type === "Textbox")
  );
  const isText = textMembers.length > 0;
  const textCount = textMembers.length;
  // Reference text used to populate the "current" values shown in inputs. With
  // multi-select these reflect the first text member — we don't currently show
  // "mixed" states; the user can still type a new value and it applies to all.
  const textRef = textMembers[0] || (isText ? selectedObject : null);
  // Character-range editing only makes sense inside a SINGLE textbox.
  const hasCharRange = !!(textCount === 1 && selectedTextRange && selectedTextRange.end > selectedTextRange.start);

  // Pending color for range mode — picker stages a value, Apply commits it.
  // (Whole-object color stays live for the existing UX.)
  const [pendingColor, setPendingColor] = useState<string>("#000000");
  // fontSize input is also staged — committing on every keystroke meant typing
  // "100" applied 1, then 10, then 100, leaving intermediate small sizes if the
  // user then deleted chars. Commit on blur / Enter instead.
  const [pendingFontSize, setPendingFontSize] = useState<string>("");
  useEffect(() => {
    if (!selectedObject) return;
    if (hasCharRange && selectedTextRange) {
      try {
        const styles = selectedObject.getSelectionStyles?.(selectedTextRange.start, selectedTextRange.start + 1);
        setPendingColor(styles?.[0]?.fill || selectedObject.fill || "#000000");
      } catch {
        setPendingColor(selectedObject.fill || "#000000");
      }
    } else if (selectedObject.fill) {
      setPendingColor(selectedObject.fill);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasCharRange, selectedTextRange?.start, selectedTextRange?.end, selectedObject?.fill, selectedObject?.text]);

  const panelStyle: React.CSSProperties = {
    width: 220,
    background: "var(--bg-elevated)",
    borderLeft: "1px solid var(--border)",
    padding: "12px 14px",
    overflowY: "auto",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 600,
    color: "var(--text-tertiary)",
    letterSpacing: "0.07em",
    textTransform: "uppercase",
    display: "block",
    marginBottom: 6,
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "5px 8px",
    background: "var(--bg-overlay)",
    border: "1px solid var(--border)",
    borderRadius: 5,
    fontSize: 12,
    color: "var(--text-primary)",
    outline: "none",
  };

  if (!selectedObject) {
    return (
      <div style={panelStyle}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", marginTop: 60, textAlign: "center" }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--bg-overlay)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 10 }}>
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="var(--text-tertiary)">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.042 21.672 13.684 16.6m0 0-2.51 2.225.569-9.47 5.227 7.917-3.286-.672Zm-7.518-.267A8.25 8.25 0 1 1 20.25 10.5M8.288 14.212A5.25 5.25 0 1 1 17.25 10.5" />
            </svg>
          </div>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", lineHeight: 1.6 }}>
            객체를 선택하면<br />속성을 편집할 수 있습니다
          </p>
        </div>
      </div>
    );
  }

  const selLen = hasCharRange && selectedTextRange ? (selectedTextRange.end - selectedTextRange.start) : 0;

  // Bold-active state — checks the first char in the range if any, else the
  // (first) textbox. Multi-select uses textRef[0] for display only; toggling
  // applies to every member via CanvasEditor's updateSelectedProperty.
  let currentBold = false;
  let currentWeight: string = String(textRef?.fontWeight || "normal");
  let currentFontSize: number = Number(textRef?.fontSize) || 24;
  if (isText && textRef) {
    if (hasCharRange && selectedTextRange) {
      try {
        const styles = textRef.getSelectionStyles?.(selectedTextRange.start, selectedTextRange.start + 1);
        const w = styles?.[0]?.fontWeight || textRef.fontWeight || "normal";
        currentWeight = String(w);
        currentBold = isBoldWeight(w);
        if (typeof styles?.[0]?.fontSize === "number") currentFontSize = styles[0].fontSize;
      } catch {
        currentBold = isBoldWeight(textRef.fontWeight);
      }
    } else {
      currentBold = isBoldWeight(textRef.fontWeight);
    }
  }

  // Tab visibility — each tab can be empty for some object types (e.g. a
  // textbox has no image-fill controls under 효과). We still render both tabs
  // so the user can switch context without the panel shifting.
  const tabs: { key: TabKey; label: string }[] = [
    { key: "basic", label: "기본" },
    { key: "effects", label: "효과" },
    { key: "ai", label: "AI" },
  ];

  return (
    <div style={panelStyle}>
      <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10, paddingLeft: 2 }}>
        속성
      </p>

      {/* Tab navigation */}
      <div style={{ display: "flex", gap: 2, marginBottom: 14, borderBottom: "1px solid var(--border)" }}>
        {tabs.map((t) => {
          const active = t.key === activeTab;
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              style={{
                flex: 1,
                padding: "6px 8px",
                fontSize: 11,
                fontWeight: active ? 600 : 500,
                color: active ? "var(--text-primary)" : "var(--text-tertiary)",
                background: "transparent",
                border: "none",
                borderBottom: active ? "2px solid var(--accent)" : "2px solid transparent",
                marginBottom: -1,
                cursor: "pointer",
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {hasCharRange && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 10px",
            marginBottom: 12,
            background: "rgba(94,106,210,0.12)",
            border: "1px solid var(--accent)",
            borderRadius: 6,
            fontSize: 11,
            color: "var(--accent-text, var(--accent))",
          }}
        >
          <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 4.5h18M3 9h18m-6 4.5H3m12 6H3" />
          </svg>
          <span>선택 영역 {selLen}자 · B 버튼 굵게, 색상 적용 버튼</span>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {/* ──────────── BASIC TAB ──────────── */}
        {activeTab === "basic" && (<>
        {/* Position */}
        <div>
          <label style={labelStyle}>위치</label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {[
              { label: "X", prop: "left", val: Math.round(selectedObject.left || 0) },
              { label: "Y", prop: "top", val: Math.round(selectedObject.top || 0) },
            ].map(({ label, prop, val }) => (
              <div key={prop}>
                <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontWeight: 500 }}>{label}</span>
                <input
                  type="number"
                  value={val}
                  onChange={(e) => onUpdate(prop, Number(e.target.value))}
                  style={inputStyle}
                  onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
                  onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Size */}
        <div>
          <label style={labelStyle}>크기</label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
            {[
              { label: "W", prop: "width", val: Math.round(selectedObject.width * (selectedObject.scaleX || 1)) },
              { label: "H", prop: "height", val: Math.round((selectedObject.height || 0) * (selectedObject.scaleY || 1)) },
            ].map(({ label, prop, val }) => (
              <div key={prop}>
                <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontWeight: 500 }}>{label}</span>
                <input
                  type="number"
                  value={val}
                  onChange={(e) => onUpdate(prop, Number(e.target.value))}
                  style={inputStyle}
                  onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
                  onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Color */}
        <div>
          <label style={labelStyle}>
            {hasCharRange ? `색상 · 선택 ${selLen}자` : "색상"}
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="color"
              value={hasCharRange ? pendingColor : (selectedObject.fill || "#000000")}
              onChange={(e) => {
                setPendingColor(e.target.value);
                onUpdate("fill", e.target.value);
              }}
              style={{ width: 32, height: 32, borderRadius: 5, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", padding: 2 }}
            />
            <TransparentToggle
              size={32}
              // Image objects: fabric.Image renders its bitmap, ignoring fill,
              // so toggling fill="transparent" has no visible effect — exactly
              // the "투명버튼 적용 안 됨" complaint on /editor/72. For images
              // the toggle reads/writes opacity (0 = invisible, 1 = visible)
              // instead. Text / shapes keep the fill-based semantics where the
              // native fill IS the rendered color.
              value={
                hasCharRange
                  ? pendingColor
                  : isImage
                    ? ((selectedObject.opacity ?? 1) === 0 ? "transparent" : "#FFFFFF")
                    : selectedObject.fill
              }
              onChange={(next) => {
                if (isImage && !hasCharRange) {
                  // Map transparent ↔ visible to opacity 0 ↔ 1. The existing
                  // 불투명도 slider tracks the same field so the two stay in sync.
                  onUpdate("opacity", isTransparentValue(next) ? 0 : 1);
                  return;
                }
                setPendingColor(next);
                onUpdate("fill", next);
              }}
            />
            <input
              type="text"
              value={hasCharRange ? pendingColor : (selectedObject.fill || "#000000")}
              onChange={(e) => {
                setPendingColor(e.target.value);
                // text input fires on every keystroke — only commit complete hex
                if (/^#?[0-9a-fA-F]{6}$/.test(e.target.value.trim())) {
                  onUpdate("fill", e.target.value.startsWith("#") ? e.target.value : "#" + e.target.value);
                }
              }}
              style={{ ...inputStyle, flex: 1, fontFamily: "monospace" }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
            />
          </div>
          {/* Gradient toggle — only for shapes (Rect/Circle), not text */}
          {!isText && (selectedObject.type === "rect" || selectedObject.type === "Rect" || selectedObject.type === "circle" || selectedObject.type === "Circle") && (
            <GradientFillEditor selectedObject={selectedObject} onUpdate={onUpdate} />
          )}
        </div>

        {/* Opacity */}
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <label style={{ ...labelStyle, marginBottom: 0 }}>불투명도</label>
            <span style={{ fontSize: 11, color: "var(--accent-text)", fontWeight: 600 }}>
              {Math.round((selectedObject.opacity ?? 1) * 100)}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={selectedObject.opacity ?? 1}
            onChange={(e) => onUpdate("opacity", Number(e.target.value))}
            style={{ width: "100%", accentColor: "var(--accent)" }}
          />
        </div>

        </>)}

        {/* ──────────── EFFECTS TAB ──────────── */}
        {activeTab === "effects" && (<>
        {/* Replace image — single-selection only. Reusing the upload-asset
            endpoint so the file lands in the same /api/images/template-assets/
            namespace as PNG decorations. */}
        {isImage && imageCount === 1 && onReplaceImage && (
          <div>
            <label style={labelStyle}>이미지 교체</label>
            <button
              onClick={() => replaceInputRef.current?.click()}
              disabled={!!replaceBusy}
              title="선택한 이미지를 업로드한 파일로 교체"
              style={{
                width: "100%",
                padding: "7px 10px",
                fontSize: 12,
                fontWeight: 500,
                color: "rgb(180,200,255)",
                background: "rgba(94,106,210,0.18)",
                border: "1px solid rgba(94,106,210,0.45)",
                borderRadius: 5,
                cursor: replaceBusy ? "default" : "pointer",
                opacity: replaceBusy ? 0.6 : 1,
              }}
            >
              {replaceBusy ? "교체 중…" : "🖼️ 다른 이미지로 교체"}
            </button>
            <input
              ref={replaceInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style={{ display: "none" }}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.currentTarget.value = "";
                if (file) await onReplaceImage(file);
              }}
            />
          </div>
        )}
        {/* Image-specific actions */}
        {isImage && onCutout && (
          <div>
            <label style={labelStyle}>
              누끼 제거{imageCount > 1 ? ` · ${imageCount}개 선택` : ""}
            </label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <button
                onClick={() => onCutout("standard")}
                disabled={!!cutoutBusy}
                title={imageCount > 1 ? `${imageCount}개를 병렬 처리 (~4초)` : "배경만 제거 (~4초)"}
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  fontSize: 12,
                  fontWeight: 500,
                  color: "rgb(160,230,190)",
                  background: "rgba(100,200,150,0.15)",
                  border: "1px solid rgba(100,200,150,0.35)",
                  borderRadius: 5,
                  cursor: cutoutBusy ? "default" : "pointer",
                  opacity: cutoutBusy ? 0.6 : 1,
                }}
              >
                {cutoutBusy ? "처리 중…" : imageCount > 1 ? `✂️ 일반 누끼 (${imageCount}개)` : "✂️ 일반 누끼"}
              </button>
              <button
                onClick={() => onCutout("generative")}
                disabled={!!cutoutBusy}
                title={imageCount > 1 ? `${imageCount}개를 병렬 처리, 손까지 제거 (~4초)` : "손·사람까지 제거하고 제품만 추출 (~4초)"}
                style={{
                  width: "100%",
                  padding: "7px 10px",
                  fontSize: 12,
                  fontWeight: 500,
                  color: "rgb(255,200,140)",
                  background: "rgba(255,170,80,0.15)",
                  border: "1px solid rgba(255,170,80,0.35)",
                  borderRadius: 5,
                  cursor: cutoutBusy ? "default" : "pointer",
                  opacity: cutoutBusy ? 0.6 : 1,
                }}
              >
                {cutoutBusy ? "처리 중…" : imageCount > 1 ? `🎯 생성 누끼 (${imageCount}개)` : "🎯 생성 누끼 (손 제거)"}
              </button>
            </div>
          </div>
        )}

        {/* Color fill (image-only): blends a chosen color over the image at
            a given intensity. Backed by fabric's BlendColor filter so the
            original pixels stay intact and the effect can be removed. */}
        {isImage && (
          <ColorFillSection selectedObject={selectedObject} onUpdate={onUpdate} labelStyle={labelStyle} inputStyle={inputStyle} />
        )}
        </>)}

        {/* ──────────── AI TAB ──────────── */}
        {activeTab === "ai" && (<>
          {isImage && (
            <FilterPresetSection
              selectedObject={selectedObject}
              onUpdate={onUpdate}
              labelStyle={labelStyle}
            />
          )}
          {isImage && onEnhance && (
            <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
              <label style={labelStyle}>
                AI 화질 향상{imageCount > 1 ? ` · ${imageCount}개 선택` : ""}
              </label>
              <p style={{ fontSize: 10, color: "var(--text-tertiary)", lineHeight: 1.5, margin: "0 0 8px" }}>
                사진 종류에 맞는 AI 모델로 해상도/디테일을 끌어올립니다. 인터넷 연결 필요, 한 장당 5~10초.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {([
                  { cat: "food",      label: "음식 개선",  desc: "질감·채도 강조" },
                  { cat: "landscape", label: "풍경 개선",  desc: "4x 해상도, 환각 없음" },
                  { cat: "portrait",  label: "인물 개선",  desc: "피부·이목구비 또렷이" },
                ] as const).map(({ cat, label, desc }) => (
                  <button
                    key={cat}
                    onClick={() => onEnhance(cat)}
                    disabled={!!enhanceBusy}
                    title={imageCount > 1 ? `${imageCount}개를 병렬 처리` : desc}
                    style={{
                      width: "100%",
                      padding: "8px 10px",
                      fontSize: 12,
                      fontWeight: 500,
                      color: "rgb(180,200,255)",
                      background: "rgba(94,106,210,0.18)",
                      border: "1px solid rgba(94,106,210,0.45)",
                      borderRadius: 5,
                      cursor: enhanceBusy ? "default" : "pointer",
                      opacity: enhanceBusy ? 0.6 : 1,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-start",
                      gap: 2,
                    }}
                  >
                    <span>{enhanceBusy ? "처리 중…" : label}</span>
                    <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontWeight: 400 }}>{desc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {!isImage && (
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", lineHeight: 1.6 }}>
              이미지를 선택하면 AI 기능이 표시됩니다.
            </div>
          )}
        </>)}

        {/* ──────────── BASIC TAB (continued) ──────────── */}
        {activeTab === "basic" && (<>
        {/* Layer ordering */}
        {onChangeLayer && (
          <div>
            <label style={labelStyle}>레이어 순서</label>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
              {([
                { key: "front", label: "맨 앞", title: "맨 앞으로", path: "M3.75 9.75L9 4.5l5.25 5.25M9 4.5v15" },
                { key: "forward", label: "앞으로", title: "한 단계 앞으로", path: "M4.5 15.75L9 11.25l4.5 4.5M9 11.25V21" },
                { key: "backward", label: "뒤로", title: "한 단계 뒤로", path: "M4.5 8.25L9 12.75l4.5-4.5M9 12.75V3" },
                { key: "back", label: "맨 뒤", title: "맨 뒤로", path: "M3.75 14.25L9 19.5l5.25-5.25M9 19.5v-15" },
              ] as const).map((b) => (
                <button
                  key={b.key}
                  onClick={() => onChangeLayer(b.key as "front" | "forward" | "backward" | "back")}
                  title={b.title}
                  style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 4,
                    padding: "5px 6px", fontSize: 11,
                    background: "var(--bg-overlay)", color: "var(--text-secondary)",
                    border: "1px solid var(--border)", borderRadius: 5, cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                >
                  <svg width="11" height="11" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d={b.path} />
                  </svg>
                  {b.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Text properties */}
        {isText && (
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14, display: "flex", flexDirection: "column", gap: 12 }}>
            <p style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", letterSpacing: "0.08em", textTransform: "uppercase", margin: 0, paddingLeft: 2 }}>
              {textCount > 1 ? `텍스트 · ${textCount}개 일괄 편집` : "텍스트"}
            </p>

            <div>
              <label style={labelStyle}>
                {hasCharRange ? `글꼴 크기 · 선택 ${selLen}자` : "글꼴 크기"}
              </label>
              <input
                type="number"
                min={1}
                max={500}
                value={pendingFontSize !== "" ? pendingFontSize : String(Math.round(currentFontSize))}
                onChange={(e) => {
                  // Track the input string so partial typing ("" or "1" en route
                  // to "100") stays visible, but ALSO commit immediately when the
                  // value is a sane positive number — users don't always know to
                  // press Enter / click elsewhere.
                  const raw = e.target.value;
                  setPendingFontSize(raw);
                  const n = Number(raw);
                  if (raw !== "" && Number.isFinite(n) && n > 0 && n <= 500) {
                    onUpdate("fontSize", n);
                  }
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = "var(--border)";
                  // Drop any half-typed value; the display falls back to currentFontSize
                  setPendingFontSize("");
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === "Escape") {
                    e.currentTarget.blur();
                  }
                }}
                style={inputStyle}
                onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
              />
            </div>

            <div>
              <label style={labelStyle}>
                {hasCharRange ? `굵기 · 선택 ${selLen}자` : "굵기"}
              </label>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={() => onUpdate("fontWeight", currentBold ? "normal" : "bold")}
                  title={hasCharRange ? "선택 영역 굵게 토글" : "전체 굵게 토글 (Ctrl+B)"}
                  style={{
                    width: 36,
                    padding: "5px 0",
                    fontSize: 14,
                    fontWeight: 800,
                    fontFamily: "Georgia, serif",
                    background: currentBold ? "var(--accent)" : "var(--bg-overlay)",
                    color: currentBold ? "white" : "var(--text-secondary)",
                    border: "1px solid",
                    borderColor: currentBold ? "var(--accent)" : "var(--border)",
                    borderRadius: 5,
                    cursor: "pointer",
                  }}
                >
                  B
                </button>
                <select
                  value={currentWeight}
                  onChange={(e) => onUpdate("fontWeight", e.target.value)}
                  style={{ ...inputStyle, flex: 1 }}
                >
                  <option value="normal">일반</option>
                  <option value="bold">굵게</option>
                  <option value="900">아주 굵게</option>
                </select>
              </div>
            </div>

            <div>
              <label style={labelStyle}>정렬</label>
              <div style={{ display: "flex", gap: 4 }}>
                {(["left", "center", "right"] as const).map((align) => (
                  <button
                    key={align}
                    onClick={() => onUpdate("textAlign", align)}
                    style={{
                      flex: 1,
                      padding: "5px 0",
                      fontSize: 11,
                      borderRadius: 4,
                      fontWeight: 500,
                      background: textRef?.textAlign === align ? "var(--accent)" : "var(--bg-overlay)",
                      color: textRef?.textAlign === align ? "white" : "var(--text-secondary)",
                      border: "1px solid",
                      borderColor: textRef?.textAlign === align ? "var(--accent)" : "var(--border)",
                      cursor: "pointer",
                    }}
                  >
                    {align === "left" ? "왼쪽" : align === "center" ? "가운데" : "오른쪽"}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label style={labelStyle}>행간</label>
              <input
                type="number"
                min="0.8"
                max="3"
                step="0.1"
                value={textRef?.lineHeight || 1.4}
                onChange={(e) => onUpdate("lineHeight", Number(e.target.value))}
                style={inputStyle}
                onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
                onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
              />
            </div>
          </div>
        )}

        </>)}

        {/* Delete — always visible regardless of tab */}
        {onDelete && (
          <button
            onClick={onDelete}
            style={{
              marginTop: 4,
              padding: "8px 10px",
              fontSize: 12, fontWeight: 500,
              color: "var(--red)",
              background: "var(--red-muted, rgba(232,91,91,0.12))",
              border: "1px solid rgba(232,91,91,0.25)",
              borderRadius: 6,
              cursor: "pointer",
              display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
            }}
            title="삭제 (Delete)"
          >
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
            </svg>
            요소 삭제
          </button>
        )}

        {/* Outline + Shadow — universal, work for image/shape/text. Live in
            the 효과 tab. */}
        {activeTab === "effects" && (
          <>
            <OutlineSection selectedObject={selectedObject} isText={isText} onUpdate={onUpdate} labelStyle={labelStyle} inputStyle={inputStyle} />
            <ShadowSection selectedObject={selectedObject} onUpdate={onUpdate} labelStyle={labelStyle} inputStyle={inputStyle} />
            {isImage && (
              <ImageAdjustmentsSection
                selectedObject={selectedObject}
                onUpdate={onUpdate}
                labelStyle={labelStyle}
                inputStyle={inputStyle}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ─── Gradient fill toggle for shape objects ───
function GradientFillEditor({
  selectedObject,
  onUpdate,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedObject: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdate: (prop: string, value: any) => void;
}) {
  const fill = selectedObject.fill;
  const isGradient = fill && typeof fill === "object" && (fill.type === "linear" || fill.colorStops);
  const stops: { offset: number; color: string }[] = isGradient
    ? (fill.colorStops || []).map((s: { offset: number; color: string }) => ({ offset: s.offset, color: s.color }))
    : [];
  const dir: "vertical" | "horizontal" | "diagonal" = (() => {
    if (!isGradient) return "vertical";
    const c = fill.coords || {};
    if ((c.x1 || 0) !== (c.x2 || 0) && (c.y1 || 0) !== (c.y2 || 0)) return "diagonal";
    if ((c.x1 || 0) !== (c.x2 || 0)) return "horizontal";
    return "vertical";
  })();

  function makeGradient(stopsIn: { offset: number; color: string }[], direction: string) {
    const w = (selectedObject.width || 200) * (selectedObject.scaleX || 1);
    const h = (selectedObject.height || 200) * (selectedObject.scaleY || 1);
    const coords =
      direction === "horizontal" ? { x1: 0, y1: 0, x2: w, y2: 0 }
      : direction === "diagonal" ? { x1: 0, y1: 0, x2: w, y2: h }
      : { x1: 0, y1: 0, x2: 0, y2: h };
    return { type: "linear", coords, colorStops: stopsIn };
  }

  function toggleGradient() {
    if (isGradient) {
      onUpdate("fill", stops[0]?.color || "#000000");
    } else {
      onUpdate("fill", makeGradient(
        [
          { offset: 0, color: typeof fill === "string" ? fill : "#000000" },
          { offset: 1, color: "rgba(0,0,0,0)" },
        ],
        "vertical",
      ));
    }
  }

  function updateStop(i: number, patch: Partial<{ offset: number; color: string }>) {
    const next = stops.map((s, idx) => (idx === i ? { ...s, ...patch } : s));
    onUpdate("fill", makeGradient(next, dir));
  }

  function setDir(d: string) {
    onUpdate("fill", makeGradient(stops, d));
  }

  return (
    <div style={{ marginTop: 8 }}>
      <button
        onClick={toggleGradient}
        style={{
          width: "100%",
          padding: "5px 8px",
          fontSize: 11,
          fontWeight: 500,
          background: isGradient ? "var(--accent)" : "var(--bg-overlay)",
          color: isGradient ? "white" : "var(--text-secondary)",
          border: "1px solid",
          borderColor: isGradient ? "var(--accent)" : "var(--border)",
          borderRadius: 4,
          cursor: "pointer",
        }}
      >
        {isGradient ? "그라데이션 끄기 (단색으로)" : "그라데이션 채우기"}
      </button>
      {isGradient && (
        <div style={{ marginTop: 6, padding: 6, background: "var(--bg-overlay)", borderRadius: 4 }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
            {(["vertical", "horizontal", "diagonal"] as const).map((d) => (
              <button
                key={d}
                onClick={() => setDir(d)}
                style={{
                  flex: 1,
                  padding: "3px 0",
                  fontSize: 10,
                  borderRadius: 3,
                  background: dir === d ? "var(--accent)" : "transparent",
                  color: dir === d ? "white" : "var(--text-secondary)",
                  border: "1px solid",
                  borderColor: dir === d ? "var(--accent)" : "var(--border)",
                  cursor: "pointer",
                }}
              >
                {d === "vertical" ? "↓" : d === "horizontal" ? "→" : "↘"}
              </button>
            ))}
          </div>
          {stops.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4, alignItems: "center" }}>
              <input
                type="color"
                value={(s.color.match(/^#[0-9a-fA-F]{6}/) || ["#000000"])[0]}
                onChange={(e) => updateStop(i, { color: e.target.value })}
                style={{ width: 28, height: 22, padding: 0, border: "1px solid var(--border)", borderRadius: 3, cursor: "pointer" }}
              />
              <TransparentToggle
                size={22}
                value={s.color}
                onChange={(next) => updateStop(i, { color: next })}
              />
              <input
                type="number"
                step={0.05}
                min={0}
                max={1}
                value={s.offset}
                onChange={(e) => updateStop(i, { offset: Number(e.target.value) })}
                style={{ flex: 1, padding: "3px 6px", fontSize: 11, background: "var(--bg-base)", border: "1px solid var(--border)", borderRadius: 3, color: "var(--text-primary)" }}
              />
              <span style={{ fontSize: 9, color: "var(--text-tertiary)", fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.color}
              </span>
            </div>
          ))}
          <button
            onClick={() => {
              const next = [...stops, { offset: 0.5, color: "rgba(0,0,0,0.5)" }].sort((a, b) => a.offset - b.offset);
              onUpdate("fill", makeGradient(next, dir));
            }}
            style={{ width: "100%", padding: "3px 0", fontSize: 10, marginTop: 2, background: "transparent", color: "var(--text-secondary)", border: "1px dashed var(--border)", borderRadius: 3, cursor: "pointer" }}
          >
            + 스톱 추가
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Outline control ────────────────────────────────────────────────────
// Adds a stroke around image/shape/text. For text we flip paintFirst:"stroke"
// so the outline sits behind the fill (matches Miricanvas's behavior — the
// glyph reads as filled-with-outline rather than fill-eats-into-stroke).
interface OutlineSectionProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedObject: any;
  isText: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdate: (prop: string, value: any) => void;
  labelStyle: React.CSSProperties;
  inputStyle: React.CSSProperties;
}

const OUTLINE_DEFAULT_COLOR = "#000000";
const OUTLINE_DEFAULT_WIDTH = 4;
const OUTLINE_MAX = 216;

function OutlineSection({ selectedObject, isText, onUpdate, labelStyle, inputStyle }: OutlineSectionProps) {
  // Read from live fabric ref when available — the snapshot strips methods
  // but not props; stroke/strokeWidth survive.
  const obj = selectedObject?.__fabricRef ?? selectedObject;
  const rawStroke = obj?.stroke;
  const strokeColor = typeof rawStroke === "string" ? rawStroke : OUTLINE_DEFAULT_COLOR;
  const strokeWidth = Number(obj?.strokeWidth) || 0;
  // Toggle reflects intent (is an outline configured?) — not whether it is
  // currently being drawn. Dragging the thickness slider to 0 keeps the
  // section open so users can crank it back up without re-enabling first.
  const enabled = !!rawStroke;

  function toggleOn() {
    const color = strokeColor || OUTLINE_DEFAULT_COLOR;
    // Fabric assigns strokeWidth=1 to most classes by default even when
    // stroke is null. Treat "no outline yet" as the trigger to use our
    // visible default (4px) so toggling ON actually shows something.
    const hadOutline = !!rawStroke;
    const width = hadOutline && strokeWidth > 0 ? strokeWidth : OUTLINE_DEFAULT_WIDTH;
    onUpdate("stroke", color);
    onUpdate("strokeWidth", width);
    onUpdate("strokeUniform", true);
    // For text, draw stroke first so the fill sits on top — otherwise the
    // stroke chews into the glyph and the text reads thinner than intended.
    if (isText) onUpdate("paintFirst", "stroke");
  }
  function toggleOff() {
    onUpdate("stroke", null);
    onUpdate("strokeWidth", 0);
  }
  function setColor(c: string) { onUpdate("stroke", c); }
  function setWidth(n: number) {
    const v = Math.max(0, Math.min(OUTLINE_MAX, Math.round(n)));
    onUpdate("strokeWidth", v);
    // Keep the stroke color set even at width 0 so the section stays open and
    // bumping the slider back up restores the outline immediately. (Width 0
    // makes fabric draw nothing — visually identical to "off" — but the
    // configuration persists.)
    if (v > 0 && !rawStroke) {
      onUpdate("stroke", strokeColor);
      onUpdate("strokeUniform", true);
      if (isText) onUpdate("paintFirst", "stroke");
    }
  }

  const SwitchToggle = (
    <button
      type="button"
      onClick={() => (enabled ? toggleOff() : toggleOn())}
      aria-pressed={enabled}
      title={enabled ? "외곽선 끄기" : "외곽선 켜기"}
      style={{
        position: "relative",
        width: 32, height: 18,
        borderRadius: 9, border: "none",
        background: enabled ? "var(--accent)" : "var(--bg-overlay)",
        cursor: "pointer", padding: 0, transition: "background 0.15s",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 2, left: enabled ? 16 : 2,
          width: 14, height: 14, borderRadius: "50%",
          background: "white",
          transition: "left 0.15s",
          boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
        }}
      />
    </button>
  );

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <label style={{ ...labelStyle, marginBottom: 0 }}>외곽선</label>
        {SwitchToggle}
      </div>
      {enabled && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* 색상 */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>색상</span>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <input
                type="color"
                value={strokeColor}
                onChange={(e) => setColor(e.target.value)}
                style={{ width: 28, height: 22, borderRadius: 4, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", padding: 1 }}
              />
              <TransparentToggle
                size={22}
                value={strokeColor}
                onChange={(next) => setColor(next)}
              />
              <input
                type="text"
                value={strokeColor}
                onChange={(e) => {
                  const v = e.target.value.trim();
                  if (/^#?[0-9a-fA-F]{6}$/.test(v)) setColor(v.startsWith("#") ? v : "#" + v);
                }}
                style={{ ...inputStyle, width: 86, padding: "2px 6px", fontSize: 11, fontFamily: "monospace" }}
              />
            </div>
          </div>
          {/* 두께 */}
          <div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>두께</span>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
                <input
                  type="number"
                  min={0}
                  max={OUTLINE_MAX}
                  value={strokeWidth}
                  onChange={(e) => setWidth(Number(e.target.value))}
                  style={{ ...inputStyle, width: 56, padding: "2px 5px", fontSize: 11, textAlign: "right" }}
                />
                <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>px</span>
              </div>
            </div>
            <input
              type="range"
              min={0}
              max={OUTLINE_MAX}
              value={strokeWidth}
              onChange={(e) => setWidth(Number(e.target.value))}
              style={{ width: "100%", accentColor: "var(--accent)", margin: 0 }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Shadow control ─────────────────────────────────────────────────────
interface ShadowSectionProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedObject: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdate: (prop: string, value: any) => void;
  labelStyle: React.CSSProperties;
  inputStyle: React.CSSProperties;
}

interface ShadowSpec {
  color: string;     // hex #rrggbb
  opacity: number;   // 0-100
  angle: number;     // 0-360 degrees
  distance: number;  // 0-100 (px in design space)
  blur: number;      // 0-100 (px)
}

// Defaults tuned to be visible immediately on a 1080×1350 design at typical
// editor display sizes. Too-subtle defaults made users think the feature
// wasn't applied at all.
const DEFAULT_SHADOW: ShadowSpec = { color: "#000000", opacity: 70, angle: 135, distance: 24, blur: 24 };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseShadowFromObject(sh: any): ShadowSpec | null {
  if (!sh) return null;
  let color = "rgba(0,0,0,0.5)";
  let offsetX = 0, offsetY = 0, blur = 0;
  if (typeof sh === "string") {
    const m = sh.match(/(rgba?\([^\)]+\)|#[0-9a-fA-F]+)\s+(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px\s+(\d+(?:\.\d+)?)px/);
    if (m) {
      color = m[1]; offsetX = parseFloat(m[2]); offsetY = parseFloat(m[3]); blur = parseFloat(m[4]);
    }
  } else {
    color = sh.color || "rgba(0,0,0,0.5)";
    offsetX = Number(sh.offsetX) || 0;
    offsetY = Number(sh.offsetY) || 0;
    blur = Number(sh.blur) || 0;
  }
  let opacity = 100;
  let hexColor = "#000000";
  const rgba = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
  if (rgba) {
    const r = parseInt(rgba[1]), g = parseInt(rgba[2]), b = parseInt(rgba[3]);
    const a = rgba[4] != null ? parseFloat(rgba[4]) : 1;
    hexColor = `#${r.toString(16).padStart(2,"0")}${g.toString(16).padStart(2,"0")}${b.toString(16).padStart(2,"0")}`;
    opacity = Math.round(a * 100);
  } else if (color.startsWith("#") && color.length === 7) {
    hexColor = color;
  }
  const distance = Math.round(Math.sqrt(offsetX * offsetX + offsetY * offsetY));
  let angle = 0;
  if (distance > 0) {
    angle = Math.round((Math.atan2(offsetY, offsetX) * 180) / Math.PI);
    if (angle < 0) angle += 360;
  }
  return { color: hexColor, opacity, angle, distance, blur: Math.round(blur) };
}

function buildShadowString(spec: ShadowSpec): string {
  const rad = (spec.angle * Math.PI) / 180;
  const offsetX = Math.round(spec.distance * Math.cos(rad));
  const offsetY = Math.round(spec.distance * Math.sin(rad));
  const hex = spec.color.replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16) || 0;
  const g = parseInt(hex.slice(2, 4), 16) || 0;
  const b = parseInt(hex.slice(4, 6), 16) || 0;
  const a = (Math.max(0, Math.min(100, spec.opacity)) / 100).toFixed(2);
  return `rgba(${r},${g},${b},${a}) ${offsetX}px ${offsetY}px ${spec.blur}px`;
}

// Defined at module scope (NOT inside ShadowSection) so React keeps the
// slider mounted across renders. When this lived inside the parent, every
// state update returned a fresh function reference — React treated it as a
// new component type, unmounted the old slider mid-drag, and the user's
// pointer drag was lost after the first move event.
function ShadowParamRow({ label, suffix, min, max, value, onChange, inputStyle }: {
  label: string; suffix: string; min: number; max: number; value: number;
  onChange: (n: number) => void;
  inputStyle: React.CSSProperties;
}) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{label}</span>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
          <input
            type="number"
            min={min}
            max={max}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            style={{ ...inputStyle, width: 48, padding: "2px 5px", fontSize: 11, textAlign: "right" }}
          />
          <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{suffix}</span>
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: "var(--accent)", margin: 0 }}
      />
    </div>
  );
}

function ShadowSection({ selectedObject, onUpdate, labelStyle, inputStyle }: ShadowSectionProps) {
  // Live state from the fabric object (if it has a shadow filter).
  const parsed = parseShadowFromObject(selectedObject?.shadow ?? selectedObject?.__fabricRef?.shadow);
  const enabled = !!parsed;

  // Pending values for when the checkbox is OFF — keeps the user's last
  // adjustments visible in the controls so they can dial values in before
  // turning the effect on, and so values aren't lost when toggling off & on.
  const [draft, setDraft] = useState<ShadowSpec>(parsed || DEFAULT_SHADOW);
  // Sync draft when the object's actual shadow changes (e.g. selection change,
  // undo/redo, programmatic update).
  useEffect(() => { if (parsed) setDraft(parsed); }, [parsed?.color, parsed?.opacity, parsed?.angle, parsed?.distance, parsed?.blur]);

  // What to show in the controls right now. When enabled use the live shadow;
  // when disabled use the draft so the user sees their work-in-progress.
  const spec = parsed || draft;

  function update(next: Partial<ShadowSpec>) {
    const merged = { ...spec, ...next };
    setDraft(merged);
    // Only push to the canvas when the checkbox is checked — otherwise we
    // just stage the value. The user can preview by checking the box.
    if (enabled) onUpdate("shadow", buildShadowString(merged));
  }
  function toggle(checked: boolean) {
    if (checked) onUpdate("shadow", buildShadowString(draft));
    else onUpdate("shadow", null);
  }

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <label style={{ ...labelStyle, marginBottom: 0 }}>그림자</label>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 11, color: "var(--text-secondary)" }}>
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => toggle(e.target.checked)}
            style={{ margin: 0, accentColor: "var(--accent)" }}
          />
          적용
        </label>
      </div>
      {/* Controls always visible — user can edit values even with the checkbox
          off, then flip it on to apply. */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10, opacity: enabled ? 1 : 0.85 }}>
        {/* 색상 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>색상</span>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "monospace" }}>
              {spec.color}
            </span>
            <input
              type="color"
              value={spec.color}
              onChange={(e) => update({ color: e.target.value })}
              style={{ width: 22, height: 22, padding: 0, border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer", background: "transparent" }}
            />
            <TransparentToggle
              size={22}
              value={spec.color}
              onChange={(next) => update({ color: next })}
            />
          </div>
        </div>
        <ShadowParamRow label="방향" suffix="°" min={0} max={360} value={spec.angle}
          onChange={(n) => update({ angle: n })} inputStyle={inputStyle} />
        <ShadowParamRow label="불투명도" suffix="%" min={0} max={100} value={spec.opacity}
          onChange={(n) => update({ opacity: n })} inputStyle={inputStyle} />
        <ShadowParamRow label="거리" suffix="" min={0} max={100} value={spec.distance}
          onChange={(n) => update({ distance: n })} inputStyle={inputStyle} />
        <ShadowParamRow label="흐림" suffix="" min={0} max={100} value={spec.blur}
          onChange={(n) => update({ blur: n })} inputStyle={inputStyle} />
      </div>
    </div>
  );
}

// ─── Image color-fill (BlendColor filter) ──────────────────────────────
interface ColorFillProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedObject: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdate: (prop: string, value: any) => void;
  labelStyle: React.CSSProperties;
  inputStyle: React.CSSProperties;
}

interface ColorFillSpec {
  color: string;     // hex #rrggbb
  intensity: number; // 0-100, mapped to filter alpha
}

const DEFAULT_FILL: ColorFillSpec = { color: "#FF3B6A", intensity: 50 };

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseColorFill(obj: any): ColorFillSpec | null {
  if (!obj) return null;
  // Inspect fabric Image filters[]. Look for BlendColor with mode "tint".
  // Filters serialise to plain objects on toJSON output, so the entries can
  // be either fabric.filters.BlendColor instances or plain {type, ...} dicts.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filters: any[] = obj.filters || obj.__fabricRef?.filters || [];
  for (const f of filters) {
    const t = f?.type || f?.constructor?.name || "";
    if (t === "BlendColor" || t === "blend-color") {
      const color = String(f.color || "#000000");
      const alpha = typeof f.alpha === "number" ? f.alpha : 1;
      // Normalize color to hex
      let hex = "#000000";
      if (color.startsWith("#") && color.length === 7) hex = color;
      else {
        const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
        if (m) {
          const r = parseInt(m[1]), g = parseInt(m[2]), b = parseInt(m[3]);
          hex = `#${r.toString(16).padStart(2,"0")}${g.toString(16).padStart(2,"0")}${b.toString(16).padStart(2,"0")}`;
        }
      }
      return { color: hex, intensity: Math.round(alpha * 100) };
    }
  }
  return null;
}

function ColorFillSection({ selectedObject, onUpdate, labelStyle, inputStyle }: ColorFillProps) {
  // No on/off toggle — controls are always visible. When intensity > 0 the
  // BlendColor filter is present; intensity 0 means it's removed. This
  // matches Miricanvas's "always-on" panel and avoids the extra click.
  const parsed = parseColorFill(selectedObject);
  // Show the picker with sensible defaults even when no filter is set yet.
  const spec: ColorFillSpec = parsed || { color: DEFAULT_FILL.color, intensity: 0 };

  function update(next: Partial<ColorFillSpec>) {
    const merged = { ...spec, ...next };
    // Treat intensity 0 as "no fill" — remove the filter cleanly rather than
    // leaving a no-op BlendColor in the filter chain.
    if (!merged.intensity || merged.intensity <= 0) onUpdate("__colorFill", null);
    else onUpdate("__colorFill", merged);
  }

  return (
    <div style={{ marginTop: 4 }}>
      <label style={{ ...labelStyle, marginBottom: 6 }}>색상 채우기</label>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10, color: "var(--text-tertiary)", width: 50 }}>색상</span>
          <input
            type="color"
            value={spec.color}
            onChange={(e) => update({ color: e.target.value })}
            style={{ width: 32, height: 24, padding: 0, border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer", background: "transparent" }}
          />
          <TransparentToggle
            size={24}
            value={spec.color}
            onChange={(next) => update({ color: next })}
          />
          <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "monospace", flex: 1, overflow: "hidden" }}>
            {spec.color}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10, color: "var(--text-tertiary)", width: 50 }}>강도</span>
          <input
            type="range"
            min={0}
            max={100}
            value={spec.intensity}
            onChange={(e) => update({ intensity: Number(e.target.value) })}
            style={{ flex: 1, accentColor: "var(--accent)" }}
          />
          <input
            type="number"
            min={0}
            max={100}
            value={spec.intensity}
            onChange={(e) => update({ intensity: Number(e.target.value) })}
            style={{ ...inputStyle, width: 50, padding: "3px 5px", fontSize: 10 }}
          />
          <span style={{ fontSize: 9, color: "var(--text-tertiary)", width: 14 }}>%</span>
        </div>
      </div>
    </div>
  );
}

// ─── Image-only one-click filter presets (화사한/선명한/밝은/...) ───
//
// User feedback (carousel studio feedback slide 7): images need preset filters
// like Miricanvas/Canva — pick a thumbnail, get a tuned combination of
// brightness/contrast/saturation/sepia/etc. Fine-tuning still happens via the
// sliders in the 효과 tab; this section is just the quick path.
//
// CSS filter() strings power the thumbnail previews so the user sees what
// they'd get before clicking. The fabric-side `__filterPreset` handler in
// CanvasEditor reuses the same recipe to swap the actual fabric filter slots.
const FILTER_PRESETS: { key: string; label: string; css: string }[] = [
  { key: "none",      label: "원본",     css: "" },
  { key: "vivid",     label: "화사한",   css: "saturate(1.4) brightness(1.1)" },
  { key: "sharp",     label: "선명한",   css: "contrast(1.3) saturate(1.2)" },
  { key: "bright",    label: "밝은",     css: "brightness(1.2) contrast(1.05)" },
  { key: "warm",      label: "따뜻한",   css: "sepia(0.3) saturate(1.2) brightness(1.05)" },
  { key: "cool",      label: "시원한",   css: "hue-rotate(-10deg) saturate(1.15)" },
  { key: "vintage",   label: "빈티지",   css: "sepia(0.5) contrast(1.1) saturate(0.8)" },
  { key: "bw",        label: "흑백",     css: "grayscale(1) contrast(1.1)" },
  { key: "cinematic", label: "영화같은", css: "contrast(1.3) saturate(0.7) brightness(0.9) sepia(0.2)" },
  { key: "sunset",    label: "노을",     css: "sepia(0.4) saturate(1.3) hue-rotate(-20deg) brightness(1.1)" },
  { key: "dreamy",    label: "몽환적",   css: "brightness(1.15) contrast(0.75) saturate(1.15) blur(0.5px)" },
  { key: "faded",     label: "페이드",   css: "contrast(0.8) saturate(0.65) brightness(1.1) sepia(0.15)" },
];

function FilterPresetSection({
  selectedObject,
  onUpdate,
  labelStyle,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedObject: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdate: (prop: string, value: any) => void;
  labelStyle: React.CSSProperties;
}) {
  // Pull the original bitmap URL for thumbnail previews. Snapshot first, then
  // the real fabric ref — the snapshot omits non-enumerable methods like
  // getSrc(), so __fabricRef is the reliable path.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ref: any = selectedObject?.__fabricRef || selectedObject;
  const src: string | undefined =
    (typeof ref?.getSrc === "function" ? ref.getSrc() : null) ||
    ref?._originalElement?.src ||
    ref?.src;

  const active: string | undefined =
    selectedObject?.__filterPreset || ref?.__filterPreset || undefined;

  return (
    <div>
      <label style={labelStyle}>필터 프리셋</label>
      <p style={{ fontSize: 10, color: "var(--text-tertiary)", lineHeight: 1.5, margin: "0 0 8px" }}>
        한 번에 적용. 효과 탭 슬라이더로 미세 조정 가능.
      </p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
        {FILTER_PRESETS.map((p) => {
          const isActive = active ? active === p.key : p.key === "none";
          return (
            <button
              key={p.key}
              type="button"
              onClick={() => onUpdate("__filterPreset", p.key)}
              title={p.label}
              style={{
                display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                padding: 3, background: "transparent",
                border: "1.5px solid",
                borderColor: isActive ? "var(--accent)" : "transparent",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              <div
                style={{
                  width: "100%", aspectRatio: "1 / 1",
                  borderRadius: 4, overflow: "hidden",
                  background: "var(--bg-overlay)",
                  border: "1px solid var(--border)",
                  position: "relative",
                }}
              >
                {src && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={src}
                    alt={p.label}
                    draggable={false}
                    style={{
                      width: "100%", height: "100%",
                      objectFit: "cover", display: "block",
                      filter: p.css,
                    }}
                  />
                )}
              </div>
              <span
                style={{
                  fontSize: 10,
                  color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                  fontWeight: isActive ? 600 : 400,
                  whiteSpace: "nowrap",
                }}
              >
                {p.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Image-only photo adjustments (밝기/대비/채도/컬러톤/온도/선명·흐림) ───
//
// User feedback (carousel studio feedback slide 6): images need the same kind
// of tone-curve controls that every other editor has. Each slider rides on
// top of an existing fabric filter (Brightness, Contrast, Saturation,
// HueRotation, ColorMatrix-as-temperature, Blur+Convolute-as-sharpness) and
// the CanvasEditor side owns the actual filter chain mutation — this panel
// just reads the current slot from selectedObject.filters and dispatches an
// __-prefixed update.
//
// Why -100..100 sliders instead of native units: every adjustment in this
// section is the same shape, the consumer-grade ranges (BRIGHT/CONTRAST/SAT
// in -1..1, hue in radians, temperature as a custom 0..0.3 lift) would each
// need their own input. -100..100 normalizes them and matches the mental
// model of "Instagram-style edit sliders".
function ImageAdjustmentsSection({
  selectedObject,
  onUpdate,
  labelStyle,
  inputStyle,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  selectedObject: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onUpdate: (prop: string, value: any) => void;
  labelStyle: React.CSSProperties;
  inputStyle: React.CSSProperties;
}) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const filters: any[] = Array.isArray(selectedObject?.filters) ? selectedObject.filters : [];

  // Read the slider position for a "single-slot" filter (Brightness etc.).
  // Multiple values would be ambiguous — fabric only lets one of each type
  // own the slot at a time because the CanvasEditor handler strips dupes.
  //
  // We try several name fields because production builds may mangle the
  // constructor name (terser drops debug names) while fabric also exposes
  // a static `type` string AND a serialized `type` property on toObject.
  function filterMatches(x: unknown, ctor: string): boolean {
    if (!x || typeof x !== "object") return false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const obj = x as any;
    const cn = obj?.constructor?.name || "";
    const tp = obj?.type || "";
    const stt = obj?.constructor?.type || "";  // fabric's static type marker
    const lc = ctor.toLowerCase();
    return [cn, tp, stt].some((s) => {
      const v = String(s || "").toLowerCase();
      return v === lc || v.endsWith("." + lc);
    });
  }
  function readSlot(ctor: string, prop: string, range: number): number {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const f = filters.find((x) => filterMatches(x, ctor)) as any;
    if (!f) return 0;
    return Math.round(((f[prop] || 0) / range) * 100);
  }
  function readTemperature(): number {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cm = filters.find((f: any) => filterMatches(f, "ColorMatrix") && f.__adj === "temperature") as any;
    if (!cm || !Array.isArray(cm.matrix)) return 0;
    const t = (cm.matrix[0] ?? 1) - 1;
    return Math.round((t / 0.3) * 100);
  }
  function readSharpness(): number {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const blur = filters.find((f: any) => filterMatches(f, "Blur")) as any;
    if (blur) return -Math.round(((blur.blur || 0) / 0.5) * 100);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const conv = filters.find((f: any) => filterMatches(f, "Convolute") && f.__adj === "sharpen") as any;
    if (conv && Array.isArray(conv.matrix)) {
      const c = conv.matrix[4] ?? 1;
      const s = (c - 1) / 4;
      return Math.round(s * 100);
    }
    return 0;
  }

  // The slider position lives in LOCAL state so a dragged slider stays put
  // even when the filter snapshot from CanvasEditor doesn't round-trip the
  // value (e.g. production minifies fabric class names and readSlot can't
  // recover the current setting). The state resets on every selection
  // change so a different image starts fresh from whatever filters it has.
  //
  // The slider is the source of truth for THIS panel session; CanvasEditor
  // owns the actual fabric filter chain.
  const sigBase = selectedObject?.__uid__ || selectedObject?.cacheKey || (selectedObject ? "obj" : "none");
  const [localValues, setLocalValues] = useState<Record<string, number>>(() => ({
    __brightness: readSlot("Brightness", "brightness", 1),
    __contrast: readSlot("Contrast", "contrast", 1),
    __saturation: readSlot("Saturation", "saturation", 1),
    __hue: readSlot("HueRotation", "rotation", Math.PI),
    __temperature: readTemperature(),
    __sharpness: readSharpness(),
  }));
  const [signedSig, setSignedSig] = useState<string>(sigBase);
  if (signedSig !== sigBase) {
    // Selection changed — reset from the new object's filters.
    setSignedSig(sigBase);
    setLocalValues({
      __brightness: readSlot("Brightness", "brightness", 1),
      __contrast: readSlot("Contrast", "contrast", 1),
      __saturation: readSlot("Saturation", "saturation", 1),
      __hue: readSlot("HueRotation", "rotation", Math.PI),
      __temperature: readTemperature(),
      __sharpness: readSharpness(),
    });
  }

  const adjustments: { label: string; prop: string; value: number; min: number; max: number; help?: string }[] = [
    { label: "밝기",      prop: "__brightness", value: localValues.__brightness, min: -100, max: 100 },
    { label: "대비",      prop: "__contrast",   value: localValues.__contrast,   min: -100, max: 100 },
    { label: "채도",      prop: "__saturation", value: localValues.__saturation, min: -100, max: 100 },
    { label: "컬러톤",    prop: "__hue",        value: localValues.__hue,         min: -100, max: 100, help: "색조 회전" },
    { label: "온도",      prop: "__temperature", value: localValues.__temperature, min: -100, max: 100, help: "왼쪽: 시원, 오른쪽: 따뜻" },
    { label: "선명/흐림", prop: "__sharpness",  value: localValues.__sharpness,   min: -100, max: 100, help: "왼쪽: 흐림, 오른쪽: 선명" },
  ];

  function dispatch(prop: string, v: number) {
    setLocalValues((cur) => ({ ...cur, [prop]: v }));
    onUpdate(prop, v);
  }

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
      <label style={{ ...labelStyle, marginBottom: 6 }}>이미지 보정</label>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {adjustments.map((a) => (
          <div key={a.prop} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {/* Row 1 — label + bold value badge so the user always sees the
                exact 정도 (degree/level) at a glance, even before touching
                the slider. Reset button sits next to the value for symmetry. */}
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                title={a.help || a.label}
                style={{ fontSize: 11, color: "var(--text-secondary)", flex: 1 }}
              >
                {a.label}
              </span>
              <input
                type="number"
                inputMode="numeric"
                aria-label={`${a.label} 값`}
                min={a.min}
                max={a.max}
                step={1}
                value={a.value}
                onChange={(e) => {
                  // type=number doesn't clamp until blur, so do it inline
                  // so typing past the range snaps the canvas right away.
                  const raw = e.target.value;
                  if (raw === "" || raw === "-") {
                    dispatch(a.prop, 0);
                    return;
                  }
                  let n = Number(raw);
                  if (Number.isNaN(n)) return;
                  if (n > a.max) n = a.max;
                  if (n < a.min) n = a.min;
                  dispatch(a.prop, n);
                }}
                onFocus={(e) => e.currentTarget.select()}
                style={{
                  width: 56,
                  textAlign: "right",
                  padding: "3px 6px",
                  fontSize: 12,
                  fontWeight: 600,
                  fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, monospace)",
                  fontVariantNumeric: "tabular-nums",
                  color: a.value === 0 ? "var(--text-tertiary)" : "var(--text-primary)",
                  background: a.value === 0 ? "transparent" : "var(--bg-overlay)",
                  borderRadius: 4,
                  border: a.value === 0 ? "1px solid var(--border)" : "1px solid var(--accent)",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
              <button
                type="button"
                onClick={() => dispatch(a.prop, 0)}
                title="초기화"
                disabled={a.value === 0}
                style={{
                  width: 20,
                  height: 20,
                  padding: 0,
                  fontSize: 12,
                  lineHeight: "18px",
                  color: a.value === 0 ? "var(--text-tertiary)" : "var(--text-secondary)",
                  background: "transparent",
                  border: "1px solid var(--border)",
                  borderRadius: 3,
                  cursor: a.value === 0 ? "default" : "pointer",
                  opacity: a.value === 0 ? 0.4 : 1,
                  flexShrink: 0,
                }}
              >
                ↺
              </button>
            </div>
            {/* Row 2 — slider takes the full row width so the user has the
                widest possible drag range, especially helpful on a narrow
                220px property panel. */}
            <input
              type="range"
              min={a.min}
              max={a.max}
              value={a.value}
              onChange={(e) => dispatch(a.prop, Number(e.target.value))}
              style={{ width: "100%", accentColor: "var(--accent)" }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
