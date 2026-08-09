"use client";

import { useEffect, useRef, useState } from "react";

const PRESETS = [
  { label: "1:1 정사각형", w: 1080, h: 1080 },
  { label: "4:5 세로", w: 1080, h: 1350 },
  { label: "9:16 스토리", w: 1080, h: 1920 },
  { label: "2:1 와이드", w: 2160, h: 1080 },
];

interface Props {
  width: number;
  height: number;
  onChange: (w: number, h: number) => void;
}

export function CanvasSizeSelector({ width, height, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [customW, setCustomW] = useState(String(width));
  const [customH, setCustomH] = useState(String(height));
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function applyCustom() {
    const w = parseInt(customW, 10);
    const h = parseInt(customH, 10);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w < 100 || h < 100 || w > 5000 || h > 5000) {
      return;
    }
    onChange(w, h);
    setOpen(false);
  }

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => {
          if (!open) {
            setCustomW(String(width));
            setCustomH(String(height));
          }
          setOpen((v) => !v);
        }}
        title="캔버스 사이즈"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "5px 10px",
          fontSize: 11,
          color: "var(--text-secondary)",
          background: "var(--bg-overlay)",
          border: "1px solid var(--border)",
          borderRadius: 5,
          cursor: "pointer",
        }}
      >
        <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
        </svg>
        {width} × {height}
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            zIndex: 50,
            width: 240,
            padding: 8,
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
          }}
        >
          <div style={{ fontSize: 10, color: "var(--text-tertiary)", padding: "2px 6px 4px", textTransform: "uppercase", letterSpacing: 0.4 }}>
            프리셋
          </div>
          {PRESETS.map((p) => {
            const isActive = p.w === width && p.h === height;
            return (
              <button
                key={`${p.w}x${p.h}`}
                onClick={() => {
                  onChange(p.w, p.h);
                  setOpen(false);
                }}
                style={{
                  display: "flex",
                  width: "100%",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "6px 8px",
                  fontSize: 12,
                  color: isActive ? "var(--text-primary)" : "var(--text-secondary)",
                  background: isActive ? "var(--bg-overlay)" : "transparent",
                  border: "none",
                  borderRadius: 4,
                  cursor: "pointer",
                  textAlign: "left",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.04)";
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.background = "transparent";
                }}
              >
                <span>{p.label}</span>
                <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                  {p.w}×{p.h}
                </span>
              </button>
            );
          })}
          <div style={{ height: 1, background: "var(--border)", margin: "8px 4px" }} />
          <div style={{ fontSize: 10, color: "var(--text-tertiary)", padding: "2px 6px 4px", textTransform: "uppercase", letterSpacing: 0.4 }}>
            직접 입력 (px)
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 6px" }}>
            <input
              type="number"
              value={customW}
              onChange={(e) => setCustomW(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyCustom()}
              style={{
                width: 70,
                padding: "5px 6px",
                fontSize: 12,
                background: "var(--bg-overlay)",
                border: "1px solid var(--border)",
                borderRadius: 4,
                color: "var(--text-primary)",
              }}
              placeholder="W"
            />
            <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>×</span>
            <input
              type="number"
              value={customH}
              onChange={(e) => setCustomH(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applyCustom()}
              style={{
                width: 70,
                padding: "5px 6px",
                fontSize: 12,
                background: "var(--bg-overlay)",
                border: "1px solid var(--border)",
                borderRadius: 4,
                color: "var(--text-primary)",
              }}
              placeholder="H"
            />
            <button
              onClick={applyCustom}
              style={{
                flex: 1,
                padding: "5px 8px",
                fontSize: 11,
                color: "white",
                background: "var(--accent)",
                border: "none",
                borderRadius: 4,
                cursor: "pointer",
              }}
            >
              적용
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
