# 소재 한 번에 긁기 — Togetter · 일본 매체 RSS · 유튜브 · 스레드.
#
# 규칙(문턱·등급·한국 접점)은 `docs/process/_유형공통.md` 와 `_일본매체_RSS.md` 다.
# 여기서는 **긁어서 줄 세우기만** 한다. 무엇을 만들지는 사람이 고른다.
#
# 쓰는 법:
#   python scripts/collect_sources.py                 # Togetter + RSS (빠름, 1분 안쪽)
#   python scripts/collect_sources.py --youtube       # 유튜브까지 (키워드당 ~15초)
#   python scripts/collect_sources.py --threads       # 스레드까지 (키워드당 ~40초, 건질 게 적다)
#   python scripts/collect_sources.py --all --n 30
#
# 결과는 `tmp/수집_<날짜>.md` 에 쓰고, 요약을 화면에 찍는다.
import argparse, datetime, json, pathlib, re, subprocess, sys, html as htmllib
import xml.etree.ElementTree as ET
import httpx

ROOT = pathlib.Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"}
TODAY = datetime.date.today().isoformat()

# ── 문턱 — 플랫폼마다 수치의 뜻이 다르다. 2026-10-20 실측 분포로 잡았다.
THRESHOLD = {           # (A등급, B등급) — B 미만은 후보에서 뺀다
    "togetter": (90_000, 20_000),      # pv. 112건 분포에서 상위 10% / 중앙
    "youtube":  (1_000_000, 100_000),  # 조회수
    "threads":  (3_000, 500),          # 좋아요
}

TOGETTER = ["https://togetter.com/hot",
            "https://togetter.com/t/%E6%97%85%E8%A1%8C",        # 여행
            "https://togetter.com/t/%E3%82%B0%E3%83%AB%E3%83%A1",  # 그루메
            "https://togetter.com/t/%E6%B5%B7%E5%A4%96%E3%81%AE%E5%8F%8D%E5%BF%9C",  # 해외반응
            "https://togetter.com/t/%E3%83%8D%E3%82%BF"]        # 네타

# 2026-10-20 직접 호출해 항목이 돌아온 것만 남겼다.
FEEDS = [
    ("J타운넷", "https://j-town.net/index.xml"),
    ("ねとらぼ", "https://rss.itmedia.co.jp/rss/2.0/netlab.xml"),
    ("로켓뉴스24", "https://rocketnews24.com/feed/"),
    ("데일리포털Z", "https://dailyportalz.jp/feed/headline"),
    ("J-CAST", "https://www.j-cast.com/index.xml"),
    ("訪日ラボ", "https://honichi.com/feed"),
    ("TRAICY", "https://www.traicy.com/feed"),
    ("트래블보이스", "https://www.travelvoice.jp/feed"),
    ("야마토고코로", "https://yamatogokoro.jp/feed/"),
    ("트래블워치", "https://travel.watch.impress.co.jp/data/rss/1.0/trw/feed.rdf"),
]

YT_KEYWORDS = ["外国人インタビュー 日本", "初来日 驚いた", "日本 旅行 外国人 反応"]
TH_KEYWORDS = ["まさかの", "韓国人"]

# 한국 독자와 닿는 말 — 하나도 안 걸리면 후보 아래로 내린다.
KO_HIT = ["韓国", "ソウル", "釜山", "K-POP", "日韓"]
TRAVEL_HIT = ["観光", "旅行", "インバウンド", "外国人", "空港", "新幹線", "ホテル", "旅館", "コンビニ",
              "ラーメン", "寿司", "駅", "温泉", "物価", "円安", "値上げ", "マナー", "免税", "宿"]
# 일본 내부 정치·혐오·중범죄는 이 채널에서 쓰지 않는다.
DROP = ["政治", "選挙", "参政党", "自民", "立憲", "国会", "首相", "内閣", "移民政策",
        "殺害", "殺人", "自殺", "わいせつ", "性的暴行", "児童ポルノ", "献金"]


def grade(kind, n):
    if n is None:
        return "-"
    a, b = THRESHOLD[kind]
    return "A" if n >= a else ("B" if n >= b else "C")


def tag(title):
    if any(k in title for k in DROP):
        return "제외"
    if any(k in title for k in KO_HIT):
        return "한국"
    if any(k in title for k in TRAVEL_HIT):
        return "여행접점"
    return "일반"


def fetch_togetter():
    out = []
    for url in TOGETTER:
        try:
            h = httpx.get(url, headers=UA, timeout=30, follow_redirects=True).text
        except Exception as e:
            print(f"  ! {url} {e}", file=sys.stderr); continue
        for b in h.split('<li class='):
            m = re.search(r'<a href="(https://togetter\.com/li/\d+)" title="([^"]+)"', b)
            if not m:
                continue
            pv = re.search(r'view_str"><span>(\d+)</span>pv', b)
            dt = re.search(r'datetime="(\d{4}-\d{2}-\d{2})', b)
            out.append({"src": "Togetter", "kind": "togetter", "title": htmllib.unescape(m.group(2)),
                        "url": m.group(1), "num": int(pv.group(1)) if pv else None,
                        "unit": "pv", "date": dt.group(1) if dt else None})
    return out


