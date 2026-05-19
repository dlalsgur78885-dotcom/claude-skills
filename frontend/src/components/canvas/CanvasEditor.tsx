"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { ToolPanel } from "./ToolPanel";
import { PropertyPanel } from "./PropertyPanel";
import { SlideNavigator } from "./SlideNavigator";
import { createCoverSlide, createEmptySlide, createCtaSlide } from "@/lib/canvas-utils";
import { api, proxiedImageUrl } from "@/lib/api";
import { getFabric } from "@/lib/fabric";
import { CanvasSizeSelector } from "@/components/CanvasSizeSelector";
import type { SlideData, TemplateSummary } from "@/lib/types";

const DISPLAY_MAX = 700;
// Padding (canvas-space px) around the page on every side. Fabric draws into a
// buffer of (page + 2·PAD), and a viewportTransform shifts every object by PAD
// so object coordinates stay page-relative — only the pixel buffer changes.
// Result: selection chrome (border + handles) on objects that extend past the
// page is no longer clipped by the canvas edge.
//
// Padding wide enough that the surrounding band reads as real workspace
// (~55% of the page width on each side) — small enough that the page itself
// still takes the central ~45% of the canvas display. Adjust together with
// DISPLAY_MAX above.
// Pad is sized so the canvas buffer always overflows the viewport on every
// side at the typical editor layout — that way the PAD and the workspace
// around the canvas are the same surface (same color, same role: out-of-page
// objects render and stay selectable anywhere the user can see).
// overflow:hidden on the viewport container clips the excess.
const PAGE_PAD = 2000;

function displayDims(w: number, h: number) {
  // Scale based on the page (not the buffer) so the page itself renders at the
  // configured display size regardless of how big PAGE_PAD grows.
  const s = DISPLAY_MAX / Math.max(w, h);
  const totalW = w + 2 * PAGE_PAD;
  const totalH = h + 2 * PAGE_PAD;
  return { w: Math.round(totalW * s), h: Math.round(totalH * s) };
}

// `data.kind` marker on the page-boundary rect so the auto-lock pass and
// other heuristics can recognize it.
const PAGE_BOUNDARY_KIND = "page_boundary";

/** Stamp the CSS size of the fabric canvas DOM nodes from a (pageW, pageH).
 *  setDimensions() updates the bitmap buffer AND the CSS by default, which
 *  blows up the on-screen size to the padded buffer dimensions. We want CSS
 *  to follow displayDims (DISPLAY_MAX-fit) instead.
 *
 *  Mirrors the manual size-stamp that the init block already does so every
 *  size change goes through one place. */
function applyDisplayCss(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  canvas: any,
  pageW: number,
  pageH: number,
) {
  const d = displayDims(pageW, pageH);
  const lower = canvas.lowerCanvasEl;
  const upper = canvas.upperCanvasEl;
  if (lower) { lower.style.width = `${d.w}px`; lower.style.height = `${d.h}px`; }
  if (upper) { upper.style.width = `${d.w}px`; upper.style.height = `${d.h}px`; }
  if (canvas.wrapperEl) { canvas.wrapperEl.style.width = `${d.w}px`; canvas.wrapperEl.style.height = `${d.h}px`; }
}

/** Add or refresh the page-boundary rect on a canvas. Called from the initial
 *  setup AND after every load — canvas.clear() and loadFromJSON wipe all
 *  objects, including ours, so we have to put it back. The rect is kept
 *  inside the canvas at object-space (0,0,w,h); the viewportTransform handles
 *  shifting it inside the padded pixel buffer. */
