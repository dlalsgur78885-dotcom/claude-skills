import asyncio, json, sys
from app.services import studio_remote

async def main():
    sid = sys.argv[1]
    d = await studio_remote.call(f"/studio-sessions/{sid}", method="GET")
    print("axis:", d.get("axis"), "| pending:", repr(d.get("pending")), "| error:", repr(d.get("error")))
    print("created:", d.get("created_at"))
    print("candidates keys:", list((d.get("candidates") or {}).keys()))
    ch = d.get("chosen") or {}
    print("chosen keys:", list(ch.keys()))
    for k, v in ch.items():
        s = json.dumps(v, ensure_ascii=False)
        print(f"  - {k}: {s[:200]}")
    r = d.get("result")
    print("result:", json.dumps(r, ensure_ascii=False)[:600] if r else None)
    print("built:", d.get("built"))
asyncio.run(main())
