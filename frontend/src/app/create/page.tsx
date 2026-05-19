"use client";

import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { api, resolveImageUrl } from "@/lib/api";
import type { TemplateSummary } from "@/lib/types";
import { TemplateThumbnail } from "@/components/template-editor/TemplateThumbnail";

type Slide = { index: number; type: string; headline: string; body?: string; subtext?: string; cta_text?: string; items?: Array<{ title?: string; subtitle?: string; description?: string; image_path?: string }> };
type ImageResult = { id: string; url: string; preview_url: string; width: number; height: number; source: string; _query?: string };
// Composite key: "<slide_index>" for single-slide images, "<slide_index>:<item_index>" for grid cells.
type ImageKey = string;
type SlideImages = Record<ImageKey, ImageResult[]>;
type SelectedImages = Record<ImageKey, ImageResult | null>;
type RefPost = { id: number; caption: string; post_url: string; like_count: number; comment_count: number; slide_count: number; thumbnail: string | null };
type RefImage = { post_id: number; slide_index: number; url: string; caption: string };

function imageKey(slideIdx: number, itemIdx: number | null | undefined): ImageKey {
  return itemIdx === null || itemIdx === undefined ? `${slideIdx}` : `${slideIdx}:${itemIdx}`;
}

// Mirrors backend `carousel_renderer._LAYOUT_PREFERENCE` + `_pick_layout` so
// the frontend can show the user EXACTLY which layout each slide will receive
// at render time. Keep this in sync with the backend (search for the same
// constant name) — divergence means displayed != actual.
const LAYOUT_PREFERENCE: Record<string, string[]> = {
  cover: ["photo_with_caption", "fullbg_overlay", "single_image", "text_only"],
  cta: ["phone_mockup", "fullbg_overlay", "photo_with_caption", "single_image", "text_only"],
  content_grid: ["grid_2x2", "grid_3x1", "grid_1x2", "list_vertical", "photo_with_caption", "single_image"],
  content_list: ["list_vertical", "grid_3x1", "grid_2x2", "photo_with_caption", "single_image"],
  content_solo: ["photo_with_caption", "single_image", "fullbg_overlay", "text_only"],
};

function autoPickLayout(slide: Slide, templateLayouts: string[]): string | null {
  if (!templateLayouts || templateLayouts.length === 0) return null;
  const items = slide.items || [];
  let prefs: string[];
  if (slide.type === "cover") prefs = LAYOUT_PREFERENCE.cover;
  else if (slide.type === "cta") prefs = LAYOUT_PREFERENCE.cta;
  else if (items.length >= 4) prefs = LAYOUT_PREFERENCE.content_grid;
  else if (items.length >= 1) prefs = LAYOUT_PREFERENCE.content_list;
  else prefs = LAYOUT_PREFERENCE.content_solo;
  for (const name of prefs) {
    if (templateLayouts.includes(name)) return name;
  }
  // last resort: first layout the template has
  return templateLayouts[0];
}

// Step labels differ by entry path. The "수집된 소재 → 캐러셀 만들기" flow
// (refIds in the URL) needs the user to pick a template up front — the
// template's grid shape decides how many images each slide consumes, so it
// has to be settled before "이미지 선택" runs.
const STEPS_REF = ["템플릿 선택", "콘텐츠 확인", "이미지 선택", "완성"];
const STEPS_URL = ["경쟁사 URL 입력", "콘텐츠 확인", "이미지 선택", "완성"];

