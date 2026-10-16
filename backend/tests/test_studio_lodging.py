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


# ─── 교통 원문 (2026-10-16) ─────────────────────────────────────────────────

def _access_block(yad: str) -> str:
    """고정 파일에서 `<div id="…">` 한 덩이만 잘라 낸다(다음 덩이 앞까지)."""
    html = (FIX / "jalan_access.html").read_text(encoding="utf-8")
    start = html.index(f'<div id="{yad}">')
    end = html.find('\n<div id="', start + 1)
    return html[start:end if end > 0 else len(html)]


def test_parse_access_reads_cell_not_label():
    """「アクセス」 칸의 첫 글만 읽는다 — 아래 이름표 「駅から徒歩5分以内」는 쟈란 분류라 읽지 않는다."""
    ginza = jalan.parse_access(_access_block("yad381362"))
    assert ginza == "地下鉄【東銀座駅】より徒歩1分/東京メトロ【銀座駅】より徒歩4分"
    assert jalan.walk_minutes(ginza) == [("東銀座駅", 1), ("銀座駅", 4)]
    namba = jalan.parse_access(_access_block("yad361794"))
    assert namba.startswith("南海電鉄難波駅直結")
    assert ("南海電鉄難波駅", None) in jalan.walk_minutes(namba)
    assert "以内" not in namba


def test_parse_access_falls_back_to_header_line():
    head = _access_block("header381362")
    assert jalan.walk_minutes(jalan.parse_access(head))[0] == ("東銀座駅", 1)
    assert jalan.parse_access("<html>no access</html>") == ""


def test_fact_line_carries_access():
    line = jalan.fact_line({"stars": None, "min_yen": 33210, "dates": ["2026-11-18"],
                            "access": "地下鉄【東銀座駅】より徒歩1分"})
    assert "東銀座駅 도보 1분" in line and "27만원대" in line


# ─── 얼버무린 설명 · 주제 값 대조 (2026-10-16) ────────────────────────────────

@pytest.mark.parametrize("why, hedged", [
    ("역에서 짐을 옮기는 동선과 전망. 연결 동선과 객실별 전망은 확인이 필요하다.", True),
    ("도보 시간과 요금 확인 필요.", True),
    ("요금이 아직 확인되지 않았다", True),
    ("난바역 도보 3분에 2인 9만원대", False),
])
def test_hedge_guard(why, hedged):
    assert studio._hedged({"topic": "아무 주제", "why": why}) is hedged


def _verify_with(monkeypatch, topic, places, verdicts, why="이유"):
    """`_find_places` · 쟈란 · 판정 모델을 가짜로 바꾸고 `_verify_topics` 를 돌린다."""
    from app.services import place_lookup

    asked = {}

    async def fake_find(t, axis, want):
        return list(places), [[] for _ in places], []

    async def fake_facts(good):
        return [{"stars": None, "min_yen": 10000, "dates": ["2026-11-18"], "access": ""} for _ in good]

    async def fake_ask(step, task, shape, extra="", schema=None, axis=None, **kw):
        asked["schema"] = schema
        asked["extra"] = extra
        return {"claims": ["가성비"], "items": verdicts}

    monkeypatch.setattr(place_lookup, "is_available", lambda: True)
    monkeypatch.setattr(studio, "_find_places", fake_find)
    monkeypatch.setattr(jalan, "facts_many", fake_facts)
    monkeypatch.setattr(studio, "_ask", fake_ask)
    monkeypatch.setattr(studio, "_drops", lambda axis: [])
    monkeypatch.setattr(studio, "_CHECKED", {})
    kept = asyncio.run(studio._verify_topics([{"topic": topic, "why": why}], AXIS))
    return kept, asked, studio._CHECKED


def _hotels(n):
    return [{"name": f"H{i}", "place_id": f"p{i}", "rating": 4.2} for i in range(1, n + 1)]


