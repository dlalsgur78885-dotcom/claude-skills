"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { TemplateEditor, type TemplateData } from "@/components/template-editor/TemplateEditor";

export default function TemplateEditPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: idParam } = use(params);
  const id = Number(idParam);
  const router = useRouter();

  const [template, setTemplate] = useState<TemplateData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!Number.isFinite(id)) {
      setError("잘못된 템플릿 ID");
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const data = await api.getTemplate(id);
        setTemplate(data as unknown as TemplateData);
      } catch (err) {
        setError(err instanceof Error ? err.message : "템플릿을 불러올 수 없습니다");
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) {
    return <div style={{ padding: 24, color: "var(--text-secondary)" }}>로딩 중...</div>;
  }
  if (error || !template) {
    return (
      <div style={{ padding: 24 }}>
        <p style={{ color: "#e85b5b", marginBottom: 12 }}>{error || "템플릿 없음"}</p>
        <button
          onClick={() => router.push("/templates")}
          style={{
            padding: "6px 14px",
            fontSize: 13,
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            color: "var(--text-primary)",
            cursor: "pointer",
          }}
        >
          ← 템플릿 목록
        </button>
      </div>
    );
  }

  return (
    <TemplateEditor
      templateId={id}
      template={template}
      onSave={async (next) => {
        await api.updateTemplate(id, {
          name: next.name,
          canvas: next.canvas as unknown as Record<string, unknown>,
          brand: next.brand as unknown as Record<string, unknown>,
          layouts: next.layouts as unknown as Record<string, unknown>,
        });
      }}
      onClose={() => router.push("/templates")}
    />
  );
}
