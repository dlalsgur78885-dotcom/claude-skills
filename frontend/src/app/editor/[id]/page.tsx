"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { CanvasEditor } from "@/components/canvas/CanvasEditor";
import { api } from "@/lib/api";
import type { SlideData } from "@/lib/types";

export default function EditorPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);

  const [initialSlides, setInitialSlides] = useState<SlideData[] | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [carouselMeta, setCarouselMeta] = useState<Record<string, any>>({});
  const [status, setStatus] = useState<"draft" | "editing" | "finalized">("draft");
  const [title, setTitle] = useState<string>("");
  const [sourcePostUrl, setSourcePostUrl] = useState<string>("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!Number.isFinite(id)) {
      setError("잘못된 캐러셀 ID");
      return;
    }
    (async () => {
      try {
        const carousel = await api.getCarousel(id);
        const cd = (carousel.canvas_data || {}) as Record<string, unknown>;
        const slides = (cd.canvas_slides || cd.slides || []) as SlideData[];
        setInitialSlides(Array.isArray(slides) && slides.length > 0 ? slides : []);
        setCarouselMeta({
          source_slides: cd.source_slides || null,
          user_image_urls: cd.user_image_urls || {},
          // Preserve grid cell picks + per-slide layout overrides. Without these
          // the editor's debounced auto-save (CanvasEditor fires 1s after mount)
          // would write back canvas_data missing these keys — the user's image
          // picks would vanish from DB minutes after step 3 saves them.
          user_item_image_urls: cd.user_item_image_urls || {},
          layout_overrides: cd.layout_overrides || {},
          template_db_id: cd.template_db_id || null,
          caption: cd.caption || "",
          hashtags: cd.hashtags || [],
        });
        setStatus((carousel.status as "draft" | "editing" | "finalized") || "draft");
        setTitle(carousel.title || "");
        // Surface the benchmark post's Instagram URL in the toolbar so users can
        // jump back to the source without leaving the editor. Backend hydrates
        // this field via _hydrate_source_url (see backend/app/api/carousels.py).
        setSourcePostUrl(typeof carousel.source_post_url === "string" ? carousel.source_post_url : "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "캐러셀을 불러올 수 없습니다");
      }
    })();
  }, [id]);

  async function toggleFinalized() {
    const next = status === "finalized" ? "draft" : "finalized";
    try {
      await api.updateCarousel(id, { status: next });
      setStatus(next);
    } catch (err) {
      alert(err instanceof Error ? err.message : "상태 변경 실패");
    }
  }

  async function handleRenameTitle(next: string) {
    await api.updateCarousel(id, { title: next });
    setTitle(next);
  }

  async function handleSave(slides: SlideData[]) {
    try {
      // fabric's toJSON already emits the cover-fit pose (left/top set to the
      // recenter offset, width = image natural pixel size, scaleX/Y = the
      // uniform cover scale). Writing that pose back to the DB used to drift
      // because subsequent loads scaled the coords by canvas.getWidth() (=
      // page + 2·PAD); that's fixed in CanvasEditor's image load (now uses
      // pageW), and the renderer stamps _slotL/T/W/H so we always have the
      // canonical box for reference. Persist the fabric output verbatim —
      // earlier attempts to "restore" the slot box with scale 1 reset cropped
      // the photo to its top-left corner because the slot is smaller than the
      // photo's natural size, which is what produced empty grid cells in
      // exports while thumbnails (which read obj.width × scaleX) stayed fine.
      await api.updateCarousel(id, {
        canvas_data: { canvas_slides: slides, ...carouselMeta },
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : "저장 실패");
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async function handleReapplyTemplate(templateId: number): Promise<SlideData[] | null> {
    const sourceSlides = carouselMeta.source_slides;
    if (!sourceSlides || !Array.isArray(sourceSlides) || sourceSlides.length === 0) {
      alert("이 캐러셀에는 원본 슬라이드 데이터가 없습니다. 다시 만들어 주세요.");
      return null;
    }
    try {
      const rendered = await api.renderCarousel({
        template_id: templateId,
        slides: sourceSlides,
        user_image_urls: carouselMeta.user_image_urls || {},
      });
      const newSlides = rendered.canvas_slides as unknown as SlideData[];
      setCarouselMeta((m) => ({ ...m, template_db_id: templateId }));
      // Persist immediately so the new render survives a reload
      await api.updateCarousel(id, {
        canvas_data: {
          canvas_slides: newSlides,
          source_slides: sourceSlides,
          user_image_urls: carouselMeta.user_image_urls || {},
          user_item_image_urls: carouselMeta.user_item_image_urls || {},
          layout_overrides: carouselMeta.layout_overrides || {},
          template_db_id: templateId,
          caption: carouselMeta.caption,
          hashtags: carouselMeta.hashtags,
        },
      });
      return newSlides;
    } catch (err) {
      alert(err instanceof Error ? err.message : "템플릿 적용 실패");
      return null;
    }
  }

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <p style={{ color: "#e85b5b", marginBottom: 12 }}>{error}</p>
        <button
          onClick={() => router.push("/")}
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
          ← 홈으로
        </button>
      </div>
    );
  }

  if (initialSlides === null) {
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center" }}>
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      <CanvasEditor
        initialSlides={initialSlides}
        onSave={handleSave}
        currentTemplateId={carouselMeta.template_db_id || null}
        canReapplyTemplate={!!carouselMeta.source_slides}
        onReapplyTemplate={handleReapplyTemplate}
        isFinalized={status === "finalized"}
        onToggleFinalized={toggleFinalized}
        title={title}
        onRenameTitle={handleRenameTitle}
        caption={typeof carouselMeta.caption === "string" ? carouselMeta.caption : ""}
        hashtags={Array.isArray(carouselMeta.hashtags) ? carouselMeta.hashtags : []}
        sourcePostUrl={sourcePostUrl}
      />
    </div>
  );
}