def test_single_hotel_kept_when_claims_confirmed(monkeypatch):
    kept, asked, checked = _verify_with(
        monkeypatch, "난바역 도보 3분 가성비 호텔 그레이스리 오사카 난바", _hotels(1),
        [{"n": "1", "ok": True, "why": ""}])
    assert [k["topic"] for k in kept] == ["난바역 도보 3분 가성비 호텔 그레이스리 오사카 난바"]
    assert asked["schema"] is studio.S_CLAIMS
    assert "쟈란" in asked["extra"]
    # 확인된 숙소가 담겨 훅·본문이 다시 찾지 않는다.
    assert len(next(iter(checked.values()))[0]) == 1


def test_single_hotel_dropped_when_claim_fails(monkeypatch):
    kept, _, checked = _verify_with(
        monkeypatch, "난바역 도보 3분 가성비 스위소텔 난카이 오사카", _hotels(1),
        [{"n": "1", "ok": False, "why": "2인 30만원대 — 가성비 아님"}])
    assert kept == [] and checked == {}


def test_set_partial_fails_count_rule(monkeypatch):
    """모음은 여덟 곳이 다 값을 채워야 한다 — 한 곳이라도 빠지면 8곳 문턱에 걸려 주제가 빠진다."""
    verdicts = [{"n": str(i), "ok": i != 3, "why": "" if i != 3 else "대욕장 근거 없음"} for i in range(1, 9)]
    kept, _, _ = _verify_with(monkeypatch, "삿포로 대욕장 숙소 8곳", _hotels(8), verdicts)
    assert kept == []


def test_set_all_confirmed_kept(monkeypatch):
    verdicts = [{"n": str(i), "ok": True, "why": ""} for i in range(1, 9)]
    kept, _, _ = _verify_with(monkeypatch, "삿포로 대욕장 숙소 8곳", _hotels(8), verdicts)
    assert len(kept) == 1


def test_missing_verdict_counts_as_unconfirmed():
    bad = studio._claim_verdicts({"items": [{"n": "1", "ok": True}, {"n": "2", "ok": True},
                                            {"n": "2", "ok": False, "why": "x"}]}, 3)
    assert set(bad) == {2, 3}


def test_hedged_topic_dropped_before_lookup(monkeypatch):
    kept, asked, _ = _verify_with(
        monkeypatch, "시부야역 연결에 객실 야경까지, 시부야 엑셀 호텔 도큐", _hotels(1),
        [{"n": "1", "ok": True}], why="연결 동선과 객실별 전망은 확인이 필요하다.")
    assert kept == [] and not asked                      # 모델도 안 불렀다


def test_judge_failure_drops_lodging_topic(monkeypatch):
    from app.services import place_lookup

    async def fake_find(t, axis, want):
        return _hotels(1), [[]], []

    async def boom(*a, **kw):
        raise RuntimeError("codex down")

    async def fake_facts(good):
        return [None for _ in good]

    monkeypatch.setattr(place_lookup, "is_available", lambda: True)
    monkeypatch.setattr(studio, "_find_places", fake_find)
    monkeypatch.setattr(jalan, "facts_many", fake_facts)
    monkeypatch.setattr(studio, "_ask", boom)
    monkeypatch.setattr(studio, "_drops", lambda axis: [])
    monkeypatch.setattr(studio, "_CHECKED", {})
    assert asyncio.run(studio._verify_topics([{"topic": "콘래드 오사카", "why": "야경"}], AXIS)) == []


# ─── 본문 금지어 (2026-10-16 d44f 회차) ──────────────────────────────────────

