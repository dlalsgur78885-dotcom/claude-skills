"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface ImageDropModalProps {
  // Fired once a valid image file is chosen — by drop or by the file picker.
  onSelect: (file: File) => void;
  onClose: () => void;
}

// Drag-and-drop image picker — carousel studio feedback slide 7. The bare
// "다른 이미지로 교체" button used to open the native OS file dialog directly;
// this modal lets the user drag a file in instead, with a click-to-browse
// fallback (Google Lens style).
const OK_MIME = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/pjpeg"];
const OK_EXT = /\.(jpe?g|png|webp|jfif|pjpeg)$/i;

function isImageFile(file: File): boolean {
  return (!!file.type && OK_MIME.includes(file.type)) || OK_EXT.test(file.name);
}

export function ImageDropModal({ onSelect, onClose }: ImageDropModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleFile(file: File | undefined | null) {
    if (!file) return;
    if (!isImageFile(file)) {
      alert("지원하지 않는 이미지 형식입니다. jpg, png, webp만 지원합니다.");
      return;
    }
    onSelect(file);
    onClose();
  }

  // Rendered into document.body — the property panel is a 220px column with
  // overflow:auto, so a position:fixed child could be clipped if an ancestor
  // establishes a containing block (transform/filter). Matches the template
  // editor's replace-image modal.
  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-base)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          width: "100%",
          maxWidth: 460,
          padding: 24,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
            다른 이미지로 교체
          </h2>
          <button
            onClick={onClose}
            aria-label="닫기"
            style={{
              border: "none",
              background: "transparent",
              color: "var(--text-tertiary)",
              fontSize: 20,
              lineHeight: 1,
              cursor: "pointer",
            }}
          >
            ×
          </button>
        </div>
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            if (Array.from(e.dataTransfer.types || []).includes("Files")) {
              e.preventDefault();
              e.dataTransfer.dropEffect = "copy";
              setDragOver(true);
            }
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            handleFile(Array.from(e.dataTransfer.files || [])[0]);
          }}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            padding: "44px 20px",
            border: `2px dashed ${dragOver ? "var(--accent)" : "var(--border)"}`,
            borderRadius: 10,
            background: dragOver ? "rgba(94,106,210,0.12)" : "var(--bg-overlay)",
            cursor: "pointer",
            transition: "background 0.12s, border-color 0.12s",
          }}
        >
          <div style={{ fontSize: 32 }}>🖼️</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", textAlign: "center" }}>
            여기로 이미지를 드래그하거나{" "}
            <span style={{ color: "var(--accent-text)", fontWeight: 600, textDecoration: "underline" }}>
              파일을 업로드하세요
            </span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>JPG · PNG · WEBP</div>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          style={{ display: "none" }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.currentTarget.value = "";
            handleFile(file);
          }}
        />
      </div>
    </div>,
    document.body,
  );
}
