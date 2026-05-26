"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { HexColorPicker } from "react-colorful";
import { getByPath } from "@/lib/template-paths";
import type { TemplateData, FabricMeta, TextStyle, GridSpec, ShadowSpec, GradientFill, Decoration } from "./types";
import { GradientBarEditor, splitColor, mergeColor, type GradValue } from "@/components/GradientBarEditor";

interface Props {
  template: TemplateData;
  layoutName: string;
  selected: FabricMeta | null;
  onChange: (path: string, value: unknown) => void;
  onMoveLayer?: (direction: "front" | "forward" | "backward" | "back") => void;
  onDeleteSelected?: () => void;
  onReplaceImage?: (file: File) => Promise<void> | void;
  onCutoutImage?: (mode: "standard" | "generative") => Promise<void> | void;
  imageBusy?: { replace?: boolean; cutout?: boolean };
}

// ─── Editor-matching design tokens ──────────────────────────────────────
const ROW_GAP = 14;
const LABEL_STYLE: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: "var(--text-tertiary)",
  letterSpacing: "0.07em",
  textTransform: "uppercase",
  display: "block",
  marginBottom: 6,
};
const INPUT_STYLE: React.CSSProperties = {
  width: "100%",
  padding: "5px 8px",
  fontSize: 12,
  background: "var(--bg-overlay)",
  color: "var(--text-primary)",
  border: "1px solid var(--border)",
  borderRadius: 5,
  outline: "none",
};

/** Compact 0~360° angle picker — rotary indicator + slider + number.
 *  Used for background and overlay gradient direction (피드백 #10 slide 1).
 *  Legacy `direction` enum is translated upstream via DIR_TO_ANGLE. */
function AngleRow({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  const setNorm = (a: number) => onChange(((Math.round(a) % 360) + 360) % 360);
  return (
    <div>
      <label style={LABEL_STYLE}>{label}</label>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <div
          title="드래그로 각도 조절"
          onPointerDown={(e) => {
            e.preventDefault();
            const el = e.currentTarget;
            const compute = (ev: PointerEvent | React.PointerEvent) => {
              const r = el.getBoundingClientRect();
              const dx = ev.clientX - (r.left + r.width / 2);
              const dy = ev.clientY - (r.top + r.height / 2);
              setNorm((Math.atan2(dx, -dy) * 180) / Math.PI);
            };
            compute(e);
            const move = (ev: PointerEvent) => compute(ev);
            const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
            window.addEventListener("pointermove", move);
            window.addEventListener("pointerup", up);
          }}
          style={{
            width: 26, height: 26, borderRadius: "50%",
            border: "1px solid var(--border)", background: "var(--bg-base)",
            position: "relative", flexShrink: 0, cursor: "grab", touchAction: "none",
          }}
        >
          <div style={{
            position: "absolute", left: "50%", top: "50%",
            width: 2, height: 11, background: "var(--accent)",
            transformOrigin: "50% 100%",
            transform: `translate(-50%, -100%) rotate(${value}deg)`,
            borderRadius: 1,
          }} />
        </div>
        <input
          type="range" min={0} max={360} step={1}
          value={value}
          onChange={(e) => setNorm(Number(e.target.value))}
          style={{ flex: 1, minWidth: 0 }}
        />
        <input
          type="number" min={0} max={360} step={1}
          value={value}
          onChange={(e) => setNorm(Number(e.target.value))}
          style={{ ...INPUT_STYLE, width: 50, padding: "4px 6px", textAlign: "right" }}
        />
        <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>°</span>
      </div>
    </div>
  );
}

// Legacy direction enum → CSS angle (matches GradientBarEditor's mapping).
const DIR_TO_ANGLE_BG = { vertical: 180, horizontal: 90, diagonal: 135 } as const;
type LegacyDir = keyof typeof DIR_TO_ANGLE_BG;
const SECTION_STYLE: React.CSSProperties = {
  padding: "12px 14px",
  borderBottom: "1px solid var(--border)",
  display: "flex",
  flexDirection: "column",
  gap: ROW_GAP,
};
const SECTION_TITLE: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  color: "var(--text-tertiary)",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  paddingLeft: 2,
  margin: 0,
};
const isBoldWeight = (w: unknown) => {
  const s = String(w);
  return s === "bold" || s === "700" || s === "800" || s === "900";
};

// ─── Small generic controls (editor-style) ─────────────────────────────

function NumberRow({
  label,
  value,
  step = 1,
  min,
  max,
  suffix,
  onChange,
}: {
  label: string;
  value: number | undefined;
  step?: number;
  min?: number;
  max?: number;
  suffix?: string;
  onChange: (n: number) => void;
}) {
  return (
    <div>
      <label style={LABEL_STYLE}>{label}</label>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input
          type="number"
          value={value ?? 0}
          step={step}
          min={min}
          max={max}
          onChange={(e) => {
            const v = e.target.value === "" ? 0 : Number(e.target.value);
            if (Number.isFinite(v)) onChange(v);
          }}
          style={{ ...INPUT_STYLE, flex: 1 }}
        />
        {suffix && <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{suffix}</span>}
      </div>
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step = 1,
  suffix,
  onChange,
}: {
  label: string;
  value: number | undefined;
  min: number;
  max: number;
  step?: number;
  suffix?: string;
  onChange: (n: number) => void;
}) {
  const v = value ?? min;
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <label style={{ ...LABEL_STYLE, marginBottom: 0 }}>{label}</label>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          <input
            type="number"
            min={min}
            max={max}
            step={step}
            value={v}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (Number.isFinite(n)) onChange(Math.max(min, Math.min(max, n)));
            }}
            style={{ ...INPUT_STYLE, width: 56, padding: "2px 5px", fontSize: 11, textAlign: "right" }}
          />
          {suffix && <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{suffix}</span>}
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={v}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: "var(--accent)", margin: 0 }}
      />
    </div>
  );
}

/** Inline color swatch + popover with react-colorful.
 *
 * Native <input type="color"> opens the OS picker which closes on click —
 * "팔레트 안에서 연속 변화" 요구를 만족 못 한다. 이 컴포넌트는 swatch만 노출
 * 하고 클릭 시 같은 패널 안에 picker를 띄워, 드래그 중에도 onChange가 연속
 * 발화하고 외부 클릭으로만 닫힌다. */
