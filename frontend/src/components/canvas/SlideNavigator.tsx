"use client";

import { Fragment, useState } from "react";
import type { SlideData } from "@/lib/types";
import { SlideThumbnail } from "./SlideThumbnail";

const THUMB_SIZE = 64;

interface SlideNavigatorProps {
  slides: SlideData[];
  currentIndex: number;
  onSelect: (index: number) => void;
  onAdd: () => void;
  onDuplicate: () => void;
  onRemove: (index: number) => void;
  // Drag-and-drop reorder. `dropBefore` is the slot in the original array
  // where the moved slide should land (0..slides.length).
  onReorder?: (from: number, dropBefore: number) => void;
}

export function SlideNavigator({
  slides,
  currentIndex,
  onSelect,
  onAdd,
  onDuplicate,
  onRemove,
  onReorder,
}: SlideNavigatorProps) {
  // Drag-state: which thumb is being dragged, and where it would drop.
  // dropBefore = index in the ORIGINAL array where the moved thumb should
  // land (so dropBefore = slides.length means drop at the very end).
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dropBefore, setDropBefore] = useState<number | null>(null);
  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderTop: "1px solid var(--border)",
        padding: "10px 16px",
      }}
    >
      <div
        style={{ display: "flex", alignItems: "center", gap: 8, overflowX: "auto", position: "relative" }}
        onDragLeave={(e) => {
          // Only reset when the cursor leaves the whole strip, not when
          // crossing between thumbs (those fire their own leave events).
          const rel = e.relatedTarget as Node | null;
          if (rel && (e.currentTarget as HTMLDivElement).contains(rel)) return;
          setDropBefore(null);
        }}
        onDrop={(e) => {
          // Catch drops that land in the gap BETWEEN thumbs (the indicator
          // overlays don't capture events because pointerEvents:none).
          if (!onReorder || dragIndex === null || dropBefore === null) return;
          e.preventDefault();
          onReorder(dragIndex, dropBefore);
          setDragIndex(null); setDropBefore(null);
        }}
      >
        {slides.map((slide, index) => {
          const isDarkBg = typeof slide.background === "string" && /^#?(0[0-9a-f]|1[0-9a-f]|2[0-9a-f])/i.test(slide.background);
          const badgeColor = isDarkBg ? "rgba(255,255,255,0.95)" : "rgba(0,0,0,0.7)";
          const showLeftIndicator = dragIndex !== null && dropBefore === index && dragIndex !== index && dragIndex !== index - 1;
          const showRightIndicator = dragIndex !== null && dropBefore === index + 1 && index === slides.length - 1 && dragIndex !== index && dragIndex !== index + 1;
          // Thumbnail box matches the slide's aspect ratio (e.g. 4:5 for an
          // Instagram carousel) instead of a forced square — so the preview
          // looks like the actual work, not a letter-boxed crop. The longer
          // side fits THUMB_SIZE; SlideThumbnail (size=THUMB_SIZE) then fills it.
          const sw = Number(slide.width) || 1080;
          const sh = Number(slide.height) || 1080;
          const longSide = Math.max(sw, sh) || 1080;
          const boxW = Math.round(THUMB_SIZE * sw / longSide);
          const boxH = Math.round(THUMB_SIZE * sh / longSide);
        return (
          <Fragment key={index}>
          {showLeftIndicator && (
            <div
              data-drop-indicator="left"
              style={{
                width: 3,
                height: THUMB_SIZE + 8,
                background: "#3CC8FF",
                borderRadius: 2,
                flexShrink: 0,
                marginLeft: -5, marginRight: -6,
                pointerEvents: "none",
                boxShadow: "0 0 6px rgba(60,200,255,0.7)",
              }}
            />
          )}
          <div
            data-slide-thumb={index}
            tabIndex={0}
            role="option"
            aria-selected={index === currentIndex}
            draggable={!!onReorder}
            onDragStart={(e) => {
              if (!onReorder) return;
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", String(index));
              setDragIndex(index);
            }}
            onDragOver={(e) => {
              if (!onReorder || dragIndex === null) return;
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
              // Decide whether to land BEFORE or AFTER this thumb based on
              // which half of the thumb the cursor sits over.
              const r = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
              const halfX = r.left + r.width / 2;
              const slot = e.clientX < halfX ? index : index + 1;
              if (slot !== dropBefore) setDropBefore(slot);
            }}
            onDragLeave={() => {
              // Don't reset here — the bar's onDragLeave below handles it.
              // Per-thumb leave fires every time the cursor crosses between
              // adjacent thumbs, which would flicker the indicator.
            }}
            onDragEnd={() => { setDragIndex(null); setDropBefore(null); }}
            onDrop={(e) => {
              if (!onReorder || dragIndex === null) return;
              e.preventDefault();
              // Stop propagation so the strip-level onDrop doesn't fire the
              // same reorder a second time when the drop lands on a thumb.
              e.stopPropagation();
              const target = dropBefore ?? index;
              onReorder(dragIndex, target);
              setDragIndex(null); setDropBefore(null);
            }}
            onClick={(e) => {
              onSelect(index);
              // Move focus to the clicked thumb so subsequent ←/→ navigate.
              (e.currentTarget as HTMLDivElement).focus();
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft" || e.key === "ArrowRight"
                  || e.key === "Home" || e.key === "End") {
                e.preventDefault();
                // Stop the underlying KeyboardEvent so CanvasEditor's
                // window-level keydown doesn't also nudge a fabric object.
                e.nativeEvent.stopImmediatePropagation();
                let next = index;
                if (e.key === "ArrowLeft") next = Math.max(0, index - 1);
                else if (e.key === "ArrowRight") next = Math.min(slides.length - 1, index + 1);
                else if (e.key === "Home") next = 0;
                else if (e.key === "End") next = slides.length - 1;
                if (next === index) return;
                onSelect(next);
                // After re-render lands the new active thumb in the DOM,
                // move focus to it so the next arrow keeps stepping.
                requestAnimationFrame(() => {
                  const el = document.querySelector<HTMLElement>(`[data-slide-thumb="${next}"]`);
                  el?.focus();
                });
              }
            }}
            className="group"
            style={{
              position: "relative",
              flexShrink: 0,
              width: boxW,
              height: boxH,
              borderRadius: 6,
              cursor: dragIndex === index ? "grabbing" : "grab",
              border: index === currentIndex
                ? "2px solid var(--accent)"
                : "2px solid var(--border)",
              boxShadow: index === currentIndex ? "0 0 0 2px rgba(94,106,210,0.2)" : "none",
              outline: "none",
              overflow: "hidden",
              background: "var(--bg-overlay)",
              opacity: dragIndex === index ? 0.4 : 1,
              transition: "opacity 0.12s",
            }}
          >
            {/* Full-design preview (renders bg + every object scaled down) */}
            <SlideThumbnail slide={slide} size={THUMB_SIZE} />

            <span
              style={{
                position: "absolute",
                top: 3,
                left: 4,
                fontSize: 9,
                fontWeight: 700,
                color: index === currentIndex ? "var(--accent)" : badgeColor,
                textShadow: "0 0 2px rgba(0,0,0,0.4)",
                pointerEvents: "none",
              }}
            >
              {index + 1}
            </span>

            {slides.length > 1 && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(index);
                }}
                className="group-hover:opacity-100"
                style={{
                  position: "absolute",
                  top: -6,
                  right: -6,
                  width: 18,
                  height: 18,
                  background: "var(--red)",
                  color: "white",
                  borderRadius: "50%",
                  fontSize: 9,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  opacity: 0,
                }}
              >
                <svg width="9" height="9" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
          {showRightIndicator && (
            <div
              data-drop-indicator="right"
              style={{
                width: 3,
                height: THUMB_SIZE + 8,
                background: "#3CC8FF",
                borderRadius: 2,
                flexShrink: 0,
                marginLeft: -6, marginRight: -5,
                pointerEvents: "none",
                boxShadow: "0 0 6px rgba(60,200,255,0.7)",
              }}
            />
          )}
          </Fragment>
        );
        })}

        <button
          onClick={onAdd}
          style={{
            flexShrink: 0,
            width: 64,
            height: 64,
            borderRadius: 6,
            border: "2px dashed var(--border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-tertiary)",
            cursor: "pointer",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--accent)";
            e.currentTarget.style.color = "var(--accent-text)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.color = "var(--text-tertiary)";
          }}
        >
          <svg width="20" height="20" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
        </button>

        <div style={{ marginLeft: "auto", flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={onDuplicate}
            title="현재 페이지 복제 (Ctrl+D)"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "5px 10px",
              fontSize: 11,
              fontWeight: 500,
              color: "var(--text-secondary)",
              background: "var(--bg-overlay)",
              borderRadius: 5,
              border: "1px solid var(--border)",
              cursor: "pointer",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--border-strong)")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
          >
            <svg width="11" height="11" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 0 1-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 0 1 1.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 0 0-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 0 1-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H9.75" />
            </svg>
            복제
          </button>
          <button
            onClick={() => onRemove(currentIndex)}
            disabled={slides.length <= 1}
            title={slides.length <= 1 ? "마지막 페이지는 삭제할 수 없습니다" : "현재 페이지 삭제 (Delete)"}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "5px 10px",
              fontSize: 11,
              fontWeight: 500,
              color: slides.length <= 1 ? "var(--text-tertiary)" : "var(--red)",
              background: slides.length <= 1 ? "var(--bg-overlay)" : "var(--red-muted, rgba(232,91,91,0.12))",
              borderRadius: 5,
              border: `1px solid ${slides.length <= 1 ? "var(--border)" : "rgba(232,91,91,0.25)"}`,
              cursor: slides.length <= 1 ? "not-allowed" : "pointer",
              opacity: slides.length <= 1 ? 0.55 : 1,
            }}
            onMouseEnter={(e) => { if (slides.length > 1) e.currentTarget.style.background = "rgba(232,91,91,0.20)"; }}
            onMouseLeave={(e) => { if (slides.length > 1) e.currentTarget.style.background = "var(--red-muted, rgba(232,91,91,0.12))"; }}
          >
            <svg width="11" height="11" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
            </svg>
            삭제
          </button>
          <div style={{ padding: "5px 10px", fontSize: 11, fontWeight: 500, color: "var(--text-tertiary)", background: "var(--bg-overlay)", borderRadius: 5, border: "1px solid var(--border)" }}>
            {currentIndex + 1} / {slides.length}
          </div>
        </div>
      </div>
    </div>
  );
}
