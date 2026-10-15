"""일본숙소 축 — 모양 가르기 · TAG 번호 · 지침서 · 쟈란 읽기 · 원화 범위.

네트워크는 부르지 않는다. 쟈란 페이지는 `tests/fixtures/` 에 잘라 둔 실제 응답을 읽는다.
"""
import asyncio
from datetime import date
from pathlib import Path

import pytest

from app.services import jalan_lookup as jalan
from app.services import studio_steps as studio

AXIS = "일본숙소"
FIX = Path(__file__).parent / "fixtures"
L1, L2 = "본문(일본숙소)_1", "본문(일본숙소)_2"


# ─── 모음 / 호텔 하나 가르기 ─────────────────────────────────────────────────

@pytest.mark.parametrize("topic, want", [
    ("역 3분, 쇼핑 짐 놓는 이케부쿠로 숙소 8곳", 8),
    ("쇼핑 짐 내려놓기 좋은 숙소 8곳 (도쿄 긴자)", 8),
    ("하카타역 코앞 후쿠오카 호텔 8곳", 8),
    ("가성비 조식·역 3분 토요코인 오사카 우메다 히가시", 1),
    # 「곳」이 주제 **안**에 있어도 호텔 하나다(1단계 43회차 8번).
    ("온나손 돌고래·풀 2곳 르네상스 오키나와 리조트", 1),
    ("10월 오픈 도쿄 신상 호텔 / 주방 있는 가성비 4인 숙소", 1),
])
def test_places_for_splits_set_and_single(topic, want):
    assert studio.places_for(AXIS, topic) == want


def test_places_for_other_axes_ignore_shape():
    assert studio.places_for("일본맛집", "후쿠오카, 크레페, 줄서서먹는") == 8
    assert studio.places_for("상황별일본어", "아무 주제") == 0


def test_topic_core_lodging_keeps_whole_topic():
    assert studio._topic_core("역 3분, 쇼핑 짐 놓는 이케부쿠로 숙소 8곳", AXIS) == \
        "역 3분, 쇼핑 짐 놓는 이케부쿠로 숙소"
    # 다른 축은 예전 그대로(앞 두 칸).
    assert studio._topic_core("오사카, 맛집, 가성비") == "오사카 맛집"


# ─── TAG 번호 · 항목별 낱장 ─────────────────────────────────────────────────

def test_page_tags_numbers_set():
    assert studio.page_tags([L1] * 8, L1, "•") == [str(i) for i in range(1, 9)]


def test_page_tags_single_hotel_gets_bullet_and_points_blank():
    assert studio.page_tags([L1, L2, L2, L2], L1, "•") == ["•", "", "", ""]


def test_page_tags_without_tag_layout_are_blank():
    assert studio.page_tags(["본문(맛집)"] * 3, "", "") == ["", "", ""]


def test_pages_for_item_uses_item_layout():
    conf = studio.axis_conf(AXIS)
    assert studio.pages_for_item(conf, {"layout": L2}) == [
        {"layout": L2, "fields": ["", "where", "desc", "tag"]}]
    assert studio.pages_for_item(conf, {"layout": L1})[0]["fields"] == ["name", "where", "desc", "tag"]
    # 모르는 낱장·없는 낱장은 축 기본값.
    assert studio.pages_for_item(conf, {})[0]["layout"] == L1


def test_pages_for_item_other_axes_unchanged():
    conf = studio.axis_conf("일본맛집2")
    assert studio.pages_for_item(conf, {"layout": L2}) == conf["body_pages"]
    conf = studio.axis_conf("일본맛집")
    assert studio.pages_for_item(conf, {}) == [{"layout": "본문(맛집)", "fields": conf["body_fields"]}]


