const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const API_ORIGIN = API_BASE.replace(/\/api\/?$/, "");

export interface LayoutHint {
  slide_index: number;
  kind: "single" | "grid";
  rows?: number;
  cols?: number;
}

/** Resolve a URL that may be a full http URL, a relative /api path, or a raw string. */
export function resolveImageUrl(url: string): string {
  if (!url) return "";
  if (url.startsWith("http")) return url;
  if (url.startsWith("/")) return `${API_ORIGIN}${url}`;
  return url;
}

/** Route an external image URL through the backend proxy so canvas exports stay CORS-clean.
 *  Same-origin / relative URLs are returned unchanged. */
export function proxiedImageUrl(url: string): string {
  if (!url) return "";
  if (!url.startsWith("http")) return url;
  // Already pointing at our own backend? Leave alone. Two checks because in
  // production NEXT_PUBLIC_API_URL is relative "/api", making API_ORIGIN
  // empty — the startsWith guard never fires. Match the proxy path instead,
  // so a previously-wrapped URL (which fabric.toJSON emits as an absolute
  // URL on subsequent mounts) doesn't get double-wrapped and 404 the image.
  if (API_ORIGIN && url.startsWith(API_ORIGIN)) return url;
  if (url.includes("/api/images/proxy?")) return url;
  return `${API_BASE}/images/proxy?url=${encodeURIComponent(url)}`;
}

