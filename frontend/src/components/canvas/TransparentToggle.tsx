"use client";

// Lightweight "transparent" toggle dropped next to every color picker in the
// app. User feedback (carousel studio feedback slide 4):
//   "도형이나 배경, 그림자, 그라데이션 등 모든 색상을 바꿀 때 '투명' 옵션 추가."
//
// CSS / Canvas2D / fabric all accept the literal string "transparent" as
// rgba(0,0,0,0) — each consumer just passes its existing color setter and the
// button toggles between current solid color and "transparent". When the
// current value is already transparent, clicking restores `fallbackColor`.

export function isTransparentValue(v: unknown): boolean {
  if (v == null || v === "" || v === "null") return true;
  const s = String(v).toLowerCase().replace(/\s+/g, "");
  return s === "transparent" || s === "rgba(0,0,0,0)";
}

export function TransparentToggle({
  value,
  onChange,
  size = 22,
  fallbackColor = "#FFFFFF",
}: {
  value: unknown;
  onChange: (next: string) => void;
  size?: number;
  fallbackColor?: string;
}) {
  const transparent = isTransparentValue(value);
  const tile = Math.max(8, Math.round(size / 3));
  const half = Math.max(4, Math.round(size / 6));
  return (
    <button
      type="button"
      onClick={() => onChange(transparent ? fallbackColor : "transparent")}
      title={transparent ? "현재: 투명 (클릭해서 색 적용)" : "투명으로 변경"}
      aria-pressed={transparent}
      style={{
        width: size,
        height: size,
        padding: 0,
        border: transparent ? "2px solid var(--accent)" : "1px solid var(--border)",
        borderRadius: 4,
        cursor: "pointer",
        backgroundColor: "#ffffff",
        // 4-tile checkerboard so the swatch reads as "transparent" instantly —
        // matches Figma / Photoshop convention.
        backgroundImage:
          "linear-gradient(45deg, #cccccc 25%, transparent 25%), " +
          "linear-gradient(-45deg, #cccccc 25%, transparent 25%), " +
          "linear-gradient(45deg, transparent 75%, #cccccc 75%), " +
          "linear-gradient(-45deg, transparent 75%, #cccccc 75%)",
        backgroundSize: `${tile}px ${tile}px`,
        backgroundPosition: `0 0, 0 ${half}px, ${half}px -${half}px, -${half}px 0`,
        position: "relative",
        flexShrink: 0,
        boxSizing: "border-box",
      }}
    >
      {!transparent && (
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#E55",
            fontSize: Math.max(10, Math.round(size * 0.75)),
            fontWeight: 700,
            lineHeight: 1,
            pointerEvents: "none",
            transform: "rotate(-15deg)",
          }}
        >
          ⌀
        </span>
      )}
    </button>
  );
}
