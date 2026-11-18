"""「<연예인>이 다녀간」 주제 — 가게를 X 근거에서 받는다 (2026-11-18 솔희 지시).

규칙은 `docs/process/일본맛집_1단계_주제후보.md` 「연예인이 다녀간 맛집」 이고,
여기서는 코드가 그 길로 가는지만 본다 — ① 모델에게 가게를 묻지 않는다
② 원문이 안 열리는 근거는 버린다 ③ 하나도 못 건지면 주제를 버린다.
"""

import asyncio

import pytest

from app.services import place_lookup as pl
from app.services import studio_steps as studio
from app.services import x_search


def _wire(monkeypatch, *, asked: list, parsed: list, live: list):
    async def fake_ask(*a, **kw):
        asked.append(a)
        return {"places": ["모델이 댄 가게"]}

    async def fake_search(request, max_searches=None):
        return "grok 답"

    async def fake_verify(items):
        return live

    async def fake_hits(*a, **kw):
        return []

    async def fake_verify_many(names, country="jp", limit=6):
        return [{"ok": True, "name": n, "place_id": f"id{n}", "address": f"a{n}", "rating": 4.6}
                for n in names]

    async def fake_reviews_many(places, cap=30, limit=12, terms=None, source=None):
        return [[{"text": "r"}] for _ in places]

    async def fake_screen(topic, places, revs, axis, want=0, kw=""):
        return places, revs, []

    monkeypatch.setattr(studio, "_ask", fake_ask)
    monkeypatch.setattr(studio, "_used_places", lambda axis: {})
    monkeypatch.setattr(studio, "_screen_places", fake_screen)
    monkeypatch.setattr(x_search, "is_available", lambda: True)
    monkeypatch.setattr(x_search, "search", fake_search)
    monkeypatch.setattr(x_search, "parse", lambda raw: parsed)
    monkeypatch.setattr(x_search, "verify", fake_verify)
    monkeypatch.setattr(pl, "hits_by_search", fake_hits)
    monkeypatch.setattr(pl, "verify_many", fake_verify_many)
    monkeypatch.setattr(pl, "reviews_many", fake_reviews_many)


def test_celeb_topic_takes_places_from_x_evidence(monkeypatch):
    asked: list = []
    posts = [{"post_id": "1", "url": "https://x.com/a/status/1", "title": "麺匠たか松 京都"},
             {"post_id": "2", "url": "https://x.com/b/status/2", "title": "喫茶ソワレ 京都"}]
    _wire(monkeypatch, asked=asked, parsed=posts, live=posts)

    good, _, _ = asyncio.run(studio._find_places("교토, 맛집, 아이유가 다녀간", "일본맛집", 8))

    names = [g["name"] for g in good]
    assert names == ["麺匠たか松 京都", "喫茶ソワレ 京都"]     # 근거에서 온 가게만
    assert not asked                                          # 모델에게 가게를 묻지 않았다
    assert [g["evidence"] for g in good] == ["https://x.com/a/status/1",
                                             "https://x.com/b/status/2"]


def test_dead_evidence_is_dropped(monkeypatch):
    """원문이 안 열리는 글은 `x_search.verify` 가 버린다 — 그 가게도 함께 빠진다."""
    posts = [{"post_id": "1", "url": "https://x.com/a/status/1", "title": "살아 있는 가게"},
             {"post_id": "2", "url": "https://x.com/b/status/2", "title": "지어낸 가게"}]
    _wire(monkeypatch, asked=[], parsed=posts, live=[posts[0]])

    good, _, _ = asyncio.run(studio._find_places("교토, 맛집, 아이유가 다녀간", "일본맛집", 8))

    assert [g["name"] for g in good] == ["살아 있는 가게"]


def test_no_evidence_drops_the_topic(monkeypatch):
    _wire(monkeypatch, asked=[], parsed=[], live=[])

    with pytest.raises(studio.TopicUnfit):
        asyncio.run(studio._find_places("교토, 맛집, 아이유가 다녀간", "일본맛집", 8))


def test_other_axis_keeps_the_old_path(monkeypatch):
    """`celeb_keyword` 가 없는 축은 길이 그대로다 — 같은 말이 와도 모델에게 묻는다."""
    asked: list = []
    _wire(monkeypatch, asked=asked, parsed=[], live=[])
    monkeypatch.setattr(studio, "_min_rating", lambda topic: None)

    good, _, _ = asyncio.run(studio._find_places("오사카, 편집샵, 아이유가 다녀간", "쇼핑", 7))

    assert asked                                              # 모델에게 물었다
    assert [g["name"] for g in good] == ["모델이 댄 가게"]
    assert all("evidence" not in g for g in good)
