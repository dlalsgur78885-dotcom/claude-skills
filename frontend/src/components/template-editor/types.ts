/** Shape mirrors backend's template_spec.py — kept loose for editor flexibility. */

export interface Position {
  x: number;
  y: number;
  anchor?: "top-left" | "center" | "top-center" | "bottom-center";
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
}

export interface TextSlot {
  role: string;
  position: Position;
  size: Size;
  style: TextStyle;
  opacity?: number;  // 0..1, default 1
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

/** What a Fabric object's `data` field carries so we can sync back. */
export interface FabricMeta {
  path: string;            // e.g. "layouts.grid_2x2.text_slots[0]"
  kind: "decoration" | "text_slot" | "grid_origin" | "grid_image" | "background_overlay";
}
