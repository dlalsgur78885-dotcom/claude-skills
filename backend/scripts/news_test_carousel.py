"""일본뉴스 축 테스트 — 기사 1건으로 캐러셀 한 편 (템플릿 92).

축/지침서가 아직 없어 문구는 인자로 받고, 나머지 흐름은 studio_steps.build 와 같게 맞췄다.
"""
import json, sys, urllib.request, ssl, secrets, uuid

BASE = "https://3-35-18-166.sslip.io:3443"
API = BASE + "/api"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

sys.path.insert(0, ".")
from app.services.studio_steps import _tidy_canvas_slides  # noqa: E402


def call(path, payload=None, token=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, context=CTX, timeout=180) as r:
        return json.loads(r.read().decode())


def upload(blob, token, filename="news.jpg"):
    b = uuid.uuid4().hex
    body = b"".join([
        f"--{b}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: image/jpeg\r\n\r\n", blob, f"\r\n--{b}--\r\n".encode(),
    ])
    req = urllib.request.Request(API + "/images/upload", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={b}")
    req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, context=CTX, timeout=120) as r:
        return BASE + json.loads(r.read().decode())["url"]


def main():
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    pw = cfg["password"]
    token = call("/auth/login", {"username": cfg["account"], "password": pw})["access_token"]

    req = urllib.request.Request(cfg["photo_url"], headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
        photo = upload(r.read(), token)
    print("photo:", photo)

    bodies = cfg["bodies"]
    slides = [{"index": 0, "type": "cover", "headline": "\n".join(cfg["hook_lines"]),
               "subtext": "", "body": "", "tag": ""}]
    for i, text in enumerate(bodies, start=1):
        slides.append({"index": i, "type": "content", "headline": "", "subtext": "",
                       "body": text, "tag": "", "items": [{"image_url": photo}]})
    cta = len(slides)
    slides.append({"index": cta, "type": "cta", "headline": "", "subtext": "", "body": "", "tag": ""})

    overrides = {"0": "썸네일", str(cta): "CTA(X인용)"}
    for i in range(1, cta):
        overrides[str(i)] = "본문(X인용)"
    user_image_urls = {"0": photo, str(cta): photo}
    user_item_image_urls = {str(i): {"0": photo} for i in range(1, cta)}

    rendered = call("/carousels/render", {
        "template_id": cfg["template_id"], "slides": slides,
        "layout_overrides": overrides,
        "user_image_urls": user_image_urls,
        "user_item_image_urls": user_item_image_urls,
    }, token)
    cs = rendered.get("canvas_slides") or []
    print("rendered slides:", len(cs))
    cs = _tidy_canvas_slides(cs, {0, cta})

    created = call("/carousels/", {
        "title": cfg["topic"],
        "template_id": str(rendered.get("template_slug") or "minimal"),
        "canvas_data": {
            "canvas_slides": cs, "source_slides": slides,
            "user_image_urls": user_image_urls,
            "user_item_image_urls": user_item_image_urls,
            "layout_overrides": overrides,
            "template_db_id": cfg["template_id"],
            "caption": "", "hashtags": [],
        },
    }, token)
    print("carousel:", created.get("id"), BASE + "/editor/" + str(created.get("id")))


main()
