"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { getFabric } from "@/lib/fabric";
import { renderLayoutToCanvas } from "./renderer";
import type { TemplateData } from "./types";

interface Props {
  templateId: number;
  layoutName?: string;       // if not given, uses the first layout
  size?: number;             // pixel side length of the rendered square
  onLoaded?: (template: TemplateData) => void;
}

/** Tiny static-canvas preview of one layout, used in template cards. */
export function TemplateThumbnail({ templateId, layoutName, size = 220, onLoaded }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let fabricCanvas: any = null;

    (async () => {
      try {
        const data = (await api.getTemplate(templateId)) as unknown as TemplateData;
        if (cancelled || !canvasRef.current) return;
        onLoaded?.(data);

        const fabric = await getFabric();
        if (cancelled || !canvasRef.current) return;

        const canvasW = data.canvas?.width || 1080;
        const canvasH = data.canvas?.height || 1080;
        const scale = size / Math.max(canvasW, canvasH);

        fabricCanvas = new fabric.StaticCanvas(canvasRef.current, {
          width: canvasW * scale,
          height: canvasH * scale,
          backgroundColor: data.brand?.background_color || "#FFFFFF",
        });

        const name = layoutName || Object.keys(data.layouts || {})[0];
        const layout = name ? data.layouts?.[name] : undefined;
        if (layout) {
          await renderLayoutToCanvas(fabricCanvas, name!, layout, data.brand, scale, canvasW, canvasH);
          // Strip selection chrome — this is read-only
          for (const obj of fabricCanvas.getObjects()) {
            obj.selectable = false;
            obj.evented = false;
            obj.hasControls = false;
          }
          fabricCanvas.renderAll();
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "로딩 실패");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (fabricCanvas) fabricCanvas.dispose();
    };
  }, [templateId, layoutName, size, onLoaded]);

  return (
    <div
      style={{
        width: size,
        height: size,
        background: "var(--bg-overlay)",
        borderRadius: 6,
        overflow: "hidden",
        position: "relative",
        flexShrink: 0,
        // The square wrapper holds an aspect-fitted canvas (e.g. 176×220 for a
        // 4:5 template) — without centering it hugs the top-left (피드백 14-3).
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {loading && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-tertiary)",
            fontSize: 11,
          }}
        >
          로딩…
        </div>
      )}
      {error && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            padding: 8,
            color: "#e85b5b",
            fontSize: 10,
          }}
        >
          {error}
        </div>
      )}
      <canvas ref={canvasRef} />
    </div>
  );
}
