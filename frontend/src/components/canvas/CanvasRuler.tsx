"use client";

import { memo } from "react";

// Top + left rulers along the design page edges — carousel studio feedback,
// slide 5. Mounted INSIDE the canvas wrapper div (a sibling of <canvas>), so it
// pans with the page automatically; only zoom and page size change its content.
//
// Wrapper-space coordinate of a design point d:  (d * zoom + pad) * scale
// So the page's top-left sits at (pad*scale, pad*scale) and the page renders
// pageW*zoom*scale wide. The rulers hug those page edges and never extend into
// the dark workspace gutter (feedback req 2). Strip thickness is screen px and
// zoom-independent; only tick spacing/labels scale with zoom (req 3-4).

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

function buildTicks(lenUnits: number, major: number): { u: number; major: boolean }[] {
  const minor = major / 5;
  const out: { u: number; major: boolean }[] = [];
  for (let i = 0; i * minor <= lenUnits + 0.5; i++) {
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
}: {
  pageW: number;
  pageH: number;
  zoom: number;
  pad: number;
  scale: number;
}) {
  const pxPerUnit = zoom * scale; // screen px per design unit
  const major = niceInterval(pxPerUnit);
  const origin = pad * scale; // page top-left in wrapper coords
  const railW = pageW * pxPerUnit; // on-screen page width
  const railH = pageH * pxPerUnit; // on-screen page height

  const strip: React.CSSProperties = {
    position: "absolute",
    background: BG,
    pointerEvents: "none",
    overflow: "hidden",
    zIndex: 3,
  };

  return (
    <>
      {/* corner square where the two rulers meet */}
      <div
        style={{
          ...strip,
          left: origin - THICKNESS,
          top: origin - THICKNESS,
          width: THICKNESS,
          height: THICKNESS,
          borderRight: `1px solid ${LINE}`,
          borderBottom: `1px solid ${LINE}`,
        }}
      />

      {/* top ruler — X axis, canvas width only */}
      <div
        style={{
          ...strip,
          left: origin,
          top: origin - THICKNESS,
          width: railW,
          height: THICKNESS,
          borderBottom: `1px solid ${LINE}`,
        }}
      >
        <svg width={Math.max(railW, 1)} height={THICKNESS} style={{ display: "block" }}>
          {buildTicks(pageW, major).map((t, i) => {
            const x = t.u * pxPerUnit;
            const h = t.major ? 7 : 4;
            return (
              <g key={i}>
                <line x1={x} y1={THICKNESS - h} x2={x} y2={THICKNESS} stroke={LINE} strokeWidth={1} />
                {t.major && t.u > 0 && (
                  <text x={x + 2} y={8} fill={TEXT} fontSize={8} fontFamily="monospace">
                    {Math.round(t.u)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {/* left ruler — Y axis, canvas height only */}
      <div
        style={{
          ...strip,
          left: origin - THICKNESS,
          top: origin,
          width: THICKNESS,
          height: railH,
          borderRight: `1px solid ${LINE}`,
        }}
      >
        <svg width={THICKNESS} height={Math.max(railH, 1)} style={{ display: "block" }}>
          {buildTicks(pageH, major).map((t, i) => {
            const y = t.u * pxPerUnit;
            const h = t.major ? 7 : 4;
            return (
              <g key={i}>
                <line x1={THICKNESS - h} y1={y} x2={THICKNESS} y2={y} stroke={LINE} strokeWidth={1} />
                {t.major && t.u > 0 && (
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
