"""Use Gemini Vision to classify a slide's background structure precisely.

Pure CV (gradient_analyzer) hits a wall on slides where:
  - a solid caption strip sits under a photo with overlaid text
  - the background is a true 2-color gradient (sunset, etc.) that pixel-row
    variance can't distinguish from a photo
  - decorative shapes sit on top of an otherwise-uniform background

Vision LLMs handle these in one shot. We send one slide image and ask for a
structured JSON description of its background. This costs ~$0.001 (2.0-flash)
per slide and runs once at template creation, so it's well worth the accuracy.

The output dict matches what `to_background_dict()` in gradient_analyzer
would have returned — same downstream consumers, just better classification.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.llm_client import gemini_vision

logger = logging.getLogger(__name__)


_PROMPT = """Analyze the BACKGROUND of this single Instagram carousel slide image.
Ignore text and small decorations; focus on the underlying visual surface.

Classify it as ONE of these four kinds:

1. **solid**     — a single flat color fills the whole canvas
                   (foreground photos / text float on top)
2. **gradient**  — a smooth two-color (or multi-stop) color transition fills
                   the whole canvas (e.g. sunset orange→purple)
3. **photo**     — a single full-canvas photograph (the photo itself may
                   contain natural color gradation — that's still "photo")
4. **composite** — the canvas is SPLIT into a photo zone AND a solid color
                   zone (typical: photo on top, white caption strip on bottom).
                   Provide where the split is.

ALSO detect any OVERLAY laid on top of a photo bg (for readability of text):
- If the photo has a UNIFORM dark/light tint covering the whole canvas →
  `overlay_kind: "solid"`, `overlay_color` (hex), `overlay_opacity` (0..1).
- If the overlay FADES (e.g. transparent at the top, dark at the bottom, so
  caption text reads cleanly) → `overlay_kind: "gradient"`, with stops:
  `[{offset:0, color:"#RRGGBB", alpha:0..1}, {offset:1, color:"#RRGGBB", alpha:0..1}]`.
  Direction is typically `"vertical"`. Use 2-3 stops only.
- If there's no overlay → `overlay_kind: null`.

Output ONLY this JSON (no prose, no fences):

```
{
  "kind": "solid" | "gradient" | "photo" | "composite",
  "color_a": "#RRGGBB" | null,
  "color_b": "#RRGGBB" | null,
  "direction": "vertical" | "horizontal" | "diagonal" | "none",
  "split_y": 0.0-1.0 | null,
  "image_keyword": "<short English search keyword for the photo>" | null,
  "overlay_kind": "solid" | "gradient" | null,
  "overlay_color": "#RRGGBB" | null,
  "overlay_opacity": 0.0-1.0 | null,
  "overlay_gradient_direction": "vertical" | "horizontal" | "diagonal" | null,
  "overlay_gradient_stops": [{"offset": 0.0, "color": "#RRGGBB", "alpha": 0.0}, ...] | null
}
```

Rules:
- `solid`     → `color_a` = the flat color. Others mostly null.
- `gradient`  → `color_a` = top-or-left endpoint, `color_b` = bottom-or-right endpoint,
                `direction` = vertical/horizontal/diagonal. `image_keyword` = null.
- `photo`     → `image_keyword` = REQUIRED. 2-4 word English describing the scene
                (e.g. "santorini blue domes", "bali sunset temple"). NEVER empty.
                If overlay exists, fill the overlay_* fields.
- `composite` → photo on one side + solid strip on the other (split_y).
                `image_keyword` = REQUIRED. Describe the photo zone. NEVER empty.

Examples:
  Solid white card with a centered photo:
    {"kind":"solid","color_a":"#FFFFFF",...,"overlay_kind":null}

  Sunset photo with NO overlay:
    {"kind":"photo","image_keyword":"bali sunset temple","overlay_kind":null,...}

  Train station photo with a vertical FADE that darkens the bottom for the caption:
    {"kind":"photo","image_keyword":"japan snowy train station","overlay_kind":"gradient",
     "overlay_gradient_direction":"vertical",
     "overlay_gradient_stops":[{"offset":0,"color":"#000000","alpha":0.0},
                               {"offset":0.55,"color":"#000000","alpha":0.35},
                               {"offset":1,"color":"#000000","alpha":0.80}]}

  Yakiniku photo with a uniform 40% black tint everywhere:
    {"kind":"photo","image_keyword":"yakiniku grill","overlay_kind":"solid",
     "overlay_color":"#000000","overlay_opacity":0.4}
"""


async def analyze_background_vision(image_path: str) -> dict[str, Any] | None:
    """Run Gemini Vision on a slide and return a normalized background dict.

    Returns None on failure (caller should fall back to the CV analyzer).
    """
    try:
        raw = await gemini_vision(
            image_paths=[image_path],
            prompt=_PROMPT,
            system="You are a precise visual analyst. Output strict JSON only.",
            # Claude Sonnet 4 reads subtle visual structure (gradient overlays,
            # split layouts) far better than Gemini Flash. ~$0.005-0.015/call.
            # Despite the function name, gemini_vision() routes by model id, so
            # this transparently calls Anthropic via litellm.
            model="sonnet",
            json_mode=True,
            max_tokens=512,
        )
    except Exception as e:
        logger.warning("[bg_vision] Gemini call failed for %s: %s", image_path, e)
        return None

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            logger.warning("[bg_vision] non-JSON response: %s", str(raw)[:120])
            return None
    if not isinstance(raw, dict):
        logger.warning("[bg_vision] unexpected response shape: %s", type(raw).__name__)
        return None

    kind = raw.get("kind")
    if kind not in ("solid", "gradient", "photo", "composite"):
        logger.warning("[bg_vision] invalid kind: %s", kind)
        return None

    return raw


def vision_to_background_dict(v: dict[str, Any]) -> dict[str, Any]:
    """Convert the Gemini Vision result into the Template `background` JSON shape."""
    # Overlay info — carried through to all kinds where it makes sense.
    overlay_extras: dict[str, Any] = {}
    ok = v.get("overlay_kind")
    if ok in ("solid", "gradient"):
        overlay_extras["overlay_kind"] = ok
        if ok == "solid":
            overlay_extras["overlay_color"] = v.get("overlay_color") or "#000000"
            overlay_extras["overlay_opacity"] = float(v.get("overlay_opacity") or 0.0)
        else:
            overlay_extras["overlay_gradient_direction"] = v.get("overlay_gradient_direction") or "vertical"
            stops = v.get("overlay_gradient_stops") or []
            overlay_extras["overlay_gradient_stops"] = [
                {
                    "offset": float(s.get("offset", 0)),
                    "color": s.get("color") or "#000000",
                    "alpha": float(s.get("alpha", 0.5)),
                }
                for s in stops if isinstance(s, dict)
            ]
            # Also leave overlay_opacity at 0 so the solid path doesn't fire too.
            overlay_extras["overlay_color"] = None
            overlay_extras["overlay_opacity"] = 0.0

    kind = v.get("kind")
    if kind == "solid":
        return {
            "type": "color",
            "value": v.get("color_a") or "#FFFFFF",
            "overlay_color": None,
            "overlay_opacity": 0.0,
            **overlay_extras,
        }
    if kind == "gradient":
        a = v.get("color_a") or "#FFFFFF"
        b = v.get("color_b") or "#000000"
        direction = v.get("direction") or "vertical"
        return {
            "type": "gradient",
            "value": f"{a}→{b} {direction}",
            "color_a": a,
            "color_b": b,
            "direction": direction,
            "overlay_color": None,
            "overlay_opacity": 0.0,
            **overlay_extras,
        }
    if kind == "composite":
        return {
            "type": "composite",
            "value": v.get("image_keyword") or "",
            "split_y": v.get("split_y") or 0.75,
            "top": {"type": "image_keyword", "value": v.get("image_keyword") or ""},
            "bottom": {"type": "color", "value": v.get("color_b") or "#FFFFFF"},
            "overlay_color": None,
            "overlay_opacity": 0.0,
            **overlay_extras,
        }
    # photo
    return {
        "type": "image_keyword",
        "value": v.get("image_keyword") or "",
        "overlay_color": None,
        "overlay_opacity": 0.0,
        **overlay_extras,
    }
