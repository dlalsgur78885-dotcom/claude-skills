"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";

interface SharedPreview {
  id: number;
  name: string;
  layouts: Record<string, unknown> | string[];
  created_by: string;
  source_post_url?: string | null;
  source_slides?: string[];
}

export default function TemplateImportPage() {
  const router = useRouter();
  const params = useSearchParams();
  const code = params.get("code") || "";

  const [preview, setPreview] = useState<SharedPreview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [cloning, setCloning] = useState(false);

  useEffect(() => {
    if (!code) {
      setError("공유 코드가 없습니다");
      setLoading(false);
      return;
    }
    api.getTemplateByShareCode(code)
      .then((d) => setPreview(d as unknown as SharedPreview))
      .catch((e) => setError(e instanceof Error ? e.message : "공유 템플릿을 찾을 수 없습니다"))
      .finally(() => setLoading(false));
  }, [code]);

  async function add() {
    if (cloning || !code) return;
    setCloning(true);
    try {
      const cloned = await api.cloneTemplateByShareCode(code);
      router.push(`/templates/${cloned.id}/edit`);
    } catch (e) {
      alert(e instanceof Error ? e.message : "가져오기 실패");
      setCloning(false);
    }
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 640, margin: "0 auto" }}>
      <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 8 }}>
        공유받은 템플릿
      </h1>
      <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 24 }}>
        다른 사용자가 공유한 템플릿을 내 라이브러리로 가져옵니다.
      </p>

      {loading && (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>불러오는 중…</p>
      )}

      {!loading && error && (
        <div style={{
          padding: 14, background: "rgba(255,80,80,0.08)",
          border: "1px solid rgba(255,80,80,0.3)", borderRadius: 8,
          color: "#e85b5b", fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {!loading && preview && (
        <div style={{
          padding: 18, background: "var(--bg-subtle)",
          border: "1px solid var(--border)", borderRadius: 10,
        }}>
          <div style={{ fontSize: 17, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
            {preview.name}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 14 }}>
            레이아웃: {Array.isArray(preview.layouts) ? preview.layouts.join(", ") : Object.keys(preview.layouts || {}).join(", ")}
            {preview.created_by && ` · ${preview.created_by}`}
          </div>
          {preview.source_slides && preview.source_slides.length > 0 && (
            <div style={{ display: "flex", gap: 6, overflowX: "auto", marginBottom: 16 }}>
              {preview.source_slides.slice(0, 6).map((u) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={u} src={u} alt="" style={{ height: 96, width: 96, objectFit: "cover", borderRadius: 6, border: "1px solid var(--border)", flexShrink: 0 }} />
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={add}
              disabled={cloning}
              style={{
                padding: "10px 18px", fontSize: 13, fontWeight: 600, color: "white",
                background: "var(--accent)", border: "none", borderRadius: 8,
                cursor: cloning ? "default" : "pointer", opacity: cloning ? 0.6 : 1,
              }}
            >
              {cloning ? "가져오는 중…" : "내 라이브러리에 추가"}
            </button>
            <button
              onClick={() => router.push("/templates")}
              style={{
                padding: "10px 18px", fontSize: 13,
                color: "var(--text-secondary)", background: "var(--bg-elevated)",
                border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer",
              }}
            >
              취소
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
