/**
 * Centralized Fabric.js loader.
 *
 * Fabric v7 changed the default `originX/Y` of every object from `"left"/"top"`
 * (v6 behavior) to `"center"`. That means `new fabric.Rect({ left, top })` now
 * treats `(left, top)` as the OBJECT CENTER, not the top-left corner — so a
 * rect drawn at `(0, 0)` ends up half off-canvas. We've hit this exact bug
 * twice (FabricImage in `CanvasEditor.tsx`, then Rect/Textbox in
 * `template-editor/renderer.ts`), so we restore v6 behavior globally here.
 *
 * Every component that uses Fabric MUST import from this module instead of
 * calling `import("fabric")` directly:
 *
 *     import { getFabric } from "@/lib/fabric";
 *     const fabric = await getFabric();
 *
 * Direct `import("fabric")` calls should be considered legacy.
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let cached: any | null = null;

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function getFabric(): Promise<any> {
  if (cached) return cached;
  const fabric = await import("fabric");
  // Restore v6 default: (left, top) means the top-left corner of the object.
  // Mutating the prototype is the only way to affect every existing subclass
  // (Rect, Textbox, FabricImage, Path, …) in one place.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const proto = (fabric as any).FabricObject?.prototype;
  if (proto) {
    proto.originX = "left";
    proto.originY = "top";

    // ─── Selection chrome ────────────────────────────────────────────
    // Fabric's default selection border is a thin 1px gray line that's
    // nearly invisible against most carousel slide backgrounds. Bump it
    // to a bright accent color + double thickness, and enlarge the corner
    // handles so the user can hit them comfortably even at small canvas
    // display sizes. Matches the Miricanvas reference (PDF page 2).
    proto.borderColor = "#3CC8FF";        // bright cyan/blue, high-contrast on dark and light bgs
    proto.borderScaleFactor = 2;          // 2× default thickness (~2px)
    proto.borderDashArray = null;         // solid line, not dashed
    proto.cornerColor = "#3CC8FF";
    proto.cornerStrokeColor = "#FFFFFF";  // white outline around each handle
    proto.cornerSize = 12;
    proto.cornerStyle = "circle";
    proto.transparentCorners = false;     // filled handles, not hollow
    proto.padding = 2;                    // small gap between border and object edge

    // ─── Preserve `obj.data` through serialization ───────────────────
    // Fabric's default toObject() only emits a fixed list of props. Custom
    // markers we stash on objects (e.g. {kind: "user_image", slide_index})
    // would be dropped the first time the user saves the slide, so on
    // reload the editor wouldn't know to keep that image unlocked.
    // Patch toObject to always include `data` so the round-trip survives.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const baseToObject = proto.toObject;
    if (typeof baseToObject === "function" && !(proto as { __dataPatched?: boolean }).__dataPatched) {
      proto.toObject = function (propertiesToInclude?: string[]) {
        return baseToObject.call(this, ["data", ...(propertiesToInclude || [])]);
      };
      (proto as { __dataPatched?: boolean }).__dataPatched = true;
    }
  }

  // ─── Preserve original src for placeholdered (unreachable) images ────
  // The canvas editor swaps an unreachable image's src for a transparent 1×1
  // placeholder so one dead photo can't blank the whole slide, and stashes the
  // real URL on `obj.__originalSrc`. Patch FabricImage.toObject so EVERY
  // serialization (toJSON / autosave / undo snapshot / resize) re-emits that
  // original URL instead of the placeholder — the placeholder is display-only
  // and must never reach the DB. No-op for normal images (no __originalSrc).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ImageClass = (fabric as any).FabricImage || (fabric as any).Image;
  if (ImageClass?.prototype && !(ImageClass.prototype as { __originalSrcPatched?: boolean }).__originalSrcPatched) {
    const baseImageToObject = ImageClass.prototype.toObject;
    if (typeof baseImageToObject === "function") {
      ImageClass.prototype.toObject = function (propertiesToInclude?: string[]) {
        const obj = baseImageToObject.call(this, propertiesToInclude);
        const orig = (this as { __originalSrc?: unknown }).__originalSrc;
        if (typeof orig === "string" && orig) obj.src = orig;
        return obj;
      };
      (ImageClass.prototype as { __originalSrcPatched?: boolean }).__originalSrcPatched = true;
    }
  }

  cached = fabric;
  // Expose for E2E tests / debugging. Lets headless scripts build an
  // ActiveSelection without bundling fabric themselves. No effect at runtime
  // beyond a window property.
  if (typeof window !== "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (window as any).__fabric = fabric;
  }
  return fabric;
}