@pytest.mark.parametrize("page, bad", [
    ({"name": "", "sub": "가격", "desc": "쟈란 조회 최저가는 2인 1박 27만원대였어\n저렴한 가격인지는 비교해 봐야 해"}, True),
    ({"name": "호텔 닛코 오사카", "sub": "📍신사이바시역 연결", "desc": "신사이바시역과 지하로 연결된 성급·요금 미확인 호텔"}, True),
    ({"name": "", "sub": "요금", "desc": "숙박일에 따라 달라지니 예약 전엔 다시 확인해야 해"}, True),
    ({"name": "", "sub": "전망", "desc": "부분 시티뷰 객실은 전망이 아쉬울 수도 있어"}, True),
    ({"name": "", "sub": "날짜", "desc": "숙박일 네 날짜를 비교해 봤어"}, True),
    ({"name": "", "sub": "장점", "desc": "2인 9만원대 가격에 대욕장까지 씁니다."}, False),
    # 지침서가 정한 서브 꼴은 통과한다.
    ({"name": "콘래드 오사카", "where": "⭐구글 평점 4.4", "desc": "나카노시마 40층 로비 5성급 호텔\n야경이 바로 보입니다."}, False),
    ({"name": "도미인", "sub": "📍간다역 도보 5분", "desc": "대욕장 딸린 2인 20만원대 호텔\n야식 라멘을 무료로 줍니다."}, False),
])
def test_lodging_body_guard(page, bad):
    assert bool(studio._lodging_faults([page])) is bad


def _body_with(monkeypatch, topic, n_places, answers):
    """`make_lodging_body` 를 숙소·쟈란·사진·모델 모두 가짜로 돌린다. `answers` 는 차례로 돌려줄 응답."""
    calls = []
    hotels = [{"name": f"H{i}", "place_id": f"p{i}"} for i in range(1, n_places + 1)]

    async def fake_places(axis, t):
        return hotels, [[] for _ in hotels], []

    async def fake_facts(good):
        return [None for _ in good]

    async def fake_shots(place, cap):
        return ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]

    async def fake_ask(step, task, shape, extra="", schema=None, axis=None, **kw):
        calls.append(extra)
        return answers[len(calls) - 1]

    monkeypatch.setattr(studio, "_lodging_places", fake_places)
    monkeypatch.setattr(jalan, "facts_many", fake_facts)
    monkeypatch.setattr(studio, "_lodging_shots", fake_shots)
    monkeypatch.setattr(studio, "_ask", fake_ask)
    return calls, lambda: asyncio.run(studio.make_lodging_body(studio.BodyBody(axis=AXIS, topic=topic)))


def _one(intro_desc, point_descs):
    return {"intro": {"name": "H1", "sub": "⭐구글 평점 4.4", "desc": intro_desc},
            "points": [{"sub": f"장점{i}", "desc": d} for i, d in enumerate(point_descs)]}


def test_body_prompt_has_no_raw_unknown_labels(monkeypatch):
    calls, run = _body_with(monkeypatch, "콘래드 오사카", 1,
                            [_one("40층 로비 호텔\n야경이 보입니다.", ["좋다\n정말", "넓다\n방", "조식\n맛"])])
    out = run()
    assert len(out["items"]) == 4 and len(calls) == 1
    prompt = calls[0]
    assert "확인 못 함" not in prompt and "미확인" not in prompt and "쟈란:" not in prompt
    assert "성급·요금 사실이 없다" in prompt                   # 없는 값은 지시로 말한다


def test_body_retries_once_then_ok(monkeypatch):
    bad = _one("40층 로비 호텔\n야경", ["쟈란 조회 최저가는 27만원대였어\n비싸", "넓다\n방", "조식\n맛"])
    good = _one("40층 로비 호텔\n야경", ["고층 바\n야경이 보입니다.", "넓다\n방", "조식\n맛"])
    calls, run = _body_with(monkeypatch, "콘래드 오사카", 1, [bad, good])
    out = run()
    assert len(calls) == 2
    assert "걸린 말" in calls[1] and "쟈란" in calls[1]       # 두 번째엔 걸린 이유를 붙였다
    assert all("쟈란" not in str(it.get("desc")) for it in out["items"])


