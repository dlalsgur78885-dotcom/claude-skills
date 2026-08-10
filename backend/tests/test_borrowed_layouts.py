"""빌려온 낱장 참조 파싱 회귀 테스트.

DB 를 타는 resolve_borrowed_layouts 는 dev 스택에서 실제 템플릿으로 검증한다.
여기서는 파싱 규칙만 고정한다 — 로컬 키를 빌린 참조로 오인하면 렌더가 조용히
자동선택으로 떨어져서 원인 찾기가 어려워진다.

실행: cd backend && python -m pytest tests/test_borrowed_layouts.py -q
"""

from app.services.template_studio import parse_borrowed


def test_borrowed_reference():
    assert parse_borrowed("@42:썸네일") == (42, "썸네일")
    assert parse_borrowed("@7:grid_2x2") == (7, "grid_2x2")


def test_local_keys_are_not_treated_as_borrowed():
    """레이아웃 키는 사용자가 자유 작명한다. '@' 표식이 없으면 전부 로컬 키다."""
    for local in ("썸네일", "grid_2x2", "CTA", "2x2", "2:3 비율", "42:썸네일"):
        assert parse_borrowed(local) is None, local


def test_layout_key_may_contain_colon():
    """partition(':') 이라 키 안의 콜론은 살아남아야 한다."""
    assert parse_borrowed("@42:비율 2:3") == (42, "비율 2:3")


def test_malformed_references_are_rejected():
    assert parse_borrowed("@:썸네일") is None      # 템플릿 id 없음
    assert parse_borrowed("@42:") is None          # 키 없음
    assert parse_borrowed("@42") is None           # 구분자 없음
    assert parse_borrowed("@abc:썸네일") is None    # id 가 숫자 아님
    assert parse_borrowed("@") is None
    assert parse_borrowed("") is None
    assert parse_borrowed(None) is None
    assert parse_borrowed(123) is None
