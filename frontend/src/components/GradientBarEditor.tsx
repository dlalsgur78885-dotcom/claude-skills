"use client";

import { useRef, useState } from "react";
import { HexColorPicker, HexColorInput } from "react-colorful";

// Shared visual gradient editor — a horizontal preview bar with draggable
// color-stop handles. Replaces the old list/number-input gradient UIs in both
// the canvas editor (PropertyPanel) and the template studio (LayoutPropertyPanel).
// Carousel studio feedback #1 (slides 1-2 / 8-9).
//
// The component works on a normalised model (GradValue) — each side keeps its
// own storage format (fabric gradient / GradientFill) and converts with a tiny
// adapter plus the splitColor / mergeColor helpers exported here.

// color is always a `#rrggbb` hex; opacity (0-1) is split out so the UI can
// show it as a separate control. position is 0-1.
export type GradStop = { color: string; opacity: number; position: number };
// CSS-style angle: 0°=up, 90°=right, 180°=down, 270°=left.
export type GradValue = { angle: number; stops: GradStop[] };

/** Map a CSS-style gradient angle to fabric (x1,y1)→(x2,y2) coords across a
 *  w×h bounding box. Line passes through center; length is the projection of
 *  the half-bbox onto the direction vector (covers the box fully). */
export function angleToCoords(angle: number, w: number, h: number) {
  const rad = (angle * Math.PI) / 180;
  const dx = Math.sin(rad);
  const dy = -Math.cos(rad);
  const cx = w / 2, cy = h / 2;
  const half = (Math.abs(dx) * w + Math.abs(dy) * h) / 2;
  return {
    x1: cx - dx * half,
    y1: cy - dy * half,
    x2: cx + dx * half,
    y2: cy + dy * half,
  };
}

/** Inverse of angleToCoords — recover the CSS-style angle from fabric coords. */
export function coordsToAngle(c: { x1?: number; y1?: number; x2?: number; y2?: number }): number {
  const dx = (c.x2 || 0) - (c.x1 || 0);
  const dy = (c.y2 || 0) - (c.y1 || 0);
  if (dx === 0 && dy === 0) return 180;
  const a = (Math.atan2(dx, -dy) * 180) / Math.PI;
  return (Math.round(a) + 360) % 360;
}

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, isNaN(n) ? 0 : n));
}

/** Split a CSS color string (`#rrggbb`, `#rrggbbaa`, `#rgb`, `rgb()`, `rgba()`,
 *  `transparent`) into a `#rrggbb` hex + a 0-1 opacity. Stop colors are stored
 *  as one string; the editor edits hex and opacity separately. */
export function splitColor(s: string): { hex: string; opacity: number } {
  const str = (s || "").trim().toLowerCase();
  if (!str) return { hex: "#000000", opacity: 1 };
  if (str === "transparent") return { hex: "#000000", opacity: 0 };
  const rgba = str.match(/^rgba?\(([^)]+)\)$/);
  if (rgba) {
    const p = rgba[1].split(",").map((x) => parseFloat(x.trim()));
    const hex =
      "#" +
      [p[0], p[1], p[2]].map((n) => Math.round(n || 0).toString(16).padStart(2, "0")).join("");
    return { hex, opacity: p[3] == null || isNaN(p[3]) ? 1 : clamp01(p[3]) };
  }
  if (/^#[0-9a-f]{8}$/.test(str)) {
    return { hex: str.slice(0, 7), opacity: clamp01(parseInt(str.slice(7), 16) / 255) };
  }
  if (/^#[0-9a-f]{6}$/.test(str)) return { hex: str, opacity: 1 };
  if (/^#[0-9a-f]{3}$/.test(str)) {
    return { hex: "#" + str.slice(1).split("").map((c) => c + c).join(""), opacity: 1 };
  }
  return { hex: "#000000", opacity: 1 };
}

