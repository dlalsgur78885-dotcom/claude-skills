"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { TemplateData, FabricMeta, LayoutSpec, TextSlot, Decoration } from "./types";
import { renderLayoutToCanvas } from "./renderer";
import { setByPath, getByPath, removeArrayItem } from "@/lib/template-paths";
import { getFabric } from "@/lib/fabric";
import { api } from "@/lib/api";
import { LayoutPropertyPanel } from "./LayoutPropertyPanel";
import { LayoutMiniPreview } from "./LayoutMiniPreview";
import { CanvasSizeSelector } from "@/components/CanvasSizeSelector";

export type { TemplateData };

const DISPLAY_SIZE = 560;

interface Props {
  templateId?: number;
  template: TemplateData;
  onSave: (next: TemplateData) => Promise<void>;
  onClose: () => void;
}

export function TemplateEditor({ templateId, template: initial, onSave, onClose }: Props) {
  const [template, setTemplate] = useState<TemplateData>(initial);
  const [layoutName, setLayoutName] = useState<string>(
    Object.keys(initial.layouts || {})[0] || ""
  );
  const [selectedMeta, setSelectedMeta] = useState<FabricMeta | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  // Timestamp of the most recent successful save — drives the "방금 저장됨"
  // pill so the user knows their work is safe without having to click save.
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  // Which layout mini-preview is being hovered — drives the visibility of the
  // per-thumbnail delete button without needing one boolean per item.
  const [hoveredLayoutName, setHoveredLayoutName] = useState<string | null>(null);
  // Which layout the user is currently copying. When non-null, the copy-target
  // picker popup is open over that thumbnail.
  const [copySourceLayout, setCopySourceLayout] = useState<string | null>(null);
  // Anchor rect (viewport coords) of the thumbnail wrapper for the open copy
  // popup. Used to position the portal-rendered popup with fixed coords —
  // the layout bar has overflow-x:auto which CSS-spec-clips overflow-y too,
  // so an in-tree absolute popup gets cut off.
  const [copyAnchorRect, setCopyAnchorRect] = useState<{ x: number; y: number; w: number } | null>(null);
  // Other templates the user can copy this layout INTO. Lazily fetched the
  // first time the copy popup opens so the editor's initial render stays cheap.
  const [otherTemplates, setOtherTemplates] = useState<
    { id: number; name: string }[] | null
  >(null);
  const [copyingTo, setCopyingTo] = useState<number | null>(null);
  const [copyResultMsg, setCopyResultMsg] = useState<string>("");
  // Undo/redo as JSON snapshots (each commit pushes onto undo, clears redo).
  const [undoStack, setUndoStack] = useState<string[]>([]);
  const [redoStack, setRedoStack] = useState<string[]>([]);

  // Close the copy popup when the user clicks outside of it. The popup is
  // portaled to body and the copy buttons live elsewhere in the tree, so
  // React's e.stopPropagation() on the popup doesn't reliably stop a native
  // document-level listener (the native event passes through body to
  // document independently of React's delegation). Instead, check the click
  // target directly — if it's inside the popup OR inside any copy button,
  // ignore. Anything else closes.
  useEffect(() => {
    if (!copySourceLayout) return;
    function handler(e: MouseEvent) {
      const t = e.target as HTMLElement | null;
      if (!t) return;
      if (t.closest('[role="dialog"][aria-label*="복사"]')) return;
      if (t.closest('button[aria-label*="복사"]')) return;
      setCopySourceLayout(null);
      setCopyAnchorRect(null);
      setCopyResultMsg("");
    }
    // setTimeout(0) so the click that opened the popup isn't itself the
    // outside click that closes it.
    const id = setTimeout(() => document.addEventListener("mousedown", handler), 0);
    return () => {
      clearTimeout(id);
      document.removeEventListener("mousedown", handler);
    };
  }, [copySourceLayout]);

  async function openCopyPopup(layoutName: string, anchor?: HTMLElement) {
    setCopySourceLayout(layoutName);
    setCopyResultMsg("");
    if (anchor) {
      const r = anchor.getBoundingClientRect();
      setCopyAnchorRect({ x: r.left, y: r.bottom + 4, w: r.width });
    }
    if (otherTemplates !== null) return;
    try {
      const res = await api.listTemplates();
      const list = (res.templates || [])
        .filter((t) => t.id !== templateId)
        .map((t) => ({ id: t.id, name: t.name }));
      setOtherTemplates(list);
    } catch (e) {
      setOtherTemplates([]);
      setCopyResultMsg(e instanceof Error ? e.message : "템플릿 목록을 불러올 수 없습니다");
    }
  }

  async function doCopyLayout(dstTemplateId: number) {
    if (!copySourceLayout || templateId == null) return;
    setCopyingTo(dstTemplateId);
    setCopyResultMsg("");
    try {
      const res = await api.copyLayoutToTemplate(dstTemplateId, templateId, copySourceLayout);
      const dstName = otherTemplates?.find((t) => t.id === dstTemplateId)?.name || `#${dstTemplateId}`;
      setCopyResultMsg(`"${dstName}"에 "${res.layout_name}" 으로 복사됨 ✓`);
    } catch (e) {
      setCopyResultMsg(e instanceof Error ? e.message : "복사 실패");
    } finally {
      setCopyingTo(null);
    }
  }

  function commit(next: TemplateData, currentSnapshot: string) {
    setUndoStack((u) => {
      const trimmed = u.length >= 50 ? u.slice(-49) : u;
      return [...trimmed, currentSnapshot];
    });
    setRedoStack([]);
    setTemplate(next);
    setDirty(true);
  }

  function undo() {
    setUndoStack((u) => {
      if (u.length === 0) return u;
      const prev = u[u.length - 1];
      setRedoStack((r) => [...r, JSON.stringify(templateRef.current)]);
      setTemplate(JSON.parse(prev) as TemplateData);
      setSelectedMeta(null);
      setDirty(true);
      return u.slice(0, -1);
    });
  }

  function redo() {
    setRedoStack((r) => {
      if (r.length === 0) return r;
      const next = r[r.length - 1];
      setUndoStack((u) => [...u, JSON.stringify(templateRef.current)]);
      setTemplate(JSON.parse(next) as TemplateData);
      setSelectedMeta(null);
      setDirty(true);
      return r.slice(0, -1);
    });
  }

  const canvasRef = useRef<HTMLCanvasElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fabricRef = useRef<any>(null);
  // Tracked-in-state copy of the fabric instance so render effects can
  // re-run after the async import("fabric") finishes — refs aren't reactive.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [fabricReady, setFabricReady] = useState<any>(null);
  const templateRef = useRef(template);
  templateRef.current = template;

  // When set true before a commit, the render effect on the *next* tick is
  // skipped — so a drag/resize/nudge doesn't tear down and rebuild every
  // Fabric object (which would lose the active selection and feel jerky).
  const skipRenderRef = useRef(false);
  // Mirror of selectedMeta so the render effect can re-attach the selection
  // after a *real* re-render (e.g. property-panel edit), without including
  // selectedMeta in the effect deps (which would cause spurious re-renders).
  const selectedMetaRef = useRef<FabricMeta | null>(null);
  selectedMetaRef.current = selectedMeta;
  // True while a layout redraw is in flight. canvas.clear() inside the redraw
  // fires selection:cleared; without this gate that would null selectedMeta
  // and dissolve the right panel contents (scroll lost, every property edit
  // collapsed the panel to "선택 없음").
  const inRedrawRef = useRef(false);
  // Monotonic token so a slow async render that finishes after a newer one
  // started doesn't stomp the newer selection.
  const renderTokenRef = useRef(0);

  const canvasW = template.canvas?.width || 1080;
  const canvasH = template.canvas?.height || 1080;
  const scale = DISPLAY_SIZE / Math.max(canvasW, canvasH);

  const layoutNames = useMemo(() => Object.keys(template.layouts || {}), [template.layouts]);

  // Initialize Fabric canvas once
  useEffect(() => {
    let mounted = true;
    (async () => {
      const fabric = await getFabric();
      if (!mounted || !canvasRef.current) return;
      const canvas = new fabric.Canvas(canvasRef.current, {
        width: canvasW * scale,
        height: canvasH * scale,
        backgroundColor: "#FFFFFF",
        selection: true,
      });
      fabricRef.current = canvas;
      setFabricReady(canvas);

      canvas.on("selection:created", (e: { selected?: unknown[] }) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const obj = e.selected?.[0] as any;
        setSelectedMeta(obj?.data || null);
      });
      canvas.on("selection:updated", (e: { selected?: unknown[] }) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const obj = e.selected?.[0] as any;
        setSelectedMeta(obj?.data || null);
      });
      canvas.on("selection:cleared", () => {
        // canvas.clear() inside a property-edit redraw dispatches this — we
        // restore the selection right after, so the null state would only
        // last for one render and erase the panel. Ignore it during redraw.
        if (inRedrawRef.current) return;
        setSelectedMeta(null);
      });

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      canvas.on("object:modified", (e: { target?: any }) => {
        const obj = e.target;
        if (!obj || !obj.data) return;
        applyMovementToTemplate(obj);
      });
    })();

    return () => {
      mounted = false;
      if (fabricRef.current) fabricRef.current.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Resize fabric canvas when template canvas dimensions change
  useEffect(() => {
    if (!fabricReady) return;
    fabricReady.setDimensions({
      width: canvasW * scale,
      height: canvasH * scale,
    });
  }, [fabricReady, canvasW, canvasH, scale]);

  // Snap/alignment guides — wires up object:moving on the live canvas so the
  // dragged object snaps to the nearest canvas edge/center or sibling object
  // edge/center when within 8px (display coords). Draws pink guide lines
  // while dragging and clears them on mouse:up. Only snaps on translate —
  // resize/scale don't snap because picking *which* corner is anchored is
  // non-obvious and tends to fight the user.
  useEffect(() => {
    if (!fabricReady) return;
    const canvas = fabricReady;
    let alive = true;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const guideLines: any[] = [];

    function clearGuides() {
      while (guideLines.length) {
        const line = guideLines.pop();
        try { canvas.remove(line); } catch { /* already gone */ }
      }
    }

    (async () => {
      const fabric = await getFabric();
      if (!alive) return;
      const SNAP_PX = 8;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      function onMoving(e: { target?: any }) {
        const obj = e.target;
        if (!obj || !obj.data) return;
        clearGuides();
        const W = canvas.getWidth();
        const H = canvas.getHeight();
        const objW = (obj.width || 0) * (obj.scaleX || 1);
        const objH = (obj.height || 0) * (obj.scaleY || 1);
        const objL = obj.left || 0;
        const objT = obj.top || 0;
        const objCx = objL + objW / 2;
        const objCy = objT + objH / 2;
        const objR = objL + objW;
        const objB = objT + objH;

        const vTargets: number[] = [0, W / 2, W];
        const hTargets: number[] = [0, H / 2, H];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        for (const other of canvas.getObjects() as any[]) {
          if (other === obj) continue;
          if (!other.data) continue; // skip labels / background chrome
          const oL = other.left || 0;
          const oT = other.top || 0;
          const oW = (other.width || 0) * (other.scaleX || 1);
          const oH = (other.height || 0) * (other.scaleY || 1);
          vTargets.push(oL, oL + oW / 2, oL + oW);
          hTargets.push(oT, oT + oH / 2, oT + oH);
        }

        // Find the closest vertical target across (left|center|right) edges.
        let bestVDist = SNAP_PX + 1;
        let bestVTarget: number | null = null;
        let bestVLeft = objL;
        for (const t of vTargets) {
          const candidates: [number, number][] = [
            [Math.abs(objL - t), t],
            [Math.abs(objCx - t), t - objW / 2],
            [Math.abs(objR - t), t - objW],
          ];
          for (const [d, newL] of candidates) {
            if (d < bestVDist) { bestVDist = d; bestVTarget = t; bestVLeft = newL; }
          }
        }

        let bestHDist = SNAP_PX + 1;
        let bestHTarget: number | null = null;
        let bestHTop = objT;
        for (const t of hTargets) {
          const candidates: [number, number][] = [
            [Math.abs(objT - t), t],
            [Math.abs(objCy - t), t - objH / 2],
            [Math.abs(objB - t), t - objH],
          ];
          for (const [d, newT] of candidates) {
            if (d < bestHDist) { bestHDist = d; bestHTarget = t; bestHTop = newT; }
          }
        }

        if (bestVTarget !== null) {
          obj.left = bestVLeft;
          const line = new fabric.Line([bestVTarget, 0, bestVTarget, H], {
            stroke: "#FF00B8", strokeWidth: 1,
            selectable: false, evented: false, excludeFromExport: true,
            originX: "left", originY: "top",
          });
          canvas.add(line);
          guideLines.push(line);
        }
        if (bestHTarget !== null) {
          obj.top = bestHTop;
          const line = new fabric.Line([0, bestHTarget, W, bestHTarget], {
            stroke: "#FF00B8", strokeWidth: 1,
            selectable: false, evented: false, excludeFromExport: true,
            originX: "left", originY: "top",
          });
          canvas.add(line);
          guideLines.push(line);
        }
        if (bestVTarget !== null || bestHTarget !== null) {
          obj.setCoords();
        }
      }

      function onSettle() { clearGuides(); }
      canvas.on("object:moving", onMoving);
      canvas.on("mouse:up", onSettle);
      canvas.on("object:modified", onSettle);
    })();

    return () => {
      alive = false;
      clearGuides();
    };
  }, [fabricReady]);

  // Re-render when layout selection changes or template changes — but skip
  // when the change came from a canvas-side gesture (drag/resize/nudge) so
  // the active selection survives. After a *real* re-render, re-attach the
  // selection by matching `data.path`.
  useEffect(() => {
    if (!fabricReady || !layoutName) return;
    if (skipRenderRef.current) {
      skipRenderRef.current = false;
      return;
    }
    const layout = template.layouts?.[layoutName];
    if (!layout) return;
    const myToken = ++renderTokenRef.current;
    const targetPath = selectedMetaRef.current?.path;
    inRedrawRef.current = true;
    renderLayoutToCanvas(fabricReady, layoutName, layout, template.brand, scale, canvasW, canvasH).then(() => {
      if (myToken !== renderTokenRef.current) { inRedrawRef.current = false; return; }
      if (targetPath) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const match = fabricReady.getObjects().find((o: any) => o?.data?.path === targetPath);
        if (match) {
          fabricReady.setActiveObject(match);
          fabricReady.requestRenderAll();
        }
      }
      inRedrawRef.current = false;
    });
  }, [fabricReady, layoutName, template, scale, canvasW, canvasH]);

  function setCanvasSize(w: number, h: number) {
    const prev = templateRef.current;
    let next = setByPath(prev, "canvas.width", w) as TemplateData;
    next = setByPath(next, "canvas.height", h) as TemplateData;
    commit(next, JSON.stringify(prev));
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function applyMovementToTemplate(obj: any) {
    const meta: FabricMeta = obj.data;
    if (!meta?.path) return;

    const realX = Math.round(obj.left / scale);
    const realY = Math.round(obj.top / scale);
    const realW = Math.round((obj.width || 0) * (obj.scaleX || 1) / scale);
    const realH = Math.round((obj.height || 0) * (obj.scaleY || 1) / scale);

    // Bake scale back into width/height for non-image objects so the next
    // drag/resize starts from a clean (scaleX=1) state. For FabricImage we
    // leave scaleX/scaleY alone because the image's `width` is the source
    // bitmap pixel count — overwriting it would crop/stretch the bitmap.
    if (obj.type !== "image" && (obj.scaleX !== 1 || obj.scaleY !== 1)) {
      obj.set({
        width: (obj.width || 0) * (obj.scaleX || 1),
        height: (obj.height || 0) * (obj.scaleY || 1),
        scaleX: 1,
        scaleY: 1,
      });
    }

    const prev = templateRef.current;
    const node = getByPath(prev, meta.path) as Record<string, unknown> | undefined;
    if (!node) return;

    let next: TemplateData = prev;
    if (meta.kind === "text_slot" || meta.kind === "decoration") {
      next = setByPath(prev, `${meta.path}.position.x`, realX) as TemplateData;
      next = setByPath(next, `${meta.path}.position.y`, realY) as TemplateData;
      if (realW > 0) next = setByPath(next, `${meta.path}.size.width`, realW) as TemplateData;
      if (realH > 0) next = setByPath(next, `${meta.path}.size.height`, realH) as TemplateData;
    } else if (meta.kind === "grid_origin") {
      next = setByPath(prev, `${meta.path}.x`, realX) as TemplateData;
      next = setByPath(next, `${meta.path}.y`, realY) as TemplateData;
    } else if (meta.kind === "grid_image") {
      next = setByPath(prev, `${meta.path}.x`, realX) as TemplateData;
      next = setByPath(next, `${meta.path}.y`, realY) as TemplateData;
      if (realW > 0) next = setByPath(next, `${meta.path}.width`, realW) as TemplateData;
      if (realH > 0) next = setByPath(next, `${meta.path}.height`, realH) as TemplateData;
    } else {
      return;
    }

    // The fabric object is already at its final spot visually — re-running
    // renderLayoutToCanvas would only clear/rebuild and drop the selection.
    skipRenderRef.current = true;
    commit(next, JSON.stringify(prev));
  }

  function patchTemplate(path: string, value: unknown) {
    const prev = templateRef.current;
    const next = setByPath(prev, path, value) as TemplateData;
    // React state는 비동기라 setTemplate 후에도 다음 render 전까지 ref가
    // prev 상태다. toggleOn처럼 같은 tick에 patchTemplate을 연달아 두 번
    // 호출하는 케이스에서 두 번째가 stale prev로 덮어써서 첫번째 변경이
    // 사라졌다 (외곽선 토글: stroke set → stroke_width set으로 stroke 누락).
    // ref를 즉시 갱신해 같은 tick 내 후속 호출이 누적된 상태를 보게 한다.
    templateRef.current = next;
    commit(next, JSON.stringify(prev));
  }

  // Keyboard-driven position nudge for the active selection. dx/dy are in
  // canvas-coordinate pixels (not display pixels) so 1 = "1px in the saved
  // template", regardless of the editor's zoom-to-fit scale. shift+arrow
  // bumps it to 10px in the caller.
  function nudgeSelected(dx: number, dy: number) {
    if (!selectedMeta || !fabricRef.current) return;
    const active = fabricRef.current.getActiveObject();
    if (!active) return;
    const prev = templateRef.current;
    const node = getByPath(prev, selectedMeta.path) as Record<string, unknown> | undefined;
    if (!node) return;

    // Move the fabric object in place so the canvas updates instantly without
    // a teardown/rebuild — same idea as drag.
    active.left = (active.left || 0) + dx * scale;
    active.top = (active.top || 0) + dy * scale;
    active.setCoords();
    fabricRef.current.requestRenderAll();

    let next: TemplateData = prev;
    if (selectedMeta.kind === "text_slot" || selectedMeta.kind === "decoration") {
      const pos = (node as { position?: { x?: number; y?: number } }).position || {};
      next = setByPath(prev, `${selectedMeta.path}.position.x`, (pos.x || 0) + dx) as TemplateData;
      next = setByPath(next, `${selectedMeta.path}.position.y`, (pos.y || 0) + dy) as TemplateData;
    } else if (selectedMeta.kind === "grid_origin" || selectedMeta.kind === "grid_image") {
      const n = node as { x?: number; y?: number };
      next = setByPath(prev, `${selectedMeta.path}.x`, (n.x || 0) + dx) as TemplateData;
      next = setByPath(next, `${selectedMeta.path}.y`, (n.y || 0) + dy) as TemplateData;
    } else {
      return;
    }
    skipRenderRef.current = true;
    commit(next, JSON.stringify(prev));
  }

  function addTextSlot() {
    if (!layoutName) return;
    const prev = templateRef.current;
    const layout = prev.layouts?.[layoutName];
    const idx = layout?.text_slots?.length ?? 0;
    const slot: TextSlot = {
      role: "headline",
      position: { x: 80, y: 80, anchor: "top-left" },
      size: { width: 920, height: 100 },
      style: { font_size: 32, font_family: "Pretendard", font_weight: "700", fill: "#FFFFFF", text_align: "left", line_height: 1.4 },
    };
    const next = setByPath(prev, `layouts.${layoutName}.text_slots[${idx}]`, slot) as TemplateData;
    commit(next, JSON.stringify(prev));
  }

  function addDecoration() {
    if (!layoutName) return;
    const prev = templateRef.current;
    const layout = prev.layouts?.[layoutName];
    const idx = layout?.decorations?.length ?? 0;
    const dec: Decoration = {
      kind: "shape",
      position: { x: 80, y: 80, anchor: "top-left" },
      size: { width: 200, height: 100 },
      fill: "#FFFFFF",
    };
    const next = setByPath(prev, `layouts.${layoutName}.decorations[${idx}]`, dec) as TemplateData;
    commit(next, JSON.stringify(prev));
  }

  // Convert a grid layout into a flat list of independently positioned
  // decorations + text_slots. The grid concept "one cell rule applies to all"
  // is the reason non-(0,0) cells are locked in the renderer — exploding
  // removes that constraint so every cell becomes individually editable.
  // One-way operation; the grid spec is set to null. Undo restores it.
  // Remove one layout from the template. Keeps at least one layout so the
  // editor and downstream renderer always have something to draw — if the
  // user wants to clear *every* layout they should delete the template
  // itself. If the active layout is the one being removed, switch focus to
  // the first remaining layout. Undoable via the normal Ctrl+Z snapshot.
  function removeLayout(name: string) {
    const prev = templateRef.current;
    const layouts = prev.layouts || {};
    const names = Object.keys(layouts);
    if (names.length <= 1) return;
    if (!(name in layouts)) return;
    const newLayouts: Record<string, LayoutSpec> = {};
    for (const k of names) {
      if (k !== name) newLayouts[k] = layouts[k];
    }
    const next: TemplateData = { ...prev, layouts: newLayouts };
    if (name === layoutName) {
      setLayoutName(Object.keys(newLayouts)[0] || "");
    }
    setSelectedMeta(null);
    setHoveredLayoutName(null);
    commit(next, JSON.stringify(prev));
  }

  // Rename a layout — the layout key is also the display name and shows up in
  // selectedMeta.path (e.g. "layouts.foo.decorations[0]"). To rename safely we
  // (1) rebuild the layouts object preserving insertion order, (2) move
  // layoutName focus if the active layout was renamed, (3) rewrite any in-
  // flight selectedMeta.path so the property panel keeps pointing at the same
  // object. Returns true on success — caller uses this to swap UI back from
  // edit mode.
  function renameLayout(oldName: string, newName: string): boolean {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === oldName) return false;
    const prev = templateRef.current;
    const layouts = prev.layouts || {};
    if (!(oldName in layouts)) return false;
    if (trimmed in layouts) return false;
    const newLayouts: Record<string, LayoutSpec> = {};
    for (const k of Object.keys(layouts)) {
      newLayouts[k === oldName ? trimmed : k] = layouts[k];
    }
    const next: TemplateData = { ...prev, layouts: newLayouts };
    templateRef.current = next;
    if (oldName === layoutName) setLayoutName(trimmed);
    if (selectedMeta && selectedMeta.path.startsWith(`layouts.${oldName}.`)) {
      setSelectedMeta({
        ...selectedMeta,
        path: selectedMeta.path.replace(`layouts.${oldName}.`, `layouts.${trimmed}.`),
      });
    }
    commit(next, JSON.stringify(prev));
    return true;
  }

  function explodeGrid() {
    if (!layoutName) return;
    const prev = templateRef.current;
    const layout = prev.layouts?.[layoutName];
    if (!layout?.grid) return;

    const g = layout.grid;
    const newDecorations: Decoration[] = [...(layout.decorations || [])];
    const newTextSlots: TextSlot[] = [...(layout.text_slots || [])];

    // Heuristic for slot height — texts in fabric flow vertically based on
    // content, so the stored height mostly matters for the property panel.
    // Pick a comfy default proportional to font size.
    const fontSizeOr = (s: { font_size?: number } | undefined | null, fallback: number) =>
      s?.font_size || fallback;
    const titleH = Math.round(fontSizeOr(g.item_box.title_style, 28) * 1.6);
    const subtitleH = Math.round(fontSizeOr(g.item_box.subtitle_style, 18) * 1.6);
    const descriptionH = Math.round(fontSizeOr(g.item_box.description_style, 16) * 3.2);

    for (let r = 0; r < g.rows; r++) {
      for (let c = 0; c < g.cols; c++) {
        const cellX = g.origin.x + c * (g.cell_size.width + g.gap_x);
        const cellY = g.origin.y + r * (g.cell_size.height + g.gap_y);
        const ia = g.item_box.image_area;
        const tag = `r${r}c${c}`;

        // Image slot (placeholder — user can drag-drop a PNG onto it)
        newDecorations.push({
          kind: "image",
          position: { x: cellX + ia.x, y: cellY + ia.y, anchor: "top-left" },
          size: { width: ia.width, height: ia.height },
          src: null,
        });

        if (g.item_box.title_style) {
          newTextSlots.push({
            role: `cell_title_${tag}`,
            position: { x: cellX, y: cellY + (g.item_box.title_offset_y || 0), anchor: "top-left" },
            size: { width: g.cell_size.width, height: titleH },
            style: g.item_box.title_style,
          });
        }
        if (g.item_box.subtitle_style && g.item_box.subtitle_offset_y != null) {
          newTextSlots.push({
            role: `cell_subtitle_${tag}`,
            position: { x: cellX, y: cellY + g.item_box.subtitle_offset_y, anchor: "top-left" },
            size: { width: g.cell_size.width, height: subtitleH },
            style: g.item_box.subtitle_style,
          });
        }
        if (g.item_box.description_style && g.item_box.description_offset_y != null) {
          newTextSlots.push({
            role: `cell_description_${tag}`,
            position: { x: cellX, y: cellY + g.item_box.description_offset_y, anchor: "top-left" },
            size: { width: g.cell_size.width, height: descriptionH },
            style: g.item_box.description_style,
          });
        }
      }
    }

    let next: TemplateData = prev;
    next = setByPath(next, `layouts.${layoutName}.decorations`, newDecorations) as TemplateData;
    next = setByPath(next, `layouts.${layoutName}.text_slots`, newTextSlots) as TemplateData;
    next = setByPath(next, `layouts.${layoutName}.grid`, null) as TemplateData;
    setSelectedMeta(null);
    commit(next, JSON.stringify(prev));
  }

  const pngInputRef = useRef<HTMLInputElement>(null);
  const [uploadingAsset, setUploadingAsset] = useState(false);
  // Tracks whether a file is currently being dragged over the canvas drop
  // zone, so we can show the highlighted border without flicker. We bump a
  // counter (not a boolean) because dragenter/dragleave fire for every child
  // element the cursor crosses — a counter only hits zero when the drag has
  // truly left the wrapper.
  const [dropDepth, setDropDepth] = useState(0);

  // Shared upload pipeline for both the file picker button and drag-and-drop.
  // dropPos (canvas-coordinate pixels) centers the inserted image around the
  // drop point; omit it and the image lands in the canvas center.
  async function uploadAndAddPng(file: File, dropPos?: { x: number; y: number } | null) {
    if (!layoutName) return;
    if (!file.type.startsWith("image/")) {
      alert("이미지 파일만 업로드 가능합니다");
      return;
    }
    setUploadingAsset(true);
    try {
      const { path } = await api.uploadTemplateAsset(file);

      // Probe natural dimensions so the inserted box keeps the PNG's aspect ratio.
      // Fall back to a 200x200 square if the probe fails (cross-origin, decode error).
      let naturalW = 200;
      let naturalH = 200;
      try {
        const dims = await new Promise<{ w: number; h: number }>((resolve, reject) => {
          const img = new window.Image();
          img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight });
          img.onerror = reject;
          img.src = path;
        });
        if (dims.w > 0 && dims.h > 0) {
          // Cap the longer side so a huge upload doesn't fill the slide.
          const maxSide = Math.min(canvasW, canvasH) * 0.35;
          const scaleDown = Math.min(1, maxSide / Math.max(dims.w, dims.h));
          naturalW = Math.round(dims.w * scaleDown);
          naturalH = Math.round(dims.h * scaleDown);
        }
      } catch {
        // ignore — fall back to 200×200
      }

      const x = dropPos
        ? Math.max(0, Math.min(canvasW - naturalW, Math.round(dropPos.x - naturalW / 2)))
        : Math.round((canvasW - naturalW) / 2);
      const y = dropPos
        ? Math.max(0, Math.min(canvasH - naturalH, Math.round(dropPos.y - naturalH / 2)))
        : Math.round((canvasH - naturalH) / 2);

      const prev = templateRef.current;
      const layout = prev.layouts?.[layoutName];
      const idx = layout?.decorations?.length ?? 0;
      const dec: Decoration = {
        kind: "image",
        position: { x, y, anchor: "top-left" },
        size: { width: naturalW, height: naturalH },
        src: path,
      };
      const next = setByPath(prev, `layouts.${layoutName}.decorations[${idx}]`, dec) as TemplateData;
      commit(next, JSON.stringify(prev));
    } catch (err) {
      alert(err instanceof Error ? err.message : "PNG 업로드 실패");
    } finally {
      setUploadingAsset(false);
    }
  }

  async function handlePngPicked(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Reset the input so picking the same file twice still fires onChange.
    e.target.value = "";
    if (!file) return;
    await uploadAndAddPng(file);
  }

  // Convert a drop event's screen coordinates to template-canvas pixels using
  // the underlying <canvas> element's bounding rect — accounts for the
  // editor's display-fit scale and any wrapper padding.
  // Replace the selected image decoration's src with a freshly uploaded file.
  // Reuses the same template-assets upload endpoint as the toolbar PNG picker.
  const [replaceBusy, setReplaceBusy] = useState(false);
  async function replaceSelectedImage(file: File) {
    if (!selectedMeta) return;
    if (!/\.decorations\[\d+\]$/.test(selectedMeta.path)) return;
    if (!file.type.startsWith("image/")) { alert("이미지 파일만 가능"); return; }
    setReplaceBusy(true);
    try {
      const { path } = await api.uploadTemplateAsset(file);
      patchTemplate(`${selectedMeta.path}.src`, path);
    } catch (e) {
      alert(e instanceof Error ? e.message : "교체 실패");
    } finally {
      setReplaceBusy(false);
    }
  }

  // Run /api/images/cutout on the selected image's current src; swap in the
  // returned cutout URL when it lands.
  const [cutoutBusy, setCutoutBusy] = useState(false);
  async function cutoutSelectedImage(mode: "standard" | "generative") {
    if (!selectedMeta) return;
    if (!/\.decorations\[\d+\]$/.test(selectedMeta.path)) return;
    const d = getByPath(templateRef.current, selectedMeta.path) as { src?: string | null } | undefined;
    if (!d?.src) return;
    setCutoutBusy(true);
    try {
      const { url } = await api.cutoutImage({ source_url: d.src, mode });
      patchTemplate(`${selectedMeta.path}.src`, url);
    } catch (e) {
      alert(e instanceof Error ? e.message : "누끼 제거 실패");
    } finally {
      setCutoutBusy(false);
    }
  }

  function dropEventToCanvasCoords(e: React.DragEvent<HTMLDivElement>): { x: number; y: number } | null {
    if (!canvasRef.current) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / scale;
    const y = (e.clientY - rect.top) / scale;
    return { x, y };
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    // Required to enable drop. Setting dropEffect signals to the OS that this
    // is a copy operation (browser shows the "+" cursor).
    if (Array.from(e.dataTransfer.types || []).includes("Files")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  }
  function handleDragEnter(e: React.DragEvent<HTMLDivElement>) {
    if (Array.from(e.dataTransfer.types || []).includes("Files")) {
      e.preventDefault();
      setDropDepth((d) => d + 1);
    }
  }
  function handleDragLeave(e: React.DragEvent<HTMLDivElement>) {
    if (Array.from(e.dataTransfer.types || []).includes("Files")) {
      e.preventDefault();
      setDropDepth((d) => Math.max(0, d - 1));
    }
  }
  async function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDropDepth(0);
    const files = Array.from(e.dataTransfer.files || []);
    const imageFile = files.find((f) => f.type.startsWith("image/"));
    if (!imageFile) return;
    const pos = dropEventToCanvasCoords(e);
    await uploadAndAddPng(imageFile, pos);
  }

  // Reorder the active selection within its array so it renders earlier
  // (back) or later (front). Text slots and decorations live in separate
  // arrays and the renderer draws decorations first, so this only changes
  // z-order *within* the same kind — it can't put a text slot behind a shape.
  function moveLayer(direction: "front" | "back" | "forward" | "backward") {
    if (!selectedMeta) return;
    const m = selectedMeta.path.match(/^(layouts\.[^.]+\.(?:decorations|text_slots))\[(\d+)\]$/);
    if (!m) return;
    const arrayPath = m[1];
    const idx = Number(m[2]);
    const prev = templateRef.current;
    const arr = getByPath(prev, arrayPath) as unknown[] | undefined;
    if (!Array.isArray(arr) || arr.length < 2) return;

    let newIdx: number;
    if (direction === "front") newIdx = arr.length - 1;
    else if (direction === "back") newIdx = 0;
    else if (direction === "forward") newIdx = Math.min(idx + 1, arr.length - 1);
    else newIdx = Math.max(idx - 1, 0);
    if (newIdx === idx) return;

    const newArr = arr.slice();
    const [moved] = newArr.splice(idx, 1);
    newArr.splice(newIdx, 0, moved);
    const next = setByPath(prev, arrayPath, newArr) as TemplateData;
    // The selection's path index just changed — point selectedMeta at the
    // new slot so the post-render reselect finds the right object.
    setSelectedMeta({ ...selectedMeta, path: `${arrayPath}[${newIdx}]` });
    commit(next, JSON.stringify(prev));
  }

  function deleteSelected() {
    if (!selectedMeta) return;
    if (selectedMeta.kind !== "text_slot" && selectedMeta.kind !== "decoration") return;
    const prev = templateRef.current;
    const next = removeArrayItem(prev, selectedMeta.path) as TemplateData;
    setSelectedMeta(null);
    commit(next, JSON.stringify(prev));
  }

  // Keyboard shortcuts: Delete/Backspace, Ctrl+Z, Ctrl+Y / Ctrl+Shift+Z
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const inField = !!target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT");
      const mod = e.ctrlKey || e.metaKey;

      if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
        return;
      }
      if (mod && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) {
        e.preventDefault();
        redo();
        return;
      }
      if (inField) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selectedMeta) {
        e.preventDefault();
        deleteSelected();
        return;
      }
      // Arrow-key nudge — 1px per press, 10px with shift
      if (selectedMeta && (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "ArrowUp" || e.key === "ArrowDown")) {
        const step = e.shiftKey ? 10 : 1;
        let dx = 0, dy = 0;
        if (e.key === "ArrowLeft") dx = -step;
        else if (e.key === "ArrowRight") dx = step;
        else if (e.key === "ArrowUp") dy = -step;
        else dy = step;
        e.preventDefault();
        nudgeSelected(dx, dy);
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedMeta]);

  async function handleSave() {
    setSaving(true);
    setSaveError("");
    try {
      await onSave(templateRef.current);
      setDirty(false);
      setLastSavedAt(Date.now());
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  // Auto-save: 1s after the last edit, push the current template to the
  // server. Re-arms on every change so a continuous edit (e.g. dragging a
  // slider) doesn't trigger a flood of saves — only one fires when the user
  // pauses. Skips while a save is already in-flight; will re-arm when that
  // save finishes if more edits arrived in the meantime.
  useEffect(() => {
    if (!dirty || saving) return;
    const handle = setTimeout(() => { void handleSave(); }, 1000);
    return () => clearTimeout(handle);
    // handleSave reads templateRef.current — no need to depend on `template`
    // identity since the ref always points at the latest. We DO depend on
    // `template` so the debounce timer resets on every edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, saving, template]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "var(--bg-app)" }}>
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 20px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-elevated)",
        }}
      >
        <button
          onClick={onClose}
          style={{
            padding: "6px 10px",
            fontSize: 12,
            color: "var(--text-secondary)",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            cursor: "pointer",
          }}
        >
          ← 목록
        </button>
        <input
          value={template.name}
          onChange={(e) => {
            setTemplate((p) => ({ ...p, name: e.target.value }));
            setDirty(true);
          }}
          style={{
            flex: 1,
            maxWidth: 360,
            padding: "6px 10px",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            color: "var(--text-primary)",
            fontSize: 13,
            fontWeight: 500,
          }}
        />
        <CanvasSizeSelector width={canvasW} height={canvasH} onChange={setCanvasSize} />
        <button
          onClick={undo}
          disabled={undoStack.length === 0}
          title="실행취소 (Ctrl+Z)"
          style={{
            padding: "5px 10px",
            fontSize: 11,
            color: "var(--text-secondary)",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            cursor: undoStack.length === 0 ? "not-allowed" : "pointer",
            opacity: undoStack.length === 0 ? 0.4 : 1,
          }}
        >
          ↶
        </button>
        <button
          onClick={redo}
          disabled={redoStack.length === 0}
          title="다시실행 (Ctrl+Y)"
          style={{
            padding: "5px 10px",
            fontSize: 11,
            color: "var(--text-secondary)",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            cursor: redoStack.length === 0 ? "not-allowed" : "pointer",
            opacity: redoStack.length === 0 ? 0.4 : 1,
          }}
        >
          ↷
        </button>
        <div style={{ width: 1, height: 18, background: "var(--border)", margin: "0 4px" }} />
        <button
          onClick={addTextSlot}
          style={{
            padding: "5px 10px",
            fontSize: 11,
            color: "var(--text-secondary)",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            cursor: "pointer",
          }}
          title="텍스트 슬롯 추가"
        >
          + 텍스트
        </button>
        <button
          onClick={addDecoration}
          style={{
            padding: "5px 10px",
            fontSize: 11,
            color: "var(--text-secondary)",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            cursor: "pointer",
          }}
          title="장식 사각형 추가"
        >
          + 장식
        </button>
        {(() => {
          const hasGrid = !!(layoutName && template.layouts?.[layoutName]?.grid);
          if (!hasGrid) return null;
          return (
            <button
              onClick={explodeGrid}
              title="그리드를 셀별 개별 도형/텍스트로 변환 (Ctrl+Z로 되돌리기)"
              style={{
                padding: "5px 10px",
                fontSize: 11,
                color: "var(--text-secondary)",
                background: "var(--bg-overlay)",
                border: "1px solid var(--border)",
                borderRadius: 5,
                cursor: "pointer",
              }}
            >
              ⌗ 그리드 해제
            </button>
          );
        })()}
        <button
          onClick={() => pngInputRef.current?.click()}
          disabled={uploadingAsset || !layoutName}
          style={{
            padding: "5px 10px",
            fontSize: 11,
            color: "var(--text-secondary)",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            cursor: uploadingAsset || !layoutName ? "not-allowed" : "pointer",
            opacity: uploadingAsset || !layoutName ? 0.5 : 1,
          }}
          title="PNG 이미지 업로드 (로고/CTA 배지 등)"
        >
          {uploadingAsset ? "업로드 중…" : "+ PNG"}
        </button>
        <input
          ref={pngInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/svg+xml"
          onChange={handlePngPicked}
          style={{ display: "none" }}
        />
        {(() => {
          const reorderable = !!selectedMeta && /\.(decorations|text_slots)\[\d+\]$/.test(selectedMeta.path);
          const layerBtn = (label: string, dir: "front" | "back" | "forward" | "backward", title: string) => (
            <button
              key={dir}
              onClick={() => moveLayer(dir)}
              disabled={!reorderable}
              title={title}
              style={{
                padding: "5px 8px",
                fontSize: 11,
                color: "var(--text-secondary)",
                background: "var(--bg-overlay)",
                border: "1px solid var(--border)",
                borderRadius: 5,
                cursor: reorderable ? "pointer" : "not-allowed",
                opacity: reorderable ? 1 : 0.4,
              }}
            >
              {label}
            </button>
          );
          return (
            <>
              {layerBtn("⤒", "front", "맨 앞으로")}
              {layerBtn("↑", "forward", "한 단계 앞으로")}
              {layerBtn("↓", "backward", "한 단계 뒤로")}
              {layerBtn("⤓", "back", "맨 뒤로")}
            </>
          );
        })()}
        <button
          onClick={deleteSelected}
          disabled={!selectedMeta || (selectedMeta.kind !== "text_slot" && selectedMeta.kind !== "decoration")}
          style={{
            padding: "5px 10px",
            fontSize: 11,
            color: "var(--red)",
            background: "var(--red-muted)",
            border: "none",
            borderRadius: 5,
            cursor: !selectedMeta || (selectedMeta.kind !== "text_slot" && selectedMeta.kind !== "decoration") ? "not-allowed" : "pointer",
            opacity: !selectedMeta || (selectedMeta.kind !== "text_slot" && selectedMeta.kind !== "decoration") ? 0.4 : 1,
          }}
          title="선택 요소 삭제 (Delete)"
        >
          삭제
        </button>

        <div style={{ flex: 1 }} />
        <AutoSaveStatus dirty={dirty} saving={saving} saveError={saveError} lastSavedAt={lastSavedAt} />
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          style={{
            padding: "6px 16px",
            fontSize: 12,
            fontWeight: 500,
            color: "white",
            background: "var(--accent)",
            border: "none",
            borderRadius: 5,
            cursor: !dirty || saving ? "not-allowed" : "pointer",
            opacity: !dirty || saving ? 0.5 : 1,
          }}
        >
          {saving ? "저장 중..." : "저장"}
        </button>
      </div>

      {/* Layout picker — clickable mini previews instead of a dropdown */}
      {layoutNames.length > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "8px 20px",
            borderBottom: "1px solid var(--border)",
            background: "var(--bg-subtle)",
            overflowX: "auto",
          }}
        >
          <span style={{ fontSize: 11, color: "var(--text-tertiary)", flexShrink: 0 }}>레이아웃</span>
          {layoutNames.map((n) => {
            const canDelete = layoutNames.length > 1;
            const isHovered = hoveredLayoutName === n;
            const showDelete = canDelete && isHovered;
            const showCopy = isHovered && templateId != null;
            const isCopyOpen = copySourceLayout === n;
            return (
              <div
                key={n}
                onMouseEnter={() => setHoveredLayoutName(n)}
                onMouseLeave={() => setHoveredLayoutName((cur) => (cur === n ? null : cur))}
                style={{ position: "relative", flexShrink: 0 }}
              >
                <LayoutMiniPreview
                  template={template}
                  layoutName={n}
                  size={64}
                  active={n === layoutName}
                  onClick={() => setLayoutName(n)}
                  onRename={(next) => renameLayout(n, next)}
                  existingNames={layoutNames}
                />
                {templateId != null && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      const wrapper = (e.currentTarget as HTMLElement).parentElement;
                      openCopyPopup(n, wrapper || undefined);
                    }}
                    title={`레이아웃 "${n}" 다른 템플릿으로 복사`}
                    aria-label={`레이아웃 ${n} 복사`}
                    style={{
                      position: "absolute",
                      top: -6,
                      left: -6,
                      width: 18,
                      height: 18,
                      padding: 0,
                      borderRadius: "50%",
                      background: "var(--accent, #3CC8FF)",
                      color: "white",
                      border: "2px solid var(--bg-subtle)",
                      fontSize: 11,
                      lineHeight: 1,
                      cursor: "pointer",
                      opacity: showCopy || isCopyOpen ? 1 : 0,
                      pointerEvents: showCopy || isCopyOpen ? "auto" : "none",
                      transition: "opacity 100ms",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      boxShadow: "0 1px 4px rgba(0,0,0,0.4)",
                    }}
                  >
                    ⎘
                  </button>
                )}
                {/* Popup rendered via portal further down to escape overflow clipping. */}
                {canDelete && (
                  <button
                    onClick={() => removeLayout(n)}
                    title={`레이아웃 "${n}" 삭제 (Ctrl+Z로 복구)`}
                    aria-label={`레이아웃 ${n} 삭제`}
                    style={{
                      position: "absolute",
                      top: -6,
                      right: -6,
                      width: 18,
                      height: 18,
                      padding: 0,
                      borderRadius: "50%",
                      background: "var(--red, #e85b5b)",
                      color: "white",
                      border: "2px solid var(--bg-subtle)",
                      fontSize: 11,
                      lineHeight: 1,
                      cursor: "pointer",
                      opacity: showDelete ? 1 : 0,
                      pointerEvents: showDelete ? "auto" : "none",
                      transition: "opacity 100ms",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      boxShadow: "0 1px 4px rgba(0,0,0,0.4)",
                    }}
                  >
                    ×
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Body */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Center: canvas */}
        <div
          onDragOver={handleDragOver}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          style={{
            flex: 1,
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-subtle)",
            padding: 24,
          }}
        >
          <div
            style={{
              borderRadius: 8,
              boxShadow: "0 8px 40px rgba(0,0,0,0.4)",
              overflow: "hidden",
              background: "#FFFFFF",
              outline: dropDepth > 0 ? "3px dashed var(--accent)" : "none",
              outlineOffset: 4,
              transition: "outline-color 120ms",
            }}
          >
            <canvas ref={canvasRef} />
          </div>
          {dropDepth > 0 && (
            <div
              style={{
                position: "absolute",
                top: 16,
                left: "50%",
                transform: "translateX(-50%)",
                padding: "8px 16px",
                fontSize: 12,
                fontWeight: 500,
                color: "white",
                background: "var(--accent)",
                borderRadius: 999,
                pointerEvents: "none",
                boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
              }}
            >
              여기에 놓으면 이미지가 추가됩니다
            </div>
          )}
          {uploadingAsset && (
            <div
              style={{
                position: "absolute",
                bottom: 16,
                left: "50%",
                transform: "translateX(-50%)",
                padding: "6px 14px",
                fontSize: 12,
                color: "var(--text-secondary)",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: 999,
                pointerEvents: "none",
              }}
            >
              업로드 중…
            </div>
          )}
        </div>

        {/* Right: property panel */}
        <LayoutPropertyPanel
          template={template}
          layoutName={layoutName}
          selected={selectedMeta}
          onChange={patchTemplate}
          onMoveLayer={moveLayer}
          onDeleteSelected={deleteSelected}
          onReplaceImage={replaceSelectedImage}
          onCutoutImage={cutoutSelectedImage}
          imageBusy={{ replace: replaceBusy, cutout: cutoutBusy }}
        />
      </div>

      {/* Copy-layout target picker — portaled to body to escape the layout-bar
          overflow clipping. */}
      {copySourceLayout && copyAnchorRect && typeof document !== "undefined" &&
        createPortal(
          <div
            role="dialog"
            aria-label="레이아웃 복사 대상 선택"
            style={{
              position: "fixed",
              top: copyAnchorRect.y,
              left: copyAnchorRect.x,
              zIndex: 9999,
              minWidth: Math.max(220, copyAnchorRect.w + 60),
              maxHeight: 320,
              overflowY: "auto",
              background: "var(--bg-elevated, #2a2a2a)",
              border: "1px solid var(--border, #444)",
              borderRadius: 6,
              padding: 6,
              boxShadow: "0 4px 16px rgba(0,0,0,0.45)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "4px 6px 6px",
                borderBottom: "1px solid var(--border, #444)",
                marginBottom: 4,
              }}
            >
              <span style={{ fontSize: 11, color: "var(--text-secondary, #aaa)" }}>
                &quot;{copySourceLayout}&quot; → 대상 템플릿 선택
              </span>
              <button
                onClick={() => { setCopySourceLayout(null); setCopyAnchorRect(null); }}
                aria-label="닫기"
                style={{
                  width: 18,
                  height: 18,
                  padding: 0,
                  background: "transparent",
                  border: "none",
                  color: "var(--text-tertiary, #888)",
                  fontSize: 13,
                  cursor: "pointer",
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>
            {otherTemplates === null && (
              <div style={{ padding: "8px 6px", fontSize: 11, color: "var(--text-tertiary, #888)" }}>
                로딩 중...
              </div>
            )}
            {otherTemplates !== null && otherTemplates.length === 0 && (
              <div style={{ padding: "8px 6px", fontSize: 11, color: "var(--text-tertiary, #888)" }}>
                복사 가능한 다른 템플릿이 없습니다
              </div>
            )}
            {otherTemplates?.map((t) => (
              <button
                key={t.id}
                onClick={() => doCopyLayout(t.id)}
                disabled={copyingTo != null}
                style={{
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  padding: "6px 8px",
                  background: "transparent",
                  border: "none",
                  color: "var(--text-primary, #fff)",
                  fontSize: 12,
                  cursor: copyingTo != null ? "wait" : "pointer",
                  borderRadius: 4,
                  opacity: copyingTo != null && copyingTo !== t.id ? 0.5 : 1,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-overlay, #3a3a3a)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                {copyingTo === t.id ? "복사 중..." : t.name}
              </button>
            ))}
            {copyResultMsg && (
              <div
                style={{
                  padding: "6px 8px",
                  marginTop: 4,
                  fontSize: 11,
                  color: copyResultMsg.includes("✓") ? "#4ade80" : "#e85b5b",
                  borderTop: "1px solid var(--border, #444)",
                }}
              >
                {copyResultMsg}
              </div>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}

// Re-export so we don't break import chains. (Used by some property forms.)
export type { LayoutSpec };

/** Auto-save indicator pill in the toolbar.
 *
 * States, in priority order:
 *   error    — surfaces the message so the user knows their work isn't safe
 *   saving   — a save is in-flight right now
 *   dirty    — edited; debounce timer is counting down
 *   saved    — clean and we've successfully saved at least once this session
 *   idle     — clean, never saved (just opened the editor) → render nothing
 */
function AutoSaveStatus({
  dirty,
  saving,
  saveError,
  lastSavedAt,
}: {
  dirty: boolean;
  saving: boolean;
  saveError: string;
  lastSavedAt: number | null;
}) {
  const baseStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    fontSize: 11,
    padding: "4px 10px",
    borderRadius: 999,
    fontWeight: 500,
  };
  const dot = (color: string): React.CSSProperties => ({
    width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0,
  });

  if (saveError) {
    return (
      <span style={{ ...baseStyle, color: "#e85b5b", background: "rgba(232,91,91,0.12)" }}>
        <span style={dot("#e85b5b")} />
        저장 실패 · {saveError.length > 30 ? saveError.slice(0, 30) + "…" : saveError}
      </span>
    );
  }
  if (saving) {
    return (
      <span style={{ ...baseStyle, color: "var(--accent-text, var(--accent))", background: "rgba(94,106,210,0.12)" }}>
        <span style={dot("var(--accent)")} />
        저장 중…
      </span>
    );
  }
  if (dirty) {
    return (
      <span style={{ ...baseStyle, color: "var(--text-tertiary)", background: "var(--bg-overlay)" }}>
        <span style={dot("#f0b429")} />
        변경됨 · 자동 저장 대기
      </span>
    );
  }
  if (lastSavedAt) {
    return (
      <span style={{ ...baseStyle, color: "var(--text-tertiary)" }}>
        <span style={dot("rgb(140,200,160)")} />
        저장됨
      </span>
    );
  }
  return null;
}