export default function CreatePage() {
  const searchParams = useSearchParams();
  const refParam = searchParams.get("refs");
  const refIds = refParam ? refParam.split(",").map(Number).filter(Boolean) : [];

  const [step, setStep] = useState(0);

  // Step 1
  const [topic, setTopic] = useState("");
  const [postUrlsText, setPostUrlsText] = useState("");
  const [tone, setTone] = useState("professional");
  const [slideCount, setSlideCount] = useState(8);
  const [refPosts, setRefPosts] = useState<RefPost[]>([]);
  const [refImages, setRefImages] = useState<RefImage[]>([]);

  // Step 2
  const [slides, setSlides] = useState<Slide[]>([]);
  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState<string[]>([]);
  const [imageKeywords, setImageKeywords] = useState<{ slide_index: number; item_index?: number | null; keywords: string[]; style: string; country?: string }[]>([]);
  const [generating, setGenerating] = useState(false);

  // Step 3
  const [slideImages, setSlideImages] = useState<SlideImages>({});
  const [selectedImages, setSelectedImages] = useState<SelectedImages>({});
  const [searching, setSearching] = useState(false);
  const [restyling, setRestyling] = useState<Set<ImageKey>>(new Set());
  // composite key → original src before restyle (so user can revert)
  const [originalSrc, setOriginalSrc] = useState<Record<ImageKey, string>>({});

  // Template selection (used in Step 2 / save)
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null);

  // Step 4
  const [saving, setSaving] = useState(false);
  const [savedId, setSavedId] = useState<number | null>(null);

  // Original-size image preview modal (Step 3 picker). Stores the URL to show;
  // null means closed. Clicking the backdrop closes it.
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);

  // Per-slide layout override (slide_index → layout name). Empty when the user
  // hasn't deviated from the auto-pick; populated from the dropdown in Step 1.
  // Reset explicitly inside handleGenerate when a new set of slides comes in —
  // NOT via a `[slides]` effect, because every text edit / paraphrase rebuilds
  // the slides array and would silently wipe the user's layout choices, which
  // is exactly the "레이아웃을 바꿔도 결과에 반영 안 됨" bug.
  const [layoutOverrides, setLayoutOverrides] = useState<Record<number, string>>({});

  // Per-account override for the description-paraphrase prompt. The modal
  // loads the user's saved value AND the system default so the user can see
  // exactly what they're replacing.
  const [paraphrasePromptModalOpen, setParaphrasePromptModalOpen] = useState(false);
  const [paraphrasePrompt, setParaphrasePrompt] = useState<string>("");
  const [paraphrasePromptDefault, setParaphrasePromptDefault] = useState<string>("");
  const [paraphrasePromptSaving, setParaphrasePromptSaving] = useState(false);
  const [paraphrasePromptLoaded, setParaphrasePromptLoaded] = useState(false);

  async function openParaphrasePromptModal() {
    setParaphrasePromptModalOpen(true);
    if (paraphrasePromptLoaded) return;
    try {
      const res = await api.getParaphrasePrompt();
      setParaphrasePrompt(res.prompt || "");
      setParaphrasePromptDefault(res.default_prompt || "");
      setParaphrasePromptLoaded(true);
    } catch (err) {
      alert(err instanceof Error ? err.message : "프롬프트 불러오기 실패");
    }
  }

  async function saveParaphrasePrompt() {
    setParaphrasePromptSaving(true);
    try {
      const res = await api.setParaphrasePrompt(paraphrasePrompt);
      setParaphrasePrompt(res.prompt || "");
      setParaphrasePromptModalOpen(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "프롬프트 저장 실패");
    } finally {
      setParaphrasePromptSaving(false);
    }
  }

  // Template picker popover
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
  const templatePickerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!templatePickerOpen) return;
    function onDown(e: MouseEvent) {
      if (!templatePickerRef.current?.contains(e.target as Node)) setTemplatePickerOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setTemplatePickerOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [templatePickerOpen]);

  // Load templates once on mount
  useEffect(() => {
    api.listTemplates().then((res) => {
      setTemplates(res.templates);
      if (res.templates.length > 0 && selectedTemplateId === null) {
        // Prefer the user's own latest template, fall back to any system template
        const own = res.templates.find((t) => t.user_id !== null);
        setSelectedTemplateId((own || res.templates[0]).id);
      }
    }).catch(() => { /* ignore */ });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Used to fire `handleGenerate` automatically when refIds were in the URL,
  // but the ref flow now opens on a template-picker step instead. The user
  // commits to a template, then clicks "다음" which calls handleGenerate.

  async function handleGenerate(refs?: number[]) {
    const ids = refs || refIds;
    const postUrls = postUrlsText
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter((s) => /instagram\.com\/(p|reel|reels)\//i.test(s));
    if (!topic.trim() && ids.length === 0 && postUrls.length === 0) return;
    setGenerating(true);
    try {
      const res = await (api as any).fetch("/carousels/generate-content", {
        method: "POST",
        body: JSON.stringify({
          topic: topic.trim(),
          tone,
          slide_count: slideCount,
          ref_ids: ids,
          post_urls: postUrls,
        }),
      }) as any;
      // Fresh blueprint → previous per-slide layout choices no longer apply.
      // Reset here (not in a [slides] effect) so subsequent in-place edits
      // (text/paraphrase) preserve the user's layout picks.
      setLayoutOverrides({});
      setSlides(res.slides || []);
      setCaption(res.caption || "");
      setHashtags(res.hashtags || []);
      setImageKeywords(res.image_keywords || []);
      if (res.topic) setTopic(res.topic);
      if (res.ref_posts) setRefPosts(res.ref_posts);
      if (res.ref_images) setRefImages(res.ref_images);
      setStep(1);
    } catch (err) {
      alert(err instanceof Error ? err.message : "콘텐츠 생성 실패");
    } finally {
      setGenerating(false);
    }
  }

  async function handleSearchImages() {
    setSearching(true);
    const results: SlideImages = {};

    async function searchOneEntry(kw: typeof imageKeywords[number]) {
      // 4개 언어 키워드 → 병렬 호출 → round-robin merge + dedupe + unique id
      // country 코드 백엔드로 전달 → 해당 국가 프록시로 라우팅
      const queries = (kw.keywords || []).filter(Boolean);
      const perQuery = await Promise.all(
        queries.map(async (q) => {
          try {
            const res = await api.searchImages(q, kw.style as "photo" | "icon" | "cutout", 12, kw.country);
            return res.images.map((img) => ({ ...img, _query: q }));
          } catch {
            return [];
          }
        })
      );
      const merged: (ImageResult & { _query?: string })[] = [];
      const maxLen = Math.max(0, ...perQuery.map((r) => r.length));
      const seen = new Set<string>();
      for (let i = 0; i < maxLen; i++) {
        for (const list of perQuery) {
          const img = list[i];
          if (!img) continue;
          const dedupKey = img.url || img.preview_url || img.id;
          if (seen.has(dedupKey)) continue;
          seen.add(dedupKey);
          merged.push({ ...img, id: `m${merged.length}-${img.source}-${img.url.slice(-12)}` });
        }
      }
      results[imageKey(kw.slide_index, kw.item_index)] = merged.slice(0, 16);
    }

    // Slides run in batches of 5 — caps Naver/Pexels concurrent load to avoid rate limits.
    const CONCURRENCY = 5;
    for (let i = 0; i < imageKeywords.length; i += CONCURRENCY) {
      const batch = imageKeywords.slice(i, i + CONCURRENCY);
      await Promise.all(batch.map(searchOneEntry));
    }

    setSlideImages(results);
    setSearching(false);
    setStep(2);
  }

  function selectImage(key: ImageKey, img: ImageResult | null) {
    setSelectedImages((prev) => {
      const next = { ...prev, [key]: img };
      // Auto-advance to the next still-unfilled cell after a real pick. Only
      // fires on selections (img != null) — clearing a pick stays put so the
      // user can re-pick without losing their place. Wrapped in rAF so the
      // scroll happens after React has had a chance to commit the new ✓
      // state on the just-clicked cell.
      if (img) {
        requestAnimationFrame(() => {
          const here = imageKeywords.findIndex(
            (kw) => imageKey(kw.slide_index, kw.item_index) === key,
          );
          if (here < 0) return;
          for (let i = here + 1; i < imageKeywords.length; i++) {
            const kw = imageKeywords[i];
            const k = imageKey(kw.slide_index, kw.item_index);
            if (next[k]?.url) continue;             // already picked
            const candidates = slideImages[k];
            if (!candidates || candidates.length === 0) continue;  // no options
            const el = document.querySelector(`[data-image-key="${k}"]`);
            if (el) (el as HTMLElement).scrollIntoView({ behavior: "smooth", block: "center" });
            break;
          }
        });
      }
      return next;
    });
  }

  // Step 2 re-search: when the auto-search results miss the mark, the user
  // edits the query and re-runs the search for that one cell.
  const [researching, setResearching] = useState<Set<ImageKey>>(new Set());
  const [researchQuery, setResearchQuery] = useState<Record<ImageKey, string>>({});

  async function researchOne(key: ImageKey, query: string) {
    const q = query.trim();
    if (!q || researching.has(key)) return;
    setResearching((prev) => new Set(prev).add(key));
    try {
      const [sidxStr, iidxStr] = key.includes(":") ? key.split(":") : [key, ""];
      const sidx = Number(sidxStr);
      const iidx = iidxStr === "" ? null : Number(iidxStr);
      const existing = imageKeywords.find((k) =>
        k.slide_index === sidx && (k.item_index ?? null) === iidx
      );

      // 1) Translate the typed Korean query into search variants. Place →
      //    native script first; general → ko first. Falls back to [q] if LLM
      //    fails, so search always proceeds.
      let queries: string[] = [q];
      let country: string = existing?.country || "kr";
      try {
        const t = await api.translateKeyword(q, topic);
        if (t.queries && t.queries.length > 0) queries = t.queries;
        if (t.country) country = t.country;
      } catch {
        // keep raw fallback
      }

      // 2) Run each variant in parallel, round-robin merge, dedupe.
      const style = (existing?.style as "photo" | "icon" | "cutout") || "photo";
      const perQuery = await Promise.all(
        queries.map(async (qv) => {
          try {
            const res = await api.searchImages(qv, style, 12, country);
            return res.images.map((img) => ({ ...img, _query: qv }));
          } catch {
            return [];
          }
        })
      );
      const merged: (ImageResult & { _query?: string })[] = [];
      const maxLen = Math.max(0, ...perQuery.map((r) => r.length));
      const seen = new Set<string>();
      for (let i = 0; i < maxLen; i++) {
        for (const list of perQuery) {
          const img = list[i];
          if (!img) continue;
          const dedupKey = img.url || img.preview_url || img.id;
          if (seen.has(dedupKey)) continue;
          seen.add(dedupKey);
          merged.push({ ...img, id: `r${Date.now()}-${merged.length}-${img.source}-${img.url.slice(-12)}` });
        }
      }
      const results = merged.slice(0, 16);

      setSlideImages((prev) => ({ ...prev, [key]: results }));
      // The user-facing keyword stays Korean (their input). Internally we
      // store the multi-language variants in `keywords` so saved state retains
      // the translation for any later re-search.
      setImageKeywords((prev) => prev.map((k) =>
        k.slide_index === sidx && (k.item_index ?? null) === iidx
          ? { ...k, keywords: [q, ...queries.filter((v) => v !== q)], country }
          : k
      ));
      setSelectedImages((prev) => ({ ...prev, [key]: null }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "재검색 실패");
    } finally {
      setResearching((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
    }
  }

  async function restyleSelected(key: ImageKey) {
    const img = selectedImages[key];
    if (!img || restyling.has(key)) return;
    setRestyling((prev) => new Set(prev).add(key));
    try {
      const res = await api.restyleImage({
        source_url: img.url,
        brand_mood: "editorial travel magazine",
      });
      // res.url is a relative path `/api/images/...` — browser resolves same-origin.
      const fullUrl = res.url;
      // Remember original for revert
      setOriginalSrc((prev) => ({ ...prev, [key]: prev[key] || img.url }));
      setSelectedImages((prev) => ({
        ...prev,
        [key]: { ...img, url: fullUrl, preview_url: fullUrl, source: "restyled" },
      }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "스타일 변환 실패");
    } finally {
      setRestyling((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
    }
  }

  async function cutoutSelected(key: ImageKey, mode: "standard" | "generative" = "standard") {
    const img = selectedImages[key];
    if (!img || restyling.has(key)) return;
    setRestyling((prev) => new Set(prev).add(key));
    try {
      const res = await api.cutoutImage({ source_url: img.url, mode });
      // res.url is a relative path `/api/images/...` — browser resolves same-origin.
      const fullUrl = res.url;
      setOriginalSrc((prev) => ({ ...prev, [key]: prev[key] || img.url }));
      setSelectedImages((prev) => ({
        ...prev,
        [key]: { ...img, url: fullUrl, preview_url: fullUrl, source: mode === "generative" ? "cutout-gen" : "cutout" },
      }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "누끼 제거 실패");
    } finally {
      setRestyling((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
    }
  }

  function revertRestyle(key: ImageKey) {
    const orig = originalSrc[key];
    const img = selectedImages[key];
    if (!orig || !img) return;
    setSelectedImages((prev) => ({
      ...prev,
      [key]: { ...img, url: orig, preview_url: orig, source: "naver" },
    }));
    setOriginalSrc((prev) => {
      const n = { ...prev };
      delete n[key];
      return n;
    });
  }

  async function handleSave() {
    if (!selectedTemplateId) {
      alert("템플릿을 먼저 선택하세요.");
      return;
    }

    // Collect every cell that still needs a pick. Walk in keyword order so
    // "first missing" follows the visual top-to-bottom layout of the picker.
    const missing: { sidx: number; iidx: number | null; key: ImageKey }[] = [];
    for (const kw of imageKeywords) {
      const key = imageKey(kw.slide_index, kw.item_index);
      if (selectedImages[key]?.url) continue;
      const candidates = slideImages[key];
      if (!candidates || candidates.length === 0) continue; // no candidates → not user's fault
      missing.push({ sidx: kw.slide_index, iidx: kw.item_index ?? null, key });
    }
    if (missing.length > 0) {
      // Scroll the first un-picked cell into view and surface a brief alert,
      // instead of auto-filling silently. The red outline on the cell already
      // tells the user where the gap is.
      const first = missing[0];
      const el = document.querySelector(`[data-image-key="${first.key}"]`) as HTMLElement | null;
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      const where = first.iidx == null
        ? `슬라이드 ${first.sidx + 1}`
        : `슬라이드 ${first.sidx + 1} · 셀 ${first.iidx + 1}`;
      alert(`아직 ${missing.length}개 셀에 이미지가 선택되지 않았습니다.\n빨간색으로 표시된 칸을 채워주세요.\n\n첫 미선택: ${where}`);
      return;
    }
    const ensured: SelectedImages = selectedImages;

    setSaving(true);
    try {
      // 1. Split selected images by composite key:
      //    "<slide>"        → background image for that slide
      //    "<slide>:<item>" → per-cell image for grid slides
      const userImageUrls: Record<number, string> = {};
      const userItemImageUrls: Record<number, Record<number, string>> = {};
      for (const [k, v] of Object.entries(ensured)) {
        if (!v?.url) continue;
        if (k.includes(":")) {
          const [s, i] = k.split(":").map(Number);
          (userItemImageUrls[s] ||= {})[i] = v.url;
        } else {
          userImageUrls[Number(k)] = v.url;
        }
      }

      // 2. Server applies the chosen template to the blueprint slides
      const rendered = await api.renderCarousel({
        template_id: selectedTemplateId,
        slides: slides as unknown as Record<string, unknown>[],
        user_image_urls: userImageUrls,
        user_item_image_urls: userItemImageUrls,
        layout_overrides: layoutOverrides,
      });

      // 3. Persist the rendered canvas slides + the source blueprint so the
      //    editor can re-apply a different template later without re-running
      //    Gemini Vision.
      const tplSlug = String(rendered.template_slug || "minimal");
      const res = await api.createCarousel({
        title: (slides[0]?.headline || topic).replace(/\n/g, " "),
        template_id: tplSlug,
        canvas_data: {
          canvas_slides: rendered.canvas_slides,
          source_slides: slides,
          user_image_urls: userImageUrls,
          user_item_image_urls: userItemImageUrls,
          layout_overrides: layoutOverrides,
          template_db_id: selectedTemplateId,
          caption,
          hashtags,
        },
      });
      setSavedId((res as { id: number }).id);
      setStep(3);
    } catch (err) {
      alert(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  function updateSlide(index: number, field: string, value: string) {
    setSlides((prev) => prev.map((s) => (s.index === index ? { ...s, [field]: value } : s)));
  }

  // Mutate one cell inside a grid slide. Used by Step 1 to let the user edit
  // each item's title/description before the template renders the carousel.
  function updateSlideItem(slideIdx: number, itemIdx: number, field: "title" | "description" | "subtitle", value: string) {
    setSlides((prev) => prev.map((s) => {
      if (s.index !== slideIdx) return s;
      const items = (s.items || []).map((it, j) =>
        j === itemIdx ? { ...it, [field]: value } : it
      );
      return { ...s, items };
    }));
  }

  // Paraphrase one or more descriptions through the backend. `targets` lists
  // (slideIdx, itemIdx-or-null) pairs whose description text gets rewritten.
  // All targets go in one LLM call (one HTTP roundtrip = "parallel" treatment),
  // then results land back atomically.
  type ParaTarget = { sidx: number; iidx: number | null };
  const [paraphrasing, setParaphrasing] = useState<Set<string>>(new Set());
  const paraKey = (t: ParaTarget) => imageKey(t.sidx, t.iidx);

  const [captionBusy, setCaptionBusy] = useState(false);
  async function paraphraseCaption() {
    if (!caption.trim() || captionBusy) return;
    setCaptionBusy(true);
    try {
      const res = await api.paraphraseCaption(caption, topic);
      if (res.paraphrased) setCaption(res.paraphrased);
    } catch (err) {
      alert(err instanceof Error ? err.message : "캡션 치환 실패");
    } finally {
      setCaptionBusy(false);
    }
  }

  async function paraphraseTargets(targets: ParaTarget[]) {
    if (targets.length === 0) return;
    // Gather current description text per target
    const payload: { target: ParaTarget; text: string }[] = [];
    for (const t of targets) {
      const slide = slides.find((s) => s.index === t.sidx);
      if (!slide) continue;
      const txt = t.iidx == null
        ? (slide.body || "").trim()
        : ((slide.items || [])[t.iidx]?.description || "").trim();
      if (!txt) continue;
      payload.push({ target: t, text: txt });
    }
    if (payload.length === 0) return;
    const keys = payload.map(({ target }) => paraKey(target));
    setParaphrasing((prev) => {
      const next = new Set(prev);
      for (const k of keys) next.add(k);
      return next;
    });
    try {
      const res = await api.paraphrase(payload.map((p) => p.text));
      const rewrites = res.paraphrased || [];
      setSlides((prev) => prev.map((s) => {
        const slideTargets = payload
          .map((p, i) => ({ p, rewrite: rewrites[i] }))
          .filter(({ p }) => p.target.sidx === s.index && rewrites[payload.indexOf(p)]);
        if (slideTargets.length === 0) return s;
        let next = { ...s };
        for (const { p, rewrite } of slideTargets) {
          if (!rewrite) continue;
          if (p.target.iidx == null) {
            next = { ...next, body: rewrite };
          } else {
            const items = (next.items || []).map((it, j) =>
              j === p.target.iidx ? { ...it, description: rewrite } : it
            );
            next = { ...next, items };
          }
        }
        return next;
      }));
    } catch (err) {
      alert(err instanceof Error ? err.message : "치환 실패");
    } finally {
      setParaphrasing((prev) => {
        const next = new Set(prev);
        for (const k of keys) next.delete(k);
        return next;
      });
    }
  }

  function updateKeyword(slideIndex: number, itemIndex: number | null | undefined, value: string) {
    setImageKeywords((prev) => prev.map((k) => {
      const sameSlide = k.slide_index === slideIndex;
      const sameItem = (k.item_index ?? null) === (itemIndex ?? null);
      return sameSlide && sameItem ? { ...k, keywords: [value] } : k;
    }));
  }

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "8px 12px", fontSize: 13,
    background: "var(--bg-overlay)", color: "var(--text-primary)",
    border: "1px solid var(--border)", borderRadius: 6, outline: "none",
  };

  const STEPS = refIds.length > 0 ? STEPS_REF : STEPS_URL;

  return (
    <div style={{ padding: "32px 40px", maxWidth: 760, margin: "0 auto" }}>
      {/* Steps */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
        {STEPS.map((label, i) => (
          <div key={label} style={{ flex: 1, textAlign: "center" }}>
            <div style={{ height: 3, borderRadius: 2, marginBottom: 8, background: i <= step ? "var(--accent)" : "var(--border)", transition: "background 0.2s" }} />
            <span style={{ fontSize: 11, fontWeight: i === step ? 600 : 400, color: i <= step ? "var(--text-primary)" : "var(--text-tertiary)" }}>{label}</span>
          </div>
        ))}
      </div>

      {/* 템플릿 선택 dropdown — Step 0부터 보이되, refIds 모드 Step 0는
          이미 본문에서 큰 카드 그리드로 템플릿을 보여주므로 중복을 피해 숨김. */}
      {step < 3 && !(step === 0 && refIds.length > 0) && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "10px 14px",
            marginBottom: 24,
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: 8,
          }}
        >
          <span style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 500, whiteSpace: "nowrap" }}>
            템플릿
          </span>
          <div ref={templatePickerRef} style={{ position: "relative", flex: 1 }}>
            {(() => {
              const selected = selectedTemplateId
                ? templates.find((t) => t.id === selectedTemplateId)
                : null;
              return (
                <button
                  type="button"
                  onClick={() => setTemplatePickerOpen((o) => !o)}
                  disabled={templates.length === 0}
                  style={{
                    ...inputStyle,
                    cursor: templates.length === 0 ? "not-allowed" : "pointer",
                    padding: "6px 10px",
                    fontSize: 13,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    textAlign: "left",
                    width: "100%",
                  }}
                >
                  {selected ? (
                    <>
                      {/* Inline mini-thumb of current selection */}
                      <span style={{ display: "inline-flex", width: 28, height: 28, borderRadius: 4, overflow: "hidden", flexShrink: 0 }}>
                        <TemplateThumbnail templateId={selected.id} size={28} />
                      </span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {selected.name}
                        {selected.user_id === null ? " (시스템)" : ""}
                        {selected.layouts.length > 0 ? ` — ${selected.layouts.join(", ")}` : ""}
                      </span>
                    </>
                  ) : (
                    <span style={{ flex: 1, color: "var(--text-tertiary)" }}>
                      {templates.length === 0 ? "템플릿이 없습니다 — /templates에서 먼저 만드세요" : "템플릿을 선택하세요"}
                    </span>
                  )}
                  <span style={{ color: "var(--text-tertiary)", fontSize: 11 }}>▾</span>
                </button>
              );
            })()}

            {templatePickerOpen && templates.length > 0 && (
              <div
                style={{
                  position: "absolute",
                  top: "calc(100% + 4px)",
                  left: 0,
                  right: 0,
                  zIndex: 50,
                  background: "var(--bg-base)",
                  border: "1px solid var(--border)",
                  borderRadius: 8,
                  boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                  padding: 8,
                  maxHeight: 560,
                  overflowY: "auto",
                }}
              >
                {/* List rows — one per template. Each row shows ALL of that
                    template's layouts as labelled mini-thumbnails so the user
                    can see exactly what designs are inside before picking. */}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {templates.map((t) => {
                    const isSelected = t.id === selectedTemplateId;
                    return (
                      <div
                        key={t.id}
                        onClick={() => {
                          setSelectedTemplateId(t.id);
                          setTemplatePickerOpen(false);
                        }}
                        style={{
                          padding: 10,
                          background: isSelected ? "var(--accent-muted)" : "var(--bg-subtle)",
                          border: `1px solid ${isSelected ? "var(--accent)" : "var(--border)"}`,
                          borderRadius: 6,
                          cursor: "pointer",
                          color: "var(--text-primary)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                          <span style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</span>
                          {t.user_id === null && (
                            <span style={{ fontSize: 9, color: "var(--text-tertiary)" }}>시스템</span>
                          )}
                          <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-tertiary)" }}>
                            레이아웃 {t.layouts.length}개
                          </span>
                        </div>
                        {t.layouts.length > 0 ? (
                          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {t.layouts.map((layoutName) => (
                              <div
                                key={layoutName}
                                style={{
                                  display: "flex",
                                  flexDirection: "column",
                                  alignItems: "center",
                                  gap: 3,
                                  flexShrink: 0,
                                }}
                              >
                                <div style={{ background: "var(--bg-overlay)", borderRadius: 4, padding: 3 }}>
                                  <TemplateThumbnail templateId={t.id} layoutName={layoutName} size={88} />
                                </div>
                                <span style={{ fontSize: 9, color: "var(--text-tertiary)", maxWidth: 94, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {layoutName}
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>레이아웃 정보 없음</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
          {selectedTemplateId && templates.find((t) => t.id === selectedTemplateId)?.user_id === null && (
            <span style={{ fontSize: 10, color: "var(--text-tertiary)", flexShrink: 0 }}>
              시스템 (수정 불가)
            </span>
          )}
        </div>
      )}

      {/* Step 0 — REF flow: pick a template before generating content.
          The template's grid shape decides slide layouts and how many images
          each slide consumes, so locking it in first means step 2 (이미지 선택)
          can show the right number of slots from the start. */}
      {step === 0 && !generating && refIds.length > 0 && (
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", margin: "0 0 8px" }}>템플릿 선택</h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 20 }}>
            선택한 {refIds.length}개 포스트를 어떤 디자인으로 만들지 정해주세요. 템플릿의 슬라이드 구성에 따라 다음 단계에서 가져올 이미지 수가 달라집니다.
          </p>
          {templates.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13, border: "1px dashed var(--border)", borderRadius: 8 }}>
              템플릿을 불러오는 중…
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {templates.map((t) => {
                const isSelected = t.id === selectedTemplateId;
                return (
                  <div
                    key={t.id}
                    onClick={() => setSelectedTemplateId(t.id)}
                    style={{
                      padding: 12,
                      background: isSelected ? "var(--accent-muted)" : "var(--bg-subtle)",
                      border: `1px solid ${isSelected ? "var(--accent)" : "var(--border)"}`,
                      borderRadius: 8,
                      cursor: "pointer",
                      color: "var(--text-primary)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
                      <span style={{ fontSize: 14, fontWeight: 600 }}>{t.name}</span>
                      {t.user_id === null && (
                        <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>시스템</span>
                      )}
                      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-tertiary)" }}>
                        레이아웃 {t.layouts.length}개
                      </span>
                    </div>
                    {t.layouts.length > 0 ? (
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {t.layouts.map((layoutName) => (
                          <div
                            key={layoutName}
                            style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0 }}
                          >
                            <div style={{ background: "var(--bg-overlay)", borderRadius: 4, padding: 3 }}>
                              <TemplateThumbnail templateId={t.id} layoutName={layoutName} size={96} />
                            </div>
                            <span style={{ fontSize: 10, color: "var(--text-tertiary)", maxWidth: 102, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {layoutName}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>레이아웃 정보 없음</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 20 }}>
            <button
              onClick={() => handleGenerate(refIds)}
              disabled={!selectedTemplateId || generating}
              style={{
                padding: "10px 20px",
                fontSize: 13,
                fontWeight: 600,
                color: "white",
                background: "var(--accent)",
                border: "none",
                borderRadius: 8,
                cursor: !selectedTemplateId || generating ? "not-allowed" : "pointer",
                opacity: !selectedTemplateId || generating ? 0.5 : 1,
              }}
            >
              이 템플릿으로 콘텐츠 생성 →
            </button>
          </div>
        </div>
      )}

      {/* Step 0: 경쟁사 URL 입력 (레퍼런스 없을 때) */}
      {step === 0 && !generating && refIds.length === 0 && (() => {
        const validUrls = postUrlsText
          .split(/[\n,]+/)
          .map((s) => s.trim())
          .filter((s) => /instagram\.com\/(p|reel|reels)\//i.test(s));
        const canSubmit = refIds.length > 0 || validUrls.length > 0 || topic.trim().length > 0;
        return (
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", margin: "0 0 8px" }}>캐러셀 만들기</h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 28 }}>
            {refIds.length > 0
              ? `선택한 ${refIds.length}개 포스트를 레퍼런스로 콘텐츠를 생성합니다`
              : "경쟁사 게시글 URL을 붙여넣으면 자동 분석 후 슬라이드/이미지 키워드를 생성합니다"}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6, fontWeight: 500 }}>
                경쟁사 게시글 URL <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>(여러 개는 줄바꿈으로 구분)</span>
              </label>
              <textarea
                value={postUrlsText}
                onChange={(e) => setPostUrlsText(e.target.value)}
                placeholder={"https://www.instagram.com/p/DXItkDNEZTj/\nhttps://www.instagram.com/reel/XXXX/"}
                rows={4}
                autoFocus
                style={{ ...inputStyle, fontFamily: "monospace", fontSize: 12, resize: "vertical", lineHeight: 1.6 }}
              />
              {postUrlsText && (
                <p style={{ fontSize: 11, color: validUrls.length > 0 ? "var(--text-secondary)" : "#e85b5b", marginTop: 4 }}>
                  {validUrls.length > 0 ? `${validUrls.length}개 URL 인식됨` : "유효한 인스타그램 URL이 없습니다"}
                </p>
              )}
            </div>
            <details style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
              <summary style={{ cursor: "pointer", color: "var(--text-secondary)", fontWeight: 500, marginBottom: 6 }}>
                고급 옵션 (톤·슬라이드 수·주제 직접 입력)
              </summary>
              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: 10 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6, fontWeight: 500 }}>주제 (선택)</label>
                  <input type="text" value={topic} onChange={(e) => setTopic(e.target.value)}
                    placeholder="비워두면 URL에서 자동 추출" style={inputStyle} />
                </div>
                <div style={{ display: "flex", gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6, fontWeight: 500 }}>톤</label>
                    <select value={tone} onChange={(e) => setTone(e.target.value)} style={{ ...inputStyle, cursor: "pointer" }}>
                      <option value="professional">전문적</option>
                      <option value="casual">캐주얼</option>
                      <option value="educational">교육적</option>
                      <option value="viral">바이럴</option>
                    </select>
                  </div>
                  <div style={{ flex: 1 }}>
                    <label style={{ display: "block", fontSize: 12, color: "var(--text-secondary)", marginBottom: 6, fontWeight: 500 }}>슬라이드 수</label>
                    <select value={slideCount} onChange={(e) => setSlideCount(Number(e.target.value))} style={{ ...inputStyle, cursor: "pointer" }}>
                      {[5, 6, 7, 8, 9, 10].map((n) => <option key={n} value={n}>{n}장</option>)}
                    </select>
                  </div>
                </div>
              </div>
            </details>
            <button onClick={() => handleGenerate()} disabled={generating || !canSubmit}
              style={{ padding: "10px 20px", fontSize: 13, fontWeight: 600, color: "white", background: "var(--accent)", border: "none", borderRadius: 8, cursor: "pointer", opacity: generating || !canSubmit ? 0.5 : 1 }}>
              {validUrls.length > 0 ? `${validUrls.length}개 URL로 콘텐츠 생성` : "콘텐츠 생성"}
            </button>
          </div>
        </div>
        );
      })()}

      {/* 생성 중 로딩 */}
      {step === 0 && generating && (
        <div style={{ textAlign: "center", paddingTop: 80 }}>
          <div className="spinner" style={{ margin: "0 auto 16px" }} />
          <p style={{ fontSize: 14, color: "var(--text-secondary)" }}>
            {refIds.length > 0 ? "레퍼런스 분석 중..." : "URL 수집 + 콘텐츠 생성 중..."}
          </p>
        </div>
      )}

      {/* Step 1: 콘텐츠 확인 */}
      {step === 1 && (
        <div>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
            <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>콘텐츠 확인</h1>
            <button
              type="button"
              onClick={openParaphrasePromptModal}
              title="🔄 병렬 치환 버튼이 사용하는 LLM 프롬프트를 본인 계정에만 적용되게 수정"
              style={{
                padding: "5px 10px",
                fontSize: 11,
                fontWeight: 500,
                color: "rgb(180,165,255)",
                background: "rgba(120,100,255,0.12)",
                border: "1px solid rgba(120,100,255,0.3)",
                borderRadius: 5,
                cursor: "pointer",
              }}
            >
              ⚙ 병렬 치환 프롬프트 설정
            </button>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 24 }}>
            슬라이드 문구를 확인하고 수정하세요
          </p>

          {/* 레퍼런스 포스트 표시 */}
          {refPosts.length > 0 && (
            <div style={{ marginBottom: 20, padding: 12, background: "var(--bg-subtle)", border: "1px solid var(--border)", borderRadius: 8 }}>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600 }}>레퍼런스</span>
              <div style={{ display: "flex", gap: 8, marginTop: 8, overflowX: "auto" }}>
                {refPosts.map((rp) => (
                  <a key={rp.id} href={rp.post_url} target="_blank" rel="noopener noreferrer"
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, flexShrink: 0, textDecoration: "none", transition: "border-color 0.12s" }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}>
                    {rp.thumbnail && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={rp.thumbnail} alt="" style={{ width: 28, height: 28, borderRadius: 4, objectFit: "cover" }} />
                    )}
                    <div>
                      <p style={{ fontSize: 11, color: "var(--text-primary)", margin: 0, maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {rp.caption || "캡션 없음"}
                      </p>
                      <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>
                        {rp.like_count.toLocaleString()} likes · {rp.slide_count}장
                      </span>
                    </div>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* 슬라이드 편집 */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 24 }}>
            {slides.map((slide) => {
              const slideKw = imageKeywords.find((k) => k.slide_index === slide.index && (k.item_index ?? null) === null);
              const cellKws = imageKeywords.filter((k) => k.slide_index === slide.index && (k.item_index ?? null) !== null);
              const refImg = refImages.find((r) => r.slide_index === slide.index);
              const items = slide.items || [];
              const isGrid = cellKws.length > 0 && items.length > 0;
              return (
                <div key={slide.index} style={{ padding: 14, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, display: "flex", gap: 12 }}>
                  {/* 원본 슬라이드 썸네일 */}
                  <div style={{ flexShrink: 0 }}>
                    {refImg ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={refImg.url}
                        alt={`slide ${slide.index}`}
                        style={{ width: 120, height: 120, borderRadius: 6, objectFit: "cover", background: "var(--bg-overlay)", border: "1px solid var(--border)" }}
                        onError={(e) => { (e.target as HTMLImageElement).style.opacity = "0.3"; }}
                      />
                    ) : (
                      <div style={{
                        width: 120, height: 120, borderRadius: 6, background: "var(--bg-overlay)",
                        border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center",
                        color: "var(--text-tertiary)", fontSize: 11,
                      }}>
                        no ref
                      </div>
                    )}
                    <div style={{
                      marginTop: 6, fontSize: 11, fontWeight: 600, textAlign: "center",
                      color: slide.type === "cover" ? "var(--accent-text)" : slide.type === "cta" ? "var(--green)" : "var(--text-tertiary)",
                    }}>
                      {slide.type === "cover" ? "표지" : slide.type === "cta" ? "CTA" : `#${slide.index}`}
                      {isGrid && <span style={{ display: "block", fontSize: 9, color: "var(--text-tertiary)", marginTop: 2 }}>그리드 {cellKws.length}셀</span>}
                    </div>
                    {/* Per-slide layout picker. Shows the auto-matched layout
                        from the selected template; user can override here so
                        e.g. single-item slides don't all fall back to
                        fullbg_overlay when the template lacks a card layout. */}
                    {(() => {
                      const tpl = templates.find((t) => t.id === selectedTemplateId);
                      const tplLayouts = tpl?.layouts || [];
                      if (tplLayouts.length === 0) return null;
                      const auto = autoPickLayout(slide, tplLayouts);
                      const current = layoutOverrides[slide.index] || auto || "";
                      const isOverridden = !!layoutOverrides[slide.index] && layoutOverrides[slide.index] !== auto;
                      return (
                        <div style={{ marginTop: 6, width: 120 }}>
                          <div style={{ fontSize: 9, color: "var(--text-tertiary)", marginBottom: 2, textAlign: "left" }}>
                            레이아웃 {isOverridden && <span style={{ color: "var(--accent-text)" }}>· 수정됨</span>}
                          </div>
                          <select
                            value={current}
                            onChange={(e) => {
                              const v = e.target.value;
                              setLayoutOverrides((prev) => {
                                const next = { ...prev };
                                if (!v || v === auto) delete next[slide.index];
                                else next[slide.index] = v;
                                return next;
                              });
                            }}
                            style={{
                              width: "100%",
                              padding: "3px 6px",
                              fontSize: 10,
                              background: "var(--bg-overlay)",
                              color: "var(--text-primary)",
                              border: `1px solid ${isOverridden ? "var(--accent)" : "var(--border)"}`,
                              borderRadius: 4,
                              cursor: "pointer",
                            }}
                            title={`자동 매치: ${auto || "(없음)"}\n다른 레이아웃 선택 시 백엔드 폴백 무시`}
                          >
                            {tplLayouts.map((l) => (
                              <option key={l} value={l}>
                                {l}{l === auto ? " (자동)" : ""}
                              </option>
                            ))}
                          </select>
                        </div>
                      );
                    })()}
                  </div>

                  {/* 텍스트 입력 */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <input type="text" value={slide.headline} onChange={(e) => updateSlide(slide.index, "headline", e.target.value)}
                      style={{ ...inputStyle, fontWeight: 600, marginBottom: 6 }} placeholder="제목" />

                    {/* Single-element slide: headline + description + (optional cover subtext) + keyword */}
                    {!isGrid && (slide.body || slide.subtext || slide.type === "content" || slide.type === "cover") && (() => {
                      const k = imageKey(slide.index, null);
                      const busy = paraphrasing.has(k);
                      const has = !!(slide.body || "").trim();
                      return (
                        <div style={{ marginBottom: 6 }}>
                          <textarea
                            value={slide.body || ""}
                            onChange={(e) => updateSlide(slide.index, "body", e.target.value)}
                            rows={2}
                            style={{ ...inputStyle, resize: "vertical", lineHeight: 1.4, fontFamily: "inherit" }}
                            placeholder="설명 (description)"
                          />
                          <button
                            onClick={() => paraphraseTargets([{ sidx: slide.index, iidx: null }])}
                            disabled={busy || !has}
                            title="같은 의미, 다른 표현으로 다시 쓰기"
                            style={{
                              marginTop: 4, padding: "3px 10px", fontSize: 11, fontWeight: 500,
                              color: "rgb(180,165,255)", background: "rgba(120,100,255,0.12)",
                              border: "1px solid rgba(120,100,255,0.3)", borderRadius: 5,
                              cursor: busy || !has ? "default" : "pointer",
                              opacity: busy || !has ? 0.5 : 1,
                            }}
                          >
                            {busy ? "치환 중…" : "🔄 병렬 치환"}
                          </button>
                        </div>
                      );
                    })()}
                    {!isGrid && slideKw && (
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 11, color: "var(--text-tertiary)", flexShrink: 0, minWidth: 44 }}>이미지</span>
                        <input type="text" value={slideKw.keywords[0] || ""} onChange={(e) => updateKeyword(slide.index, null, e.target.value)}
                          style={{ ...inputStyle, fontSize: 11 }} placeholder="검색 키워드" />
                      </div>
                    )}

                    {/* Grid slide: each cell shows title + description + keyword, all editable */}
                    {isGrid && (() => {
                      const slideCellTargets: ParaTarget[] = cellKws
                        .map((kw) => ({ sidx: slide.index, iidx: kw.item_index as number }))
                        .filter((t) => {
                          if (t.iidx == null) return false;
                          const txt = (items[t.iidx]?.description || "").trim();
                          return !!txt;
                        });
                      const slideBusy = slideCellTargets.some((t) => paraphrasing.has(paraKey(t)));
                      return (
                        <>
                          {slideCellTargets.length > 1 && (
                            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 6 }}>
                              <button
                                onClick={() => paraphraseTargets(slideCellTargets)}
                                disabled={slideBusy}
                                title={`이 슬라이드의 ${slideCellTargets.length}개 설명을 한 번에 다른 표현으로 다시 쓰기`}
                                style={{
                                  padding: "4px 12px", fontSize: 11, fontWeight: 500,
                                  color: "rgb(180,165,255)", background: "rgba(120,100,255,0.15)",
                                  border: "1px solid rgba(120,100,255,0.35)", borderRadius: 5,
                                  cursor: slideBusy ? "default" : "pointer",
                                  opacity: slideBusy ? 0.5 : 1,
                                }}
                              >
                                {slideBusy ? "치환 중…" : `🔄 ${slideCellTargets.length}개 병렬 치환`}
                              </button>
                            </div>
                          )}
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {cellKws.map((kw) => {
                              const itemIdx = kw.item_index as number;
                              const item = items[itemIdx];
                              const k = imageKey(slide.index, itemIdx);
                              const cellBusy = paraphrasing.has(k);
                              const hasDesc = !!(item?.description || "").trim();
                              return (
                                <div key={itemIdx} style={{
                                  display: "flex", flexDirection: "column", gap: 4,
                                  padding: 8, background: "var(--bg-subtle)",
                                  border: "1px solid var(--border)", borderRadius: 6,
                                }}>
                                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", flexShrink: 0, minWidth: 18 }}>
                                      #{itemIdx + 1}
                                    </span>
                                    <input
                                      type="text"
                                      value={item?.title || ""}
                                      onChange={(e) => updateSlideItem(slide.index, itemIdx, "title", e.target.value)}
                                      style={{ ...inputStyle, fontSize: 12, fontWeight: 500, padding: "5px 8px" }}
                                      placeholder="제목"
                                    />
                                  </div>
                                  <textarea
                                    value={item?.description || ""}
                                    onChange={(e) => updateSlideItem(slide.index, itemIdx, "description", e.target.value)}
                                    rows={2}
                                    style={{ ...inputStyle, fontSize: 11, padding: "5px 8px", resize: "vertical", lineHeight: 1.4, fontFamily: "inherit" }}
                                    placeholder="설명 (description)"
                                  />
                                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    <button
                                      onClick={() => paraphraseTargets([{ sidx: slide.index, iidx: itemIdx }])}
                                      disabled={cellBusy || !hasDesc}
                                      title="같은 의미, 다른 표현으로 다시 쓰기"
                                      style={{
                                        padding: "2px 8px", fontSize: 10, fontWeight: 500,
                                        color: "rgb(180,165,255)", background: "rgba(120,100,255,0.12)",
                                        border: "1px solid rgba(120,100,255,0.3)", borderRadius: 4,
                                        cursor: cellBusy || !hasDesc ? "default" : "pointer",
                                        opacity: cellBusy || !hasDesc ? 0.5 : 1,
                                      }}
                                    >
                                      {cellBusy ? "치환 중…" : "🔄 치환"}
                                    </button>
                                    <span style={{ fontSize: 10, color: "var(--text-tertiary)", flexShrink: 0, marginLeft: "auto" }}>이미지</span>
                                    <input
                                      type="text"
                                      value={kw.keywords[0] || ""}
                                      onChange={(e) => updateKeyword(slide.index, kw.item_index, e.target.value)}
                                      style={{ ...inputStyle, fontSize: 11, padding: "5px 8px", flex: 1 }}
                                      placeholder="검색 키워드"
                                    />
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              );
            })}
          </div>

          {/* 캡션 */}
          <div style={{ padding: 14, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
              <label style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 500 }}>
                캡션 <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>(첫 줄은 '더보기' 후킹 미끼)</span>
              </label>
              <button
                onClick={paraphraseCaption}
                disabled={captionBusy || !caption.trim()}
                title="첫 줄을 10자 이내 후킹 문구로 + 본문을 같은 의미 다른 표현으로"
                style={{
                  padding: "4px 12px", fontSize: 11, fontWeight: 500,
                  color: "rgb(180,165,255)", background: "rgba(120,100,255,0.15)",
                  border: "1px solid rgba(120,100,255,0.35)", borderRadius: 5,
                  cursor: captionBusy || !caption.trim() ? "default" : "pointer",
                  opacity: captionBusy || !caption.trim() ? 0.5 : 1,
                }}
              >
                {captionBusy ? "치환 중…" : "🔄 치환"}
              </button>
            </div>
            <textarea value={caption} onChange={(e) => setCaption(e.target.value)} rows={4}
              style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6, fontFamily: "inherit" }} />
            {hashtags.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
                {hashtags.map((tag, i) => (
                  <span key={`${tag}-${i}`} style={{ fontSize: 11, color: "var(--accent-text)", background: "var(--accent-muted)", padding: "2px 8px", borderRadius: 4 }}>{tag}</span>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => setStep(0)}
              style={{ padding: "10px 20px", fontSize: 13, color: "var(--text-secondary)", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer" }}>
              이전
            </button>
            <button onClick={handleSearchImages} disabled={searching}
              style={{ flex: 1, padding: "10px 20px", fontSize: 13, fontWeight: 600, color: "white", background: "var(--accent)", border: "none", borderRadius: 8, cursor: searching ? "default" : "pointer", opacity: searching ? 0.5 : 1 }}>
              {searching ? "이미지 검색 중..." : "이미지 검색"}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: 이미지 선택 */}
      {step === 2 && (
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", margin: "0 0 8px" }}>이미지 선택</h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 16 }}>
            각 슬라이드에 사용할 이미지를 선택하세요
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 24, marginBottom: 24 }}>
            {slides.map((slide) => {
              // Collect all (item_index, label) pairs we need to render a picker for.
              const slideEntries: { itemIndex: number | null; label: string }[] = [];
              const cellKws = imageKeywords.filter((k) => k.slide_index === slide.index && (k.item_index ?? null) !== null);
              if (cellKws.length > 0) {
                const items = slide.items || [];
                cellKws.sort((a, b) => (a.item_index as number) - (b.item_index as number));
                for (const kw of cellKws) {
                  const it = items[kw.item_index as number];
                  slideEntries.push({
                    itemIndex: kw.item_index as number,
                    label: it?.title ? `${(kw.item_index as number) + 1}. ${it.title}` : `셀 #${(kw.item_index as number) + 1}`,
                  });
                }
              } else if (slideImages[imageKey(slide.index, null)]) {
                slideEntries.push({ itemIndex: null, label: slide.headline || `슬라이드 ${slide.index}` });
              }
              if (slideEntries.length === 0) return null;

              // Body / subtext preview lets the user see step 1 context while
              // picking images. Two lines max so a long body doesn't push the
              // image grid off-screen — full text stays in step 1.
              const bodyPreview = (slide.body || slide.subtext || "").trim();
              // Reference slide thumbnail from the benchmark Instagram post —
              // gives the user a visual anchor for which cell they're picking
              // an image for. Without it cell labels like "1. 마루세이 버터샌드"
              // are abstract; with it the user sees the original slide layout
              // (e.g. "ah, that's the top-left product in slide 2").
              const refImg = refImages.find((r) => r.slide_index === slide.index);
              return (
                <div key={slide.index} style={{ paddingBottom: 16, borderBottom: "1px solid var(--border)" }}>
                  {/* Slide header */}
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: bodyPreview ? 6 : 12 }}>
                    {refImg?.url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={resolveImageUrl(refImg.url)}
                        alt={`벤치 슬라이드 ${slide.index + 1}`}
                        title="벤치마크 원본 슬라이드 — 어떤 위치의 셀인지 참고용"
                        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
                        style={{
                          width: 96, height: 96, objectFit: "cover",
                          borderRadius: 8, flexShrink: 0,
                          border: "1px solid var(--border)",
                        }}
                      />
                    )}
                    <span style={{
                      fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 4,
                      background: slide.type === "cover" ? "var(--accent-muted)" : "var(--bg-overlay)",
                      color: slide.type === "cover" ? "var(--accent-text)" : "var(--text-tertiary)",
                    }}>
                      {slide.type === "cover" ? "표지" : slide.type === "cta" ? "CTA" : `#${slide.index}`}
                    </span>
                    <span style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 500 }}>{slide.headline}</span>
                    {cellKws.length > 0 && (() => {
                      const filled = cellKws.filter((kw) => !!selectedImages[imageKey(kw.slide_index, kw.item_index)]?.url).length;
                      const complete = filled === cellKws.length;
                      return (
                        <span style={{
                          fontSize: 11,
                          fontWeight: 500,
                          padding: "1px 8px",
                          borderRadius: 10,
                          background: complete ? "rgba(100,200,150,0.18)" : "rgba(255,170,80,0.18)",
                          color: complete ? "rgb(160,230,190)" : "rgb(255,200,140)",
                        }}>
                          그리드 · {filled}/{cellKws.length} 선택
                        </span>
                      );
                    })()}
                  </div>
                  {bodyPreview && (
                    <p
                      title={bodyPreview}
                      style={{
                        fontSize: 12,
                        lineHeight: 1.5,
                        color: "var(--text-secondary)",
                        margin: "0 0 12px",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {bodyPreview}
                    </p>
                  )}

                  {/* One picker per cell (or one for the whole slide) */}
                  {slideEntries.map(({ itemIndex, label }) => {
                    const key = imageKey(slide.index, itemIndex);
                    const images = slideImages[key];
                    if (!images) return null;
                    const selected = selectedImages[key];
                    // Missing = picker has candidates but user hasn't picked one.
                    // Drawing a red outline makes unchecked cells obvious during
                    // a long picker list so the user doesn't accidentally skip any.
                    const missing = !selected?.url && images.length > 0;
                    return (
                      <div
                        key={key}
                        data-image-key={key}
                        style={{
                          marginBottom: 14,
                          padding: missing ? 8 : 0,
                          borderRadius: missing ? 6 : 0,
                          border: missing ? "2px solid #e85b5b" : "none",
                          background: missing ? "rgba(232,91,91,0.06)" : "transparent",
                          transition: "border-color 0.2s, background 0.2s",
                        }}
                      >
                        {cellKws.length > 0 && (() => {
                          // Show the cell's description right under the label so
                          // the user can pick an image with full text context
                          // (matches step 1's content card).
                          const cellDesc = itemIndex != null
                            ? ((slide.items?.[itemIndex]?.description || slide.items?.[itemIndex]?.subtitle) || "").trim()
                            : "";
                          return (
                          <div style={{ display: "flex", flexDirection: "column", gap: 2, marginBottom: 6 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            {/* Mini ref-slide thumb next to each cell label so
                                the user can map "1. 사보리노 모닝 마스크팩" back
                                to the physical slide it came from on the
                                benchmark feed at a glance. Without this the
                                cell label is just text and the user has to
                                scroll back up to the slide header thumbnail
                                to figure out the location. */}
                            {refImg?.url && (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={resolveImageUrl(refImg.url)}
                                alt=""
                                title={`벤치 슬라이드 ${slide.index + 1}`}
                                onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
                                style={{
                                  width: 48, height: 48, objectFit: "cover",
                                  borderRadius: 6, flexShrink: 0,
                                  border: "1px solid var(--border)",
                                }}
                              />
                            )}
                            <span style={{ fontSize: 12, fontWeight: 500, color: "var(--text-primary)" }}>{label}</span>
                            {refImg?.url && (
                              <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>
                                벤치 슬라이드 {slide.index + 1}{itemIndex != null ? ` · 항목 ${itemIndex + 1}` : ""}
                              </span>
                            )}
                            {missing && (
                              <span style={{ fontSize: 10, fontWeight: 600, padding: "1px 6px", borderRadius: 3, background: "rgba(232,91,91,0.18)", color: "#ff8a8a" }}>
                                선택 필요
                              </span>
                            )}
                            {selected && (
                              <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                                {!originalSrc[key] ? (
                                  <>
                                    <button onClick={() => cutoutSelected(key, "standard")} disabled={restyling.has(key)}
                                      title="배경만 제거 (빠름, 무료)"
                                      style={{ fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 4, background: "rgba(100,200,150,0.15)", color: "rgb(160,230,190)", border: "none", cursor: restyling.has(key) ? "default" : "pointer", opacity: restyling.has(key) ? 0.6 : 1 }}>
                                      {restyling.has(key) ? "처리 중…" : "✂️ 일반"}
                                    </button>
                                    <button onClick={() => cutoutSelected(key, "generative")} disabled={restyling.has(key)}
                                      title="손/사람까지 제거, 제품만 추출 (~4초, $0.003)"
                                      style={{ fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 4, background: "rgba(255,170,80,0.15)", color: "rgb(255,200,140)", border: "none", cursor: restyling.has(key) ? "default" : "pointer", opacity: restyling.has(key) ? 0.6 : 1 }}>
                                      {restyling.has(key) ? "처리 중…" : "🎯 생성"}
                                    </button>
                                    <button onClick={() => restyleSelected(key)} disabled={restyling.has(key)}
                                      style={{ fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 4, background: "rgba(120,100,255,0.15)", color: "rgb(180,165,255)", border: "none", cursor: restyling.has(key) ? "default" : "pointer", opacity: restyling.has(key) ? 0.6 : 1 }}>
                                      {restyling.has(key) ? "변환 중…" : "✨ 스타일"}
                                    </button>
                                  </>
                                ) : (
                                  <button onClick={() => revertRestyle(key)}
                                    style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border)", cursor: "pointer" }}>
                                    원본으로
                                  </button>
                                )}
                                <button onClick={() => selectImage(key, null)}
                                  style={{ fontSize: 11, color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                                  선택 해제
                                </button>
                              </div>
                            )}
                          </div>
                          {cellDesc && (
                            <p
                              title={cellDesc}
                              style={{
                                fontSize: 11,
                                lineHeight: 1.5,
                                color: "var(--text-tertiary)",
                                margin: 0,
                                paddingLeft: 2,
                                display: "-webkit-box",
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: "vertical",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                              }}
                            >
                              {cellDesc}
                            </p>
                          )}
                          </div>
                          );
                        })()}
                        {/* When single-slide picker, render the original toolbar */}
                        {cellKws.length === 0 && selected && (
                          <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                            {!originalSrc[key] ? (
                              <>
                                <button onClick={() => cutoutSelected(key, "standard")} disabled={restyling.has(key)}
                                  title="배경만 제거 (~5초, 무료)"
                                  style={{ fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 4, background: "rgba(100,200,150,0.15)", color: "rgb(160,230,190)", border: "none", cursor: restyling.has(key) ? "default" : "pointer", opacity: restyling.has(key) ? 0.6 : 1 }}>
                                  {restyling.has(key) ? "처리 중…" : "✂️ 일반 누끼"}
                                </button>
                                <button onClick={() => cutoutSelected(key, "generative")} disabled={restyling.has(key)}
                                  title="손/사람까지 제거, 제품만 추출 (~4초, $0.003)"
                                  style={{ fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 4, background: "rgba(255,170,80,0.15)", color: "rgb(255,200,140)", border: "none", cursor: restyling.has(key) ? "default" : "pointer", opacity: restyling.has(key) ? 0.6 : 1 }}>
                                  {restyling.has(key) ? "처리 중…" : "🎯 생성 누끼"}
                                </button>
                                <button onClick={() => restyleSelected(key)} disabled={restyling.has(key)}
                                  style={{ fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 4, background: "rgba(120,100,255,0.15)", color: "rgb(180,165,255)", border: "none", cursor: restyling.has(key) ? "default" : "pointer", opacity: restyling.has(key) ? 0.6 : 1 }}>
                                  {restyling.has(key) ? "변환 중…" : "✨ 스타일 변환"}
                                </button>
                              </>
                            ) : (
                              <button onClick={() => revertRestyle(key)}
                                style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border)", cursor: "pointer" }}>
                                원본으로 되돌리기
                              </button>
                            )}
                            <button onClick={() => selectImage(key, null)}
                              style={{ fontSize: 11, color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline" }}>
                              선택 해제
                            </button>
                          </div>
                        )}

                        {selected && originalSrc[key] && (
                          <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginBottom: 4 }}>BEFORE</div>
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img src={originalSrc[key]} alt="" style={{ width: "100%", aspectRatio: "1", objectFit: "cover", borderRadius: 6, opacity: 0.6 }} />
                            </div>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 10, color: "rgb(180,165,255)", marginBottom: 4, fontWeight: 600 }}>AFTER ✨</div>
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img src={selected.url} alt="" style={{ width: "100%", aspectRatio: "1", objectFit: "cover", borderRadius: 6, border: "2px solid rgba(120,100,255,0.4)" }} />
                            </div>
                          </div>
                        )}

                        {/* Re-search row — type a different keyword if the auto-results miss. */}
                        {(() => {
                          const [sidxStr, iidxStr] = key.includes(":") ? key.split(":") : [key, ""];
                          const sidx = Number(sidxStr);
                          const iidx = iidxStr === "" ? null : Number(iidxStr);
                          const kw = imageKeywords.find((k) =>
                            k.slide_index === sidx && (k.item_index ?? null) === iidx
                          );
                          const defaultQ = kw?.keywords?.[0] || "";
                          const liveQ = researchQuery[key] ?? defaultQ;
                          const busy = researching.has(key);
                          return (
                            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
                              <input
                                type="text"
                                value={liveQ}
                                disabled={busy}
                                onChange={(e) => setResearchQuery((p) => ({ ...p, [key]: e.target.value }))}
                                onKeyDown={(e) => { if (e.key === "Enter" && !busy) { e.preventDefault(); researchOne(key, liveQ); } }}
                                placeholder="다른 키워드로 검색"
                                style={{
                                  flex: 1, padding: "5px 10px", fontSize: 11,
                                  background: "var(--bg-overlay)", color: "var(--text-primary)",
                                  border: "1px solid var(--border)", borderRadius: 5, outline: "none",
                                }}
                              />
                              <button
                                onClick={() => researchOne(key, liveQ)}
                                disabled={busy || !liveQ.trim()}
                                style={{
                                  fontSize: 11, fontWeight: 500, padding: "5px 10px", borderRadius: 5,
                                  background: "var(--bg-elevated)", color: "var(--text-primary)",
                                  border: "1px solid var(--border)",
                                  cursor: busy || !liveQ.trim() ? "default" : "pointer",
                                  opacity: busy || !liveQ.trim() ? 0.5 : 1,
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {busy ? "검색 중…" : "🔄 재검색"}
                              </button>
                            </div>
                          );
                        })()}

                        {images.length === 0 ? (
                          <p style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "8px 0" }}>검색 결과가 없습니다</p>
                        ) : (
                          <>
                            <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 6 }}>
                              {images.length}개 후보 — 클릭해서 선택
                            </p>
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
                              {images.map((img) => {
                                const isSelected = selected?.id === img.id;
                                return (
                                  <div key={img.id} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                    <div onClick={() => selectImage(key, isSelected ? null : img)}
                                      style={{ position: "relative", aspectRatio: "1", borderRadius: 6, overflow: "hidden", cursor: "pointer", border: isSelected ? "2px solid var(--accent)" : "2px solid transparent", opacity: selected && !isSelected ? 0.4 : 1, transition: "all 0.15s" }}>
                                      {/* eslint-disable-next-line @next/next/no-img-element */}
                                      <img src={img.preview_url || img.url} alt="" loading="lazy"
                                        style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                                        onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
                                      {img._query && (
                                        <span style={{ position: "absolute", bottom: 4, left: 4, fontSize: 9, fontWeight: 500, padding: "1px 6px", borderRadius: 3, background: "rgba(0,0,0,0.7)", color: "white", maxWidth: "calc(100% - 8px)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={img._query}>
                                          {img._query}
                                        </span>
                                      )}
                                      {isSelected && (
                                        <div style={{ position: "absolute", top: 4, right: 4, width: 18, height: 18, borderRadius: 9, background: "var(--accent)", color: "white", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>✓</div>
                                      )}
                                    </div>
                                    <button
                                      type="button"
                                      onClick={(e) => { e.stopPropagation(); setPreviewImageUrl(img.url || img.preview_url); }}
                                      style={{
                                        padding: "3px 6px",
                                        fontSize: 10,
                                        color: "var(--text-secondary)",
                                        background: "var(--bg-overlay)",
                                        border: "1px solid var(--border)",
                                        borderRadius: 4,
                                        cursor: "pointer",
                                        width: "100%",
                                      }}
                                      title="원본 크기로 보기"
                                    >
                                      🔍 원본보기
                                    </button>
                                  </div>
                                );
                              })}
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => setStep(1)}
              style={{ padding: "10px 20px", fontSize: 13, color: "var(--text-secondary)", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer" }}>
              이전
            </button>
            <button onClick={handleSave} disabled={saving || !selectedTemplateId}
              style={{ flex: 1, padding: "10px 20px", fontSize: 13, fontWeight: 600, color: "white", background: "var(--accent)", border: "none", borderRadius: 8, cursor: saving || !selectedTemplateId ? "default" : "pointer", opacity: saving || !selectedTemplateId ? 0.5 : 1 }}>
              {saving ? "템플릿 적용 중..." : "캐러셀 저장"}
            </button>
          </div>
        </div>
      )}

      {/* Per-account paraphrase-prompt editor.
          Empty textarea = use the system default; otherwise the user's text
          becomes the entire prompt body sent to the LLM. */}
      {paraphrasePromptModalOpen && (
        <div
          onClick={() => setParaphrasePromptModalOpen(false)}
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
            zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(900px, 100%)", maxHeight: "90vh",
              background: "var(--bg-base)", border: "1px solid var(--border)",
              borderRadius: 10, padding: 20, display: "flex", flexDirection: "column", gap: 12,
              overflow: "hidden",
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
              <h2 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>병렬 치환 프롬프트 설정</h2>
              <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>본인 계정에만 적용</span>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0, lineHeight: 1.6 }}>
              🔄 병렬 치환 버튼이 LLM에 보내는 본문을 직접 작성합니다. 입력 텍스트와 JSON 출력 형식은 서버가 자동으로 추가하니, 원칙·예시·금지 규칙만 자유롭게 적으세요. 비워두면 시스템 기본값을 사용합니다.
            </p>
            <textarea
              data-testid="paraphrase-prompt-textarea"
              value={paraphrasePrompt}
              onChange={(e) => setParaphrasePrompt(e.target.value)}
              placeholder={paraphrasePromptDefault || "프롬프트를 불러오는 중…"}
              spellCheck={false}
              style={{
                flex: 1, minHeight: 320, maxHeight: "60vh",
                padding: 12, fontFamily: "ui-monospace, monospace", fontSize: 12, lineHeight: 1.5,
                background: "var(--bg-overlay)", color: "var(--text-primary)",
                border: "1px solid var(--border)", borderRadius: 6, outline: "none", resize: "vertical",
              }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--text-tertiary)" }}>
              {paraphrasePrompt.trim() ? (
                <span>현재: <b style={{ color: "rgb(180,165,255)" }}>본인 설정 사용</b> ({paraphrasePrompt.trim().length.toLocaleString()}자)</span>
              ) : (
                <span>현재: <b style={{ color: "var(--text-secondary)" }}>시스템 기본값 사용</b></span>
              )}
              <span style={{ flex: 1 }} />
              <button
                type="button"
                onClick={() => setParaphrasePrompt(paraphrasePromptDefault || "")}
                disabled={!paraphrasePromptDefault}
                style={{
                  padding: "5px 10px", fontSize: 11,
                  background: "var(--bg-overlay)", color: "var(--text-secondary)",
                  border: "1px solid var(--border)", borderRadius: 5,
                  cursor: paraphrasePromptDefault ? "pointer" : "not-allowed", opacity: paraphrasePromptDefault ? 1 : 0.5,
                }}
              >
                기본값 불러오기
              </button>
              <button
                type="button"
                onClick={() => setParaphrasePrompt("")}
                style={{
                  padding: "5px 10px", fontSize: 11,
                  background: "var(--bg-overlay)", color: "var(--text-secondary)",
                  border: "1px solid var(--border)", borderRadius: 5, cursor: "pointer",
                }}
              >
                비우기 (기본값 사용)
              </button>
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                type="button"
                onClick={() => setParaphrasePromptModalOpen(false)}
                style={{ padding: "8px 14px", fontSize: 12, background: "var(--bg-overlay)", color: "var(--text-secondary)", border: "1px solid var(--border)", borderRadius: 6, cursor: "pointer" }}
              >
                취소
              </button>
              <button
                type="button"
                onClick={saveParaphrasePrompt}
                disabled={paraphrasePromptSaving}
                style={{
                  padding: "8px 18px", fontSize: 12, fontWeight: 600,
                  color: "white", background: "var(--accent)",
                  border: "none", borderRadius: 6,
                  cursor: paraphrasePromptSaving ? "default" : "pointer", opacity: paraphrasePromptSaving ? 0.5 : 1,
                }}
              >
                {paraphrasePromptSaving ? "저장 중…" : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Full-size image preview overlay — click anywhere to dismiss */}
      {previewImageUrl && (
        <div
          onClick={() => setPreviewImageUrl(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.88)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 32,
            cursor: "zoom-out",
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={previewImageUrl}
            alt=""
            style={{
              maxWidth: "100%",
              maxHeight: "100%",
              objectFit: "contain",
              borderRadius: 8,
              boxShadow: "0 12px 40px rgba(0,0,0,0.6)",
              pointerEvents: "none",
            }}
          />
        </div>
      )}

      {/* Step 3: 완성 */}
      {step === 3 && (
        <div style={{ textAlign: "center", paddingTop: 60 }}>
          <div style={{ width: 48, height: 48, borderRadius: 12, background: "var(--green-muted)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
            <svg width="24" height="24" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="var(--green)">
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", margin: "0 0 8px" }}>캐러셀이 생성되었습니다</h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 28 }}>에디터에서 세부 편집을 할 수 있습니다</p>
          <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
            <a href={`/editor/${savedId}`}
              style={{ padding: "10px 24px", fontSize: 13, fontWeight: 600, color: "white", background: "var(--accent)", borderRadius: 8, textDecoration: "none" }}>
              에디터에서 열기
            </a>
            <button onClick={() => { setStep(0); setTopic(""); setSlides([]); setSelectedImages({}); setSavedId(null); setRefPosts([]); }}
              style={{ padding: "10px 20px", fontSize: 13, color: "var(--text-secondary)", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, cursor: "pointer" }}>
              새로 만들기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
