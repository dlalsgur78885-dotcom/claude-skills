"""Carousel design service - generates Fabric.js canvas JSON."""

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.template import CarouselTemplate

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class CarouselDesigner:
    """Creates carousel design data in Fabric.js JSON format."""

    def __init__(self):
        # Files act as a fallback when no DB row exists for a slug.
        self.templates = self._load_templates_from_files()

    def _load_templates_from_files(self) -> dict:
        """Load template JSON files (fallback when DB lookup misses)."""
        templates = {}
        if TEMPLATES_DIR.exists():
            for f in TEMPLATES_DIR.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    templates[data.get("id", f.stem)] = data
                except Exception as e:
                    logger.error(f"Failed to load template {f}: {e}")
        if "minimal" not in templates:
            templates["minimal"] = self._default_minimal_template()
        return templates

    async def load_template_from_db(
        self, db: AsyncSession, *, template_id: int | None = None, slug: str | None = None
    ) -> dict | None:
        """Look up a template row in DB and return its dict shape."""
        if template_id is not None:
            row = await db.get(CarouselTemplate, template_id)
        elif slug is not None:
            result = await db.execute(
                select(CarouselTemplate).where(CarouselTemplate.slug == slug).limit(1)
            )
            row = result.scalar_one_or_none()
        else:
            return None

        if not row:
            return None

        return {
            "id": row.slug,
            "name": row.name,
            "canvas": row.canvas,
            "brand": row.brand,
            "layouts": row.layouts,
            # CarouselDesigner's render path expects `slides` (legacy text-only templates).
            # New layout-based templates render via a different path; we expose both.
            "slides": (row.layouts or {}).get("_legacy_slides") or {},
        }

    def _default_minimal_template(self) -> dict:
        return {
            "id": "minimal",
            "name": "미니멀",
            "canvas": {"width": 1080, "height": 1080},
            "slides": {
                "cover": {
                    "background": "#FFFFFF",
                    "objects": [
                        {
                            "type": "textbox",
                            "role": "headline",
                            "left": 100,
                            "top": 400,
                            "width": 880,
                            "fontSize": 48,
                            "fontFamily": "Pretendard",
                            "fontWeight": "bold",
                            "fill": "#1A1A1A",
                            "textAlign": "center",
                        },
                        {
                            "type": "textbox",
                            "role": "subtext",
                            "left": 100,
                            "top": 520,
                            "width": 880,
                            "fontSize": 24,
                            "fontFamily": "Pretendard",
                            "fill": "#666666",
                            "textAlign": "center",
                        },
                    ],
                },
                "content": {
                    "background": "#FFFFFF",
                    "objects": [
                        {
                            "type": "textbox",
                            "role": "headline",
                            "left": 80,
                            "top": 100,
                            "width": 920,
                            "fontSize": 36,
                            "fontFamily": "Pretendard",
                            "fontWeight": "bold",
                            "fill": "#1A1A1A",
                        },
                        {
                            "type": "textbox",
                            "role": "body",
                            "left": 80,
                            "top": 200,
                            "width": 920,
                            "fontSize": 22,
                            "fontFamily": "Pretendard",
                            "fill": "#333333",
                            "lineHeight": 1.6,
                        },
                    ],
                },
                "cta": {
                    "background": "#1A1A1A",
                    "objects": [
                        {
                            "type": "textbox",
                            "role": "headline",
                            "left": 100,
                            "top": 380,
                            "width": 880,
                            "fontSize": 40,
                            "fontFamily": "Pretendard",
                            "fontWeight": "bold",
                            "fill": "#FFFFFF",
                            "textAlign": "center",
                        },
                        {
                            "type": "textbox",
                            "role": "cta_text",
                            "left": 100,
                            "top": 500,
                            "width": 880,
                            "fontSize": 24,
                            "fontFamily": "Pretendard",
                            "fill": "#CCCCCC",
                            "textAlign": "center",
                        },
                    ],
                },
            },
        }

    async def create_carousel(
        self,
        text_data: dict,
        image_paths: list[str] | None = None,
        template: str = "minimal",
        canvas_size: dict | None = None,
    ) -> dict:
        """Generate Fabric.js canvas JSON for each slide."""
        tmpl = self.templates.get(template, self.templates["minimal"])
        size = canvas_size or tmpl.get("canvas", {"width": 1080, "height": 1080})

        slides_data = text_data.get("slides", [])
        canvas_slides = []

        for slide in slides_data:
            slide_type = slide.get("type", "content")
            tmpl_slide = tmpl["slides"].get(slide_type, tmpl["slides"]["content"])

            # Build Fabric.js canvas JSON for this slide
            canvas_json = {
                "version": "6.0.0",
                "width": size["width"],
                "height": size["height"],
                "background": tmpl_slide["background"],
                "objects": [],
            }

            for obj_template in tmpl_slide["objects"]:
                role = obj_template.get("role", "")
                text = slide.get(role, "")

                if not text:
                    continue

                fabric_obj = {
                    "type": obj_template["type"],
                    "left": obj_template["left"],
                    "top": obj_template["top"],
                    "width": obj_template["width"],
                    "text": text,
                    "fontSize": obj_template.get("fontSize", 24),
                    "fontFamily": obj_template.get("fontFamily", "Pretendard"),
                    "fontWeight": obj_template.get("fontWeight", "normal"),
                    "fill": obj_template.get("fill", "#000000"),
                    "textAlign": obj_template.get("textAlign", "left"),
                    "lineHeight": obj_template.get("lineHeight", 1.4),
                }
                canvas_json["objects"].append(fabric_obj)

            # Add image if available
            if image_paths and slide_type == "content":
                idx = slide.get("index", 0)
                if idx < len(image_paths):
                    canvas_json["objects"].insert(0, {
                        "type": "image",
                        "src": image_paths[idx],
                        "left": 0,
                        "top": 0,
                        "width": size["width"],
                        "height": size["height"],
                        "opacity": 0.3,
                    })

            canvas_slides.append(canvas_json)

        return {
            "template": template,
            "canvas_size": size,
            "slide_count": len(canvas_slides),
            "canvas_slides": canvas_slides,
        }

    async def apply_template(self, carousel_id: int, template: str) -> dict:
        """Apply a new template to an existing carousel."""
        # Stub - would load from DB, re-apply template, save
        return {"carousel_id": carousel_id, "template": template, "applied": True}

    async def suggest_layout(
        self, slide_text: str = "", has_image: bool = False, style_preference: str = ""
    ) -> dict:
        """Suggest suitable layouts for given content."""
        suggestions = []
        for tid, tmpl in self.templates.items():
            score = 0.5
            if has_image and "photo" in tid:
                score += 0.3
            if not has_image and "minimal" in tid:
                score += 0.2
            suggestions.append({"template_id": tid, "name": tmpl["name"], "score": score})

        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return {"suggestions": suggestions}