function ensurePageBoundary(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  canvas: any,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fabric: any,
  w: number,
  h: number,
  fill: string,
) {
  // Reuse an existing boundary if one survived (some clear paths preserve
  // refs but drop them from the canvas). Otherwise build a fresh one.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let pb = (canvas as any).__pageBoundary;
  const existing = pb && canvas.getObjects().includes(pb);
  if (!existing) {
    pb = new fabric.Rect({
      left: 0, top: 0,
      width: w, height: h,
      fill,
      // Strong outline so the page edge is obvious regardless of how the
      // slide content fills it — otherwise slides whose content sits inside
      // a sub-region of the page (e.g. cover slides) read as "smaller" than
      // slides whose grid fills the page edge to edge.
      stroke: "#3CC8FF",
      strokeWidth: 4,
      strokeUniform: true,
      selectable: false, evented: false,
      excludeFromExport: true,
      hoverCursor: "default",
      originX: "left", originY: "top",
    });
    pb.data = { kind: PAGE_BOUNDARY_KIND };
    canvas.add(pb);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (canvas as any).__pageBoundary = pb;
  } else {
    pb.set({
      width: w, height: h, fill,
      stroke: "#3CC8FF",
      strokeWidth: 4,
      strokeUniform: true,
    });
    pb.setCoords();
  }
  canvas.sendObjectToBack(pb);
  return pb;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function rgbaFromPsd(c: any): string | null {
  if (!c) return null;
  const r = Math.round(c.r ?? c.red ?? 0);
  const g = Math.round(c.g ?? c.green ?? 0);
  const b = Math.round(c.b ?? c.blue ?? 0);
  const a = typeof c.a === "number" ? c.a : 1;
  return a < 1 ? `rgba(${r},${g},${b},${a})` : `#${[r, g, b].map((n) => n.toString(16).padStart(2, "0")).join("")}`;
}

interface CanvasEditorProps {
  initialSlides?: SlideData[];
  onSave?: (slides: SlideData[]) => void;
  currentTemplateId?: number | null;
  canReapplyTemplate?: boolean;
  onReapplyTemplate?: (templateId: number) => Promise<SlideData[] | null>;
  // When the parent owns finalization state (e.g. the /editor/[id] page), it
  // can pass the current value and a setter so the header surfaces a "✓ 완성"
  // toggle next to the save button.
  isFinalized?: boolean;
  onToggleFinalized?: () => void | Promise<void>;
  // Project title — shown at the top of the toolbar with click-to-rename.
  // onRenameTitle is async so the caller can PATCH the server and bubble
  // errors back; the editor only displays + reports the new value.
  title?: string;
  onRenameTitle?: (next: string) => void | Promise<void>;
  // Instagram caption + hashtag chips generated in the "콘텐츠 확인" step.
  // Surfaced in the left tool panel via a "캡션 보기" button so the user can
  // grab the copy when they're ready to post — it's otherwise stranded in
  // backend canvas_data and invisible inside the editor.
  caption?: string;
  hashtags?: string[];
}

export function CanvasEditor({
  initialSlides,
  onSave,
  currentTemplateId,
  canReapplyTemplate,
  onReapplyTemplate,
  isFinalized,
  onToggleFinalized,
  title,
  onRenameTitle,
  caption,
  hashtags,
}: CanvasEditorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fabricRef = useRef<any>(null);

  // Workspace zoom + pan (Miricanvas-style). Zoom is applied inside fabric via
  // viewportTransform scale — the canvas DOM keeps its full CSS size so the
  // PAD band always overflows the viewport (no exposed "outer viewport" at
  // low zoom). Pan stays as a CSS translate on the wrapper.
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const zoomRef = useRef(1);
  const canvasViewportRef = useRef<HTMLDivElement>(null);

  // Inline project-title rename in the top toolbar. Click the title to switch
  // into an input; Enter / blur commits via onRenameTitle, Esc cancels.
  const [titleEditing, setTitleEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  function startTitleEdit() {
    if (!onRenameTitle) return;
    setTitleDraft(title || "");
    setTitleEditing(true);
  }
  function cancelTitleEdit() { setTitleEditing(false); setTitleDraft(""); }
  async function commitTitleEdit() {
    const next = titleDraft.trim();
    if (!next || next === (title || "")) { cancelTitleEdit(); return; }
    try {
      await onRenameTitle?.(next);
    } catch (err) {
      alert(err instanceof Error ? err.message : "이름 변경 실패");
    } finally {
      setTitleEditing(false);
      setTitleDraft("");
    }
  }
  const ZOOM_MIN = 0.2;
  const ZOOM_MAX = 4;
  const ZOOM_STEP = 0.1;
  const clampZoom = (z: number) => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
  function resetZoomPan() { setZoom(1); setPan({ x: 0, y: 0 }); }

  // Push the zoom state into fabric's viewportTransform whenever it changes.
  // The canvas DOM stays at constant CSS size — zoom only affects how the
  // content is rendered within the buffer — so the PAD always overflows the
  // viewport regardless of zoom level.
  useEffect(() => {
    zoomRef.current = zoom;
    const canvas = fabricRef.current;
    if (!canvas) return;
    canvas.setViewportTransform([zoom, 0, 0, zoom, PAGE_PAD, PAGE_PAD]);
    canvas.requestRenderAll();
  }, [zoom]);

  // Image crop mode. Triggered by double-clicking an image — we add an
  // auxiliary fabric.Rect with 8 corner handles for the user to resize. On
  // commit, the rect bounds become an absolutePositioned clipPath on the
  // image (non-destructive crop — the original pixels stay, only visibility
  // changes). Enter / outside-click = confirm, Esc = cancel.
  const [cropping, setCropping] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cropAuxRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cropImgRef = useRef<any>(null);
  // Original clipPath captured when crop mode begins so Esc / cancel can
  // restore the pre-crop state after a live-preview drag.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cropOrigClipRef = useRef<any>(null);
  // Four rectangles that dim the canvas OUTSIDE the crop selection
  // (Miricanvas-style — makes the surviving slice obvious).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cropDimsRef = useRef<any[]>([]);

  // Editable zoom-% input. We hold the displayed text separately so the user
  // can type "12" without it snapping back to the live zoom mid-keystroke.
  // The input syncs to `zoom` whenever it isn't focused (wheel/keyboard nudges).
  const [zoomInputText, setZoomInputText] = useState("100");
  const [zoomInputFocused, setZoomInputFocused] = useState(false);
  useEffect(() => {
    if (!zoomInputFocused) setZoomInputText(String(Math.round(zoom * 100)));
  }, [zoom, zoomInputFocused]);
  function commitZoomInput() {
    const n = parseFloat(zoomInputText.replace(/[^\d.]/g, ""));
    if (Number.isFinite(n) && n > 0) {
      setZoom(clampZoom(n / 100));
    } else {
      setZoomInputText(String(Math.round(zoom * 100)));
    }
  }
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);
  // Ref mirror so keyboard handlers (registered once with empty deps) and
  // SlideNavigator callbacks always see the freshest slide index — otherwise
  // Ctrl+D / Delete duplicate / remove the slide that was current at mount
  // time instead of the one the user just clicked in the bottom strip.
  const currentSlideIndexRef = useRef(0);
  currentSlideIndexRef.current = currentSlideIndex;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [selectedObject, setSelectedObject] = useState<any>(null);
  // Character range inside a textbox. Persists across text:editing:exited so the
  // property panel can apply styles to the user's drag-selection even after focus
  // moves to a panel input (fabric resets selectionStart/End when editing ends).
  const [selectedTextRange, setSelectedTextRange] = useState<{ start: number; end: number } | null>(null);
  // Ref mirror so the Ctrl+B keyboard handler (registered with empty deps) reads
  // the latest range instead of a stale closure value.
  const selectedTextRangeRef = useRef<{ start: number; end: number } | null>(null);
  selectedTextRangeRef.current = selectedTextRange;
  // Stable per-object id so selection:updated can detect "same object, just
  // updated handles" vs "switched to a different object". Without this we'd
  // null out the textRange every time fabric refreshes the selection box.
  const selectedObjectIdRef = useRef<string | null>(null);
  // In-memory clipboard for Ctrl+C / Ctrl+V of canvas objects. Cleared by Ctrl+X.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const objectClipboardRef = useRef<any>(null);
  const [slides, setSlides] = useState<SlideData[]>(
    initialSlides || [createCoverSlide(), createEmptySlide(), createCtaSlide()]
  );
  // Ref mirror so loadSlide / removeSlide / duplicateSlide can always read
  // the freshest slides array — React state updates are batched and don't
  // commit until the next render, but Ctrl+D / Delete may fire a follow-up
  // loadSlide inside the same tick.
  const slidesRef = useRef<SlideData[]>(slides);
  slidesRef.current = slides;

  // ─── Auto-save ─────────────────────────────────────────────────────────
  // Watch the slides array; whenever the user mutates something the editor
  // re-serializes into state via saveCurrentSlide(), so any change here
  // means there is something new to persist. Debounce by 1s so a burst of
  // edits (drag, slider scrub, IME composition) collapses into one PATCH.
  // The manual 저장 button is kept for an explicit immediate-flush path.
  type SaveStatus = "idle" | "pending" | "saving" | "saved" | "error";
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  // useRef for the latest onSave so a fresh parent render doesn't rearm the
  // debounce effect just because the callback identity changed.
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Skip the very first slides effect — that fires when initialSlides hydrate
  // and there's nothing user-driven to persist yet.
  const firstSlidesEffectRef = useRef(true);
  useEffect(() => {
    if (firstSlidesEffectRef.current) {
      firstSlidesEffectRef.current = false;
      return;
    }
    if (!onSaveRef.current) return;
    setSaveStatus("pending");
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    autoSaveTimerRef.current = setTimeout(async () => {
      const handler = onSaveRef.current;
      if (!handler) return;
      setSaveStatus("saving");
      try {
        await Promise.resolve(handler(slidesRef.current));
        setSaveStatus("saved");
      } catch {
        setSaveStatus("error");
      }
    }, 1000);
    return () => {
      if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    };
  }, [slides]);
  // Warn before leaving the page if a save is mid-flight or queued.
  useEffect(() => {
    function onBeforeUnload(e: BeforeUnloadEvent) {
      if (saveStatus === "pending" || saveStatus === "saving") {
        e.preventDefault();
        e.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [saveStatus]);

  // Canvas size is per-carousel — pulled from first slide's stored width/height (default 1080).
  const initialW = Number(initialSlides?.[0]?.width) || 1080;
  const initialH = Number(initialSlides?.[0]?.height) || 1080;
  const [canvasW, setCanvasW] = useState(initialW);
  const [canvasH, setCanvasH] = useState(initialH);
  const canvasSizeRef = useRef({ w: initialW, h: initialH });
  canvasSizeRef.current = { w: canvasW, h: canvasH };
  const [undoStack, setUndoStack] = useState<string[]>([]);
  const [redoStack, setRedoStack] = useState<string[]>([]);
  // Snapshot of the LAST committed canvas state — used to push to undo before each modification.
  const lastSnapshotRef = useRef<string | null>(null);
  // Tracks the current slide's background color so the toolbar swatch + picker
  // stays in sync (re-read on slide change / undo / template re-apply).
  const [bgColor, setBgColor] = useState<string>(
    typeof initialSlides?.[0]?.background === "string" ? initialSlides[0].background : "#FFFFFF"
  );

  // Template re-apply (header dropdown)
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [applyingTemplate, setApplyingTemplate] = useState(false);
  useEffect(() => {
    if (!onReapplyTemplate) return;
    api.listTemplates().then((res) => setTemplates(res.templates || [])).catch(() => {});
  }, [onReapplyTemplate]);

  async function handleTemplateChange(templateId: number) {
    if (!onReapplyTemplate || templateId === currentTemplateId) return;
    if (!canReapplyTemplate) {
      alert("이 캐러셀은 원본 데이터가 없어 템플릿을 바꿀 수 없습니다.\n캐러셀 만들기에서 다시 만들어 주세요.");
      return;
    }
    if (!confirm("다른 템플릿을 적용하면 현재 슬라이드가 새로 그려집니다. 진행할까요?")) return;
    setApplyingTemplate(true);
    try {
      const newSlides = await onReapplyTemplate(templateId);
      if (newSlides && fabricRef.current) {
        setSlides(newSlides);
        setCurrentSlideIndex(0);
        // Force a reload from the new state
        loadSlide(0);
        setUndoStack([]);
        setRedoStack([]);
      }
    } finally {
      setApplyingTemplate(false);
    }
  }

  // Initialize Fabric.js canvas
  useEffect(() => {
    let mounted = true;

    async function initCanvas() {
      const fabric = await getFabric();

      if (!mounted || !canvasRef.current) return;

      // Selection outlines are barely visible at the default 1-px blue. Make
      // them thicker and high-contrast (vivid sky-blue) so the user can always
      // tell which element is active, even against busy photos or dark
      // backgrounds. Matches the marquee-selection accent below for a single
      // cohesive selection language across the canvas.
      // Fabric v7 copies these props from ownDefaults onto each instance at
      // construction, so we have to mutate ownDefaults on FabricObject (and
      // its leaf subclasses) BEFORE any object is built. We also need to
      // re-apply on existing instances loaded via loadFromJSON below.
      const SELECTION_STYLE = {
        borderColor: "#3CC8FF",
        borderScaleFactor: 3.6,
        cornerColor: "#3CC8FF",
        cornerStrokeColor: "#FFFFFF",
        cornerSize: 13,
        transparentCorners: false,
      };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const fabricNs = fabric as any;
      for (const cls of [fabricNs.FabricObject, fabricNs.Object, fabricNs.Textbox, fabricNs.IText, fabricNs.Text, fabricNs.Rect, fabricNs.Circle, fabricNs.FabricImage, fabricNs.Image, fabricNs.ActiveSelection]) {
        if (cls?.ownDefaults) Object.assign(cls.ownDefaults, SELECTION_STYLE);
        if (cls?.prototype) Object.assign(cls.prototype, SELECTION_STYLE);
      }

      // Halo / double-line effect for the selection border. Fabric only draws
      // a single solid stroke, so we wrap the border draw method and turn on
      // canvas2d shadow before it strokes — that gives the sky-blue line a
      // soft outer glow without affecting the actual exported design. The
      // corner handles get the same treatment so they pop against any
      // background. Done once per page load — guarded with a flag to survive
      // HMR re-runs.
      const Base = fabricNs.FabricObject || fabricNs.Object;
      if (Base?.prototype && !Base.prototype.__haloPatched) {
        const origDrawBorders = Base.prototype.drawBorders;
        const origDrawControls = Base.prototype.drawControls;
        Base.prototype.drawBorders = function (
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ctx: any,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          options?: any,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          styleOverride?: any,
        ) {
          ctx.save();
          ctx.shadowColor = "rgba(60, 200, 255, 0.95)";
          ctx.shadowBlur = 19;
          const r = origDrawBorders.call(this, ctx, options, styleOverride);
          ctx.restore();
          return r;
        };
        Base.prototype.drawControls = function (
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ctx: any,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          styleOverride?: any,
        ) {
          ctx.save();
          ctx.shadowColor = "rgba(60, 200, 255, 0.9)";
          ctx.shadowBlur = 12;
          const r = origDrawControls.call(this, ctx, styleOverride);
          ctx.restore();
          return r;
        };
        Base.prototype.__haloPatched = true;
      }

      // Internal canvas runs at full design-space resolution PLUS a padding
      // band on every side. Object coordinates stay page-relative (0..pageW,
      // 0..pageH); a viewportTransform of (PAGE_PAD, PAGE_PAD) shifts the
      // whole render so the page sits inside the padded buffer. Selection
      // chrome on objects that spill past the page edge is therefore no
      // longer clipped — it can extend into the PAD band.
      const { w: initW, h: initH } = canvasSizeRef.current;
      const canvas = new fabric.Canvas(canvasRef.current, {
        width: initW + 2 * PAGE_PAD,
        height: initH + 2 * PAGE_PAD,
        // The editor surface is three concentric zones:
        //   1. page (1080×1350) — drawn by the pageBoundary rect, white by default
        //   2. PAD workspace — this backgroundColor, distinct mid-dark so the user
        //      sees where they can extend objects past the page edge
        //   3. app viewport (around the canvas) — --bg-app on the parent div
        backgroundColor: "#1E1E1E",
        selection: true,
        enableRetinaScaling: false,
        // Marquee-selection box (drag on empty area) — match the object-border
        // accent so the user always sees vivid feedback on what's being grabbed.
        selectionColor: "rgba(60,200,255,0.18)",
        selectionBorderColor: "#3CC8FF",
        selectionLineWidth: 2,
      });
      // Shift the camera so (0,0) in object space lands at (PAD, PAD) in
      // pixel space — i.e. the top-left of the page.
      canvas.setViewportTransform([zoomRef.current, 0, 0, zoomRef.current, PAGE_PAD, PAGE_PAD]);
      ensurePageBoundary(canvas, fabric, initW, initH, "#FFFFFF");
      const d = displayDims(initW, initH);
      const lower = canvas.lowerCanvasEl;
      const upper = canvas.upperCanvasEl;
      if (lower) {
        lower.style.width = `${d.w}px`;
        lower.style.height = `${d.h}px`;
      }
      if (upper) {
        upper.style.width = `${d.w}px`;
        upper.style.height = `${d.h}px`;
      }
      const wrapper = canvas.wrapperEl;
      if (wrapper) {
        wrapper.style.width = `${d.w}px`;
        wrapper.style.height = `${d.h}px`;
      }

      fabricRef.current = canvas;
      // Expose the fabric canvas globally for E2E tests / debugging. Cheap,
      // harmless, and there's only ever one editor canvas on screen at a time.
      if (typeof window !== "undefined") {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).__editorCanvas = canvas;
      }

      // Page-edge overlay. The pageBoundary rect lives at the back of the
      // object stack so any opaque slide background (grid templates often have
      // a black rect covering the entire page) hides its stroke. Drawing the
      // outline directly on the 2D context after fabric finishes rendering
      // guarantees the page edge is always visible — and sits just outside the
      // page area so it never bleeds into the downloaded crop (toDataURL is
      // called with rect (PAD, PAD, w, h) and our stroke is at PAD-4..PAD).
      canvas.on("after:render", () => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const c = canvas as any;
        if (c.__suppressPageOutline) return;
        const pb = c.__pageBoundary;
        const ctx = canvas.lowerCanvasEl?.getContext("2d");
        if (!pb || !ctx) return;
        const z = zoomRef.current;
        const bufW = canvas.getWidth();
        const bufH = canvas.getHeight();
        // Page rect in buffer coords (where the page actually rendered).
        const pageX0 = PAGE_PAD, pageY0 = PAGE_PAD;
        const pageW = pb.width * z, pageH = pb.height * z;
        const pageX1 = pageX0 + pageW, pageY1 = pageY0 + pageH;

        // 1. Mask the out-of-page area with the workspace bg so any content
        //    extending past the page edge gets erased — this is what makes
        //    out-of-page objects fade to "outline only". Clip via evenodd so
        //    we only paint outside the page rect; inside (the export area)
        //    stays untouched.
        ctx.save();
        ctx.beginPath();
        ctx.rect(0, 0, bufW, bufH);
        ctx.rect(pageX0, pageY0, pageW, pageH);
        ctx.clip("evenodd");
        ctx.fillStyle = "#1E1E1E";
        ctx.fillRect(0, 0, bufW, bufH);

        // 2. Within the same outside-page clip, draw a dashed bbox outline
        //    for each object that pokes past the page edge — so the user
        //    still sees where these objects sit.
        //    fabric's getBoundingRect returns object-space coords (no
        //    viewportTransform applied), so we project to buffer coords by
        //    hand using zoom + PAD.
        ctx.strokeStyle = "#3CC8FF";
        ctx.lineWidth = 2;
        for (const obj of canvas.getObjects()) {
          if (obj === pb) continue;
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const o = obj as any;
          if (o.excludeFromExport) continue;
          const r = o.getBoundingRect();
          const bx = r.left * z + PAGE_PAD;
          const by = r.top * z + PAGE_PAD;
          const bw = r.width * z;
          const bh = r.height * z;
          const fullyInside =
            bx >= pageX0 && by >= pageY0 &&
            bx + bw <= pageX1 && by + bh <= pageY1;
          if (!fullyInside) ctx.strokeRect(bx, by, bw, bh);
        }
        ctx.restore();

        // 3. Page-edge stroke. Sits just outside the page at PAD-4..PAD so
        //    the export crop (PAD..PAD+pageW) skips it.
        ctx.save();
        ctx.strokeStyle = "#3CC8FF";
        ctx.lineWidth = 4;
        ctx.strokeRect(PAGE_PAD - 2, PAGE_PAD - 2, pageW + 4, pageH + 4);
        ctx.restore();
      });

      // Force the vivid red selection style onto every object that lands on
      // the canvas — fabric copies these props from class defaults onto each
      // instance at construction, so just patching prototype/ownDefaults isn't
      // enough for objects already loaded from JSON.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const applySelectionStyle = (obj: any) => {
        if (!obj) return;
        for (const [k, v] of Object.entries(SELECTION_STYLE)) obj.set(k, v);
      };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      canvas.on("object:added", (e: any) => applySelectionStyle(e?.target));

      // Event listeners.
      // We DO NOT null out selectedTextRange on selection events — the panel
      // inputs steal focus from the canvas and may make fabric fire
      // selection:cleared, which would otherwise wipe the user's drag range
      // before the input's onChange runs. Instead the range is owned by the
      // text-editing events below, and is also cleared whenever we switch to a
      // different object (handled inline).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const onSelectionChange = (e: { selected?: any[] }) => {
        // For multi-select fabric reports each member in e.selected[]. The
        // PropertyPanel needs the ActiveSelection wrapper (with `_objects`)
        // to count member images for batch actions like parallel cutout.
        // Use canvas.getActiveObject() so we get the wrapper when >1 items
        // are selected, or the single item otherwise.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const obj: any = canvas.getActiveObject() || e.selected?.[0] || null;
        // If we moved to a different object, the previous textRange no longer
        // applies. Compare against the previous selectedObject via ref to avoid
        // stale closures.
        const prev = selectedObjectIdRef.current;
        const curId = obj ? (obj.__uid__ ||= Math.random().toString(36).slice(2)) : null;
        if (prev !== curId) setSelectedTextRange(null);
        selectedObjectIdRef.current = curId;
        setSelectedObject(obj);
      };
      canvas.on("selection:created", onSelectionChange);
      canvas.on("selection:updated", onSelectionChange);
      canvas.on("selection:cleared", () => {
        selectedObjectIdRef.current = null;
        // Keep range a bit longer so panel onChange handlers still see it.
        // The next selection:created (if any) will reset it via id check.
        setSelectedObject(null);
      });
      // Before any drag/resize commits, the LAST snapshot is the "before" state.
      // Push it onto undo, then take a new snapshot of the (now modified) canvas.
      canvas.on("object:modified", () => {
        clearSnapGuides();
        commitUndo();
        saveCurrentSlide();
      });

      // ── Snap-to-align while dragging ─────────────────────────────────────
      // On mouse drag, nudge the moving object so its left/center/right (and
      // top/center/bottom) line up with the canvas edges/center or another
      // object's edges/center when within SNAP_THRESHOLD. Draws thin pink
      // guide lines at the snap positions and removes them when the drag ends.
      //
      // Threshold is in fabric/canvas coordinates (full design space e.g.
      // 1080×1080) — CSS shrinks the visible canvas to ~540px, so each
      // canvas-px is ~½ display-px. 16 canvas-px ≈ 8 display-px, a snap window
      // wide enough to actually "catch" while dragging with a normal hand.
      const SNAP_THRESHOLD = 16;
      const GUIDE_COLOR = "#FF3B6A";
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const snapGuides: any[] = [];

      function clearSnapGuides() {
        if (snapGuides.length === 0) return;
        for (const g of snapGuides) canvas.remove(g);
        snapGuides.length = 0;
        canvas.requestRenderAll();
      }

      function addGuide(x1: number, y1: number, x2: number, y2: number) {
        const line = new fabric.Line([x1, y1, x2, y2], {
          stroke: GUIDE_COLOR,
          strokeWidth: 1,
          selectable: false,
          evented: false,
          excludeFromExport: true,
          hoverCursor: "default",
        });
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (line as any).__snapGuide = true;
        canvas.add(line);
        canvas.bringObjectToFront(line);
        snapGuides.push(line);
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      canvas.on("object:moving", (e: any) => {
        const obj = e?.target;
        if (!obj) return;
        // ActiveSelection (multi-drag) has compound origin behavior we don't
        // want to wrestle with; skip snapping in that case.
        const t = (obj.type || "").toLowerCase();
        if (t === "activeselection" || t === "group") return;

        clearSnapGuides();

        // axis-aligned bbox in canvas coords (handles scale/rotation)
        const r = obj.getBoundingRect();
        const cw = canvas.getWidth();
        const ch = canvas.getHeight();

        const movX = { left: r.left, center: r.left + r.width / 2, right: r.left + r.width };
        const movY = { top: r.top, center: r.top + r.height / 2, bottom: r.top + r.height };

        // Build target lists from canvas + every other object on the canvas
        const others = canvas.getObjects().filter(
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (o: any) => o !== obj && !o.__snapGuide && o.visible !== false,
        );

        const targetsX: number[] = [0, cw / 2, cw];
        const targetsY: number[] = [0, ch / 2, ch];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        for (const o of others as any[]) {
          const ob = o.getBoundingRect();
          targetsX.push(ob.left, ob.left + ob.width / 2, ob.left + ob.width);
          targetsY.push(ob.top, ob.top + ob.height / 2, ob.top + ob.height);
        }

        // Find the smallest snap delta per axis across all (mov ref × target) pairs.
        type Best = { delta: number; target: number };
        let bestX: Best | null = null;
        let bestY: Best | null = null;
        for (const target of targetsX) {
          for (const refKey of ["left", "center", "right"] as const) {
            const dist = target - movX[refKey];
            if (Math.abs(dist) <= SNAP_THRESHOLD && (bestX == null || Math.abs(dist) < Math.abs(bestX.delta))) {
              bestX = { delta: dist, target };
            }
          }
        }
        for (const target of targetsY) {
          for (const refKey of ["top", "center", "bottom"] as const) {
            const dist = target - movY[refKey];
            if (Math.abs(dist) <= SNAP_THRESHOLD && (bestY == null || Math.abs(dist) < Math.abs(bestY.delta))) {
              bestY = { delta: dist, target };
            }
          }
        }

        if (bestX) {
          obj.set({ left: obj.left + bestX.delta });
          addGuide(bestX.target, 0, bestX.target, ch);
        }
        if (bestY) {
          obj.set({ top: obj.top + bestY.delta });
          addGuide(0, bestY.target, cw, bestY.target);
        }

        if (bestX || bestY) {
          obj.setCoords();
          canvas.requestRenderAll();
        }
      });

      canvas.on("mouse:up", () => clearSnapGuides());

      // Track character-level selection inside textboxes so the property panel
      // can apply styles to just the user's drag range. The range is captured to
      // state so it survives text:editing:exited (which fabric fires when focus
      // moves to a panel input — otherwise the drag selection would be lost).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const refreshSelection = (e: any) => {
        const t = e?.target || canvas.getActiveObject();
        if (t) {
          // Fabric stores `type` on the prototype; a plain spread drops it.
          // Re-attach the keys the property panel reads + give a fresh ref so
          // React re-renders even when the underlying fabric object is the same.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const snap: any = { ...t };
          snap.type = t.type;
          snap.text = t.text;
          snap.fill = t.fill;
          snap.fontSize = t.fontSize;
          snap.fontWeight = t.fontWeight;
          snap.fontStyle = t.fontStyle;
          snap.fontFamily = t.fontFamily;
          snap.textAlign = t.textAlign;
          snap.lineHeight = t.lineHeight;
          snap.isEditing = t.isEditing;
          snap.selectionStart = t.selectionStart;
          snap.selectionEnd = t.selectionEnd;
          // Keep references back to the fabric instance so range-mode mutations
          // still work when canvas.getActiveObject() momentarily returns null
          // (e.g. while a panel input is focused).
          snap.getSelectionStyles = t.getSelectionStyles?.bind(t);
          snap.setSelectionStyles = t.setSelectionStyles?.bind(t);
          snap.set = t.set?.bind(t);
          snap.__fabricRef = t;
          setSelectedObject(snap);
        }
        if (t && (t.type === "textbox" || t.type === "Textbox")) {
          const start = t.selectionStart ?? 0;
          const end = t.selectionEnd ?? 0;
          if (end > start) {
            setSelectedTextRange({ start, end });
          } else if (t.isEditing) {
            // Collapsed cursor inside editing — user clicked into text without dragging
            setSelectedTextRange(null);
          }
          // else: not editing (focus left canvas) — KEEP prior range
        }
      };
      canvas.on("text:selection:changed", refreshSelection);
      canvas.on("text:editing:entered", refreshSelection);
      canvas.on("text:editing:exited", refreshSelection);

      // Fabric v7 doesn't always auto-enter editing on dblclick when the textbox
      // already has selectable=true but isn't yet active. Force it so the user
      // can drag-select characters and apply per-range styles. Also: double-
      // click on an image enters crop mode (see enterCropMode below).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      canvas.on("mouse:dblclick", (e: any) => {
        const t = e?.target;
        if (!t) return;
        const isTextbox = t.type === "textbox" || t.type === "Textbox";
        const isImage = t.type === "image" || t.type === "FabricImage" || t.type === "fabricimage";
        if (isImage && t.selectable !== false) {
          enterCropMode(t);
          return;
        }
        if (!isTextbox || t.editable === false) return;
        if (!t.isEditing && typeof t.enterEditing === "function") {
          t.enterEditing();
          canvas.requestRenderAll?.();
        }
      });

      // While in crop mode: clicking anywhere that isn't the auxiliary crop
      // rect commits the crop (matches the user's "OK or click outside" UX).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      canvas.on("mouse:down", (e: any) => {
        const aux = cropAuxRef.current;
        if (!aux) return;
        // Click on the aux rect itself (or its controls) — keep editing.
        if (e?.target === aux) return;
        // Click elsewhere → commit. Defer one tick so fabric finishes its own
        // pointer-down handling first (otherwise the new selection fires
        // before we tear down the aux rect).
        setTimeout(() => commitCrop(), 0);
      });

      // Load initial slide
      loadSlide(0);
    }

    initCanvas();

    return () => {
      mounted = false;
      if (fabricRef.current) {
        fabricRef.current.dispose();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveCurrentSlide = useCallback(() => {
    const canvas = fabricRef.current;
    if (!canvas) return;

    const json = canvas.toJSON();
    const { w, h } = canvasSizeRef.current;
    // The user-visible slide background lives on the page-boundary rect now
    // (canvas.backgroundColor paints the gutter). Pull its fill back into the
    // top-level `background` field so save/load round-trips stay the same
    // shape as before this refactor — old slides still load and look right.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const pb = (canvas as any).__pageBoundary;
    const pageFill = typeof pb?.fill === "string" ? pb.fill : (json as { background?: string }).background;
    // Read the destination index from the ref so a keyboard handler that
    // was registered at mount (stale closure) still writes the canvas back
    // to the CURRENTLY selected slide — otherwise Ctrl+D overwrites slide 0
    // every time, no matter which page the user has clicked.
    const idx = currentSlideIndexRef.current;
    setSlides((prev) => {
      const updated = [...prev];
      updated[idx] = {
        ...json,
        background: pageFill,
        version: "6.0.0",
        width: w,
        height: h,
      };
      slidesRef.current = updated;
      return updated;
    });
  }, []);

  function loadSlide(index: number) {
    const canvas = fabricRef.current;
    // Always read from the ref so a load triggered immediately after a
    // setSlides (e.g. duplicateSlide / removeSlide) reflects the new array.
    const currentSlides = slidesRef.current;
    if (!canvas || !currentSlides[index]) return;

    const slideData = currentSlides[index];

    // Slide data may be in two formats:
    //   (a) Our custom format from /api/carousels/render — lowercase types: "textbox", "image", "rect"
    //   (b) Fabric's own toJSON() output (after saveCurrentSlide) — PascalCase: "Textbox", "FabricImage", "Rect"
    // (b) is round-trippable via canvas.loadFromJSON, but (a) needs manual reconstruction.
    const looksFabric = (slideData.objects || []).some(
      (o) => typeof o.type === "string" && /^[A-Z]/.test(o.type)
    );

    canvas.clear();
    const slideBg = slideData.background || "#FFFFFF";
    const bgFill = typeof slideBg === "string" ? slideBg : "#FFFFFF";
    setBgColor(bgFill);

    if (looksFabric) {
      // Some legacy slides were saved with a canvas-level clipPath baked into
      // their JSON (left over from a thumbnail-renderer round-trip). When that
      // clip is restored via loadFromJSON it crops the whole editor view to a
      // sub-rectangle of the page, hiding most of the content. Strip it.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const cleanData = { ...(slideData as any), clipPath: null };
      // Fabric round-trip path
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (canvas as any).loadFromJSON(cleanData).then(async () => {
        // loadFromJSON reapplies the dimensions / backgroundColor / viewport
        // transform that were baked into the saved JSON — i.e. page-sized
        // buffer, page-color gutter, identity transform. Re-establish our
        // padded workspace from scratch every time:
        const { w: pageW, h: pageH } = canvasSizeRef.current;
        canvas.setDimensions({ width: pageW + 2 * PAGE_PAD, height: pageH + 2 * PAGE_PAD });
        applyDisplayCss(canvas, pageW, pageH);
        canvas.backgroundColor = "#1E1E1E";  // workspace gutter — distinct from app bg
        canvas.setViewportTransform([zoomRef.current, 0, 0, zoomRef.current, PAGE_PAD, PAGE_PAD]);
        // Defensive: even if a future fabric version re-applies clipPath after
        // resolve, null it again so the editor view stays unclipped.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (canvas as any).clipPath = null;
        const fabric = await getFabric();
        ensurePageBoundary(canvas, fabric, pageW, pageH, bgFill);
        markBackdropObjects(canvas);
        canvas.renderAll();
        lastSnapshotRef.current = JSON.stringify(canvas.toJSON());
      });
      return;
    }

    // Manual reconstruction path — clear() removed the page boundary too;
    // put it back at the start so subsequent adds layer above the page.
    {
      const { w: pageW, h: pageH } = canvasSizeRef.current;
      // Defensive: make sure the buffer still has the padding around the
      // page. setCanvasSize already does this on size changes, but loads
      // that come through without a setCanvasSize call (initial mount on
      // a different-sized template) need it too.
      canvas.setDimensions({ width: pageW + 2 * PAGE_PAD, height: pageH + 2 * PAGE_PAD });
      applyDisplayCss(canvas, pageW, pageH);
    }
    canvas.backgroundColor = "#1E1E1E";  // workspace gutter — distinct from app bg — page is drawn by the boundary rect
    canvas.setViewportTransform([1, 0, 0, 1, PAGE_PAD, PAGE_PAD]);

    // Canvas runs at design-space resolution internally; CSS shrinks for display.
    // Saved coords are already in design space — no scaling for textbox/rect/circle.
    const scale = 1;
    // For images, the source slide may have been authored at a different size
    // (e.g. /api/carousels/render produces 1080×1080). Map proportionally.
    const sourceW = Number(slideData.width) || 1080;
    const sourceH = Number(slideData.height) || 1080;

    // Add objects (sequentially so z-order matches the source array)
    (async () => {
      const fabric = await getFabric();
      // Put the page boundary in first so every reconstructed object lands
      // above it. (canvas.clear() above wiped the prior boundary.)
      ensurePageBoundary(canvas, fabric, canvasSizeRef.current.w, canvasSizeRef.current.h, bgFill);
      for (const obj of slideData.objects || []) {
        if (obj.type === "textbox") {
          const textbox = new fabric.Textbox(obj.text || "", {
            left: (obj.left || 0) * scale,
            top: (obj.top || 0) * scale,
            width: (obj.width || 400) * scale,
            fontSize: (obj.fontSize || 24) * scale,
            fontFamily: obj.fontFamily || "sans-serif",
            fontWeight: obj.fontWeight || "normal",
            fill: obj.fill || "#000000",
            textAlign: (obj.textAlign as "left" | "center" | "right" | "justify") || "left",
            lineHeight: (obj.lineHeight as number) || 1.4,
            originX: "left",
            originY: "top",
          });
          // Drop shadow string from renderer (Fabric accepts CSS-like syntax)
          if (typeof obj.shadow === "string") {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (textbox as any).set("shadow", obj.shadow);
          }
          canvas.add(textbox);
        } else if (obj.type === "rect") {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          let fill: any = obj.fill || "#E0E0E0";
          // Backend renderer may emit a gradient fill spec instead of a hex.
          // Convert it into a fabric.Gradient instance, scaling coords to display.
          if (fill && typeof fill === "object" && fill.type === "linear" && Array.isArray(fill.colorStops)) {
            const c = fill.coords || {};
            fill = new fabric.Gradient({
              type: "linear",
              coords: {
                x1: (c.x1 || 0) * scale,
                y1: (c.y1 || 0) * scale,
                x2: (c.x2 || 0) * scale,
                y2: (c.y2 || 0) * scale,
              },
              colorStops: fill.colorStops,
            });
          }
          const rect = new fabric.Rect({
            left: (obj.left || 0) * scale,
            top: (obj.top || 0) * scale,
            width: (obj.width || 200) * scale,
            height: (obj.height || 200) * scale,
            fill,
            rx: 0,
            ry: 0,
            originX: "left",
            originY: "top",
            selectable: obj.selectable !== false,
            evented: obj.selectable !== false,
          });
          canvas.add(rect);
        } else if (obj.type === "circle") {
          const circle = new fabric.Circle({
            left: (obj.left || 0) * scale,
            top: (obj.top || 0) * scale,
            radius: ((obj.width || 200) / 2) * scale,
            fill: obj.fill || "#E0E0E0",
          });
          canvas.add(circle);
        } else if (obj.type === "image" && typeof obj.src === "string") {
          try {
            const proxied = proxiedImageUrl(obj.src);
            const img = await fabric.FabricImage.fromURL(proxied, { crossOrigin: "anonymous" });

            // Map source design-space coords to current PAGE dims (not the
            // padded buffer). Object coords are page-relative (0..pageW), and
            // viewportTransform already translates them by PAGE_PAD at render
            // time — multiplying by canvas.getWidth() (= pageW + 2·PAGE_PAD)
            // expands every coordinate by ~2.1× and pushes grid cells past
            // the page edge. Use the page size for the ratio so a 1:1 design
            // hands back the original coords (sourceW == pageW → ratio == 1).
            const cW = canvas.getWidth();
            const cH = canvas.getHeight();
            const pageWLocal = cW - 2 * PAGE_PAD;
            const pageHLocal = cH - 2 * PAGE_PAD;
            const ratioX = pageWLocal / sourceW;
            const ratioY = pageHLocal / sourceH;
            const targetL = (obj.left || 0) * ratioX;
            const targetT = (obj.top || 0) * ratioY;
            const targetW = (obj.width || sourceW) * ratioX;
            const targetH = (obj.height || sourceH) * ratioY;

            const fw = img.width || targetW;
            const fh = img.height || targetH;

            // Preserve the photo's natural aspect ratio. The renderer hands us a
            // target box (e.g. a grid cell) whose aspect rarely matches the user-
            // picked photo's — independent scaleX/Y would squash portraits into
            // squares. Use a `cover` fit (uniform scale + center crop via clipPath)
            // so the slot is fully filled at the correct ratio.
            const coverScale = Math.max(targetW / fw, targetH / fh);
            const renderedW = fw * coverScale;
            const renderedH = fh * coverScale;
            const offsetL = targetL + (targetW - renderedW) / 2;
            const offsetT = targetT + (targetH - renderedH) / 2;

            // Skip the clip when the rendered size already fits inside the slot —
            // happens with decoration PNGs whose size is authored to match the
            // image's natural aspect ratio, so there's nothing to crop.
            const needsClip = renderedW > targetW + 0.5 || renderedH > targetH + 0.5;

            img.set({
              originX: "left",
              originY: "top",
              left: offsetL,
              top: offsetT,
              scaleX: coverScale,
              scaleY: coverScale,
              opacity: typeof obj.opacity === "number" ? obj.opacity : 1,
            });
            // Propagate the backend-supplied marker (e.g. {kind:"user_image"})
            // so the auto-lock pass below and downstream UI can recognize photos
            // the user picked in step 2 and let them be edited.
            //
            // Stash the slot's design coords + the auto-fit result.
            // handleSave compares them to detect user drag/scale and, when
            // unchanged, persists the canonical slot coords instead of the
            // cover-fit offset — without this, fabric's natural-size scaling
            // gets baked into the DB and grid cells drift off-canvas after a
            // mount cycle (cover-fit applied a second time on top of the
            // already-fitted left/width). See editor/[id]/page.tsx handleSave.
            //
            // Prefer the backend-supplied _slotL/T/W/H when present — those are
            // the canonical design-space coords from the renderer. obj.left/top
            // can already be the fitted (drifted) values if this carousel was
            // saved by a pre-fix editor session, so we'd stash the drift.
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const backendData: any = obj.data || {};
            const slotL = typeof backendData._slotL === "number" ? backendData._slotL : targetL;
            const slotT = typeof backendData._slotT === "number" ? backendData._slotT : targetT;
            const slotW = typeof backendData._slotW === "number" ? backendData._slotW : targetW;
            const slotH = typeof backendData._slotH === "number" ? backendData._slotH : targetH;
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (img as any).data = {
              ...backendData,
              _slotL: slotL,
              _slotT: slotT,
              _slotW: slotW,
              _slotH: slotH,
              _autoLeft: offsetL,
              _autoTop: offsetT,
              _autoScale: coverScale,
            };
            if (needsClip) {
              // absolutePositioned: clipPath stays in canvas coords so the image
              // can be repositioned within the slot ("object-position" equivalent)
              // without dragging the clip along.
              // originX/Y must be "left"/"top" — fabric's default Rect origin is
              // "center", which would center the clip rect on (targetL, targetT)
              // and only expose the slot's bottom-right quadrant.
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (img as any).clipPath = new fabric.Rect({
                left: targetL,
                top: targetT,
                width: targetW,
                height: targetH,
                originX: "left",
                originY: "top",
                absolutePositioned: true,
                selectable: false,
                evented: false,
              });
            }
            canvas.add(img);
            img.setCoords();
            // User-picked photos (from step 2) stay interactive — the user has
            // to be able to move/resize/replace them. Other full-bleed images
            // (template backgrounds, fetched stock photos) still get auto-locked
            // so marquee selection still works on the foreground.
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const imgData = (img as any).data;
            const isUserPhoto = imgData?.kind === "user_image" || imgData?.kind === "user_item_image";
            if (!isUserPhoto && targetL <= 1 && targetT <= 1 && targetW >= cW * 0.95 && targetH >= cH * 0.95) {
              canvas.sendObjectToBack(img);
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (img as any).set({ selectable: false, evented: false, hoverCursor: "default" });
            } else if (imgData?.kind === "user_image") {
              // Single-photo slides: push the full-bleed user photo to the back
              // so text/decorations layer over it, but keep it interactive.
              // Grid cells (kind === "user_item_image") must NOT go to the back —
              // the layout's full-canvas background image would sit on top of
              // them and the user's cell pick disappears off-screen visually.
              canvas.sendObjectToBack(img);
            }
            canvas.requestRenderAll();

          } catch (err) {
            console.warn("[canvas] image load failed", obj.src, err);
          }
        }
      }
      // Any object whose bounding box covers most of the canvas is treated as
      // a backdrop (full-bleed photo, gradient overlay, background tint) and
      // made non-interactive so a click-drag on the canvas starts a marquee
      // selection instead of grabbing the backdrop. Real foreground content
      // (text, decorations, grid cells) stays clickable.
      markBackdropObjects(canvas);
      canvas.renderAll();
      // After load completes, capture this as the baseline for future undos
      lastSnapshotRef.current = JSON.stringify(canvas.toJSON());
    })();
  }

  // ─── Image crop ─────────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async function enterCropMode(img: any) {
    const canvas = fabricRef.current;
    if (!canvas) return;
    // Cancel any prior crop session before starting a new one.
    if (cropAuxRef.current) cancelCrop();

    const fabric = await getFabric();

    // Start the crop rect at the image's currently visible bounds. If the
    // image already has an absolutePositioned clipPath (e.g. from cover-fit
    // or a prior crop) we use those bounds so the user resumes from the
    // current visible region. Otherwise fall back to the image's bbox.
    let startL: number, startT: number, startW: number, startH: number;
    const clip = img.clipPath;
    if (clip && clip.absolutePositioned) {
      startL = clip.left || 0;
      startT = clip.top || 0;
      startW = (clip.width || 0) * (clip.scaleX || 1);
      startH = (clip.height || 0) * (clip.scaleY || 1);
    } else {
      const br = img.getBoundingRect();
      startL = br.left;
      startT = br.top;
      startW = br.width;
      startH = br.height;
    }

    const aux = new fabric.Rect({
      left: startL,
      top: startT,
      width: startW,
      height: startH,
      originX: "left",
      originY: "top",
      fill: "rgba(0, 122, 255, 0.10)",
      stroke: "#007AFF",
      strokeWidth: 2,
      strokeDashArray: [6, 4],
      cornerSize: 14,
      cornerColor: "#007AFF",
      cornerStyle: "circle",
      transparentCorners: false,
      hasBorders: true,
      hasControls: true,
      lockRotation: true,
      lockSkewingX: true,
      lockSkewingY: true,
      selectable: true,
      evented: true,
      excludeFromExport: true, // not part of the design — never saved
    });
    aux.setControlsVisibility?.({ mtr: false });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (aux as any).__cropAux = true;

    // Build 4 dim rects (top / bottom / left / right of the aux box) to dim
    // the canvas area that will be cropped away. They live below the aux rect
    // in z-order so the crop region itself stays at full brightness.
    const cw = canvas.getWidth();
    const ch = canvas.getHeight();
    const dimFill = "rgba(0,0,0,0.45)";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mkDim = () => new (fabric as any).Rect({
      left: 0, top: 0, width: 0, height: 0,
      originX: "left", originY: "top",
      fill: dimFill,
      stroke: undefined,
      selectable: false,
      evented: false,
      hoverCursor: "default",
      excludeFromExport: true,
      hasBorders: false,
      hasControls: false,
    });
    const dimT = mkDim(), dimB = mkDim(), dimL = mkDim(), dimR = mkDim();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    [dimT, dimB, dimL, dimR].forEach((d: any) => { d.__cropDim = true; });
    cropDimsRef.current = [dimT, dimB, dimL, dimR];

    const syncDims = () => {
      const left = aux.left ?? 0;
      const top = aux.top ?? 0;
      const w = (aux.width || 0) * (aux.scaleX || 1);
      const h = (aux.height || 0) * (aux.scaleY || 1);
      dimT.set({ left: 0, top: 0, width: cw, height: Math.max(0, top) });
      dimB.set({ left: 0, top: top + h, width: cw, height: Math.max(0, ch - top - h) });
      dimL.set({ left: 0, top: top, width: Math.max(0, left), height: Math.max(0, h) });
      dimR.set({ left: left + w, top: top, width: Math.max(0, cw - left - w), height: Math.max(0, h) });
      [dimT, dimB, dimL, dimR].forEach((d) => d.setCoords());
    };

    // Add dim rects first (back layer), then aux on top
    for (const d of [dimT, dimB, dimL, dimR]) canvas.add(d);
    canvas.add(aux);
    canvas.bringObjectToFront?.(aux);
    canvas.setActiveObject(aux);
    syncDims();

    // Live preview: while the user drags / resizes the aux rect, mirror its
    // bounds onto the image's clipPath so they see the crop result in real
    // time. We snapshot the pre-crop clipPath first so Esc can restore it.
    cropOrigClipRef.current = img.clipPath ?? null;
    // Start the image already clipped to the aux bounds (so identity drag is a no-op).
    img.clipPath = new fabric.Rect({
      left: startL, top: startT, width: startW, height: startH,
      originX: "left", originY: "top",
      absolutePositioned: true,
      selectable: false, evented: false,
    });
    img.dirty = true;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const syncAll = () => {
      const r = aux;
      const w = (r.width || 0) * (r.scaleX || 1);
      const h = (r.height || 0) * (r.scaleY || 1);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const clip = (img as any).clipPath;
      if (clip) {
        clip.set({ left: r.left, top: r.top, width: w, height: h, scaleX: 1, scaleY: 1 });
        img.dirty = true;
      }
      syncDims();
      canvas.requestRenderAll();
    };
    aux.on("moving", syncAll);
    aux.on("scaling", syncAll);
    aux.on("modified", syncAll);

    canvas.requestRenderAll();
    cropAuxRef.current = aux;
    cropImgRef.current = img;
    setCropping(true);
  }

  async function commitCrop() {
    const canvas = fabricRef.current;
    const aux = cropAuxRef.current;
    const img = cropImgRef.current;
    if (!canvas || !aux || !img) return;
    pushUndo();

    // Convert the absolute-positioned live-preview clipPath into fabric's
    // native source crop (cropX/cropY + width/height). The clipPath approach
    // is only good for "fill this slot" templates — the clip stays in canvas
    // coords, so dragging the image after crop would scroll pixels through a
    // fixed window instead of moving the cropped piece as one unit. Baking
    // the crop into cropX/cropY collapses the image's bounding box to exactly
    // the visible piece, so it behaves like any other movable object.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const imgAny = img as any;
    const auxL = aux.left || 0;
    const auxT = aux.top || 0;
    const auxW = (aux.width || 0) * (aux.scaleX || 1);
    const auxH = (aux.height || 0) * (aux.scaleY || 1);
    const sx = imgAny.scaleX || 1;
    const sy = imgAny.scaleY || 1;
    const imgL = imgAny.left || 0;
    const imgT = imgAny.top || 0;
    const existCropX = imgAny.cropX || 0;
    const existCropY = imgAny.cropY || 0;
    const newCropX = existCropX + (auxL - imgL) / sx;
    const newCropY = existCropY + (auxT - imgT) / sy;
    const newWidth = auxW / sx;
    const newHeight = auxH / sy;
    imgAny.set({
      cropX: Math.max(0, newCropX),
      cropY: Math.max(0, newCropY),
      width: Math.max(1, newWidth),
      height: Math.max(1, newHeight),
      left: auxL,
      top: auxT,
      clipPath: null,
    });
    img.dirty = true;
    if (typeof img.setCoords === "function") img.setCoords();

    canvas.remove(aux);
    for (const d of cropDimsRef.current) canvas.remove(d);
    cropDimsRef.current = [];
    canvas.discardActiveObject();
    // Re-select the freshly-cropped image so the user can drag it immediately
    // — without this, they'd have to click the image again after every crop.
    canvas.setActiveObject(img);
    cropAuxRef.current = null;
    cropImgRef.current = null;
    cropOrigClipRef.current = null;
    setCropping(false);
    canvas.requestRenderAll();
    saveCurrentSlide();
  }

  function cancelCrop() {
    const canvas = fabricRef.current;
    const aux = cropAuxRef.current;
    const img = cropImgRef.current;
    if (!canvas || !aux) {
      setCropping(false);
      return;
    }
    // Restore the clipPath that existed before the user entered crop mode
    // so live-preview changes don't stick when they back out with Esc.
    if (img) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (img as any).clipPath = cropOrigClipRef.current;
      img.dirty = true;
    }
    canvas.remove(aux);
    for (const d of cropDimsRef.current) canvas.remove(d);
    cropDimsRef.current = [];
    canvas.discardActiveObject();
    cropAuxRef.current = null;
    cropImgRef.current = null;
    cropOrigClipRef.current = null;
    setCropping(false);
    canvas.requestRenderAll();
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function markBackdropObjects(canvas: any) {
    const cW = canvas.getWidth();
    const cH = canvas.getHeight();
    const canvasArea = cW * cH;
    const objs = canvas.getObjects();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    for (const o of objs as any[]) {
      const br = o.getBoundingRect();
      // Use the visible intersection with the canvas rect (not just the raw
      // bbox) so a cover-fit photo that extends past the top/bottom still
      // counts as a backdrop. Threshold 0.9 captures any object that fills
      // most of the visible area.
      const ix0 = Math.max(0, br.left);
      const iy0 = Math.max(0, br.top);
      const ix1 = Math.min(cW, br.left + br.width);
      const iy1 = Math.min(cH, br.top + br.height);
      const visibleArea = Math.max(0, ix1 - ix0) * Math.max(0, iy1 - iy0);
      if (visibleArea < canvasArea * 0.9) continue;
      const t = String(o.type || "").toLowerCase();
      // Only auto-lock obvious backdrop types. We leave Textbox / Group alone
      // so weird "huge text" or grouped designs aren't accidentally bricked.
      if (!["image", "fabricimage", "rect", "circle"].includes(t)) continue;
      // User-picked photos (marked by the backend renderer with
      // data.kind === "user_image" / "user_item_image") are kept editable —
      // they're the whole point of step 2 and the user expects to move/replace
      // them just like any other object.
      const k = o?.data?.kind;
      if (k === "user_image" || k === "user_item_image") continue;
      // Page boundary is already evented:false; skip to keep the marker clean.
      if (k === PAGE_BOUNDARY_KIND) continue;
      o.set({ selectable: false, evented: false, hoverCursor: "default" });
    }
  }

  function switchSlide(index: number) {
    saveCurrentSlide();
    setCurrentSlideIndex(index);
    loadSlide(index);
    setSelectedObject(null);
    // Per-slide undo history — clear when switching so Ctrl+Z doesn't pull
    // changes from a different slide into the current one.
    setUndoStack([]);
    setRedoStack([]);
  }

  function setCanvasSize(w: number, h: number) {
    const canvas = fabricRef.current;
    if (!canvas) return;
    // Snapshot current slide BEFORE resize so coords are saved at the previous size.
    const json = canvas.toJSON();
    const prevW = canvasSizeRef.current.w;
    const prevH = canvasSizeRef.current.h;

    setSlides((prev) => {
      const updated = prev.map((s, i) =>
        i === currentSlideIndex
          ? { ...json, version: "6.0.0", width: prevW, height: prevH }
          : { ...s, width: s.width || prevW, height: s.height || prevH }
      );
      return updated;
    });

    canvasSizeRef.current = { w, h };
    setCanvasW(w);
    setCanvasH(h);
    // Resize the pixel buffer to include the same PAD band on every side, then
    // re-apply the viewport translate (setDimensions resets the transform).
    canvas.setDimensions({ width: w + 2 * PAGE_PAD, height: h + 2 * PAGE_PAD });
    canvas.setViewportTransform([1, 0, 0, 1, PAGE_PAD, PAGE_PAD]);
    // Resize the page-boundary rect to track the new page size.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const pb = (canvas as any).__pageBoundary;
    if (pb) {
      pb.set({ width: w, height: h });
      pb.setCoords();
    }
    const d = displayDims(w, h);
    const lower = canvas.lowerCanvasEl;
    const upper = canvas.upperCanvasEl;
    if (lower) { lower.style.width = `${d.w}px`; lower.style.height = `${d.h}px`; }
    if (upper) { upper.style.width = `${d.w}px`; upper.style.height = `${d.h}px`; }
    if (canvas.wrapperEl) { canvas.wrapperEl.style.width = `${d.w}px`; canvas.wrapperEl.style.height = `${d.h}px`; }
    canvas.renderAll();
    // After resize the same slide is now "saved at the new size" for future saves.
    // Re-save with new dims so width/height reflect current canvas.
    setSlides((prev) => {
      const updated = [...prev];
      const cur = updated[currentSlideIndex];
      if (cur) updated[currentSlideIndex] = { ...cur, width: w, height: h };
      return updated;
    });
    lastSnapshotRef.current = JSON.stringify(canvas.toJSON());
  }

  function addSlide() {
    saveCurrentSlide();
    const newSlides = [...slides, createEmptySlide()];
    setSlides(newSlides);
    const newIndex = newSlides.length - 1;
    setCurrentSlideIndex(newIndex);
    loadSlide(newIndex);
  }

  function duplicateSlide() {
    // Snapshot the current fabric canvas back into slides BEFORE we splice,
    // otherwise unsaved edits on the live slide get lost. Use the ref-mirrored
    // index so a stale closure (e.g. keyboard handler bound at mount) can't
    // duplicate the wrong slide after the user clicked a different thumb.
    saveCurrentSlide();
    const idx = currentSlideIndexRef.current;
    setSlides((prev) => {
      if (idx < 0 || idx >= prev.length) return prev;
      const copy = JSON.parse(JSON.stringify(prev[idx]));
      const next = [...prev];
      next.splice(idx + 1, 0, copy);
      // Immediate ref sync so a follow-up loadSlide (next tick) reads
      // the updated array even though React hasn't committed yet.
      slidesRef.current = next;
      return next;
    });
    // Auto-jump to the newly-created duplicate so the user immediately sees
    // and can keep editing the copy — matches user expectation that "복제"
    // selects the new page.
    const newIdx = idx + 1;
    setCurrentSlideIndex(newIdx);
    currentSlideIndexRef.current = newIdx;
    setTimeout(() => loadSlide(newIdx), 0);
  }

  function removeSlide(index: number) {
    setSlides((prev) => {
      if (prev.length <= 1) return prev;
      const next = prev.filter((_, i) => i !== index);
      slidesRef.current = next;
      const newIndex = Math.min(currentSlideIndexRef.current, next.length - 1);
      if (newIndex !== currentSlideIndexRef.current) {
        setCurrentSlideIndex(newIndex);
        currentSlideIndexRef.current = newIndex;
      }
      setTimeout(() => loadSlide(newIndex), 0);
      return next;
    });
  }

  // Reorder slides via drag-and-drop in the bottom navigator.
  //   from       — current index of the dragged slide
  //   dropBefore — index in the ORIGINAL array where the slide should land
  //                (slots 0..length; e.g. dropBefore=length means drop at end)
  // The currentSlideIndex follows the moved slide so the user keeps editing
  // the same page they were on.
  function reorderSlides(from: number, dropBefore: number) {
    // Identity drop (in front of or behind itself) → no-op.
    if (dropBefore === from || dropBefore === from + 1) return;
    // Persist the live fabric canvas FIRST so a mid-edit reorder doesn't lose
    // the buffered changes on the slide being moved.
    saveCurrentSlide();
    setSlides((prev) => {
      if (from < 0 || from >= prev.length) return prev;
      const insertAt = dropBefore > from ? dropBefore - 1 : dropBefore;
      if (insertAt < 0 || insertAt > prev.length - 1) return prev;
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(insertAt, 0, moved);
      slidesRef.current = next;
      // Keep the user on the slide they were editing.
      const cur = currentSlideIndexRef.current;
      let newCur = cur;
      if (cur === from) newCur = insertAt;
      else if (from < cur && insertAt >= cur) newCur = cur - 1;
      else if (from > cur && insertAt <= cur) newCur = cur + 1;
      if (newCur !== cur) {
        setCurrentSlideIndex(newCur);
        currentSlideIndexRef.current = newCur;
      }
      return next;
    });
  }

  function addText() {
    const canvas = fabricRef.current;
    if (!canvas) return;

    getFabric().then((fabric) => {
      const textbox = new fabric.Textbox("텍스트 입력", {
        left: 100,
        top: 200,
        width: 340,
        fontSize: 18,
        fontFamily: "sans-serif",
        fill: "#1A1A1A",
      });
      canvas.add(textbox);
      canvas.setActiveObject(textbox);
      canvas.renderAll();
      saveCurrentSlide();
    });
  }

  function addRect() {
    const canvas = fabricRef.current;
    if (!canvas) return;

    getFabric().then((fabric) => {
      const rect = new fabric.Rect({
        left: 150,
        top: 150,
        width: 200,
        height: 200,
        fill: "#E0E0E0",
      });
      canvas.add(rect);
      canvas.setActiveObject(rect);
      canvas.renderAll();
      saveCurrentSlide();
    });
  }

  async function importPsd(file: File) {
    const canvas = fabricRef.current;
    if (!canvas) return;
    try {
      const fabric = await getFabric();
      const { readPsd } = await import("ag-psd");
      const buf = await file.arrayBuffer();
      const psd = readPsd(buf);
      const cw = canvas.getWidth();
      const ch = canvas.getHeight();
      // Scale PSD to fit the current canvas size
      const sx = cw / (psd.width || cw);
      const sy = ch / (psd.height || ch);
      const s = Math.min(sx, sy);

      pushUndo();
      let layerCount = 0;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const walk = async (layer: any) => {
        if (layer.hidden) return;
        // Group: recurse into children
        if (layer.children && layer.children.length > 0) {
          for (const child of layer.children) {
            await walk(child);
          }
          return;
        }
        const left = (layer.left || 0) * s;
        const top = (layer.top || 0) * s;
        const w = ((layer.right || 0) - (layer.left || 0)) * s;
        const h = ((layer.bottom || 0) - (layer.top || 0)) * s;
        if (w <= 0 || h <= 0) return;

        // Text layer → Textbox
        if (layer.text?.text) {
          const t = layer.text;
          const style = t.style || {};
          const fontSize = (style.fontSize || 24) * s;
          const tb = new fabric.Textbox(t.text, {
            left, top, width: w,
            fontSize,
            fontFamily: style.font?.name || "Pretendard",
            fontWeight: style.fauxBold || (style.fontSize && (style.fontSize as number) > 50) ? "700" : "400",
            fontStyle: style.fauxItalic ? "italic" : "normal",
            fill: rgbaFromPsd(style.fillColor) || "#000000",
            textAlign: (t.paragraphStyle?.justification === "center" ? "center"
              : t.paragraphStyle?.justification === "right" ? "right" : "left"),
            originX: "left",
            originY: "top",
          });
          canvas.add(tb);
          layerCount++;
          return;
        }
        // Raster layer → FabricImage from layer.canvas
        if (layer.canvas) {
          const dataUrl = (layer.canvas as HTMLCanvasElement).toDataURL("image/png");
          try {
            const img = await fabric.FabricImage.fromURL(dataUrl, { crossOrigin: "anonymous" });
            const fw = img.width || w;
            const fh = img.height || h;
            img.set({
              left, top,
              scaleX: w / fw,
              scaleY: h / fh,
              originX: "left",
              originY: "top",
              opacity: typeof layer.opacity === "number" ? layer.opacity / 255 : 1,
            });
            canvas.add(img);
            layerCount++;
          } catch (e) {
            console.warn("[psd] image layer load failed", layer.name, e);
          }
        }
      };

      // PSD layer tree is bottom-up in `children`, walk in reverse so z-order
      // matches Photoshop (bottom layer first → topmost last).
      const tree = psd.children || [];
      for (const root of tree) {
        await walk(root);
      }

      canvas.requestRenderAll();
      saveCurrentSlide();
      console.log(`[psd] imported ${layerCount} layers from ${file.name}`);
    } catch (err) {
      console.error("[psd] import failed", err);
      alert("PSD 가져오기 실패: " + (err instanceof Error ? err.message : String(err)));
    }
  }

  // Drag-and-drop image insertion. The canvas area listens for file drops,
  // showing a tinted overlay while a file is hovering over it. Same validation
  // + insertion logic as the toolbar's "이미지 추가" button.
  const [dragActive, setDragActive] = useState(false);
  const dragCounterRef = useRef(0);

  function onCanvasDragEnter(e: React.DragEvent<HTMLDivElement>) {
    if (!Array.from(e.dataTransfer.types || []).includes("Files")) return;
    e.preventDefault();
    dragCounterRef.current += 1;
    if (dragCounterRef.current === 1) setDragActive(true);
  }
  function onCanvasDragOver(e: React.DragEvent<HTMLDivElement>) {
    if (Array.from(e.dataTransfer.types || []).includes("Files")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  }
  function onCanvasDragLeave(e: React.DragEvent<HTMLDivElement>) {
    if (!Array.from(e.dataTransfer.types || []).includes("Files")) return;
    dragCounterRef.current = Math.max(0, dragCounterRef.current - 1);
    if (dragCounterRef.current === 0) setDragActive(false);
  }
  async function onCanvasDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    dragCounterRef.current = 0;
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length === 0) return;
    // Insert each dropped image in order — supports multi-file drop.
    for (const f of files) {
      await importImageFile(f);
    }
  }

  async function importImageFile(file: File) {
    const canvas = fabricRef.current;
    if (!canvas) return;
    // Accept jpg/jpeg/png/webp/jfif/pjpeg. Browser may report MIME for these as
    // image/jpeg, image/png, image/webp, image/pjpeg (jfif), or empty.
    const okMime = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/pjpeg"];
    const okExt = /\.(jpe?g|png|webp|jfif|pjpeg)$/i;
    if (file.type && !okMime.includes(file.type) && !okExt.test(file.name)) {
      alert("지원하지 않는 이미지 형식입니다. jpg, png, webp, jfif만 지원합니다.");
      return;
    }
    try {
      const fabric = await getFabric();
      // Read the file as a data URL — fabric can load any browser-decodable
      // raster format (incl. jfif) directly from a data URL.
      const dataUrl: string = await new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result || ""));
        r.onerror = () => reject(r.error || new Error("file read failed"));
        r.readAsDataURL(file);
      });
      pushUndo();
      const img = await fabric.FabricImage.fromURL(dataUrl, { crossOrigin: "anonymous" });
      // Fit the image inside the canvas with some breathing room (max 80% of
      // either dimension); preserve aspect ratio; center it.
      const cw = canvas.getWidth();
      const ch = canvas.getHeight();
      const iw = img.width || cw;
      const ih = img.height || ch;
      const maxW = cw * 0.8;
      const maxH = ch * 0.8;
      const scale = Math.min(1, maxW / iw, maxH / ih);
      const finalW = iw * scale;
      const finalH = ih * scale;
      img.set({
        originX: "left",
        originY: "top",
        left: Math.round((cw - finalW) / 2),
        top: Math.round((ch - finalH) / 2),
        scaleX: scale,
        scaleY: scale,
      });
      canvas.add(img);
      canvas.setActiveObject(img);
      canvas.requestRenderAll();
      saveCurrentSlide();
    } catch (err) {
      console.error("[importImage] failed", err);
      alert("이미지 추가 실패: " + (err instanceof Error ? err.message : String(err)));
    }
  }

  function addGradientOverlay() {
    const canvas = fabricRef.current;
    if (!canvas) return;
    getFabric().then((fabric) => {
      // Locate the highest text on the slide so the gradient starts above it.
      const objs = canvas.getObjects();
      let topmostTextY: number | null = null;
      for (const o of objs) {
        const t = String(o.type || "").toLowerCase();
        if (t === "textbox" || t === "i-text") {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const top = (o as any).top || 0;
          if (topmostTextY === null || top < topmostTextY) topmostTextY = top;
        }
      }
      const H = canvas.getHeight();
      const W = canvas.getWidth();
      const padding = Math.round(H * 0.05); // gradient starts this much above the first text
      const startY = topmostTextY !== null ? Math.max(0, topmostTextY - padding) : Math.round(H * 0.5);
      const height = H - startY;

      const gradient = new fabric.Gradient({
        type: "linear",
        coords: { x1: 0, y1: 0, x2: 0, y2: height },
        colorStops: [
          { offset: 0, color: "rgba(0,0,0,0)" },
          { offset: 0.55, color: "rgba(0,0,0,0.45)" },
          { offset: 1, color: "rgba(0,0,0,0.88)" },
        ],
      });

      const rect = new fabric.Rect({
        left: 0,
        top: startY,
        width: W,
        height: height,
        fill: gradient,
        selectable: true,
        evented: true,
        originX: "left",
        originY: "top",
      });
      canvas.add(rect);

      // Z-order: above all images, below all texts.
      // (Newly added objects sit on top; push back past any text objects.)
      const arr = canvas.getObjects();
      let lastTextIdx = -1;
      // find the LOWEST-index text so the gradient ends up just below it
      for (let i = 0; i < arr.length; i++) {
        if (arr[i] === rect) continue;
        const t = String(arr[i].type || "").toLowerCase();
        if (t === "textbox" || t === "i-text") {
          if (lastTextIdx === -1) lastTextIdx = i;
        }
      }
      if (lastTextIdx >= 0) {
        // Move backwards until we're at lastTextIdx
        let safety = 50;
        while (safety-- > 0 && arr.indexOf(rect) > lastTextIdx) {
          canvas.sendObjectBackwards(rect);
        }
      }

      canvas.setActiveObject(rect);
      canvas.renderAll();
      saveCurrentSlide();
    });
  }

  function addCircle() {
    const canvas = fabricRef.current;
    if (!canvas) return;

    getFabric().then((fabric) => {
      const circle = new fabric.Circle({
        left: 200,
        top: 200,
        radius: 80,
        fill: "#E0E0E0",
      });
      canvas.add(circle);
      canvas.setActiveObject(circle);
      canvas.renderAll();
      saveCurrentSlide();
    });
  }

  function deleteSelected() {
    const canvas = fabricRef.current;
    if (!canvas) return;

    const active = canvas.getActiveObject();
    if (!active) return;
    // Multi-selection (ActiveSelection) — fabric stores members in `_objects`.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const members: any[] = active._objects ? [...active._objects] : [active];
    pushUndo();
    canvas.discardActiveObject();
    members.forEach((m) => canvas.remove(m));
    canvas.renderAll();
    setSelectedObject(null);
    saveCurrentSlide();
  }

  // ─── Cutout (rembg background removal) ───
  // Track which fabric image is currently being processed so the panel can
  // disable the button + show a spinner state.
  const [cutoutBusy, setCutoutBusy] = useState(false);
  const [enhanceBusy, setEnhanceBusy] = useState(false);
  const [replaceBusy, setReplaceBusy] = useState(false);

  function _resolveOriginalSrc(src: string | null | undefined): string | null {
    if (!src) return null;
    // If src points at our backend proxy, peel the inner `url=` param so the
    // backend's cutout fetches the real source (cleaner cache key + smaller URL).
    try {
      const m = src.match(/\/api\/images\/proxy\?url=([^&]+)/);
      if (m) return decodeURIComponent(m[1]);
    } catch { /* ignore */ }
    return src;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function _imageMembersOf(active: any): any[] {
    if (!active) return [];
    // Multi-selection (ActiveSelection): fabric stores members in `_objects`.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const members: any[] = Array.isArray(active._objects) ? [...active._objects] : [active];
    return members.filter((m) =>
      m && (m.type === "image" || m.type === "FabricImage")
    );
  }

  async function cutoutSelectedImage(mode: "standard" | "generative" = "standard") {
    const canvas = fabricRef.current;
    if (!canvas || cutoutBusy) return;
    const active = canvas.getActiveObject();
    const imageMembers = _imageMembersOf(active);
    if (imageMembers.length === 0) return;

    setCutoutBusy(true);
    pushUndo();

    // Run all cutouts in parallel. fal.ai BiRefNet handles concurrent calls
    // fine; flux/evf-sam each become a separate inference request. Local
    // rembg fallback would serialize because Python GIL + single CPU model,
    // but in the common case (fal.ai) this is a real ~Nx speedup over
    // sequential per-image clicks.
    const results = await Promise.all(
      imageMembers.map(async (img) => {
        try {
          const currentSrc =
            (typeof img.getSrc === "function" ? img.getSrc() : null) ||
            img._originalElement?.src ||
            img.src ||
            null;
          const originUrl = _resolveOriginalSrc(currentSrc);
          if (!originUrl) return { img, ok: false, reason: "no-url" };
          const res = await api.cutoutImage({ source_url: originUrl, mode });
          const out = res.url; // relative `/api/images/...`, browser resolves
          if (typeof img.setSrc === "function") {
            await img.setSrc(proxiedImageUrl(out), { crossOrigin: "anonymous" });
          }
          img.dirty = true;
          return { img, ok: true };
        } catch (err) {
          return { img, ok: false, reason: err instanceof Error ? err.message : String(err) };
        }
      })
    );

    canvas.requestRenderAll();
    saveCurrentSlide();
    setSelectedObject(active ? { ...active } : null);
    setCutoutBusy(false);

    const failed = results.filter((r) => !r.ok);
    if (failed.length > 0) {
      const reasons = Array.from(new Set(failed.map((r) => r.reason).filter(Boolean))).slice(0, 2).join(", ");
      alert(`${failed.length}/${results.length}개 이미지 누끼 실패${reasons ? ` — ${reasons}` : ""}`);
    }
  }

  // AI super-resolution / detail enhance. Same shape as cutoutSelectedImage:
  // resolve each selected image's *original* source URL → POST to the
  // backend → swap the fabric image's src to the result. Parallel over the
  // selection so multi-select takes the same wall-clock as one image.
  async function enhanceSelectedImage(category: "food" | "landscape" | "portrait") {
    const canvas = fabricRef.current;
    if (!canvas || enhanceBusy) return;
    const active = canvas.getActiveObject();
    const imageMembers = _imageMembersOf(active);
    if (imageMembers.length === 0) return;

    setEnhanceBusy(true);
    pushUndo();

    const results = await Promise.all(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      imageMembers.map(async (img: any) => {
        try {
          const currentSrc =
            (typeof img.getSrc === "function" ? img.getSrc() : null) ||
            img._originalElement?.src ||
            img.src ||
            null;
          const originUrl = _resolveOriginalSrc(currentSrc);
          if (!originUrl) return { img, ok: false, reason: "no-url" };
          const res = await api.enhanceImage({ source_url: originUrl, category });
          if (typeof img.setSrc === "function") {
            await img.setSrc(proxiedImageUrl(res.url), { crossOrigin: "anonymous" });
          }
          img.dirty = true;
          return { img, ok: true };
        } catch (err) {
          return { img, ok: false, reason: err instanceof Error ? err.message : String(err) };
        }
      })
    );

    canvas.requestRenderAll();
    saveCurrentSlide();
    setSelectedObject(active ? { ...active } : null);
    setEnhanceBusy(false);

    const failed = results.filter((r) => !r.ok);
    if (failed.length > 0) {
      const reasons = Array.from(new Set(failed.map((r) => r.reason).filter(Boolean))).slice(0, 2).join(", ");
      alert(`${failed.length}/${results.length}개 이미지 화질 향상 실패${reasons ? ` — ${reasons}` : ""}`);
    }
  }

  // Swap the selected image's bitmap for a user-uploaded file. Preserves the
  // existing slot's position/scale/clip — only the underlying pixels change,
  // so a portrait swapped for a landscape still respects the slot's aspect.
  async function replaceSelectedImage(file: File) {
    const canvas = fabricRef.current;
    if (!canvas || replaceBusy) return;
    const active = canvas.getActiveObject();
    const imageMembers = _imageMembersOf(active);
    // Replace only works one image at a time — multi-select would force the
    // same file into every slot, which is rarely what the user means.
    if (imageMembers.length !== 1) return;
    const img = imageMembers[0];

    setReplaceBusy(true);
    pushUndo();
    try {
      const { path } = await api.uploadTemplateAsset(file);
      if (typeof img.setSrc === "function") {
        await img.setSrc(proxiedImageUrl(path), { crossOrigin: "anonymous" });
      }
      img.dirty = true;
      canvas.requestRenderAll();
      saveCurrentSlide();
      setSelectedObject(active ? { ...active } : null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "이미지 교체 실패");
    } finally {
      setReplaceBusy(false);
    }
  }

  // ─── Layer ordering ───
  function changeLayer(action: "forward" | "backward" | "front" | "back") {
    const canvas = fabricRef.current;
    if (!canvas) return;
    const active = canvas.getActiveObject();
    if (!active) return;
    pushUndo();
    if (action === "forward") canvas.bringObjectForward(active);
    else if (action === "backward") canvas.sendObjectBackwards(active);
    else if (action === "front") canvas.bringObjectToFront(active);
    else canvas.sendObjectToBack(active);
    canvas.renderAll();
    saveCurrentSlide();
    setSelectedObject({ ...active });
  }

  /** Snapshot the CURRENT canvas state and push the previous one onto undo. */
  function commitUndo() {
    const canvas = fabricRef.current;
    if (!canvas) return;
    const prev = lastSnapshotRef.current;
    if (prev !== null) {
      setUndoStack((u) => {
        const trimmed = u.length >= 50 ? u.slice(-49) : u;
        return [...trimmed, prev];
      });
      setRedoStack([]);
    }
    lastSnapshotRef.current = JSON.stringify(canvas.toJSON());
  }

  /** Manual snapshot — used by toolbar buttons (addText/addRect/...) before they mutate. */
  function pushUndo() {
    commitUndo();
  }

  function applyBgToCurrent(color: string) {
    const canvas = fabricRef.current;
    if (!canvas) return;
    pushUndo();
    // The page boundary rect is what the user reads as the slide background.
    // canvas.backgroundColor still paints the PAD band — leaving that alone
    // keeps the gutter visually distinct from the page.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const pb = (canvas as any).__pageBoundary;
    if (pb) { pb.set("fill", color); }
    canvas.renderAll();
    setBgColor(color);
    saveCurrentSlide();
  }

  function applyBgToAll(color: string) {
    // Bulk-update bypasses the canvas-snapshot undo stack (which only tracks
    // the current slide). User confirms once; revert means re-pick the old color.
    if (!confirm(`모든 슬라이드 배경색을 ${color}로 변경하시겠습니까?`)) return;
    const canvas = fabricRef.current;
    if (canvas) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const pb = (canvas as any).__pageBoundary;
      if (pb) { pb.set("fill", color); }
      canvas.renderAll();
      lastSnapshotRef.current = JSON.stringify(canvas.toJSON());
    }
    setSlides((prev) => prev.map((s) => ({ ...s, background: color })));
    setBgColor(color);
  }

  function undo() {
    const canvas = fabricRef.current;
    if (!canvas) return;
    setUndoStack((u) => {
      if (u.length === 0) return u;
      const prev = u[u.length - 1];
      // Save current state on redo stack before reverting
      const current = JSON.stringify(canvas.toJSON());
      setRedoStack((r) => [...r, current]);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (canvas as any).loadFromJSON(JSON.parse(prev)).then(() => {
        canvas.renderAll();
        lastSnapshotRef.current = prev;
        saveCurrentSlide();
      });
      return u.slice(0, -1);
    });
  }

  function redo() {
    const canvas = fabricRef.current;
    if (!canvas) return;
    setRedoStack((r) => {
      if (r.length === 0) return r;
      const next = r[r.length - 1];
      const current = JSON.stringify(canvas.toJSON());
      setUndoStack((u) => [...u, current]);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (canvas as any).loadFromJSON(JSON.parse(next)).then(() => {
        canvas.renderAll();
        lastSnapshotRef.current = next;
        saveCurrentSlide();
      });
      return r.slice(0, -1);
    });
  }

  // Keyboard: Ctrl/Cmd+Z = undo, Ctrl/Cmd+Y or Ctrl/Cmd+Shift+Z = redo,
  //           Ctrl/Cmd+0 = reset zoom.
  //           Arrow / Shift+Arrow = nudge the selected object (1px / 10px).
  //           Shift+Arrow with nothing selected = pan workspace (fallback).
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      // Block default editing intercepts ONLY when focus is a real, user-facing
      // input in a side panel. Fabric injects a hidden <textarea> *inside* the
      // canvas wrapper (for IME) that grabs focus on canvas click — treating
      // that as "in field" would mute every shortcut once the user works on the
      // canvas. So we whitelist anything inside the canvas viewport.
      const inCanvas = !!(target && canvasViewportRef.current?.contains(target));
      const inField = !inCanvas && !!target && (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      );
      // Suppress while the user is mid-edit inside a fabric Textbox (the
      // hidden textarea is in canvasViewport so the check above wouldn't catch).
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const editingText = (fabricRef.current as any)?.getActiveObject?.()?.isEditing === true;
      if (inField || editingText) return;
      const mod = e.ctrlKey || e.metaKey;
      const key = e.key.toLowerCase();

      if (mod) {
        if (key === "z" && !e.shiftKey) {
          e.preventDefault();
          undo();
          return;
        }
        if (key === "y" || (key === "z" && e.shiftKey)) {
          e.preventDefault();
          redo();
          return;
        }
        if (key === "0") {
          e.preventDefault();
          resetZoomPan();
          return;
        }
      }

      const isArrow = e.key === "ArrowLeft" || e.key === "ArrowRight"
                   || e.key === "ArrowUp"   || e.key === "ArrowDown";
      if (!isArrow || mod || e.altKey) return;

      // Focus is on a slide thumbnail → SlideNavigator owns this arrow press
      // (it walks the bottom page list). It also calls stopImmediatePropagation
      // on the native event, but checking here gives us a clean early-out
      // regardless of listener ordering.
      if (target && typeof (target as HTMLElement).closest === "function"
          && (target as HTMLElement).closest("[data-slide-thumb]")) return;

      // Arrow keys nudge the active fabric object (1px, or 10px with Shift).
      // Crop mode owns its own keydown handler higher up, so we skip nudging
      // while an auxiliary crop rect is live.
      const canvas = fabricRef.current;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const active: any = canvas?.getActiveObject?.();
      const inCrop = !!cropAuxRef.current;
      if (active && !inCrop) {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 1;
        let dx = 0, dy = 0;
        if (e.key === "ArrowLeft") dx = -step;
        else if (e.key === "ArrowRight") dx = step;
        else if (e.key === "ArrowUp") dy = -step;
        else if (e.key === "ArrowDown") dy = step;
        // One undo entry per press session: skip auto-repeat ticks so holding
        // an arrow doesn't flood the stack with single-pixel hops.
        if (!e.repeat) pushUndo();
        active.set({ left: (active.left || 0) + dx, top: (active.top || 0) + dy });
        if (typeof active.setCoords === "function") active.setCoords();
        canvas?.requestRenderAll();
        saveCurrentSlide();
        return;
      }

      // Fallback: with nothing selected, Shift+Arrow still pans the workspace.
      // Plain arrows do nothing in this state (would conflict with browser
      // scrolling if it were enabled, and pan via wheel / middle-drag is the
      // primary path).
      if (e.shiftKey) {
        const raw = 60;
        let dx = 0, dy = 0;
        if (e.key === "ArrowLeft") dx = raw;
        else if (e.key === "ArrowRight") dx = -raw;
        else if (e.key === "ArrowUp") dy = raw;
        else if (e.key === "ArrowDown") dy = -raw;
        e.preventDefault();
        setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Mouse-wheel routing in the canvas viewport:
  //   Ctrl/Cmd + wheel → zoom
  //   Shift + wheel    → explicit horizontal pan (matches native browser shift+wheel)
  //   plain wheel       → free pan; we consume whichever axes the device sent
  //                       (mouse wheel = deltaY only, touchpad two-finger = both).
  // Default browser behaviors (page zoom, page scroll) are suppressed with
  // preventDefault — React's synthetic onWheel is always passive, so we have
  // to use a raw DOM listener with passive:false.
  useEffect(() => {
    const el = canvasViewportRef.current;
    if (!el) return;
    function onWheel(e: WheelEvent) {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        // Exponential step so the zoom feels consistent across the range.
        // deltaY is positive when scrolling down (→ zoom out).
        setZoom((z) => {
          const factor = Math.exp(-e.deltaY * 0.0015);
          return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z * factor));
        });
        return;
      }
      if (e.shiftKey) {
        e.preventDefault();
        // Some browsers (Chrome/Edge on Windows) auto-swap shift+wheel into
        // deltaX; others leave it in deltaY. Take whichever axis the OS chose.
        const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
        // Wheel-down (positive d) reveals content to the right → shift the
        // canvas leftward in the viewport (pan.x decreases). Matches the
        // direction native horizontal scroll uses.
        setPan((p) => ({ x: p.x - d, y: p.y }));
        return;
      }
      // plain wheel → pan along whatever axis the device reported. Wheel-down
      // (deltaY > 0) reveals content lower in the page, so the canvas shifts
      // upward in the viewport (pan.y decreases). deltaX handles touchpad
      // horizontal swipes without needing shift.
      e.preventDefault();
      setPan((p) => ({ x: p.x - e.deltaX, y: p.y - e.deltaY }));
    }
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Middle-mouse-button drag pans the workspace freely (Figma / Photoshop
  // hand-tool behavior). mousedown starts a session, mousemove/mouseup are
  // tracked on window so the drag survives leaving the viewport bounds.
  useEffect(() => {
    const el = canvasViewportRef.current;
    if (!el) return;
    let panning = false;
    let lastX = 0;
    let lastY = 0;

    function onDown(e: MouseEvent) {
      if (e.button !== 1) return; // middle button only
      // preventDefault suppresses Windows' auto-scroll-cursor on middle-click.
      e.preventDefault();
      panning = true;
      lastX = e.clientX;
      lastY = e.clientY;
      el!.style.cursor = "grabbing";
    }
    function onMove(e: MouseEvent) {
      if (!panning) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      lastX = e.clientX;
      lastY = e.clientY;
      setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
    }
    function onUp(e: MouseEvent) {
      if (!panning) return;
      if (e.button !== 1 && e.button !== -1) return; // accept the matching release
      panning = false;
      el!.style.cursor = "";
    }
    function onAuxClick(e: MouseEvent) {
      // Some browsers fire an auxclick after middle-click — eat it so it
      // doesn't trigger paste-on-middle-click or other auxclick handlers.
      if (e.button === 1) e.preventDefault();
    }

    el.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    el.addEventListener("auxclick", onAuxClick);
    return () => {
      el.removeEventListener("mousedown", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      el.removeEventListener("auxclick", onAuxClick);
    };
  }, []);

  // Marquee-select that starts OUTSIDE the design canvas. Fabric's built-in
  // marquee only fires on the upper-canvas; clicks in the gray area around
  // the page were dead. With this handler the user can press in the gray
  // background, drag into the canvas, and the swept rect creates an
  // ActiveSelection of every object whose bounding box it touches.
  useEffect(() => {
    const el = canvasViewportRef.current;
    if (!el) return;
    let overlay: HTMLDivElement | null = null;
    let startX = 0, startY = 0;
    let dragging = false;
    // Track whether the user actually moved the mouse — a plain click in
    // empty space should just deselect, not create a zero-size marquee.
    let moved = false;

    function cleanup() {
      if (overlay) { overlay.remove(); overlay = null; }
      dragging = false;
      moved = false;
    }

    function onDown(e: MouseEvent) {
      if (e.button !== 0) return; // left-click only
      const canvas = fabricRef.current;
      if (!canvas) return;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const upper = (canvas as any).upperCanvasEl as HTMLCanvasElement | undefined;
      if (!upper) return;
      const ur = upper.getBoundingClientRect();
      // Click landed on the canvas itself → let fabric handle it.
      if (e.clientX >= ur.left && e.clientX <= ur.right &&
          e.clientY >= ur.top  && e.clientY <= ur.bottom) return;
      // Skip clicks on inline controls (zoom widget buttons/inputs).
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "BUTTON" || target.tagName === "INPUT" ||
                     target.closest("button") || target.closest("input"))) return;
      // Clear any existing selection before starting the marquee.
      canvas.discardActiveObject();
      canvas.requestRenderAll();
      setSelectedObject(null);

      startX = e.clientX;
      startY = e.clientY;
      dragging = true;
      moved = false;
      e.preventDefault();
    }

    function onMove(e: MouseEvent) {
      if (!dragging) return;
      if (!moved) {
        // Threshold: ignore tiny accidental wiggles
        if (Math.abs(e.clientX - startX) + Math.abs(e.clientY - startY) < 4) return;
        moved = true;
        // Lazily create the overlay on the first real move.
        overlay = document.createElement("div");
        overlay.setAttribute("data-marquee", "true");
        overlay.style.cssText = [
          "position:fixed",
          "pointer-events:none",
          "z-index:9999",
          "background:rgba(60,200,255,0.18)",
          "border:2px solid #3CC8FF",
          "box-sizing:border-box",
        ].join(";");
        document.body.appendChild(overlay);
      }
      if (!overlay) return;
      const x = Math.min(startX, e.clientX);
      const y = Math.min(startY, e.clientY);
      const w = Math.abs(e.clientX - startX);
      const h = Math.abs(e.clientY - startY);
      overlay.style.left = `${x}px`;
      overlay.style.top = `${y}px`;
      overlay.style.width = `${w}px`;
      overlay.style.height = `${h}px`;
    }

    function onUp(e: MouseEvent) {
      if (!dragging) return;
      const endX = e.clientX, endY = e.clientY;
      const didMove = moved;
      cleanup();
      if (!didMove) return;
      const canvas = fabricRef.current;
      if (!canvas) return;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const upper = (canvas as any).upperCanvasEl as HTMLCanvasElement | undefined;
      if (!upper) return;
      const ur = upper.getBoundingClientRect();
      // Convert the screen-space marquee rect into fabric's design space.
      // Scale factor accounts for both the CSS sizing and the zoom transform
      // (getBoundingClientRect already reports the post-transform size).
      const sx = canvas.width / ur.width;
      const sy = canvas.height / ur.height;
      const x1 = (Math.min(startX, endX) - ur.left) * sx;
      const y1 = (Math.min(startY, endY) - ur.top) * sy;
      const x2 = (Math.max(startX, endX) - ur.left) * sx;
      const y2 = (Math.max(startY, endY) - ur.top) * sy;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const hits = canvas.getObjects().filter((obj: any) => {
        if (!obj || typeof obj.getBoundingRect !== "function") return false;
        if (obj.evented === false || obj.selectable === false) return false;
        const r = obj.getBoundingRect();
        // Standard AABB intersection
        return r.left < x2 && r.left + r.width > x1 &&
               r.top  < y2 && r.top  + r.height > y1;
      });
      if (hits.length === 0) return;
      if (hits.length === 1) {
        canvas.setActiveObject(hits[0]);
        canvas.requestRenderAll();
        return;
      }
      // 2+ hits → group into an ActiveSelection. fabric.ActiveSelection needs
      // the live fabric module, which we resolve via getFabric().
      getFabric().then((fabric) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const sel = new (fabric as any).ActiveSelection(hits, { canvas });
        canvas.setActiveObject(sel);
        canvas.requestRenderAll();
      });
    }

    el.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      el.removeEventListener("mousedown", onDown);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      cleanup();
    };
  }, []);

  // ─── Download flow: open modal → user picks slides → user picks save target ───
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [downloadSelection, setDownloadSelection] = useState<Set<number>>(new Set());
  const [downloadPrefix, setDownloadPrefix] = useState("slide");
  const [downloading, setDownloading] = useState(false);

  function openDownloadModal() {
    // Default = all slides selected
    setDownloadSelection(new Set(slides.map((_, i) => i)));
    setDownloadOpen(true);
  }

  async function runDownload() {
    const canvas = fabricRef.current;
    if (!canvas || downloadSelection.size === 0) return;
    const selected = Array.from(downloadSelection).sort((a, b) => a - b);
    const prefix = (downloadPrefix || "slide").replace(/[^\w가-힣.-]+/g, "_");
    setDownloading(true);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any;
    const hasSecureAccess = window.isSecureContext;
    const hasFilePicker = hasSecureAccess && typeof w.showSaveFilePicker === "function";

    // Single-slide save: keep the per-file save-as picker so the user can
    // rename. Multi-slide save: zip everything and prompt once for the .zip.
    let fileHandle: unknown = null;
    if (selected.length === 1 && hasFilePicker) {
      try {
        fileHandle = await w.showSaveFilePicker({
          suggestedName: `${prefix}_${selected[0] + 1}.png`,
          types: [{ description: "PNG image", accept: { "image/png": [".png"] } }],
        });
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          setDownloading(false);
          return;
        }
        fileHandle = null;
      }
    } else if (selected.length > 1 && hasFilePicker) {
      try {
        fileHandle = await w.showSaveFilePicker({
          suggestedName: `${prefix}.zip`,
          types: [{ description: "ZIP archive", accept: { "application/zip": [".zip"] } }],
        });
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") {
          setDownloading(false);
          return;
        }
        fileHandle = null;
      }
    }

    async function renderSlideBlob(i: number): Promise<Blob> {
      switchSlide(i);
      await new Promise((r) => setTimeout(r, 120));
      // Crop to the page area only. The canvas pixel buffer is page + PAD on
      // every side (so selection chrome on out-of-page objects stays visible
      // while editing), but the downloaded PNG should be exactly the 1080×1350
      // — or whatever — design surface. Hide the page boundary stroke for the
      // duration of the export so its 1px outline doesn't bleed into the crop
      // edge, then restore it.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const pb = (canvas as any).__pageBoundary;
      const savedStroke = pb?.stroke;
      const savedStrokeWidth = pb?.strokeWidth;
      // Zoom is applied via fabric's viewportTransform; reset to identity-PAD
      // so the export renders the page at full resolution regardless of the
      // current editor zoom level.
      const savedVT = canvas!.viewportTransform?.slice() as number[];
      canvas!.setViewportTransform([1, 0, 0, 1, PAGE_PAD, PAGE_PAD]);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (canvas as any).__suppressPageOutline = true;
      if (pb) {
        pb.set({ stroke: null, strokeWidth: 0 });
        canvas!.renderAll();
      }
      const { w: pageW, h: pageH } = canvasSizeRef.current;
      const dataUrl = canvas!.toDataURL({
        format: "png",
        multiplier: 2,
        left: PAGE_PAD,
        top: PAGE_PAD,
        width: pageW,
        height: pageH,
      });
      if (pb) {
        pb.set({ stroke: savedStroke, strokeWidth: savedStrokeWidth });
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (canvas as any).__suppressPageOutline = false;
      if (savedVT) canvas!.setViewportTransform(savedVT);
      canvas!.renderAll();
      return (await fetch(dataUrl)).blob();
    }

    function triggerAnchorDownload(blob: Blob, name: string) {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.download = name;
      link.href = url;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    try {
      if (selected.length === 1) {
        const i = selected[0];
        const blob = await renderSlideBlob(i);
        const filename = `${prefix}_${i + 1}.png`;
        if (fileHandle) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const writable = await (fileHandle as any).createWritable();
          await writable.write(blob);
          await writable.close();
        } else {
          triggerAnchorDownload(blob, filename);
        }
      } else {
        // Multi-slide → zip first, then a single download.
        const { default: JSZip } = await import("jszip");
        const zip = new JSZip();
        for (const i of selected) {
          const blob = await renderSlideBlob(i);
          zip.file(`${prefix}_${i + 1}.png`, blob);
        }
        const zipBlob = await zip.generateAsync({ type: "blob" });
        const zipName = `${prefix}.zip`;
        if (fileHandle) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const writable = await (fileHandle as any).createWritable();
          await writable.write(zipBlob);
          await writable.close();
        } else {
          triggerAnchorDownload(zipBlob, zipName);
        }
      }
      setDownloadOpen(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "다운로드 실패");
    } finally {
      setDownloading(false);
    }
  }

  function handleSave() {
    const canvas = fabricRef.current;
    if (!canvas) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const active: any = canvas.getActiveObject?.();
    const editing =
      active &&
      (active.type === "textbox" || active.type === "Textbox") &&
      active.isEditing;
    if (editing) {
      const ok = confirm("대본 수정 중인데 완료된 게 맞나요?\n[확인] 저장하고 닫기\n[취소] 계속 편집");
      if (!ok) return;
      // Commit any in-progress IME composition / pending text before serializing
      if (typeof active.exitEditing === "function") active.exitEditing();
      canvas.requestRenderAll?.();
    }
    // Serialize the fabric canvas RIGHT NOW so we don't rely on setSlides()
    // having committed yet (the state update is async; the previous version
    // of this function sent the prior render's snapshot to the server).
    saveCurrentSlide();
    const json = canvas.toJSON();
    const { w, h } = canvasSizeRef.current;
    const idx = currentSlideIndexRef.current;
    const latest = [...slidesRef.current];
    latest[idx] = { ...json, version: "6.0.0", width: w, height: h };
    // Cancel the auto-save debounce — we're about to PATCH right now.
    if (autoSaveTimerRef.current) clearTimeout(autoSaveTimerRef.current);
    const handler = onSaveRef.current;
    if (!handler) return;
    setSaveStatus("saving");
    Promise.resolve(handler(latest)).then(
      () => setSaveStatus("saved"),
      () => setSaveStatus("error"),
    );
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function updateSelectedProperty(prop: string, value: any) {
    const canvas = fabricRef.current;
    if (!canvas) return;
    // `selectedObject` is a snapshot for rendering. For mutations we MUST use
    // fabric's real active object (which carries the prototype methods like
    // setSelectionStyles / set). The snapshot drops methods on the prototype.
    // Three fallbacks in priority: canvas active object → snap.__fabricRef
    // (the original fabric instance stashed during refreshSelection) → snap.
    const target = canvas.getActiveObject()
      || (selectedObject && selectedObject.__fabricRef)
      || selectedObject;
    if (!target) return;

    // Multi-select text editing: when the active selection contains 2+ text
    // members and the prop is text-specific, apply it to every text member
    // directly. Fabric's ActiveSelection.set() doesn't propagate text props
    // (fontSize/textAlign/etc) to children, so we have to iterate ourselves.
    const TEXT_BATCH_PROPS = new Set([
      "fontSize", "fontWeight", "fontStyle", "fontFamily",
      "textAlign", "lineHeight", "underline", "linethrough", "fill",
    ]);
    const t = target.type;
    const isActiveSel = t === "activeselection" || t === "ActiveSelection";

    // Image color fill via fabric.filters.BlendColor (mode "tint"). Value is
    // either `null` (remove the filter) or `{ color: "#rrggbb", intensity: 0-100 }`.
    // Applies to every image member in a multi-select; non-image members are skipped.
    if (prop === "__colorFill") {
      (async () => {
        const fabric = await getFabric();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const targets: any[] = isActiveSel && Array.isArray(target._objects)
          ? target._objects
          : [target];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const imgs = targets.filter((m: any) => {
          const tp = String(m.type || "").toLowerCase();
          return tp === "image" || tp === "fabricimage";
        });
        if (imgs.length === 0) return;
        pushUndo();
        for (const img of imgs) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const filters: any[] = Array.isArray(img.filters) ? img.filters : [];
          // Strip existing BlendColor entries (regardless of whether we'll add
          // a new one below). Lets a single BlendColor own the "tint" slot.
          const remaining = filters.filter((f) => {
            const ft = f?.type || f?.constructor?.name || "";
            return ft !== "BlendColor" && ft !== "blend-color";
          });
          if (value && value.color) {
            const alpha = Math.max(0, Math.min(1, Number(value.intensity) / 100));
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const bc = new (fabric as any).filters.BlendColor({
              color: value.color,
              mode: "tint",
              alpha,
            });
            remaining.push(bc);
          }
          img.filters = remaining;
          if (typeof img.applyFilters === "function") img.applyFilters();
          img.dirty = true;
        }
        target.dirty = true;
        canvas.requestRenderAll();
        saveCurrentSlide();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const snap: any = { ...target };
        snap.type = target.type;
        snap.filters = target.filters;
        snap.__fabricRef = target;
        setSelectedObject(snap);
      })();
      return;
    }

    // Shadow needs to be a real `fabric.Shadow` instance — passing the CSS
    // string from the panel directly into target.set is a no-op in fabric v6.
    // Construct here, then propagate to every member when multi-select.
    if (prop === "shadow") {
      (async () => {
        const fabric = await getFabric();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const shadowObj: any = value ? new (fabric as any).Shadow(value) : null;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const targets: any[] = isActiveSel && Array.isArray(target._objects)
          ? target._objects
          : [target];
        pushUndo();
        for (const m of targets) {
          m.set("shadow", shadowObj);
          m.dirty = true;
        }
        target.dirty = true;
        canvas.requestRenderAll();
        saveCurrentSlide();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const snap: any = { ...target };
        snap.type = target.type;
        snap.shadow = target.shadow;
        snap.__fabricRef = target;
        setSelectedObject(snap);
      })();
      return;
    }

    if (isActiveSel && TEXT_BATCH_PROPS.has(prop)) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const members: any[] = Array.isArray(target._objects) ? target._objects : [];
      const textMembers = members.filter((m) =>
        m && (m.type === "textbox" || m.type === "Textbox" || m.type === "i-text")
      );
      if (textMembers.length > 0) {
        pushUndo();
        for (const m of textMembers) {
          m.set(prop, value);
          if (typeof m.initDimensions === "function") m.initDimensions();
          m.dirty = true;
        }
        target.dirty = true;
        canvas.requestRenderAll();
        saveCurrentSlide();
        // Re-snapshot the selection wrapper so the panel reflects new values
        // (it reads from textMembers[0] via _objects on the snapshot).
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const snap: any = { ...target };
        snap.type = target.type;
        snap._objects = members;
        snap.__fabricRef = target;
        setSelectedObject(snap);
        return;
      }
    }

    const isTextbox = target.type === "textbox" || target.type === "Textbox";
    const RANGE_PROPS = new Set([
      "fontSize", "fontWeight", "fontStyle", "fill",
      "underline", "linethrough", "fontFamily",
    ]);

    // Use the ref so a fabric event that ran between render and onChange
    // (which would null out the state) can't strip the range away.
    const range = selectedTextRangeRef.current;
    if (isTextbox && range && range.end > range.start && RANGE_PROPS.has(prop) && typeof target.setSelectionStyles === "function") {
      pushUndo();
      target.setSelectionStyles({ [prop]: value }, range.start, range.end);
      // Force the textbox to recompute character metrics so fontSize / weight
      // changes are visible immediately (fabric otherwise lazy-redraws).
      if (typeof target.initDimensions === "function") target.initDimensions();
      target.dirty = true;
      canvas.requestRenderAll();
      saveCurrentSlide();
      // Re-snapshot so the panel reflects the post-change state
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const snap: any = { ...target };
      snap.type = target.type;
      snap.fill = target.fill;
      snap.fontSize = target.fontSize;
      snap.fontWeight = target.fontWeight;
      snap.text = target.text;
      snap.isEditing = target.isEditing;
      snap.selectionStart = target.selectionStart;
      snap.selectionEnd = target.selectionEnd;
      snap.getSelectionStyles = target.getSelectionStyles?.bind(target);
      setSelectedObject(snap);
      return;
    }

    pushUndo();
    // fill can come in as a hex string OR as a gradient spec dict. Convert
    // the dict into a fabric.Gradient so the canvas renders the gradient now,
    // and saveCurrentSlide() round-trips through fabric.toJSON cleanly.
    if (prop === "fill" && value && typeof value === "object" && (value.type === "linear" || Array.isArray(value.colorStops))) {
      getFabric().then((fabric) => {
        const grad = new fabric.Gradient({
          type: "linear",
          coords: value.coords || { x1: 0, y1: 0, x2: 0, y2: (target.height || 200) * (target.scaleY || 1) },
          colorStops: value.colorStops || [],
        });
        target.set("fill", grad);
        target.dirty = true;
        canvas.requestRenderAll();
        saveCurrentSlide();
      });
    } else if (prop === "strokeWidth" && !isTextbox && target.type !== "i-text") {
      // Outline-thickness change on a shape or image: keep the *visible*
      // center fixed by measuring the bounding rect before vs. after the
      // set() and compensating left/top by the delta. With
      // strokeUniform=true, fabric grows the stroke asymmetrically (the
      // bbox extends more in one direction than the other), which makes
      // the element appear to drift as the slider moves. Snapping the
      // center back cancels that drift.
      const before = typeof target.getBoundingRect === "function"
        ? target.getBoundingRect(true, true)
        : null;
      target.set(prop, value);
      if (typeof target.setCoords === "function") target.setCoords();
      const after = typeof target.getBoundingRect === "function"
        ? target.getBoundingRect(true, true)
        : null;
      if (before && after) {
        const dx = (before.left + before.width / 2)
                 - (after.left + after.width / 2);
        const dy = (before.top + before.height / 2)
                 - (after.top + after.height / 2);
        if (dx !== 0 || dy !== 0) {
          target.set("left", (target.left || 0) + dx);
          target.set("top", (target.top || 0) + dy);
          if (typeof target.setCoords === "function") target.setCoords();
        }
      }
      target.dirty = true;
      canvas.requestRenderAll();
      saveCurrentSlide();
    } else {
      target.set(prop, value);
      if (isTextbox && typeof target.initDimensions === "function") target.initDimensions();
      target.dirty = true;
      canvas.requestRenderAll();
      saveCurrentSlide();
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const snap: any = { ...target };
    snap.type = target.type;
    snap.fill = target.fill;
    snap.fontSize = target.fontSize;
    snap.fontWeight = target.fontWeight;
    setSelectedObject(snap);
  }

  // Keyboard shortcuts (only when the canvas — not an input/textarea — has focus):
  //   Ctrl/Cmd+B → bold toggle (selection-aware inside a textbox)
  //   Delete/Backspace → delete the active object (when NOT inside textbox editing)
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField = !!target && (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      );
      if (inField) return;

      const canvas = fabricRef.current;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const active: any = canvas?.getActiveObject();

      // Crop mode: Enter confirms, Escape cancels. Block other shortcuts
      // (delete, copy, etc.) while cropping so the aux rect isn't deleted.
      if (cropAuxRef.current) {
        if (e.key === "Enter") {
          e.preventDefault();
          commitCrop();
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          cancelCrop();
          return;
        }
        // Block destructive shortcuts during crop
        if (e.key === "Delete" || e.key === "Backspace") {
          e.preventDefault();
          return;
        }
      }

      // Delete / Backspace — delete the active object, OR (when nothing is
      // selected) remove the current slide. Read the index from the ref so
      // a thumb click that ran *after* this handler was registered still
      // results in the freshly-selected slide being removed, not the one
      // that was current at mount time.
      if (e.key === "Delete" || e.key === "Backspace") {
        if (active && !active.isEditing) {
          e.preventDefault();
          deleteSelected();
          return;
        }
        if (!active) {
          e.preventDefault();
          removeSlide(currentSlideIndexRef.current);
          return;
        }
      }

      // Ctrl/Cmd + D → duplicate the current slide. Browser default is
      // "bookmark this page" so we must preventDefault.
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "d" && !active?.isEditing) {
        e.preventDefault();
        duplicateSlide();
        return;
      }

      // Ctrl/Cmd + C → copy active object into in-memory clipboard
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && active && !active.isEditing) {
        e.preventDefault();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Promise.resolve((active as any).clone()).then((cloned) => {
          objectClipboardRef.current = cloned;
        }).catch((err) => console.warn("[copy] clone failed", err));
        return;
      }

      // Ctrl/Cmd + X → cut: copy then delete
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "x" && active && !active.isEditing) {
        e.preventDefault();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        Promise.resolve((active as any).clone()).then((cloned) => {
          objectClipboardRef.current = cloned;
          deleteSelected();
        }).catch((err) => console.warn("[cut] clone failed", err));
        return;
      }

      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "b") return;
      if (!active) return;
      const isTextbox = active.type === "textbox" || active.type === "Textbox";
      if (!isTextbox) return;
      e.preventDefault();
      const isBold = (w: unknown) => {
        const s = String(w);
        return s === "bold" || s === "700" || s === "800" || s === "900";
      };
      const range = selectedTextRangeRef.current;
      if (range) {
        const { start, end } = range;
        const styles = active.getSelectionStyles(start, start + 1);
        const cur = styles?.[0]?.fontWeight || active.fontWeight || "normal";
        pushUndo();
        active.setSelectionStyles({ fontWeight: isBold(cur) ? "normal" : "bold" }, start, end);
      } else {
        const cur = active.fontWeight || "normal";
        pushUndo();
        active.set("fontWeight", isBold(cur) ? "normal" : "bold");
      }
      canvas?.renderAll();
      saveCurrentSlide();
      setSelectedObject({ ...active });
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Paste image from clipboard (Ctrl/Cmd+V) — Win+Shift+S screenshot, copied
  // image files, etc. Skipped when the user is typing inside a textbox so the
  // native text paste keeps working.
  useEffect(() => {
    async function onPaste(e: ClipboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField = !!target && (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable
      );
      if (inField) return;
      const canvas = fabricRef.current;
      if (!canvas) return;
      // If a textbox is currently being edited, let the textbox handle text paste
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const active: any = canvas.getActiveObject();
      if (active?.isEditing) return;

      const items = e.clipboardData?.items;
      // Check if the OS clipboard has an image (e.g. screenshot). If so, handle
      // that and ignore the in-memory object clipboard (the user just took a
      // screenshot so they obviously want THAT, not their last copied shape).
      const hasImage = items && Array.from(items).some((it) => it.type.startsWith("image/"));

      if (!hasImage && objectClipboardRef.current) {
        // Paste the previously copied/cut canvas object
        e.preventDefault();
        try {
          const fabric = await getFabric();
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const cloned: any = await Promise.resolve(objectClipboardRef.current.clone());
          cloned.set({
            left: (objectClipboardRef.current.left || 0) + 24,
            top: (objectClipboardRef.current.top || 0) + 24,
            originX: "left",
            originY: "top",
          });
          pushUndo();
          canvas.add(cloned);
          canvas.setActiveObject(cloned);
          canvas.requestRenderAll();
          saveCurrentSlide();
          // Update the in-memory clipboard so consecutive Ctrl+V keeps offsetting
          objectClipboardRef.current = cloned;
          void fabric;
        } catch (err) {
          console.warn("[paste] object clone failed", err);
        }
        return;
      }

      if (!items) return;
      for (const item of Array.from(items)) {
        if (!item.type.startsWith("image/")) continue;
        const file = item.getAsFile();
        if (!file) continue;
        e.preventDefault();
        const dataUrl = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result));
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
        const fabric = await getFabric();
        try {
          const img = await fabric.FabricImage.fromURL(dataUrl);
          // Fit the pasted image into the canvas, centered.
          const cw = canvas.getWidth();
          const ch = canvas.getHeight();
          const iw = img.width || cw;
          const ih = img.height || ch;
          const scale = Math.min(1, (cw * 0.6) / iw, (ch * 0.6) / ih);
          img.set({
            left: Math.round((cw - iw * scale) / 2),
            top: Math.round((ch - ih * scale) / 2),
            scaleX: scale,
            scaleY: scale,
            originX: "left",
            originY: "top",
          });
          pushUndo();
          canvas.add(img);
          canvas.setActiveObject(img);
          canvas.requestRenderAll();
          saveCurrentSlide();
        } catch (err) {
          console.warn("[paste] failed to load clipboard image", err);
        }
        return;  // one image is enough
      }
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "var(--bg-app)" }}>
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 16px",
          background: "var(--bg-elevated)",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}
      >
        {/* Project title (click to rename) */}
        {onRenameTitle && (
          <>
            {titleEditing ? (
              <input
                autoFocus
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onBlur={commitTitleEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") (e.currentTarget as HTMLInputElement).blur();
                  else if (e.key === "Escape") cancelTitleEdit();
                }}
                style={{
                  minWidth: 160, maxWidth: 320,
                  padding: "4px 8px",
                  fontSize: 13, fontWeight: 500,
                  color: "var(--text-primary)", background: "var(--bg-overlay)",
                  border: "1px solid var(--accent)", borderRadius: 5,
                  outline: "none",
                }}
              />
            ) : (
              <button
                type="button"
                onClick={startTitleEdit}
                title="이름 변경 (클릭)"
                style={{
                  maxWidth: 320,
                  padding: "4px 8px",
                  fontSize: 13, fontWeight: 500,
                  color: "var(--text-primary)", background: "transparent",
                  border: "1px solid transparent", borderRadius: 5, cursor: "text",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  display: "inline-flex", alignItems: "center", gap: 4,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-overlay)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {title?.trim() || "(제목 없음)"}
                </span>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ opacity: 0.55, flexShrink: 0 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125" />
                </svg>
              </button>
            )}
            <div style={{ width: 1, height: 18, background: "var(--border)" }} />
          </>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 2, background: "var(--bg-overlay)", borderRadius: 6, padding: 2 }}>
          <button
            onClick={undo}
            disabled={undoStack.length === 0}
            style={{
              padding: 6,
              borderRadius: 4,
              color: undoStack.length === 0 ? "var(--text-tertiary)" : "var(--text-secondary)",
              opacity: undoStack.length === 0 ? 0.4 : 1,
              cursor: undoStack.length === 0 ? "not-allowed" : "pointer",
            }}
            title="실행취소"
          >
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3" />
            </svg>
          </button>
          <button
            onClick={redo}
            disabled={redoStack.length === 0}
            style={{
              padding: 6,
              borderRadius: 4,
              color: redoStack.length === 0 ? "var(--text-tertiary)" : "var(--text-secondary)",
              opacity: redoStack.length === 0 ? 0.4 : 1,
              cursor: redoStack.length === 0 ? "not-allowed" : "pointer",
            }}
            title="다시실행"
          >
            <svg width="15" height="15" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m15 15 6-6m0 0-6-6m6 6H9a6 6 0 0 0 0 12h3" />
            </svg>
          </button>
        </div>

        <div style={{ width: 1, height: 18, background: "var(--border)" }} />

        <button
          onClick={deleteSelected}
          disabled={!selectedObject}
          style={{
            padding: 6,
            borderRadius: 5,
            color: "var(--text-secondary)",
            opacity: !selectedObject ? 0.35 : 1,
            cursor: !selectedObject ? "not-allowed" : "pointer",
          }}
          onMouseEnter={(e) => { if (selectedObject) e.currentTarget.style.color = "var(--red)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-secondary)"; }}
          title="삭제"
        >
          <svg width="15" height="15" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
          </svg>
        </button>

        <div style={{ width: 1, height: 18, background: "var(--border)" }} />
        <CanvasSizeSelector width={canvasW} height={canvasH} onChange={setCanvasSize} />

        {onReapplyTemplate && (
          <>
            <div style={{ width: 1, height: 18, background: "var(--border)" }} />
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>템플릿</span>
              <select
                value={currentTemplateId ?? ""}
                disabled={applyingTemplate || !canReapplyTemplate}
                onChange={(e) => handleTemplateChange(Number(e.target.value))}
                title={canReapplyTemplate ? "다른 템플릿 적용" : "원본 데이터 없음 — 변경 불가"}
                style={{
                  padding: "4px 8px",
                  fontSize: 11,
                  background: "var(--bg-overlay)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border)",
                  borderRadius: 5,
                  maxWidth: 200,
                  cursor: canReapplyTemplate ? "pointer" : "not-allowed",
                  opacity: canReapplyTemplate ? 1 : 0.55,
                }}
              >
                {templates.length === 0 && <option value="">불러오는 중...</option>}
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}{t.user_id === null ? " (시스템)" : ""}
                  </option>
                ))}
              </select>
              {applyingTemplate && (
                <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>적용 중…</span>
              )}
            </div>
          </>
        )}

        <div style={{ flex: 1 }} />

        {/* Auto-save status — reflects the debounced PATCH cycle. Stays out
            of the way when nothing has changed yet (status: idle). */}
        <span
          data-save-status={saveStatus}
          style={{
            fontSize: 11,
            color: saveStatus === "error" ? "var(--red)" : "var(--text-tertiary)",
            minWidth: 64,
            textAlign: "right",
            transition: "opacity 0.15s",
            opacity: saveStatus === "idle" ? 0 : 1,
          }}
        >
          {saveStatus === "pending" && "변경 사항 대기…"}
          {saveStatus === "saving" && "저장 중…"}
          {saveStatus === "saved" && "저장됨"}
          {saveStatus === "error" && "저장 실패"}
        </span>

        <button
          onClick={handleSave}
          title="즉시 저장 (자동 저장과 별도로 변경 사항을 바로 PATCH)"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            padding: "6px 14px",
            fontSize: 12,
            fontWeight: 500,
            background: "var(--accent)",
            color: "white",
            borderRadius: 6,
            cursor: "pointer",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "var(--accent)")}
        >
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M17.593 3.322c1.1.128 1.907 1.077 1.907 2.185V21L12 17.25 4.5 21V5.507c0-1.108.806-2.057 1.907-2.185a48.507 48.507 0 0 1 11.186 0Z" />
          </svg>
          저장
        </button>
        {onToggleFinalized && (
          <button
            onClick={() => { void onToggleFinalized(); }}
            title={isFinalized ? "완성 표시를 해제하면 '작업 중'으로 돌아갑니다" : "내 작업 > 완성 탭에 모입니다"}
            style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "6px 14px", fontSize: 12, fontWeight: 500,
              color: isFinalized ? "rgb(160,230,190)" : "var(--text-secondary)",
              background: isFinalized ? "rgba(100,200,150,0.18)" : "var(--bg-elevated)",
              border: isFinalized ? "1px solid rgba(100,200,150,0.4)" : "1px solid var(--border)",
              borderRadius: 6, cursor: "pointer",
            }}
          >
            <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75 10.5 18.75 19.5 5.25" />
            </svg>
            {isFinalized ? "완성됨" : "완성"}
          </button>
        )}
        <button
          onClick={openDownloadModal}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            padding: "6px 14px",
            fontSize: 12,
            fontWeight: 500,
            background: "var(--bg-overlay)",
            color: "var(--text-secondary)",
            borderRadius: 6,
            border: "1px solid var(--border)",
            cursor: "pointer",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
        >
          <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          다운로드
        </button>
      </div>

      {/* Download modal — page selector + save target */}
      {downloadOpen && (
        <div
          onClick={() => !downloading && setDownloadOpen(false)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.78)",
            backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)",
            zIndex: 200, display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "var(--bg-base, #141414)",
              border: "1px solid var(--border)",
              borderRadius: 12, width: "100%", maxWidth: 520,
              padding: 22, boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
            }}
          >
            <h3 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 4 }}>
              슬라이드 다운로드
            </h3>
            <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0, marginBottom: 14 }}>
              저장할 페이지를 골라주세요. 한 장은 “다른 이름으로 저장”, 여러 장이면 폴더를 한 번에 선택할 수 있어요.
            </p>

            {/* Prefix input */}
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: "block", fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>
                파일명 접두어
              </label>
              <input
                type="text"
                value={downloadPrefix}
                disabled={downloading}
                onChange={(e) => setDownloadPrefix(e.target.value)}
                placeholder="slide"
                style={{
                  width: "100%", padding: "7px 10px", fontSize: 12,
                  background: "var(--bg-overlay)", color: "var(--text-primary)",
                  border: "1px solid var(--border)", borderRadius: 5, outline: "none",
                  fontFamily: "monospace",
                }}
              />
              <p style={{ fontSize: 10, color: "var(--text-tertiary)", margin: "4px 0 0" }}>
                예: <code>{(downloadPrefix || "slide")}_1.png</code>
              </p>
            </div>

            {/* Select all toggle */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                페이지 ({downloadSelection.size}/{slides.length})
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  disabled={downloading}
                  onClick={() => setDownloadSelection(new Set(slides.map((_, i) => i)))}
                  style={{
                    padding: "3px 10px", fontSize: 11,
                    color: "var(--text-secondary)", background: "var(--bg-elevated)",
                    border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer",
                  }}
                >
                  전체
                </button>
                <button
                  disabled={downloading}
                  onClick={() => setDownloadSelection(new Set())}
                  style={{
                    padding: "3px 10px", fontSize: 11,
                    color: "var(--text-secondary)", background: "var(--bg-elevated)",
                    border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer",
                  }}
                >
                  해제
                </button>
              </div>
            </div>

            <div style={{
              display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(72px, 1fr))",
              gap: 6, marginBottom: 16, maxHeight: 240, overflowY: "auto",
              padding: 8, background: "var(--bg-app)",
              border: "1px solid var(--border)", borderRadius: 6,
            }}>
              {slides.map((_, i) => {
                const checked = downloadSelection.has(i);
                return (
                  <button
                    key={i}
                    onClick={() => {
                      const n = new Set(downloadSelection);
                      if (checked) n.delete(i); else n.add(i);
                      setDownloadSelection(n);
                    }}
                    disabled={downloading}
                    style={{
                      padding: "10px 4px", fontSize: 11, fontWeight: 500,
                      color: checked ? "white" : "var(--text-secondary)",
                      background: checked ? "var(--accent)" : "var(--bg-overlay)",
                      border: `1px solid ${checked ? "var(--accent)" : "var(--border)"}`,
                      borderRadius: 5, cursor: downloading ? "default" : "pointer",
                    }}
                  >
                    {i + 1}
                  </button>
                );
              })}
            </div>

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                onClick={() => setDownloadOpen(false)}
                disabled={downloading}
                style={{
                  padding: "8px 14px", fontSize: 12,
                  color: "var(--text-secondary)", background: "var(--bg-elevated)",
                  border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer",
                }}
              >
                취소
              </button>
              <button
                onClick={runDownload}
                disabled={downloading || downloadSelection.size === 0}
                style={{
                  padding: "8px 16px", fontSize: 12, fontWeight: 500,
                  color: "white", background: "var(--accent)",
                  border: "none", borderRadius: 6,
                  cursor: downloading || downloadSelection.size === 0 ? "default" : "pointer",
                  opacity: downloading || downloadSelection.size === 0 ? 0.6 : 1,
                }}
              >
                {downloading ? "다운로드 중…" : `${downloadSelection.size}장 다운로드`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main editor area */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left: Tool Panel */}
        <ToolPanel
          onAddText={addText}
          onAddRect={addRect}
          onAddCircle={addCircle}
          onAddGradientOverlay={addGradientOverlay}
          onImportImage={importImageFile}
          onImportPsd={importPsd}
          bgColor={bgColor}
          onApplyBgToCurrent={applyBgToCurrent}
          onApplyBgToAll={applyBgToAll}
          caption={caption}
          hashtags={hashtags}
        />

        {/* Center: Canvas (also the drop target for image files) */}
        <div
          ref={canvasViewportRef}
          onDragEnter={onCanvasDragEnter}
          onDragOver={onCanvasDragOver}
          onDragLeave={onCanvasDragLeave}
          onDrop={onCanvasDrop}
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            // Match the fabric canvas gutter (#1E1E1E) so the PAD band inside
            // the canvas buffer and the workspace around it read as one
            // continuous surface — page (white) sits on a single dark
            // workspace with no inner boundary.
            background: "#1E1E1E",
            padding: 0,
            position: "relative",
            overflow: "hidden", // ← clip zoomed/panned canvas so it doesn't spill into side panels
          }}
        >
          <div
            style={{
              // The canvas buffer is much wider/taller than the viewport (PAD
              // is sized so the buffer spills past every edge). Flex centering
              // breaks when the child overflows the container, so position the
              // wrapper absolutely and center it via transform — that keeps
              // the page exactly at viewport center regardless of buffer size.
              position: "absolute",
              left: "50%",
              top: "50%",
              transform: `translate(-50%, -50%) translate(${pan.x}px, ${pan.y}px)`,
              transformOrigin: "center",
              transition: "transform 0.06s ease-out",
              willChange: "transform",
            }}
          >
            <canvas ref={canvasRef} />
          </div>

          {/* Zoom control (bottom-right): −, editable %, +, reset. */}
          <div
            style={{
              position: "absolute",
              right: 16,
              bottom: 12,
              display: "inline-flex",
              alignItems: "stretch",
              fontSize: 11,
              fontWeight: 500,
              color: "var(--text-secondary)",
              background: "var(--bg-overlay)",
              border: "1px solid var(--border)",
              borderRadius: 5,
              overflow: "hidden",
              opacity: 0.92,
            }}
          >
            <button
              type="button"
              onClick={() => setZoom((z) => clampZoom(z - ZOOM_STEP))}
              disabled={zoom <= ZOOM_MIN + 1e-6}
              title="축소"
              style={{
                padding: "4px 8px", background: "transparent",
                border: "none", borderRight: "1px solid var(--border)",
                color: "inherit",
                cursor: zoom <= ZOOM_MIN + 1e-6 ? "default" : "pointer",
                opacity: zoom <= ZOOM_MIN + 1e-6 ? 0.4 : 1,
              }}
            >
              −
            </button>
            <input
              type="text"
              value={zoomInputText}
              onChange={(e) => setZoomInputText(e.target.value)}
              onFocus={(e) => { setZoomInputFocused(true); e.currentTarget.select(); }}
              onBlur={() => { setZoomInputFocused(false); commitZoomInput(); }}
              onKeyDown={(e) => {
                if (e.key === "Enter") { (e.currentTarget as HTMLInputElement).blur(); }
                else if (e.key === "Escape") {
                  setZoomInputText(String(Math.round(zoom * 100)));
                  (e.currentTarget as HTMLInputElement).blur();
                }
              }}
              title={`수치 입력 (${Math.round(ZOOM_MIN * 100)}~${Math.round(ZOOM_MAX * 100)})`}
              style={{
                width: 44, padding: "4px 4px", textAlign: "center",
                background: "transparent", color: "inherit",
                border: "none", outline: "none", fontSize: 11, fontWeight: 500,
              }}
            />
            <span style={{ alignSelf: "center", paddingRight: 6, color: "var(--text-tertiary)" }}>%</span>
            <button
              type="button"
              onClick={() => setZoom((z) => clampZoom(z + ZOOM_STEP))}
              disabled={zoom >= ZOOM_MAX - 1e-6}
              title="확대"
              style={{
                padding: "4px 8px", background: "transparent",
                border: "none", borderLeft: "1px solid var(--border)",
                color: "inherit",
                cursor: zoom >= ZOOM_MAX - 1e-6 ? "default" : "pointer",
                opacity: zoom >= ZOOM_MAX - 1e-6 ? 0.4 : 1,
              }}
            >
              +
            </button>
            <button
              type="button"
              onClick={resetZoomPan}
              title="100%로 복원 (Ctrl+0)"
              style={{
                padding: "4px 8px", background: "transparent",
                border: "none", borderLeft: "1px solid var(--border)",
                color: "inherit", cursor: "pointer",
              }}
            >
              ↺
            </button>
          </div>

          {/* Crop confirm/cancel bar — visible only while an image crop is in progress */}
          {cropping && (
            <div
              style={{
                position: "absolute",
                top: 16,
                left: "50%",
                transform: "translateX(-50%)",
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                background: "rgba(20,20,20,0.92)",
                border: "1px solid var(--border)",
                borderRadius: 8,
                color: "var(--text-primary)",
                fontSize: 12,
                boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
                zIndex: 20,
              }}
            >
              <span style={{ color: "var(--text-secondary)" }}>
                자르기 영역 조절 — Enter 또는 바깥 클릭으로 확정 · Esc 취소
              </span>
              <button
                onClick={cancelCrop}
                style={{
                  padding: "4px 10px", fontSize: 11, fontWeight: 500,
                  color: "var(--text-secondary)", background: "var(--bg-elevated)",
                  border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer",
                }}
              >
                취소
              </button>
              <button
                onClick={commitCrop}
                style={{
                  padding: "4px 12px", fontSize: 11, fontWeight: 600,
                  color: "white", background: "#007AFF",
                  border: "none", borderRadius: 4, cursor: "pointer",
                }}
              >
                ✓ 확인
              </button>
            </div>
          )}

          {/* Drag overlay — only shown while a file is hovering over the area */}
          {dragActive && (
            <div
              style={{
                position: "absolute",
                inset: 16,
                pointerEvents: "none",
                background: "rgba(94,106,210,0.10)",
                border: "2px dashed rgba(94,106,210,0.55)",
                borderRadius: 12,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "rgb(180,190,255)",
                fontSize: 15,
                fontWeight: 500,
                letterSpacing: 0.3,
                backdropFilter: "blur(2px)",
                WebkitBackdropFilter: "blur(2px)",
                zIndex: 5,
              }}
            >
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📥</div>
                <div>이미지를 여기에 드롭</div>
                <div style={{ fontSize: 11, color: "rgba(180,190,255,0.7)", marginTop: 4 }}>
                  jpg · png · webp · jfif
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: Property Panel */}
        <PropertyPanel
          selectedObject={selectedObject}
          selectedTextRange={selectedTextRange}
          onUpdate={updateSelectedProperty}
          onChangeLayer={changeLayer}
          onDelete={deleteSelected}
          onCutout={(mode) => cutoutSelectedImage(mode)}
          cutoutBusy={cutoutBusy}
          onEnhance={(category) => enhanceSelectedImage(category)}
          enhanceBusy={enhanceBusy}
          onReplaceImage={(file) => replaceSelectedImage(file)}
          replaceBusy={replaceBusy}
        />
      </div>

      {/* Bottom: Slide Navigator */}
      <SlideNavigator
        slides={slides}
        currentIndex={currentSlideIndex}
        onSelect={switchSlide}
        onAdd={addSlide}
        onDuplicate={duplicateSlide}
        onRemove={removeSlide}
        onReorder={reorderSlides}
      />
    </div>
  );
}