def test_build_renders_one_page_per_item_with_tags(monkeypatch):
    """`build` 가 항목마다 그 낱장 하나만 그리고, TAG 를 매기고, 이력 칸을 채우는지."""
    from app.services import studio_remote

    sent: dict = {}
    history: dict = {}

    async def fake_call(path, payload=None, **kw):
        if path == "/carousels/render":
            sent["render"] = payload
            return {"canvas_slides": [{"objects": []}] * len(payload["slides"]), "template_slug": "t"}
        return {"id": 999}

    async def same(photo_at, account, prompt_key=""):
        sent["regen_prompt"] = prompt_key
        return dict(photo_at)

    monkeypatch.setattr(studio_remote, "is_configured", lambda: True)
    monkeypatch.setattr(studio_remote, "call", fake_call)
    monkeypatch.setattr(studio, "_regen_backgrounds", same)
    monkeypatch.setattr(studio, "_append_history",
                        lambda *a, **kw: history.update(kw.get("extra") or {}) or True)
    monkeypatch.setattr(studio, "_append_used_places", lambda *a, **kw: 0)
    monkeypatch.setattr(studio, "_write_keeps", lambda *a, **kw: None)
    monkeypatch.setattr(studio, "_keeps", lambda *a, **kw: [])

    items = [
        {"layout": L1, "name": "콘래드 오사카", "where": "⭐5성급 호텔", "desc": "a\nb",
         "photo": "p0", "photos": ["p0"], "place_id": "X"},
        {"layout": L2, "name": "", "where": "장점 1", "desc": "c\nd", "photo": "p1", "photos": ["p1", "p2"]},
        {"layout": L2, "name": "", "where": "장점 2", "desc": "e\nf", "photo": "p2", "photos": ["p1", "p2"]},
    ]
    out = asyncio.run(studio.build(studio.BuildBody(
        axis=AXIS, topic="40층에서 오사카 야경 콘래드 오사카", hook_lines=["a", "b"],
        image_url="cover", items=items)))
    assert out["id"] == 999
    r = sent["render"]
    slides = r["slides"]
    assert len(slides) == 5                                  # 표지 + 본문 3 + CTA
    assert r["layout_overrides"] == {"0": "표지_2줄", "1": L1, "2": L2, "3": L2, "4": "CTA"}
    assert [s["tag"] for s in slides[1:4]] == ["•", "", ""]
    assert slides[1]["headline"] == "콘래드 오사카" and slides[2]["headline"] == ""
    assert slides[2]["subtext"] == "장점 1" and slides[2]["body"] == "c\nd"
    assert r["user_image_urls"] == {"0": "cover", "4": "cover", "1": "p0", "2": "p1", "3": "p2"}
    assert sent["regen_prompt"] == "hotel"
    assert history == {"묶음": "호텔 하나", "숙소": "콘래드 오사카"}


# ─── 지침서 ─────────────────────────────────────────────────────────────────

def test_every_guide_file_exists():
    conf = studio.axis_conf(AXIS)
    names = [n for step in conf["guides"].values() for n in step] + [conf["history"]]
    missing = [n for n in names if not (studio.PROCESS_DIR / n).is_file()]
    assert not missing


@pytest.mark.parametrize("step", ["topics", "hooks", "images", "body", "caption"])
def test_rules_cut_run_logs(step):
    """회차 기록이 잘려야 한다 — 안 잘리면 1단계 하나만 30만 자다(2026-10-15 표시를 넣었다)."""
    text = studio._rules_for(step, AXIS)
    assert 0 < len(text) < 60_000
    assert "이번 회차" not in text.split("===== 규칙 원본")[-1][-200:]


def test_history_lodgings_reads_column(monkeypatch):
    # 이력은 30건마다 비워지므로 실제 파일 대신 같은 모양의 표로 본다(`일본숙소_이력.md` 머리줄 그대로).
    table = "\n".join([
        "| # | 날짜 | 주제 | 묶음 | 숙소 | 캐러셀 |",
        "|---|---|---|---|---|---|",
        "| 1 | 2026-09-17 | 하카타역 코앞 후쿠오카 호텔 8곳 | 모음 | 미야코 호텔 하카타 · 호텔 블라섬 하카타 주오 | 554 |",
        "",
        "| 8 | 2026-09-28 | 40층에서 오사카 야경 콘래드 오사카 | 호텔 하나 | 콘래드 오사카 | 618 |",
    ])
    monkeypatch.setattr(studio, "_read_doc", lambda name: table)
    assert studio._history_lodgings(AXIS) == ["미야코 호텔 하카타", "호텔 블라섬 하카타 주오", "콘래드 오사카"]


