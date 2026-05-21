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
            if (!obj.src) return null;
            const sx = Number(obj.scaleX) || 1;
            const sy = Number(obj.scaleY) || 1;
            const imgX = Number(obj.left) || 0;
            const imgY = Number(obj.top) || 0;
            const imgW = (Number(obj.width) || 0) * sx;
            const imgH = (Number(obj.height) || 0) * sy;
            if (imgW <= 0 || imgH <= 0) return null;
            const src = proxiedImageUrl(String(obj.src));
            // Cover-fit images carry an absolutePositioned clipPath = the visible
            // slot. Draw the image at its REAL pan/zoom and clip it to that slot
            // so the thumbnail mirrors the canvas crop. (objectFit:cover would
            // re-center and ignore the user's pan/resize — the slide preview
            // then never reflects a moved/resized photo.)
            const clip = obj.clipPath;
            if (clip && (clip.absolutePositioned || clip.left != null)) {
              const clipX = Number(clip.left) || 0;
              const clipY = Number(clip.top) || 0;
              const clipW = (Number(clip.width) || 0) * (Number(clip.scaleX) || 1);
              const clipH = (Number(clip.height) || 0) * (Number(clip.scaleY) || 1);
              if (clipW > 0 && clipH > 0) {
                return (
                  <div
                    key={i}
                    style={{
                      position: "absolute",
                      left: clipX,
                      top: clipY,
                      width: clipW,
                      height: clipH,
                      overflow: "hidden",
                      opacity,
                      pointerEvents: "none",
                    }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt=""
                      style={{
                        position: "absolute",
                        left: imgX - clipX,
                        top: imgY - clipY,
                        width: imgW,
                        height: imgH,
                        display: "block",
                      }}
                    />
                  </div>
                );
              }
            }
            return (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={src}
                alt=""
                style={{
                  position: "absolute",
                  left: imgX,
                  top: imgY,
                  width: imgW,
                  height: imgH,
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
