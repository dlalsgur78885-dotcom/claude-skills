"use client";

import { useEffect, useState } from "react";
import { getByPath } from "@/lib/template-paths";
import type { TemplateData, FabricMeta, TextStyle, GridSpec, ShadowSpec, GradientFill, Decoration } from "./types";

interface Props {
  template: TemplateData;
  layoutName: string;
  selected: FabricMeta | null;
  onChange: (path: string, value: unknown) => void;
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

function ColorRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | undefined;
  onChange: (s: string) => void;
}) {
  const display = value || "#000000";
  return (
    <div>
      <label style={LABEL_STYLE}>{label}</label>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input
          type="color"
          value={/^#[0-9a-fA-F]{6}$/.test(display) ? display : "#000000"}
          onChange={(e) => onChange(e.target.value)}
          style={{ width: 32, height: 32, borderRadius: 5, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", padding: 2 }}
        />
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
              // accept partial typing; commit only when hex completes
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

function TextStyleEditor({
  path,
  style,
  onChange,
}: {
  path: string;
  style: TextStyle | undefined;
  onChange: (path: string, value: unknown) => void;
}) {
  const s: TextStyle = style || {};
  const weight = String(s.font_weight || "normal");
  const bold = isBoldWeight(weight);

  return (
    <>
      {/* Color */}
      <ColorRow label="색상" value={s.fill} onChange={(v) => onChange(`${path}.fill`, v)} />

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

      {/* Outline (stroke) */}
      <OutlineEditor
        basePath={path}
        color={s.stroke}
        width={s.stroke_width}
        isText
        onChange={onChange}
      />

      {/* Drop shadow */}
      <ShadowEditor
        basePath={path}
        shadow={s.shadow}
        onChange={onChange}
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
            <input
              type="color"
              value={/^#[0-9a-fA-F]{6}$/.test(spec.color) ? spec.color : "#000000"}
              onChange={(e) => patch({ color: e.target.value })}
              style={{ width: 22, height: 22, padding: 0, border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer", background: "transparent" }}
            />
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
              <input
                type="color"
                value={c}
                onChange={(e) => setColor(e.target.value)}
                style={{ width: 28, height: 22, borderRadius: 4, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", padding: 1 }}
              />
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

export function LayoutPropertyPanel({ template, layoutName, selected, onChange }: Props) {
  const layoutPath = `layouts.${layoutName}`;
  const layout = template.layouts?.[layoutName];

  return (
    <aside
      style={{
        width: 320,
        borderLeft: "1px solid var(--border)",
        background: "var(--bg-elevated)",
        overflowY: "auto",
      }}
    >
      {/* Brand */}
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>브랜드 · 전 레이아웃 공유</p>
        <ColorRow label="주요 색상" value={template.brand?.primary_color} onChange={(v) => onChange("brand.primary_color", v)} />
        <ColorRow label="배경 색상" value={template.brand?.background_color} onChange={(v) => onChange("brand.background_color", v)} />
        <TextRow label="글꼴" value={template.brand?.font_family} onChange={(v) => onChange("brand.font_family", v)} />
      </div>

      {/* Background */}
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
          <TextRow
            label="값"
            value={layout.background.value || ""}
            onChange={(v) => onChange(`${layoutPath}.background.value`, v)}
          />
          <OverlayEditor
            layoutPath={layoutPath}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            bg={layout.background as any}
            onChange={onChange}
          />
        </div>
      )}

      {/* Selection details */}
      {selected ? (
        <SelectionEditor template={template} selected={selected} onChange={onChange} />
      ) : layout?.grid ? (
        <GridStyleSection layoutPath={layoutPath} grid={layout.grid} onChange={onChange} />
      ) : (
        <div style={{ padding: "32px 14px", textAlign: "center", color: "var(--text-tertiary)", fontSize: 12, lineHeight: 1.6 }}>
          캔버스에서 요소를<br />선택하면 속성이 표시됩니다
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
  const dir = grad?.direction || "vertical";

  function toggle() {
    if (isGradient) {
      // Collapse to the first stop's color as a sane solid default.
      onChange(`${basePath}.fill`, stops[0]?.color || "#000000");
    } else {
      const seed: GradientFill = {
        type: "linear",
        direction: "vertical",
        stops: [
          { offset: 0, color: typeof fill === "string" ? fill : "#000000" },
          { offset: 1, color: "rgba(0,0,0,0)" },
        ],
      };
      onChange(`${basePath}.fill`, seed);
    }
  }
  function setDir(d: GradientFill["direction"]) {
    if (!grad) return;
    onChange(`${basePath}.fill`, { ...grad, direction: d });
  }
  function updateStop(i: number, patch: Partial<{ offset: number; color: string }>) {
    if (!grad) return;
    const next = grad.stops.map((s, idx) => (idx === i ? { ...s, ...patch } : s));
    onChange(`${basePath}.fill`, { ...grad, stops: next });
  }
  function addStop() {
    if (!grad) return;
    const next = [...grad.stops, { offset: 0.5, color: "rgba(0,0,0,0.5)" }].sort((a, b) => a.offset - b.offset);
    onChange(`${basePath}.fill`, { ...grad, stops: next });
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
        <div style={{ marginTop: 6, padding: 8, background: "var(--bg-overlay)", borderRadius: 4, display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", gap: 4 }}>
            {(["vertical", "horizontal", "diagonal"] as const).map((d) => {
              const active = dir === d;
              return (
                <button
                  key={d}
                  onClick={() => setDir(d)}
                  style={{
                    flex: 1, padding: "3px 0", fontSize: 10, borderRadius: 3,
                    background: active ? "var(--accent)" : "transparent",
                    color: active ? "white" : "var(--text-secondary)",
                    border: "1px solid",
                    borderColor: active ? "var(--accent)" : "var(--border)",
                    cursor: "pointer",
                  }}
                >
                  {d === "vertical" ? "↓" : d === "horizontal" ? "→" : "↘"}
                </button>
              );
            })}
          </div>
          {stops.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <input
                type="color"
                value={(s.color.match(/^#[0-9a-fA-F]{6}/) || ["#000000"])[0]}
                onChange={(e) => updateStop(i, { color: e.target.value })}
                style={{ width: 28, height: 22, padding: 0, border: "1px solid var(--border)", borderRadius: 3, cursor: "pointer" }}
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
            onClick={addStop}
            style={{ width: "100%", padding: "3px 0", fontSize: 10, background: "transparent", color: "var(--text-secondary)", border: "1px dashed var(--border)", borderRadius: 3, cursor: "pointer" }}
          >
            + 스톱 추가
          </button>
        </div>
      )}
    </div>
  );
}

function SelectionEditor({
  template,
  selected,
  onChange,
}: {
  template: TemplateData;
  selected: FabricMeta;
  onChange: (path: string, value: unknown) => void;
}) {
  const node = getByPath(template, selected.path);

  if (selected.kind === "text_slot") {
    const t = node as { role?: string; position?: { x: number; y: number }; size?: { width: number; height: number }; style?: TextStyle };
    return (
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>텍스트 슬롯{t?.role ? ` · ${t.role}` : ""}</p>
        <XYGrid basePath={`${selected.path}.position`} vals={{ x: t?.position?.x, y: t?.position?.y }} onChange={onChange} />
        <WHGrid basePath={`${selected.path}.size`} vals={{ width: t?.size?.width, height: t?.size?.height }} onChange={onChange} />
        <div style={{ height: 1, background: "var(--border)", margin: 0 }} />
        <TextStyleEditor path={`${selected.path}.style`} style={t?.style} onChange={onChange} />
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
        <XYGrid basePath={`${selected.path}.position`} vals={{ x: d?.position?.x, y: d?.position?.y }} onChange={onChange} />
        <WHGrid basePath={`${selected.path}.size`} vals={{ width: d?.size?.width, height: d?.size?.height }} onChange={onChange} />
        {/* Solid color (hidden while gradient mode is on — picker replaced by the gradient stops below). */}
        {!fillIsGradient && (
          <ColorRow label="색상" value={solidFill || ""} onChange={(v) => onChange(`${selected.path}.fill`, v)} />
        )}
        {/* Gradient toggle — only meaningful for shape decorations. Logos/images
            paint their bitmap so a gradient fill wouldn't render. */}
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
        <ShadowEditor
          basePath={selected.path}
          shadow={d.shadow}
          onChange={onChange}
        />
      </div>
    );
  }

  if (selected.kind === "grid_origin") {
    const p = node as { x?: number; y?: number };
    return (
      <div style={SECTION_STYLE}>
        <p style={SECTION_TITLE}>그리드 원점</p>
        <XYGrid basePath={selected.path} vals={{ x: p?.x, y: p?.y }} onChange={onChange} />
      </div>
    );
  }

  if (selected.kind === "grid_image") {
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
          <div>
            <label style={LABEL_STYLE}>방향</label>
            <div style={{ display: "flex", gap: 4 }}>
              {(["vertical", "horizontal", "diagonal"] as const).map((d) => {
                const active = bg.overlay_gradient_direction === d;
                return (
                  <button
                    key={d}
                    onClick={() => onChange(`${layoutPath}.background.overlay_gradient_direction`, d)}
                    style={{
                      flex: 1, padding: "5px 0",
                      fontSize: 14,
                      borderRadius: 4,
                      background: active ? "var(--accent)" : "var(--bg-overlay)",
                      color: active ? "white" : "var(--text-secondary)",
                      border: "1px solid",
                      borderColor: active ? "var(--accent)" : "var(--border)",
                      cursor: "pointer",
                    }}
                  >
                    {d === "vertical" ? "↓" : d === "horizontal" ? "→" : "↘"}
                  </button>
                );
              })}
            </div>
          </div>
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
          <input
            type="color"
            value={(colorText || "#000000").slice(0, 7)}
            onChange={(e) => { setColorText(e.target.value); onCommit({ color: e.target.value }); }}
            style={{ width: 32, height: 32, borderRadius: 5, border: "1px solid var(--border)", background: "transparent", cursor: "pointer", padding: 2, flexShrink: 0 }}
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