def test_history_extra_only_for_lodging():
    items = [{"name": "A", "place_id": "1"}, {"name": "B", "place_id": "2"}, {"name": "", "where": "x"}]
    assert studio._history_extra(AXIS, "도쿄 숙소 8곳", items) == {"묶음": "모음", "숙소": "A · B"}
    assert studio._history_extra("일본맛집", "도쿄 맛집", items) == {}


# ─── 쟈란 ───────────────────────────────────────────────────────────────────

def _search_html() -> str:
    return (FIX / "jalan_search.html").read_text(encoding="utf-8")


def test_parse_search_reads_blocks():
    rows = jalan.parse_search(_search_html())
    assert [r["yad"] for r in rows] == ["377788", "399999"]
    assert "ドーミーイン" in rows[0]["name"]
    assert rows[0]["address"].startswith("東京都千代田区神田須田町")


def test_pick_yad_matches_name_and_address():
    rows = jalan.parse_search(_search_html())
    assert jalan.pick_yad(rows, "ドーミーインPREMIUM神田", "〒101-0041 東京都千代田区神田須田町１丁目１６") == "377788"
    assert jalan.pick_yad(rows, "ドーミーインPREMIUM渋谷", "東京都渋谷区道玄坂1丁目2-3") == "399999"


def test_pick_yad_refuses_other_branch():
    """지점만 다른 체인은 이름이 0.85 쯤 닮는다 — 주소까지 다르면 고르지 않는다."""
    rows = jalan.parse_search(_search_html())
    assert jalan.pick_yad(rows, "ドーミーインPREMIUM池袋", "東京都豊島区東池袋1丁目") is None
    assert jalan.pick_yad(rows, "ホテルグレイスリー大阪なんば", "") is None


def test_parse_min_price_from_fixture():
    html = (FIX / "jalan_plan.html").read_text(encoding="utf-8")
    assert jalan.parse_min_price(html) == 35000
    assert jalan.parse_min_price("<html>満室</html>") is None


def test_parse_stars_only_when_written():
    assert jalan.parse_stars("<p>ホテルランク：４つ星ホテル</p>") == 4
    # 별 그림은 후기 평점이다 — 등급으로 읽지 않는다.
    assert jalan.parse_stars('<div class="c-starRating c-starRating--45"><span></span></div> 4.5') is None
    # 서로 다른 등급이 둘이면 믿지 않는다.
    assert jalan.parse_stars("<p>3つ星</p><p>5つ星</p>") is None


def test_stay_dates_are_offseason_weekdays_from_today():
    today = date(2026, 3, 30)
    days = jalan.stay_dates(today)
    assert len(days) >= 4
    assert all(d > today and d.weekday() == jalan.STAY_WEEKDAY for d in days)
    assert days == sorted(days)
    assert not any(jalan._in_peak(d) for d in days)   # 골든위크(4/29·5/6)를 건너뛴다


@pytest.mark.parametrize("yen, want", [
    (35000, "29만원대"),     # 35,000 × 8.4156 = 294,546
    (7700, "6만원대"),
    (1000, "1만원 미만"),
    (None, ""),
    (0, ""),
])
def test_krw_range(yen, want):
    assert jalan.krw_range(yen, rate=8.4156) == want


def test_fact_line_says_unknown_instead_of_guessing():
    assert "성급 확인 못 함" in jalan.fact_line({"stars": None, "min_yen": None, "dates": ["2026-11-18"]})
    assert "요금 확인 못 함" in jalan.fact_line(None)
    line = jalan.fact_line({"stars": 4, "min_yen": 35000, "dates": ["2026-11-18", "2026-12-16"]})
    assert "4성급" in line and "만원대" in line and "2026-12-16" in line
