"""값을 내세운 주제 — 금액 든 리뷰를 따로 받아 앞에 싣고, 값 없는 가게는 뺀다 (2026-11-18 솔희 신고).

규칙은 `docs/process/일본맛집_3-3단계_본문.md` 「가성비와 관련된 주제는 여덟 장 모두에 금액을
넣는다」·「가격 공개」 절이고, 여기서는 코드가 그 재료를 쥐어 주는지만 본다.
"""

import asyncio

from app.services import place_lookup as pl
from app.services import studio_steps as studio


def test_price_topic_detection():
    assert studio._price_topic("후쿠오카, 맛집, 가격 공개", "일본맛집")
    assert studio._price_topic("나고야, 카페, 가성비", "일본맛집")
    assert studio._price_topic("도쿄, 런치 오마카세, 5만원 이하", "일본맛집")
    assert not studio._price_topic("도쿄, 맛집, 줄서서먹는", "일본맛집")
    # 쇼핑·숙소·코스는 값 규칙이 따로 있다 — 이 길로 오지 않는다
    assert not studio._price_topic("오사카, 편집샵, 가성비", "쇼핑")
    assert not studio._price_topic("오사카, 가성비 호텔", "일본숙소")


def test_price_reviews_are_put_first(monkeypatch):
    async def fake_reviews_many(places, cap=30, limit=12, terms=None, source=None):
        assert terms == studio.PRICE_TERMS and source == "resolver"
        return [[{"text": "돈코츠 라멘 980엔에 먹었다"}, {"text": "값 얘기 없는 줄"}]]

    monkeypatch.setattr(pl, "reviews_many", fake_reviews_many)
    good = [{"name": "A"}]
    revs = [[{"text": "친절했어요"}]]

    out = asyncio.run(studio._price_reviews(good, revs))

    assert out[0][0]["text"] == "돈코츠 라멘 980엔에 먹었다"      # 값 든 줄이 맨 앞
    assert {"text": "친절했어요"} in out[0]                       # 원래 리뷰도 남는다
    assert {"text": "값 얘기 없는 줄"} not in out[0]              # 값 없는 검색 결과는 안 붙인다


def test_price_reviews_do_not_duplicate(monkeypatch):
    same = {"text": "세트 1,200円이면 싸다"}

    async def fake_reviews_many(places, cap=30, limit=12, terms=None, source=None):
        return [[same]]

    monkeypatch.setattr(pl, "reviews_many", fake_reviews_many)

    out = asyncio.run(studio._price_reviews([{"name": "A"}], [[same, {"text": "다른 줄"}]]))

    assert [r["text"] for r in out[0]] == ["세트 1,200円이면 싸다", "다른 줄"]


def test_places_without_price_are_dropped_above_the_floor():
    good = [{"name": f"가게{i}"} for i in range(8)]
    revs = [[{"text": "980엔"}] for _ in range(6)] + [[{"text": "맛있다"}], [{"text": "친절"}]]

    kept, kept_revs, note = studio._price_screen(good, revs, 5)

    assert [g["name"] for g in kept] == [f"가게{i}" for i in range(6)]
    assert len(kept_revs) == 6
    assert note == ""


def test_floor_wins_and_prompt_gets_a_warning():
    """값이 든 가게가 문턱보다 적으면 주제를 죽이지 않고 「지어내지 마라」를 붙인다."""
    good = [{"name": "값있음"}, {"name": "값없음1"}, {"name": "값없음2"}]
    revs = [[{"text": "¥980"}], [{"text": "조용함"}], [{"text": "넓다"}]]

    kept, _, note = studio._price_screen(good, revs, 5)

    assert len(kept) == 3
    assert "값없음1" in note and "값없음2" in note and "지어내지 마라" in note


def test_all_priced_keeps_everything():
    good = [{"name": "A"}, {"name": "B"}]
    revs = [[{"text": "1,000엔"}], [{"text": "500円"}]]

    assert studio._price_screen(good, revs, 5) == (good, revs, "")
