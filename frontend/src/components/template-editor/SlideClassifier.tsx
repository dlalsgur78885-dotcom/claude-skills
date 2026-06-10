"use client";

import { proxiedImageUrl, type LayoutHint } from "@/lib/api";

interface Props {
  slideUrls: string[];
  hints: LayoutHint[];
  onChange: (hints: LayoutHint[]) => void;
}

// Labels read 가로×세로 (cols×rows) — users describe a grid by how many cells
// run ACROSS first (feedback 13 slide 2: a 2-wide 3-tall post is "2×3", but the
// old rows-first mapping generated 3-wide 2-tall). rows/cols stay rows-first
// internally to match the backend's grid_{rows}x{cols} layout keys.
const GRID_OPTIONS: { label: string; rows: number; cols: number }[] = [
  { label: "1×2", rows: 2, cols: 1 },
  { label: "1×3", rows: 3, cols: 1 },
  { label: "2×1", rows: 1, cols: 2 },
  { label: "2×2", rows: 2, cols: 2 },
  { label: "2×3", rows: 3, cols: 2 },
  { label: "3×1", rows: 1, cols: 3 },
  { label: "3×2", rows: 2, cols: 3 },
  { label: "3×3", rows: 3, cols: 3 },
];

export function SlideClassifier({ slideUrls, hints, onChange }: Props) {
  function update(idx: number, patch: Partial<LayoutHint>) {
    const next = slideUrls.map((_, i) => {
      // Untouched slides default to "none" — only the slides the user
      // explicitly classifies are extracted (피드백 13-4).
      const existing = hints.find((h) => h.slide_index === i) ?? { slide_index: i, kind: "none" as const };
      if (i === idx) return { ...existing, ...patch };
      return existing;
    });
    onChange(next);
  }

  function gridValue(h: LayoutHint | undefined): string {
    if (!h || h.kind !== "grid" || !h.rows || !h.cols) return "";
    return `${h.rows}x${h.cols}`;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <p style={{ fontSize: 11, color: "var(--text-tertiary)", margin: 0 }}>
        템플릿으로 추출할 슬라이드만 분류해주세요 — 없음으로 둔 슬라이드는 추출에서 제외됩니다. 단일은 한 화면에 메인 콘텐츠 하나, 그리드는 작은 셀이 여러 개 (가로×세로 — 예: 2×3 = 가로 2칸, 세로 3줄).
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {slideUrls.map((url, i) => {
          const h = hints.find((x) => x.slide_index === i);
          const isGrid = h?.kind === "grid";
          const isSingle = h?.kind === "single";
          const isNone = !h || h.kind === "none";
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: 8,
                background: "var(--bg-overlay)",
                border: "1px solid var(--border)",
                borderRadius: 6,
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={proxiedImageUrl(url)}
                alt={`slide ${i + 1}`}
                style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 4, flexShrink: 0, background: "#222" }}
              />
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", width: 50, flexShrink: 0 }}>
                슬라이드 {i + 1}
              </span>
              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--text-tertiary)", cursor: "pointer" }}>
                <input
                  type="radio"
                  name={`kind-${i}`}
                  checked={isNone}
                  onChange={() => update(i, { kind: "none", rows: undefined, cols: undefined })}
                />
                없음
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--text-primary)", cursor: "pointer" }}>
                <input
                  type="radio"
                  name={`kind-${i}`}
                  checked={isSingle}
                  onChange={() => update(i, { kind: "single", rows: undefined, cols: undefined })}
                />
                단일
              </label>
              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, color: "var(--text-primary)", cursor: "pointer" }}>
                <input
                  type="radio"
                  name={`kind-${i}`}
                  checked={isGrid}
                  onChange={() => update(i, { kind: "grid", rows: 2, cols: 2 })}
                />
                그리드
              </label>
              <select
                value={gridValue(h)}
                disabled={!isGrid}
                onChange={(e) => {
                  const [r, c] = e.target.value.split("x").map(Number);
                  update(i, { kind: "grid", rows: r, cols: c });
                }}
                style={{
                  padding: "3px 6px",
                  fontSize: 11,
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: 4,
                  color: "var(--text-primary)",
                  opacity: isGrid ? 1 : 0.4,
                }}
              >
                {!isGrid && <option value="">—</option>}
                {GRID_OPTIONS.map((opt) => (
                  <option key={opt.label} value={`${opt.rows}x${opt.cols}`}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
    </div>
  );
}
