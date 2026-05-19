"use client";

import { proxiedImageUrl } from "@/lib/api";
import type { SlideData } from "@/lib/types";

interface Props {
  slide: SlideData;
  size?: number;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Obj = Record<string, any>;

// Render a SlideData object's fill into a CSS-compatible background value.
// Fabric/renderer emits either a hex string or a gradient spec `{ type:"linear",
// coords:{x1,y1,x2,y2}, colorStops:[{offset, color}] }`. The CSS linear-gradient
// angle is computed from the gradient's two endpoints.
function fillToCss(fill: unknown): string {
  if (typeof fill === "string") return fill;
  if (fill && typeof fill === "object") {
    const f = fill as Obj;
    if (f.type === "linear" && Array.isArray(f.colorStops)) {
      const c = f.coords || {};
      const dx = (c.x2 || 0) - (c.x1 || 0);
      const dy = (c.y2 || 0) - (c.y1 || 0);
      // CSS angle: 0deg points up; gradient grows downward by default.
      const deg = (Math.atan2(dy, dx) * 180) / Math.PI + 90;
      const stops = f.colorStops
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .map((s: any) => `${s.color} ${(Number(s.offset) || 0) * 100}%`)
        .join(", ");
      return `linear-gradient(${deg}deg, ${stops})`;
    }
  }
  return "transparent";
}

// Pick the rect that "represents" this image in design coords. For fabric-format
// images saved with cover-fit clipPath, the clip's box IS the slot the user
// sees, even though the underlying image extends beyond it. Render to that
// box and let CSS object-fit:cover handle the crop.
function imageBox(obj: Obj): { x: number; y: number; w: number; h: number } {
  const clip = obj.clipPath;
  if (clip && (clip.absolutePositioned || clip.left != null)) {
    const cw = (Number(clip.width) || 0) * (Number(clip.scaleX) || 1);
    const ch = (Number(clip.height) || 0) * (Number(clip.scaleY) || 1);
    if (cw > 0 && ch > 0) {
      return { x: Number(clip.left) || 0, y: Number(clip.top) || 0, w: cw, h: ch };
    }
  }
  const sx = Number(obj.scaleX) || 1;
  const sy = Number(obj.scaleY) || 1;
  return {
    x: Number(obj.left) || 0,
    y: Number(obj.top) || 0,
    w: (Number(obj.width) || 0) * sx,
    h: (Number(obj.height) || 0) * sy,
  };
}

export function SlideThumbnail({ slide, size = 80 }: Props) {
  const designW = Number(slide.width) || 1080;
  const designH = Number(slide.height) || 1080;
  // Fit the design rect inside `size` (square) while preserving aspect.
  const scale = size / Math.max(designW, designH);
  const renderedW = designW * scale;
  const renderedH = designH * scale;

  return (
    <div
      style={{
        position: "relative",
        width: renderedW,
        height: renderedH,
        overflow: "hidden",
        background: typeof slide.background === "string" ? slide.background : "#FFFFFF",
        borderRadius: 4,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: designW,
          height: designH,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
        }}
      >
        {/* Render in z-priority order rather than array order. fabric's
            sendObjectToBack / send-to-front shuffles canvas.getObjects(), and
            toJSON emits that mutated sequence into slide.objects. A naive
            map() then paints small grid-cell photos before the full-bleed
            background — so the bg ends up on top and hides the cells, even
            though fabric's render and the downloaded PNG show the cells
            correctly. Sort here by intent (bg → rect → cell → text) so the
            thumbnail mirrors the export. */}
        {(slide.objects || []).slice().sort((a, b) => {
          const aa = a as Obj, bb = b as Obj;
          const pri = (o: Obj) => {
            const t = String(o.type || "").toLowerCase();
            if (t === "textbox" || t === "text" || t === "i-text" || t === "itext") return 4;
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const kind = (o.data as any)?.kind;
            if (kind === "user_item_image") return 3;
            if (kind === "user_image") return 2;
            if (t === "rect") return 1;
            return 0;  // background image / decoration
          };
          return pri(aa) - pri(bb);
        }).map((rawObj, i) => {
          const obj = rawObj as Obj;
          const t = String(obj.type || "").toLowerCase();
          const opacity = typeof obj.opacity === "number" ? obj.opacity : 1;

          if (t === "image" || t === "fabricimage") {
            const { x, y, w, h } = imageBox(obj);
            if (!obj.src || w <= 0 || h <= 0) return null;
            return (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={proxiedImageUrl(String(obj.src))}
                alt=""
                style={{
                  position: "absolute",
                  left: x,
                  top: y,
                  width: w,
                  height: h,
                  objectFit: "cover",
                  opacity,
                  pointerEvents: "none",
                  display: "block",
                }}
              />
            );
          }

          if (t === "textbox" || t === "text" || t === "i-text" || t === "itext") {
            const fontSize = Number(obj.fontSize) || 24;
            const sx = Number(obj.scaleX) || 1;
            const sy = Number(obj.scaleY) || 1;
            // Fabric stores wrap width as `width`; height auto-grows. Use scaleY
            // as a vertical hint so resized text stays roughly the right size.
            const widthBox = (Number(obj.width) || 400) * sx;
            return (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: Number(obj.left) || 0,
                  top: Number(obj.top) || 0,
                  width: widthBox,
                  fontSize: fontSize * sy,
                  lineHeight: typeof obj.lineHeight === "number" ? obj.lineHeight : 1.4,
                  fontFamily: typeof obj.fontFamily === "string" ? obj.fontFamily : "Pretendard, sans-serif",
                  fontWeight: obj.fontWeight ?? 400,
                  fontStyle: typeof obj.fontStyle === "string" ? obj.fontStyle : "normal",
                  color: typeof obj.fill === "string" ? obj.fill : "#000000",
                  textAlign: (obj.textAlign as "left" | "center" | "right") || "left",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  opacity,
                  pointerEvents: "none",
                }}
              >
                {typeof obj.text === "string" ? obj.text : ""}
              </div>
            );
          }

          if (t === "rect") {
            const sx = Number(obj.scaleX) || 1;
            const sy = Number(obj.scaleY) || 1;
            return (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: Number(obj.left) || 0,
                  top: Number(obj.top) || 0,
                  width: (Number(obj.width) || 0) * sx,
                  height: (Number(obj.height) || 0) * sy,
                  background: fillToCss(obj.fill),
                  borderRadius: Number(obj.rx) || 0,
                  opacity,
                  pointerEvents: "none",
                }}
              />
            );
          }

          if (t === "circle") {
            const r = Number(obj.radius) || 0;
            const sx = Number(obj.scaleX) || 1;
            const sy = Number(obj.scaleY) || 1;
            return (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: Number(obj.left) || 0,
                  top: Number(obj.top) || 0,
                  width: r * 2 * sx,
                  height: r * 2 * sy,
                  background: fillToCss(obj.fill),
                  borderRadius: "50%",
                  opacity,
                  pointerEvents: "none",
                }}
              />
            );
          }

          // Unknown / unsupported types (line, path, group, etc.) — skip for thumbs
          return null;
        })}
      </div>
    </div>
  );
}
