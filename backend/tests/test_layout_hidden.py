"""layout_hidden 인코딩/디코딩 회귀 테스트.

DB 왕복은 dev 스택에서 실제로 검증했다(숨김 → 카탈로그 반영 → 원본 불변 → 해제).
여기서는 저장 포맷의 견고성만 고정한다 — 숨김은 부가 기능이라, 값이 손상돼도
목록 조회 자체가 죽으면 안 된다.

실행: cd backend && python -m pytest tests/test_layout_hidden.py -q
"""

from app.services.layout_hidden import _decode, _encode


def test_round_trip():
    keys = {(78, "썸네일"), (77, "grid_2x2")}
    assert _decode(_encode(keys)) == keys


def test_encoding_is_stable():
    """같은 집합이면 항상 같은 문자열 — 불필요한 쓰기를 막고 눈으로 확인하기 쉽다."""
    a = {(2, "b"), (1, "a")}
    b = {(1, "a"), (2, "b")}
    assert _encode(a) == _encode(b)


def test_korean_keys_are_not_escaped():
    """레이아웃 키는 한글이 흔하다. \\uXXXX 로 새면 DB 값을 눈으로 못 읽는다."""
    assert "썸네일" in _encode({(1, "썸네일")})


def test_empty():
    assert _decode("") == set()
    assert _decode(_encode(set())) == set()


def test_corrupt_values_do_not_raise():
    """깨진 값은 빈 집합으로 흘려보낸다 — 카탈로그 조회를 죽이지 않는다."""
    assert _decode("not json") == set()
    assert _decode("{}") == set()          # list 가 아님
    assert _decode("null") == set()
    assert _decode('[{"t":"x","k":"a"}]') == set()   # t 가 int 아님 → 건너뜀
    assert _decode('[{"t":1}]') == set()              # k 없음 → 건너뜀


def test_partial_corruption_keeps_good_entries():
    raw = '[{"t":1,"k":"a"},{"broken":true},{"t":2,"k":"b"}]'
    assert _decode(raw) == {(1, "a"), (2, "b")}
