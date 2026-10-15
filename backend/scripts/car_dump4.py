import asyncio, json, sys
from app.services import studio_remote
async def main():
    cid = sys.argv[1]
    d = await studio_remote.call(f"/carousels/{cid}", method="GET")
    cd = d.get("canvas_data") or {}
    cs = cd.get("canvas_slides") or []
    ss = cd.get("source_slides") or []
    print("canvas_slides:", len(cs), "| source_slides:", len(ss),
          "| layout_overrides:", cd.get("layout_overrides"),
          "| user_image_urls:", [ (u or "")[-28:] for u in (cd.get("user_image_urls") or [])][:4])
    for i, s in enumerate(cs):
        objs = (s or {}).get("objects") or []
        texts = [(o.get("text") or "").replace("\n"," / ")[:50] for o in objs if o.get("text")]
        imgs = [(o.get("src") or "")[-30:] for o in objs if o.get("type") == "image"]
        print(f" [{i+1}] texts={texts[:4]} imgs={imgs[:2]}")
    print("--- source_slides ---")
    for i, s in enumerate(ss):
        print(f" [{i+1}]", json.dumps(s, ensure_ascii=False)[:160])
asyncio.run(main())
