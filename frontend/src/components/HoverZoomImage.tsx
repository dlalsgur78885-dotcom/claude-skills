"use client";

import { useEffect, useRef, useState, type ImgHTMLAttributes } from "react";
import { createPortal } from "react-dom";

type Props = ImgHTMLAttributes<HTMLImageElement>;

/** Thumbnail <img> drop-in that pops up a ~480px portal-rendered enlargement
 *  on hover. Used in /create so small benchmark slide thumbnails are legible
 *  without clicking.
 *
 *  Why a portal: Step 0's reference strip is overflow-x:auto, which would clip
 *  a CSS transform:scale() preview. Rendering into document.body via portal
 *  escapes every ancestor's overflow context. pointer-events:none on the
 *  popover keeps it from stealing the hover (no flicker).
 *
 *  Why the same src: Instagram raw images are cached at full resolution, so
 *  rendering the same URL at 480×480 stays sharp — no extra fetch needed.
 *
 *  Caller props (style, onError, title, loading, alt, …) are spread onto the
 *  thumbnail FIRST, so mouse handlers below win and the zoom always works
 *  regardless of what callers pass. Touch devices: enter/leave never fire on
 *  taps, so this degrades cleanly to a plain <img>. */
export function HoverZoomImage({ src, alt, ...rest }: Props) {
  const [show, setShow] = useState(false);
  // Anchor rect captured at hover-start; popover position is derived from this
  // (NOT the live cursor) so the enlarged image doesn't jitter as the mouse
  // moves inside the thumbnail.
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const [mounted, setMounted] = useState(false);
  const enterTimerRef = useRef<number | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  // createPortal needs document — only safe after client-side mount.
  useEffect(() => { setMounted(true); }, []);

  // Close on any scroll. Without this the fixed-positioned popover stays
  // anchored to its old viewport coords while the page scrolls underneath,
  // drifting off the thumbnail it belongs to.
  useEffect(() => {
    if (!show) return;
    const close = () => setShow(false);
    window.addEventListener("scroll", close, true);
    return () => window.removeEventListener("scroll", close, true);
  }, [show]);

  function onEnter() {
    if (enterTimerRef.current != null) window.clearTimeout(enterTimerRef.current);
    // 150ms gate — quick mouse fly-bys shouldn't open the popover.
    enterTimerRef.current = window.setTimeout(() => {
      if (imgRef.current) setAnchor(imgRef.current.getBoundingClientRect());
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

  // Position the popover next to the thumbnail. Default = right side; flip
  // left when the viewport doesn't have POP+GAP+MARGIN of room. Vertically
  // center on the thumbnail and clamp inside the viewport.
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
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        {...rest}
        ref={imgRef}
        src={src}
        alt={alt}
        onMouseEnter={onEnter}
        onMouseLeave={onLeave}
      />
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
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt=""
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
              background: "var(--bg-overlay)",
            }}
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = "0.3"; }}
          />
        </div>,
        document.body
      )}
    </>
  );
}
