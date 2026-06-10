"use client";

import { useEffect, useState } from "react";
import { api, resolveImageUrl } from "@/lib/api";
import { gridNameHint, type TemplateData } from "./types";
import { TemplateThumbnail } from "./TemplateThumbnail";

interface Props {
  templateId: number;
  templateName: string;
  onClose: () => void;
  onEdit?: () => void;
  editing?: boolean;
}

/** Read-only modal showing every layout in a template. */
export function TemplatePreviewModal({ templateId, templateName, onClose, onEdit, editing }: Props) {
  const [data, setData] = useState<(TemplateData & { source_slides?: string[]; source_post_url?: string | null }) | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getTemplate(templateId).then((d) => {
      if (!cancelled) setData(d as unknown as (TemplateData & { source_slides?: string[]; source_post_url?: string | null }));
    });
    return () => {
      cancelled = true;
    };
  }, [templateId]);

  const layoutNames = Object.keys(data?.layouts || {});
  const sourceSlides = data?.source_slides || [];

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.78)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
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
          background: "var(--bg-base, #141414)",
          border: "1px solid var(--border)",
          borderRadius: 12,
          width: "100%",
          maxWidth: 1100,
          maxHeight: "90vh",
          overflowY: "auto",
          padding: 24,
          boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 20,
          }}
        >
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
              {templateName}
            </h2>
            <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>
              {layoutNames.length}개 레이아웃 미리보기
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {onEdit && (
              <button
                onClick={onEdit}
                disabled={editing}
                style={{
                  padding: "7px 16px",
                  fontSize: 12,
                  fontWeight: 500,
                  color: "white",
                  background: "var(--accent)",
                  border: "none",
                  borderRadius: 6,
                  cursor: editing ? "default" : "pointer",
                  opacity: editing ? 0.6 : 1,
                }}
              >
                {editing ? "복제 중…" : "편집"}
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                padding: "7px 14px",
                fontSize: 12,
                color: "var(--text-secondary)",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              닫기
            </button>
          </div>
        </div>

        {!data ? (
          <p style={{ color: "var(--text-tertiary)", fontSize: 13 }}>로딩 중…</p>
        ) : layoutNames.length === 0 ? (
          <p style={{ color: "var(--text-tertiary)", fontSize: 13 }}>레이아웃이 없습니다.</p>
        ) : (
          <>
            {/* 원본 인스타 슬라이드 (예시) */}
            {sourceSlides.length > 0 && (
              <section style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                  <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                    원본 예시 — Gemini가 이 슬라이드를 보고 템플릿 추출
                  </h3>
                  {data?.source_post_url && (
                    <a
                      href={data.source_post_url}
                      target="_blank"
                      rel="noreferrer"
                      style={{ fontSize: 11, color: "var(--accent)" }}
                    >
                      인스타 원본 →
                    </a>
                  )}
                </div>
                <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
                  {sourceSlides.map((u, i) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={u}
                      src={resolveImageUrl(u)}
                      alt={`slide ${i}`}
                      style={{
                        width: 160,
                        height: 160,
                        objectFit: "cover",
                        borderRadius: 6,
                        border: "1px solid var(--border)",
                        flexShrink: 0,
                      }}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* 추상 템플릿 렌더 (placeholder) */}
            <div style={{ marginBottom: 10, fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
              템플릿 레이아웃 — 콘텐츠 없이 구조만
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: 16,
              }}
            >
              {layoutNames.map((name) => (
                <div
                  key={name}
                  style={{
                    background: "var(--bg-subtle)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 12,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <TemplateThumbnail templateId={templateId} layoutName={name} size={280} />
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", fontFamily: "monospace" }}>
                    {name}{gridNameHint(name)}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