function InlineColorPicker({
  value,
  onChange,
  size = 28,
}: {
  value: string | undefined;
  onChange: (s: string) => void;
  size?: number;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const swatchRef = useRef<HTMLDivElement | null>(null);
  const display = /^#[0-9a-fA-F]{6}$/.test(value || "") ? (value as string) : "#000000";

  function toggle() {
    if (!open && swatchRef.current) {
      const r = swatchRef.current.getBoundingClientRect();
      // viewport 기준 좌표. popover는 body로 portal되어 fixed 배치되므로
      // aside의 overflow에 잘리지 않는다. (이전엔 absolute라 aside 안에서
      // 잘려서 saturation 영역이 화면 밖으로 밀려났음.)
      const PICKER_W = 216, PICKER_H = 216, PAD = 16;
      let left = r.left;
      let top = r.bottom + 6;
      if (left + PICKER_W + PAD > window.innerWidth) {
        left = Math.max(8, window.innerWidth - PICKER_W - PAD);
      }
      if (top + PICKER_H + PAD > window.innerHeight) {
        top = Math.max(8, r.top - PICKER_H - 6);
      }
      setPos({ top, left });
    }
    setOpen((v) => !v);
  }

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      const t = e.target as Element | null;
      if (t && t.closest) {
        if (t.closest("[data-color-popover]")) return;
        if (t.closest("[data-color-swatch]")) return;
      }
      setOpen(false);
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  return (
    <>
      <div
        ref={swatchRef}
        data-color-swatch=""
        onClick={toggle}
        title="클릭해서 색 고르기"
        style={{
          width: size, height: size, borderRadius: 4,
          border: "1px solid var(--border)",
          background: display,
          cursor: "pointer",
          display: "inline-block",
        }}
      />
      {open && typeof document !== "undefined" && createPortal(
        <div
          data-color-popover=""
          style={{
            position: "fixed", top: pos.top, left: pos.left, zIndex: 1000,
            padding: 8, borderRadius: 8,
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
          }}
        >
          <HexColorPicker color={display} onChange={onChange} />
        </div>,
        document.body,
      )}
    </>
  );
}

function ColorRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | undefined;
  onChange: (s: string) => void;
}) {
  return (
    <div>
      <label style={LABEL_STYLE}>{label}</label>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <InlineColorPicker value={value} onChange={onChange} size={32} />
        <input
          type="text"
          value={value || ""}
          onChange={(e) => {
            const v = e.target.value;
            if (/^#?[0-9a-fA-F]{6}$/.test(v.trim())) {
              onChange(v.trim().startsWith("#") ? v.trim() : "#" + v.trim());
            } else if (v === "") {
              onChange("");
            } else {
              onChange(v);
            }
          }}
          style={{ ...INPUT_STYLE, flex: 1, fontFamily: "monospace" }}
          placeholder="#000000"
        />
      </div>
    </div>
  );
}

function TextRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | undefined;
  onChange: (s: string) => void;
}) {
  return (
    <div>
      <label style={LABEL_STYLE}>{label}</label>
      <input
        type="text"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        style={INPUT_STYLE}
      />
    </div>
  );
}