/** Inverse of splitColor — opaque stops stay `#rrggbb`, translucent become `rgba()`. */
export function mergeColor(hex: string, opacity: number): string {
  const o = clamp01(opacity);
  const h = (hex || "#000000").replace("#", "");
  if (o >= 1) return "#" + h;
  const r = parseInt(h.slice(0, 2), 16) || 0;
  const g = parseInt(h.slice(2, 4), 16) || 0;
  const b = parseInt(h.slice(4, 6), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${Number(o.toFixed(3))})`;
}

function lerpHex(a: string, b: string, t: number): string {
  const ca = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16) || 0);
  const cb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16) || 0);
  return "#" + ca.map((v, i) => Math.round(v + (cb[i] - v) * t).toString(16).padStart(2, "0")).join("");
}

const CHECKER: React.CSSProperties = {
  backgroundColor: "#fff",
  backgroundImage:
    "linear-gradient(45deg,#ccc 25%,transparent 25%),linear-gradient(-45deg,#ccc 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#ccc 75%),linear-gradient(-45deg,transparent 75%,#ccc 75%)",
  backgroundSize: "10px 10px",
  backgroundPosition: "0 0,0 5px,5px -5px,-5px 0",
};

const ROW: React.CSSProperties = { display: "flex", alignItems: "center", gap: 6 };
const LBL: React.CSSProperties = { fontSize: 11, color: "var(--text-tertiary)", width: 40, flexShrink: 0 };
const FIELD: React.CSSProperties = {
  padding: "3px 6px", fontSize: 11, background: "var(--bg-base)",
  border: "1px solid var(--border)", borderRadius: 3, color: "var(--text-primary)",
};

export function GradientBarEditor({
  value,
  onChange,
}: {
  value: GradValue;
  onChange: (v: GradValue) => void;
}) {
  const stops = value.stops;
  const [selected, setSelected] = useState(0);
  const [pickerOpen, setPickerOpen] = useState(false);
  const barRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<number | null>(null);
  // Latest stops for the window-level drag listeners (closures would go stale).
  const stopsRef = useRef(stops);
  stopsRef.current = stops;

  const selIdx = Math.min(selected, stops.length - 1);
  const sel: GradStop | undefined = stops[selIdx];

  // Sort by position and emit. `keep` is the stop that should stay selected —
  // returns its index in the sorted result so drags survive a reorder.
  function emit(next: GradStop[], keep?: GradStop, angle: number = value.angle): number {
    const sorted = [...next].sort((a, b) => a.position - b.position);
    onChange({ angle, stops: sorted });
    return keep ? sorted.indexOf(keep) : 0;
  }

  function setAngle(a: number) {
    const norm = ((Math.round(a) % 360) + 360) % 360;
    onChange({ angle: norm, stops });
  }

  // Drag the rotary indicator — translate pointer position into a CSS angle.
  function startAngleDrag(e: React.PointerEvent<HTMLDivElement>) {
    e.stopPropagation();
    const el = e.currentTarget;
    function compute(ev: PointerEvent | React.PointerEvent) {
      const r = el.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dx = ev.clientX - cx;
      const dy = ev.clientY - cy;
      const a = (Math.atan2(dx, -dy) * 180) / Math.PI;
      setAngle(a);
    }
    compute(e);
    function move(ev: PointerEvent) { compute(ev); }
    function up() {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  function posFromX(clientX: number): number {
    const r = barRef.current?.getBoundingClientRect();
    if (!r || r.width === 0) return 0;
    return clamp01((clientX - r.left) / r.width);
  }

  function startDrag(i: number, e: React.PointerEvent) {
    e.stopPropagation();
    setSelected(i);
    dragRef.current = i;
    function move(ev: PointerEvent) {
      const idx = dragRef.current;
      if (idx == null) return;
      const cur = stopsRef.current;
      if (!cur[idx]) return;
      const moved = { ...cur[idx], position: posFromX(ev.clientX) };
      const newIdx = emit(cur.map((s, k) => (k === idx ? moved : s)), moved);
      dragRef.current = newIdx;
      setSelected(newIdx);
    }
    function up() {
      dragRef.current = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    }
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }

  // Click an empty spot on the bar → add a stop there, color interpolated from
  // its two neighbours so it visually "lands on" the existing gradient.
  function addAt(e: React.PointerEvent) {
    if (e.target !== barRef.current) return; // a handle was clicked, not the bar
    const pos = posFromX(e.clientX);
    const sorted = [...stops].sort((a, b) => a.position - b.position);
    let lo = sorted[0];
    let hi = sorted[sorted.length - 1];
    for (let k = 0; k < sorted.length - 1; k++) {
      if (pos >= sorted[k].position && pos <= sorted[k + 1].position) {
        lo = sorted[k];
        hi = sorted[k + 1];
        break;
      }
    }
    const span = hi.position - lo.position;
    const t = span > 0 ? (pos - lo.position) / span : 0;
    const added: GradStop = {
      color: lerpHex(lo.color, hi.color, t),
      opacity: clamp01(lo.opacity + (hi.opacity - lo.opacity) * t),
      position: pos,
    };
    setSelected(emit([...stops, added], added));
  }

  function patchSel(patch: Partial<GradStop>) {
    if (!sel) return;
    const moved = { ...sel, ...patch };
    setSelected(emit(stops.map((s, k) => (k === selIdx ? moved : s)), moved));
  }

  function removeSel() {
    if (stops.length <= 2 || !sel) return; // keep at least 2 stops
    onChange({ angle: value.angle, stops: stops.filter((_, k) => k !== selIdx) });
    setSelected(Math.max(0, selIdx - 1));
  }

  const cssBar = [...stops]
    .sort((a, b) => a.position - b.position)
    .map((s) => `${mergeColor(s.color, s.opacity)} ${(s.position * 100).toFixed(1)}%`)
    .join(", ");

  const angle = value.angle;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {/* 방향 — 회전 인디케이터 + 슬라이더 + 숫자 (0~360°). 인디케이터는
          드래그로 직접 회전, 슬라이더는 거친 조절, 숫자는 정밀 입력. */}
      <div style={ROW}>
        <span style={LBL}>방향</span>
        <div
          onPointerDown={startAngleDrag}
          title="드래그로 각도 조절"
          style={{
            width: 28, height: 28, borderRadius: "50%",
            border: "1px solid var(--border)",
            background: "var(--bg-base)",
            position: "relative", flexShrink: 0,
            cursor: "grab", touchAction: "none",
          }}
        >
          <div
            style={{
              position: "absolute", left: "50%", top: "50%",
              width: 2, height: 12,
              background: "var(--accent)",
              transformOrigin: "50% 100%",
              transform: `translate(-50%, -100%) rotate(${angle}deg)`,
              borderRadius: 1,
            }}
          />
          <div
            style={{
              position: "absolute", left: "50%", top: "50%",
              width: 4, height: 4, borderRadius: "50%",
              background: "var(--accent)",
              transform: "translate(-50%, -50%)",
            }}
          />
        </div>
        <input
          type="range" min={0} max={360} step={1}
          value={angle}
          onChange={(e) => setAngle(Number(e.target.value))}
          style={{ flex: 1, minWidth: 0 }}
        />
        <input
          type="number" min={0} max={360} step={1}
          value={angle}
          onChange={(e) => setAngle(Number(e.target.value))}
          style={{ ...FIELD, width: 48, textAlign: "right" }}
        />
        <span style={{ ...LBL, width: "auto", color: "var(--text-secondary)" }}>°</span>
      </div>

      {/* 프리뷰 바 + 핸들 */}
      <div style={{ ...CHECKER, borderRadius: 6, padding: "9px 2px" }}>
        <div
          ref={barRef}
          onPointerDown={addAt}
          style={{
            position: "relative", height: 22, borderRadius: 5,
            // Preview bar reflects the live angle so the user can see what the
            // shape will actually look like — req #7/#9 in 피드백 #10 slide 1.
            background: `linear-gradient(${angle}deg, ${cssBar})`,
            cursor: "copy", touchAction: "none",
          }}
        >
          {stops.map((s, i) => {
            const isSel = i === selIdx;
            const canDelete = stops.length > 2;
            return (
              <div
                key={i}
                onPointerDown={(e) => startDrag(i, e)}
                title={`${Math.round(s.position * 100)}%`}
                style={{
                  position: "absolute", left: `${s.position * 100}%`, top: "50%",
                  width: 16, height: 16, borderRadius: "50%",
                  background: mergeColor(s.color, s.opacity),
                  border: `2px solid ${isSel ? "var(--accent)" : "#fff"}`,
                  boxShadow: "0 0 0 1px rgba(0,0,0,0.4)",
                  transform: `translate(-50%,-50%) scale(${isSel ? 1.18 : 1})`,
                  zIndex: isSel ? 2 : 1,
                  cursor: "grab", touchAction: "none",
                }}
              >
                {isSel && canDelete && (
                  <button
                    type="button"
                    aria-label="스톱 삭제"
                    title="스톱 삭제"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      removeSel();
                    }}
                    style={{
                      position: "absolute",
                      left: "50%",
                      bottom: "calc(100% + 4px)",
                      transform: "translateX(-50%) scale(0.847)",
                      width: 16, height: 16, padding: 0,
                      borderRadius: "50%",
                      background: "#1a1a1a",
                      color: "#fff",
                      border: "1px solid #fff",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.5)",
                      fontSize: 11, lineHeight: 1,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      cursor: "pointer",
                    }}
                  >
                    ×
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 선택된 스톱 편집 */}
      {sel && (
        <div style={{ padding: 8, background: "var(--bg-overlay)", borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={ROW}>
            <button
              type="button"
              onClick={() => setPickerOpen((o) => !o)}
              title="색상 선택"
              style={{
                width: 26, height: 26, borderRadius: 4, flexShrink: 0,
                background: sel.color, border: "1px solid var(--border)", cursor: "pointer",
              }}
            />
            <HexColorInput
              color={sel.color}
              onChange={(hex) => patchSel({ color: hex })}
              prefixed
              style={{ ...FIELD, flex: 1, minWidth: 0, textTransform: "uppercase" }}
            />
            <button
              type="button"
              onClick={removeSel}
              disabled={stops.length <= 2}
              title={stops.length <= 2 ? "스톱은 최소 2개 유지" : "선택한 스톱 삭제"}
              style={{
                width: 26, height: 26, borderRadius: 4, flexShrink: 0, fontSize: 12,
                background: "transparent", color: "var(--text-secondary)",
                border: "1px solid var(--border)",
                cursor: stops.length <= 2 ? "default" : "pointer",
                opacity: stops.length <= 2 ? 0.4 : 1,
              }}
            >
              🗑
            </button>
          </div>

          {pickerOpen && (
            <div className="gradient-bar-picker" style={{ display: "flex", justifyContent: "center" }}>
              <HexColorPicker color={sel.color} onChange={(hex) => patchSel({ color: hex })} />
            </div>
          )}

          {/* 투명도 */}
          <div style={ROW}>
            <span style={LBL}>투명도</span>
            <input
              type="range" min={0} max={100} step={1}
              value={Math.round(sel.opacity * 100)}
              onChange={(e) => patchSel({ opacity: Number(e.target.value) / 100 })}
              style={{ flex: 1, minWidth: 0 }}
            />
            <span style={{ ...LBL, width: 34, textAlign: "right", color: "var(--text-secondary)" }}>
              {Math.round(sel.opacity * 100)}%
            </span>
          </div>

          {/* 위치 */}
          <div style={ROW}>
            <span style={LBL}>위치</span>
            <input
              type="number" min={0} max={100} step={1}
              value={Math.round(sel.position * 100)}
              onChange={(e) => patchSel({ position: clamp01(Number(e.target.value) / 100) })}
              style={{ ...FIELD, width: 64 }}
            />
            <span style={{ ...LBL, width: "auto", color: "var(--text-secondary)" }}>%</span>
          </div>
        </div>
      )}
    </div>
  );
}