def fetch_feeds():
    out = []
    for name, url in FEEDS:
        try:
            r = httpx.get(url, headers=UA, timeout=30, follow_redirects=True)
            root = ET.fromstring(r.content)
        except Exception as e:
            print(f"  ! {name} {e}", file=sys.stderr); continue
        # RSS 2.0 / RSS 1.0(RDF) / Atom — 세 모양을 다 받는다
        items = list(root.iter("item")) or list(root.iter("{http://purl.org/rss/1.0/}item"))             or list(root.iter("{http://www.w3.org/2005/Atom}entry"))
        n = 0
        for it in items:
            t = (it.findtext("title") or it.findtext("{http://purl.org/rss/1.0/}title")
                 or it.findtext("{http://www.w3.org/2005/Atom}title") or "")
            link = it.findtext("link") or it.findtext("{http://purl.org/rss/1.0/}link") or ""
            if not link:
                ln = it.find("{http://www.w3.org/2005/Atom}link")
                link = ln.get("href") if ln is not None else ""
            date = (it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or "")[:16]
            out.append({"src": name, "kind": "rss", "title": t.strip(), "url": link.strip(),
                        "num": None, "unit": "", "date": date})
            n += 1
            if n >= 25:
                break
        print(f"  {name}: {n}건", file=sys.stderr)
    return out


def fetch_youtube():
    out = []
    for kw in YT_KEYWORDS:
        url = f"https://www.youtube.com/results?search_query={httpx.URL(kw).raw_path.decode()}&sp=CAMSBAgDEAE"
        try:
            p = subprocess.run(["yt-dlp", "--flat-playlist", "--no-warnings", "--playlist-end", "10",
                                "--print", "%(view_count)s\t%(channel)s\t%(title)s\t%(webpage_url)s", url],
                               capture_output=True, text=True, timeout=240, encoding="utf-8")
        except Exception as e:
            print(f"  ! youtube {kw} {e}", file=sys.stderr); continue
        for line in (p.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            v, ch, title, u = parts
            out.append({"src": f"유튜브/{ch[:14]}", "kind": "youtube", "title": title,
                        "url": u, "num": int(v) if v.isdigit() else None, "unit": "회", "date": ""})
    return out


def fetch_threads():
    out = []
    for kw in TH_KEYWORDS:
        try:
            p = subprocess.run(["node", str(ROOT / "scripts" / "threads-search.mjs"), kw, "15"],
                               capture_output=True, text=True, timeout=300, encoding="utf-8", cwd=ROOT)
        except Exception as e:
            print(f"  ! threads {kw} {e}", file=sys.stderr); continue
        for line in (p.stdout or "").splitlines():
            if not line.startswith("{"):
                continue
            d = json.loads(line)
            t = (d.get("text") or "").replace("\n", " ")
            if any(w in t for w in ["炎上覚悟", "黄金", "無料で共有", "フォローしてくださった"]):
                continue  # 투자·도박 스팸
            likes = int(re.sub(r"[^\d]", "", d.get("likes") or "0") or 0)
            out.append({"src": "스레드", "kind": "threads", "title": t[:90], "url": d["url"],
                        "num": likes, "unit": "♥", "date": (d.get("time") or "")[:10]})
    return out


def known_urls():
    """이미 다룬 소재 — 이력과 지난 후보 파일에 적힌 URL 은 빼고 보여준다."""
    seen = set()
    for f in (ROOT / "docs" / "process").glob("*.md"):
        if "이력" in f.name or "후보" in f.name:
            seen |= set(re.findall(r"https?://[^\s)\]]+", f.read_text(encoding="utf-8")))
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--youtube", action="store_true")
    ap.add_argument("--threads", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--n", type=int, default=30, help="추려서 보여줄 개수")
    a = ap.parse_args()

    rows = fetch_togetter() + fetch_feeds()
    if a.youtube or a.all:
        rows += fetch_youtube()
    if a.threads or a.all:
        rows += fetch_threads()

    seen_url, old = set(), known_urls()
    picked = []
    for r in rows:
        if not r["url"] or r["url"] in seen_url:
            continue
        seen_url.add(r["url"])
        r["tag"] = tag(r["title"])
        r["grade"] = grade(r["kind"], r["num"]) if r["kind"] in THRESHOLD else "-"
        r["old"] = r["url"] in old
        if r["tag"] == "제외" or r["grade"] == "C" or r["old"]:
            continue
        picked.append(r)

    order = {"한국": 0, "여행접점": 1, "일반": 2}
    picked.sort(key=lambda r: (order[r["tag"]], {"A": 0, "B": 1, "-": 2}[r["grade"]], -(r["num"] or 0)))
    top = picked[: a.n]

    out = [f"# 소재 수집 {TODAY} — {len(top)}건 (긁은 것 {len(rows)}건)", "",
           "`scripts/collect_sources.py` 자동 수집. 문턱·등급은 `docs/process/_유형공통.md`.",
           "**제목·수치만 본 단계다.** 본문·사진·일본인 반응은 고른 뒤 연다.", "",
           "| 접점 | 등급 | 수치 | 출처 | 제목 | 원문 |", "|---|---|---|---|---|---|"]
    for r in top:
        num = f'{r["num"]:,}{r["unit"]}' if r["num"] else "-"
        out.append(f'| {r["tag"]} | {r["grade"]} | {num} | {r["src"]} | {r["title"][:60]} | {r["url"]} |')
    p = ROOT / "tmp" / f"수집_{TODAY}.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")

    from collections import Counter
    print(f'\n긁은 것 {len(rows)} → 문턱 통과 {len(picked)} → 보여줄 것 {len(top)}')
    print("접점:", dict(Counter(r["tag"] for r in picked)), "/ 등급:", dict(Counter(r["grade"] for r in picked)))
    print("→", p)


if __name__ == "__main__":
    main()
