import asyncio, json, sys
from app.services import studio_remote
async def main():
    cid = sys.argv[1]
    d = await studio_remote.call(f"/carousels/{cid}", method="GET")
    cd = d.get("canvas_data") or {}
    print("canvas_data keys:", list(cd.keys()))
    slides = cd.get("slides") or []
    print("n slides:", len(slides))
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            print(i, type(s)); continue
        objs = (s.get("canvas") or s).get("objects") or s.get("objects") or []
        texts = [(o.get("text") or "").replace("\n"," / ")[:60] for o in objs if "text" in o]
        imgs = [(o.get("src") or "")[-36:] for o in objs if o.get("type") == "image"]
        print(f" [{i+1}] layout={s.get('layout_name') or s.get('layout') or s.get('name')} texts={texts[:5]} imgs={imgs[:2]}")
asyncio.run(main())