function XYGrid({
  basePath,
  vals,
  onChange,
}: {
  basePath: string;
  vals: { x?: number; y?: number };
  onChange: (path: string, v: unknown) => void;
}) {
  return (
    <div>
      <label style={LABEL_STYLE}>위치</label>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
        {[
          { sub: "X", key: "x", val: vals.x },
          { sub: "Y", key: "y", val: vals.y },
        ].map((c) => (
          <div key={c.key}>
            <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontWeight: 500 }}>{c.sub}</span>
            <input
              type="number"
              value={Math.round(c.val ?? 0)}
              onChange={(e) => onChange(`${basePath}.${c.key}`, Number(e.target.value) || 0)}
              style={INPUT_STYLE}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function WHGrid({
  basePath,
  vals,
  onChange,
}: {
  basePath: string;
  vals: { width?: number; height?: number };
  onChange: (path: string, v: unknown) => void;
}) {
  return (
    <div>
      <label style={LABEL_STYLE}>크기</label>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
        {[
          { sub: "W", key: "width", val: vals.width },
          { sub: "H", key: "height", val: vals.height },
        ].map((c) => (
          <div key={c.key}>
            <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontWeight: 500 }}>{c.sub}</span>
            <input
              type="number"
              value={Math.round(c.val ?? 0)}
              onChange={(e) => onChange(`${basePath}.${c.key}`, Number(e.target.value) || 0)}
              style={INPUT_STYLE}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Editor-style text style controls ───────────────────────────────────

type TabKey = "basic" | "effects" | "ai";

/** Section selector matches the editor's basic-tab ordering: color goes near
 *  the top (right after position/size/opacity) while typography sits below
 *  layer-ordering. */
type TextSection = "all" | "color" | "typography" | "effects";

function TextStyleEditor({
  path,
  style,
  onChange,
  section = "all",
}: {
  path: string;
  style: TextStyle | undefined;
  onChange: (path: string, value: unknown) => void;
  section?: TextSection;
}) {
  const s: TextStyle = style || {};
  const weight = String(s.font_weight || "normal");
  const bold = isBoldWeight(weight);

  if (section === "effects") {
    return (
      <>
        <OutlineEditor
          basePath={path}
          color={s.stroke}
          width={s.stroke_width}
          isText
          onChange={onChange}
        />
        <ShadowEditor basePath={path} shadow={s.shadow} onChange={onChange} />
      </>
    );
  }

  if (section === "color") {
    return (
      <ColorRow label="색상" value={s.fill} onChange={(v) => onChange(`${path}.fill`, v)} />
    );
  }

  // section === "typography" — everything except the leading color picker.
  // (section === "all" still renders the color first to keep external callers.)
  return (
    <>
      {section === "all" && (
        <ColorRow label="색상" value={s.fill} onChange={(v) => onChange(`${path}.fill`, v)} />
      )}

      {/* Font family */}
      <TextRow label="글꼴" value={s.font_family} onChange={(v) => onChange(`${path}.font_family`, v)} />

      {/* Font size — slider + number */}
      <SliderRow
        label="글꼴 크기"
        value={s.font_size}
        min={8}
        max={500}
        step={1}
        suffix="px"
        onChange={(v) => onChange(`${path}.font_size`, v)}
      />

      {/* Bold + weight dropdown */}
      <div>
        <label style={LABEL_STYLE}>굵기</label>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            type="button"
            onClick={() => onChange(`${path}.font_weight`, bold ? "400" : "700")}
            title="굵게 토글"
            style={{
              width: 36, padding: "5px 0",
              fontSize: 14, fontWeight: 800,
              fontFamily: "Georgia, serif",
              background: bold ? "var(--accent)" : "var(--bg-overlay)",
              color: bold ? "white" : "var(--text-secondary)",
              border: "1px solid",
              borderColor: bold ? "var(--accent)" : "var(--border)",
              borderRadius: 5,
              cursor: "pointer",
            }}
          >
            B
          </button>
          <select
            value={weight}
            onChange={(e) => onChange(`${path}.font_weight`, e.target.value)}
            style={{ ...INPUT_STYLE, flex: 1 }}
          >
            <option value="300">얇게 (300)</option>
            <option value="400">일반 (400)</option>
            <option value="500">중간 (500)</option>
            <option value="600">세미볼드 (600)</option>
            <option value="700">굵게 (700)</option>
            <option value="800">매우 굵게 (800)</option>
            <option value="900">최대 굵기 (900)</option>
          </select>
        </div>
      </div>

      {/* Text align — button group */}
      <div>
        <label style={LABEL_STYLE}>정렬</label>
        <div style={{ display: "flex", gap: 4 }}>
          {(["left", "center", "right"] as const).map((align) => {
            const active = s.text_align === align;
            return (
              <button
                key={align}
                type="button"
                onClick={() => onChange(`${path}.text_align`, align)}
                style={{
                  flex: 1, padding: "5px 0",
                  fontSize: 11, fontWeight: 500,
                  borderRadius: 4,
                  background: active ? "var(--accent)" : "var(--bg-overlay)",
                  color: active ? "white" : "var(--text-secondary)",
                  border: "1px solid",
                  borderColor: active ? "var(--accent)" : "var(--border)",
                  cursor: "pointer",
                }}
              >
                {align === "left" ? "왼쪽" : align === "center" ? "가운데" : "오른쪽"}
              </button>
            );
          })}
        </div>
      </div>

      {/* Line height — slider + number */}
      <SliderRow
        label="행간"
        value={s.line_height}
        min={0.8}
        max={3}
        step={0.1}
        onChange={(v) => onChange(`${path}.line_height`, v)}
      />

    </>
  );
}

// ─── Shadow / outline editors (parity with editor PropertyPanel) ────────

const DEFAULT_SHADOW: ShadowSpec = { color: "#000000", opacity: 70, angle: 135, distance: 24, blur: 24 };

function ShadowEditor({
  basePath,
  shadow,
  onChange,
}: {
  basePath: string;
  shadow: ShadowSpec | null | undefined;
  onChange: (path: string, value: unknown) => void;
}) {
  const enabled = !!shadow;
  // Keep last-edited values around while the toggle is off so the user doesn't
  // lose their work when flipping the switch — mirrors PropertyPanel's draft.
  // Sync the draft to the upstream shadow during render (not in an effect) so
  // selection/undo updates propagate without extra render cycles. Deep
  // equality guards against the infinite loop that bare identity would cause
  // here — setByPath JSON-clones the tree, so reference equality is useless.
  const [draft, setDraft] = useState<ShadowSpec>(shadow || DEFAULT_SHADOW);
  if (shadow && JSON.stringify(shadow) !== JSON.stringify(draft)) {
    setDraft(shadow);
  }
  const spec: ShadowSpec = shadow || draft;

  function toggle(on: boolean) {
    if (on) onChange(`${basePath}.shadow`, draft);
    else onChange(`${basePath}.shadow`, null);
  }
  function patch(next: Partial<ShadowSpec>) {
    const merged = { ...spec, ...next };
    setDraft(merged);
    // Only push to the canvas when the checkbox is on — otherwise we just
    // stage the values. Same behavior as the editor's ShadowSection.
    if (enabled) onChange(`${basePath}.shadow`, merged);
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <label style={{ ...LABEL_STYLE, marginBottom: 0 }}>그림자</label>
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
      <div style={{ display: "flex", flexDirection: "column", gap: 10, opacity: enabled ? 1 : 0.85 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>색상</span>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "monospace" }}>{spec.color}</span>
            <InlineColorPicker value={spec.color} onChange={(c) => patch({ color: c })} size={22} />
          </div>
        </div>
        <SliderRow label="방향" suffix="°" min={0} max={360} step={1} value={spec.angle}
          onChange={(n) => patch({ angle: n })} />
        <SliderRow label="불투명도" suffix="%" min={0} max={100} step={1} value={spec.opacity}
          onChange={(n) => patch({ opacity: n })} />
        <SliderRow label="거리" min={0} max={100} step={1} value={spec.distance}
          onChange={(n) => patch({ distance: n })} />
        <SliderRow label="흐림" min={0} max={100} step={1} value={spec.blur}
          onChange={(n) => patch({ blur: n })} />
      </div>
    </div>
  );
}

const OUTLINE_DEFAULT_COLOR = "#000000";
// 캐러셀 에디터(PropertyPanel.tsx)와 통일 — fabric native stroke만으로 image
// 외곽선이 충분히 보이는 게 확인되어 4px로 되돌림.
const OUTLINE_DEFAULT_WIDTH = 4;
const OUTLINE_MAX = 216;

function OutlineEditor({
  basePath,
  color,
  width,
  isText,
  onChange,
}: {
  basePath: string;
  color: string | null | undefined;
  width: number | undefined;
  isText: boolean;
  onChange: (path: string, value: unknown) => void;
}) {
  // "Configured" — intent — vs. "currently drawing" — width > 0. Keep the
  // section open even when width hits 0 so the user can dial it back up.
  const enabled = !!color;
  const c = color || OUTLINE_DEFAULT_COLOR;
  const w = Math.max(0, Math.min(OUTLINE_MAX, Math.round(width || 0)));

  function toggleOn() {
    onChange(`${basePath}.stroke`, c);
    onChange(`${basePath}.stroke_width`, w > 0 ? w : OUTLINE_DEFAULT_WIDTH);
  }
  function toggleOff() {
    onChange(`${basePath}.stroke`, null);
    onChange(`${basePath}.stroke_width`, 0);
  }
  function setColor(next: string) { onChange(`${basePath}.stroke`, next); }
  function setWidth(n: number) {
    const v = Math.max(0, Math.min(OUTLINE_MAX, Math.round(n)));
    onChange(`${basePath}.stroke_width`, v);
    if (v > 0 && !color) {
      onChange(`${basePath}.stroke`, c);
    }
  }

  // Suppress unused-prop warning — kept in the signature so callers can wire
  // isText hint for renderer parity (paint-first stroke for glyphs).
  void isText;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <label style={{ ...LABEL_STYLE, marginBottom: 0 }}>외곽선</label>
        <button
          type="button"
          onClick={() => (enabled ? toggleOff() : toggleOn())}
          aria-pressed={enabled}
          title={enabled ? "외곽선 끄기" : "외곽선 켜기"}
          style={{
            position: "relative", width: 32, height: 18,
            borderRadius: 9, border: "none",
            background: enabled ? "var(--accent)" : "var(--bg-overlay)",
            cursor: "pointer", padding: 0, transition: "background 0.15s",
          }}
        >
          <span
            style={{
              position: "absolute", top: 2, left: enabled ? 16 : 2,
              width: 14, height: 14, borderRadius: "50%",
              background: "white", transition: "left 0.15s",
              boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
            }}
          />
        </button>
      </div>
      {enabled && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>색상</span>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <InlineColorPicker value={c} onChange={setColor} size={22} />
              <input
                type="text"
                value={c}
                onChange={(e) => {
                  const v = e.target.value.trim();
                  if (/^#?[0-9a-fA-F]{6}$/.test(v)) setColor(v.startsWith("#") ? v : "#" + v);
                }}
                style={{ ...INPUT_STYLE, width: 86, padding: "2px 6px", fontSize: 11, fontFamily: "monospace" }}
              />
            </div>
          </div>
          <SliderRow label="두께" suffix="px" min={0} max={OUTLINE_MAX} step={1} value={w}
            onChange={(n) => setWidth(n)} />
        </div>
      )}
    </div>
  );
}

// ─── Top-level panel ────────────────────────────────────────────────────

export function LayoutPropertyPanel({ template, layoutName, selected, onChange, onMoveLayer, onDeleteSelected, onReplaceImage, onCutoutImage, imageBusy }: Props) {
  const layoutPath = `layouts.${layoutName}`;
  const layout = template.layouts?.[layoutName];

  const [activeTab, setActiveTab] = useState<TabKey>("basic");

  // 토글·슬라이더 조작 시 autoSave→setTemplate가 LayoutPropertyPanel을
  // unmount-remount할 수 있어 component-local ref만으로는 scroll이 유지
  // 안 된다. sessionStorage에 위치를 저장해 다음 mount에서 복원한다.
  const asideRef = useRef<HTMLElement | null>(null);
  const SCROLL_KEY = "layoutPanelScroll";
  useLayoutEffect(() => {
    if (!asideRef.current) return;
    const saved = Number(sessionStorage.getItem(SCROLL_KEY) || "0");
    if (saved > 0 && asideRef.current.scrollTop !== saved) {
      asideRef.current.scrollTop = saved;
    }
  });

  const tabs: { key: TabKey; label: string }[] = [
    { key: "basic", label: "기본" },
    { key: "effects", label: "효과" },
    { key: "ai", label: "AI" },
  ];

  return (
    <aside
      ref={asideRef as React.RefObject<HTMLElement>}
      onScroll={(e) => { sessionStorage.setItem(SCROLL_KEY, String((e.currentTarget as HTMLElement).scrollTop)); }}
      style={{
        width: 320,
        borderLeft: "1px solid var(--border)",
        background: "var(--bg-elevated)",
        overflowY: "auto",
      }}
    >
      {/* Tab navigation — mirrors canvas/PropertyPanel.tsx */}
      <div style={{ display: "flex", gap: 2, padding: "8px 12px 0", borderBottom: "1px solid var(--border)", position: "sticky", top: 0, background: "var(--bg-elevated)", zIndex: 5 }}>
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

      {activeTab === "basic" && (
        <>
          {/* Brand */}
          <div style={SECTION_STYLE}>
            <p style={SECTION_TITLE}>브랜드 · 전 레이아웃 공유</p>
            <ColorRow label="주요 색상" value={template.brand?.primary_color} onChange={(v) => onChange("brand.primary_color", v)} />
            <ColorRow label="배경 색상" value={template.brand?.background_color} onChange={(v) => onChange("brand.background_color", v)} />
            <TextRow label="글꼴" value={template.brand?.font_family} onChange={(v) => onChange("brand.font_family", v)} />
          </div>

          {/* Background — layout-wide. 오버레이도 같이 (에디터엔 없는 layout-wide 설정이라
              효과 탭으로 분리하면 오히려 객체 효과가 묻혀버린다.) */}
          {layout?.background && (
            <div style={SECTION_STYLE}>
              <p style={SECTION_TITLE}>배경</p>
              <div>
                <label style={LABEL_STYLE}>종류</label>
                <select
                  value={layout.background.type || "color"}
                  onChange={(e) => onChange(`${layoutPath}.background.type`, e.target.value)}
                  style={INPUT_STYLE}
                >
                  <option value="color">단색</option>
                  <option value="image_keyword">이미지 키워드</option>
                  <option value="image_path">이미지 경로</option>
                  <option value="gradient">그라데이션</option>
                  <option value="composite">조합</option>
                </select>
              </div>
              {/* The "값" field holds the solid color / image keyword / image
                  path — meaningless for a gradient background, so hide it then
                  and show the gradient color + direction controls instead. */}
              {layout.background.type !== "gradient" && (
                <TextRow
                  label="값"
                  value={layout.background.value || ""}
                  onChange={(v) => onChange(`${layoutPath}.background.value`, v)}
                />
              )}
              {layout.background.type === "gradient" && (
                <>
                  <ColorRow
                    label="그라데이션 시작색"
                    value={layout.background.color_a || "#FFFFFF"}
                    onChange={(v) => onChange(`${layoutPath}.background.color_a`, v)}
                  />
                  <ColorRow
                    label="그라데이션 끝색"
                    value={layout.background.color_b || "#000000"}
                    onChange={(v) => onChange(`${layoutPath}.background.color_b`, v)}
                  />
                  <AngleRow
                    label="방향"
                    value={layout.background.angle ?? DIR_TO_ANGLE_BG[(layout.background.direction as LegacyDir) || "vertical"]}
                    onChange={(v) => onChange(`${layoutPath}.background.angle`, v)}
                  />
                </>
              )}
              <OverlayEditor
                layoutPath={layoutPath}
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                bg={layout.background as any}
                onChange={onChange}
              />
            </div>
          )}

          {selected ? (
            <SelectionEditor template={template} selected={selected} onChange={onChange} activeTab={activeTab} onMoveLayer={onMoveLayer} onDeleteSelected={onDeleteSelected} onReplaceImage={onReplaceImage} onCutoutImage={onCutoutImage} imageBusy={imageBusy} />
          ) : layout?.grid ? (
            <GridStyleSection layoutPath={layoutPath} grid={layout.grid} onChange={onChange} />
          ) : (
            <div style={{ padding: "32px 14px", textAlign: "center", color: "var(--text-tertiary)", fontSize: 12, lineHeight: 1.6 }}>
              캔버스에서 요소를<br />선택하면 속성이 표시됩니다
            </div>
          )}
        </>
      )}

      {activeTab === "effects" && (
        selected ? (
          <SelectionEditor template={template} selected={selected} onChange={onChange} activeTab={activeTab} onMoveLayer={onMoveLayer} onDeleteSelected={onDeleteSelected} onReplaceImage={onReplaceImage} onCutoutImage={onCutoutImage} imageBusy={imageBusy} />
        ) : (
          <div style={{ padding: "32px 14px", textAlign: "center", color: "var(--text-tertiary)", fontSize: 12, lineHeight: 1.6 }}>
            요소를 선택하면<br />외곽선·그림자·그라데이션을<br />설정할 수 있습니다
          </div>
        )
      )}

      {activeTab === "ai" && (
        <div style={{ padding: "32px 14px", textAlign: "center", color: "var(--text-tertiary)", fontSize: 12, lineHeight: 1.6 }}>
          AI 기능 준비 중
        </div>
      )}
    </aside>
  );
}

function GradientFillEditor({
  basePath,
  fill,
  onChange,
}: {
  basePath: string;
  fill: Decoration["fill"];
  onChange: (path: string, value: unknown) => void;
}) {
  const isGradient = !!(fill && typeof fill === "object" && fill.type === "linear");
  const grad: GradientFill | null = isGradient ? (fill as GradientFill) : null;
  const stops = grad?.stops || [];
  // Read angle from the explicit field; fall back to the legacy direction enum
  // so older templates (vertical/horizontal/diagonal) keep rendering correctly.
  const angle = grad?.angle ?? ({ vertical: 180, horizontal: 90, diagonal: 135 }[grad?.direction ?? "vertical"]);

  function toggle() {
    if (isGradient) {
      // Collapse to the first stop's color as a sane solid default.
      onChange(`${basePath}.fill`, stops[0]?.color || "#000000");
    } else {
      const seed: GradientFill = {
        type: "linear",
        angle: 180,
        stops: [
          { offset: 0, color: typeof fill === "string" ? fill : "#000000" },
          { offset: 1, color: "rgba(0,0,0,0)" },
        ],
      };
      onChange(`${basePath}.fill`, seed);
    }
  }
  // GradientFill <-> GradientBarEditor's normalised {color,opacity,position}.
  const gradValue: GradValue = {
    angle,
    stops: stops.map((s) => {
      const { hex, opacity } = splitColor(s.color);
      return { color: hex, opacity, position: s.offset };
    }),
  };
  function applyGrad(v: GradValue) {
    onChange(`${basePath}.fill`, {
      type: "linear",
      angle: v.angle,
      stops: v.stops.map((s) => ({ offset: s.position, color: mergeColor(s.color, s.opacity) })),
    } as GradientFill);
  }

  return (
    <div>
      <button
        onClick={toggle}
        style={{
          width: "100%", padding: "5px 8px", fontSize: 11, fontWeight: 500,
          background: isGradient ? "var(--accent)" : "var(--bg-overlay)",
          color: isGradient ? "white" : "var(--text-secondary)",
          border: "1px solid",
          borderColor: isGradient ? "var(--accent)" : "var(--border)",
          borderRadius: 4, cursor: "pointer",
        }}
      >
        {isGradient ? "그라데이션 끄기 (단색으로)" : "그라데이션 채우기"}
      </button>
      {isGradient && grad && (
        <div style={{ marginTop: 6 }}>
          <GradientBarEditor value={gradValue} onChange={applyGrad} />
        </div>
      )}
    </div>
  );
}

const _REPLACE_ACCEPT = ["image/png", "image/jpeg", "image/webp"];

function ImageReplaceRow({ busy, onReplace }: { busy: boolean; onReplace: (file: File) => Promise<void> | void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  // Feedback slide 7: clicking 교체 used to open the OS file dialog straight
  // away. Instead open a small modal with a drag-and-drop zone (clicking the
  // zone still falls back to the OS picker).
  const [open, setOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  async function handleFile(file: File | undefined | null) {
    if (!file) return;
    if (file.type && !_REPLACE_ACCEPT.includes(file.type)) {
      alert("PNG · JPG · WebP 이미지만 올릴 수 있습니다.");
      return;
    }
    setOpen(false);
    setDragOver(false);
    await onReplace(file);
  }

  return (
    <div>
      <label style={LABEL_STYLE}>이미지 교체</label>
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={busy}
        title="선택한 이미지를 다른 파일로 교체"
        style={{
          width: "100%", padding: "7px 10px",
          fontSize: 12, fontWeight: 500,
          color: "rgb(180,200,255)",
          background: "rgba(94,106,210,0.18)",
          border: "1px solid rgba(94,106,210,0.45)",
          borderRadius: 5,
          cursor: busy ? "default" : "pointer",
          opacity: busy ? 0.6 : 1,
        }}
      >
        {busy ? "교체 중…" : "🖼️ 다른 이미지로 교체"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.currentTarget.value = "";
          handleFile(file);
        }}
      />
      {open && typeof document !== "undefined" && createPortal(
        <div
          onClick={() => setOpen(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            background: "rgba(0,0,0,0.6)",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: 380, maxWidth: "90vw",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: 18,
              boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", flex: 1 }}>
                이미지 교체
              </span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                style={{
                  width: 22, height: 22, padding: 0, lineHeight: "20px",
                  fontSize: 14, color: "var(--text-secondary)",
                  background: "transparent", border: "1px solid var(--border)",
                  borderRadius: 4, cursor: "pointer",
                }}
              >
                ×
              </button>
            </div>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); handleFile(e.dataTransfer.files?.[0]); }}
              onClick={() => inputRef.current?.click()}
              style={{
                border: `2px dashed ${dragOver ? "var(--accent)" : "var(--border)"}`,
                background: dragOver ? "var(--accent-muted, rgba(94,106,210,0.12))" : "transparent",
                borderRadius: 8,
                padding: "36px 16px",
                textAlign: "center",
                cursor: "pointer",
                transition: "border-color 0.12s, background 0.12s",
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>🖼️</div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                여기로 이미지를 드래그하거나
              </div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)", textDecoration: "underline", marginTop: 2 }}>
                클릭해서 파일 선택
              </div>
              <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 8 }}>
                PNG · JPG · WebP
              </div>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}

function ImageCutoutRow({ busy, onCutout }: { busy: boolean; onCutout: (mode: "standard" | "generative") => Promise<void> | void }) {
  return (
    <div>
      <label style={LABEL_STYLE}>누끼 제거</label>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <button
          type="button"
          onClick={() => onCutout("standard")}
          disabled={busy}
          title="배경만 제거 (~4초)"
          style={{
            width: "100%", padding: "7px 10px",
            fontSize: 12, fontWeight: 500,
            color: "rgb(160,230,190)",
            background: "rgba(100,200,150,0.15)",
            border: "1px solid rgba(100,200,150,0.35)",
            borderRadius: 5,
            cursor: busy ? "default" : "pointer",
            opacity: busy ? 0.6 : 1,
          }}
        >
          {busy ? "처리 중…" : "✂️ 일반 누끼"}
        </button>
        <button
          type="button"
          onClick={() => onCutout("generative")}
          disabled={busy}
          title="손·사람까지 제거하고 제품만 추출 (~4초)"
          style={{
            width: "100%", padding: "7px 10px",
            fontSize: 12, fontWeight: 500,
            color: "rgb(255,200,140)",
            background: "rgba(255,170,80,0.15)",
            border: "1px solid rgba(255,170,80,0.35)",
            borderRadius: 5,
            cursor: busy ? "default" : "pointer",
            opacity: busy ? 0.6 : 1,
          }}
        >
          {busy ? "처리 중…" : "🎯 생성 누끼 (손 제거)"}
        </button>
      </div>
    </div>
  );
}

function ImageColorFillRow({ spec, onChange }: { spec: { color: string; intensity: number } | null; onChange: (next: { color: string; intensity: number } | null) => void }) {
  const display: { color: string; intensity: number } = spec || { color: "#FF3B6A", intensity: 0 };
  function update(patch: Partial<{ color: string; intensity: number }>) {
    const next = { ...display, ...patch };
    // 색만 만져도 강도 0이면 캔버스에 변화가 안 보여 "기능 안 됨"으로 보인다.
    // 색상을 건드린 순간 강도가 0이라면 50%로 자동 활성화해 즉시 결과가 보이게.
    if ("color" in patch && (!next.intensity || next.intensity <= 0)) {
      next.intensity = 50;
    }
    if (!next.intensity || next.intensity <= 0) onChange(null);
    else onChange(next);
  }
  return (
    <div>
      <label style={LABEL_STYLE}>색상 채우기</label>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10, color: "var(--text-tertiary)", width: 40 }}>색상</span>
          <InlineColorPicker value={display.color} onChange={(c) => update({ color: c })} size={24} />
          <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontFamily: "monospace", flex: 1 }}>
            {display.color}
          </span>
        </div>
        <SliderRow
          label="강도"
          value={display.intensity}
          min={0} max={100} step={1} suffix="%"
          onChange={(v) => update({ intensity: v })}
        />
      </div>
    </div>
  );
}

function LayerOrderRow({ onMove }: { onMove: (d: "front" | "forward" | "backward" | "back") => void }) {
  const buttons = [
    { key: "front", label: "맨 앞", path: "M3.75 9.75L9 4.5l5.25 5.25M9 4.5v15" },
    { key: "forward", label: "앞으로", path: "M4.5 15.75L9 11.25l4.5 4.5M9 11.25V21" },
    { key: "backward", label: "뒤로", path: "M4.5 8.25L9 12.75l4.5-4.5M9 12.75V3" },
    { key: "back", label: "맨 뒤", path: "M3.75 14.25L9 19.5l5.25-5.25M9 19.5v-15" },
  ] as const;
  return (
    <div>
      <label style={LABEL_STYLE}>레이어 순서</label>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
        {buttons.map((b) => (
          <button
            key={b.key}
            type="button"
            onClick={() => onMove(b.key)}
            style={{
              display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 4,
              padding: "5px 6px", fontSize: 11,
              background: "var(--bg-overlay)", color: "var(--text-secondary)",
              border: "1px solid var(--border)", borderRadius: 5, cursor: "pointer",
            }}
          >
            <svg width="11" height="11" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d={b.path} />
            </svg>
            {b.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function DeleteRow({ onDelete }: { onDelete: () => void }) {
  return (
    <button
      type="button"
      onClick={onDelete}
      title="삭제 (Delete)"
      style={{
        width: "100%",
        padding: "8px 10px",
        fontSize: 12, fontWeight: 500,
        color: "var(--red)",
        background: "var(--red-muted, rgba(232,91,91,0.12))",
        border: "1px solid rgba(232,91,91,0.25)",
        borderRadius: 6,
        cursor: "pointer",
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 6,
      }}
    >
      <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79" />
      </svg>
      요소 삭제
    </button>
  );
}

function SelectionEditor({
  template,
  selected,
  onChange,
  activeTab,
  onMoveLayer,
  onDeleteSelected,
  onReplaceImage,
  onCutoutImage,
  imageBusy,
}: {
  template: TemplateData;
  selected: FabricMeta;
  onChange: (path: string, value: unknown) => void;
  activeTab: TabKey;
  onMoveLayer?: (direction: "front" | "forward" | "backward" | "back") => void;
  onDeleteSelected?: () => void;
  onReplaceImage?: (file: File) => Promise<void> | void;
  onCutoutImage?: (mode: "standard" | "generative") => Promise<void> | void;
  imageBusy?: { replace?: boolean; cutout?: boolean };
}) {
  const node = getByPath(template, selected.path);
  const isReorderable = /\.(decorations|text_slots)\[\d+\]$/.test(selected.path);

  if (selected.kind === "text_slot") {
    const t = node as { role?: string; position?: { x: number; y: number }; size?: { width: number; height: number }; style?: TextStyle; opacity?: number };
    return (
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>텍스트 슬롯{t?.role ? ` · ${t.role}` : ""}</p>
        {activeTab === "basic" && (
          <>
            {/* 1. 위치 */}
            <XYGrid basePath={`${selected.path}.position`} vals={{ x: t?.position?.x, y: t?.position?.y }} onChange={onChange} />
            {/* 2. 크기 */}
            <WHGrid basePath={`${selected.path}.size`} vals={{ width: t?.size?.width, height: t?.size?.height }} onChange={onChange} />
            {/* 3. 색상 */}
            <TextStyleEditor path={`${selected.path}.style`} style={t?.style} onChange={onChange} section="color" />
            {/* 4. 불투명도 */}
            <SliderRow
              label="불투명도"
              value={Math.round((t?.opacity ?? 1) * 100)}
              min={0} max={100} step={1} suffix="%"
              onChange={(v) => onChange(`${selected.path}.opacity`, v / 100)}
            />
            {/* 5. 레이어 순서 */}
            {isReorderable && onMoveLayer && <LayerOrderRow onMove={onMoveLayer} />}
            {/* 6. 텍스트 속성 (글꼴/크기/굵기/정렬/행간) */}
            <div style={{ height: 1, background: "var(--border)", margin: 0 }} />
            <TextStyleEditor path={`${selected.path}.style`} style={t?.style} onChange={onChange} section="typography" />
            {/* 7. 요소 삭제 */}
            {onDeleteSelected && <DeleteRow onDelete={onDeleteSelected} />}
          </>
        )}
        {activeTab === "effects" && (
          <TextStyleEditor path={`${selected.path}.style`} style={t?.style} onChange={onChange} section="effects" />
        )}
      </div>
    );
  }

  if (selected.kind === "decoration") {
    const d = (node || {}) as Decoration;
    const fillIsGradient = !!(d.fill && typeof d.fill === "object");
    const solidFill = !fillIsGradient ? (d.fill as string | null | undefined) : null;
    return (
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>장식{d?.kind ? ` · ${d.kind}` : ""}</p>
        {activeTab === "basic" && (
          <>
            {/* 1. 위치 */}
            <XYGrid basePath={`${selected.path}.position`} vals={{ x: d?.position?.x, y: d?.position?.y }} onChange={onChange} />
            {/* 2. 크기 */}
            <WHGrid basePath={`${selected.path}.size`} vals={{ width: d?.size?.width, height: d?.size?.height }} onChange={onChange} />
            {/* 3. 색상 */}
            {!fillIsGradient && (
              <ColorRow label="색상" value={solidFill || ""} onChange={(v) => onChange(`${selected.path}.fill`, v)} />
            )}
            {/* 4. 불투명도 */}
            <SliderRow
              label="불투명도"
              value={Math.round((d?.opacity ?? 1) * 100)}
              min={0} max={100} step={1} suffix="%"
              onChange={(v) => onChange(`${selected.path}.opacity`, v / 100)}
            />
            {/* 5. 레이어 순서 */}
            {isReorderable && onMoveLayer && <LayerOrderRow onMove={onMoveLayer} />}
            {/* 6. 요소 삭제 */}
            {onDeleteSelected && <DeleteRow onDelete={onDeleteSelected} />}
          </>
        )}
        {activeTab === "effects" && (
          <>
            {/* image decoration: 교체 / 누끼 / 컬러필 (에디터와 동일 순서) */}
            {d.kind === "image" && d.src && onReplaceImage && (
              <ImageReplaceRow busy={!!imageBusy?.replace} onReplace={onReplaceImage} />
            )}
            {d.kind === "image" && d.src && onCutoutImage && (
              <ImageCutoutRow busy={!!imageBusy?.cutout} onCutout={onCutoutImage} />
            )}
            {d.kind === "image" && d.src && (
              <ImageColorFillRow
                spec={d.color_fill || null}
                onChange={(spec) => onChange(`${selected.path}.color_fill`, spec)}
              />
            )}
            {d.kind === "shape" && (
              <GradientFillEditor basePath={selected.path} fill={d.fill} onChange={onChange} />
            )}
            <OutlineEditor
              basePath={selected.path}
              color={d.stroke}
              width={d.stroke_width}
              isText={false}
              onChange={onChange}
            />
            <ShadowEditor basePath={selected.path} shadow={d.shadow} onChange={onChange} />
          </>
        )}
      </div>
    );
  }

  if (selected.kind === "grid_origin") {
    if (activeTab !== "basic") return null;
    const p = node as { x?: number; y?: number };
    return (
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>그리드 원점</p>
        <XYGrid basePath={selected.path} vals={{ x: p?.x, y: p?.y }} onChange={onChange} />
      </div>
    );
  }

  if (selected.kind === "grid_image") {
    if (activeTab !== "basic") return null;
    const ia = node as { x?: number; y?: number; width?: number; height?: number; border_radius?: number };
    return (
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>그리드 이미지 영역</p>
        <XYGrid basePath={selected.path} vals={{ x: ia?.x, y: ia?.y }} onChange={onChange} />
        <WHGrid basePath={selected.path} vals={{ width: ia?.width, height: ia?.height }} onChange={onChange} />
        <SliderRow
          label="모서리 둥글기"
          value={ia?.border_radius}
          min={0}
          max={200}
          step={1}
          suffix="px"
          onChange={(v) => onChange(`${selected.path}.border_radius`, v)}
        />
      </div>
    );
  }

  return null;
}

function GridStyleSection({
  layoutPath,
  grid,
  onChange,
}: {
  layoutPath: string;
  grid: GridSpec;
  onChange: (path: string, value: unknown) => void;
}) {
  const path = `${layoutPath}.grid`;
  return (
    <>
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>그리드</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <NumberRow label="행 수" value={grid.rows} min={1} onChange={(v) => onChange(`${path}.rows`, v)} />
          <NumberRow label="열 수" value={grid.cols} min={1} onChange={(v) => onChange(`${path}.cols`, v)} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <NumberRow label="셀 가로" value={grid.cell_size?.width} suffix="px" onChange={(v) => onChange(`${path}.cell_size.width`, v)} />
          <NumberRow label="셀 세로" value={grid.cell_size?.height} suffix="px" onChange={(v) => onChange(`${path}.cell_size.height`, v)} />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <NumberRow label="가로 간격" value={grid.gap_x} suffix="px" onChange={(v) => onChange(`${path}.gap_x`, v)} />
          <NumberRow label="세로 간격" value={grid.gap_y} suffix="px" onChange={(v) => onChange(`${path}.gap_y`, v)} />
        </div>
      </div>

      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>아이템 · 제목</p>
        <NumberRow
          label="세로 위치"
          value={grid.item_box?.title_offset_y}
          suffix="px"
          onChange={(v) => onChange(`${path}.item_box.title_offset_y`, v)}
        />
        <TextStyleEditor
          path={`${path}.item_box.title_style`}
          style={grid.item_box?.title_style}
          onChange={onChange}
        />
      </div>

      {grid.item_box?.subtitle_style && (
        <div style={SECTION_STYLE}>
          <p style={SECTION_TITLE}>아이템 · 부제</p>
          <NumberRow
            label="세로 위치"
            value={grid.item_box.subtitle_offset_y || 0}
            suffix="px"
            onChange={(v) => onChange(`${path}.item_box.subtitle_offset_y`, v)}
          />
          <TextStyleEditor
            path={`${path}.item_box.subtitle_style`}
            style={grid.item_box.subtitle_style}
            onChange={onChange}
          />
        </div>
      )}

      {grid.item_box?.description_style && (
        <div style={SECTION_STYLE}>
          <p style={SECTION_TITLE}>아이템 · 설명</p>
          <NumberRow
            label="세로 위치"
            value={grid.item_box.description_offset_y || 0}
            suffix="px"
            onChange={(v) => onChange(`${path}.item_box.description_offset_y`, v)}
          />
          <TextStyleEditor
            path={`${path}.item_box.description_style`}
            style={grid.item_box.description_style}
            onChange={onChange}
          />
        </div>
      )}
    </>
  );
}

// ─── Background overlay editor (solid / gradient) ───

interface OverlayEditorProps {
  layoutPath: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  bg: any;
  onChange: (path: string, value: unknown) => void;
}

function OverlayEditor({ layoutPath, bg, onChange }: OverlayEditorProps) {
  const kind: "none" | "solid" | "gradient" =
    bg.overlay_kind === "gradient" ? "gradient"
    : (bg.overlay_color && (bg.overlay_opacity || 0) > 0) || bg.overlay_kind === "solid"
    ? "solid"
    : "none";

  function setKind(next: "none" | "solid" | "gradient") {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const nextBg: any = { ...bg };
    if (next === "none") {
      nextBg.overlay_kind = null;
      nextBg.overlay_color = null;
      nextBg.overlay_opacity = 0;
      nextBg.overlay_gradient_direction = null;
      nextBg.overlay_gradient_stops = null;
    } else if (next === "solid") {
      nextBg.overlay_kind = "solid";
      nextBg.overlay_color = bg.overlay_color || "#000000";
      nextBg.overlay_opacity = bg.overlay_opacity || 0.35;
      nextBg.overlay_gradient_direction = null;
      nextBg.overlay_gradient_stops = null;
    } else {
      nextBg.overlay_kind = "gradient";
      nextBg.overlay_color = null;
      nextBg.overlay_opacity = 0;
      nextBg.overlay_gradient_direction = bg.overlay_gradient_direction || "vertical";
      nextBg.overlay_gradient_stops = bg.overlay_gradient_stops?.length
        ? bg.overlay_gradient_stops
        : [
            { offset: 0.0, color: "#000000", alpha: 0.0 },
            { offset: 1.0, color: "#000000", alpha: 0.7 },
          ];
    }
    onChange(`${layoutPath}.background`, nextBg);
  }

  const stops = bg.overlay_gradient_stops || [];
  const [gradientOpen, setGradientOpen] = useState(false);

  return (
    <>
      <div>
        <label style={LABEL_STYLE}>오버레이</label>
        <div style={{ display: "flex", gap: 4 }}>
          {(["none", "solid", "gradient"] as const).map((k) => {
            const active = kind === k;
            return (
              <button
                key={k}
                onClick={() => setKind(k)}
                style={{
                  flex: 1, padding: "5px 0",
                  fontSize: 11, fontWeight: 500,
                  borderRadius: 4,
                  background: active ? "var(--accent)" : "var(--bg-overlay)",
                  color: active ? "white" : "var(--text-secondary)",
                  border: "1px solid",
                  borderColor: active ? "var(--accent)" : "var(--border)",
                  cursor: "pointer",
                }}
              >
                {k === "none" ? "없음" : k === "solid" ? "단색" : "그라데이션"}
              </button>
            );
          })}
        </div>
      </div>

      {kind === "solid" && (
        <>
          <ColorRow
            label="오버레이 색상"
            value={bg.overlay_color || ""}
            onChange={(v) => onChange(`${layoutPath}.background.overlay_color`, v)}
          />
          <SliderRow
            label="불투명도"
            value={Math.round((bg.overlay_opacity || 0) * 100)}
            min={0}
            max={100}
            step={1}
            suffix="%"
            onChange={(v) => onChange(`${layoutPath}.background.overlay_opacity`, v / 100)}
          />
        </>
      )}

      {kind === "gradient" && (
        <>
          <button
            type="button"
            onClick={() => setGradientOpen((v) => !v)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              width: "100%", padding: "6px 8px",
              fontSize: 11, fontWeight: 500,
              color: "var(--text-secondary)",
              background: "var(--bg-overlay)",
              border: "1px solid var(--border)",
              borderRadius: 4,
              cursor: "pointer",
            }}
            aria-expanded={gradientOpen}
          >
            <span>그라데이션 설정 · {stops.length}개 스톱</span>
            <span style={{ fontSize: 9, color: "var(--text-tertiary)", transform: gradientOpen ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}>▶</span>
          </button>
          {gradientOpen && (
            <>
              <AngleRow
                label="방향"
                value={bg.overlay_gradient_angle ?? DIR_TO_ANGLE_BG[(bg.overlay_gradient_direction as LegacyDir) || "vertical"]}
                onChange={(v) => onChange(`${layoutPath}.background.overlay_gradient_angle`, v)}
              />
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {stops.map((stop: any, i: number) => (
                <StopEditor
                  key={i}
                  stop={stop}
                  index={i}
                  onCommit={(patch) => {
                    const next = [...stops];
                    next[i] = { ...stop, ...patch };
                    onChange(`${layoutPath}.background.overlay_gradient_stops`, next);
                  }}
                />
              ))}
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={() => {
                    const next = [...stops, { offset: 0.5, color: "#000000", alpha: 0.35 }];
                    onChange(`${layoutPath}.background.overlay_gradient_stops`, next.sort((a, b) => a.offset - b.offset));
                  }}
                  style={{ flex: 1, padding: "5px 0", fontSize: 11, fontWeight: 500, borderRadius: 4, background: "var(--bg-overlay)", color: "var(--text-secondary)", border: "1px solid var(--border)", cursor: "pointer" }}
                >
                  + 스톱
                </button>
                {stops.length > 2 && (
                  <button
                    onClick={() => onChange(`${layoutPath}.background.overlay_gradient_stops`, stops.slice(0, -1))}
                    style={{ flex: 1, padding: "5px 0", fontSize: 11, fontWeight: 500, borderRadius: 4, background: "var(--bg-overlay)", color: "var(--red)", border: "1px solid var(--border)", cursor: "pointer" }}
                  >
                    − 스톱
                  </button>
                )}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}

function StopEditor({
  stop,
  index,
  onCommit,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  stop: any;
  index: number;
  onCommit: (patch: { offset?: number; color?: string; alpha?: number }) => void;
}) {
  const [offsetText, setOffsetText] = useState<string>(String(stop.offset ?? 0));
  const [colorText, setColorText] = useState<string>(stop.color || "#000000");

  useEffect(() => {
    setOffsetText(String(stop.offset ?? 0));
    setColorText(stop.color || "#000000");
  }, [stop.offset, stop.color]);

  function commitOffset() {
    const v = Number(offsetText);
    if (Number.isFinite(v) && v >= 0 && v <= 1) onCommit({ offset: v });
    else setOffsetText(String(stop.offset ?? 0));
  }
  function commitColor() {
    const v = colorText.trim();
    if (/^#?[0-9a-fA-F]{6}$/.test(v)) {
      onCommit({ color: v.startsWith("#") ? v : "#" + v });
    } else {
      setColorText(stop.color || "#000000");
    }
  }

  return (
    <div style={{ padding: 8, background: "var(--bg-overlay)", borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)" }}>스톱 #{index + 1}</span>
        <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>위치 / 투명도</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8 }}>
        <SliderRow
          label="위치"
          value={Number(offsetText) || 0}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => {
            setOffsetText(String(v));
            onCommit({ offset: v });
          }}
        />
        <SliderRow
          label="불투명도"
          value={Math.round((stop.alpha || 0) * 100)}
          min={0}
          max={100}
          step={1}
          suffix="%"
          onChange={(v) => onCommit({ alpha: v / 100 })}
        />
      </div>
      <div>
        <label style={LABEL_STYLE}>색상</label>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <InlineColorPicker
            value={(colorText || "#000000").slice(0, 7)}
            onChange={(c) => { setColorText(c); onCommit({ color: c }); }}
            size={32}
          />
          <input
            type="text"
            value={colorText}
            onChange={(e) => setColorText(e.target.value)}
            onBlur={commitColor}
            onKeyDown={(e) => { if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur(); }}
            style={{ ...INPUT_STYLE, flex: 1, fontFamily: "monospace" }}
            placeholder="#000000"
          />
          <input
            type="number"
            step={0.05}
            min={0}
            max={1}
            value={offsetText}
            onChange={(e) => setOffsetText(e.target.value)}
            onBlur={commitOffset}
            onKeyDown={(e) => { if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur(); }}
            style={{ ...INPUT_STYLE, width: 64, padding: "5px 6px", textAlign: "right" }}
            placeholder="0~1"
            title="위치 (offset) 0~1"
          />
        </div>
      </div>
    </div>
  );
}
