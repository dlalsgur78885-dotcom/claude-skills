// Image-search query plan + assembly — carousel studio feedback #15-16.
//
// The backend (`/translate-keyword`) classifies a keyword and returns the
// structured `ItemQueryPlan` below. This module is the deterministic code
// that turns that plan + user-toggleable overrides into the actual search
// query strings. Same axes everywhere:
//
//   query = [region_anchor] + [name form] + [image-type modifier]
//
// — name form is per language (ko + native + en, sparse)
// — region anchor is the city/area at the same language as the form
// — modifier is one of seven fixed image types, mapped per language
// — natural ordering: ko/ja/zh prefix anchor, en suffix anchor
//
// LLM picks the structural fields (forms / region_anchor / desired_image_types).
// This file produces every search string.

export type Lang = "ko" | "ja" | "zh" | "en";

export type ImageType =
  | "food" | "exterior" | "interior" | "landmark" | "scene" | "ambiance" | "product";

export type LangMap = Partial<Record<Lang, string>>;

export interface ItemQueryPlan {
  forms: LangMap;
  region_anchor: LangMap;          // empty for non-place items
  desired_image_types: ImageType[]; // default selection in the UI
  excludes?: string[];              // discount hints (used later in result scoring)
  category?: string;
  country?: string;
  kind?: "place" | "general";
}

export interface QueryEntry {
  q: string;                 // the actual search string
  lang: Lang;
  image_type: ImageType | "bare";
  priority: number;          // smaller = higher priority
}

// Generic modifier vocabulary per language. Keep small + curated; users can
// add their own words via the cell's "+추가" input (those bypass this table).
export const MODIFIER_WORDS: Record<ImageType | "bare", Record<Lang, string>> = {
  food:     { ko: "음식",    ja: "料理",         zh: "美食",  en: "food" },
  exterior: { ko: "외관",    ja: "外観",         zh: "外观",  en: "storefront" },
  interior: { ko: "내부",    ja: "店内",         zh: "内部",  en: "interior" },
  landmark: { ko: "전경",    ja: "名所",         zh: "地标",  en: "landmark" },
  scene:    { ko: "풍경",    ja: "風景",         zh: "风景",  en: "scene" },
  ambiance: { ko: "분위기",  ja: "雰囲気",       zh: "氛围",  en: "ambiance" },
  product:  { ko: "제품",    ja: "製品",         zh: "产品",  en: "product" },
  bare:     { ko: "",        ja: "",             zh: "",      en: "" },
};

export const ALL_IMAGE_TYPES: ImageType[] = [
  "food", "exterior", "interior", "landmark", "scene", "ambiance", "product",
];

// Human-facing labels (Korean) for the modifier chips. Keys match ImageType.
export const MODIFIER_LABEL_KO: Record<ImageType, string> = {
  food: "음식",
  exterior: "외관",
  interior: "내부",
  landmark: "전경",
  scene: "풍경",
  ambiance: "분위기",
  product: "제품",
};

// Order in which langs go into the result list. Native scripts first (they
// catch local web best), Korean last as Naver fallback.
const LANG_ORDER: Lang[] = ["ja", "zh", "en", "ko"];

/** Build one query string by joining anchor + form + modifier in the natural
 *  word order for that language. Anchor is skipped if the form already
 *  contains it (case-insensitive) so we don't get `東京 東京 スカイツリー`. */
function assemble(form: string, modifier: string, anchor: string, lang: Lang): string {
  let useAnchor = anchor;
  if (anchor && form.toLowerCase().includes(anchor.toLowerCase())) {
    useAnchor = "";
  }
  const parts =
    lang === "en"
      ? [form, modifier, useAnchor]     // English: anchor at the tail (`Kiyosumi-Shirakawa scene Tokyo`)
      : [useAnchor, form, modifier];    // ko/ja/zh: anchor up front (`東京 清澄白河 風景`)
  return parts.map((p) => (p || "").trim()).filter(Boolean).join(" ");
}

export interface BuildOptions {
  /** User-selected modifiers; falls back to plan.desired_image_types. */
  modifiers?: ImageType[];
  /** Off = drop the region anchor on every query. Default on. */
  regionAnchorEnabled?: boolean;
  /** Free-form modifier strings the user typed in the "+추가" field. Each is
   *  appended as-is to every form (no per-language translation). */
  customModifiers?: string[];
}

/** Build the full ordered list of search queries for an item.
 *
 *  Priority sort: `(modifier_rank, lang_rank)` — same modifier sweeps every
 *  language before moving to the next modifier; bare goes last. */
export function buildQueries(plan: ItemQueryPlan, opts: BuildOptions = {}): QueryEntry[] {
  const forms = plan.forms || {};
  const anchors = plan.region_anchor || {};
  const modifiers = (opts.modifiers && opts.modifiers.length
    ? opts.modifiers
    : (plan.desired_image_types || [])
  ).filter((m) => MODIFIER_WORDS[m]);
  const regionOn = opts.regionAnchorEnabled !== false; // default true
  const customs = (opts.customModifiers || []).map((s) => s.trim()).filter(Boolean);

  // For each lang present in forms, generate one query per modifier + bare.
  const out: QueryEntry[] = [];
  const langs = (Object.keys(forms) as Lang[]).filter((l) => (forms[l] || "").trim());

  for (const mod of modifiers) {
    for (const lang of LANG_ORDER) {
      if (!langs.includes(lang)) continue;
      const form = forms[lang] as string;
      const anchor = regionOn ? (anchors[lang] || "") : "";
      const word = MODIFIER_WORDS[mod][lang];
      const q = assemble(form, word, anchor, lang);
      if (q) {
        out.push({
          q, lang, image_type: mod,
          priority: out.length, // sequential = stable sort by insertion
        });
      }
    }
  }

  // Custom modifiers: append the user-entered string as-is to each form, in
  // every language. Detect language is hard; appending as-is is good enough.
  for (const custom of customs) {
    for (const lang of LANG_ORDER) {
      if (!langs.includes(lang)) continue;
      const form = forms[lang] as string;
      const anchor = regionOn ? (anchors[lang] || "") : "";
      const q = assemble(form, custom, anchor, lang);
      if (q) {
        out.push({ q, lang, image_type: "bare", priority: out.length });
      }
    }
  }

  // Bare fallback (form + anchor, no modifier) — last.
  for (const lang of LANG_ORDER) {
    if (!langs.includes(lang)) continue;
    const form = forms[lang] as string;
    const anchor = regionOn ? (anchors[lang] || "") : "";
    const q = assemble(form, "", anchor, lang);
    if (q) {
      out.push({ q, lang, image_type: "bare", priority: out.length });
    }
  }

  // Dedupe (case-insensitive, preserve first occurrence).
  const seen = new Set<string>();
  const deduped: QueryEntry[] = [];
  for (const e of out) {
    const k = e.q.toLowerCase();
    if (!seen.has(k)) {
      seen.add(k);
      deduped.push(e);
    }
  }
  return deduped;
}

/** Best-effort plan from a legacy `image_keywords[]` entry that only has
 *  flat `keywords[]` + `country`. Used while the real plan is still loading. */
export function planFromLegacy(keywords: string[], country?: string): ItemQueryPlan {
  // We don't know which keyword is which language without LLM help, so park
  // them all into ko and let buildQueries treat them as single-lang strings.
  return {
    forms: keywords[0] ? { ko: keywords[0] } : {},
    region_anchor: {},
    desired_image_types: [],
    country: country || "kr",
  };
}
