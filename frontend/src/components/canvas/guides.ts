// User-drawn guides (안내선) — feedback PPT slide 4.
//
// A guide is a fabric.Line marked with data.kind === GUIDE_KIND. It lives
// inside canvas.toJSON() like any other object, so save/restore round-trips
// without backend changes. We constrain its movement axis, hide controls,
// and lock its endpoints to the page edges. Snap logic and Delete-key
// handling extend the existing flows in CanvasEditor.

export const GUIDE_KIND = "guide";
export const GUIDE_COLOR = "#6E89FF"; // 1px solid violet-blue — visible on dark and light pages
// Snap thresholds (design px). The hysteresis (in < out) prevents the snap
// from flickering when the cursor sits exactly at the boundary.
export const SNAP_IN_PX = 8;
export const SNAP_OUT_PX = 12;

export type GuideAxis = "x" | "y";

/** Build a fabric.Line preset for a guide. The line spans the page edge-to-edge
 *  along its axis at `position` (design coords). Movement is locked to the
 *  perpendicular axis so the user can only drag it across, never along. */
export function createGuideObject(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fabric: any,
  axis: GuideAxis,
  position: number,
  pageW: number,
  pageH: number,
) {
  const coords: [number, number, number, number] =
    axis === "x"
      ? [position, 0, position, pageH] // vertical line, drag along X
      : [0, position, pageW, position]; // horizontal line, drag along Y
  const line = new fabric.Line(coords, {
    stroke: GUIDE_COLOR,
    strokeWidth: 1,
    strokeDashArray: undefined,
    // Movement axis: vertical guides slide horizontally, horizontal slide vertically.
    lockMovementX: axis === "y",
    lockMovementY: axis === "x",
    lockRotation: true,
    lockScalingX: true,
    lockScalingY: true,
    lockSkewingX: true,
    lockSkewingY: true,
    hasControls: false,
    hasBorders: false,
    hoverCursor: axis === "x" ? "ew-resize" : "ns-resize",
    moveCursor: axis === "x" ? "ew-resize" : "ns-resize",
    perPixelTargetFind: true,
    targetFindTolerance: 6,
    selectable: true,
    evented: true,
    // Don't export to PNG/render output — exclude on flatten by checking
    // data.kind. fabric.toJSON still keeps it (we want auto-persist).
  });
  line.data = { kind: GUIDE_KIND, axis };
  return line;
}

/** Position of a guide in design coords. For a vertical guide spanning
 *  (p, 0) → (p, h), fabric's `left` ends up tracking p (and updates as the
 *  user drags). Horizontal guides analogously track `top`. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function guidePosition(line: any): number {
  const axis: GuideAxis = line.data?.axis === "y" ? "y" : "x";
  return Math.round(axis === "x" ? (line.left || 0) : (line.top || 0));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function isGuide(obj: any): boolean {
  return obj?.data?.kind === GUIDE_KIND;
}

/** fabric.toJSON / loadFromJSON preserves geometry + `data` but the
 *  interactivity props (lockMovement*, hasControls, hoverCursor) live on the
 *  ObjectClass defaults and don't survive a round-trip. Re-stamp them on
 *  every guide after a load so saved guides keep their axis-only drag
 *  behavior. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function reapplyGuideConfig(line: any) {
  const axis: GuideAxis = line.data?.axis === "y" ? "y" : "x";
  line.set({
    stroke: GUIDE_COLOR,
    strokeWidth: 1,
    lockMovementX: axis === "y",
    lockMovementY: axis === "x",
    lockRotation: true,
    lockScalingX: true,
    lockScalingY: true,
    lockSkewingX: true,
    lockSkewingY: true,
    hasControls: false,
    hasBorders: false,
    hoverCursor: axis === "x" ? "ew-resize" : "ns-resize",
    moveCursor: axis === "x" ? "ew-resize" : "ns-resize",
    perPixelTargetFind: true,
    targetFindTolerance: 6,
  });
}
