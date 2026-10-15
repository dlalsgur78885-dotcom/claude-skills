import asyncio, json, sys
from app.services import studio_remote
async def main():
    cid = sys.argv[1]
    d = await studio_remote.call(f"/carousels/{cid}", method="GET")
    print("id:", d.get("id"), "| title:", d.get("title"), "| status:", d.get("status"),
          "| created:", d.get("created_at"), "| updated:", d.get("updated_at"))
    sl = d.get("slides") or []
    print("slides:", len(sl))
    for i, s in enumerate(sl):
        cj = s.get("canvas_json") or {}
        objs = cj.get("objects") or []
        texts = [o.get("text","").replace("\n"," / ") for o in objs if o.get("type") in ("textbox","text","i-text")]
        imgs = [ (o.get("src") or "")[-40:] for o in objs if o.get("type")=="image"]
        print(f" [{i+1}] layout={s.get('layout_name') or s.get('layout')} texts={texts[:5]} imgs={imgs[:3]}")
asyncio.run(main())
