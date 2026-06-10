"use client";

import { useEffect, useRef, useState } from "react";
import { getFabric } from "@/lib/fabric";
import { renderLayoutToCanvas } from "./renderer";
import { gridNameHint, type TemplateData } from "./types";

interface Props {
  template: TemplateData;
  layoutName: string;
  size?: number;     // longest side, in px
  active?: boolean;
  onClick?: () => void;
  // Returns true when the rename was accepted (so the input can close).
  // Returning false keeps edit mode open — typically because the new name
  // collides with an existing layout or is empty.
  onRename?: (next: string) => boolean;
  existingNames?: string[];
}

/** A clickable, static mini-canvas of one layout. Drop-in replacement for
 *  the previous "<select>" layout picker. */
export function LayoutMiniPreview({ template, layoutName, size = 64, active, onClick, onRename, existingNames }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(layoutName);
  const inputRef = useRef<HTMLInputElement>(null);
  // Sync draft when the layout name changes externally (e.g. after rename or
  // when selection moves to a different layout).
  useEffect(() => { setDraft(layoutName); }, [layoutName]);

  function startEdit(e: React.MouseEvent) {
    if (!onRename) return;
    e.stopPropagation();
    setDraft(layoutName);
    setEditing(true);
    // Focus next tick so the input exists in the DOM.
    setTimeout(() => inputRef.current?.select(), 0);
  }
  function commitEdit() {
    if (!onRename) { setEditing(false); return; }
    const trimmed = draft.trim();
    if (!trimmed || trimmed === layoutName) { setEditing(false); setDraft(layoutName); return; }
    if (existingNames && existingNames.includes(trimmed)) {
      // Collision — keep input open so the user can adjust.
      inputRef.current?.focus();
      return;
    }
    const ok = onRename(trimmed);
    if (ok) setEditing(false);
  }
  function cancelEdit() {
    setEditing(false);
    setDraft(layoutName);
  }

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let fc: any = null;

    (async () => {
      const fabric = await getFabric();
      if (cancelled || !canvasRef.current) return;

      const cw = template.canvas?.width || 1080;
      const ch = template.canvas?.height || 1080;
      const scale = size / Math.max(cw, ch);

      fc = new fabric.StaticCanvas(canvasRef.current, {
        width: cw * scale,
        height: ch * scale,
        backgroundColor: template.brand?.background_color || "#222222",
      });

      const layout = template.layouts?.[layoutName];
      if (layout) {
        await renderLayoutToCanvas(fc, layoutName, layout, template.brand, scale, cw, ch);
      }
    })();

    return () => {
      cancelled = true;
      if (fc) fc.dispose();
    };
  }, [template, layoutName, size]);

  return (
    <button
      onClick={onClick}
      title={`${layoutName}${gridNameHint(layoutName)}`}
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 4,
        padding: 4,
        borderRadius: 6,
        background: active ? "var(--bg-overlay)" : "transparent",
        border: active ? "1.5px solid var(--accent)" : "1px solid var(--border)",
        cursor: "pointer",
        transition: "border-color 100ms, background 100ms",
      }}
      onMouseEnter={(e) => {
        if (!active) e.currentTarget.style.borderColor = "var(--border-strong)";
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.borderColor = "var(--border)";
      }}
    >
      <div style={{ borderRadius: 3, overflow: "hidden", lineHeight: 0 }}>
        <canvas ref={canvasRef} />
      </div>
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Enter") commitEdit();
            else if (e.key === "Escape") cancelEdit();
          }}
          onBlur={commitEdit}
          style={{
            fontSize: 10,
            maxWidth: size + 8,
            width: size + 8,
            padding: "1px 4px",
            border: "1px solid var(--accent)",
            borderRadius: 3,
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            textAlign: "center",
            outline: "none",
          }}
        />
      ) : (
        <span
          onDoubleClick={onRename ? startEdit : undefined}
          title={onRename ? "더블클릭하여 이름 변경" : layoutName}
          style={{
            fontSize: 10,
            color: active ? "var(--text-primary)" : "var(--text-tertiary)",
            maxWidth: size + 8,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            cursor: onRename ? "text" : "inherit",
          }}
        >
          {layoutName}
        </span>
      )}
    </button>
  );
}
