import asyncio, json, urllib.parse
from app.services import studio_remote
AX = ["상황별일본어", "일본맛집", "일본맛집2", "지도", "X인용"]
async def main():
    for a in AX:
        try:
            d = await studio_remote.call(f"/studio-sessions/latest?axis={urllib.parse.quote(a)}", method="GET")
        except Exception as e:
            print(a, "ERR", e); continue
        if not d.get("id"):
            print(f"{a}: (없음)"); continue
        ch = d.get("chosen") or {}
        r = d.get("result")
        print(f"{a}: id={d['id']} created={d.get('created_at')} pending={d.get('pending')!r} "
              f"topic={ch.get('topic','')!r} hook={'O' if ch.get('hook_lines') else 'X'} "
              f"img={'O' if ch.get('image_url') else 'X'} items={len(ch.get('items') or [])} "
              f"cap={'O' if ch.get('caption') else 'X'} result={(r or {}).get('id')} err={d.get('error','')!r}")
asyncio.run(main())
