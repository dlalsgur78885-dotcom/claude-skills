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

  async function handleSave(
    slides: SlideData[],
    metaOverride?: { caption?: string; hashtags?: string[] },
  ) {
    try {
      // Caption edits arrive as a metaOverride (the caption isn't a canvas
      // object). Merge it into carouselMeta so this write — and every later
      // autosave — carries the new value.
      const meta = metaOverride ? { ...carouselMeta, ...metaOverride } : carouselMeta;
      if (metaOverride) setCarouselMeta(meta);
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
        canvas_data: { canvas_slides: slides, ...meta },
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : "저장 실패");
    }
  }

  /** 원본 문구가 없는 캐러셀에서, 화면의 글을 긁어 원본을 되만든다.
   *
   *  왜 필요한가 — 템플릿을 씌우려면 서버 `/render` 에 「무엇을 쓸지」(문구)를 줘야 하는데,
   *  참고 글 없이 만든 캐러셀에는 그게 없어 **템플릿 변경이 통째로 잠겨 있었다**
   *  (2026-09-03 피드백 1·2번, 두 건이 같은 원인). 잠그는 대신 있는 글로 되만든다.
   *
   *  ⚠ 캔버스 글상자에는 **역할(headline·body…) 표시가 없다.** 렌더러가 안 남긴다.
   *    그래서 **위에서 아래 순서**로 headline → subtext → body → tag 에 넣는다. 짐작이라
   *    자리가 어긋날 수 있어 부르는 쪽에서 사람에게 먼저 확인한다.
   */
  function deriveSourceSlides(slides: SlideData[]) {
    return slides.map((sl, index) => {
      const texts = (sl.objects || [])
        .filter((o) => typeof o.text === "string" && String(o.text).trim())
        .slice()
        .sort((a, b) => (Number(a.top) || 0) - (Number(b.top) || 0))
        .map((o) => String(o.text));
      return {
        index,
        type: index === 0 ? "cover" : "content",
        headline: texts[0] || "",
        subtext: texts[1] || "",
        body: texts[2] || "",
        tag: texts[3] || "",
      };
    });
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async function handleReapplyTemplate(templateId: number): Promise<SlideData[] | null> {
    let sourceSlides = carouselMeta.source_slides;
    if (!sourceSlides || !Array.isArray(sourceSlides) || sourceSlides.length === 0) {
      const base = initialSlides || [];
      if (base.length === 0) {
        alert("낱장이 없어 템플릿을 씌울 수 없습니다.");
        return null;
      }
      const ok = window.confirm(
        "이 캐러셀에는 원본 문구가 없습니다.\n" +
        "화면의 글을 위에서 아래 순서로 옮겨 템플릿을 씌웁니다 — 자리가 어긋날 수 있습니다.\n\n" +
        "계속할까요?"
      );
      if (!ok) return null;
      sourceSlides = deriveSourceSlides(base);
    }
    try {
      const rendered = await api.renderCarousel({
        template_id: templateId,
        slides: sourceSlides,
        user_image_urls: carouselMeta.user_image_urls || {},
        // 이 둘을 안 넘기면 /create 에서 고른 슬라이드별 레이아웃과 격자 셀 이미지가
        // 템플릿을 바꾸는 순간 조용히 사라진다(저장은 그대로 되면서 렌더에만 빠져
        // 화면과 저장값이 어긋났다). 새 템플릿에 없는 키는 렌더러가 자동 선택으로
        // 넘기므로 그대로 넘겨도 안전하다.
        user_item_image_urls: carouselMeta.user_item_image_urls || {},
        layout_overrides: carouselMeta.layout_overrides || {},
      });
      const newSlides = rendered.canvas_slides as unknown as SlideData[];
      // ⚠ source_slides 도 함께 넣어야 한다. 화면 상태에 안 넣으면 **자동저장이 옛 값으로
      //   덮어쓴다** — 되만든 원본이 사라져 다음번에 또 "원본이 없다" 로 돌아간다
      //   (2026-09-03 E2E 에서 잡음: 적용 직후 source_slides 가 [] 로 저장돼 있었다).
      //   이 파일 위쪽 handleSave 주석의 사고와 같은 종류다.
      setCarouselMeta((m) => ({ ...m, template_db_id: templateId, source_slides: sourceSlides }));
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

  /** 슬라이드 한 장의 레이아웃만 바꾼다 (피드백 슬라이드 7).
   *
   *  템플릿 교체(handleReapplyTemplate)와 다른 점은 **어느 템플릿을 쓰는지는 그대로**
   *  두고 해당 슬라이드의 layout_override 만 바꾼다는 것이다. `layoutRef` 는 이 템플릿
   *  안의 키이거나, 다른 세트에서 빌려온 "@<템플릿id>:<키>" 형식이다 — 백엔드가 렌더
   *  직전에 빌려온 레이아웃을 합쳐 넣는다(template_studio.resolve_borrowed_layouts).
   *
   *  렌더는 전체 슬라이드를 다시 그려 돌려주지만, 호출부(CanvasEditor)가 해당 인덱스
   *  한 장만 교체하므로 다른 슬라이드의 수동 편집은 보존된다.
   */
  async function handleChangeSlideLayout(
    slideIndex: number,
    layoutRef: string,
  ): Promise<SlideData[] | null> {
    const sourceSlides = carouselMeta.source_slides;
    if (!sourceSlides || !Array.isArray(sourceSlides) || sourceSlides.length === 0) {
      alert("이 캐러셀에는 원본 슬라이드 데이터가 없어 레이아웃을 바꿀 수 없습니다.");
      return null;
    }
    const templateId = carouselMeta.template_db_id;
    if (!templateId) {
      alert("템플릿 정보가 없어 레이아웃을 바꿀 수 없습니다.");
      return null;
    }
    const nextOverrides = { ...(carouselMeta.layout_overrides || {}), [slideIndex]: layoutRef };
    try {
      const rendered = await api.renderCarousel({
        template_id: templateId,
        slides: sourceSlides,
        user_image_urls: carouselMeta.user_image_urls || {},
        user_item_image_urls: carouselMeta.user_item_image_urls || {},
        layout_overrides: nextOverrides,
      });
      const newSlides = rendered.canvas_slides as unknown as SlideData[];
      setCarouselMeta((m) => ({ ...m, layout_overrides: nextOverrides }));
      await api.updateCarousel(id, {
        canvas_data: {
          canvas_slides: newSlides,
          source_slides: sourceSlides,
          user_image_urls: carouselMeta.user_image_urls || {},
          user_item_image_urls: carouselMeta.user_item_image_urls || {},
          layout_overrides: nextOverrides,
          template_db_id: templateId,
          caption: carouselMeta.caption,
          hashtags: carouselMeta.hashtags,
        },
      });
      return newSlides;
    } catch (err) {
      alert(err instanceof Error ? err.message : "레이아웃 변경 실패");
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
        onGenerateThumbnail={(blob) => api.uploadCarouselThumbnail(id, blob)}
        currentTemplateId={carouselMeta.template_db_id || null}
        canReapplyTemplate  /* 원본이 없어도 화면 글로 되만든다 → 항상 연다 */
        onReapplyTemplate={handleReapplyTemplate}
        onChangeSlideLayout={handleChangeSlideLayout}
        isFinalized={status === "finalized"}
        onToggleFinalized={toggleFinalized}
        title={title}
        onRenameTitle={handleRenameTitle}
        caption={typeof carouselMeta.caption === "string" ? carouselMeta.caption : ""}
        hashtags={Array.isArray(carouselMeta.hashtags) ? carouselMeta.hashtags : []}
        sourcePostUrl={sourcePostUrl}
        uploadCarouselId={id}
      />
    </div>
  );
}
