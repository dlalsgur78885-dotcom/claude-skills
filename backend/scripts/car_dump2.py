import asyncio, json, sys
from app.services import studio_remote
async def main():
    cid = sys.argv[1]
    d = await studio_remote.call(f"/carousels/{cid}", method="GET")
    print(json.dumps({k: (v if not isinstance(v, (list, dict)) else f"<{type(v).__name__} len={len(v)}>") for k, v in d.items()}, ensure_ascii=False))
    for k, v in d.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            print("LIST FIELD:", k, "n=", len(v), "first keys:", list(v[0].keys())[:12])
asyncio.run(main())