class ApiClient {
  private token: string | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      this.token = localStorage.getItem("token");
    }
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem("token", token);
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("token");
    }
  }

  private async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    if (res.status === 401 && typeof window !== "undefined") {
      // Token expired / invalid — clear and bounce to login.
      // Skip the redirect for the /auth/login call itself (so wrong-password
      // errors surface to the form instead of looping).
      this.clearToken();
      if (!path.startsWith("/auth/login")) {
        const here = window.location.pathname + window.location.search;
        if (!window.location.pathname.startsWith("/login")) {
          window.location.href = "/login?next=" + encodeURIComponent(here);
        }
      }
    }

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(error.detail || "API 요청 실패");
    }

    if (res.status === 204) return undefined as T;
    return res.json();
  }

  // Auth
  async signup(username: string, password: string) {
    return this.fetch("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  }

  async login(username: string, password: string) {
    const data = await this.fetch<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getMe() {
    return this.fetch<import("./types").User>("/auth/me");
  }

  // Channels
  async getChannels() {
    return this.fetch<import("./types").Channel[]>("/channels/");
  }

  async createChannel(data: {
    instagram_handle: string;
    display_name?: string;
    category?: string;
    style_tags?: string[];
  }) {
    return this.fetch<import("./types").Channel>("/channels/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateChannel(id: number, data: Record<string, unknown>) {
    return this.fetch(`/channels/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async deleteChannel(id: number) {
    return this.fetch(`/channels/${id}`, { method: "DELETE" });
  }

  async bulkDeleteChannels(ids: number[]) {
    return this.fetch<{ deleted: number }>("/channels/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    });
  }

  async listChannelTemplates(channelId: number) {
    return this.fetch<{
      channel_id: number;
      default_template_id: number | null;
      templates: import("./types").TemplateSummary[];
    }>(`/channels/${channelId}/templates`);
  }

  async createChannelTemplate(channelId: number, data: { post_url: string; template_name: string; layout_hints?: LayoutHint[] }) {
    return this.fetch<import("./types").TemplateSummary>(`/channels/${channelId}/templates`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async uploadChannelLogo(channelId: number, file: File): Promise<{ brand_logo_path: string }> {
    const fd = new FormData();
    fd.append("file", file);
    const headers: Record<string, string> = {};
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    // FormData: do NOT set Content-Type — let browser fill multipart boundary
    const res = await fetch(`${API_BASE}/channels/${channelId}/logo`, {
      method: "POST",
      headers,
      body: fd,
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(e.detail || "로고 업로드 실패");
    }
    return res.json();
  }

  // Posts
  async getPosts(
    channelId?: number,
    limit = 20,
    offset = 0,
    filters?: { minLikes?: number; maxLikes?: number; minComments?: number; maxComments?: number; minSlides?: number; maxSlides?: number; dateFrom?: string; dateTo?: string; q?: string },
  ) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (channelId) params.set("channel_id", String(channelId));
    if (filters?.minLikes != null) params.set("min_likes", String(filters.minLikes));
    if (filters?.maxLikes != null) params.set("max_likes", String(filters.maxLikes));
    if (filters?.minComments != null) params.set("min_comments", String(filters.minComments));
    if (filters?.maxComments != null) params.set("max_comments", String(filters.maxComments));
    if (filters?.minSlides != null) params.set("min_slides", String(filters.minSlides));
    if (filters?.maxSlides != null) params.set("max_slides", String(filters.maxSlides));
    if (filters?.dateFrom) params.set("date_from", filters.dateFrom);
    if (filters?.dateTo) params.set("date_to", filters.dateTo);
    if (filters?.q) params.set("q", filters.q);
    return this.fetch<import("./types").Post[]>(`/posts/?${params}`);
  }

  async getPost(id: number) {
    return this.fetch<import("./types").Post>(`/posts/${id}`);
  }

  async deletePost(id: number) {
    return this.fetch(`/posts/${id}`, { method: "DELETE" });
  }

  async getSavedPosts(limit = 50, offset = 0) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return this.fetch<import("./types").Post[]>(`/posts/saved?${params}`);
  }

  async savePost(id: number) {
    return this.fetch<import("./types").Post>(`/posts/${id}/save`, { method: "POST" });
  }

  async unsavePost(id: number) {
    return this.fetch(`/posts/${id}/save`, { method: "DELETE" });
  }

  async ingestPost(post_url: string, username: string) {
    return this.fetch<import("./types").Post>("/posts/ingest", {
      method: "POST",
      body: JSON.stringify({ post_url, username }),
    });
  }

  // Post usage / element pipeline
  async triggerUsePost(id: number) {
    return this.fetch<import("./types").PostUsageJob>(`/posts/${id}/use`, { method: "POST" });
  }

  async getUseStatus(id: number) {
    return this.fetch<import("./types").PostUsageJob>(`/posts/${id}/use`);
  }

  async getPostElements(id: number, sort: "rank" | "quality" = "quality") {
    return this.fetch<import("./types").PostElements>(`/posts/${id}/elements?sort=${sort}`);
  }

  async editElements(id: number, elements: import("./types").ElementEditItem[]) {
    return this.fetch<{ post_id: number; updated: number; inserted: number; deleted: number }>(
      `/posts/${id}/elements`,
      { method: "PUT", body: JSON.stringify({ elements }) },
    );
  }

  async triggerCollect(id: number) {
    return this.fetch<import("./types").PostUsageJob>(
      `/posts/${id}/elements/collect`,
      { method: "POST" },
    );
  }

  // Carousels
  async getCarousels(limit = 20, offset = 0, status?: "draft" | "editing" | "finalized") {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (status) params.set("status", status);
    return this.fetch<import("./types").Carousel[]>(`/carousels/?${params}`);
  }

  async createCarousel(data: Record<string, unknown>) {
    return this.fetch<import("./types").Carousel>("/carousels/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getCarousel(id: number) {
    return this.fetch<import("./types").Carousel>(`/carousels/${id}`);
  }

  async updateCarousel(id: number, data: Record<string, unknown>) {
    return this.fetch<import("./types").Carousel>(`/carousels/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async deleteCarousel(id: number) {
    return this.fetch(`/carousels/${id}`, { method: "DELETE" });
  }

  async cloneCarousel(id: number) {
    return this.fetch<import("./types").Carousel>(`/carousels/${id}/clone`, {
      method: "POST",
    });
  }

  // Content generation
  async generateContent(topic: string, tone = "professional", slideCount = 8) {
    return this.fetch<{
      topic: string;
      slides: { index: number; type: string; headline: string; body?: string; subtext?: string; cta_text?: string }[];
      caption: string;
      hashtags: string[];
      image_keywords: { slide_index: number; keywords: string[]; style: string }[];
    }>("/carousels/generate-content", {
      method: "POST",
      body: JSON.stringify({ topic, tone, slide_count: slideCount }),
    });
  }

  // Categories
  async getCategories() {
    return this.fetch<import("./types").Category[]>("/categories/");
  }

  async createCategory(data: { name: string; sort_order?: number }) {
    return this.fetch<import("./types").Category>("/categories/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateCategory(id: number, data: { name?: string; sort_order?: number }) {
    return this.fetch<import("./types").Category>(`/categories/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async deleteCategory(id: number) {
    return this.fetch(`/categories/${id}`, { method: "DELETE" });
  }

  // Users (admin)
  async getUsers() {
    return this.fetch<import("./types").User[]>("/users/");
  }

  async createUser(data: { username: string; password: string; role?: string }) {
    return this.fetch<import("./types").User>("/users/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateUserRole(id: number, role: string) {
    return this.fetch<import("./types").User>(`/users/${id}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
  }

  async deleteUser(id: number) {
    return this.fetch(`/users/${id}`, { method: "DELETE" });
  }

  // App settings (admin only)
  async getSettings() {
    return this.fetch<{
      settings: Record<string, { value: string; source: "db" | "env" | "missing"; preview: string }>;
      editable_keys: string[];
    }>("/settings/");
  }

  async updateSettings(values: Record<string, string>) {
    return this.fetch<{
      settings: Record<string, { value: string; source: "db" | "env" | "missing"; preview: string }>;
    }>("/settings/", {
      method: "PUT",
      body: JSON.stringify({ values }),
    });
  }

  // Image Search
  async searchImages(query: string, style: "photo" | "icon" | "cutout" = "photo", limit = 12, country?: string) {
    const params = new URLSearchParams({ q: query, style, limit: String(limit) });
    if (country) params.set("country", country);
    return this.fetch<{ query: string; style: string; total: number; images: { id: string; url: string; preview_url: string; width: number; height: number; source: string }[] }>(`/images/search?${params}`);
  }

  async restyleImage(data: {
    source_url: string;
    user_prompt?: string;
    brand_color?: string | null;
    brand_mood?: string;
    model?: string;
  }) {
    return this.fetch<{ url: string }>("/images/restyle", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async cutoutImage(data: { source_url: string; mode?: "standard" | "generative"; model?: string }) {
    return this.fetch<{ url: string }>("/images/cutout", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async enhanceImage(data: { source_url: string; category: "food" | "landscape" | "portrait" }) {
    return this.fetch<{ url: string }>("/images/enhance", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Per-account override for the rewrite ("치환") prompts. Three kinds — 제목 /
  // 속지 / 캡션 — each separately overridable. Empty string clears that kind's
  // override so the system default is used again (feedback #11-13).
  async getParaphrasePrompt() {
    return this.fetch<{
      body: { prompt: string; default_prompt: string };
      title: { prompt: string; default_prompt: string };
      caption: { prompt: string; default_prompt: string };
    }>("/users/me/paraphrase-prompt");
  }

  async setParaphrasePrompt(kind: "body" | "title" | "caption", prompt: string) {
    return this.fetch<{ kind: string; prompt: string }>("/users/me/paraphrase-prompt", {
      method: "PUT",
      body: JSON.stringify({ kind, prompt }),
    });
  }

  async paraphrase(
    texts: string[],
    kind: "body" | "title" = "body",
    tone: "marketing" | "casual" | "punchy" = "marketing",
  ) {
    return this.fetch<{ paraphrased: string[] }>("/carousels/paraphrase", {
      method: "POST",
      body: JSON.stringify({ texts, tone, kind }),
    });
  }

  async translateKeyword(query: string, context = "") {
    return this.fetch<{ kind: "place" | "general"; queries: string[]; country: string }>("/carousels/translate-keyword", {
      method: "POST",
      body: JSON.stringify({ query, context }),
    });
  }

  async paraphraseCaption(caption: string, topic = "") {
    return this.fetch<{ paraphrased: string; hook: string; body: string }>("/carousels/paraphrase-caption", {
      method: "POST",
      body: JSON.stringify({ caption, topic }),
    });
  }

  // Scrape
  async triggerScrape() {
    return this.fetch<{ status: string; message: string }>("/scrape/run", { method: "POST" });
  }

  async scrapeChannel(handle: string) {
    return this.fetch<{ status: string; message: string }>(`/scrape/channel/${handle}`, { method: "POST" });
  }

  async scrapeStatus() {
    return this.fetch<{ running: boolean; scheduled_jobs: { id: string; name: string; next_run: string }[] }>("/scrape/status");
  }

  async renderCarousel(data: {
    template_id: number;
    slides: Array<Record<string, unknown>>;
    brand_color?: string | null;
    brand_logo_path?: string | null;
    user_image_urls?: Record<number, string>;
    user_item_image_urls?: Record<number, Record<number, string>>;
    layout_overrides?: Record<number, string>;
  }) {
    return this.fetch<{
      canvas_slides: Array<Record<string, unknown>>;
      template_id: number;
      template_slug: string;
    }>("/carousels/render", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // Templates (Template Studio)
  async listTemplates() {
    return this.fetch<{ templates: import("./types").TemplateSummary[] }>("/templates/");
  }

  async previewSlides(postUrl: string) {
    return this.fetch<{ slide_urls: string[] }>("/templates/preview-slides", {
      method: "POST",
      body: JSON.stringify({ post_url: postUrl }),
    });
  }

  async generateTemplate(data: { post_url: string; template_name: string; channel_id?: number; layout_hints?: LayoutHint[] }) {
    return this.fetch<import("./types").TemplateSummary>("/templates/generate", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async shareTemplate(id: number) {
    return this.fetch<{ share_code: string; share_url: string; is_public: boolean }>(`/templates/${id}/share`, {
      method: "POST",
    });
  }

  async unshareTemplate(id: number) {
    return this.fetch<unknown>(`/templates/${id}/share`, { method: "DELETE" });
  }

  async getTemplateByShareCode(code: string) {
    return this.fetch<{
      id: number;
      slug: string;
      name: string;
      layouts: Record<string, unknown>;
      share_code: string;
      created_by: string;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      [k: string]: any;
    }>(`/templates/by-share/${encodeURIComponent(code)}`);
  }

  async cloneTemplateByShareCode(code: string) {
    return this.fetch<import("./types").TemplateSummary>(`/templates/by-share/${encodeURIComponent(code)}/clone`, {
      method: "POST",
    });
  }

  async getTemplate(id: number) {
    return this.fetch<{
      id: number;
      slug: string;
      name: string;
      channel_id: number | null;
      user_id: number | null;
      canvas: Record<string, unknown>;
      brand: Record<string, unknown>;
      layouts: Record<string, unknown>;
      source_post_url: string | null;
      created_by: string;
      created_at: string | null;
    }>(`/templates/${id}`);
  }

  async updateTemplate(
    id: number,
    data: {
      name?: string;
      canvas?: Record<string, unknown>;
      brand?: Record<string, unknown>;
      layouts?: Record<string, unknown>;
    }
  ) {
    return this.fetch(`/templates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async cloneTemplate(id: number) {
    return this.fetch<import("./types").TemplateSummary>(`/templates/${id}/clone`, {
      method: "POST",
    });
  }

  async copyLayoutToTemplate(
    dstTemplateId: number,
    srcTemplateId: number,
    srcLayoutName: string,
  ) {
    return this.fetch<{ layout_name: string; template: unknown }>(
      `/templates/${dstTemplateId}/layouts/copy-from`,
      {
        method: "POST",
        body: JSON.stringify({ src_template_id: srcTemplateId, src_layout_name: srcLayoutName }),
      },
    );
  }

  async deleteTemplate(id: number) {
    return this.fetch(`/templates/${id}`, { method: "DELETE" });
  }

  async uploadTemplateAsset(file: File): Promise<{ path: string }> {
    const fd = new FormData();
    fd.append("file", file);
    const headers: Record<string, string> = {};
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    // FormData: do NOT set Content-Type — let the browser fill the multipart boundary
    const res = await fetch(`${API_BASE}/templates/upload-asset`, {
      method: "POST",
      headers,
      body: fd,
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(e.detail || "에셋 업로드 실패");
    }
    return res.json();
  }

  // CTA image — reusable call-to-action PNG dropped onto a fresh last slide.
  async getCtaImage(): Promise<{ url: string | null }> {
    return this.fetch("/cta");
  }

  async uploadCtaImage(file: File): Promise<{ url: string }> {
    const fd = new FormData();
    fd.append("file", file);
    const headers: Record<string, string> = {};
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    // FormData: do NOT set Content-Type — let the browser fill the multipart boundary
    const res = await fetch(`${API_BASE}/cta/upload`, {
      method: "POST",
      headers,
      body: fd,
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(e.detail || "CTA 이미지 업로드 실패");
    }
    return res.json();
  }

  // User fonts — uploaded font files the editor registers as FontFaces.
  async getFonts(): Promise<{ fonts: { family: string; filename: string; url: string }[] }> {
    return this.fetch("/fonts");
  }

  async uploadFont(file: File): Promise<{ family: string; filename: string; url: string }> {
    const fd = new FormData();
    fd.append("file", file);
    const headers: Record<string, string> = {};
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    // FormData: do NOT set Content-Type — let the browser fill the multipart boundary
    const res = await fetch(`${API_BASE}/fonts/upload`, {
      method: "POST",
      headers,
      body: fd,
    });
    if (!res.ok) {
      const e = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(e.detail || "폰트 업로드 실패");
    }
    return res.json();
  }

  async deleteFont(filename: string): Promise<{ ok: boolean }> {
    return this.fetch(`/fonts/${encodeURIComponent(filename)}`, { method: "DELETE" });
  }

  // Orchestrator
  async orchestrate(request: string, context: Record<string, unknown> = {}) {
    return this.fetch("/carousels/orchestrate", {
      method: "POST",
      body: JSON.stringify({ request, context }),
    });
  }
}

export const api = new ApiClient();
