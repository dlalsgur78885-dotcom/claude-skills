export interface User {
  id: number;
  username: string;
  role: "admin" | "worker";
  created_at: string;
}

export interface Category {
  id: number;
  name: string;
  sort_order: number;
  created_at: string;
}

export interface Channel {
  id: number;
  instagram_handle: string;
  display_name: string;
  category: string;
  style_tags: string[];
  last_scraped_at: string | null;
  is_active: boolean;
  created_at: string;
  brand_primary_color: string | null;
  brand_logo_path: string | null;
  default_template_id: number | null;
}

export interface TemplateSummary {
  id: number;
  slug: string;
  name: string;
  user_id: number | null;
  channel_id: number | null;
  created_by: string;
  source_post_url: string | null;
  source_slides?: string[];
  layouts: string[];
  share_code?: string | null;
  is_public?: boolean;
  created_at: string | null;
}

export interface PostImage {
  id: number;
  slide_index: number;
  raw_path: string;
  /** Original Instagram CDN URL — survives the 3-hour cleanup that wipes
   *  locally-cached files. Use as a fallback when raw_path returns 404. */
  source_url?: string;
  processed_path: string;
  width: number;
  height: number;
}

export interface Post {
  id: number;
  channel_id: number;
  instagram_post_id: string;
  post_url: string;
  caption: string;
  hashtags: string[];
  post_date: string | null;
  like_count: number;
  comment_count: number;
  slide_count: number;
  collected_at: string;
  saved_at: string | null;
  images: PostImage[];
}

export interface ElementImage {
  id: number;
  source_url: string;
  local_path: string;
  thumbnail_url: string;
  width: number;
  height: number;
  rank: number;
  source: string;
  quality_score: number;
  url: string;
}

export interface ExtractedElement {
  id: number;
  post_id: number;
  name: string;
  search_query: string;
  source_text: string;
  selected: boolean;
  created_at: string;
  images: ElementImage[];
}

export interface ElementEditItem {
  id?: number;
  name: string;
  search_query: string;
  selected: boolean;
}

export interface PostUsageJob {
  id: number;
  post_id: number;
  status: "pending" | "running" | "awaiting_review" | "done" | "failed";
  stage: string;
  error: string;
  slide_texts: string[];
  started_at: string;
  finished_at: string | null;
}

export interface PostElements {
  job: PostUsageJob | null;
  elements: ExtractedElement[];
}

export interface Carousel {
  id: number;
  user_id: number;
  source_post_id: number | null;
  // Instagram URL of the benchmark post this carousel was generated from.
  // Backend populates this from the source_post_id FK on demand (see
  // _hydrate_source_url). Null when the carousel was created from scratch.
  source_post_url?: string | null;
  title: string;
  canvas_data: Record<string, unknown>;
  template_id: string;
  status: "draft" | "editing" | "finalized";
  created_at: string;
  updated_at: string;
}

export interface CarouselListItem {
  id: number;
  user_id: number;
  source_post_id: number | null;
  title: string;
  template_id: string;
  status: "draft" | "editing" | "finalized";
  created_at: string;
  updated_at: string;
  slide_count: number;
  thumbnail_url: string | null;
}

export interface SlideData {
  version: string;
  width: number;
  height: number;
  background: string;
  objects: FabricObject[];
}

export interface FabricObject {
  type: string;
  left: number;
  top: number;
  width?: number;
  height?: number;
  text?: string;
  fontSize?: number;
  fontFamily?: string;
  fontWeight?: string;
  fill?: string;
  textAlign?: string;
  lineHeight?: number;
  src?: string;
  opacity?: number;
  [key: string]: unknown;
}
