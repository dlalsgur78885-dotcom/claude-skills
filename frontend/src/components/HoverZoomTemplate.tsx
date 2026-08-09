"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { TemplateThumbnail } from "./template-editor/TemplateThumbnail";

interface Props {
  templateId: number;
  layoutName?: string;
  /** Small (in-card) size — the popover always shows ~480px. */
  size?: number;
}

/** Wrapper around <TemplateThumbnail> that pops up a ~480px preview on hover.
 *  Used in /create's template-selection step so the user can read a layout's
 *  actual text/composition without clicking into the editor.
 *
 *  Why not HoverZoomImage: TemplateThumbnail renders a <canvas> (fabric), not
 *  an <img>. Re-mounting it at size=POP renders the layout fresh at the bigger
 *  resolution, which keeps text sharp (a toDataURL from the 96px canvas would
 *  blur on upscale).
 *
 *  Positioning / scroll-close / pointer-events:none — same pattern as
 *  HoverZoomImage. Two separate files because each consumer takes very
 *  different children; factoring a shared primitive added more glue than it
 *  saved. */
export function HoverZoomTemplate({ templateId, layoutName, size = 96 }: Props) {
  const [show, setShow] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const [mounted, setMounted] = useState(false);
  const enterTimerRef = useRef<number | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => { setMounted(true); }, []);

  // Close on scroll — the fixed-positioned popover would otherwise drift away
  // from its anchor as the page scrolls underneath.
  useEffect(() => {
    if (!show) return;
    const close = () => setShow(false);
    window.addEventListener("scroll", close, true);
    return () => window.removeEventListener("scroll", close, true);
  }, [show]);

  function onEnter() {
    if (enterTimerRef.current != null) window.clearTimeout(enterTimerRef.current);
    enterTimerRef.current = window.setTimeout(() => {
      if (wrapperRef.current) setAnchor(wrapperRef.current.getBoundingClientRect());
      setShow(true);
    }, 150);
  }

  function onLeave() {
    if (enterTimerRef.current != null) {
      window.clearTimeout(enterTimerRef.current);
      enterTimerRef.current = null;
    }
    setShow(false);
  }

  // Right of the trigger by default, flip left when there isn't POP+GAP+MARGIN
  // of room. Clamp vertically inside the viewport.
  const POP = 480;
  const GAP = 12;
  const MARGIN = 8;
  let popLeft = 0;
  let popTop = 0;
  if (anchor) {
    const roomRight = window.innerWidth - anchor.right;
    if (roomRight >= POP + GAP + MARGIN) {
      popLeft = anchor.right + GAP;
    } else {
      popLeft = Math.max(MARGIN, anchor.left - POP - GAP);
    }
    popTop = anchor.top + anchor.height / 2 - POP / 2;
    popTop = Math.max(MARGIN, Math.min(popTop, window.innerHeight - POP - MARGIN));
  }

  return (
    <div
      ref={wrapperRef}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      style={{ display: "inline-block", lineHeight: 0 }}
    >
      <TemplateThumbnail templateId={templateId} layoutName={layoutName} size={size} />
      {mounted && show && anchor && createPortal(
        <div
          style={{
            position: "fixed",
            left: popLeft,
            top: popTop,
            width: POP,
            height: POP,
            zIndex: 9999,
            pointerEvents: "none",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            boxShadow: "0 18px 48px rgba(0,0,0,0.45)",
            overflow: "hidden",
          }}
        >
          <TemplateThumbnail templateId={templateId} layoutName={layoutName} size={POP} />
        </div>,
        document.body
      )}
    </div>
  );
}