def test_body_merges_only_bad_page_on_retry(monkeypatch):
    rows1 = {"items": [{"name": f"H{i}", "sub": "📍역 도보 3분", "desc": "좋은 호텔\n넓습니다."} for i in range(1, 9)]}
    rows1["items"][2]["desc"] = "성급·요금 미확인 호텔\n넓습니다."
    rows2 = {"items": [{"name": f"H{i}", "sub": "📍역 도보 3분", "desc": "다시 쓴 글\n최저가 비교"} for i in range(1, 9)]}
    rows2["items"][2]["desc"] = "역 앞 3성급 호텔\n넓습니다."
    calls, run = _body_with(monkeypatch, "도쿄 숙소 8곳", 8, [rows1, rows2])
    out = run()
    descs = [it["desc"] for it in out["items"]]
    assert descs[2] == "역 앞 3성급 호텔\n넓습니다."           # 걸린 장만 바꿔 끼웠다
    assert descs[0] == "좋은 호텔\n넓습니다."


def test_body_fails_when_retry_still_bad(monkeypatch):
    bad = _one("성급·요금 미확인 호텔\n야경", ["좋다\n정말", "넓다\n방", "조식\n맛"])
    calls, run = _body_with(monkeypatch, "콘래드 오사카", 1, [bad, bad])
    with pytest.raises(RuntimeError, match="출처·조회·얼버무림"):
        run()
    assert len(calls) == 2


# ─── 일본어 글자 (2026-10-16 「東銀座駅」 회차) ───────────────────────────────

def test_japanese_station_in_where_fails():
    faults = studio._lodging_faults([{"name": "미쓰이 가든 호텔 긴자고초메", "where": "📍東銀座駅 도보 1분",
                                      "desc": "東銀座駅에서 도보 1분, 대욕장 갖춘 2인 27만원대 호텔"}])
    assert faults == {0: ["일본어 「東銀座駅」"]}


def test_korean_station_passes_and_middle_dot_ok():
    assert studio._lodging_faults([{"name": "미쓰이 가든 호텔 긴자고초메", "where": "📍히가시긴자역 도보 1분",
                                    "desc": "대욕장・사우나 갖춘 2인 27만원대 호텔"}]) == {}


def test_verified_kanji_hotel_name_is_exempt_only_as_given():
    """구글 한국어 표기도 한자인 숙소(`旅館 由布山`)는 그 이름만 풀어 준다 — 다른 일본어는 여전히 걸린다."""
    pages = [{"name": "旅館 由布山", "where": "⭐구글 평점 4.1", "desc": "旅館 由布山 노천탕\n좋습니다."}]
    assert studio._lodging_faults(pages, ["旅館 由布山"]) == {}
    assert studio._lodging_faults(pages) != {}                 # 확인된 이름이 아니면 걸린다
    jalan_name = [{"name": "三井ガーデンホテル銀座五丁目", "desc": "좋다"}]
    assert studio._lodging_faults(jalan_name, ["미쓰이 가든 호텔 긴자고초메"]) != {}


def test_japanese_page_retried_then_fixed(monkeypatch):
    bad = _one("東銀座駅에서 도보 1분 호텔\n대욕장", ["좋다\n정말", "넓다\n방", "조식\n맛"])
    good = _one("히가시긴자역에서 도보 1분 호텔\n대욕장", ["좋다\n정말", "넓다\n방", "조식\n맛"])
    calls, run = _body_with(monkeypatch, "대욕장 있는 긴자 호텔, 미쓰이 가든 호텔 긴자고초메", 1, [bad, good])
    out = run()
    assert len(calls) == 2 and "東銀座駅" in calls[1]
    assert out["items"][0]["desc"].startswith("히가시긴자역")
    assert "히가시긴자역" in calls[0]                            # 처음부터 한국어 표기로 쓰라고 알렸다
