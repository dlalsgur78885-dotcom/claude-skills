/** Render a template Layout into a Fabric.Canvas with placeholder content.
 *
 * Each Fabric object carries `data: FabricMeta` so movements/resizes can be
 * mapped back into the source JSON.
 */

import { getFabric } from "@/lib/fabric";
import type { LayoutSpec, BrandStyle, FabricMeta, ShadowSpec, TextStyle, Decoration, GradientFill } from "./types";
import { angleToCoords } from "@/components/GradientBarEditor";

// Direction enum → CSS angle for legacy templates without `angle`.
const DIR_TO_ANGLE = { vertical: 180, horizontal: 90, diagonal: 135 } as const;

const PLACEHOLDER_TITLE = "Title";
const PLACEHOLDER_SUB = "subtitle";
const PLACEHOLDER_DESC = "Description text goes here over two lines.";

function fabricBgFromOverlay(overlay: string | null | undefined, opacity?: number): string {
  if (!overlay) return "rgba(0,0,0,0)";
  const hex = overlay.replace("#", "");
  if (hex.length !== 6) return overlay;
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${opacity ?? 0.3})`;
}

function withMeta<T>(obj: T, meta: FabricMeta): T {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (obj as any).data = meta;
  return obj;
}

/** Build a fabric-compatible shadow CSS string from a structured ShadowSpec.
 *  Distance/blur stored in template space — scale to display space here. */
function buildShadowString(spec: ShadowSpec, scale: number): string {
  const rad = (spec.angle * Math.PI) / 180;
  const offsetX = Math.round(spec.distance * Math.cos(rad) * scale);
  const offsetY = Math.round(spec.distance * Math.sin(rad) * scale);
  const blur = Math.round(spec.blur * scale);
  const hex = (spec.color || "#000000").replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16) || 0;
  const g = parseInt(hex.slice(2, 4), 16) || 0;
  const b = parseInt(hex.slice(4, 6), 16) || 0;
  const a = (Math.max(0, Math.min(100, spec.opacity)) / 100).toFixed(2);
  return `rgba(${r},${g},${b},${a}) ${offsetX}px ${offsetY}px ${blur}px`;
}

/** Apply shadow + stroke from a TextStyle/Decoration onto a fabric object.
 *  Mutates `obj` in place. */
function applyTextEffects(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  obj: any,
  src: { shadow?: ShadowSpec | null; stroke?: string | null; stroke_width?: number } | undefined,
  scale: number,
  isText: boolean,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fabric?: any,
) {
  if (!src) return;
  if (src.shadow) {
    // fabric v7: direct `obj.shadow = "css string"` bypasses the _set wrapper
    // that converts strings into a `Shadow` instance. The raw string then has
    // no .color/.offsetX/.blur, so _setShadow writes undefined/NaN and the
    // object renders incorrectly (no shadow + possible blank caching).
    // Use .set() so the wrapper kicks in, or build a Shadow explicitly.
    const css = buildShadowString(src.shadow, scale);
    if (fabric && fabric.Shadow) {
      obj.set("shadow", new fabric.Shadow(css));
    } else {
      obj.set("shadow", css);
    }
  }
  if (src.stroke && (src.stroke_width || 0) > 0) {
    obj.stroke = src.stroke;
    obj.strokeWidth = (src.stroke_width || 0) * scale;
    obj.strokeUniform = true;
    // Text outlines look right only when the stroke is drawn first — otherwise
    // the fill chews into the glyph and the text reads thinner than the slider
    // suggests. Matches the editor's ShadowSection behavior.
    if (isText) obj.paintFirst = "stroke";
  }
}

/** Build a fabric Gradient for shape decorations. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildGradient(fabric: any, spec: GradientFill, w: number, h: number) {
  const angle = spec.angle ?? DIR_TO_ANGLE[spec.direction ?? "vertical"];
  return new fabric.Gradient({
    type: "linear",
    coords: angleToCoords(angle, w, h),
    colorStops: spec.stops.map((s) => ({ offset: s.offset, color: s.color })),
  });
}

/** Decoration fill → fabric fill (color string OR fabric.Gradient). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function resolveDecorationFill(fabric: any, fill: Decoration["fill"], w: number, h: number): string | object | null {
  if (!fill) return null;
  if (typeof fill === "string") return fill;
  if (fill.type === "linear") return buildGradient(fabric, fill, w, h);
  return null;
}

/** Convert anchored (x, y) to top-left (x, y).
 *
 * Gemini emits text_slots/decorations with an `anchor` such as `"center"` or
 * `"top-center"`, treating `position.x/y` as the anchor point on the slot's
 * box. Fabric (with our v6-compat origin override) draws everything from
 * top-left, so we shift the coords by the slot size when the anchor isn't
 * already top-left.
 */
function anchorToTopLeft(
  pos: { x?: number; y?: number; anchor?: string } | undefined,
  size: { width?: number; height?: number },
): [number, number] {
  const x = pos?.x || 0;
  const y = pos?.y || 0;
  const w = size?.width || 0;
  const h = size?.height || 0;
  switch (pos?.anchor) {
    case "center":
      return [x - w / 2, y - h / 2];
    case "top-center":
      return [x - w / 2, y];
    case "bottom-center":
      return [x - w / 2, y - h];
    default:
      return [x, y]; // top-left and unknown anchors render as-is
  }
}

export async function renderLayoutToCanvas(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  canvas: any,
  layoutName: string,
  layout: LayoutSpec,
  brand: BrandStyle,
  scale: number,
  canvasW: number,
  canvasH: number
) {
  const fabric = await getFabric();

  canvas.clear();

  // 1. Background
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const bg = layout.background as any;
  if (bg?.type === "color") {
    canvas.backgroundColor = bg.value || brand.background_color || "#FFFFFF";
  } else if (bg?.type === "gradient") {
    // Render as a linear gradient rect covering the canvas.
    const a = bg.color_a || "#FFFFFF";
    const b = bg.color_b || "#000000";
    const dir = bg.direction || "vertical";
    const coords =
      dir === "horizontal"
        ? { x1: 0, y1: 0, x2: canvasW * scale, y2: 0 }
        : dir === "diagonal"
        ? { x1: 0, y1: 0, x2: canvasW * scale, y2: canvasH * scale }
        : { x1: 0, y1: 0, x2: 0, y2: canvasH * scale };
    const gradient = new fabric.Gradient({
      type: "linear",
      coords,
      colorStops: [
        { offset: 0, color: a },
        { offset: 1, color: b },
      ],
    });
    const fillRect = new fabric.Rect({
      left: 0, top: 0,
      width: canvasW * scale, height: canvasH * scale,
      fill: gradient, selectable: false, evented: false,
      originX: "left", originY: "top",
    });
    canvas.add(fillRect);
    canvas.sendObjectToBack(fillRect);
  } else if (bg?.type === "composite") {
    // Photo on one side of split_y, solid color on the other.
    canvas.backgroundColor = brand.background_color || "#222222";
    const split = typeof bg.split_y === "number" ? bg.split_y : 0.75;
    const splitPx = Math.round(canvasH * scale * split);
    const topIsPhoto = bg.top?.type !== "color";
    // Photo zone — placeholder gray rect with the keyword text label
    const photoH = topIsPhoto ? splitPx : canvasH * scale - splitPx;
    const photoY = topIsPhoto ? 0 : splitPx;
    const photoLabel = (topIsPhoto ? bg.top?.value : bg.bottom?.value) || bg.value || "photo";
    const photoRect = new fabric.Rect({
      left: 0, top: photoY,
      width: canvasW * scale, height: photoH,
      fill: "rgba(120,120,120,0.5)",
      stroke: "rgba(255,255,255,0.25)", strokeDashArray: [4, 4],
      selectable: false, evented: false,
      originX: "left", originY: "top",
    });
    canvas.add(photoRect);
    canvas.add(new fabric.Textbox(`photo: ${photoLabel}`, {
      left: 12, top: photoY + 8, width: 280,
      fontSize: 11, fontFamily: "monospace", fill: "rgba(255,255,255,0.7)",
      selectable: false, evented: false, originX: "left", originY: "top",
    }));
    // Solid zone
    const solidColor = (topIsPhoto ? bg.bottom?.value : bg.top?.value) || "#FFFFFF";
    const solidH = topIsPhoto ? canvasH * scale - splitPx : splitPx;
    const solidY = topIsPhoto ? splitPx : 0;
    canvas.add(new fabric.Rect({
      left: 0, top: solidY,
      width: canvasW * scale, height: solidH,
      fill: solidColor, selectable: false, evented: false,
      originX: "left", originY: "top",
    }));
  } else {
    // image_keyword / image_path: show brand background + small keyword label
    canvas.backgroundColor = brand.background_color || "#222222";
    if (bg?.value) {
      const label = new fabric.Textbox(`bg: ${bg.value}`, {
        left: 8,
        top: 8,
        width: 240,
        fontSize: 11,
        fontFamily: "monospace",
        fill: "rgba(255,255,255,0.5)",
        selectable: false,
        evented: false,
        originX: "left",
        originY: "top",
      });
      canvas.add(label);
    }
  }

  // 2. Background overlay — solid OR gradient
  if (bg?.overlay_kind === "gradient" && Array.isArray(bg.overlay_gradient_stops) && bg.overlay_gradient_stops.length >= 2) {
    const dir = bg.overlay_gradient_direction || "vertical";
    const coords =
      dir === "horizontal" ? { x1: 0, y1: 0, x2: canvasW * scale, y2: 0 }
      : dir === "diagonal" ? { x1: 0, y1: 0, x2: canvasW * scale, y2: canvasH * scale }
      : { x1: 0, y1: 0, x2: 0, y2: canvasH * scale };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const colorStops = bg.overlay_gradient_stops.map((s: any) => {
      const hex = (s.color || "#000000").replace("#", "");
      const r = parseInt(hex.slice(0, 2), 16) || 0;
      const g = parseInt(hex.slice(2, 4), 16) || 0;
      const b = parseInt(hex.slice(4, 6), 16) || 0;
      return { offset: Number(s.offset) || 0, color: `rgba(${r},${g},${b},${s.alpha ?? 0})` };
    });
    const ovGradient = new fabric.Gradient({ type: "linear", coords, colorStops });
    const ovRect = new fabric.Rect({
      left: 0, top: 0,
      width: canvasW * scale, height: canvasH * scale,
      fill: ovGradient, selectable: false, evented: false,
      originX: "left", originY: "top",
    });
    canvas.add(ovRect);
  } else if (bg?.overlay_color && bg?.overlay_opacity && bg.overlay_opacity > 0.001) {
    const overlay = new fabric.Rect({
      left: 0,
      top: 0,
      width: canvasW * scale,
      height: canvasH * scale,
      fill: fabricBgFromOverlay(bg.overlay_color, bg.overlay_opacity),
      selectable: false,
      evented: false,
      originX: "left",
      originY: "top",
    });
    canvas.add(overlay);
  }

  const layoutPath = `layouts.${layoutName}`;

  // 3. Decorations
  for (let i = 0; i < (layout.decorations || []).length; i++) {
    const d = layout.decorations[i];
    const path = `${layoutPath}.decorations[${i}]`;
    const [dx, dy] = anchorToTopLeft(d.position, d.size);
    const w = (d.size.width || 100) * scale;
    const h = (d.size.height || 50) * scale;

    // Image decoration: load the actual PNG so the user can position it visually.
    // Falls through to a placeholder rect on load failure so the slot is still
    // draggable and the meta path stays attached.
    if (d.kind === "image" && d.src) {
      try {
        // fabric v6 exposes FabricImage; v5 used Image. Resolve at runtime.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const ImageCtor = (fabric as any).FabricImage || (fabric as any).Image;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const img: any = await ImageCtor.fromURL(d.src, { crossOrigin: "anonymous" });
        img.set({
          left: dx * scale,
          top: dy * scale,
          originX: "left",
          originY: "top",
          cornerColor: "#3CC8FF",
          cornerSize: 8,
          transparentCorners: false,
          opacity: d.opacity ?? 1,
        });
        // Force the rendered size to match the slot box so user resizes round-trip.
        const naturalW = img.width || w;
        const naturalH = img.height || h;
        img.scaleX = w / naturalW;
        img.scaleY = h / naturalH;
        applyTextEffects(img, d, scale, false, fabric);
        // BlendColor filter (image-only color tint). intensity 0이면 skip.
        // fabric v7는 ESM modular: `fabric.BlendColor` (top-level) 와
        // `fabric.filters.BlendColor` 둘 다 가능. 둘 다 시도하고 fabric의
        // 즉시 재렌더도 명시한다.
        if (d.color_fill && d.color_fill.intensity > 0) {
          try {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const Blend = (fabric as any).filters?.BlendColor || (fabric as any).BlendColor;
            if (Blend) {
              const filter = new Blend({
                color: d.color_fill.color || "#000000",
                mode: "tint",
                alpha: Math.max(0, Math.min(1, d.color_fill.intensity / 100)),
              });
              img.filters = [filter];
              img.applyFilters();
              img.dirty = true;
            } else {
              // eslint-disable-next-line no-console
              console.warn("[renderer] fabric BlendColor not found", Object.keys((fabric as object) || {}));
            }
          } catch (e) {
            // eslint-disable-next-line no-console
            console.warn("[renderer] BlendColor apply failed:", e);
          }
        }
        canvas.add(withMeta(img, { path, kind: "decoration" }));
        continue;
      } catch {
        // fall through to placeholder
      }
    }

    // Shape kind with explicit fill renders as a real solid rectangle — no
    // dashed placeholder stroke, no "SHAPE" label. Image/logo slots without a
    // src still render as labeled placeholders so the user knows what's there.
    const isShape = d.kind === "shape";
    const hasFill = !!d.fill;
    const showPlaceholderChrome = !isShape || !hasFill;
    const userStroke = d.stroke && (d.stroke_width || 0) > 0;
    const resolvedFill = resolveDecorationFill(fabric, d.fill, w, h);

    const rect = new fabric.Rect({
      left: dx * scale,
      top: dy * scale,
      width: w,
      height: h,
      fill: resolvedFill ?? (showPlaceholderChrome ? "rgba(255,255,255,0.12)" : "transparent"),
      stroke: userStroke ? d.stroke : showPlaceholderChrome ? "rgba(255,255,255,0.6)" : undefined,
      strokeWidth: userStroke ? (d.stroke_width || 0) * scale : showPlaceholderChrome ? 1 : 0,
      strokeUniform: userStroke ? true : undefined,
      strokeDashArray: !userStroke && showPlaceholderChrome ? [4, 4] : undefined,
      cornerColor: "#3CC8FF",
      cornerSize: 8,
      transparentCorners: false,
      originX: "left",
      originY: "top",
      opacity: d.opacity ?? 1,
    });
    if (d.shadow) {
      // v7: see comment in applyTextEffects — must go through .set() or be a
      // Shadow instance, otherwise rendering produces NaN shadow params.
      rect.set("shadow", new fabric.Shadow(buildShadowString(d.shadow, scale)));
    }
    canvas.add(withMeta(rect, { path, kind: "decoration" }));

    if (showPlaceholderChrome) {
      const label = new fabric.Textbox(d.kind.toUpperCase(), {
        left: dx * scale,
        top: dy * scale + 4,
        width: w,
        fontSize: 11,
        fontFamily: "monospace",
        fill: "rgba(255,255,255,0.85)",
        textAlign: "center",
        selectable: false,
        evented: false,
        originX: "left",
        originY: "top",
      });
      canvas.add(label);
    }
  }

  // 4. Text slots
  (layout.text_slots || []).forEach((t, i) => {
    const path = `${layoutPath}.text_slots[${i}]`;
    const fontSize = (t.style?.font_size || 24) * scale;
    const [tx, ty] = anchorToTopLeft(t.position, t.size);
    const tb = new fabric.Textbox(`[${t.role.toUpperCase()}]`, {
      left: tx * scale,
      top: ty * scale,
      width: (t.size.width || 400) * scale,
      fontSize,
      fontFamily: t.style?.font_family || "Pretendard",
      fontWeight: t.style?.font_weight || "400",
      fill: t.style?.fill || "#FFFFFF",
      textAlign: (t.style?.text_align || "left") as "left" | "center" | "right",
      lineHeight: t.style?.line_height || 1.4,
      cornerColor: "#3CC8FF",
      cornerSize: 8,
      transparentCorners: false,
      editable: false,
      originX: "left",
      originY: "top",
      opacity: t.opacity ?? 1,
    });
    applyTextEffects(tb, t.style, scale, true, fabric);
    canvas.add(withMeta(tb, { path, kind: "text_slot" }));
  });

  // 5. Grid (origin point + per-cell placeholders)
  if (layout.grid) {
    const g = layout.grid;
    const originPath = `${layoutPath}.grid.origin`;
    const imageAreaPath = `${layoutPath}.grid.item_box.image_area`;

    for (let r = 0; r < g.rows; r++) {
      for (let c = 0; c < g.cols; c++) {
        const cellX = g.origin.x + c * (g.cell_size.width + g.gap_x);
        const cellY = g.origin.y + r * (g.cell_size.height + g.gap_y);

        // image area inside the cell
        const ia = g.item_box.image_area;
        const imgRect = new fabric.Rect({
          left: (cellX + ia.x) * scale,
          top: (cellY + ia.y) * scale,
          width: ia.width * scale,
          height: ia.height * scale,
          fill: "rgba(120,120,120,0.5)",
          stroke: r === 0 && c === 0 ? "#3CC8FF" : "rgba(255,255,255,0.3)",
          strokeWidth: 1.5,
          strokeDashArray: r === 0 && c === 0 ? undefined : [4, 4],
          cornerColor: "#3CC8FF",
          cornerSize: 8,
          transparentCorners: false,
          // Only the first cell is the "controller" — drag it to update item_box
          selectable: r === 0 && c === 0,
          evented: r === 0 && c === 0,
          originX: "left",
          originY: "top",
        });
        if (r === 0 && c === 0) {
          canvas.add(withMeta(imgRect, { path: imageAreaPath, kind: "grid_image" }));
        } else {
          canvas.add(imgRect);
        }

        // Title placeholder
        const titleStyle: TextStyle = g.item_box.title_style || {};
        const title = new fabric.Textbox(PLACEHOLDER_TITLE, {
          left: cellX * scale,
          top: (cellY + (g.item_box.title_offset_y || 0)) * scale,
          width: g.cell_size.width * scale,
          fontSize: (titleStyle.font_size || 24) * scale,
          fontFamily: titleStyle.font_family || "Pretendard",
          fontWeight: titleStyle.font_weight || "700",
          fill: titleStyle.fill || "#FFFFFF",
          textAlign: (titleStyle.text_align || "center") as "left" | "center" | "right",
          selectable: false,
          evented: false,
          originX: "left",
          originY: "top",
        });
        applyTextEffects(title, titleStyle, scale, true, fabric);
        canvas.add(title);

        // Subtitle (if defined)
        if (g.item_box.subtitle_style && g.item_box.subtitle_offset_y != null) {
          const ss: TextStyle = g.item_box.subtitle_style;
          const subtitle = new fabric.Textbox(PLACEHOLDER_SUB, {
            left: cellX * scale,
            top: (cellY + g.item_box.subtitle_offset_y) * scale,
            width: g.cell_size.width * scale,
            fontSize: (ss.font_size || 18) * scale,
            fontFamily: ss.font_family || "Pretendard",
            fontWeight: ss.font_weight || "400",
            fill: ss.fill || "#CCCCCC",
            textAlign: (ss.text_align || "center") as "left" | "center" | "right",
            selectable: false,
            evented: false,
            originX: "left",
            originY: "top",
          });
          applyTextEffects(subtitle, ss, scale, true, fabric);
          canvas.add(subtitle);
        }

        // Description (if defined)
        if (g.item_box.description_style && g.item_box.description_offset_y != null) {
          const ds: TextStyle = g.item_box.description_style;
          const desc = new fabric.Textbox(PLACEHOLDER_DESC, {
            left: cellX * scale,
            top: (cellY + g.item_box.description_offset_y) * scale,
            width: g.cell_size.width * scale,
            fontSize: (ds.font_size || 16) * scale,
            fontFamily: ds.font_family || "Pretendard",
            fontWeight: ds.font_weight || "400",
            fill: ds.fill || "#E0E0E0",
            textAlign: (ds.text_align || "center") as "left" | "center" | "right",
            lineHeight: ds.line_height || 1.5,
            selectable: false,
            evented: false,
            originX: "left",
            originY: "top",
          });
          applyTextEffects(desc, ds, scale, true, fabric);
          canvas.add(desc);
        }
      }
    }

    // Origin handle: a small diamond at the grid origin
    const originHandle = new fabric.Rect({
      left: g.origin.x * scale - 8,
      top: g.origin.y * scale - 8,
      width: 16,
      height: 16,
      fill: "#3CC8FF",
      angle: 45,
      lockScalingX: true,
      lockScalingY: true,
      hasControls: false,
      cornerColor: "#3CC8FF",
      originX: "left",
      originY: "top",
    });
    canvas.add(withMeta(originHandle, { path: originPath, kind: "grid_origin" }));
  }

  canvas.renderAll();
}
