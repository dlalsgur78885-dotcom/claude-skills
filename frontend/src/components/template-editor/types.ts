/** Shape mirrors backend's template_spec.py — kept loose for editor flexibility. */

export interface Position {
  x: number;
  y: number;
  anchor?: "top-left" | "center" | "top-center" | "bottom-center";
  // 세로 기준. "bottom" 이면 `y` 를 글 블록의 **아래 끝**으로 읽어, 줄이 늘면 위로
  // 자란다(줄이 줄어도 아래가 고정). 글상자에만 쓴다 — backend Position 과 같다.
  vertical_anchor?: "top" | "bottom";
}

export interface Size {
  width: number;
  height: number;
}

/** Drop-shadow params — stored in template space, scaled at render time. */
export interface ShadowSpec {
  color: string;     // #rrggbb
  opacity: number;   // 0-100
  angle: number;     // 0-360
  distance: number;  // 0-100 (template-pixel offset)
  blur: number;      // 0-100 (template-pixel blur radius)
}

export interface TextStyle {
  font_size?: number;
  font_family?: string;
  font_weight?: string;
  fill?: string;
  text_align?: "left" | "center" | "right";
  line_height?: number;
  // 자간 — 편집기 표시 단위(0 = 기본). 렌더 시 ×10 해서 Fabric charSpacing 으로.
  letter_spacing?: number;
  shadow?: ShadowSpec | null;
  stroke?: string | null;
  stroke_width?: number;
}

export interface Background {
  type: "color" | "image_keyword" | "image_path" | "gradient";
  value?: string;
  overlay_color?: string | null;
  overlay_opacity?: number;
  // Background-gradient fill — read by renderer.ts when type === "gradient".
  color_a?: string | null;
  color_b?: string | null;
  // CSS-style angle (0=up, 90=right, 180=down, 270=left). Replaces the legacy
  // direction enum — renderer reads angle if present, else maps direction.
  angle?: number;
  direction?: "vertical" | "horizontal" | "diagonal" | null;
  // Overlay layer drawn over the base background (color/image/gradient).
  overlay_kind?: "solid" | "gradient" | null;
  overlay_gradient_angle?: number;
  overlay_gradient_direction?: "vertical" | "horizontal" | "diagonal" | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  overlay_gradient_stops?: any[] | null;
}

/** Linear-gradient fill (shape decorations only — image/text ignore).
 *  `angle` is the source-of-truth CSS-style angle (0°=up, 90°=right, etc.).
 *  `direction` is kept for backward compat with templates authored before the
 *  360° rotation control — renderer falls back to it when angle is absent. */
export interface GradientFill {
  type: "linear";
  angle?: number;
  direction?: "vertical" | "horizontal" | "diagonal";
  stops: { offset: number; color: string }[];
}

export interface ColorFillSpec {
  color: string;     // #rrggbb
  intensity: number; // 0-100
}

export interface Decoration {
  kind: "logo" | "shape" | "image";
  position: Position;
  size: Size;
  src?: string | null;
  fill?: string | GradientFill | null;
  shadow?: ShadowSpec | null;
  stroke?: string | null;
  stroke_width?: number;
  opacity?: number;  // 0..1, default 1
  color_fill?: ColorFillSpec | null;  // image-only BlendColor filter
  corner_radius?: number;  // shape rect 라운드, canvas px (피드백 14-8)
  lock_aspect?: boolean;  // editor 크기 chain-lock — keep W/H proportional on resize
}

export interface TextSlot {
  role: string;
  position: Position;
  size: Size;
  style: TextStyle;
  opacity?: number;  // 0..1, default 1
  // 고정 문구 — 값이 있으면 슬라이드 데이터 대신 이 글자가 그대로 나온다.
  fixed_text?: string | null;
}

export interface ItemBox {
  image_area: { x: number; y: number; width: number; height: number; border_radius?: number };
  title_style: TextStyle;
  title_offset_y: number;
  subtitle_style?: TextStyle | null;
  subtitle_offset_y?: number | null;
  description_style?: TextStyle | null;
  description_offset_y?: number | null;
}

export interface GridSpec {
  rows: number;
  cols: number;
  cell_size: Size;
  gap_x: number;
  gap_y: number;
  origin: Position;
  item_box: ItemBox;
}

export interface LayoutSpec {
  background: Background;
  decorations: Decoration[];
  text_slots: TextSlot[];
  grid: GridSpec | null;
}

export interface BrandStyle {
  primary_color?: string;
  background_color?: string;
  font_family?: string;
  logo_path?: string | null;
}

export interface TemplateData {
  id?: number;
  slug?: string;
  name: string;
  canvas: { width: number; height: number };
  brand: BrandStyle;
  layouts: Record<string, LayoutSpec>;
  source_post_url?: string | null;
  created_by?: string;
}

/** Display name for a layout key. Grid keys are rows-first internally
 *  (grid_3x2 = 3 rows × 2 cols), but users read grids width-first — showing
 *  the raw key made a 가로2·세로3 grid look transposed even with a hint
 *  appended (피드백 13-2, 14-4). Render grid keys as 그리드 가로×세로;
 *  every other (renamable) key passes through unchanged. Display-only —
 *  the stored key never changes. */
export function displayLayoutName(name: string): string {
  const m = /^grid_(\d+)x(\d+)$/.exec(name);
  return m ? `그리드 ${m[2]}×${m[1]}` : name;
}

/** What a Fabric object's `data` field carries so we can sync back. */
export interface FabricMeta {
  path: string;            // e.g. "layouts.grid_2x2.text_slots[0]"
  kind: "decoration" | "text_slot" | "grid_origin" | "grid_image" | "background_overlay";
}
