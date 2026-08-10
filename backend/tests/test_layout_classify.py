"""layout_classify 회귀 테스트.

케이스는 전부 prod DB 실측 구조에서 가져왔다 (템플릿 22개 / 레이아웃 60개).
숫자로 검증한 결과: 표지 22 · CTA 16 · 격자 12 · 본문·단일 10.

실행: cd backend && python -m pytest tests/test_layout_classify.py -q
"""

from app.services.layout_classify import classify, describe, grid_size


def _layout(bg_type="color", bg_value="", roles=(), grid=None):
    return {
        "background": {"type": bg_type, "value": bg_value},
        "decorations": [],
        "text_slots": [{"role": r} for r in roles],
        "grid": grid,
    }


# ── ② 격자 — 표현이 두 가지라 둘 다 격자로 잡혀야 한다 ──────────────────────

def test_grid_from_cell_roles_when_grid_spec_missing():
    """펼친 형태: grid=null + cell_*_r{행}c{열}. 실측 60개 중 다수가 이 형태."""
    spec = _layout(roles=["cell_title_r0c0", "cell_title_r0c1",
                          "cell_title_r1c0", "cell_title_r1c1"])
    assert classify(spec) == "grid"
    assert grid_size(spec) == (2, 2)


def test_grid_from_grid_spec_when_no_text_slots():
    """정식형: grid 스펙에 rows/cols, 셀 텍스트칸 없음.

    이걸 놓치면 '텍스트 없는 장면'으로 새어 CTA 로 오분류된다 (실제로 처음에 그랬다).
    """
    spec = _layout(roles=[], grid={"rows": 2, "cols": 2})
    assert classify(spec) == "grid"
    assert grid_size(spec) == (2, 2)


def test_grid_size_prefers_grid_spec_over_cell_roles():
    spec = _layout(roles=["cell_title_r0c0"], grid={"rows": 3, "cols": 3})
    assert grid_size(spec) == (3, 3)


def test_grid_label_is_width_first():
    """사용자는 격자를 가로×세로로 읽는다 (프론트 displayLayoutName 과 같은 규칙).
    내부는 행 우선이므로 rows=2,cols=1 은 '격자 1×2' 로 보여야 한다."""
    assert describe(_layout(roles=[], grid={"rows": 2, "cols": 1})) == "격자 1×2"


# ── ③ CTA ────────────────────────────────────────────────────────────────

def test_cta_button_role_wins():
    """phone_mockup — headline/subheadline 이 있어도 cta_button 이 있으면 CTA."""
    assert classify(_layout(roles=["headline", "subheadline", "cta_button"])) == "cta"


def test_empty_layout_without_background_image_is_cta():
    """CTA/cover — 편집할 텍스트도 배경 사진도 없는 장면. 내용이 전부 데코 이미지."""
    assert classify(_layout(bg_type="color", roles=[])) == "cta"
    assert classify(_layout(bg_type="image_keyword", bg_value="", roles=[])) == "cta"


# ── ④ 본문·단일 ───────────────────────────────────────────────────────────

def test_empty_layout_with_background_image_is_body():
    """single_image — CTA 와 구조가 거의 같고, 배경 키워드 유무만 다르다."""
    spec = _layout(bg_type="image_keyword", bg_value="snowy train station", roles=[])
    assert classify(spec) == "body"


def test_body_and_description_roles():
    assert classify(_layout(roles=["headline", "body"])) == "body"
    assert classify(_layout(roles=["headline", "description"])) == "body"


# ── ① 표지 ────────────────────────────────────────────────────────────────

def test_headline_only_is_cover():
    assert classify(_layout(roles=["headline"])) == "cover"


def test_fullbg_overlay_is_cover():
    spec = _layout(bg_type="image_keyword", bg_value="seoul night",
                   roles=["tag", "headline", "label", "subheadline"])
    assert classify(spec) == "cover"


def test_phone_mockup_without_cta_button_is_cover():
    """실측에 2개 있다. cta_button 이 없으면 구조상 표지가 맞다 — 오분류 아님."""
    assert classify(_layout(roles=["tag", "headline"])) == "cover"


# ── 견고성 ────────────────────────────────────────────────────────────────

def test_malformed_input_does_not_raise():
    assert classify(None) == "body"
    assert classify({}) == "cta"          # 텍스트도 배경도 없음
    assert grid_size({"grid": {"rows": "x", "cols": "y"}}) is None
    assert classify({"text_slots": "not-a-list"}) == "cta"
