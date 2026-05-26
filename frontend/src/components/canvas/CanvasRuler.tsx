"use client";

import { memo } from "react";

// Top + left rulers along the editor workspace edges. Carousel studio
// feedback (slide 3): rulers used to sit flush against the canvas page and
// pan with it. Behave like 미리캔버스 instead — the strips stay pinned to the
// workspace top/left, and only the tick numbers shift so that tick "0"
// always lines up with the page's top-left edge. Zoom/pan only update the
// tick spacing and labels; the strip UI is stationary.

const THICKNESS = 20;
const BG = "var(--bg-elevated)";
const LINE = "var(--border-strong, #5a5a5a)";
const TEXT = "var(--text-tertiary)";

// Major-tick interval (design px) chosen so a numbered tick lands roughly every
// ~64 screen px at the current zoom. Minor ticks are a fifth of that.
function niceInterval(pxPerUnit: number): number {
  const target = 64 / Math.max(pxPerUnit, 1e-4);
  for (const step of [5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000]) {
    if (step >= target) return step;
  }
  return 5000;
}

/** Build ticks (in design units) covering [uMin, uMax] at minor=major/5 spacing. */
function buildTicksRange(uMin: number, uMax: number, major: number): { u: number; major: boolean }[] {
  const minor = major / 5;
  const iMin = Math.floor(uMin / minor);
  const iMax = Math.ceil(uMax / minor);
  const out: { u: number; major: boolean }[] = [];
  for (let i = iMin; i <= iMax; i++) {
    out.push({ u: i * minor, major: i % 5 === 0 });
  }
  return out;
}

export const CanvasRuler = memo(function CanvasRuler({
  pageW,
  pageH,
  zoom,
  pad,
  scale,
  panX,
  panY,
  viewportW,
  viewportH,
}: {
  pageW: number;
  pageH: number;
  zoom: number;
  pad: number;
  scale: number;
  panX: number;
  panY: number;
  viewportW: number;
  viewportH: number;
}) {
  const pxPerUnit = zoom * scale; // screen px per design unit
  const major = niceInterval(pxPerUnit);

  // Wrapper containing the fabric canvas is centered in the viewport, then
  // offset by pan. Inside that wrapper the page sits at (pad*scale, pad*scale)
  // — so the page's top-left in viewport coords is:
  const wrapperW = (pageW + 2 * pad) * scale;
  const wrapperH = (pageH + 2 * pad) * scale;
  const originX = viewportW / 2 - wrapperW / 2 + pad * scale + panX;
  const originY = viewportH / 2 - wrapperH / 2 + pad * scale + panY;

  // Visible design-unit range for each ruler — anything outside the viewport
  // would be wasted SVG. Strip itself starts at THICKNESS to clear the corner.
  const topStartX = THICKNESS;
  const topEndX = viewportW;
  const topUMin = (topStartX - originX) / pxPerUnit;
  const topUMax = (topEndX - originX) / pxPerUnit;
  const topTicks = buildTicksRange(topUMin, topUMax, major);

  const leftStartY = THICKNESS;
  const leftEndY = viewportH;
  const leftUMin = (leftStartY - originY) / pxPerUnit;
  const leftUMax = (leftEndY - originY) / pxPerUnit;
  const leftTicks = buildTicksRange(leftUMin, leftUMax, major);

  const strip: React.CSSProperties = {
    position: "absolute",
    background: BG,
    pointerEvents: "none",
    overflow: "hidden",
    zIndex: 3,
  };

  return (
    <>
      {/* corner square at the top-left of the workspace */}
      <div
        style={{
          ...strip,
          left: 0,
          top: 0,
          width: THICKNESS,
          height: THICKNESS,
          borderRight: `1px solid ${LINE}`,
          borderBottom: `1px solid ${LINE}`,
        }}
      />

      {/* top ruler — pinned to workspace top, spans the full width */}
      <div
        style={{
          ...strip,
          left: THICKNESS,
          top: 0,
          width: Math.max(0, viewportW - THICKNESS),
          height: THICKNESS,
          borderBottom: `1px solid ${LINE}`,
        }}
      >
        <svg width={Math.max(viewportW - THICKNESS, 1)} height={THICKNESS} style={{ display: "block" }}>
          {topTicks.map((t, i) => {
            // x is in strip-local coords — strip is offset by THICKNESS in
            // viewport, so subtract that from the viewport-space origin.
            const x = originX - THICKNESS + t.u * pxPerUnit;
            if (x < -2 || x > viewportW - THICKNESS + 2) return null;
            const h = t.major ? 7 : 4;
            return (
              <g key={i}>
                <line x1={x} y1={THICKNESS - h} x2={x} y2={THICKNESS} stroke={LINE} strokeWidth={1} />
                {t.major && (
                  <text x={x + 2} y={8} fill={TEXT} fontSize={8} fontFamily="monospace">
                    {Math.round(t.u)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* left ruler — pinned to workspace left, spans the full height */}
      <div
        style={{
          ...strip,
          left: 0,
          top: THICKNESS,
          width: THICKNESS,
          height: Math.max(0, viewportH - THICKNESS),
          borderRight: `1px solid ${LINE}`,
        }}
      >
        <svg width={THICKNESS} height={Math.max(viewportH - THICKNESS, 1)} style={{ display: "block" }}>
          {leftTicks.map((t, i) => {
            const y = originY - THICKNESS + t.u * pxPerUnit;
            if (y < -2 || y > viewportH - THICKNESS + 2) return null;
            const h = t.major ? 7 : 4;
            return (
              <g key={i}>
                <line x1={THICKNESS - h} y1={y} x2={THICKNESS} y2={y} stroke={LINE} strokeWidth={1} />
                {t.major && (
                  <text
                    x={7}
                    y={y}
                    fill={TEXT}
                    fontSize={8}
                    fontFamily="monospace"
                    textAnchor="middle"
                    dominantBaseline="central"
                    transform={`rotate(-90 7 ${y})`}
                  >
                    {Math.round(t.u)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </>
  );
});
